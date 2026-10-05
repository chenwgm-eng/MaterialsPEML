"""ECML 7-step closed-loop scheduling engine with SQLAlchemy persistence and polymer branch."""

from enum import Enum
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone
import json
import hashlib
import re
import uuid
import logging
from pathlib import Path

import asyncio
import time
import threading

from sqlalchemy import text

from ..config import AgentConfig, EngineMode
from ..db import get_engine

logger = logging.getLogger(__name__)


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_async_safe(coro):
    """安全地在任意上下文中运行异步协程（兼容同步和异步调用场景）。

    - 无运行中的事件循环：直接 asyncio.run。
    - 已有运行中的事件循环：通过 run_coroutine_threadsafe 调度到该循环执行，
      避免在子线程创建新事件循环。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环，直接使用 asyncio.run
        return asyncio.run(coro)
    # 已有运行中的事件循环：调度到该循环执行，避免在子线程创建新循环
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


# ── Provenance source_type 规范化（Task 16） ────────────────────────────
# 统一的候选/预测来源标签集：
#   materials_project / gnome / local_db / internlm_generated /
#   algorithm_generated / mixed
# 原始 source 字段（来自 crystal_candidate_generator / polymer_candidate_generator
# 的字符串）按下方映射归一到上述规范标签。
_SOURCE_TYPE_MAP = {
    # Materials Project API
    "materials_project": "materials_project",
    "mp": "materials_project",
    # GNoME 数据（无论来自 MP 镜像还是本地静态数据集）
    "gnome": "gnome",
    "gnome_mp_mirror": "gnome",
    "gnome_local": "gnome",
    # 本地数据库 / 已知库（含聚合物已知库）
    "local_db": "local_db",
    "local_database": "local_db",
    "local_db_fallback": "local_db",
    "local": "local_db",
    "known": "local_db",
    # InternLM LLM 生成
    "internlm": "internlm_generated",
    "internlm_generated": "internlm_generated",
    "llm_generated": "internlm_generated",
    # 算法生成（规则引擎/衍生/兜底 demo）
    "algorithm_generated": "algorithm_generated",
    "rule_based": "algorithm_generated",
    "derivative": "algorithm_generated",
    "demo": "algorithm_generated",
}


def _normalize_source_type(raw_source: str) -> str:
    """将候选原始 source 字符串映射为规范 source_type 标签。

    未知/空值统一归到 algorithm_generated（兜底，不误标为 internlm）。
    """
    if not raw_source:
        return "algorithm_generated"
    return _SOURCE_TYPE_MAP.get(raw_source, "algorithm_generated")


def _candidate_source_type(candidate: dict) -> str:
    """根据候选的 source 字段与已有 provenance 推断规范 source_type。

    若候选来自多个来源（provenance 中存在多种 source），返回 "mixed"。
    """
    sources: set[str] = set()
    raw_source = candidate.get("source", "") or ""
    if raw_source:
        sources.add(_normalize_source_type(raw_source))
    provenance = candidate.get("provenance") or []
    for p in provenance:
        if not isinstance(p, dict):
            continue
        # provenance 条目可能用 'source' 或 'source_type' 键
        s = p.get("source_type") or p.get("source") or ""
        if s:
            sources.add(_normalize_source_type(s))
    if not sources:
        return "algorithm_generated"
    if len(sources) > 1:
        return "mixed"
    return sources.pop()


def _attach_candidate_provenance(candidate: dict, config: AgentConfig | None) -> None:
    """为候选补全规范 provenance（原地修改）。

    - 顶层写入 source_type 字段（前端读这个字段）
    - provenance 列表为空时，补一条带规范 source_type 的入口
    - 已有 provenance 条目（如 generator 写入的 {source, material_id}）
      归一化为 source_type，保留 material_id 等额外字段
    """
    source_type = _candidate_source_type(candidate)
    candidate["source_type"] = source_type
    provenance = candidate.get("provenance")
    if not provenance:
        # 候选无 provenance，补一条规范入口
        model_or_tool = (
            config.internlm.model if config is not None and source_type == "internlm_generated"
            else source_type
        )
        candidate["provenance"] = [{
            "source_type": source_type,
            "provider": source_type,
            "model_or_tool": model_or_tool,
            "evidence_level": "computed",
        }]
        return
    # 已有 provenance 条目：补全 source_type 字段（保留原始 source 键以保向后兼容）
    for p in provenance:
        if not isinstance(p, dict):
            continue
        if "source_type" not in p:
            raw_s = p.get("source", "") or ""
            p["source_type"] = _normalize_source_type(raw_s) if raw_s else source_type
    # 多来源时，顶层 source_type 标为 mixed
    unique_types = {p.get("source_type") for p in provenance if isinstance(p, dict) and p.get("source_type")}
    if len(unique_types) > 1:
        candidate["source_type"] = "mixed"


class ECMLStep(str, Enum):
    STEP1_ROUTE = "step1_route"
    STEP2_GENERATE = "step2_generate"
    STEP3_SYNTHESIS_CHECK = "step3_synthesis_check"
    STEP3_INDUSTRIALIZATION = "step3_industrialization"
    STEP4_PREDICT = "step4_predict"
    STEP5_VERIFY = "step5_verify"
    STEP6_EXPERIMENT = "step6_experiment"
    WAITING_FOR_DATA = "waiting_for_data"
    STEP7_FEEDBACK = "step7_feedback"


PROPERTY_DIRECTION = {
    'formation_energy': 'minimize',
    'band_gap': 'maximize',
    'ionic_conductivity': 'maximize',
    'total_energy': 'minimize',
}
# 注：保留本地 PROPERTY_DIRECTION 字典是为了向后兼容（部分测试与外部代码可能直接引用）。
# 完整的属性方向字典请参考 material_properties.PROPERTY_DIRECTION，新代码应优先使用它。


def _get_property_direction(key: str) -> str:
    """获取属性优化方向，优先使用 material_properties 统一字典，回退到本地字典，默认 maximize。"""
    try:
        from ..material_properties import PROPERTY_DIRECTION as _UNIFIED
        return _UNIFIED.get(key, 'maximize')
    except ImportError:
        return PROPERTY_DIRECTION.get(key, 'maximize')


def _parse_llm_json(content: str) -> dict:
    """容错解析 LLM 返回的 JSON。

    LLM 可能返回：
    - 纯 JSON：{"value": 1.5, "unit": "eV"}
    - 带 markdown 标记：```json\n{...}\n```
    - 带额外文本：Here is the result: {...}
    - 思考链前缀：<think>...</think>{...}
    - 截断的 JSON（max_tokens 用尽）：{"value": 1.5, "reasoning": "Li7La3Zr...

    解析策略：
    1. 去除 markdown 代码块标记
    2. 去除 <think>...</think> 思考链
    3. 尝试直接 json.loads
    4. 失败则截取最外层 {..} 子串再解析
    5. 仍失败则用正则逐字段提取（处理截断的 JSON）
    """
    import re

    text = content.strip()

    # 去除 <think>...</think> 思考链
    if "<think>" in text and "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()

    # 去除 markdown 代码块标记（处理未闭合的 ``` 情况）
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行 ```json 或 ```
        start = 1
        end = len(lines)
        if lines[-1].strip() == "```":
            end = -1
        text = "\n".join(lines[start:end]).strip()

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 截取最外层 {..} 子串
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # 截断 JSON 容错：用正则逐字段提取
    # 场景：max_tokens 用尽，reasoning 字段被截断，JSON 不完整
    extracted: dict = {}
    # value 字段（支持整数、浮点、科学计数法）
    value_match = re.search(r'"value"\s*:\s*([0-9eE.+-]+)', text)
    if value_match:
        try:
            extracted["value"] = float(value_match.group(1))
        except ValueError:
            pass
    # unit 字段
    unit_match = re.search(r'"unit"\s*:\s*"([^"]*)"', text)
    if unit_match:
        extracted["unit"] = unit_match.group(1)
    # confidence 字段
    conf_match = re.search(r'"confidence"\s*:\s*([0-9eE.+-]+)', text)
    if conf_match:
        try:
            extracted["confidence"] = float(conf_match.group(1))
        except ValueError:
            pass
    # reasoning 字段（可能被截断，取到行尾或下一个字段）
    reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*)', text)
    if reasoning_match:
        extracted["reasoning"] = reasoning_match.group(1) + ("" if text.endswith('"') else "...[truncated]")

    if "value" in extracted:
        logger.debug("Parsed truncated LLM JSON via regex: %s", extracted)
        return extracted

    raise ValueError(f"Failed to parse LLM response as JSON: {content[:300]}")


# ===========================================================================
# SQLite 持久化层
# ===========================================================================

class ECMLStateStore:
    """ECML 运行状态的 SQLAlchemy 持久化，支持跨会话恢复。

    Schema 由 alembic 管理（ecml.ecml_runs / ecml.ecml_runs_index）。
    """

    def __init__(self, db_path: str | None = None):
        # db_path 参数已废弃：统一通过 get_engine() 获取 Engine。
        self.engine = get_engine()

    # 无意义调试目标命名：命中即判定为系统测试数据（P0-4 垃圾数据隔离）
    _TEST_TARGET_PATTERN = re.compile(
        r"^(test|demo|debug|tmp|temp|tst|asdf|qwer|aaa|abc|123|111|xxx)[\s\-_]*\d*$",
        re.IGNORECASE,
    )

    @classmethod
    def _infer_run_source(cls, target: str) -> str:
        """根据运行目标推断数据来源：production（生产研发）/ test（系统测试）。"""
        t = (target or "").strip()
        if not t:
            return "test"
        if cls._TEST_TARGET_PATTERN.match(t):
            return "test"
        return "production"

    def save(self, run_id: str, target: str, target_property: str, state: "ECMLState") -> str:
        """保存（或更新）一个 ECML 运行状态。

        注意：ecml.ecml_runs_index 表无 PRIMARY KEY，使用 DELETE + INSERT 模式避免重复 run_id 累积。
        """
        now = datetime.now(timezone.utc).isoformat()
        state_json = state.model_dump_json()
        run_source = self._infer_run_source(target)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO ecml.ecml_runs
                    (run_id, target, target_property, state_json, created_at, updated_at, run_source)
                    VALUES (:run_id, :target, :target_property, :state_json,
                            COALESCE((SELECT created_at FROM ecml.ecml_runs WHERE run_id=:run_id_for_created), :now),
                            :now, :run_source)
                    ON CONFLICT (run_id) DO UPDATE SET
                        target = EXCLUDED.target,
                        target_property = EXCLUDED.target_property,
                        state_json = EXCLUDED.state_json,
                        updated_at = EXCLUDED.updated_at,
                        run_source = EXCLUDED.run_source"""
                ),
                {
                    "run_id": run_id,
                    "target": target,
                    "target_property": target_property,
                    "state_json": state_json,
                    "run_id_for_created": run_id,
                    "now": now,
                    "run_source": run_source,
                },
            )
            # 先读取旧的 created_at（DELETE 前），再删除旧行，再插入新行
            row = conn.execute(
                text("SELECT created_at FROM ecml.ecml_runs_index WHERE run_id=:run_id LIMIT 1"),
                {"run_id": run_id},
            ).first()
            old_created_at = row[0] if row else now
            conn.execute(
                text("DELETE FROM ecml.ecml_runs_index WHERE run_id=:run_id"),
                {"run_id": run_id},
            )
            conn.execute(
                text(
                    """INSERT INTO ecml.ecml_runs_index
                    (run_id, status, iteration, is_complete, created_at, run_status, iteration_id, parent_run_id, scenario_id, task_id, project_id)
                    VALUES (:run_id, :status, :iteration, :is_complete, :created_at,
                            :run_status, :iteration_id, :parent_run_id, :scenario_id, :task_id, :project_id)"""
                ),
                {
                    "run_id": run_id,
                    "status": state.current_step.value,
                    "iteration": state.iteration,
                    "is_complete": bool(state.is_complete),
                    "created_at": old_created_at,
                    "run_status": state.status,
                    "iteration_id": state.iteration_id,
                    "parent_run_id": state.parent_run_id,
                    "scenario_id": state.scenario_id or "",
                    # FK 约束：空字符串需转为 NULL
                    "task_id": (state.task_id or None),
                    # 业务隔离：本项目/跨项目过滤（无则 NULL）
                    "project_id": (state.project_id or None),
                },
            )
        return run_id

    def load(self, run_id: str) -> "ECMLState | None":
        """恢复一个运行状态。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT state_json FROM ecml.ecml_runs WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).first()
        if row is None:
            return None
        data = row[0]
        if isinstance(data, dict):
            return ECMLState.model_validate(data)
        return ECMLState.model_validate_json(data)

    # 僵尸运行判定阈值：超过该时长未更新且未完成的运行视为超时
    _STALE_TIMEOUT_SECONDS = 3600  # 1 小时

    @staticmethod
    def _parse_updated_at(updated_at) -> datetime | None:
        """将 updated_at 解析为带时区的 datetime。

        兼容两种来源：
        - PostgreSQL TIMESTAMP 字段：SQLAlchemy 返回 datetime 对象（可能无时区）；
        - SQLite/JSON 字段：返回 ISO 字符串（可能以 Z 结尾）。
        """
        if not updated_at:
            return None
        if isinstance(updated_at, datetime):
            return updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
        if isinstance(updated_at, str):
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _backfill_run_source(self, conn) -> None:
        """懒迁移：历史记录的 run_source 为空时按 target 推断回填，保证隔离口径一致。"""
        stale_rows = conn.execute(
            text("SELECT run_id, target FROM ecml.ecml_runs WHERE run_source IS NULL OR run_source=''")
        ).all()
        for run_id, target in stale_rows:
            conn.execute(
                text("UPDATE ecml.ecml_runs SET run_source=:run_source WHERE run_id=:run_id"),
                {"run_source": self._infer_run_source(target), "run_id": run_id},
            )

    def list_runs(self, limit: int = 20, project_id: str = "") -> list[dict]:
        """列出最近的运行（按更新时间倒序）。

        对于长时间未更新且未完成的运行，自动标记为 timeout，
        避免运行历史中出现永久"进行中"的僵尸记录。
        project_id 非空时仅返回该项目的运行（:project_id='' 表示不过滤）。
        """
        now_dt = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            self._backfill_run_source(conn)
            # 子查询：每个 run_id 仅取 index 表中最新一行，避免历史重复数据导致行重复
            rows = conn.execute(
                text(
                    """SELECT r.run_id, r.target, r.target_property, r.updated_at,
                              i.iteration, i.is_complete, i.run_status, i.iteration_id, i.parent_run_id,
                              r.run_source, i.scenario_id, i.project_id
                       FROM ecml.ecml_runs r
                       LEFT JOIN (
                           SELECT run_id, iteration, is_complete, run_status, iteration_id, parent_run_id, scenario_id, project_id
                           FROM ecml.ecml_runs_index
                           WHERE ctid IN (
                               SELECT MAX(ctid) FROM ecml.ecml_runs_index GROUP BY run_id
                           )
                       ) i ON r.run_id = i.run_id
                       WHERE (:project_id = '' OR i.project_id = :project_id)
                       ORDER BY r.updated_at DESC LIMIT :limit"""
                ),
                {"limit": limit, "project_id": project_id or ""},
            ).all()
            # 检测并修复僵尸运行：未完成 + 长时间未更新 + 状态仍为 running
            for r in rows:
                is_complete = bool(r[5])
                run_status = r[6] or "running"
                updated_at = r[3]
                if is_complete or run_status != "running":
                    continue
                try:
                    updated_dt = self._parse_updated_at(updated_at)
                    if updated_dt is None:
                        continue
                    age = (now_dt - updated_dt).total_seconds()
                except (ValueError, AttributeError, TypeError):
                    continue
                if age > self._STALE_TIMEOUT_SECONDS:
                    conn.execute(
                        text("UPDATE ecml.ecml_runs_index SET run_status=:run_status WHERE run_id=:run_id"),
                        {"run_status": "timeout", "run_id": r[0]},
                    )
        return [
            {
                "run_id": r[0], "target": r[1], "target_property": r[2],
                "updated_at": r[3], "iteration": r[4] or 0,
                "is_complete": bool(r[5]),
                "status": r[6] or "running",
                "iteration_id": r[7] or 1,
                "parent_run_id": r[8] or "",
                "run_source": r[9] or "production",
                "scenario_id": r[10] or "",
                "project_id": r[11] or "",
            }
            for r in rows
        ]

    def _is_stale(self, updated_at) -> bool:
        """判断 updated_at 是否超过僵尸阈值。"""
        if not updated_at:
            return False
        updated_dt = self._parse_updated_at(updated_at)
        if updated_dt is None:
            return False
        age = (datetime.now(timezone.utc) - updated_dt).total_seconds()
        return age > self._STALE_TIMEOUT_SECONDS

    def delete(self, run_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM ecml.ecml_runs WHERE run_id=:run_id"),
                {"run_id": run_id},
            )
            conn.execute(
                text("DELETE FROM ecml.ecml_runs_index WHERE run_id=:run_id"),
                {"run_id": run_id},
            )
        return cur.rowcount > 0

    def bulk_delete(self, run_ids: list[str]) -> int:
        """批量删除运行记录，返回实际删除条数（P0-4 垃圾数据批量清理）。"""
        if not run_ids:
            return 0
        deleted = 0
        with self.engine.begin() as conn:
            for run_id in run_ids:
                cur = conn.execute(
                    text("DELETE FROM ecml.ecml_runs WHERE run_id=:run_id"),
                    {"run_id": run_id},
                )
                conn.execute(
                    text("DELETE FROM ecml.ecml_runs_index WHERE run_id=:run_id"),
                    {"run_id": run_id},
                )
                deleted += cur.rowcount
        return deleted

    def get_run_stats(self) -> dict:
        """运行统计（P0-1 统一口径）：默认排除 test 数据，与二级页面"正式"视图一致。

        返回 {total, active, completed_30d, test_total}：
        - total: 正式运行总数
        - active: 进行中（未完成且状态为 running）
        - completed_30d: 近 30 天完成的运行数
        - test_total: 被隔离的测试数据条数（供治理入口展示）
        """
        now_dt = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            self._backfill_run_source(conn)
            total = conn.execute(
                text("SELECT COUNT(*) FROM ecml.ecml_runs WHERE run_source != 'test'")
            ).scalar()
            test_total = conn.execute(
                text("SELECT COUNT(*) FROM ecml.ecml_runs WHERE run_source = 'test'")
            ).scalar()
            active = conn.execute(
                text(
                    """SELECT COUNT(*) FROM ecml.ecml_runs r
                       WHERE r.run_source != 'test' AND EXISTS (
                           SELECT 1 FROM ecml.ecml_runs_index i
                           WHERE i.run_id = r.run_id AND i.is_complete = false
                             AND i.run_status = 'running'
                       )"""
                )
            ).scalar()
            rows = conn.execute(
                text(
                    """SELECT r.updated_at FROM ecml.ecml_runs r
                       WHERE r.run_source != 'test' AND EXISTS (
                           SELECT 1 FROM ecml.ecml_runs_index i
                           WHERE i.run_id = r.run_id AND i.is_complete = true
                       )"""
                )
            ).all()
        completed_30d = 0
        for (updated_at,) in rows:
            try:
                dt = _to_datetime(updated_at)
                if dt and (now_dt - dt).days < 30:
                    completed_30d += 1
            except (ValueError, AttributeError, TypeError):
                continue
        return {
            "total": total,
            "active": active,
            "completed_30d": completed_30d,
            "test_total": test_total,
        }


class ECMLState(BaseModel):
    run_id: str = ""  # 持久化运行 ID（空表示新建）
    current_step: ECMLStep = ECMLStep.STEP1_ROUTE
    iteration: int = 0
    material_branch: str = ""
    target: str = ""  # 路由目标材料（化学式或 SMILES）
    target_property: str = ""
    target_properties: list[dict] = Field(default_factory=list)  # 多目标配置：[{property, weight, direction, min, max}]
    require_elements: list[str] = Field(default_factory=list)  # P0-4：必需包含的元素符号
    exclude_elements: list[str] = Field(default_factory=list)  # P0-4：必须排除的元素符号
    candidates: list[dict] = Field(default_factory=list)
    synthesizable: list[dict] = Field(default_factory=list)
    predictions: list[dict] = Field(default_factory=list)
    verified: list[dict] = Field(default_factory=list)
    experiment_results: list[dict] = Field(default_factory=list)
    feedback: dict[str, Any] = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)
    is_complete: bool = False
    status: str = "running"  # running, completed, timeout, degraded
    completed_at: str = ""
    max_iterations: int = 3
    start_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    iteration_id: int = 1  # 当前迭代轮次（跨 run 的迭代链）
    parent_run_id: str = ""  # 父轮次 run_id，用于迭代链追溯
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    project_id: str = ""  # 业务链路：关联研发项目 ID，用于"本项目/跨项目"数据隔离
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)，由 0009 迁移新增列
    next_round_suggestions: dict[str, Any] = Field(default_factory=dict)  # 下一轮候选建议
    external_invocation_ids: list[str] = Field(default_factory=list)
    committee_cases: list[dict] = Field(default_factory=list)  # 委员会案例记录
    committee_verdicts: list[dict] = Field(default_factory=list)  # 委员会裁决记录
    execution_profile: str = "standard"  # ExecutionProfile 值，由 run() 自动推断


class ECMLEngine:
    """7-step ECML closed-loop scheduling engine with polymer branch dispatch."""

    def __init__(self, router=None, generator=None, synthesis_planner=None,
                 predictor=None, verifier=None, experiment_controller=None,
                 middleware=None, polymer_generator=None, polymer_predictor=None,
                 state_store=None, config: AgentConfig | None = None,
                 formula_agent=None,
                 compliance_node=None,
                 feasibility_screener=None,
                 approval_engine=None,
                 llm_provider=None,
                 committee_coordinator=None,
                 run_manager=None,
                 tool_gateway=None,
                 candidate_store=None,
                 domain_thresholds: dict | None = None):
        self.router = router
        self.generator = generator  # 晶体生成器
        self.polymer_generator = polymer_generator  # 聚合物生成器
        self.synthesis_planner = synthesis_planner
        self.predictor = predictor  # 晶体预测器
        self.polymer_predictor = polymer_predictor  # 聚合物预测器
        self.verifier = verifier
        self.experiment_controller = experiment_controller
        self.middleware = middleware
        self.candidate_store = candidate_store  # 候选材料持久化存储
        self.config = config
        self.formula_agent = formula_agent
        self.compliance_node = compliance_node
        self.feasibility_screener = feasibility_screener
        self.approval_engine = approval_engine
        # v4.1：领域包覆盖的达标阈值（ADR-0003 配套，企业可按自家规格覆盖默认值）
        self._domain_thresholds: dict = dict(domain_thresholds or {})
        self._llm_provider = llm_provider
        self._committee_coordinator = committee_coordinator  # lazy-init if None
        # Mirror attribute (without underscore) used by steps 3/4/5/7 trigger checks.
        # Always set so AttributeError is not raised when committee is disabled.
        self.committee_coordinator = committee_coordinator
        # SQLite 持久化（默认 data/ecml_states.db）
        self.state_store = state_store or ECMLStateStore()
        self._ingested_samples: set[str] = set()
        self._ingested_lock = threading.Lock()  # 保护 _ingested_samples 跨线程并发写入
        # Control Plane integration (optional) — durable runs + tool gateway.
        self._run_manager = run_manager
        self._tool_gateway = tool_gateway
        self._current_run_id: str | None = None
        # P1-2：Agent 调用事件日志（可选，由 API 启动时注入）
        self._agent_event_log = None
        # 决策 7-A：AgentProxy 注入（业务活动→智能体→工具的代理层）
        # 为 None 时回退到原直接调用模式，保证向后兼容
        self._agent_proxy = None

    # P1-2：ECML 步骤 → 负责 Agent 映射（用于统一 Agent 调用事件日志）
    # 决策 1-C：activity_id 用于 AgentProxy 查找绑定的智能体+工具
    _STEP_AGENT_MAP = {
        "step1_route": ("builtin_material_router", "材料路由调度员", "ecml.step1_route"),
        "step2_generate": ("builtin_material_discovery", "首席材料学家", "ecml.step2_generate"),
        "step3_industrialization": ("builtin_industrialization", "配方工艺师", "ecml.step3_industrialization"),
        "step4_predict": ("builtin_battery_oracle", "材料性质预言者", "ecml.step4_predict"),
        "step5_verify": ("builtin_dft_verifier", "DFT 计算专家", "ecml.step5_verify"),
        "step6_experiment": ("builtin_experiment_analyst", "实验数据分析员", "ecml.step6_experiment"),
        "step7_feedback": ("builtin_battery_learner", "材料数据学习者", "ecml.step7_feedback"),
    }

    def _log_agent_event(
        self,
        step_name: str,
        run_id: str,
        duration_ms: int,
        status: str,
        input_summary: dict | None = None,
        output_summary: dict | None = None,
        agent_binding: dict | None = None,
    ) -> None:
        """写入一条 Agent 调用事件；任何失败都不影响主流程。

        决策 3-C：agent_binding 携带智能体+工具绑定信息，写入 input_summary 供前端展示。
        """
        if self._agent_event_log is None:
            return
        step_map = self._STEP_AGENT_MAP.get(step_name, ("unknown", "", ""))
        agent_id = step_map[0]
        agent_name = step_map[1]
        # 决策 3-C：将绑定信息合并到 input_summary
        effective_input = dict(input_summary or {})
        if agent_binding:
            effective_input["_agent_binding"] = agent_binding
        try:
            self._agent_event_log.log_event(
                agent_id=agent_id,
                agent_name=agent_name,
                related_run_id=run_id,
                step=step_name,
                input_summary=effective_input,
                output_summary=output_summary,
                duration_ms=duration_ms,
                status=status,
            )
        except Exception as e:
            logger.debug("Agent event log failed: %s", e)

    def _run_step_with_event(self, state: ECMLState, step_name: str,
                             input_summary: dict, fn, *args) -> ECMLState:
        """执行一个 ECML 步骤并记录 Agent 调用事件（P1-2 统一事件日志）。

        决策 3-C：附加智能体+工具绑定信息到事件日志，供前端步骤流概览显示。
        决策 7-A：通过 AgentProxy 解析绑定关系（注入时），未注入时回退到 _STEP_AGENT_MAP。
        """
        started = time.monotonic()
        # 决策 3-C：解析本次步骤的智能体+工具绑定（v4.1 按材料分支修正工具展示名）
        agent_binding_info = self._resolve_agent_binding_for_step(
            step_name, getattr(state, "material_branch", "") or "")
        try:
            new_state = fn(state, *args)
        except Exception:
            self._log_agent_event(
                step_name, state.run_id, int((time.monotonic() - started) * 1000),
                "failed", input_summary=input_summary,
                agent_binding=agent_binding_info,
            )
            raise
        duration_ms = int((time.monotonic() - started) * 1000)
        output_summary = {
            "candidates": len(new_state.candidates or []),
            "synthesizable": len(new_state.synthesizable or []),
            "predictions": len(new_state.predictions or []),
            "verified": len(new_state.verified or []),
            "experiment_results": len(new_state.experiment_results or []),
        }
        self._log_agent_event(
            step_name, new_state.run_id, duration_ms, "success",
            input_summary=input_summary, output_summary=output_summary,
            agent_binding=agent_binding_info,
        )
        # 决策 3-C：将绑定信息附加到 state.history，供前端步骤流抽屉显示
        if hasattr(new_state, 'history') and isinstance(new_state.history, list) and new_state.history:
            last_step = new_state.history[-1]
            if isinstance(last_step, dict):
                last_step["agent_binding"] = agent_binding_info
        return new_state

    def _resolve_agent_binding_for_step(self, step_name: str,
                                        branch: str = "") -> dict:
        """决策 3-C：解析步骤的智能体+工具绑定信息。

        通过 AgentProxy 查询 activity_id 对应的智能体和主工具绑定。
        v4.1：polymer 分支下 generate/predict 步骤按实际执行工具展示
        （generate_polymer_candidates / predict_polymer_properties），
        避免事件日志显示晶体工具名与实际执行不一致。
        """
        mapping = self._STEP_AGENT_MAP.get(step_name)
        if not mapping:
            return {}
        agent_id, agent_name, activity_id = mapping

        # 按分支修正工具 id：DB 绑定表仅配置了晶体工具（历史遗留），
        # polymer 分支实际执行聚合物工具，展示需与执行一致
        is_polymer = "polymer" in (branch or "").lower()
        _BRANCH_TOOL_OVERRIDE = {
            ("step2_generate", True): ("generate_polymer_candidates", "聚合物候选生成"),
            ("step4_predict", True): ("predict_polymer_properties", "聚合物性质预测"),
        }
        override = _BRANCH_TOOL_OVERRIDE.get((step_name, is_polymer))

        binding_info = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "activity_id": activity_id,
            "tool_id": "",
            "tool_name": "",
            "capability": "",
            "used_fallback": False,
        }

        if override:
            binding_info["tool_id"] = override[0]
            binding_info["tool_name"] = override[1]
            binding_info["used_fallback"] = True
            return binding_info

        if self._agent_proxy is None:
            return binding_info

        try:
            mapping_store = self._agent_proxy._mapping_store
            # 查业务活动→智能体绑定
            activity_binding = mapping_store.get_agent_for_activity(activity_id)
            if activity_binding:
                binding_info["capability"] = activity_binding.capability_need
                # 查智能体→主工具绑定
                tool_binding = mapping_store.get_tool_binding(
                    agent_id, activity_binding.capability_need
                )
                if tool_binding:
                    binding_info["tool_id"] = tool_binding.primary_tool_id
                    tool_reg = mapping_store.get_tool_registration(tool_binding.primary_tool_id)
                    if tool_reg:
                        binding_info["tool_name"] = tool_reg.name
        except Exception as e:
            logger.debug("Resolve agent binding for step %s failed: %s", step_name, e)

        return binding_info

    def run(self, target: str, target_property: str = "tensile_strength",
            max_iterations: int = 3, run_id: str = "",
            target_properties: list[dict] | None = None,
            parent_run_id: str = "",
            scenario_id: str = "",
            task_id: str = "",
            project_id: str = "") -> ECMLState:
        """运行 ECML 闭环。

        run_id 可选：传入已有的 run_id 可恢复中断的运行；否则生成新 ID。
        target_properties 可选：多目标配置列表，非空时启用多目标加权优化。
        parent_run_id 可选：父轮次 run_id，用于迭代链追溯，非空时 iteration_id = 父轮 + 1。
        scenario_id 可选：关联研发场景 ID，用于端到端数据闭环。
        task_id 可选：关联 projects.tasks(task_id)，写入 ecml_runs_index 供 stage-status 反查。
        """
        # 自动推断 execution_profile（在创建 state 之前）
        from ..config import ExecutionProfile, engine_mode_to_execution_profile
        if self.config is not None:
            execution_profile = engine_mode_to_execution_profile(self.config.engine_mode)
        else:
            execution_profile = ExecutionProfile.STANDARD
        # 如果 target 包含高精度/DFT 关键词，升级为 committee_governed
        target_str = str(target).lower()
        if any(kw in target_str for kw in ["dft", "高精度", "高精度计算", "committee", "委员会"]):
            execution_profile = ExecutionProfile.COMMITTEE_GOVERNED
        elif self.config is not None and self.config.engine_mode == EngineMode.INTERNLM:
            execution_profile = ExecutionProfile.INTERNLM_ASSISTED

        # 尝试恢复已有运行
        if run_id and self.state_store is not None:
            existing = self.state_store.load(run_id)
            if existing is not None:
                # 已完成的运行直接返回
                if existing.is_complete:
                    return existing
                # 否则从断点继续（保留 history 和 feedback）
                state = existing
                # 断点恢复时若传入了 task_id，补充写入（避免历史 run 缺 task_id）
                if task_id and not state.task_id:
                    state.task_id = task_id
                # 断点恢复时若传入了 project_id，补充写入（避免历史 run 缺 project_id）
                if project_id and not state.project_id:
                    state.project_id = project_id
            else:
                state = self._create_new_state(run_id, target_property, max_iterations, parent_run_id, scenario_id, task_id, project_id)
        else:
            state = self._create_new_state(run_id, target_property, max_iterations, parent_run_id, scenario_id, task_id, project_id)

        # 将 execution_profile 存入 state
        state.execution_profile = execution_profile.value

        # 写入多目标配置（断点恢复时若未传入则保留已有配置）
        if target_properties is not None:
            state.target_properties = target_properties

        # 断点恢复：从已完成迭代的下一轮开始，避免重跑
        start_iter = state.iteration if not state.is_complete and state.iteration > 0 else 0
        # 使用持久化的 state.start_time，确保跨断点恢复也能累计超时
        try:
            start_dt = _to_datetime(state.start_time)
            start_time = start_dt.timestamp()
        except (ValueError, AttributeError, TypeError):
            state.start_time = datetime.now(timezone.utc).isoformat()
            start_time = time.time()
        timeout = 300  # 5分钟超时

        # ── Control Plane: create durable run ──
        cp_run_id = self._cp_create_run(state)

        try:
            for iteration in range(start_iter, max_iterations):
                # 如果从断点恢复，且已完成的迭代数已达到 max，跳过
                if state.iteration >= max_iterations and state.is_complete:
                    break
                state.iteration = iteration + 1
                state.history.append({
                    "iteration": iteration + 1,
                    "step": "start",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # 超时检查（基于持久化的开始时间）
                if time.time() - start_time > timeout:
                    state.is_complete = True
                    state.status = "timeout"
                    state.completed_at = datetime.now(timezone.utc).isoformat()
                    state.history.append({"step": "timeout", "message": f"执行超时 ({timeout}s)"})
                    if self.state_store is not None:
                        self.state_store.save(state.run_id, target, target_property, state)
                    break

                self.write_checkpoint("step1_route", iteration * 10 + 1, {"target": target})
                state = self._run_step_with_event(state, "step1_route", {"target": target}, self._step1_route, target)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break

                self.write_checkpoint("step2_generate", iteration * 10 + 2, {"candidates": len(state.candidates)})
                state = self._run_step_with_event(state, "step2_generate", {"target": state.target}, self._step2_generate)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break

                self.write_checkpoint("step3_industrialization", iteration * 10 + 3, {"synthesizable": len(state.synthesizable)})
                state = self._run_step_with_event(state, "step3_industrialization", {"candidates": len(state.candidates)}, self._step3_industrialization)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break

                self.write_checkpoint("step4_predict", iteration * 10 + 4, {"predictions": len(state.predictions)})
                state = self._run_step_with_event(state, "step4_predict", {"synthesizable": len(state.synthesizable)}, self._step4_predict)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break

                self.write_checkpoint("step5_verify", iteration * 10 + 5, {"verified": len(state.verified)})
                state = self._run_step_with_event(state, "step5_verify", {"predictions": len(state.predictions)}, self._step5_verify)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break

                self.write_checkpoint("step6_experiment", iteration * 10 + 6, {"experiment_results": len(state.experiment_results)})
                state = self._run_step_with_event(state, "step6_experiment", {"verified": len(state.verified)}, self._step6_experiment)
                state = self._persist(state, target, target_property)
                if state.is_complete:
                    break
                # 生产模式：等待真实数据，暂停执行
                if state.current_step == ECMLStep.WAITING_FOR_DATA:
                    state = self._persist(state, target, target_property)
                    break

                self.write_checkpoint("step7_feedback", iteration * 10 + 7, {"iteration": state.iteration})
                state = self._run_step_with_event(state, "step7_feedback", {"iteration": state.iteration}, self._step7_feedback)
                state = self._persist(state, target, target_property)

            # 断点恢复时若迭代已用完但 is_complete 未置位，显式补上
            if state.iteration >= max_iterations and not state.is_complete:
                state.is_complete = True
                state.status = "completed"
                state.completed_at = datetime.now(timezone.utc).isoformat()

            # 最终保存
            if self.state_store is not None:
                self.state_store.save(state.run_id, target, target_property, state)

            # ── Control Plane: mark run as succeeded ──
            self._cp_update_status(cp_run_id, succeeded=True)
        except Exception:
            # ── Control Plane: mark run as failed ──
            self._cp_update_status(cp_run_id, succeeded=False)
            raise

        return state

    def _create_new_state(self, run_id: str, target_property: str, max_iterations: int,
                          parent_run_id: str = "", scenario_id: str = "",
                          task_id: str = "", project_id: str = "") -> ECMLState:
        new_id = run_id or f"ecml_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        iteration_id = 1
        if parent_run_id and self.state_store is not None:
            parent_state = self.state_store.load(parent_run_id)
            if parent_state is not None:
                iteration_id = parent_state.iteration_id + 1
                # 继承父轮 task_id（迭代链保持业务关联）
                if not task_id and parent_state.task_id:
                    task_id = parent_state.task_id
        return ECMLState(
            run_id=new_id,
            target_property=target_property,
            max_iterations=max_iterations,
            parent_run_id=parent_run_id,
            scenario_id=scenario_id,
            iteration_id=iteration_id,
            task_id=task_id,
            project_id=project_id,
        )

    def _persist(self, state: ECMLState, target: str, target_property: str) -> ECMLState:
        """每步执行后保存到 SQLite。"""
        if self.state_store is not None and state.run_id:
            try:
                self.state_store.save(state.run_id, target, target_property, state)
            except Exception as e:
                logger.warning("Failed to persist ECML state: %s", e)
        return state

    # ── Control Plane helpers ──────────────────────────────

    def _cp_create_run(self, state: ECMLState) -> str | None:
        """Create a durable Control Plane run for this ECML execution.

        Returns the CP run_id, or ``None`` if the run manager is not wired
        or creation fails. All failures are swallowed so ECML keeps working.
        """
        if self._run_manager is None:
            return None
        try:
            input_hash = hashlib.md5(
                json.dumps(state.model_dump(), default=str).encode()
            ).hexdigest()
            cp_config = getattr(self.config, "control_plane", None)
            policy_version = (
                cp_config.policy_version if cp_config is not None else "cp-v1"
            )
            run = self._run_manager.create_run(
                run_type="ecml",
                project_id=getattr(state, "project_id", None),
                input_hash=input_hash,
                policy_version=policy_version,
            )
            self._current_run_id = run.run_id
            return run.run_id
        except Exception as e:
            logger.warning("Control Plane create_run failed: %s", e)
            return None

    def _cp_update_status(self, cp_run_id: str | None, succeeded: bool) -> None:
        """Update the Control Plane run status to SUCCEEDED or FAILED.

        Silently no-ops if ``cp_run_id`` is ``None`` or the run manager is
        not wired. All failures are swallowed so ECML keeps working.
        """
        if cp_run_id is None or self._run_manager is None:
            return
        try:
            from ..control_plane.run_manager import RunStatus
            status = RunStatus.SUCCEEDED if succeeded else RunStatus.FAILED
            self._run_manager.update_status(cp_run_id, status)
        except Exception as e:
            logger.warning("Control Plane update_status failed: %s", e)

    def write_checkpoint(
        self, step_name: str, step_index: int, output_summary: dict
    ) -> None:
        """Write a durable checkpoint for the current Control Plane run.

        Silently no-ops if the run manager is not wired or no current run
        exists. All failures are swallowed so ECML keeps working.
        """
        if self._run_manager is None or self._current_run_id is None:
            return
        try:
            self._run_manager.write_checkpoint(
                run_id=self._current_run_id,
                step_name=step_name,
                step_index=step_index,
                input_hash="",
                output_summary=output_summary,
                intent_log=[],
            )
        except Exception as e:
            logger.warning("Control Plane write_checkpoint failed: %s", e)

    def run_step(self, state: ECMLState, step: ECMLStep, target: str = "") -> ECMLState:
        # 注意：api.py 的 ecml_run_step 端点调用的是 run() 而非本方法。
        # 本方法保留用于手动/逐步执行场景。
        step_methods = {
            ECMLStep.STEP1_ROUTE: self._step1_route,
            ECMLStep.STEP2_GENERATE: self._step2_generate,
            ECMLStep.STEP3_SYNTHESIS_CHECK: self._step3_synthesis_check,
            ECMLStep.STEP3_INDUSTRIALIZATION: self._step3_industrialization,
            ECMLStep.STEP4_PREDICT: self._step4_predict,
            ECMLStep.STEP5_VERIFY: self._step5_verify,
            ECMLStep.STEP6_EXPERIMENT: self._step6_experiment,
            ECMLStep.WAITING_FOR_DATA: lambda state: state,  # 无操作，等待外部数据
            ECMLStep.STEP7_FEEDBACK: self._step7_feedback,
        }
        method = step_methods.get(step)
        if method:
            if step == ECMLStep.STEP1_ROUTE:
                return method(state, target)
            return method(state)
        return state

    def _step1_route(self, state: ECMLState, target: str) -> ECMLState:
        state.current_step = ECMLStep.STEP1_ROUTE
        state.target = target
        if self.router is not None:
            from ..router.router import MaterialInput
            result = self.router.route(MaterialInput(name=target))
            state.material_branch = result.branch.value
        else:
            state.material_branch = "crystal_branch"
        # P0-4：从用户目标抽取元素包含/排除约束 + 属性比较约束
        # 调用 IntentInterpreter 的 NL 解析逻辑（同步函数，避免 async 上下文问题）
        try:
            from ..hybrid.intent_interpreter import (
                _parse_exclude_elements, _parse_require_elements,
                _parse_target_properties, _infer_lithium_context,
            )
            exclude_elements = _parse_exclude_elements(target)
            require_elements = _parse_require_elements(target)
            require_elements = _infer_lithium_context(target, require_elements, exclude_elements)
            # 冲突解决：require 优先于 exclude
            if require_elements and exclude_elements:
                exclude_elements = [e for e in exclude_elements if e not in require_elements]
            parsed_target_props = _parse_target_properties(target)
            if require_elements:
                state.require_elements = require_elements
            if exclude_elements:
                state.exclude_elements = exclude_elements
            # 仅在 state.target_properties 为空时填充（保留调用方显式传入的配置）
            if not state.target_properties and parsed_target_props:
                state.target_properties = parsed_target_props
        except Exception as e:
            logger.warning("P0-4 NL 约束抽取失败（忽略，继续原流程）: %s", e)
        state.history.append({"step": "route", "branch": state.material_branch})
        return state

    def _step2_generate(self, state: ECMLState) -> ECMLState:
        """按 material_branch 分发到晶体或聚合物生成器。"""
        state.current_step = ECMLStep.STEP2_GENERATE
        # 从上一轮 feedback 读取下一轮推荐参数
        next_params = state.feedback.get("next_iteration_params", {}) if state.feedback else {}
        num_candidates = next_params.get("num_candidates") or 10

        branch = state.material_branch or "crystal_branch"
        is_polymer = "polymer" in branch.lower()

        if is_polymer and self.polymer_generator is not None:
            try:
                # 多目标优先：target_properties 非空时传 list 触发加权评分
                if state.target_properties:
                    poly_props: dict | list = state.target_properties
                else:
                    poly_props = {"target_property": state.target_property}
                # v4.1：把目标/体系名透传给生成器，触发工程塑料模式（否则回退电池电解质候选）
                material_system = state.target or "改性塑料"
                candidates = self.polymer_generator.generate(
                    target_properties=poly_props,
                    num_candidates=num_candidates,
                    material_system=material_system,
                )
                state.candidates = [c.model_dump() for c in candidates]
            except Exception as e:
                state.candidates = [{"name": "PA6", "psmiles": "[*]CCCCC(=O)N[*]", "source": "demo", "error": str(e)}]
        elif self.generator is not None:
            try:
                # 多目标优先：target_properties 非空时传 list 触发加权评分
                crystal_kwargs = {
                    "target_property": state.target_property,
                    "num_candidates": num_candidates,
                }
                if state.target_properties:
                    crystal_kwargs["target_properties"] = state.target_properties
                # P0-4：传递元素包含/排除约束，强制候选生成阶段做元素语义校验
                if state.require_elements:
                    crystal_kwargs["require_elements"] = state.require_elements
                if state.exclude_elements:
                    crystal_kwargs["exclude_elements"] = state.exclude_elements
                candidates = self.generator.generate_candidates(**crystal_kwargs)
                state.candidates = [c.model_dump() for c in candidates]
            except Exception as e:
                logger.warning("ECML _step2_generate: generator 调用异常: %s", e)
                state.candidates = [{"formula": "NaCl", "source": "demo", "error": str(e)}]

            # 降级：generator 返回空列表时（MP/GNoME 不可用或无匹配），调用 InternLM 生成候选
            if not state.candidates:
                logger.info("ECML _step2_generate: generator 返回空列表，降级到 InternLM 生成候选")
                llm_candidates = self._generate_candidates_with_llm(state, num_candidates)
                if llm_candidates:
                    state.candidates = llm_candidates
                    state.status = "degraded"
                else:
                    logger.warning("ECML _step2_generate: InternLM 降级生成也失败，候选为空")
        else:
            state.candidates = [{"formula": "NaCl", "source": "demo"}]

        # P0-4：把 formula_validator.assess_candidate_quality 提前到入口
        # 对每个候选做化学式/SMILES 合法性 + 元素约束校验，剔除 invalid 候选
        from ..generation.formula_validator import assess_candidate_quality
        valid_candidates: list[dict] = []
        blocked_candidates: list[dict] = []
        for c in state.candidates:
            quality = assess_candidate_quality(
                c,
                require_elements=state.require_elements or None,
                exclude_elements=state.exclude_elements or None,
            )
            c["data_quality_flag"] = quality["flag"]
            c["quality_issues"] = quality["issues"]
            if quality["flag"] == "invalid" and not c.get("error"):
                # demo/error 候选保留以传递错误信息，其他 invalid 直接剔除
                blocked_candidates.append(c)
            else:
                valid_candidates.append(c)
        state.candidates = valid_candidates
        if blocked_candidates:
            logger.info(
                "P0-4 _step2_generate 入口校验：%d 个候选被拦截（require=%s, exclude=%s）",
                len(blocked_candidates), state.require_elements, state.exclude_elements,
            )

        # 降级：validator 拦截全部候选后，调用 InternLM 生成候选
        if not state.candidates:
            logger.info("ECML _step2_generate: validator 后候选为空，降级到 InternLM 生成候选")
            llm_candidates = self._generate_candidates_with_llm(state, num_candidates)
            if llm_candidates:
                state.candidates = llm_candidates
                state.status = "degraded"
            else:
                logger.warning("ECML _step2_generate: InternLM 降级生成也失败，候选为空")

        # P0-4：候选数不足 num_candidates 时标记 degraded
        if len(state.candidates) < num_candidates:
            state.status = "degraded"
            logger.info(
                "P0-4 候选数不足：%d < %d，状态标记为 degraded",
                len(state.candidates), num_candidates,
            )

        state.history.append({
            "step": "generate", "count": len(state.candidates),
            "num_candidates": num_candidates, "branch": branch,
        })
        # Attach provenance to generated candidates
        # Task 16：source_type 必须反映真实来源（materials_project / gnome /
        # local_db / internlm_generated / algorithm_generated / mixed），
        # 不再按 engine_mode 一刀切标为 internlm。
        for c in state.candidates:
            _attach_candidate_provenance(c, self.config)

        # ── Crystal Construction Committee ──
        if not is_polymer and self.config is not None and self.config.engine_mode == EngineMode.INTERNLM:
            state = self._run_crystal_committee(state)

        # 持久化候选到 candidate_store，使下游 Sample/ExperimentOrder 可通过 candidate_id 反查
        if self.candidate_store is not None:
            from ..experiment.candidate_store import CandidateRecord
            cand_type = "polymer" if is_polymer else "crystal"
            for c in state.candidates:
                try:
                    cid = c.get("candidate_id", "")
                    if not cid:
                        continue
                    name = c.get("formula") or c.get("name") or ""
                    smiles = c.get("smiles") or c.get("psmiles") or ""
                    self.candidate_store.save(CandidateRecord(
                        candidate_id=cid,
                        candidate_type=cand_type,
                        name=name,
                        smiles=smiles,
                        source=c.get("source", "ecml"),
                        multi_objective_score=c.get("multi_objective_score", 0.0),
                        data=c,
                    ))
                except Exception:
                    logger.warning("Failed to persist ECML candidate to store: %s", c.get("candidate_id", ""), exc_info=True)

        return state

    def _generate_candidates_with_llm(self, state: ECMLState, num_candidates: int) -> list[dict]:
        """当 CrystalCandidateGenerator 返回空列表时，调用 InternLM 基于研发目标生成候选材料。

        利用 LLM 的材料学知识，根据目标属性和元素约束生成真实可用的候选化学式，
        而非使用静态模板。每个候选的 formula 均经过 LLM 推理产出。

        使用同步 httpx 调用，确保在 asyncio.to_thread 上下文中可靠工作。
        """
        if self.config is None:
            return []

        cfg = self.config.internlm
        if not cfg.enabled or cfg.api_key is None:
            logger.warning("_generate_candidates_with_llm: InternLM 未启用或无 API key")
            return []

        # 构建 prompt：基于研发目标和约束让 LLM 推荐候选材料
        target_desc = state.target or "高冲击强度玻纤增强PA6"
        prop_desc = state.target_property or "tensile_strength"

        parts = [f"研发目标：{target_desc}"]
        parts.append(f"目标属性：{prop_desc}（需最大化）")
        if state.require_elements:
            parts.append(f"必须包含元素：{', '.join(state.require_elements)}")
        if state.exclude_elements:
            parts.append(f"必须排除元素：{', '.join(state.exclude_elements)}")
        if state.target_properties:
            prop_list = [f"{p.get('property', '')}({p.get('direction', 'maximize')})" for p in state.target_properties]
            parts.append(f"多目标属性：{', '.join(prop_list)}")

        example = '[{"formula":"Li7La3Zr2O12","space_group":"Ia-3d","structure_type":"Garnet","reasoning":"高离子电导率"}]'
        prompt = (
            f"你是电池材料专家。请基于以下研发目标，推荐 {num_candidates} 种候选晶体材料。\n"
            + "\n".join(parts) + "\n\n"
            f"请直接返回 JSON 数组，不要输出思考过程，不要输出任何其他文字。\n"
            f"每个元素包含：\n"
            f'- "formula": 化学式（如 Li7La3Zr2O12）\n'
            f'- "space_group": 空间群（如 Ia-3d）\n'
            f'- "structure_type": 结构类型（如 Garnet）\n'
            f'- "reasoning": 推荐理由（简述为何该材料适合目标属性）\n\n'
            f"示例格式：{example}\n"
            f"只返回 JSON 数组。"
        )

        try:
            import httpx as _httpx
            import uuid as _uuid

            base_url = cfg.base_url.rstrip("/") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {cfg.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": cfg.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 4096,
                # 禁用 thinking mode，确保直接返回 JSON 而非思考过程
                "thinking_mode": False,
            }

            with _httpx.Client(timeout=180.0) as client:
                http_resp = client.post(base_url, headers=headers, json=payload)
                http_resp.raise_for_status()
                data = http_resp.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not content:
                logger.warning("_generate_candidates_with_llm: InternLM 返回空 content, raw=%s", str(data)[:300])
                return []

            # 记录外部调用
            state.external_invocation_ids.append(f"internlm-{_uuid.uuid4().hex[:8]}")

            # 去除 markdown 代码块标记
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            # JSON 解析容错
            try:
                materials = json.loads(content)
            except json.JSONDecodeError:
                start = content.find("[")
                end = content.rfind("]")
                if start != -1 and end != -1 and end > start:
                    try:
                        materials = json.loads(content[start:end + 1])
                    except json.JSONDecodeError:
                        logger.warning("_generate_candidates_with_llm: JSON 子串解析失败, content=%s", content[:500])
                        return []
                else:
                    logger.warning("_generate_candidates_with_llm: JSON 解析失败(无数组), content=%s", content[:500])
                    return []

            if not isinstance(materials, list):
                materials = [materials]

            # 转换为 ECML 候选格式
            candidates: list[dict] = []
            for m in materials:
                if not isinstance(m, dict):
                    continue
                formula = m.get("formula", "").strip()
                if not formula:
                    continue
                candidates.append({
                    "candidate_id": f"llm-{_uuid.uuid4().hex[:8]}",
                    "formula": formula,
                    "space_group": m.get("space_group", ""),
                    "structure_type": m.get("structure_type", ""),
                    "source": "internlm",
                    "name": formula,
                    "llm_reasoning": m.get("reasoning", ""),
                    "data_quality_flag": "valid",
                    "quality_issues": [],
                })
            logger.info("_generate_candidates_with_llm: InternLM 生成 %d 个候选", len(candidates))
            # SCP 校验：用真实化学工具验证候选化学式，补充 SMILES/分子量，标记可信度
            validated = self._validate_candidates_with_scp(candidates[:num_candidates], state)
            return validated
        except Exception as e:
            logger.warning("_generate_candidates_with_llm: InternLM 候选生成失败: %s", e)
            return []

    def _validate_candidates_with_scp(self, candidates: list[dict], state: "ECMLState") -> list[dict]:
        """用 SCP 化学工具校验 InternLM 生成的候选化学式。

        校验链（不阻断，仅标记）：
        1. NameToSMILES (server 31)：尝试将化学式/材料名转为 SMILES
        2. 若成功，再用 SMILESToWeight (server 31) 验证 SMILES 有效性并补充分子量
        3. 若 NameToSMILES 失败，用 search_pubchem_by_name (server 8) 做存在性校验

        成功的候选标记 scp_verified=True 并补充 smiles/molecular_weight；
        失败的候选标记 scp_verified=False 但保留（晶体材料可能无 SMILES 表示）。

        使用同步 httpx 调用，与 _generate_candidates_with_llm 保持一致。
        """
        if not candidates:
            return candidates

        scp_cfg = self.config.scp if self.config else None
        if scp_cfg is None or not scp_cfg.enabled or scp_cfg.api_key is None:
            logger.info("_validate_candidates_with_scp: SCP 未启用或无 API key，跳过校验")
            return candidates

        import httpx as _httpx
        import uuid as _uuid

        api_key = scp_cfg.api_key.get_secret_value()
        # server 31: SciToolAgent-Chem（NameToSMILES / SMILESToWeight）
        chem_url = "https://scp.intern-ai.org.cn/api/v1/mcp/31/SciToolAgent-Chem"
        # server 8: Origene-PubChem（search_pubchem_by_name）
        pubchem_url = "https://scp.intern-ai.org.cn/api/v1/mcp/8/Origene-PubChem"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "SCP-HUB-API-KEY": api_key,
        }

        rpc_id = 1
        verified_count = 0

        for cand in candidates:
            formula = cand.get("formula", "").strip()
            if not formula:
                cand["scp_verified"] = False
                cand["scp_verification_note"] = "无化学式，跳过校验"
                continue

            # 第一步：尝试 NameToSMILES 将化学式转为 SMILES
            smiles = None
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "method": "tools/call",
                    "params": {"name": "NameToSMILES", "arguments": {"name": formula}},
                }
                rpc_id += 1
                with _httpx.Client(timeout=30.0) as client:
                    resp = client.post(chem_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    msg = self._parse_scp_response(resp)
                    result = msg.get("result") or {}
                    if not result.get("isError"):
                        smiles = self._extract_smiles_from_scp_result(result)
                        if smiles:
                            state.external_invocation_ids.append(f"scp-nametosmiles-{_uuid.uuid4().hex[:8]}")
            except Exception as e:
                logger.debug("_validate_candidates_with_scp: NameToSMILES 失败 formula=%s err=%s", formula, e)

            if smiles:
                # 第二步：用 SMILESToWeight 验证 SMILES 有效性并补充分子量
                mol_weight = None
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "method": "tools/call",
                        "params": {"name": "SMILESToWeight", "arguments": {"smiles": smiles}},
                    }
                    rpc_id += 1
                    with _httpx.Client(timeout=30.0) as client:
                        resp = client.post(chem_url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        msg = self._parse_scp_response(resp)
                        result = msg.get("result") or {}
                        if not result.get("isError"):
                            mol_weight = self._extract_weight_from_scp_result(result)
                            if mol_weight is not None:
                                state.external_invocation_ids.append(f"scp-weight-{_uuid.uuid4().hex[:8]}")
                except Exception as e:
                    logger.debug("_validate_candidates_with_scp: SMILESToWeight 失败 smiles=%s err=%s", smiles, e)

                cand["smiles"] = smiles
                cand["scp_verified"] = True
                cand["scp_verification_note"] = "NameToSMILES + SMILESToWeight 验证通过"
                if mol_weight is not None:
                    cand["molecular_weight"] = mol_weight
                verified_count += 1
            else:
                # 第三步：PubChem 存在性校验（晶体材料可能无 SMILES）
                pubchem_found = False
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "method": "tools/call",
                        "params": {"name": "search_pubchem_by_name", "arguments": {"name": formula}},
                    }
                    rpc_id += 1
                    with _httpx.Client(timeout=30.0) as client:
                        resp = client.post(pubchem_url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        msg = self._parse_scp_response(resp)
                        result = msg.get("result") or {}
                        if not result.get("isError"):
                            # PubChem 返回非空即视为存在
                            result_text = json.dumps(result)
                            if len(result_text) > 50 and "PC_Compounds" in result_text:
                                pubchem_found = True
                                state.external_invocation_ids.append(f"scp-pubchem-{_uuid.uuid4().hex[:8]}")
                except Exception as e:
                    logger.debug("_validate_candidates_with_scp: PubChem 检索失败 formula=%s err=%s", formula, e)

                if pubchem_found:
                    cand["scp_verified"] = True
                    cand["scp_verification_note"] = "PubChem 存在性校验通过（无 SMILES 表示）"
                    verified_count += 1
                else:
                    cand["scp_verified"] = False
                    cand["scp_verification_note"] = "SCP 未找到匹配记录（晶体材料可能未收录）"

        logger.info(
            "_validate_candidates_with_scp: %d/%d 候选通过 SCP 校验",
            verified_count, len(candidates),
        )
        return candidates

    @staticmethod
    def _parse_scp_response(resp) -> dict:
        """解析 SCP JSON-RPC 响应（兼容 JSON 和 SSE 帧）。"""
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            last_data = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    last_data = line[len("data:"):].strip()
            if not last_data:
                raise ValueError("SSE 响应无 data 帧")
            return json.loads(last_data)
        return resp.json()

    @staticmethod
    def _extract_smiles_from_scp_result(result: dict) -> str | None:
        """从 NameToSMILES 的 MCP result 中提取 SMILES 字符串。"""
        # result.content[].text 可能含 "SMILES: CCO" 或直接是 SMILES
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                # 尝试从结构化文本中提取 SMILES
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("SMILES") or line.startswith("Canonical SMILES"):
                        # 格式如 "SMILES: CCO" 或 "Canonical SMILES: CCO"
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            smi = parts[1].strip()
                            if smi and not smi.startswith("None"):
                                return smi
                # 若整段文本就是一个 SMILES（无前缀）
                text_stripped = text.strip()
                if text_stripped and len(text_stripped) < 200 and all(
                    c in "CNOPSFClBrI()[]=#@-/\\1234567890cnops" for c in text_stripped
                ):
                    return text_stripped
        # structuredContent 字段
        sc = result.get("structuredContent") or {}
        if isinstance(sc, dict):
            for key in ("smiles", "SMILES", "canonical_smiles", "result"):
                val = sc.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    @staticmethod
    def _extract_weight_from_scp_result(result: dict) -> float | None:
        """从 SMILESToWeight 的 MCP result 中提取分子量。"""
        import re
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                # 格式如 "Weight: 46.04 g/mol"
                match = re.search(r"(\d+\.?\d*)\s*g/mol", text)
                if match:
                    return float(match.group(1))
        sc = result.get("structuredContent") or {}
        if isinstance(sc, dict):
            for key in ("molecular_weight", "weight", "mol_weight", "result"):
                val = sc.get(key)
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    match = re.search(r"(\d+\.?\d*)", val)
                    if match:
                        return float(match.group(1))
        return None

    def _run_crystal_committee(self, state: ECMLState) -> ECMLState:
        """Run crystal construction committee on Intern-S2 generated candidates.

        - In observe mode: logs verdicts but does not block candidates.
        - In enforce mode: removes candidates that fail committee review.
        """
        from ..config import CommitteeMode
        from ..committee.enums import CommitteeType, TriggerCode, Decision

        # Short-circuit when committee is disabled — avoid building coordinator
        if self.config is None or not self.config.committee.enabled or not self.config.committee.crystal_enabled:
            return state

        # Get or build coordinator
        coordinator = self._committee_coordinator
        if coordinator is None:
            coordinator = self._build_committee_coordinator()
            self._committee_coordinator = coordinator
            self.committee_coordinator = coordinator  # keep both attributes in sync

        if coordinator is None:
            logger.warning("Crystal committee coordinator not available, skipping")
            return state

        committee_config = self.config.committee
        mode = committee_config.default_mode

        new_candidates: list[dict] = []
        for candidate in state.candidates:
            candidate_id = candidate.get("candidate_id") or candidate.get("formula", "unknown")
            formula = candidate.get("formula", "")

            try:
                case = self._make_crystal_committee_case(candidate, state)
                verdict = _run_async_safe(coordinator.assess(case, user_role="system"))

                # Record in state
                state.committee_cases.append({
                    "case_id": case.case_id,
                    "candidate_id": candidate_id,
                    "formula": formula,
                    "status": case.status.value,
                })
                state.committee_verdicts.append({
                    "case_id": case.case_id,
                    "verdict_id": verdict.verdict_id,
                    "decision": verdict.decision.value,
                    "score": verdict.scorecard.get("score", 0),
                    "blocking_reasons": verdict.blocking_reasons,
                    "warnings": verdict.warnings,
                })

                if verdict.decision == Decision.REJECT:
                    if mode == CommitteeMode.ENFORCE:
                        logger.info(
                            "Committee rejected candidate %s (formula=%s): %s",
                            candidate_id, formula, verdict.blocking_reasons,
                        )
                        continue  # skip this candidate
                    else:
                        logger.info(
                            "Committee would reject candidate %s (observe mode, not blocking): %s",
                            candidate_id, verdict.blocking_reasons,
                        )
                elif verdict.decision == Decision.HUMAN_REVIEW:
                    logger.info(
                        "Committee escalated candidate %s for human review: %s",
                        candidate_id, verdict.blocking_reasons,
                    )
                    # In observe mode: keep candidate. In enforce mode: also keep but flag.
                    if mode == CommitteeMode.ENFORCE:
                        candidate["committee_review_required"] = True

                new_candidates.append(candidate)

            except Exception as e:
                logger.warning("Committee assessment failed for candidate %s: %s", candidate_id, e)
                new_candidates.append(candidate)  # keep on error

        if mode == CommitteeMode.ENFORCE and len(new_candidates) < len(state.candidates):
            state.history.append({
                "step": "committee_filtered",
                "before": len(state.candidates),
                "after": len(new_candidates),
                "removed": len(state.candidates) - len(new_candidates),
                "mode": mode.value,
            })
            state.candidates = new_candidates

        return state

    def _make_crystal_committee_case(self, candidate: dict, state: ECMLState):
        """Create a CommitteeCase for crystal construction review."""
        import uuid
        from ..committee.enums import CommitteeType, TriggerCode, RiskLevel
        from ..committee.models import CommitteeCase

        case_id = f"cc-{state.run_id}-{candidate.get('candidate_id', uuid.uuid4().hex[:8])}"
        return CommitteeCase(
            case_id=case_id,
            committee_type=CommitteeType.CRYSTAL_CONSTRUCTION,
            project_id=getattr(state, "target", ""),
            ecml_run_id=state.run_id,
            candidate_id=candidate.get("candidate_id") or candidate.get("formula", ""),
            trigger_code=TriggerCode.CRYSTAL_GENERATED.value,
            risk_level=RiskLevel.MEDIUM,
            created_by="ecml_engine",
        )

    def _build_committee_coordinator(self):
        """Lazily build the committee coordinator."""
        try:
            from ..committee.policy import CommitteePolicy
            from ..committee.thinker import CommitteeThinker
            from ..committee.doer import CommitteeDoer
            from ..committee.verifier import CommitteeVerifier
            from ..committee.repository import CommitteeRepository
            from ..committee.event_store import CommitteeEventStore
            from ..committee.coordinator import CommitteeCoordinator

            if self.config is None:
                return None

            policy = CommitteePolicy(self.config.committee)
            thinker = CommitteeThinker(llm_provider=self._llm_provider)
            doer = CommitteeDoer()
            verifier = CommitteeVerifier()
            repository = CommitteeRepository()
            event_store = CommitteeEventStore()

            return CommitteeCoordinator(
                config=self.config.committee,
                policy=policy,
                thinker=thinker,
                doer=doer,
                verifier=verifier,
                repository=repository,
                event_store=event_store,
            )
        except Exception as e:
            logger.warning("Failed to build committee coordinator: %s", e)
            return None

    def _step3_synthesis_check(self, state: ECMLState) -> ECMLState:
        state.current_step = ECMLStep.STEP3_SYNTHESIS_CHECK
        if self.synthesis_planner is not None and state.candidates:
            try:
                # Extract SMILES/formula from each candidate for feasibility check
                smiles_list = [c.get("smiles") or c.get("formula", "") for c in state.candidates if c.get("smiles") or c.get("formula", "")]
                if smiles_list:
                    synthesizable_smiles = self.synthesis_planner.filter_synthesizable(smiles_list, threshold=0.1)
                    synth_set = set(synthesizable_smiles)
                    # Keep candidates that passed synthesis check
                    state.synthesizable = [c for c in state.candidates if (c.get("smiles") or c.get("formula", "")) in synth_set]
                    # If all filtered out (strict threshold), keep top half by score
                    if not state.synthesizable:
                        scored = self.synthesis_planner.score_candidates(smiles_list)
                        top_n = max(1, len(smiles_list) // 2)
                        keep_smiles = set(s for s, _ in scored[:top_n])
                        state.synthesizable = [c for c in state.candidates if (c.get("smiles") or c.get("formula", "")) in keep_smiles]
                else:
                    state.synthesizable = state.candidates
            except Exception as e:
                state.synthesizable = state.candidates
                state.history.append({"step": "synthesis_check_warning", "error": str(e)})
        else:
            state.synthesizable = state.candidates
        state.history.append({"step": "synthesis_check", "count": len(state.synthesizable)})
        return state

    def _step3_industrialization(self, state: ECMLState) -> ECMLState:
        """工业化落地验证层：从纯 AI 生成向真实试产过渡的漏斗。"""
        state.current_step = ECMLStep.STEP3_INDUSTRIALIZATION

        if self.formula_agent is None or self.compliance_node is None:
            # 工业化模块不可用，回退到原有合成检查
            return self._step3_synthesis_check(state)

        if not state.candidates:
            state.synthesizable = []
            state.history.append({"step": "industrialization", "count": 0, "fallback": "no_candidates"})
            return state

        # 1. 只调用一次 LLM 生成配方（取第一个候选作为目标）
        best_candidate = state.candidates[0]
        target_material = {
            "target_property": state.target_property,
            "candidate": best_candidate.get("name") or best_candidate.get("formula") or best_candidate.get("smiles") or "",
            "smiles": best_candidate.get("smiles") or best_candidate.get("psmiles") or "",
        }
        try:
            recipe = _run_async_safe(self.formula_agent.design_recipe(target_material))
            # Use evaluate_async via _run_async_safe so SCP toxicity checks
            # actually run. The sync evaluate() falls back to _evaluate_sync
            # (which skips SCP) when an event loop is already running, which
            # is always the case inside ECML steps invoked from FastAPI.
            report = _run_async_safe(self.compliance_node.evaluate_async(recipe.bom))
        except Exception as e:
            logger.warning("Industrialization recipe design failed: %s", e)
            state.synthesizable = state.candidates
            state.history.append({"step": "industrialization", "count": len(state.synthesizable), "fallback": "recipe_error"})
            return state

        # Close the audit chain: collect SCP invocation_ids from the compliance
        # report into ECMLState.external_invocation_ids.
        scp_ids = getattr(report, "external_invocation_ids", None) or []
        if scp_ids:
            state.external_invocation_ids.extend(scp_ids)

        # 2. 用本地物料库筛选候选（无 LLM 调用）
        industrial_passed = []
        for candidate in state.candidates:
            candidate_smiles = candidate.get("smiles") or candidate.get("psmiles") or ""
            if candidate_smiles:
                substitutes = self.formula_agent.db.find_substitutes(candidate_smiles, threshold=0.3)
                if substitutes:
                    candidate["matched_materials"] = [m.material_id for m in substitutes]
                    candidate["industrial_recipe"] = recipe.model_dump()
                    candidate["estimated_cost"] = report.estimated_unit_cost
                    candidate["industrialization_score"] = 0.95
                    industrial_passed.append(candidate)
                else:
                    # 物料库无替代材料时不阻断研发流程，标记后放行
                    candidate["industrial_recipe"] = recipe.model_dump()
                    candidate["estimated_cost"] = report.estimated_unit_cost
                    candidate["industrialization_score"] = 0.5
                    candidate["substitute_warning"] = "物料库中暂无匹配替代材料，需后续扩充"
                    industrial_passed.append(candidate)
            else:
                # 无 SMILES 的候选直接通过（如晶体候选）
                candidate["industrial_recipe"] = recipe.model_dump()
                candidate["estimated_cost"] = report.estimated_unit_cost
                candidate["industrialization_score"] = 0.95
                industrial_passed.append(candidate)

        # 3. 工业可行性筛选（如果 screener 可用）
        if self.feasibility_screener is not None and industrial_passed:
            try:
                from ..industrialization.feasibility import IndustrialFeasibilityScreening
                screened = self.feasibility_screener.screen(industrial_passed)
                # 只保留非 BLOCK 状态的候选
                industrial_passed = [c for c, r in screened if r.status != "BLOCK"]
                # 记录被阻断的候选
                blocked = [(c.get("formula", c.get("name", "")), r.hard_blockers) for c, r in screened if r.status == "BLOCK"]
                if blocked:
                    state.history.append({"step": "industrialization_blocked", "count": len(blocked), "blocked": blocked})
            except Exception as e:
                logger.warning("Feasibility screening failed: %s", e)

        state.synthesizable = industrial_passed
        # Attach provenance to synthesized candidates
        # Task 16：保留候选原始 source_type（materials_project / gnome / ...），
        # 仅追加 industrialization 筛选阶段 provenance（local_db 工业化规则）。
        for c in state.synthesizable:
            _attach_candidate_provenance(c, self.config)
            provenance = c.get("provenance")
            if isinstance(provenance, list):
                provenance.append({
                    "source_type": "local_db",
                    "provider": "local_db",
                    "model_or_tool": "industrialization",
                    "evidence_level": "estimated",
                })
        state.history.append({"step": "industrialization", "count": len(state.synthesizable)})

        # Committee trigger: external evidence conflict or high risk → external evidence committee
        if self.committee_coordinator is not None and self.config.committee.enabled:
            self._maybe_trigger_external_evidence_committee(state, report, industrial_passed)

        return state

    def _step4_predict(self, state: ECMLState) -> ECMLState:
        """按 material_branch 分发到晶体或聚合物预测器。"""
        state.current_step = ECMLStep.STEP4_PREDICT
        branch = state.material_branch or "crystal_branch"
        is_polymer = "polymer" in branch.lower()
        if not state.synthesizable:
            state.predictions = []
            state.history.append({"step": "predict", "count": 0, "branch": branch})
            return state

        results = None
        if self.config is not None and self.config.engine_mode == EngineMode.INTERNLM:
            # 决策 7a/7b：按属性分派
            # - band_gap (crystal) → ASE-EMT 优先，失败回退 InternLM
            # - 其他属性 → InternLM 直接预测
            if state.target_property == "band_gap" and not is_polymer:
                results = self._predict_band_gap_dispatch(state)
            else:
                try:
                    results = self._predict_with_llm(state)
                except Exception as e:
                    logger.warning("InternLM prediction failed for %s, falling back to legacy predictor: %s", state.target_property, e)
                    state.status = "degraded"
                    state.history.append({"step": "predict_warning", "error": str(e), "fallback": "legacy"})
                    results = None

        if results is None:
            if is_polymer and self.polymer_predictor is not None:
                try:
                    # 聚合物候选的 features 字段名不同
                    features_list = []
                    for c in state.synthesizable:
                        if c.get("monomer_smiles"):
                            ms = c.get("monomer_smiles")
                            smiles = ms[0] if isinstance(ms, list) and ms else ms
                        else:
                            smiles = c.get("smiles") or c.get("formula", "")
                        features_list.append({
                            "smiles": smiles,
                            "psmiles": c.get("psmiles", ""),
                            "formula": c.get("name") or c.get("formula", ""),
                        })
                    # 聚合物预测器支持的属性集合，避免 ValueError（v4.1 默认回退高分子属性）
                    poly_supported = getattr(self.polymer_predictor, "PREDICTABLE_PROPERTIES", None)
                    poly_prop = state.target_property if (not poly_supported or state.target_property in poly_supported) else "tensile_strength"
                    results = self.polymer_predictor.predict_batch(features_list, poly_prop)
                except Exception as e:
                    state.status = "degraded"
                    state.predictions = [{"formula": c.get("name") or c.get("formula", ""), "value": 0.0, "error": str(e)} for c in state.synthesizable]
                    state.history.append({"step": "predict", "count": len(state.predictions), "branch": branch, "error": str(e)})
                    return state
            elif self.predictor is not None:
                try:
                    results = self.predictor.predict_batch(state.synthesizable, state.target_property)
                except Exception as e:
                    state.status = "degraded"
                    state.predictions = [{"formula": c.get("formula", ""), "value": 0.0} for c in state.synthesizable]
                    state.history.append({"step": "predict", "count": len(state.predictions), "branch": branch, "error": str(e)})
                    return state
            else:
                state.predictions = [{"formula": c.get("formula", ""), "value": 0.0} for c in state.synthesizable]
                state.history.append({"step": "predict", "count": len(state.predictions), "branch": branch})
                return state

        if results:
            state.predictions = [r.model_dump() if hasattr(r, "model_dump") else r for r in results]
            # Attach provenance to predictions
            # Task 16：预测值的 evidence_level 统一为 "predicted"（不再是 computed）；
            # source_type 仅在 LLM 实际生成时标 internlm_generated，否则 algorithm_generated。
            for pred in state.predictions:
                if "provenance" not in pred:
                    is_llm = self.config is not None and self.config.engine_mode == EngineMode.INTERNLM
                    pred_source_type = "internlm_generated" if is_llm else "algorithm_generated"
                    pred["provenance"] = [{
                        "source_type": pred_source_type,
                        "provider": "internlm" if is_llm else "algorithm",
                        "model_or_tool": self.config.internlm.model if is_llm and self.config else "ecml_predictor",
                        "evidence_level": "predicted",
                    }]
        else:
            state.predictions = [{"formula": c.get("formula", ""), "value": 0.0} for c in state.synthesizable]
        state.history.append({"step": "predict", "count": len(state.predictions), "branch": branch})

        # Committee trigger: prediction conflict or score proximity → candidate priority committee
        if self.committee_coordinator is not None and self.config.committee.enabled:
            self._maybe_trigger_candidate_priority_committee(state)

        return state

    def _predict_band_gap_dispatch(self, state: ECMLState) -> list:
        """决策 7a/7b：band_gap 晶体预测分派器。

        优先使用 ASE-EMT 本地真实物理计算；对 ASE-EMT 失败的候选
        （如非金属氧化物），回退到 InternLM 预测。

        Returns:
            合并后的预测结果列表（dict 格式，与 _predict_with_llm 一致）
        """
        from ..prediction.crystal_property_predictor import CrystalPropertyPredictor

        predictor = CrystalPropertyPredictor(model_type="cgcnn")
        ase_results: list[dict] = []
        failed_candidates: list[dict] = []

        for candidate in state.synthesizable:
            formula = candidate.get("formula", "")
            if not formula:
                failed_candidates.append(candidate)
                continue
            try:
                result = predictor.predict({"formula": formula}, "band_gap")
                # ASE-EMT 成功时 model="ase_emt"；启发式回退时 model="heuristic_gnn"
                # 只接受 ASE-EMT 结果，启发式的留给 InternLM
                if result.model == "ase_emt":
                    ase_results.append({
                        "formula": formula,
                        "value": result.value,
                        "unit": result.unit,
                        "confidence": result.confidence,
                        "reasoning": f"ASE-EMT local computation: E_rel={result.value:.4f} eV",
                        "property_name": "band_gap",
                        "method": "ase_emt",
                        "model": "ase_emt",
                        "material_type": "crystal",
                        "provenance": [{
                            "source_type": "algorithm_generated",
                            "provider": "ase",
                            "model_or_tool": "EMT",
                            "evidence_level": "computed",
                            "reasoning": "ASE-EMT semi-empirical potential energy calculation",
                        }],
                    })
                else:
                    # 启发式回退 → 交给 InternLM
                    failed_candidates.append(candidate)
            except Exception as e:
                logger.debug("ASE-EMT failed for %s: %s, will use InternLM", formula, e)
                failed_candidates.append(candidate)

        # 对 ASE-EMT 失败的候选用 InternLM 补齐
        llm_results: list[dict] = []
        if failed_candidates:
            logger.info(
                "band_gap dispatch: ASE-EMT succeeded for %d/%d candidates, "
                "falling back to InternLM for %d",
                len(ase_results), len(state.synthesizable), len(failed_candidates),
            )
            # 临时替换 state.synthesizable 以复用 _predict_with_llm
            original_synthesizable = state.synthesizable
            state.synthesizable = failed_candidates
            try:
                llm_results = self._predict_with_llm(state)
            except Exception as e:
                logger.warning("InternLM fallback failed for band_gap: %s", e)
                llm_results = [{
                    "formula": c.get("formula", ""),
                    "value": 0.0,
                    "unit": "eV",
                    "property_name": "band_gap",
                    "method": "internlm",
                    "error": str(e),
                } for c in failed_candidates]
            finally:
                state.synthesizable = original_synthesizable
        else:
            logger.info(
                "band_gap dispatch: ASE-EMT succeeded for all %d candidates",
                len(ase_results),
            )

        return ase_results + llm_results

    def _predict_with_llm(self, state: ECMLState) -> list:
        """使用 InternLM (LLMProvider) 对可合成候选进行性质预测。"""
        if self.config is None:
            raise RuntimeError("InternLM prediction requires config")

        provider = self._llm_provider
        provider_created_locally = False
        if provider is None:
            from ..llm.factory import ProviderFactory
            provider = ProviderFactory.create(self.config)
            provider_created_locally = True

        branch = state.material_branch or "crystal_branch"
        is_polymer = "polymer" in branch.lower()
        model_name = self.config.internlm.model
        target_property = state.target_property

        results: list = []
        import asyncio

        async def _predict_single(candidate: dict) -> dict:
            if is_polymer:
                identifier = candidate.get("psmiles") or candidate.get("smiles") or candidate.get("formula", "")
                # 决策 5：聚合物用 RDKit 描述符 + InternLM 预测
                # 提取真实 RDKit 描述符，给 LLM 提供量化特征输入
                descriptor_text = ""
                monomer_smiles = candidate.get("monomer_smiles") or candidate.get("smiles") or ""
                if isinstance(monomer_smiles, list):
                    monomer_smiles = monomer_smiles[0] if monomer_smiles else ""
                if monomer_smiles:
                    try:
                        from ..prediction.polymer_property_predictor import PolymerDescriptorCalculator
                        calc = PolymerDescriptorCalculator()
                        desc = calc.calculate_descriptors(monomer_smiles)
                        # 选关键描述符加入 prompt（避免过长）
                        key_desc = {k: round(v, 4) if isinstance(v, (int, float)) else v
                                    for k, v in desc.items()
                                    if k in ("molecular_weight", "tpsa", "num_hbd", "num_hba",
                                             "num_rotatable_bonds", "num_rings", "num_aromatic_rings",
                                             "fraction_csp3", "num_heavy_atoms", "labute_asa",
                                             "max_partial_charge", "min_partial_charge")}
                        if key_desc:
                            descriptor_text = f"\nRDKit descriptors: {json.dumps(key_desc, ensure_ascii=False)}"
                    except Exception as e:
                        logger.debug("descriptor extraction failed for %s: %s", monomer_smiles, e)

                prompt = (
                    f"You are a polymer materials expert. Predict the {target_property} "
                    f"for the following polymer material.\n"
                    f"PSMILES/SMILES: {identifier}\n"
                    f"Monomer SMILES: {monomer_smiles}{descriptor_text}\n\n"
                    f"Context: This is for an engineering plastics R&D project. {target_property} should be "
                    f"a physically reasonable value (e.g., tensile_strength typically 20-300 MPa, "
                    f"flexural_modulus 1500-20000 MPa, impact_strength 2-80 kJ/m2, "
                    f"heat_deflection_temp 60-300 C).\n"
                    f"Return ONLY a JSON object: {{\"value\": float, \"unit\": str, "
                    f"\"confidence\": float, \"reasoning\": str}}. No other text."
                )
                result_key = "psmiles"
            else:
                identifier = candidate.get("formula") or ""
                # 决策 7d：晶体预测 prompt 增强——加入空间群、结构类型、LLM 推理依据
                space_group = candidate.get("space_group", "")
                structure_type = candidate.get("structure_type", "")
                llm_reasoning = candidate.get("llm_reasoning", "")
                context_parts = [f"Crystal formula: {identifier}"]
                if space_group:
                    context_parts.append(f"Space group: {space_group}")
                if structure_type:
                    context_parts.append(f"Structure type: {structure_type}")
                if llm_reasoning:
                    context_parts.append(f"Material background: {llm_reasoning}")
                context_text = "\n".join(context_parts)

                prompt = (
                    f"You are a polymer materials expert. Predict the {target_property} "
                    f"for the following crystal material.\n{context_text}\n\n"
                    f"Context: This is for a crystal materials R&D project. {target_property} should be "
                    f"a physically reasonable value (e.g., band_gap 0.5-8 eV; "
                    f"formation_energy -5 to 2 eV/atom).\n"
                    f"Return ONLY a JSON object: {{\"value\": float, \"unit\": str, "
                    f"\"confidence\": float, \"reasoning\": str}}. No other text."
                )
                result_key = "formula"

            try:
                from ..llm.schemas import ChatRequest, ChatMessage
                request = ChatRequest(
                    model=model_name,
                    messages=[ChatMessage(role="user", content=prompt)],
                    temperature=0.2,
                    max_tokens=1024,  # 增强 prompt 需要 reasoning 字段，256 不够
                )
                response = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=self.config.internlm.timeout_seconds,
                )
                # Close the audit chain: collect the invocation_id returned by
                # the provider into ECMLState.external_invocation_ids so each
                # external call is traceable from the ECML run.
                if getattr(response, "invocation_id", None):
                    state.external_invocation_ids.append(response.invocation_id)
                content = response.content
                # JSON 解析容错：LLM 可能返回带 markdown 标记或额外文本
                parsed = _parse_llm_json(content)
                value = float(parsed["value"])
                unit = str(parsed.get("unit", ""))
                confidence = float(parsed.get("confidence", 0.7))
                reasoning = str(parsed.get("reasoning", ""))
                return {
                    result_key: identifier,
                    "value": value,
                    "unit": unit,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "property_name": target_property,
                    "method": "internlm+descriptor" if is_polymer else "internlm",
                    "model": model_name,
                    "material_type": "polymer" if is_polymer else "crystal",
                    "provenance": [{
                        "source_type": "internlm_generated",
                        "provider": "internlm",
                        "model_or_tool": model_name,
                        "request_id": response.request_id,
                        "invocation_id": getattr(response, "invocation_id", None),
                        "evidence_level": "predicted",
                        "reasoning": reasoning,
                    }],
                }
            except Exception as e:
                logger.warning("InternLM prediction failed for %s: %s", identifier, e)
                return {
                    result_key: identifier,
                    "value": 0.0,
                    "unit": "",
                    "property_name": target_property,
                    "method": "internlm",
                    "model": model_name,
                    "material_type": "polymer" if is_polymer else "crystal",
                    "error": str(e),
                }

        async def _predict_all():
            tasks = [_predict_single(c) for c in state.synthesizable]
            return await asyncio.gather(*tasks, return_exceptions=True)

        async def _predict_and_close():
            """在同一个事件循环中执行预测并关闭临时 provider，避免跨 loop 调用 aclose 失败。"""
            try:
                return await _predict_all()
            finally:
                if provider_created_locally:
                    close_fn = getattr(provider, "close", None)
                    if close_fn is not None:
                        try:
                            await close_fn()
                        except Exception as close_err:
                            logger.warning("Failed to close temporary LLM provider: %s", close_err)

        try:
            gathered = _run_async_safe(_predict_and_close())
        except Exception as e:
            logger.error("LLM prediction pipeline failed: %s", e, exc_info=True)
            # 降级：对每个候选返回 0 值，避免阻塞整个 ECML 运行
            gathered = [
                {
                    result_key: getattr(c, "identifier", ""),
                    "value": 0.0,
                    "unit": "",
                    "property_name": target_property,
                    "method": "internlm",
                    "error": f"pipeline_failed: {e}",
                }
                for c in state.synthesizable
            ]
        for item in gathered:
            if isinstance(item, Exception):
                logger.warning("InternLM prediction task failed: %s", item)
                continue
            results.append(item)

        return results

    def _step5_verify(self, state: ECMLState) -> ECMLState:
        """按材料类型分发验证：DFT 验证基于 RDKit，仅对有机分子适用。

        v4.1：聚合物（含工程塑料）候选不做 DFT 单点验证（DFTVerifier 面向分子，
        对高分子无意义且 target_property 不被支持），直接保留预测值。
        """
        state.current_step = ECMLStep.STEP5_VERIFY
        if not state.predictions:
            state.verified = []
            state.history.append({"step": "verify", "count": 0})
            return state

        branch = state.material_branch or "crystal_branch"
        is_polymer = "polymer" in branch.lower()
        verified: list[dict] = []
        for pred in state.predictions[:3]:
            material_type = pred.get("material_type", "crystal")
            smiles = pred.get("smiles", "")
            # DFT 验证仅对"带 SMILES 的有机分子"适用（DFTVerifier 基于 RDKit）；
            # 高分子（psmiles）与无机晶体均不适用，直接保留估算值（predicted_only）
            if (self.verifier is not None and smiles
                    and material_type in ("molecule", "organic")):
                try:
                    result = self.verifier.verify_single_point(smiles, state.target_property or "total_energy")
                    verified_item = dict(pred)
                    verified_item.update({
                        "verification_method": "dft",
                        "verification_value": result.model_dump().get("value", 0.0),
                        "verification_converged": result.model_dump().get("convergence", False),
                    })
                    verified.append(verified_item)
                    continue
                except Exception as e:
                    state.history.append({"step": "verify_warning", "error": str(e)})
            # 晶体/聚合物或 DFT 失败：保留预测值，标记为 predicted_only
            verified_item = dict(pred)
            verified_item["verification_method"] = "predicted_only"
            verified_item["verification_value"] = pred.get("value", 0.0)
            verified_item["verification_converged"] = False
            verified.append(verified_item)

        state.verified = verified
        state.history.append({"step": "verify", "count": len(state.verified)})

        # Committee trigger: before DFT, crystal construction committee must pass
        if self.committee_coordinator is not None and self.config.committee.enabled:
            self._maybe_trigger_crystal_committee(state)

        return state

    def _step6_experiment(self, state: ECMLState) -> ECMLState:
        """执行实验并同步写入 ExperimentDataStore（experiment.experiment_result_records）。"""
        state.current_step = ECMLStep.STEP6_EXPERIMENT
        state.experiment_results = []
        # 审批门：判断是否需要人工审批
        if self.approval_engine is not None and state.verified:
            for candidate in state.verified[:2]:
                estimated_cost = candidate.get("estimated_cost", 0.0)
                model_confidence = candidate.get("confidence", 1.0)
                decision = self.approval_engine.judge(
                    candidate, estimated_cost=estimated_cost,
                    model_confidence=model_confidence,
                )
                if decision.action == "REQUIRE_MANUAL":
                    state.history.append({
                        "step": "approval_required",
                        "candidate": candidate.get("formula", candidate.get("smiles", "")),
                        "risk_factors": decision.risk_factors,
                    })
                    # 在生产模式下，暂停等待人工审批（审批通过后由 resume 端点继续）。
                    # 先创建实验任务单（等待真实数据），否则无 order 可 resume → 死锁
                    if self.experiment_controller and self.experiment_controller.run_mode == "production":
                        approval_order_id = f"ORD-ECML-{state.run_id[:8]}-{state.iteration}"
                        try:
                            from ..experiment.experiment_controller import ExperimentOrder
                            _o = ExperimentOrder(
                                order_id=approval_order_id,
                                candidate_id=candidate.get("candidate_id", ""),
                                execution_mode="MANUAL_ENTRY",
                                status="PENDING_APPROVAL",
                                priority="P1",
                                notes=f"ECML 自动生成（run={state.run_id}, iter={state.iteration}，等待人工审批）",
                                ai_draft=True,
                            )
                            self.experiment_controller._store.save_order(_o)
                            state.history.append({"step": "order_created", "order_id": approval_order_id})
                        except Exception as _e:
                            logger.warning("审批暂停时创建任务单失败: %s", _e)
                        state.current_step = ECMLStep.WAITING_FOR_DATA
                        state.history.append({
                            "step": "waiting_for_approval",
                            "order_id": approval_order_id,
                            "message": "实验需人工审批后继续（任务单已创建，审批通过后录入数据即可恢复）",
                        })
                        return state
        if self.experiment_controller is not None and state.verified:
            try:
                from ..experiment.experiment_controller import (
                    ExperimentOrder,
                )
                for candidate in state.verified[:2]:
                    # InternLM 预测 dict 可能只有 psmiles（无 formula/smiles）——补齐标识
                    formula = (candidate.get("formula")
                               or candidate.get("smiles")
                               or candidate.get("psmiles")
                               or candidate.get("name", ""))
                    if not formula:
                        continue
                    candidate_id = candidate.get("candidate_id", "")

                    # 创建 ExperimentOrder 关联候选材料，打通 candidate → order → experiment 链路
                    # 订单 id 含候选序号，避免 verified[:2] 两个候选复用同一 order/result
                    _idx = list(state.verified).index(candidate) if candidate in state.verified else 0
                    order_id = f"ORD-ECML-{state.run_id[:8]}-{state.iteration}-{_idx}"
                    try:
                        order = ExperimentOrder(
                            order_id=order_id,
                            candidate_id=candidate_id,
                            execution_mode="SIMULATION_ONLY" if self.experiment_controller.run_mode != "production" else "MANUAL_ENTRY",
                            status="APPROVED",  # ECML 自动审批
                            priority="P2",
                            notes=f"ECML 自动生成（run={state.run_id}, iter={state.iteration}）",
                            ai_draft=True,
                        )
                        self.experiment_controller._store.save_order(order)
                    except Exception:
                        logger.warning("Failed to create ExperimentOrder for %s", formula, exc_info=True)
                        order_id = ""

                    # 从候选 data 取估算属性（verified 是预测 dict 无 data；候选的工程性能在 data JSONB）
                    _cand_data = {}
                    for _c in state.candidates:
                        if (_c.get("formula") == formula or _c.get("smiles") == formula
                                or _c.get("name") == formula):
                            _cand_data = _c.get("data") or {}
                            break
                    result = self.experiment_controller.execute_experiment(
                        {
                            "formula": formula,
                            "candidate_id": candidate_id,
                            "order_id": order_id,
                            # v4.1：把候选估算属性传给模拟引擎——模拟测量值围绕估算值生成，
                            # 使 demo 闭环的"估算 vs 模拟实测"偏差分析有意义
                            "estimated": {
                                k: (_cand_data.get(k) if _cand_data.get(k) is not None else candidate.get(k))
                                for k in (
                                    "tensile_strength", "elongation_at_break", "tensile_modulus",
                                    "flexural_modulus", "flexural_strength", "impact_strength",
                                    "heat_deflection_temp", "melt_flow_index",
                                )
                                if (_cand_data.get(k) is not None or candidate.get(k) is not None)
                            },
                        },
                        self._experiment_type_for_branch(state.material_branch or ""),
                    )
                    result_dict = result.model_dump() if hasattr(result, "model_dump") else result
                    result_dict["candidate_id"] = candidate_id
                    result_dict["order_id"] = order_id

                    # 生产模式：实验任务处于 PENDING 状态，需要等待真实数据
                    if self.experiment_controller.run_mode == "production":
                        state.current_step = ECMLStep.WAITING_FOR_DATA
                        state.history.append({
                            "step": "waiting_for_data",
                            "task_id": result_dict.get("task_id", ""),
                            "order_id": order_id,
                            "candidate_id": candidate_id,
                            "formula": formula,
                            "message": "实验任务已创建，等待真实数据录入",
                        })
                        continue

                    state.experiment_results.append(result_dict)

                    # Attach provenance to experiment results
                    # ADR-0002：模拟值（demo 模式）evidence_level="simulated"，不得标 measured
                    is_sim_run = (
                        self.experiment_controller is not None
                        and self.experiment_controller.run_mode != "production"
                    )
                    if "provenance" not in result_dict:
                        result_dict["provenance"] = [{
                            "source_type": "simulation" if is_sim_run else "local_db",
                            "provider": "simulation_engine" if is_sim_run else "local_db",
                            "model_or_tool": "ecml_experiment_controller" if is_sim_run else "experiment_controller",
                            "evidence_level": "simulated" if is_sim_run else "measured",
                            "note": "ECML 闭环确定性伪随机模拟值" if is_sim_run else "",
                        }]

                    # 写入 experiment.experiment_result_records（替代 middleware.ingest_record）。
                    # 生产模式数据来自外部，不在此处写入。
                    is_production = (
                        self.experiment_controller is not None
                        and getattr(self.experiment_controller, "run_mode", "") == "production"
                    )
                    if not is_production:
                        sample_id = f"smp_{formula}_{state.iteration}"
                        # 联动创建样品记录（fk_results_sample 要求样品先存在，否则 FK 失败）
                        try:
                            from ..api import _ensure_sample_for_result
                            _ensure_sample_for_result(sample_id, source_type="experiment",
                                                      order_id=order_id, candidate_id=candidate_id)
                        except Exception:
                            pass
                        with self._ingested_lock:
                            already_ingested = sample_id in self._ingested_samples
                        if not already_ingested:
                            try:
                                self._save_ecml_result_records(
                                    result_dict=result_dict,
                                    order_id=order_id,
                                    sample_id=sample_id,
                                    iteration=state.iteration,
                                    target_property=state.target_property,
                                    scenario_id=state.scenario_id or "",
                                    source_system="ecml_closed_loop",
                                    uploaded_by="ECML_ENGINE",
                                )
                                with self._ingested_lock:
                                    self._ingested_samples.add(sample_id)
                            except Exception as e:
                                state.history.append(
                                    {"step": "experiment_record_warning", "error": str(e)}
                                )
            except Exception as e:
                state.history.append({"step": "experiment_warning", "error": str(e)})
        state.history.append({"step": "experiment", "count": len(state.experiment_results)})
        return state

    def _compute_validation_metrics(self, state: ECMLState, validation_data: list[dict]) -> dict:
        """闭环验证精度：本轮估算值 vs 实验记录（含模拟）偏差统计（MAPE/命中率）。

        对齐规则：prediction.property_name 为裸 key（tensile_strength），
        实验记录 property_name 为 prop.* 规范化形式，去前缀匹配。
        审计语义：demo 模式对比"估算 vs 模拟实测"（展示闭环自洽性），
        生产模式对比"估算 vs 真实实测"（真实精度）。不进学习决策（ADR-0002）。
        """
        if not validation_data or not state.predictions:
            return {"n_records": len(validation_data), "n_compared": 0, "note": "无实验记录可对比"}
        # 估算基准：候选 data 的查表估算值（与模拟引擎同源，ADR-0003/查表法），
        # 按 formula 索引——实验记录 sample_id 形如 smp_{formula}_{iter}，可精确反查同一候选的估算值
        cand_est_by_formula: dict[str, dict[str, float]] = {}
        for _c in state.candidates:
            _cd = _c.get("data") or {}
            _f = _c.get("formula") or _c.get("name") or ""
            if not _f:
                continue
            _props = {
                _k: float(_v) for _k, _v in _cd.items()
                if isinstance(_v, (int, float)) and _k in (
                    "tensile_strength", "elongation_at_break", "tensile_modulus",
                    "flexural_modulus", "flexural_strength", "impact_strength",
                    "heat_deflection_temp", "melt_flow_index", "crystallinity",
                )
            }
            if _props:
                cand_est_by_formula[_f] = _props

        per_prop: dict[str, dict] = {}
        total_abs_err = 0.0
        total_pairs = 0
        hit_10 = 0
        hit_20 = 0
        for rec in validation_data:
            prop = (rec.get("property_name") or "").strip()
            if prop.startswith("prop."):
                prop = prop[len("prop."):]
            # 从 sample_id 反查候选 formula（smp_{formula}_{iter}）
            sample_id = rec.get("sample_id") or ""
            formula = ""
            if sample_id.startswith("smp_"):
                rest = sample_id[len("smp_"):]
                formula = rest.rsplit("_", 1)[0]
            est = cand_est_by_formula.get(formula, {})
            pred = est.get(prop)
            if pred is None:
                # 无查表估算时回退预测器输出（候选级，要求 formula 精确匹配，避免空串误配）
                for p in state.predictions:
                    p_f = (p.get("formula") or p.get("name") or "").strip()
                    if (p.get("property_name") or "").strip() == prop and formula and p_f == formula:
                        try:
                            pred = float(p.get("value") or 0.0)
                        except (TypeError, ValueError):
                            pred = None
                        break
            if pred is None:
                continue
            try:
                actual = float(rec.get("value"))
            except (TypeError, ValueError):
                continue
            denom = abs(actual) if actual != 0 else 1e-9
            rel = abs(pred - actual) / denom
            stat = per_prop.setdefault(prop, {"n": 0, "err_sum": 0.0, "hit10": 0})
            stat["n"] += 1
            stat["err_sum"] += rel
            if rel <= 0.10:
                stat["hit10"] += 1
            total_abs_err += rel
            total_pairs += 1
            if rel <= 0.10:
                hit_10 += 1
            if rel <= 0.20:
                hit_20 += 1
        per_prop_list = [
            {
                "property": prop,
                "n": st["n"],
                "mape_pct": round(st["err_sum"] / st["n"] * 100, 1),
                "within_10pct": round(st["hit10"] / st["n"] * 100, 1),
            }
            for prop, st in per_prop.items()
        ]
        # 数据质量分布（审计：模拟/实测/估算各占多少）
        dq_dist: dict[str, int] = {}
        for rec in validation_data:
            dq = rec.get("data_quality") or "estimated"
            dq_dist[dq] = dq_dist.get(dq, 0) + 1
        return {
            "n_records": len(validation_data),
            "n_compared": total_pairs,
            "overall_mape_pct": round(total_abs_err / total_pairs * 100, 1) if total_pairs else None,
            "within_10pct_pct": round(hit_10 / total_pairs * 100, 1) if total_pairs else None,
            "within_20pct_pct": round(hit_20 / total_pairs * 100, 1) if total_pairs else None,
            "per_property": per_prop_list,
            "data_quality_distribution": dq_dist,
            "note": "demo 模式对比估算 vs 模拟实测（闭环自洽性）；生产模式对比估算 vs 真实实测（真实精度）",
        }

    def _experiment_type_for_branch(self, branch: str):
        """按材料分支选择模拟实验类型（v4.1 高分子分支走力学/热学测试）。"""
        from ..experiment.experiment_controller import ExperimentType
        if "polymer" in (branch or "").lower():
            return ExperimentType.TENSILE
        return ExperimentType.IONIC_CONDUCTIVITY

    def _save_ecml_result_records(
        self,
        result_dict: dict,
        order_id: str,
        sample_id: str,
        iteration: int,
        target_property: str,
        scenario_id: str,
        source_system: str,
        uploaded_by: str,
    ) -> None:
        """将 ECML 实验结果写入 experiment.experiment_result_records。

        替代历史 ``DataMiddleware.ingest_record`` 写入路径，统一通过
        ``ExperimentDataStore.save_result_record`` 落库（每条 measured_values 项一行）。
        """
        from ..experiment.experiment_controller import ExperimentResultRecord
        store = self.experiment_controller._store
        measured = result_dict.get("measured_values", {}) or {}
        units = result_dict.get("units", {}) or {}
        experiment_type = result_dict.get("experiment_type", "ionic_conductivity")
        # v4.1：模拟实验类型 → 标准检测方法（test_method 列 FK → mdm.test_methods）
        _EXP_TYPE_TO_METHOD = {
            "tensile": "method.gbt_1040",
            "flexural": "method.gbt_9341",
            "impact": "method.gbt_1843",
            "hdt": "method.gbt_1634",
            "mfi": "method.gbt_3682",
            "dsc": "method.dsc",
            "tga": "method.tga",
            "xrd": "method.xrd",
            "sem": "method.sem",
            "eis": "method.eis",
            "ionic_conductivity": "method.eis",
        }
        test_method = _EXP_TYPE_TO_METHOD.get(experiment_type, "") or ""
        uploaded_at = datetime.now(timezone.utc).isoformat()
        run_id_suffix = (result_dict.get("run_id") or "")[:8]
        for prop_name, value in measured.items():
            if value is None:
                continue
            try:
                value_float = float(value)
            except (TypeError, ValueError):
                continue
            # v4.1：模拟测量值 key 带单位后缀（如 tensile_strength_MPa），
            # property_name 列有 FK → mdm.properties.property_id：剥离后缀后映射到 prop.*；
            # 无对应主数据时跳过该条（避免 FK 500 静默失败污染历史）
            from ..api import _PROPERTY_ALIASES
            canonical = prop_name
            for suffix in ("_MPa", "_pct", "_percent", "_C", "_g_10min", "_kJ_m2", "_ohm", "_V", "_eV", "_K", "_m2_g", "_nm", "_deg", "_J_g",
                           "_S_cm", "_Hz", "_mAh_g", "_mAh_cm2", "_g_cm3", "_nm2", "_deg_c", "_counts"):
                if canonical.endswith(suffix):
                    canonical = canonical[: -len(suffix)]
                    break
            if not canonical.startswith("prop."):
                mapped = _PROPERTY_ALIASES.get(canonical)
                if mapped:
                    canonical = mapped
                else:
                    logger.debug("跳过无 MDM 主数据的模拟测量值: %s", prop_name)
                    continue
            # ADR-0002：demo 模拟值以 simulated 身份落库——不进学习池、不得标 measured
            is_simulation = self.experiment_controller is not None and self.experiment_controller.run_mode != "production"
            # 单位兜底：模拟结果未带 units 时按属性映射（MDM unit_code 规范）
            _PROP_UNITS = {
                "prop.tensile_strength": "MPa", "prop.tensile_modulus": "MPa",
                "prop.flexural_modulus": "MPa", "prop.flexural_strength": "MPa",
                "prop.impact_strength": "kJ/m2", "prop.heat_deflection_temp": "C",
                "prop.melt_flow_index": "g/10min", "prop.elongation_at_break": "%",
                "prop.weight_loss": "%", "prop.residual_mass": "%",
                "prop.crystallinity": "%", "prop.melting_point": "C",
                "prop.thermal_stability": "C", "prop.glass_transition_temp": "C",
                "prop.ionic_conductivity": "S/cm",
            }
            unit_val = units.get(prop_name, "") or _PROP_UNITS.get(canonical, "")
            # result_id 用 run/iteration/order 序号/属性组成业务唯一键，
            # 迭代间或不同候选同属性不再互相覆盖。
            _order_suffix = (order_id or "").rsplit("-", 1)[-1] if order_id else str(iteration)
            candidate_props = f"REC-ECML-{run_id_suffix}-{iteration}-{_order_suffix}-{prop_name}"
            # T02：同 result_id 覆盖前核对业务身份——幂等重跑（同一 run/iteration/order/sample/property）
            # 允许更新；业务键不一致（不同 run/候选/属性/样品复用同一 id）则报错，不静默覆盖。
            existing_rec = None
            try:
                existing_rec = store.get_result_record(candidate_props)
            except Exception:
                existing_rec = None
            if existing_rec is not None:
                same_measurement = (
                    (existing_rec.experiment_order_id or "") == (order_id or "")
                    and (existing_rec.sample_id or "") == (sample_id or "")
                    and (existing_rec.property_name or "") == (canonical or "")
                )
                if not same_measurement:
                    raise ValueError(
                        f"ECML result_id 冲突：{candidate_props} 已被不同业务身份占用"
                        f"（order/sample/property 不一致），拒绝静默覆盖"
                    )
            record = ExperimentResultRecord(
                result_id=candidate_props,
                experiment_order_id=order_id,
                sample_id=sample_id,
                sample_batch_id=f"ecml_iter_{iteration}",
                source_type="API_PUSH",
                source_system=source_system,
                uploaded_by=uploaded_by,
                uploaded_at=uploaded_at,
                property_name=canonical,
                value=value_float,
                unit=unit_val,
                test_method=test_method,
                test_conditions={"iteration": iteration, "target_property": target_property},
                instrument_id="",
                raw_file_uri="",
                qc_status="VALID",
                qc_issues=[],
                reviewed_by=uploaded_by,
                reviewed_at=uploaded_at,
                learning_eligible=not is_simulation,
                scenario_id=scenario_id,
                data_quality="simulated" if is_simulation else "verified",
                provenance=[{
                    "source_type": "simulation" if is_simulation else "measured",
                    "provider": "simulation_engine" if is_simulation else "local_db",
                    "model_or_tool": "ecml_experiment_controller" if is_simulation else "experiment_controller",
                    "evidence_level": "simulated" if is_simulation else "measured",
                    "note": "ECML 闭环确定性伪随机模拟值，未经验证" if is_simulation else "ECML 闭环实测录入",
                }],
            )
            store.save_result_record(record)

    def resume_from_data(self, run_id: str, experiment_results: list[dict],
                         target: str = "", target_property: str = "") -> ECMLState:
        """从 WAITING_FOR_DATA 状态恢复，注入真实实验数据后继续执行 Step 7-8。"""
        if self.state_store is None:
            raise RuntimeError("State store not available")

        state = self.state_store.load(run_id)
        if state is None:
            raise ValueError(f"Run {run_id} not found")

        if state.current_step != ECMLStep.WAITING_FOR_DATA:
            raise ValueError(f"Run {run_id} is not in WAITING_FOR_DATA state (current: {state.current_step})")

        # 注入实验结果
        state.experiment_results = experiment_results

        # 同步写入 experiment.experiment_result_records（替代 middleware.ingest_record）。
        # 检查是否已通过 _step6_experiment 写入过。
        if self.experiment_controller is not None:
            for result_dict in experiment_results:
                formula = result_dict.get("formula", "")
                measured = result_dict.get("measured_values", {})
                if not (formula and measured):
                    continue
                sample_id = f"smp_{formula}_{state.iteration}"
                with self._ingested_lock:
                    already_ingested = sample_id in self._ingested_samples
                if already_ingested:
                    continue
                try:
                    # fk_results_sample：样品必须先存在，否则结果写入因 FK 失败
                    # （此前 resume 路径未建样品，生产模式注入数据被静默丢弃）
                    try:
                        from ..api import _ensure_sample_for_result
                        _ensure_sample_for_result(
                            sample_id,
                            source_type="experiment",
                            order_id=result_dict.get("order_id", ""),
                            candidate_id=result_dict.get("candidate_id", ""),
                        )
                    except Exception:
                        logger.warning("resume_from_data 预建样品失败 sample_id=%s", sample_id, exc_info=True)
                    self._save_ecml_result_records(
                        result_dict=result_dict,
                        order_id=result_dict.get("order_id", ""),
                        sample_id=sample_id,
                        iteration=state.iteration,
                        target_property=state.target_property,
                        scenario_id=state.scenario_id or "",
                        source_system="manual_entry",
                        uploaded_by="MANUAL",
                    )
                    with self._ingested_lock:
                        self._ingested_samples.add(sample_id)
                except Exception as e:
                    logger.error(
                        "resume_from_data 同步实验结果到 result records 失败 sample_id=%s（数据未落库，需排查）",
                        sample_id, exc_info=e,
                    )

        # 继续执行 Step 7
        state.current_step = ECMLStep.STEP7_FEEDBACK
        state = self._step7_feedback(state)
        state = self._persist(state, target or state.run_id, target_property or state.target_property)

        if state.iteration >= state.max_iterations:
            state.is_complete = True
            state.status = "completed"
            state.completed_at = datetime.now(timezone.utc).isoformat()

        if self.state_store is not None:
            self.state_store.save(state.run_id, target, target_property, state)

        return state

    def _step7_feedback(self, state: ECMLState) -> ECMLState:
        """生成结构化 feedback，真正影响下一轮参数。"""
        state.current_step = ECMLStep.STEP7_FEEDBACK

        # 实验数据：从 ExperimentDataStore 读取（带 data_quality/provenance，ADR-0002 可审计），
        # 按本 run 的订单前缀过滤（ECML step6 写入 sample_id=smp_{formula}_{iter} / order_id=ORD-ECML-{run}）。
        # 注意：middleware.query_records 忽略 formula 参数且 ExperimentRecord 无 data_quality 字段，不可用。
        experiment_data: list[dict] = []
        validation_data: list[dict] = []
        order_prefix = f"ORD-ECML-{state.run_id[:8]}"
        try:
            recs = self.experiment_controller._store.list_result_records()
            for r in recs:
                if (r.experiment_order_id or "").startswith(order_prefix):
                    rec = r.model_dump()
                    validation_data.append(rec)
                    # T07：模拟值 + 不合格/未审核数据不得进入学习反馈。
                    # 仅 learning_eligible=True 且 QC 通过（VALID/VERIFIED）且 data_quality 非 simulated 的记录才可参与学习。
                    rec["learning_skip_reason"] = ""
                    if r.data_quality == "simulated":
                        rec["learning_skip_reason"] = "simulated: 模拟数据不进入学习池"
                    elif (r.qc_status or "").upper() not in {"VALID", "VERIFIED"}:
                        rec["learning_skip_reason"] = f"qc_status={r.qc_status}: QC 未通过"
                    elif not bool(getattr(r, "learning_eligible", False)):
                        rec["learning_skip_reason"] = "learning_eligible=False"
                    else:
                        experiment_data.append(rec)
        except Exception as e:
            logger.warning("ECML feedback 读取实验记录失败: %s", e)

        # 分析本轮预测质量，生成下一轮建议
        pred_values = [p.get("value", 0.0) for p in state.predictions]
        direction = _get_property_direction(state.target_property)
        if pred_values:
            best_value = max(pred_values) if direction == 'maximize' else min(pred_values)
        else:
            best_value = 0.0
        mean_value = sum(pred_values) / len(pred_values) if pred_values else 0.0

        # 阈值（可按 target_property 调整）
        target_threshold = self._get_target_threshold(state.target_property)
        recommendation = "continue_iteration"
        next_num_candidates = 10
        next_elements_filter: list[str] = []

        if state.iteration < state.max_iterations:
            # 收敛/扩大判定系数（领域包 `converge_factor`/`expand_factor` 可覆盖，默认 1.5/0.5）
            converge_factor = float(self._domain_thresholds.get("_converge_factor", 1.5))
            expand_factor = float(self._domain_thresholds.get("_expand_factor", 0.5))
            if direction == 'maximize':
                needs_expand = best_value < target_threshold
                should_converge = best_value >= target_threshold * converge_factor
            else:  # minimize
                needs_expand = best_value > target_threshold
                should_converge = best_value <= target_threshold * expand_factor

            if needs_expand:
                # 最佳值未达阈值 → 扩大候选空间
                recommendation = "expand_search_space"
                next_num_candidates = min(20, 10 + state.iteration * 5)
            elif should_converge:
                # 已有显著突破 → 收敛
                recommendation = "converge"
                next_num_candidates = max(5, 10 - state.iteration * 2)
            # 否则 continue_iteration，保持参数
        else:
            recommendation = "converged"

        state.feedback = {
            "iteration": state.iteration,
            "best_candidates": state.verified[:3],
            "best_value": best_value,
            "mean_value": mean_value,
            "target_threshold": target_threshold,
            "experiment_data_available": len(experiment_data),
            "experiment_records": experiment_data[:3],
            "recommendation": recommendation,
            "next_iteration_params": {
                "num_candidates": next_num_candidates,
                "elements_filter": next_elements_filter,
            },
            # v4.1 闭环审计：估算 vs 实测（含模拟）精度指标——审查者可直接回答"估算有多准"
            "validation_metrics": self._compute_validation_metrics(state, validation_data),
            "provenance": [{
                "source_type": "local_db",
                "provider": "local_db",
                "model_or_tool": "ecml_feedback",
                "evidence_level": "estimated",
            }],
        }
        # 多目标反馈：附加各候选的综合评分
        if state.target_properties:
            mo_scores = [
                {"id": c.get("candidate_id") or c.get("formula") or c.get("name", ""),
                 "formula": c.get("formula") or c.get("name", ""),
                 "multi_objective_score": c.get("multi_objective_score", 0.0)}
                for c in state.candidates
            ]
            mo_scores.sort(key=lambda x: x["multi_objective_score"], reverse=True)
            state.feedback["multi_objective_scores"] = mo_scores[:5]
            state.feedback["multi_objective_config"] = state.target_properties
        state.history.append({
            "step": "feedback",
            "iteration": state.iteration,
            "recommendation": recommendation,
            "best_value": best_value,
        })

        if state.iteration >= state.max_iterations:
            state.is_complete = True
            state.status = "completed"
            state.completed_at = datetime.now(timezone.utc).isoformat()

        # 自动生成下一轮候选建议（B3.3）
        try:
            if self.state_store is not None and state.run_id:
                self.state_store.save(state.run_id, state.target, state.target_property, state)
            # generate_next_round 已改为同步方法，直接调用避免嵌套事件循环
            suggestions = self.generate_next_round(state.run_id)
            state.next_round_suggestions = suggestions
        except Exception as e:
            logger.warning("Failed to generate next round suggestions: %s", e)
            state.next_round_suggestions = {}

        # Committee trigger: deviation exceeds threshold or QC/batch anomaly → deviation review committee
        if self.committee_coordinator is not None and self.config.committee.enabled:
            self._maybe_trigger_deviation_review_committee(state, experiment_data)

        return state

    def _get_target_threshold(self, target_property: str) -> float:
        """各属性的目标阈值（用于判断是否需要扩大搜索）。

        来源：工程塑料常见规格参考区间（CAMPUS 塑料数据库 / GB-T 1040、9341、1843、1634）；
        领域包 `target_thresholds` 可覆盖（企业按自家规格调整）。
        """
        thresholds = {
            # 电池时代属性（crystal 分支兼容）
            "ionic_conductivity": 1e-3,  # S/cm
            "band_gap": 1.0,  # eV
            "formation_energy": -0.5,  # eV/atom
            "electrochemical_window": 4.0,  # V
            "theoretical_capacity": 150.0,  # mAh/g
            "operating_voltage": 3.0,  # V
            # v4.1 改性塑料：高分子工程性能阈值（工程塑料常见规格）
            "tensile_strength": 100.0,  # MPa（玻纤增强工程塑料典型下限）
            "flexural_modulus": 6000.0,  # MPa（GF 增强典型下限）
            "impact_strength": 15.0,  # kJ/m2（缺口冲击，汽车件典型）
            "heat_deflection_temp": 130.0,  # C（HDT/A 载荷，耐热件典型）
            "melt_flow_index": 15.0,  # g/10min（注塑级典型）
            "elongation_at_break": 50.0,  # %（韧性材料典型）
            "thermal_stability": 300.0,  # C（TGA 5% 失重）
            "glass_transition_temp": 120.0,  # C（非晶工程塑料典型）
        }
        if target_property in self._domain_thresholds:
            return float(self._domain_thresholds[target_property])
        return thresholds.get(target_property, 0.5)

    def _maybe_trigger_external_evidence_committee(self, state, report, candidates):
        """Step 3: If external evidence conflict or high risk, start external evidence committee."""
        try:
            import uuid
            from ..committee.enums import CommitteeType, RiskLevel, TriggerCode, CaseStatus
            from ..committee.models import CommitteeCase

            has_external = any(
                c.get("external_evidence") for c in candidates
                if isinstance(c, dict)
            )
            is_high_risk = report.estimated_unit_cost > self.config.committee.dft_cost_trigger if hasattr(report, "estimated_unit_cost") else False

            if has_external or is_high_risk:
                case = CommitteeCase(
                    case_id=f"cmt-ext-{state.run_id}-{uuid.uuid4().hex[:6]}",
                    committee_type=CommitteeType.EXTERNAL_EVIDENCE,
                    project_id=getattr(state, "project_id", None),
                    ecml_run_id=state.run_id,
                    trigger_code=TriggerCode.EXTERNAL_CONFLICT.value if has_external else "high_cost_risk",
                    risk_level=RiskLevel.HIGH if is_high_risk else RiskLevel.MEDIUM,
                )
                self.committee_coordinator.repository.create_case(case)
                self.committee_coordinator.event_store.append(
                    case.case_id, "ecml_triggered",
                    {"ecml_step": "step3", "run_id": state.run_id},
                )
                # After creating the case, assess it so it does not stay PENDING forever.
                # _maybe_trigger_* methods are sync, so use _run_async_safe to invoke the
                # async coordinator.assess coroutine.
                try:
                    _run_async_safe(self.committee_coordinator.assess(case, user_role="system"))
                except Exception as e:
                    logger.warning("Committee assessment failed: %s", e, exc_info=True)
                    try:
                        self.committee_coordinator.repository.update_case_status(case.case_id, CaseStatus.FAILED)
                        self.committee_coordinator.event_store.append(case.case_id, "case_failed", {"reason": str(e)})
                    except Exception as update_err:
                        logger.warning("Failed to mark case %s as FAILED: %s", case.case_id, update_err)
                state.history.append({
                    "step": "committee_external_evidence_triggered",
                    "case_id": case.case_id,
                })
        except Exception as e:
            logger.warning("Failed to trigger external evidence committee: %s", e)

    def _maybe_trigger_candidate_priority_committee(self, state):
        """Step 4: If prediction conflict or score proximity, start candidate priority committee."""
        try:
            import uuid
            from ..committee.enums import CommitteeType, RiskLevel, TriggerCode, CaseStatus
            from ..committee.models import CommitteeCase

            pred_values = [p.get("value", 0.0) for p in state.predictions if p.get("value") is not None]
            should_trigger = False

            if len(pred_values) >= 2:
                sorted_vals = sorted(pred_values, reverse=True)
                best = sorted_vals[0]
                second = sorted_vals[1] if len(sorted_vals) > 1 else 0
                if best > 0 and (best - second) / best <= self.config.committee.top_k_score_proximity_ratio:
                    should_trigger = True

            if state.target_properties and len(state.target_properties) > 1:
                should_trigger = True

            if should_trigger:
                case = CommitteeCase(
                    case_id=f"cmt-pri-{state.run_id}-{uuid.uuid4().hex[:6]}",
                    committee_type=CommitteeType.CANDIDATE_PRIORITY,
                    project_id=getattr(state, "project_id", None),
                    ecml_run_id=state.run_id,
                    trigger_code=TriggerCode.PREDICTION_CONFLICT.value,
                    risk_level=RiskLevel.MEDIUM,
                )
                self.committee_coordinator.repository.create_case(case)
                self.committee_coordinator.event_store.append(
                    case.case_id, "ecml_triggered",
                    {"ecml_step": "step4", "run_id": state.run_id},
                )
                # After creating the case, assess it so it does not stay PENDING forever.
                try:
                    _run_async_safe(self.committee_coordinator.assess(case, user_role="system"))
                except Exception as e:
                    logger.warning("Committee assessment failed: %s", e, exc_info=True)
                    try:
                        self.committee_coordinator.repository.update_case_status(case.case_id, CaseStatus.FAILED)
                        self.committee_coordinator.event_store.append(case.case_id, "case_failed", {"reason": str(e)})
                    except Exception as update_err:
                        logger.warning("Failed to mark case %s as FAILED: %s", case.case_id, update_err)
                state.history.append({
                    "step": "committee_candidate_priority_triggered",
                    "case_id": case.case_id,
                })
        except Exception as e:
            logger.warning("Failed to trigger candidate priority committee: %s", e)

    def _maybe_trigger_crystal_committee(self, state):
        """Step 5: Before DFT, crystal construction committee must pass."""
        try:
            import uuid
            from ..committee.enums import CommitteeType, RiskLevel, TriggerCode, CaseStatus
            from ..committee.models import CommitteeCase

            if not state.verified:
                return

            case = CommitteeCase(
                case_id=f"cmt-cry-{state.run_id}-{uuid.uuid4().hex[:6]}",
                committee_type=CommitteeType.CRYSTAL_CONSTRUCTION,
                project_id=getattr(state, "project_id", None),
                ecml_run_id=state.run_id,
                trigger_code=TriggerCode.CRYSTAL_GENERATED.value,
                risk_level=RiskLevel.MEDIUM,
            )
            self.committee_coordinator.repository.create_case(case)
            self.committee_coordinator.event_store.append(
                case.case_id, "ecml_triggered",
                {"ecml_step": "step5", "run_id": state.run_id},
            )
            # After creating the case, assess it so it does not stay PENDING forever.
            try:
                _run_async_safe(self.committee_coordinator.assess(case, user_role="system"))
            except Exception as e:
                logger.warning("Committee assessment failed: %s", e, exc_info=True)
                try:
                    self.committee_coordinator.repository.update_case_status(case.case_id, CaseStatus.FAILED)
                    self.committee_coordinator.event_store.append(case.case_id, "case_failed", {"reason": str(e)})
                except Exception as update_err:
                    logger.warning("Failed to mark case %s as FAILED: %s", case.case_id, update_err)
            state.history.append({
                "step": "committee_crystal_triggered",
                "case_id": case.case_id,
            })
        except Exception as e:
            logger.warning("Failed to trigger crystal committee: %s", e)

    def _maybe_trigger_deviation_review_committee(self, state, experiment_data):
        """Step 7: If deviation exceeds threshold or QC/batch anomaly, trigger deviation review committee."""
        try:
            import uuid
            from ..committee.enums import CommitteeType, RiskLevel, TriggerCode, CaseStatus
            from ..committee.models import CommitteeCase

            should_trigger = False

            # Check experiment-prediction deviation
            for pred in state.predictions:
                pred_val = pred.get("value", 0)
                for exp in experiment_data:
                    for prop, exp_val in exp.get("measured_values", {}).items():
                        try:
                            if float(exp_val) != 0:
                                rel_dev = abs(float(pred_val) - float(exp_val)) / abs(float(exp_val))
                                if rel_dev > self.config.committee.experiment_relative_deviation_trigger:
                                    should_trigger = True
                                    break
                        except (ValueError, TypeError):
                            pass
                    if should_trigger:
                        break
                if should_trigger:
                    break

            if should_trigger:
                case = CommitteeCase(
                    case_id=f"cmt-dev-{state.run_id}-{uuid.uuid4().hex[:6]}",
                    committee_type=CommitteeType.DEVIATION_REVIEW,
                    project_id=getattr(state, "project_id", None),
                    ecml_run_id=state.run_id,
                    trigger_code=TriggerCode.EXPERIMENT_DEVIATION.value,
                    risk_level=RiskLevel.HIGH,
                )
                self.committee_coordinator.repository.create_case(case)
                self.committee_coordinator.event_store.append(
                    case.case_id, "ecml_triggered",
                    {"ecml_step": "step7", "run_id": state.run_id},
                )
                # After creating the case, assess it so it does not stay PENDING forever.
                try:
                    _run_async_safe(self.committee_coordinator.assess(case, user_role="system"))
                except Exception as e:
                    logger.warning("Committee assessment failed: %s", e, exc_info=True)
                    try:
                        self.committee_coordinator.repository.update_case_status(case.case_id, CaseStatus.FAILED)
                        self.committee_coordinator.event_store.append(case.case_id, "case_failed", {"reason": str(e)})
                    except Exception as update_err:
                        logger.warning("Failed to mark case %s as FAILED: %s", case.case_id, update_err)
                state.history.append({
                    "step": "committee_deviation_review_triggered",
                    "case_id": case.case_id,
                })
        except Exception as e:
            logger.warning("Failed to trigger deviation review committee: %s", e)

    def get_summary(self, state: ECMLState) -> dict:
        return {
            "iterations": state.iteration,
            "branch": state.material_branch,
            "target_property": state.target_property,
            "total_candidates": len(state.candidates),
            "synthesizable": len(state.synthesizable),
            "industrialization_enabled": self.formula_agent is not None and self.compliance_node is not None,
            "verified": len(state.verified),
            "experiment_results": len(state.experiment_results),
            "is_complete": state.is_complete,
            "history": state.history,
            "feedback": state.feedback,
            "candidates_preview": state.candidates[:3],
            "verified_preview": state.verified[:3],
            "iteration_id": state.iteration_id,
            "parent_run_id": state.parent_run_id,
            "scenario_id": state.scenario_id,
            "next_round_suggestions": state.next_round_suggestions,
            "committee_reviewed": len(state.committee_cases),
            "committee_rejected": sum(
                1 for v in state.committee_verdicts if v.get("decision") == "reject"
            ),
        }

    def generate_next_round(self, run_id: str) -> dict:
        """基于历史数据推荐下一轮候选材料。

        主动学习策略（简化实现）：
        1. 获取当前 run 的状态和实验结果
        2. 分析已完成候选的性能数据
        3. 基于主动学习策略推荐信息价值最高的下一批候选点
        4. 返回 {next_candidates: [...], reasoning: "...", suggested_params: {...}}

        注：本方法为纯同步实现（无 await 调用），避免在 asyncio.to_thread 上下文中
        通过 _run_async_safe 创建嵌套事件循环导致 httpx.AsyncClient 跨循环报错。
        """
        if self.state_store is None:
            raise RuntimeError("State store not available")
        state = self.state_store.load(run_id)
        if state is None:
            raise ValueError(f"Run {run_id} not found")

        direction = _get_property_direction(state.target_property)
        is_polymer = "polymer" in (state.material_branch or "").lower()
        # 缺失预测值时按方向使用最差默认值，避免 0.0 误判为最优
        default_pred_value = float('-inf') if direction == "maximize" else float('inf')

        # 1. 收集已完成实验的候选材料及其性能指标
        perf_records: list[dict] = []
        for pred in (state.predictions or []):
            identifier = pred.get("formula") or pred.get("smiles") or pred.get("psmiles") or ""
            if not identifier:
                continue
            perf_records.append({
                "identifier": identifier,
                "predicted_value": pred.get("value", default_pred_value),
                "unit": pred.get("unit", ""),
                "property": pred.get("property_name", state.target_property),
            })

        # 2. 找出性能最优的 top-3 候选
        if perf_records:
            sorted_records = sorted(
                perf_records,
                key=lambda x: x["predicted_value"],
                reverse=(direction == "maximize"),
            )
            top_records = sorted_records[:3]
        else:
            top_records = []

        # 3. 在最优候选附近生成变体（利用型）+ 探索性候选
        next_candidates: list[dict] = []

        # 3a. 利用型变体（top-3 附近微调）
        # P1-1：展示命名规范化，禁止使用 variant_1_from_xxx 这类调试痕迹命名
        _VARIANT_SUFFIX = "ABCDEFGHIJ"
        for i, rec in enumerate(top_records):
            identifier = rec["identifier"]
            base_value = rec["predicted_value"]
            expected = base_value * (1.05 if direction == "maximize" else 0.95)
            variant = {
                "name": f"{identifier[:20]}-变体{_VARIANT_SUFFIX[i]}",
                "formula": identifier if not is_polymer else "",
                "smiles": identifier if is_polymer else "",
                "psmiles": identifier if is_polymer else "",
                "source": "exploitation",
                "base_identifier": identifier,
                "reasoning": (
                    f"基于本轮 top-{i + 1} 候选 {identifier}"
                    f"（预测值 {base_value:.4g} {rec.get('unit', '')}）"
                    f"的局部变体，微调组分比例以探索更优解"
                ),
                "expected_performance": expected,
                "strategy": "exploitation",
            }
            next_candidates.append(variant)

        # 3b. 探索型候选（未测试区域）
        num_explore = max(2, 5 - len(top_records))
        for i in range(num_explore):
            if is_polymer:
                explore_candidate = {
                    "name": f"探索候选-{i + 1}",
                    "smiles": f"[*]CC{i + 1}O[*]",
                    "psmiles": f"[*]CC{i + 1}O[*]",
                    "formula": "",
                    "source": "exploration",
                    "reasoning": f"探索未测试聚合物区域候选 {i + 1}，扩大搜索空间以发现潜在更优解",
                    "expected_performance": None,
                    "strategy": "exploration",
                }
            else:
                # 探索型晶体候选：轮换不同过渡金属元素 M 构造尖晶石型 LiM2O4，
                # 每个候选探索不同元素体系，比同元素变比例更具科学探索价值
                _EXPLORE_ELEMENTS = ["Ti", "Mn", "Fe", "Co", "Ni", "V", "Cr", "Cu"]
                elem = _EXPLORE_ELEMENTS[i % len(_EXPLORE_ELEMENTS)]
                explore_candidate = {
                    "name": f"探索候选-{i + 1}",
                    "formula": f"Li{elem}2O4",
                    "smiles": "",
                    "psmiles": "",
                    "source": "exploration",
                    "reasoning": f"探索未测试晶体区域候选 {i + 1}（{elem} 基尖晶石体系），扩大搜索空间以发现潜在更优解",
                    "expected_performance": None,
                    "strategy": "exploration",
                }
            next_candidates.append(explore_candidate)

        # P1-1：化学式/SMILES 合法性前置校验——非法候选标记并阻止进入推荐池
        from ..generation.formula_validator import (
            assess_batch_quality,
            assess_candidate_quality,
        )
        blocked_candidates: list[dict] = []
        valid_candidates: list[dict] = []
        for cand in next_candidates:
            quality = assess_candidate_quality(cand)
            cand["data_quality_flag"] = quality["flag"]
            cand["quality_issues"] = quality["issues"]
            if quality["flag"] == "invalid":
                blocked_candidates.append(cand)
            else:
                valid_candidates.append(cand)
        next_candidates = valid_candidates

        # 限制 5-10 个候选
        next_candidates = next_candidates[:10]
        # 候选不足时不硬凑无效占位候选（原 fallback 硬编码 valid 绕过校验），
        # 改为在 reasoning 中提示候选不足，由用户调整目标或参数
        candidate_shortage = len(next_candidates) < 5

        # P1-1：批量质量检测——全部预测值为 0 判定为模型推理失效，整轮标记异常
        batch_quality = assess_batch_quality(next_candidates)

        # P1-2 触发条件B：非法候选自动创建"候选质量审核"委员会案件（触发器内部去重）
        quality_case_id = None
        if blocked_candidates and self.committee_coordinator is not None:
            from ..committee.triggers import trigger_candidate_quality_case
            quality_case_id = trigger_candidate_quality_case(
                self.committee_coordinator, run_id, blocked_candidates,
            )

        reasoning_parts = []
        if top_records:
            reasoning_parts.append(
                f"本轮最优 top-{len(top_records)} 候选已识别，"
                f"基于其组分生成 {len(top_records)} 个局部变体（利用型）"
            )
        reasoning_parts.append(f"同时推荐 {num_explore} 个探索型候选以扩大搜索空间")
        if blocked_candidates:
            reasoning_parts.append(
                f"已拦截 {len(blocked_candidates)} 个未通过化学式合法性校验的候选"
            )
        if candidate_shortage:
            reasoning_parts.append(
                f"有效候选仅 {len(next_candidates)} 个，不足 5 个，建议调整目标材料或属性约束后重新运行"
            )
        # batch_quality 为 all_zero_predictions 时不在此重复提示，
        # 下方 batch_quality_warning 字段会单独以 error 级别展示给用户

        suggested_params = {
            "num_candidates": len(next_candidates),
            "parent_iteration_id": state.iteration_id,
            "next_iteration_id": state.iteration_id + 1,
            "target_property": state.target_property,
            "exploration_ratio": round(num_explore / max(len(next_candidates), 1), 2),
        }

        return {
            "next_candidates": next_candidates,
            "reasoning": "；".join(reasoning_parts),
            "suggested_params": suggested_params,
            "blocked_candidates": blocked_candidates,
            "quality_case_id": quality_case_id or "",
            "batch_quality_warning": (
                "全部候选预测值为 0，疑似模型推理失效，建议降级到基线模型重新计算"
                if batch_quality == "all_zero_predictions" else ""
            ),
        }

    # ─────────────────── 贝叶斯优化推荐（决策引擎） ───────────────────
    def _candidate_pool(self, state: ECMLState) -> list[dict]:
        """构造待评分候选池：复用本轮已生成候选；不足时用 next-round 探索候选补充。"""
        pool = list(state.candidates or [])
        is_polymer = "polymer" in (state.material_branch or "").lower()
        if len(pool) < 5:
            try:
                nr = self.generate_next_round(state.run_id)
                for c in (nr.get("next_candidates") or []):
                    if c.get("formula") or c.get("smiles"):
                        pool.append(c)
                    if len(pool) >= 10:
                        break
            except Exception:
                logger.warning("Failed to enrich candidate pool", exc_info=True)
        return pool[:40]

    def run_bayesian_round(
        self,
        run_id: str,
        family: str | None = None,
        acquisition: str = "ei",
        explore: float = 0.5,
        model_family_override: str | None = None,
        budget: float | None = None,
        include_cross_project: bool = False,
        project_id: str = "",
        objectives: list[dict] | None = None,
        num_candidates: int = 10,
    ) -> dict:
        """装配训练池 → 拟合代理模型 → 采集函数评分 → 写 Round 记录（待复核）。

        返回给前端的推荐结果。多目标（objectives 非空且 >1）走 EHVI。
        """
        from .bo import BayesianOptimizer, ObjectiveMeta, classify_family
        from .rounds_store import RoundStore

        state = self.state_store.load(run_id)
        if state is None:
            raise ValueError(f"Run {run_id} not found")

        # 持久化 project_id 到 state，供"本项目/跨项目"数据隔离端到端成立
        if project_id and state.project_id != project_id:
            state.project_id = project_id
            try:
                self.state_store.save(state.run_id, state.target, state.target_property, state)
            except Exception:
                pass

        target_property = state.target_property
        family = family or classify_family(state.target)
        pool = self._candidate_pool(state)

        opt = BayesianOptimizer(engine=self.state_store.engine)
        objectives_meta = None
        # 未显式传入 objectives 时，回退到 run 状态里持久化的多目标配置（state.target_properties）
        objectives = objectives or state.target_properties
        if objectives and len(objectives) > 1:
            objectives_meta = [
                ObjectiveMeta(property=o.get("property", target_property), direction=o.get("direction", "maximize"), weight=o.get("weight", 1.0))
                for o in objectives
            ]
        rec = opt.recommend(
            family=family,
            property_name=target_property,
            candidates=pool,
            acquisition=acquisition,
            explore=explore,
            objectives=objectives_meta,
            budget=budget,
            model_family_override=model_family_override,
            include_cross_project=include_cross_project,
            project_id=state.project_id or project_id,
            num_candidates=num_candidates,
        )

        round_no = (state.iteration or 0) + 1
        store = RoundStore(engine=self.state_store.engine)
        round_id = store.create_round(
            run_id=run_id,
            round_no=round_no,
            target=state.target,
            target_property=target_property,
            material_family=family,
            status="pending_review",
            train_pool_snapshot=rec.pool,
            model_meta=rec.model,
            acquisition_meta=rec.acquisition,
            recommended=rec.candidates,
            model_metrics=rec.model_metrics,
        )
        return {
            "round_id": round_id,
            "round_no": round_no,
            "status": "pending_review",
            "recommended": rec.candidates,
            "reasoning": rec.reasoning,
            "model": rec.model,
            "acquisition": rec.acquisition,
            "pool": rec.pool,
            "model_metrics": rec.model_metrics,
        }

    def pool_stats(
        self, run_id: str, family: str | None = None, property_name: str | None = None
    ) -> dict:
        """训练池统计预览（策略配置面板展示“当前材料体系+属性有多少条有效数据”）。

        数据聚合维度 = 材料体系 + 目标属性，项目只是查询过滤标签而非隔离边界。
        """
        from .bo import BayesianOptimizer, classify_family

        state = self.state_store.load(run_id)
        if state is None:
            raise ValueError(f"Run {run_id} not found")
        prop = property_name or state.target_property
        fam = family or classify_family(state.target)
        opt = BayesianOptimizer(engine=self.state_store.engine)
        pool = opt.build_pool(fam, prop)
        return {
            "family": fam,
            "property_name": prop,
            "stats": pool.stats,
            "quality_report": pool.quality_report,
        }

    def list_rounds(self, run_id: str) -> list[dict]:
        from .rounds_store import RoundStore
        return RoundStore(engine=self.state_store.engine).list_rounds(run_id)

    def get_round(self, round_id: str) -> dict | None:
        from .rounds_store import RoundStore
        return RoundStore(engine=self.state_store.engine).get_round(round_id)

    def confirm_round(self, round_id: str, adopted: list[dict | str] | None = None) -> dict:
        """课题负责人复核确认后下发：为采纳候选创建实验任务，并推进状态机。"""
        from .rounds_store import RoundStore

        store = RoundStore(engine=self.state_store.engine)
        rnd = store.get_round(round_id)
        if rnd is None:
            raise ValueError(f"Round {round_id} not found")

        adopted_list = adopted or []
        created_orders: list[str] = []
        if self.experiment_controller is not None and adopted_list:
            try:
                from ..experiment.experiment_controller import ExperimentOrder
                for item in adopted_list:
                    cand = item if isinstance(item, dict) else {"formula": str(item)}
                    formula = cand.get("formula") or cand.get("smiles") or ""
                    if not formula:
                        continue
                    order_id = f"ORD-BO-{round_id[:8]}-{len(created_orders) + 1}"
                    try:
                        order = ExperimentOrder(
                            order_id=order_id,
                            candidate_id=cand.get("candidate_id", ""),
                            execution_mode="MANUAL_ENTRY",
                            status="APPROVED",
                            priority="P2",
                            notes=f"BO 复核下发（round={round_id}）",
                            ai_draft=True,
                        )
                        self.experiment_controller._store.save_order(order)
                        created_orders.append(order_id)
                    except Exception:
                        logger.warning("Failed to create order for %s", formula, exc_info=True)
            except Exception:
                logger.warning("Failed to create experiment orders for round %s", round_id, exc_info=True)

        store.update_status(
            round_id,
            status="in_execution",
            review_actions={"adopted": adopted_list, "created_orders": created_orders},
        )
        return {
            "round_id": round_id,
            "status": "in_execution",
            "created_orders": created_orders,
            "adopted": len(adopted_list),
        }
