"""FastAPI server for the Battery Materials Agent."""

from fastapi import FastAPI, HTTPException, Request, Query, Depends, Body
from fastapi import Path as FastApiPath
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, SecretStr, field_validator
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typing import Literal
import asyncio
import json
import math
import os
import time
import uuid
from .agent import BatteryMaterialsAgent
from .config import get_config, ensure_project_root, EngineMode, save_config_to_env

# 启动守卫：无论从哪个目录启动 uvicorn，都强制把 CWD 切到项目根目录，
# 保证 .env / data/ / cache 等相对路径落到正确位置。幂等。
ensure_project_root()
from .agent_team.registry import AgentRegistry
from .agent_team.orchestrator import TaskOrchestrator
from .agent_team.executor import AgenticExecutor
from .agent_team.models import AgentDefinition, OrchestrationPlan, AgentRole, TaskStep
from .experiment.experiment_controller import (
    ExperimentOrder, ExperimentResultRecord, IllegalStateTransitionError,
)
from .experiment.approval import ApprovalEngine

from .experiment.equipment_store import Equipment, EquipmentStatus, EquipmentStore
from .experiment.sample_store import Sample, SampleStatus, SampleStore
from .experiment.sample_guard import (
    ensure_sample_for_result,
    register_order_lookup,
    register_sample_store_getter,
)
from .experiment.candidate_store import CandidateRecord, CandidateStore
from .experiment.idea_store import Idea, IdeaStatus, IdeaStore
from .agent_team.agents.experiment_analyst import ExperimentAnalystAgent
from .agent_team.agents.literature_researcher import LiteratureResearcherAgent
from .knowledge import (
    get_claim_store,
    get_ingestion_pipeline,
    get_knowledge_graph_store,
    get_material_store,
    get_paper_store,
)
from .workflow_schema import get_schema_loader
from .projects import Project, ProjectStore, ProjectTask, _iso
from .audit import get_audit_logger, AuditEntry
from .auth.tenant_store import TenantStore
from .auth.tenant_router import router as _tenant_router
from .auth import (
    UserRole, User, UserStore,
    get_current_user, require_role, require_login, check_project_access,
    require_permission,
)
from .auth.user_store import hash_password, is_legacy_hash, verify_password, normalize_disciplines
from .auth.permissions import role_has_permission
from .auth.tokens import issue_token, verify_token
from .auth import sso as sso_module
from .auth import ldap_auth
from .version_store import (
    Version, VersionType, get_version_store,
)
from .industrialization.formula_store import FormulaVersion, get_formula_store

from .integrations.audit_store import AuditStore
from .integrations import init_audit_db
from .db import get_tenant
from .mcp_tools.scp_client import SCPClientPool
from .mcp_tools.scp_catalog import SCPCatalog, RiskLevel
from .mcp_tools.scp_policy import SCPPolicy, PolicyDeniedError
from .mcp_tools.scp_adapters import (
    SCPAdapter,
    MoleculeDescriptorAdapter,
    ToxicityAssessmentAdapter,
    LiteratureSearchAdapter,
    ProtocolDraftAdapter,
    MaterialTransformAdapter,
)
from .control_plane.context import ExecutionContext
from .control_plane.identity import IdentityManager
from .control_plane.tool_catalog import ToolCatalog
from .control_plane.tool_gateway import ToolGateway
from .control_plane.policy_engine import PolicyEngine
from .control_plane.policy_store import PolicyStore
from .control_plane.run_manager import Run as ControlPlaneRun, RunManager, RunStatus as ControlPlaneRunStatus
from .control_plane.budget import BudgetManager, BudgetScope, BudgetEnvelope
from .control_plane.observability import ObservabilityService
from .control_plane.memory_service import MemoryService, MemoryCardType
from .control_plane.provider_registry import ProviderRegistry
from .evals.runner import EvalRunner
from .evals.coe_audit import CoeAuditor
from .ai_assistant import AiSessionStore
from .report.export import (
    build_report, export_excel, export_pdf, schedule_report,
    start_report_scheduler, VALID_FORMATS, REPORT_TYPES,
)

# 后台任务引用集：避免 asyncio.create_task 创建的任务被 GC 回收，并集中管理生命周期
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> asyncio.Task:
    """安全地创建后台任务：持有强引用防止 GC，完成后自动清理。"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


app = FastAPI(
    title="Battery Materials Agent API", version="0.1.0",
    # 全局依赖：解析 X-Auth-Token 并写入 request.state.current_user（匿名时为 None，不阻断请求）
    dependencies=[Depends(get_current_user)],
)

# CORS：默认同源部署不开启；跨域部署前端时通过环境变量配置白名单（逗号分隔），
# 避免届时图省事写成 allow_origins=["*"]
_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Content-Type", "X-Auth-Token", "X-Correlation-Id", "X-Project-Id"],
    )

# 战略工作包子路由（无 /api 前缀：Vite 代理已剥离 /api，前端 client baseURL=/api）
# 安全审查（2026-08）：统一为所有子路由挂载 require_login 依赖，
# 阻断匿名访问（此前放行卡/成本规则/数据导入/科学服务等路由完全无鉴权）。
from .capability.router import router as _capability_router
from .release_card.router import router as _release_card_router
from .value_realization.router import router as _value_realization_router
from .data_ingest.router import router as _data_ingest_router
from .agent_team.mapping_router import router as _mapping_router

app.include_router(_capability_router, dependencies=[Depends(require_login)])
app.include_router(_release_card_router, dependencies=[Depends(require_login)])
app.include_router(_tenant_router, dependencies=[Depends(require_login)])
app.include_router(_value_realization_router, dependencies=[Depends(require_login)])
app.include_router(_data_ingest_router, dependencies=[Depends(require_login)])
app.include_router(_mapping_router, dependencies=[Depends(require_login)])

# ── 原生科学服务路由（Phase 0 — 新架构，无历史数据负担） ──
from .scientific_routes.scientific_runs import router as _scientific_runs_router
from .scientific_routes.evidence import router as _evidence_router
from .scientific_routes.artifacts import router as _artifacts_router
from .scientific_routes.approvals import router as _approvals_router
app.include_router(_scientific_runs_router, dependencies=[Depends(require_login)])
app.include_router(_evidence_router, dependencies=[Depends(require_login)])
app.include_router(_artifacts_router, dependencies=[Depends(require_login)])
app.include_router(_approvals_router, dependencies=[Depends(require_login)])

# ── Phase 1 原生科学服务路由（MPA, Chemical, Structure, Formulation） ──
from .scientific_routes.mpa_routes import router as _mpa_router
from .scientific_routes.chemical_routes import router as _chemical_router
from .scientific_routes.structure_routes import router as _structure_router
from .scientific_routes.formulation_routes import router as _formulation_router
app.include_router(_mpa_router, dependencies=[Depends(require_login)])
app.include_router(_chemical_router, dependencies=[Depends(require_login)])
app.include_router(_structure_router, dependencies=[Depends(require_login)])
app.include_router(_formulation_router, dependencies=[Depends(require_login)])

# ── Phase 2 原生科学服务路由（MolecularSim, Synthesis, Process） ──
from .scientific_routes.molecular_simulation_routes import router as _molecular_simulation_router
from .scientific_routes.synthesis_planning_routes import router as _synthesis_planning_router
from .scientific_routes.process_modeling_routes import router as _process_modeling_router
app.include_router(_molecular_simulation_router, dependencies=[Depends(require_login)])
app.include_router(_synthesis_planning_router, dependencies=[Depends(require_login)])
app.include_router(_process_modeling_router, dependencies=[Depends(require_login)])

# ── Phase 3: 高级原生科学服务路由 ──
from .scientific_routes.reaction_network_routes import router as _reaction_network_router
from .scientific_routes.wavefunction_analysis_routes import router as _wavefunction_analysis_router
from .scientific_routes.fluid_simulation_routes import router as _fluid_simulation_router
from .scientific_routes.molecular_docking_routes import router as _molecular_docking_router
app.include_router(_reaction_network_router, dependencies=[Depends(require_login)])
app.include_router(_wavefunction_analysis_router, dependencies=[Depends(require_login)])
app.include_router(_fluid_simulation_router, dependencies=[Depends(require_login)])
app.include_router(_molecular_docking_router, dependencies=[Depends(require_login)])

# ── 全局后台异步任务查询 ──
from .scientific_routes.async_task_routes import router as _async_task_router
app.include_router(_async_task_router, dependencies=[Depends(require_login)])

# ── 工作流混编执行路由 ──
from .scientific_routes.workflow_routes import router as _workflow_router
app.include_router(_workflow_router, dependencies=[Depends(require_login)])

# ── 能力契约门禁装饰器（用于直接 API 端点） ──
# 模块级单例，避免每次调用都新建 CapabilityRegistry
_capability_registry_singleton = None


def _get_capability_registry():
    """懒加载 CapabilityRegistry 单例。"""
    global _capability_registry_singleton
    if _capability_registry_singleton is None:
        from .capability.registry import CapabilityRegistry
        _capability_registry_singleton = CapabilityRegistry()
    return _capability_registry_singleton


def require_capability(capability_id: str):
    """装饰器：要求对应能力契约可调用，否则返回 403。

    门禁规则：
    - 契约 status=deprecated → 尝试 fallback_chain
    - 契约 status=pending_approval 且 risk_level=high → 尝试 fallback_chain
    - 有可调用 fallback → 降级执行（日志记录），不阻塞业务
    - 整条 fallback 链都不可调用 → 抛 403
    - 契约不存在或 status=active → 正常执行

    用法：
        @app.post("/discover/crystal")
        @require_capability("crystal_candidate_generation_v1")
        async def discover_crystal(req): ...
    """
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            reg = _get_capability_registry()
            ok, reason = reg.is_callable(capability_id)
            if not ok:
                fallback_id, fb_reason = reg.find_callable_fallback(capability_id)
                if fallback_id is None:
                    logger.warning(
                        "Capability gate blocked %s: contract %s (%s), no callable fallback",
                        capability_id, capability_id, reason,
                    )
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "capability_blocked",
                            "capability_id": capability_id,
                            "reason": reason,
                            "message": f"能力契约 '{capability_id}' 不可调用（{reason}），且 fallback 链无可用契约",
                        },
                    )
                # 有可调用 fallback：降级执行，仅记录日志
                logger.info(
                    "Capability %s degraded to %s (reason=%s, fallback=%s)",
                    capability_id, fallback_id, reason, fb_reason,
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


agent = None

# Agent Team 全局实例（在 startup 中初始化）
_registry = None
_orchestrator = None
_executor = None

# SCP 全局实例（在 startup 中初始化）
_scp_client_pool = None
_scp_catalog = None
_scp_policy = None
_scp_adapters = None
_scp_audit_store = None

# SKILL 全局实例（在 startup 中初始化）
_skill_catalog = None
_skill_executor = None

# 评测修复 BEMCL-AI-P2-003：统一 LLMProvider 实例（在 startup 中初始化）
_llm_provider = None

# Committee 全局实例（在 startup 中初始化）
_committee_policy = None
_committee_coordinator = None
_committee_repository = None
_committee_event_store = None

# Control Plane 全局实例
# _identity_manager 是信任根，模块级即可就绪；其余组件在 startup 中按需初始化。
_identity_manager = IdentityManager()
_tool_catalog: ToolCatalog | None = None
_tool_gateway: ToolGateway | None = None
_policy_engine: PolicyEngine | None = None
_policy_store: PolicyStore | None = None
_run_manager: RunManager | None = None
_budget_manager: BudgetManager | None = None
_agent_event_log = None  # P1-2: AgentEventLog，启动时初始化
_research_event_stream = None  # P3-1: ResearchEventStream，启动时初始化
_activity_mapping_store = None  # 决策 1-13: ActivityMappingStore，启动时初始化
_agent_proxy = None  # 决策 7-A: AgentProxy，启动时初始化
_observability_service: ObservabilityService | None = None
_memory_service: MemoryService | None = None
_provider_registry: ProviderRegistry | None = None
_eval_runner: EvalRunner | None = None
_coe_auditor: "CoeAuditor | None" = None

_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_frontend_index = _frontend_dist / "index.html"

import logging
logger = logging.getLogger(__name__)

# 日志持久化（可观测性）：错误与警告写入 data/app.log，重启不丢、可离线审计
_log_dir = Path(__file__).resolve().parent.parent / "data"
try:
    _log_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(str(_log_dir / "app.log"), encoding="utf-8")
    _file_handler.setLevel(logging.WARNING)
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logging.getLogger().addHandler(_file_handler)
except Exception:
    # 日志目录不可写时仅控制台，不影响服务
    pass


def _init_control_plane():
    """初始化 Control Plane 组件（Tool Catalog / Gateway / Policy Engine / Store）。

    仅当 ``config.control_plane.enabled`` 为 True 时初始化；未启用时全局实例保持
    ``None``，端点与中间件应据此降级（shadow mode：仅观测、不强制）。
    """
    global _tool_catalog, _tool_gateway, _policy_engine, _policy_store
    global _run_manager, _budget_manager, _observability_service
    global _memory_service, _provider_registry, _eval_runner
    config = get_config()
    if not config.control_plane.enabled:
        return
    db_path = str(config.data_dir / "control_plane.db")
    _tool_catalog = ToolCatalog()
    _policy_store = PolicyStore()
    _policy_engine = PolicyEngine(policy_store=_policy_store)
    _tool_gateway = ToolGateway(
        catalog=_tool_catalog,
        policy_engine=_policy_engine,
    )
    _run_manager = RunManager(db_path=db_path)
    _budget_manager = BudgetManager(db_path=db_path)
    _observability_service = ObservabilityService(db_path=db_path)
    _memory_service = MemoryService(db_path=db_path)
    _provider_registry = ProviderRegistry(db_path=db_path)
    _eval_runner = EvalRunner(
        golden_set_dir=config.eval.golden_set_dir,
        report_dir=config.eval.report_dir,
    )
    _coe_auditor = CoeAuditor(report_dir=config.eval.report_dir)
    logger.info(
        "Control Plane initialized (shadow_mode=%s, policy_version=%s)",
        config.control_plane.shadow_mode,
        config.control_plane.policy_version,
    )


# 与前端路由同名的 API 路径（如 /agents、/tools）会先于 SPA fallback 被匹配，
# 导致浏览器直接刷新/书签访问时返回 JSON。通过中间件对显式请求 HTML 的 GET
# 请求优先返回 index.html，保留 API 的 JSON 响应给 Accept: application/json。
_SPA_HTML_SKIP_PREFIXES = ("/api/", "/assets/")
_SPA_HTML_EXACT_SKIP = {"/health", "/docs", "/openapi.json"}

# 评测修复 P2-001：API 命名空间集合。
# 浏览器请求（Accept: text/html）命中这些命名空间下的【多级路径】时，
# 说明是在探测 API 而非访问前端页面（前端路由均为单级路径，少数例外见下方排除），
# 不再返回 SPA index.html 掩盖 404，而是放行让 FastAPI 返回 404 JSON。
# 排除 projects / ecml / value-reports / tool-catalog：前端存在多级路由
# （/projects/new、/projects/:id、/ecml/runs、/value-reports/:id、/tool-catalog/:id），
# 浏览器刷新这些页面仍需返回 SPA。
_SPA_API_NAMESPACES = frozenset({
    "mdm", "qc", "ingest", "data-ingest", "data-quality", "dashboard",
    "capabilities", "capability-contracts", "control-plane", "release-cards",
    "value-report", "knowledge", "knowledge-base", "knowledge-graph",
    "discover", "synthesis", "candidates", "experiments", "samples",
    "equipment", "tools", "budgets", "mappings", "agents", "auth",
    "users", "settings", "materials", "topology", "orchestration",
    "research", "formula-design", "prediction", "workbench",
    "committees", "approvals", "my-tasks", "eval-center",
    "technology-intelligence", "properties", "agent-events", "metrics",
})


@app.middleware("http")
async def spa_html_routes_middleware(request: Request, call_next):
    """浏览器 GET 请求且期望 HTML 时，对非 API/静态资源路径直接返回 SPA 入口。"""
    path = request.url.path
    if (
        request.method == "GET"
        and _frontend_dist.is_dir()
        and "text/html" in (request.headers.get("accept") or "")
        and not path.startswith(_SPA_HTML_SKIP_PREFIXES)
        and path not in _SPA_HTML_EXACT_SKIP
    ):
        # P2-001：API 命名空间下的多级路径（如 /mdm/dict）不返回 SPA，
        # 放行后由 FastAPI 路由未命中返回 404 JSON，避免掩盖"路由不存在"
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 2 and segments[0] in _SPA_API_NAMESPACES:
            return await call_next(request)
        return FileResponse(str(_frontend_index))
    return await call_next(request)


@app.middleware("http")
async def rewrite_api_prefix_middleware(request: Request, call_next):
    """URL 重写中间件：将 /api/xxx 重写为 /xxx。

    背景：前端 axios baseURL 为 '/api'，原设计依赖 vite dev server 的 proxy rewrite
    去掉 /api 前缀。但生产模式下后端直接 serve 前端 dist 时无此 rewrite，
    导致 /api/mdm/... 等请求落到 spa_fallback 返回 404，前端各页面回退到本地兜底常量
    并提示"部分下拉选项未能从主数据加载"。

    本中间件统一在入口处重写 URL，使两种访问方式行为一致：
    - 生产模式：浏览器 → 后端 :8000/api/xxx → 重写为 /xxx → 匹配已注册路由
    - 开发模式：浏览器 → vite :5173/api/xxx → vite proxy 已 rewrite 为 /xxx → 后端不再重写

    假设：本系统后端不注册任何 /api/* 真实路由（所有业务路由均为 /xxx 形式）。
    若未来新增 /api/* 真实路由，需调整本判断或避免使用 /api 前缀。

    实现说明：直接修改 request.scope["path"] 不符合 ASGI 规范的"不可变"约定，
    但 FastAPI/Starlette 的 BaseHTTPMiddleware 实现允许此操作，且是经实测唯一
    能实际影响下游路由匹配的方式（创建新 Request + 浅拷贝 scope 的方式无效）。
    """
    path = request.url.path
    if path.startswith("/api/") or path == "/api":
        new_path = path[4:] or "/"
        request.scope["__api_original_path"] = path
        request.scope["path"] = new_path
        request.scope["raw_path"] = new_path.encode("utf-8")
        request.scope["is_api_request"] = True
        logger.debug("API 前缀重写: %s -> %s", path, new_path)
    # 评测修复 P2-003：路由命名别名——文档/旧客户端使用的历史路径统一重写到现行路由，
    # 避免维护重复的路由处理函数
    cur = request.scope["path"]
    alias = _resolve_route_alias(cur, request.method)
    if alias is not None and alias != cur:
        logger.debug("路由别名重写: %s -> %s", cur, alias)
        request.scope["path"] = alias
        request.scope["raw_path"] = alias.encode("utf-8")
    return await call_next(request)


def _resolve_route_alias(path: str, method: str) -> str | None:
    """P2-003：历史/文档路径 → 现行路由的别名映射。无别名时返回 None。"""
    # /data-ingest/* → /ingest/*
    if path == "/data-ingest":
        return "/ingest/imports"
    if path.startswith("/data-ingest/"):
        return "/ingest/" + path[len("/data-ingest/"):]
    # /capability-contracts[/...] → /capabilities[/...]
    if path == "/capability-contracts":
        return "/capabilities"
    if path.startswith("/capability-contracts/"):
        return "/capabilities/" + path[len("/capability-contracts/"):]
    # /control-plane/budget → /control-plane/budgets（仅此单数形式）
    if path == "/control-plane/budget":
        return "/control-plane/budgets"
    # /value-report/{id} → /value-reports/{id}
    if path.startswith("/value-report/"):
        return "/value-reports/" + path[len("/value-report/"):]
    # GET /knowledge/graph → /knowledge/graphs（POST /knowledge/graph 真实存在，不重写）
    if path == "/knowledge/graph" and method == "GET":
        return "/knowledge/graphs"
    # /mdm/dict/* → /mdm/*（仅 GET 只读语义；POST/PUT/DELETE 不重写，避免非预期写入）
    if method in ("GET", "HEAD"):
        if path.startswith("/mdm/dict/"):
            return "/mdm/" + path[len("/mdm/dict/"):]
        if path == "/mdm/dict":
            return "/mdm/properties"
    # /data-quality/rules → /dashboard/data-quality
    if path == "/data-quality/rules":
        return "/dashboard/data-quality"
    return None


@app.middleware("http")
async def execution_context_middleware(request: Request, call_next):
    """为每个请求注入 ExecutionContext（correlation_id / trace_id / 用户身份）。

    非阻断：上下文创建失败时仅记录告警并以无上下文继续，不影响请求处理。
    健康检查与文档路径跳过上下文注入。

    注：rewrite_api_prefix_middleware 已重写 request.url.path，本中间件看到的是
    重写后的路径（/xxx）。审计/日志如需原始路径（/api/xxx），从 scope 读取
    __api_original_path。
    """
    # 审计与日志使用的原始路径（如未被重写则等同于当前 path）
    audit_path = request.scope.get("__api_original_path") or request.url.path
    # Skip for health checks and docs（重写后 request.url.path 已是 /xxx 形式，直接判断即可）
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    # Extract or generate correlation_id / trace_id
    correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    trace_id = str(uuid.uuid4())

    # Extract user info from token (匿名时 user_id 为 None，角色降级为 viewer)
    # 只信任服务端签发的 X-Auth-Token；裸 X-User-Id 头不再作为身份依据（防冒充）。
    user_id = None
    project_id = request.headers.get("X-Project-Id")
    # user_role 必须来自已认证用户，绝不信任客户端 X-User-Role 头（防伪造）。
    # 中间件先于依赖执行，故此处按 token 自行查表；结果与 get_current_user 一致。
    user_role = "viewer"
    _uid = verify_token(request.headers.get("X-Auth-Token", ""))
    if _uid:
        _store = getattr(request.app.state, "user_store", None)
        if _store is not None:
            _u = _store.get(_uid)
            if _u is not None and _u.is_active:
                user_id = _uid
                user_role = _u.role.value
                request.state.current_user = _u
    # H1: 校验角色合法性，未知值降级为 viewer（fail-closed）。
    if user_role not in {"admin", "pm", "researcher", "reviewer", "viewer"}:
        user_role = "viewer"

    # Create execution context (graceful: continue without it on failure)
    try:
        context = _identity_manager.sign_context(
            user_id=user_id,
            user_role=user_role,
            project_id=project_id,
        )
        context.correlation_id = correlation_id
        context.trace_id = trace_id
        request.state.execution_context = context
    except Exception:
        logger.warning(
            "Failed to create ExecutionContext for %s; continuing without context",
            audit_path,
            exc_info=True,
        )
        request.state.execution_context = None

    # AI 身份服务端化（增量）：Agent 可携带 X-Execution-Context 头
    # （IdentityManager 签发的含 agent_id 的子上下文）。验签+有效期+委托链
    # 校验通过时，服务端据此判定该请求为 AI 发起——高危门禁不再只依赖
    # 请求体自报的 ai_initiated 标志（该标志迁移期保留为冗余信号）。
    _presented_ctx_header = request.headers.get("X-Execution-Context")
    if _presented_ctx_header and request.state.execution_context is not None:
        try:
            from .control_plane.context import ExecutionContext as _ExecCtx
            _presented = _ExecCtx.model_validate(json.loads(_presented_ctx_header))
            if (
                _presented.agent_id
                and _identity_manager.validate_context(_presented)
            ):
                # 沿用本请求的 correlation/trace 便于全链路追踪
                _presented.correlation_id = correlation_id
                _presented.trace_id = trace_id
                request.state.execution_context = _presented
                request.state.ai_principal = True
        except Exception:
            logger.warning("X-Execution-Context 校验失败，按普通用户处理 path=%s", audit_path)

    request.state.correlation_id = correlation_id
    request.state.trace_id = trace_id

    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


@app.on_event("startup")
async def startup():
    """初始化 agent 和 Agent Team 模块。"""
    global agent, _registry, _orchestrator, _executor, _literature_researcher
    global _scp_client_pool, _scp_catalog, _scp_policy, _scp_adapters, _scp_audit_store
    global _committee_policy, _committee_coordinator, _committee_repository, _committee_event_store
    global _skill_catalog, _skill_executor, _llm_provider
    config = get_config()
    agent = BatteryMaterialsAgent(config)
    app.state.agent = agent
    # 评测修复 BEMCL-AI-P2-003：创建统一 LLMProvider 并注入 orchestrator，
    # 消除 httpx 直连 LLM API 的绕过治理链行为
    from .llm.factory import ProviderFactory
    _llm_provider = ProviderFactory.create(config)
    app.state.llm_provider = _llm_provider
    # 初始化 Agent Team 模块（依赖 agent）
    _registry = AgentRegistry()
    _orchestrator = TaskOrchestrator(_registry, agent.config.llm, llm_provider=_llm_provider)
    _executor = AgenticExecutor(_registry, agent)
    # 初始化文献调研员：注入配置与工具注册表，启用 LLM/SCP/WebAPI 真实检索
    _literature_researcher = LiteratureResearcherAgent(
        config=config,
        tool_registry=agent.tools,
        enable_llm=True,
        enable_scp=True,
        enable_web_api=True,
        enable_template_fallback=True,
    )
    # 初始化设备台账存储
    app.state.equipment_store = EquipmentStore()
    # 初始化样品管理存储
    app.state.sample_store = SampleStore()
    # 注册样品守护依赖（供 sample_guard.ensure_sample_for_result / ecml_engine 使用）
    register_sample_store_getter(lambda: getattr(app.state, "sample_store", None))
    register_order_lookup(lambda oid: agent.experiment_controller._store.get_order(oid) if agent else None)
    # 初始化放行卡存储（用于 human_review_required 候选自动创建放行卡）
    from .release_card.store import ReleaseCardStore
    app.state.release_card_store = ReleaseCardStore()
    # 候选材料存储：复用 agent 的 candidate_store，确保 Discovery 和 ECML 两条路径
    # 写入同一 store，下游 Sample/ExperimentOrder 可通过 candidate_id 反查
    app.state.candidate_store = agent.candidate_store
    # 架构解耦（审查 2026-08）：领域模块通过注入获取依赖，禁止反向 import api
    from .release_card.router import set_candidate_store as _rc_set_candidate_store
    _rc_set_candidate_store(agent.candidate_store)
    # T11：放行卡审批回写失败时，将补偿任务写入 notifications，供运维对账
    from .release_card.router import set_notification_sink as _rc_set_notification_sink

    def _rc_notification_sink(order_id: str, assignee: str, message: str) -> None:
        try:
            if not agent.experiment_controller.notification_exists(order_id=order_id, assignee=assignee):
                agent.experiment_controller.save_notification(order_id=order_id, assignee=assignee, message=message)
        except Exception as e:
            logger.warning("放行卡补偿通知写入失败: %s", e)

    _rc_set_notification_sink(_rc_notification_sink)
    from .experiment.experiment_controller import set_raw_material_db
    set_raw_material_db(getattr(agent, "raw_material_db", None))
    # 业务链路 MDM：BOM 方案存储（候选材料 1:N BOM 方案，0021 迁移放宽）
    from .experiment.bom_store import BomStore
    app.state.bom_store = BomStore()
    # 0021 新增：工艺方案存储（与 BomScheme 1:1）
    from .experiment.process_scheme_store import ProcessSchemeStore
    app.state.process_scheme_store = ProcessSchemeStore()
    # 0021 新增：候选材料产出物存储（性质预测、合规检查等结果持久化）
    from .experiment.candidate_artifact_store import CandidateArtifactStore
    app.state.candidate_artifact_store = CandidateArtifactStore()
    # 业务链路 MDM：测试任务存储（实验任务 1:N 测试任务）
    from .experiment.test_task_store import TestTaskStore
    app.state.test_task_store = TestTaskStore()
    # 初始化假设（Idea）存储
    app.state.idea_store = IdeaStore()
    # 初始化用户存储（含默认 admin 用户）
    app.state.user_store = UserStore()
    # Step B：导航可见性覆盖存储（含默认隐藏矩阵 seed）
    from .auth import nav_visibility_store as _nvs
    app.state.nav_visibility_store = _nvs.NavVisibilityStore()
    app.state.nav_entries = list(_nvs.NAV_ENTRIES)
    # P1 参考字典中心：状态码/分类码/单位/方法标准/GHS/通用维度
    from .mdm.reference_dict import ReferenceDictStore
    app.state.reference_dict_store = ReferenceDictStore()
    # P2 物料/样品类型/设备模板/位置主数据
    from .mdm.master_data import MasterDataStore
    app.state.master_data_store = MasterDataStore()
    # P3 CIMC（特性-指标-方法-能力）
    from .mdm.cimc import CimcStore
    app.state.cimc_store = CimcStore()
    # P4 工艺路线-步骤-参数-设备能力
    from .mdm.process import ProcessStore
    app.state.process_store = ProcessStore()
    # P5 文档版本与执行快照
    from .mdm.documents import DocumentStore
    app.state.document_store = DocumentStore()

    # 初始化 SCP 基础设施
    init_audit_db()
    _scp_audit_store = AuditStore()
    _scp_catalog = SCPCatalog()
    # 应用 .env 中对默认绑定启用状态的覆盖
    config.scp.apply_binding_overrides(_scp_catalog)
    _scp_policy = SCPPolicy(_scp_catalog)
    _scp_adapters = {
        "molecule_descriptor": MoleculeDescriptorAdapter(),
        "toxicity_assessment": ToxicityAssessmentAdapter(),
        "literature_search": LiteratureSearchAdapter(),
        "protocol_draft": ProtocolDraftAdapter(),
        "material_transform": MaterialTransformAdapter(),
    }
    if config.scp.enabled:
        _scp_client_pool = SCPClientPool(config.scp)
        agent.tools.register_scp_tools(
            _scp_catalog, _scp_client_pool, _scp_policy,
            _scp_adapters, _scp_audit_store,
        )

    # 工艺深化编排服务（Phase B 第二层：SCP 优先 + 本地回退）
    from .experiment.process_deepening_service import ProcessDeepeningService
    app.state.process_deepening_service = ProcessDeepeningService(
        process_scheme_store=app.state.process_scheme_store,
        candidate_store=app.state.candidate_store,
        scp_client_pool=_scp_client_pool if config.scp.enabled else None,
        scp_catalog=_scp_catalog if config.scp.enabled else None,
    )

    # 初始化 SKILL 基础设施
    from .mcp_tools.skill_catalog import SkillCatalog
    from .mcp_tools.skill_executor import SkillExecutor
    _skill_catalog = SkillCatalog()
    if _scp_client_pool is not None:
        _skill_executor = SkillExecutor(_scp_client_pool, _scp_catalog)

    # 初始化 Committee 模块
    import logging
    _logger = logging.getLogger("battery_materials_agent.api")
    if config.committee.enabled:
        _logger.info("Committee 模块已启用 (COMMITTEE_ENABLED=true)，开始初始化…")
        from .committee.policy import CommitteePolicy
        from .committee.coordinator import CommitteeCoordinator
        from .committee.thinker import CommitteeThinker
        from .committee.doer import CommitteeDoer
        from .committee.verifier import CommitteeVerifier
        from .committee.repository import CommitteeRepository
        from .committee.event_store import CommitteeEventStore
        from .committee.executor import CommitteeExecutor
        from .committee.claim_verifier import ClaimVerifier
        from .domain.runtime.execution_kernel import ScientificExecutionKernel

        _committee_repository = CommitteeRepository()
        _committee_event_store = CommitteeEventStore()
        _committee_policy = CommitteePolicy(config.committee)

        # P0-005 修复：注入真实 executor，使 evidence 收集走 adapter 而非 simulated 分支
        def _candidate_lookup(candidate_id: str):
            """从候选存储中查找候选材料信息。"""
            try:
                from .experiment.candidate_store import CandidateStore
                store = CandidateStore()
                return store.get(candidate_id)
            except Exception as e:
                logger.warning("candidate_lookup failed id=%s: %s", candidate_id, e, exc_info=True)
                return None

        _committee_executor = CommitteeExecutor(candidate_lookup=_candidate_lookup)

        _committee_coordinator = CommitteeCoordinator(
            config=config.committee,
            policy=_committee_policy,
            thinker=CommitteeThinker(),
            doer=CommitteeDoer(),
            verifier=CommitteeVerifier(claim_verifier=ClaimVerifier(ScientificExecutionKernel())),
            repository=_committee_repository,
            event_store=_committee_event_store,
            executor=_committee_executor,
        )
        # Wire committee coordinator into ECML engine
        if hasattr(agent, 'ecml') and agent.ecml is not None:
            agent.ecml.committee_coordinator = _committee_coordinator
        _logger.info("Committee 模块初始化完成。")
    else:
        _logger.warning(
            "Committee 模块未启用 (COMMITTEE_ENABLED=%s)。相关接口将返回 503。"
            "若需启用，请在项目根目录 .env 中设置 COMMITTEE_ENABLED=true 并重启后端。",
            config.committee.enabled,
        )

    # 初始化 Control Plane（Tool Catalog / Gateway / Policy Engine / Store）
    _init_control_plane()

    # 将 Control Plane RunManager 回填到 ECML 引擎，让闭环迭代写入 control_plane.db
    if _run_manager is not None and hasattr(agent, "ecml") and agent.ecml is not None:
        agent.ecml._run_manager = _run_manager
        logger.info("ECML engine wired to Control Plane RunManager")

    # P1-2：初始化统一 Agent 调用事件日志并注入 ECML 引擎，
    # 让委员会中心/控制平面/Agent 管理页共享同一套调用事件数据源
    global _agent_event_log
    try:
        from .agent_team.event_log import AgentEventLog
        _agent_event_log = AgentEventLog(db_path=str(config.data_dir / "agent_events.db"))
        if hasattr(agent, "ecml") and agent.ecml is not None:
            agent.ecml._agent_event_log = _agent_event_log
        logger.info("Agent event log initialized")
    except Exception as e:
        logger.warning("Agent event log init failed (non-fatal): %s", e)

    # 决策 1-13：业务活动—智能体—工具 三层映射初始化
    # - ActivityMappingStore：持久化 + 全量缓存（决策 12-C）
    # - AgentProxy：智能体代理层（决策 7-A），业务活动通过它调用工具
    # - 注入 ECML 引擎，让每个 step 的智能体+工具绑定信息可被前端感知（决策 3-C）
    global _activity_mapping_store, _agent_proxy
    try:
        from .agent_team.activity_mapping import ActivityMappingStore, seed_default_mappings
        _activity_mapping_store = ActivityMappingStore()
        seed_default_mappings(_activity_mapping_store)
        logger.info("Activity mapping store initialized with %d activities, %d tool bindings, %d tools",
                    len(_activity_mapping_store.list_activity_bindings()),
                    len(_activity_mapping_store.list_tool_bindings()),
                    len(_activity_mapping_store.list_tool_registrations()))

        from .agent_team.agent_proxy import AgentProxy
        from .services.registry import get_service_registry

        _agent_proxy = AgentProxy(
            agent_registry=_registry,
            mapping_store=_activity_mapping_store,
            mcp_tool_registry=agent.tools,
            capability_router=_capability_router if '_capability_router' in globals() else None,
            tool_gateway=_tool_gateway,
            scp_client_pool=_scp_client_pool,
            scp_catalog=_scp_catalog,
            skill_catalog=_skill_catalog,
            skill_executor=_skill_executor,
            scientific_registry=get_service_registry(),
        )
        # 注入到 ECML 引擎
        if hasattr(agent, "ecml") and agent.ecml is not None:
            agent.ecml._agent_proxy = _agent_proxy
        # 注入映射控制台子路由（替代其反向 import api 全局变量）
        from .agent_team import mapping_router as _mapping_router_module
        _mapping_router_module.configure(_activity_mapping_store, _agent_proxy)
        logger.info("AgentProxy initialized and wired to ECML engine")
    except Exception as e:
        logger.warning("Activity mapping / AgentProxy init failed (non-fatal): %s", e)

    # P3-1：初始化统一研发事件流水表，作为首页看板"最近活动"、迭代历史、
    # 控制平面运行队列的唯一业务事件数据源（委员会触发沿用 triggers.py，
    # 其触发条件与本表同源——均由同一批业务动作产生）
    global _research_event_stream
    try:
        from .agent_team.research_event_stream import ResearchEventStream
        _research_event_stream = ResearchEventStream(
            db_path=str(config.data_dir / "research_events.db")
        )
        logger.info("Research event stream initialized")
    except Exception as e:
        logger.warning("Research event stream init failed (non-fatal): %s", e)

    # 同步 MCPToolRegistry 工具到 Control Plane ToolCatalog，
    # 让 /control-plane/tools 返回与 /tools 一致的真实工具列表
    if _tool_catalog is not None and hasattr(agent, "tools"):
        from .control_plane.tool_catalog import ToolDescriptor, ToolRiskLevel
        _source_map = {"local": "local", "scp": "scp", "internlm": "mcp"}
        for mcp_tool in agent.tools.list_tools():
            if not _tool_catalog.is_registered(mcp_tool.name):
                risk = ToolRiskLevel.D
                if mcp_tool.risk_level in ("A", "B", "C", "D"):
                    risk = ToolRiskLevel(mcp_tool.risk_level)
                _tool_catalog.register(ToolDescriptor(
                    tool_id=mcp_tool.name,
                    source=_source_map.get(mcp_tool.source, "mcp"),
                    description=mcp_tool.description,
                    risk_level=risk,
                ))
        # 评测修复 P1-001：全部工具注册完成后，按默认回退链补齐 fallback_tool_id
        _applied = _tool_catalog.apply_default_fallbacks()
        if _applied:
            logger.info("工具默认 fallback 配置完成: 新增 %d 条回退关系", _applied)

        # 评测修复 P1-018：工具 health_status 初始化 + 定期刷新
        def _collect_provider_health() -> dict[str, str]:
            """按 provider_type 聚合最差健康状态：scp→SCP 族, mcp→LLM。"""
            health: dict[str, str] = {}
            if _provider_registry is None:
                return health
            _rank = {"healthy": 0, "degraded": 1, "unhealthy": 2, "unknown": 3}
            try:
                for p in _provider_registry.list_providers():
                    ptype = p.provider_type.value
                    key = "mcp" if ptype == "llm" else ptype
                    cur = p.health_status.value
                    if key not in health or _rank.get(cur, 3) > _rank.get(health[key], 3):
                        health[key] = cur
            except Exception:
                pass
            return health

        # 评测修复 P1-018：provider 健康探测（启动即执行 + 周期执行），
        # 使 scp/mcp 工具的 health_status 不停留在 unknown。
        # local:// → healthy；http(s) → GET health_check_url/endpoint，
        # 2xx→healthy，4xx→degraded，5xx/不可达→unhealthy（真实反映环境状态）。
        async def _probe_providers_once() -> None:
            if _provider_registry is None:
                return
            import httpx as _httpx
            from .control_plane.provider_registry import ProviderHealth as _PH

            async def _probe_one(p):
                try:
                    if (p.endpoint or "").startswith("local://"):
                        _provider_registry.update_health(p.provider_id, _PH.HEALTHY)
                        return
                    ptype = getattr(p, "provider_type", None)
                    ptype_val = getattr(ptype, "value", None) if ptype is not None else None

                    # ── SCP（MCP JSON-RPC 端点，只接受 POST）：用 tools/list 探测 ──
                    if ptype_val == "scp":
                        h = _PH.UNHEALTHY
                        try:
                            tools = await _scp_client_pool.list_tools(
                                p.provider_id, server_url=p.endpoint or None
                            )
                            if tools and tools[0].get("_error"):
                                # 远端可达但 JSON-RPC 报错 → 降级
                                h = _PH.DEGRADED
                            else:
                                h = _PH.HEALTHY
                        except Exception:
                            h = _PH.UNHEALTHY
                        _provider_registry.update_health(p.provider_id, h)
                        return

                    # ── LLM（OpenAI 兼容 /chat/completions）：用 GET /models 探测 ──
                    if ptype_val == "llm":
                        base = (p.endpoint or "").rstrip("/")
                        url = f"{base}/models"
                        try:
                            async with _httpx.AsyncClient(
                                timeout=_httpx.Timeout(4.0), follow_redirects=True
                            ) as client:
                                resp = await client.get(url)
                            h = _PH.HEALTHY if resp.status_code < 500 else _PH.UNHEALTHY
                        except Exception:
                            h = _PH.UNHEALTHY
                        _provider_registry.update_health(p.provider_id, h)
                        return

                    # ── 其余 REST 服务（materials_project / askcos 等）：GET endpoint ──
                    url = p.health_check_url or p.endpoint or ""
                    if not url.startswith(("http://", "https://")):
                        return
                    try:
                        async with _httpx.AsyncClient(
                            timeout=_httpx.Timeout(4.0), follow_redirects=True
                        ) as client:
                            resp = await client.get(url)
                        if 200 <= resp.status_code < 300:
                            h = _PH.HEALTHY
                        elif 400 <= resp.status_code < 500:
                            h = _PH.DEGRADED
                        else:
                            h = _PH.UNHEALTHY
                    except Exception:
                        h = _PH.UNHEALTHY
                    _provider_registry.update_health(p.provider_id, h)
                except Exception:
                    pass

            try:
                await asyncio.gather(
                    *(_probe_one(p) for p in _provider_registry.list_providers())
                )
            except Exception:
                pass

        async def _tool_health_loop():
            while True:
                try:
                    await _probe_providers_once()
                    counts = _tool_catalog.refresh_health(_collect_provider_health())
                    logger.debug("工具健康刷新: %s", counts)
                except Exception:
                    logger.debug("工具健康刷新失败", exc_info=True)
                await asyncio.sleep(300)

        try:
            _tool_catalog.refresh_health(_collect_provider_health())
            _spawn_background(_tool_health_loop())
        except Exception as e:
            logger.warning("工具健康检查启动失败 (non-fatal): %s", e)

    # 评测修复 P1-019：token 用量回写预算系统（usage sink）
    if _budget_manager is not None:
        try:
            from .llm.token_tracker import set_usage_sink
            from .control_plane.budget import BudgetScope, BudgetCategory

            def _token_usage_sink(project_id: str, total_tokens: int) -> None:
                if total_tokens <= 0:
                    return
                scope = BudgetScope.PROJECT if project_id else BudgetScope.ORGANIZATION
                scope_id = project_id or "global"
                try:
                    entry = _budget_manager.reserve(
                        scope, scope_id, BudgetCategory.TOKEN, float(total_tokens),
                    )
                    _budget_manager.settle(entry.ledger_id, float(total_tokens))
                except ValueError as ve:
                    # 预算超限：记录告警，不阻断 LLM 调用本身
                    logger.warning("token 预算回写被拒 (%s:%s): %s", scope.value, scope_id, ve)
                except Exception:
                    logger.debug("token 预算回写失败", exc_info=True)

            set_usage_sink(_token_usage_sink)
            logger.info("Token 用量统计已接入预算系统")
        except Exception as e:
            logger.warning("Token 用量预算回写接入失败 (non-fatal): %s", e)

    # 一次性数据迁移：把 middleware 历史实验记录中的 sample_id 导入 sample_store，
    # 打通历史数据与样品管理模块
    try:
        existing_samples = app.state.sample_store.list_all()
        existing_ids = {s.sample_id for s in existing_samples}
        migrated = 0
        for record in agent.middleware.query_records(limit=10000):
            if record.sample_id and record.sample_id not in existing_ids:
                app.state.sample_store.save(Sample(
                    sample_id=record.sample_id,
                    name=record.sample_id,
                    source_type="experiment_legacy",
                ))
                existing_ids.add(record.sample_id)
                migrated += 1
        if migrated:
            logger.info("历史样品数据迁移完成: 新增 %d 条样品记录", migrated)
    except Exception as e:
        logger.warning("历史样品数据迁移失败: %s", e)

    # ── 启动 CoE Audit 每日凌晨定时审计 ──
    try:
        from datetime import datetime as _dt, timezone, time as _time, timedelta as _timedelta

        async def _daily_coe_audit():
            """每日凌晨 01:00 触发一次证据链完整性审计。"""
            while True:
                now = _dt.now()
                target = now.replace(hour=1, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += _timedelta(days=1)
                await asyncio.sleep((target - now).total_seconds())
                try:
                    report = _coe_auditor.run(limit=100)
                    logger.info(
                        "每日 CoE Audit 完成: integrity=%s report=%s",
                        report.get("metrics", {}).get("integrity_score"),
                        report.get("report_path"),
                    )
                except Exception as e:
                    logger.warning("每日 CoE Audit 失败: %s", e)

        _audit_task = asyncio.create_task(_daily_coe_audit())
        _background_tasks.add(_audit_task)
        _audit_task.add_done_callback(_background_tasks.discard)
        logger.info("CoE Audit 每日定时任务已启动（每日 01:00）")
    except Exception as e:
        logger.warning("CoE Audit 定时任务启动失败 (non-fatal): %s", e)

    # ── 启动原生科学服务 CPU Worker ──
    try:
        from .services.registry import setup_cpu_worker
        from .workers.cpu_worker import start_worker
        setup_cpu_worker()
        start_worker()
        logger.info("Scientific CPU Worker started with all 12 native services")
    except Exception as e:
        logger.warning("Scientific CPU Worker startup failed (non-fatal): %s", e)

    # ── 启动 Outbox 消费者（可靠事件派发） ──
    # 若无消费者，execution_kernel 入队的任务/运行/审批事件会永久滞留在 pending。
    try:
        from .domain.runtime.outbox import ScientificOutbox
        from .domain.runtime.outbox_dispatcher import OutboxDispatcher
        _dispatcher = OutboxDispatcher(ScientificOutbox())
        _spawn_background(_dispatcher.run_forever())
        logger.info("Outbox 消费者已启动")
    except Exception as e:
        logger.warning("Outbox 消费者启动失败 (non-fatal): %s", e)

    # ── 启动报表定时调度器（APScheduler + PostgreSQL 持久化） ──
    try:
        start_report_scheduler()
        logger.info("报表定时调度器已启动（APScheduler 持久化调度）")
    except Exception as e:
        logger.warning("报表定时调度器启动失败 (non-fatal): %s", e)


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理后台任务与外部连接池。"""
    # 取消尚未完成的后台任务
    for task in list(_background_tasks):
        if not task.done():
            task.cancel()
    # 等待任务结束（忽略 CancelledError）
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()
    # 关闭 SynthesisPlanner 的 httpx 连接池
    if agent is not None and getattr(agent, "synthesis_planner", None) is not None:
        try:
            await agent.synthesis_planner.aclose()
        except Exception as e:
            logger.warning("关闭 SynthesisPlanner 连接池失败: %s", e)

    # 停止科学服务 CPU Worker
    try:
        from .workers.cpu_worker import stop_worker
        stop_worker()
        logger.info("Scientific CPU Worker stopped")
    except Exception as e:
        logger.warning("Scientific CPU Worker stop failed (non-fatal): %s", e)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：返回具体的错误信息而非笼统的 500，便于前端定位问题。"""
    import logging
    logger = logging.getLogger("battery_materials_agent.api")
    logger.error("未处理异常 %s %s: %s", request.method, request.url.path, exc, exc_info=True)

    # 区分常见异常类型给出可操作提示
    exc_type = type(exc).__name__
    hint = "请检查请求参数后重试；如持续出现，请查看后端日志定位"
    if "ConnectionRefused" in str(exc) or "ConnectionError" in exc_type:
        hint = "下游服务连接失败，请确认 ASKCOS / Materials Project 等外部服务可用"
    elif "Timeout" in exc_type or "timeout" in str(exc).lower():
        hint = "下游服务响应超时，请稍后重试或检查服务负载"

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": "internal_error",
                "message": f"{exc_type}: {exc}",
                "path": request.url.path,
                "method": request.method,
                "hint": hint,
            }
        },
    )


def _require_agent_team():
    """守卫：Agent Team 模块未初始化时抛出 503。"""
    if _registry is None or _orchestrator is None or _executor is None:
        raise HTTPException(status_code=503, detail="Agent Team 模块未初始化，请稍后重试")


def _get_execution_context(request: Request) -> ExecutionContext | None:
    """从 request.state 取出中间件注入的 ExecutionContext，未注入时返回 None。"""
    return getattr(request.state, "execution_context", None)


class RouteRequest(BaseModel):
    name: str = ""
    smiles: str = ""
    psmiles: str = ""
    cif_path: str = ""
    formula: str = ""


class DiscoverRequest(BaseModel):
    target: str = ""
    target_property: str = "tensile_strength"  # v4.1 改性塑料默认目标
    max_iterations: int = Field(default=3, ge=1, le=20)
    elements: list[str] = Field(default_factory=list)
    num_candidates: int = Field(default=10, ge=1, le=50)  # P1-004: 添加边界校验
    run_id: str = ""  # 可选：传入已有 run_id 可恢复中断的运行
    target_properties: list[dict] = Field(default_factory=list)  # 多目标：[{property, weight, direction, min, max}]
    parent_run_id: str = ""  # 可选：父轮次 run_id，用于迭代链追溯
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    smiles: str = ""  # 聚合物输入：SMILES / 体系提示（v4.1 透传给生成器）
    # 评测修复 P0-002：关联项目/任务，发现生成的候选材料必须落到项目下，
    # 否则 /projects/{id}/candidates 永远查不到（项目-候选关联断裂）
    project_id: str = ""
    task_id: str = ""


class GenerateRequest(BaseModel):
    mode: str = "molecule"  # molecule / crystal
    constraints: dict = Field(default_factory=dict)
    count: int = 10


class SynthesisRequest(BaseModel):
    smiles: str


class VerifyRequest(BaseModel):
    smiles: str
    property_name: str = "total_energy"


class ExperimentQueryRequest(BaseModel):
    formula: str = ""
    experiment_type: str = ""
    project_id: str = ""
    sample_id: str = ""
    batch_id: str = ""
    source_type: str = ""
    operator: str = ""
    order_id: str = ""
    date_from: str = ""
    date_to: str = ""


class SynthesisPlanRequest(BaseModel):
    smiles: str
    max_depth: int = 3
    num_routes: int = 5
    scenario_id: str = ""  # P0-001：关联研发场景 ID


class MultiSynthesisPlanRequest(BaseModel):
    smiles: str
    num_routes: int = 3
    scenario_id: str = ""  # P0-001：关联研发场景 ID


class DFTVerifyRequest(BaseModel):
    """DFT 可行性校验请求：传入单条合成路线。"""
    route: dict = Field(default_factory=dict)


class SynthesisAsyncRequest(BaseModel):
    """异步合成规划请求：提交后立即返回 task_id，前端轮询结果。"""
    smiles: str = ""
    num_routes: int = 3
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    # 0727：允许前端显式指定合成引擎（覆盖系统设置），可选 askcos/internlm（logos 为兼容别名）
    engine_type: str | None = None
    # 0727：允许前端指定由哪个有 synthesis_evidence 能力的 agent 执行
    agent_id: str | None = None
    # 0727：材料类型，crystal 走 InternLM 固相合成，molecule 走原 ASKCOS/InternLM 逆合成
    material_type: str = "molecule"
    # 0727：晶体候选的化学式（material_type=crystal 时必填）
    formula: str = ""
    # 0727：晶体候选的空间群（可选，提升 LLM 推理质量）
    space_group: str = ""
    # 0021：关联候选材料 ID，便于按候选回溯合成历史与从路径生成 BOM
    candidate_id: str = ""


class ManualRouteStep(BaseModel):
    reactants: list[str]
    conditions: str = ""
    score: float = 0.5


class ManualRouteRequest(BaseModel):
    """手动填写合成路线（逆合成服务不可用时的业务兜底）。"""
    smiles: str
    steps: list[ManualRouteStep]
    note: str = ""
    scenario_id: str = ""  # P0-001：关联研发场景 ID


class ECMLRunStepRequest(BaseModel):
    target: str = ""
    target_property: str = "ionic_conductivity"
    max_iterations: int = 3
    target_properties: list[dict] = Field(default_factory=list)  # 多目标：[{property, weight, direction, min, max}]
    parent_run_id: str = ""  # 可选：父轮次 run_id，启动下一轮时传入形成迭代链
    scenario_id: str = ""  # 可选：关联研发场景 ID
    task_id: str = ""  # 可选：关联 projects.tasks(task_id)，供 stage-status 反查
    project_id: str = ""  # 可选：关联研发项目 ID，用于"本项目/跨项目"数据隔离


class ConfigUpdateRequest(BaseModel):
    mp_api_key: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_max_tokens: int | None = None
    crystal_model: str | None = None
    polymer_model: str | None = None
    dft_method: str | None = None
    basis_set: str | None = None
    askcos_url: str | None = None
    internlm_enabled: bool | None = None
    internlm_api_key: str | None = None
    internlm_base_url: str | None = None
    internlm_model: str | None = None
    internlm_timeout: float | None = None
    internlm_thinking_mode: bool | None = None
    internlm_max_concurrency: int | None = None
    scp_enabled: bool | None = None
    scp_api_key: str | None = None
    scp_base_url: str | None = None
    scp_allowed_servers: list[str] | None = None
    scp_allowed_tools: list[str] | None = None
    scp_max_concurrency: int | None = None
    engine_mode: str | None = None
    run_mode: str | None = None


class ConfigUpdatePayload(BaseModel):
    engine_mode: str | None = None
    logos_base_url: str | None = None
    logos_model_name: str | None = None
    logos_api_key: str | None = None
    logos_timeout: int | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_max_tokens: int | None = None


class CreateAgentRequest(BaseModel):
    name: str
    role: str = "custom"
    description: str = ""
    expertise: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    avatar: str = "🤖"
    llm_model: str = "LongCat-2.0"
    # 模型提供方："llm" / "internlm" / ""（自动）
    provider: str = ""
    # 备选模型（fallback）：优先模型失败时自动调用。空表示无 fallback
    provider_secondary: str = ""
    llm_model_secondary: str = ""


class AgentChatRequest(BaseModel):
    """智能体测试对话请求。"""
    message: str
    history: list[dict] = Field(default_factory=list)  # [{role, content}, ...]


class AnalyzeTaskRequest(BaseModel):
    target: str
    constraints: dict = Field(default_factory=dict)


class ExecutePlanRequest(BaseModel):
    target: str
    team: list[dict]  # AgentDefinition dicts
    steps: list[dict]  # TaskStep dicts


class ExperimentOrderRequest(BaseModel):
    project_id: str = ""
    rd_package_id: str = ""
    candidate_id: str = ""
    process_id: str = ""  # 0040：双来源引用——关联已确认的工艺方案（ProcessScheme）
    formulation_version: str = ""
    process_version: str = ""
    test_protocol_version: str = ""
    execution_mode: str = "MANUAL_ENTRY"
    priority: str = "P2"
    assignee: str = ""
    material_requirements: list[dict] = Field(default_factory=list)
    procedure: list[dict] = Field(default_factory=list)
    required_results: list[str] = Field(default_factory=list)
    acceptance_criteria: dict = Field(default_factory=dict)
    notes: str = ""
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    bom_id: str = ""  # 业务链路：关联 experiment.bom_schemes(bom_id)
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)
    idempotency_key: str = ""  # 幂等键：同一 key 重复提交返回首次创建的订单，防止双击/重试产生重复任务单
    ai_initiated: bool = False  # T-031：标记为 AI 自动创建时进入人工确认三段式


class ExperimentResultManualRequest(BaseModel):
    experiment_order_id: str = ""
    sample_id: str = ""
    sample_batch_id: str = ""
    property_name: str = ""
    value: float  # P0-5：必填，不传或解析失败立即返回 422（不再静默兜底为 0）
    unit: str = ""
    test_method: str = ""
    test_conditions: dict = Field(default_factory=dict)
    instrument_id: str = ""
    uploaded_by: str = ""
    raw_file_uri: str = ""
    scenario_id: str = ""  # P0-001：关联研发场景 ID（未传时由 order_id 反查填充）
    # 评测修复 P2-5：数据质量分层标记，默认 estimated，QC 审批通过后自动升级为 verified
    data_quality: str = "estimated"
    # T-029：标记结果来源为 AI 预测（非人工录入），触发按 confidence 自动标记 data_quality
    ai_generated: bool = False
    # T-029：AI 预测置信度，ai_generated=True 时据此分层：>=0.8 → simulated，<0.8 → estimated
    confidence: float | None = None

    @field_validator("data_quality")
    @classmethod
    def _validate_data_quality(cls, v: str) -> str:
        allowed = {"verified", "estimated", "simulated", "literature"}
        if v and v not in allowed:
            raise ValueError(f"data_quality 必须为 {sorted(allowed)} 之一")
        return v or "estimated"

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: float) -> float:
        # 拒绝 NaN 与无穷大，避免脏数据入库后被展示为 0
        if v is None:
            raise ValueError("value 不能为空")
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ValueError("value 不能为 NaN 或无穷大")
        return v


from .validators import (_normalize_test_method, _normalize_unit, _normalize_property_name, _validate_value_range)


class QCApproveRequest(BaseModel):
    reviewed_by: str = ""
    learning_eligible: bool = False
    reason: str = ""


def _is_ai_initiated(request: Request, payload_flag: bool) -> bool:
    """服务端判定 AI 发起（T-031 门禁信号收敛）。

    权威信号：验签通过的 X-Execution-Context 且含 agent_id（见
    execution_context_middleware）。请求体 ai_initiated 自报标志不再作为
    任何信任依据——删掉它也不改变判定结果（防冒名 AI 身份）。
    """
    if getattr(request.state, "ai_principal", False):
        return True
    ctx = getattr(request.state, "execution_context", None)
    if ctx is not None and getattr(ctx, "agent_id", None):
        return True
    return False


class OrderApprovalRequest(BaseModel):
    approved_by: str = ""
    notes: str = ""


class ApprovalJudgeRequest(BaseModel):
    candidate: dict = Field(default_factory=dict)
    estimated_cost: float = 0.0
    model_confidence: float = 1.0


class DeviationCheckRequest(BaseModel):
    order_id: str
    predicted_values: dict = Field(default_factory=dict)
    threshold: float = 0.2


class AnomalyMarkRequest(BaseModel):
    anomalies: list[dict] = Field(default_factory=list)


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    target_application: str = ""
    current_stage: str = "立项"
    target_properties: list[dict] = Field(default_factory=list)
    owner: str = ""
    notes: str = ""
    department: str = ""
    start_date: str = ""
    end_date: str = ""
    budget: float = Field(default=0.0, ge=0)
    iteration_progress: int = Field(default=0, ge=0, le=100)
    # 项目立项时拆解出的任务列表，每项含交付物（材料）与目标属性
    tasks: list[dict] = Field(default_factory=list)


class ProjectDecomposeRequest(BaseModel):
    """AI 拆解项目目标的请求。"""
    name: str = Field(..., min_length=1, max_length=100)
    goal: str = Field(..., min_length=1)
    end_date: str = ""
    # 触发拆解的 Agent ID（通常为项目经理 Agent）；后端将使用该 Agent 的
    # llm_model 与人设（description / expertise / capabilities）进行调用
    agent_id: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


# ===========================================================================
# 认证与用户管理 API
# ===========================================================================

class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class UserCreateRequest(BaseModel):
    username: str = ""
    display_name: str = ""
    email: str = ""
    role: str = "viewer"
    project_ids: list[str] = Field(default_factory=list)
    password: str = ""
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    project_ids: list[str] | None = None
    password: str | None = None  # 留空则不修改密码
    is_active: bool | None = None
    disciplines: list[str] | None = None
    primary_discipline: str | None = None


class MyDisciplinesRequest(BaseModel):
    disciplines: list[str] = Field(default_factory=list)
    primary_discipline: str = ""


class NavVisibilityUpdateRequest(BaseModel):
    """nav_visibility 批量覆盖：{role: {entry_key: visible}}。"""
    matrix: dict[str, dict[str, bool]] = Field(default_factory=dict)


def _user_to_dict(user: User) -> dict:
    """转换为字典并剔除密码哈希，避免泄露到接口响应。"""
    d = user.model_dump()
    d.pop("password_hash", None)
    return d


def user_permissions(user: User | None) -> list[str]:
    """返回当前用户拥有的权限点列表（供前端 UI 门禁用）。"""
    if user is None:
        return []
    from .auth.permissions import ROLE_PERMISSIONS, role_has_permission
    if user.role == UserRole.ADMIN:
        perms = set()
        for permset in ROLE_PERMISSIONS.values():
            perms |= permset
        perms |= {"user.manage", "tenant.manage"}
        return sorted(perms)
    return sorted(ROLE_PERMISSIONS.get(user.role, set()))


@app.post("/auth/login")
async def login(req: LoginRequest, request: Request):
    """登录：校验用户名/密码，签发带 HMAC 签名与过期时间的认证 token。"""
    store: UserStore = app.state.user_store
    user = store.get_by_username(req.username)
    client_ip = request.client.host if request.client else ""
    if user is None or not user.is_active or not verify_password(req.password, user.password_hash):
        # LDAP 兜底：本地用户不存在或密码不符时，尝试企业 LDAP 认证（A2）
        from .config import get_config as _gc
        ldap_cfg = _gc().ldap
        if ldap_cfg.enabled and ldap_cfg.server:
            try:
                identity = ldap_auth.authenticate(ldap_cfg, req.username, req.password)
                if identity:
                    user, _created = sso_module.provision_user(
                        store, ldap_cfg, dict(identity, default_role=ldap_cfg.default_role,
                                              default_tenant=ldap_cfg.default_tenant),
                        auth_source="ldap",
                    )
                    store.update_last_login(user.user_id)
                    get_audit_logger().log(AuditEntry(
                        event_type="auth", module="auth", action="ldap_login",
                        operator=user.username, user_id=user.user_id, ip=client_ip,
                        resource_type="user", resource_id=user.user_id,
                        tenant_id=user.tenant_id,
                    ))
                    return {
                        "user_id": user.user_id, "username": user.username,
                        "display_name": user.display_name, "email": user.email,
                        "role": user.role.value, "project_ids": user.project_ids,
                        "tenant_id": user.tenant_id or "default",
                        "token": issue_token(user.user_id),
                    }
            except Exception as e:
                logger.warning("LDAP 认证异常：%s", e)
        # 认证失败审计（登录失败不一定有 user，operator 用请求用户名）
        get_audit_logger().log(AuditEntry(
            event_type="auth", module="auth", action="login_failed",
            operator=req.username, ip=client_ip,
            detail={"username": req.username},
        ))
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    # 旧 sha256 格式密码在登录成功时透明升级为 pbkdf2
    if is_legacy_hash(user.password_hash):
        user.password_hash = hash_password(req.password)
        store.save(user)
    store.update_last_login(user.user_id)
    get_audit_logger().log(AuditEntry(
        event_type="auth", module="auth", action="login_success",
        operator=user.username, user_id=user.user_id, ip=client_ip,
        resource_type="user", resource_id=user.user_id,
        tenant_id=user.tenant_id,
    ))
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.value,
        "project_ids": user.project_ids,
        "tenant_id": user.tenant_id or "default",
        "token": issue_token(user.user_id),
    }


# --- 企业 SSO / LDAP 认证（A2）---

def _sso_enabled() -> bool:
    from .config import get_config as _gc
    return _gc().sso.enabled


@app.get("/auth/sso/status")
async def sso_status():
    """返回 SSO 是否启用（前端据此显示登录按钮）。"""
    return {"enabled": _sso_enabled()}


@app.get("/auth/sso/login")
async def sso_login(request: Request):
    """重定向到 IdP 授权端点。"""
    from .config import get_config as _gc
    cfg = _gc().sso
    if not cfg.enabled or not cfg.issuer or not cfg.client_id:
        raise HTTPException(status_code=400, detail="SSO 未启用或配置不完整")
    state = sso_module.make_state("sso-login")
    try:
        url = sso_module.build_auth_url(cfg, state)
    except Exception as e:
        logger.error("构造 SSO 授权 URL 失败：%s", e)
        raise HTTPException(status_code=502, detail="无法连接企业身份提供商")
    return RedirectResponse(url)


@app.get("/auth/sso/callback")
async def sso_callback(code: str, state: str):
    """IdP 回调：校验 state → 换 token → JIT 开户 → 签发本系统 token。"""
    from .config import get_config as _gc
    cfg = _gc().sso
    if not sso_module.verify_state(state):
        raise HTTPException(status_code=400, detail="state 校验失败，请重新发起登录")
    try:
        token_resp = sso_module.exchange_code(cfg, code)
        claims = sso_module._extract_claims(cfg, token_resp)
        identity = sso_module.claims_to_identity(claims)
    except Exception as e:
        logger.error("SSO 换 token 失败：%s", e)
        raise HTTPException(status_code=401, detail="SSO 认证失败")
    store: UserStore = app.state.user_store
    try:
        user, created = sso_module.provision_user(store, cfg, identity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    store.update_last_login(user.user_id)
    get_audit_logger().log(AuditEntry(
        event_type="auth", module="auth", action="sso_login",
        operator=user.username, user_id=user.user_id,
        resource_type="user", resource_id=user.user_id,
        tenant_id=user.tenant_id,
    ))
    token = issue_token(user.user_id)
    return RedirectResponse(f"/login?sso_token={token}")


@app.get("/auth/me")
async def get_me(current: User | None = Depends(get_current_user)):
    """获取当前登录用户信息（依据 X-Auth-Token 请求头）。"""
    if current is None:
        raise HTTPException(status_code=401, detail="未登录")
    data = _user_to_dict(current)
    data["permissions"] = user_permissions(current)
    return data


@app.post("/auth/logout")
async def logout(current: User | None = Depends(get_current_user)):
    """退出登录。

    本系统采用无状态签名 token 鉴权（X-Auth-Token 请求头），后端不维护 session，
    因此注销仅做形式化确认并记录审计日志，前端负责清理本地凭证。
    """
    if current is not None:
        logger.info("User logged out: %s", current.user_id)
    return {"logged_out": True}


@app.get("/auth/users", dependencies=[Depends(require_permission("user.manage"))])
async def list_users():
    """列出所有用户（user.manage 权限）。"""
    store: UserStore = app.state.user_store
    return [_user_to_dict(u) for u in store.list_all()]


@app.get("/auth/users/brief", dependencies=[Depends(require_login)])
async def list_users_brief():
    """返回用户简要列表（id + display_name），供项目负责人选择等场景使用。"""
    store: UserStore = app.state.user_store
    return [{"user_id": u.user_id, "display_name": u.display_name or u.username} for u in store.list_all()]


@app.post("/auth/users", dependencies=[Depends(require_permission("user.manage"))])
async def create_user(req: UserCreateRequest):
    """创建用户（user.manage 权限）。"""
    store: UserStore = app.state.user_store
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if store.get_by_username(req.username) is not None:
        raise HTTPException(status_code=409, detail=f"用户名 {req.username} 已存在")
    try:
        role = UserRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的角色: {req.role}")
    user = User(
        username=req.username,
        display_name=req.display_name,
        email=req.email,
        role=role,
        project_ids=req.project_ids,
        is_active=req.is_active,
        password_hash=hash_password(req.password or ""),
    )
    store.save(user)
    return _user_to_dict(user)


@app.put("/auth/users/{user_id}", dependencies=[Depends(require_permission("user.manage"))])
async def update_user(user_id: str, req: UserUpdateRequest, current: User = Depends(require_login)):
    """更新用户（user.manage 权限）。password 留空则不修改。"""
    store: UserStore = app.state.user_store
    user = store.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.email is not None:
        user.email = req.email
    if req.role is not None:
        try:
            user.role = UserRole(req.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的角色: {req.role}")
    if req.project_ids is not None:
        user.project_ids = req.project_ids
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password:
        user.password_hash = hash_password(req.password)
    # 专业画像：任一字段非 None 时整体归一化并校验（P0 不变量）
    if req.disciplines is not None or req.primary_discipline is not None:
        before = {"disciplines": user.disciplines, "primary_discipline": user.primary_discipline}
        try:
            ds, p = normalize_disciplines(
                req.disciplines if req.disciplines is not None else user.disciplines,
                req.primary_discipline if req.primary_discipline is not None else user.primary_discipline,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        user.disciplines, user.primary_discipline = ds, p
        get_audit_logger().log(AuditEntry(
            event_type="human_edit", module="auth", action="update_user_disciplines",
            operator=current.username, user_id=current.user_id,
            resource_type="user", resource_id=user.user_id,
            before=before, after={"disciplines": ds, "primary_discipline": p},
            tenant_id=user.tenant_id,
        ))
    store.save(user)
    return _user_to_dict(user)


@app.put("/auth/me/disciplines")
async def update_my_disciplines(req: MyDisciplinesRequest, current: User = Depends(require_login)):
    """当前用户自助修改自己的专业画像（无需 user.manage 权限）。"""
    try:
        ds, p = normalize_disciplines(req.disciplines, req.primary_discipline)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    before = {"disciplines": current.disciplines, "primary_discipline": current.primary_discipline}
    current.disciplines, current.primary_discipline = ds, p
    app.state.user_store.save(current)
    get_audit_logger().log(AuditEntry(
        event_type="human_edit", module="auth", action="update_my_disciplines",
        operator=current.username, user_id=current.user_id,
        resource_type="user", resource_id=current.user_id,
        before=before, after={"disciplines": ds, "primary_discipline": p},
        tenant_id=current.tenant_id,
    ))
    return _user_to_dict(current)


# --- 导航可见性（Step B） ---

@app.get("/nav-visibility")
async def get_nav_visibility(current: User = Depends(require_login)):
    """导航可见性。

    - 普通角色：返回其角色的可见 entry_key 列表；
    - 具备 ``user.manage`` 权限（系统管理员）：返回全量矩阵（role × entry_key）。
    visible=true 不能把无最小权限入口变可见；权限下限由后端 permission 判定保证。
    """
    store = app.state.nav_visibility_store
    if role_has_permission(current.role, "user.manage"):
        return {
            "entries": list(app.state.nav_entries),
            "matrix": {
                role: store.role_matrix(role)
                for role in sorted({r.role for r in store.list_all()})
                if role
            },
        }
    role_entries = store.visible_entries(current.role.value)
    return {"entries": role_entries, "visible": role_entries}


@app.put("/nav-visibility", dependencies=[Depends(require_permission("user.manage"))])
async def update_nav_visibility(
    req: NavVisibilityUpdateRequest,
    current: User = Depends(require_login),
):
    """批量覆盖导航可见性（user.manage 权限）。审计 before/after + 操作人。"""
    store = app.state.nav_visibility_store
    # 归一化：仅接受合法 role 与 entry_key，忽略非法 key
    valid_roles = {"admin", "pm", "researcher", "reviewer", "viewer", "data_engineer"}
    updates: dict[str, dict[str, bool]] = {}
    for role, entries in (req.matrix or {}).items():
        if role not in valid_roles:
            continue
        updates[role] = {k: v for k, v in (entries or {}).items() if k in app.state.nav_entries}
    if not updates:
        raise HTTPException(status_code=400, detail="没有有效的导航可见性覆盖项")

    before = {role: store.role_matrix(role) for role in updates}
    store.upsert_batch(updates, updated_by=current.username)
    after = {role: store.role_matrix(role) for role in updates}
    get_audit_logger().log(AuditEntry(
        event_type="human_edit", module="auth", action="update_nav_visibility",
        operator=current.username, user_id=current.user_id,
        resource_type="nav_visibility", resource_id=",".join(updates),
        before=before, after=after,
        tenant_id=current.tenant_id,
    ))
    # 返回全量矩阵供前端刷新（缓存失效信号：前端收到后重拉/重算）
    return {
        "ok": True,
        "before": before,
        "after": after,
        "matrix": {role: store.role_matrix(role) for role in sorted(updates)},
    }


@app.delete("/auth/users/{user_id}", dependencies=[Depends(require_permission("user.manage"))])
async def delete_user(user_id: str):
    """删除用户（user.manage 权限）。不允许删除默认 admin 账户以防锁死系统。"""
    store: UserStore = app.state.user_store
    default_admin = store.get_by_username("admin")
    if default_admin is not None and default_admin.user_id == user_id:
        raise HTTPException(status_code=400, detail="不允许删除默认管理员账户")
    if not store.delete(user_id):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user_id": user_id}


# --- 审计日志 ---

# A4：多条件分页查询（兼容旧参数 module/limit）
@app.get("/audit/logs", dependencies=[Depends(require_permission("audit.view"))])
async def list_audit_logs(
    module: str | None = None,
    action: str | None = None,
    operator: str | None = None,
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    page: int = 1,
    page_size: int = 20,
    limit: int | None = None,
):
    """多条件分页查询审计日志（需登录）。

    兼容旧客户端：仅传 module/limit 时退化为简单列表；传分页参数时返回
    ``{items, total, page, page_size}``。行级可见性受当前用户租户隔离。
    """
    logger = get_audit_logger()
    if limit is not None:
        return [e.model_dump() for e in logger.query(module=module, limit=limit)]
    return logger.query_paged(
        module=module, action=action, operator=operator, event_type=event_type,
        resource_type=resource_type, resource_id=resource_id,
        start_at=start_at, end_at=end_at, page=page, page_size=page_size,
    )


@app.post("/audit/archive", dependencies=[Depends(require_permission("audit.view"))])
async def archive_audit(before_at: str):
    """归档早于 before_at 的审计记录（仅当前租户）。"""
    logger = get_audit_logger()
    count = logger.archive(before_at)
    return {"archived": count}


# --- 租户管理（多租户隔离 A1）---

# --- 异常监控 ---

@app.get("/debug/committee", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def debug_committee():
    """临时调试端点：检查 Committee 模块状态。"""
    return {
        "coordinator_is_none": _committee_coordinator is None,
        "policy_is_none": _committee_policy is None,
        "repository_is_none": _committee_repository is None,
        "event_store_is_none": _committee_event_store is None,
    }

@app.get("/health/tasks", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def health_check_tasks():
    """扫描超时未完成的任务。"""
    from .ecml.ecml_engine import ECMLStateStore
    from .config import get_config

    config = get_config()
    try:
        store = ECMLStateStore(db_path=str(Path(__file__).resolve().parents[1] / "data" / "ecml_states.db"))
        runs = store.list_runs()
    except Exception as e:
        logger.warning("ECML state store health check failed: %s", e, exc_info=True)
        return {"status": "degraded", "issues": [{"error": "state_store_unavailable", "detail": str(e)}]}

    issues = []
    for run in runs:
        if not run.get("is_complete") and run.get("status") != "timeout":
            updated = run.get("updated_at", "")
            if updated:
                try:
                    from datetime import datetime, timezone, timedelta
                    updated_dt = updated if isinstance(updated, datetime) else datetime.fromisoformat(updated)
                    elapsed = (datetime.now(timezone.utc) - updated_dt).total_seconds()
                    if elapsed > 600:  # 超过 10 分钟
                        issues.append({
                            "run_id": run.get("run_id"),
                            "status": run.get("status", "unknown"),
                            "elapsed_seconds": elapsed,
                            "issue": "任务超时未完成",
                        })
                except Exception:
                    pass

    return {
        "status": "degraded" if issues else "ok",
        "total_runs": len(runs),
        "issues": issues,
    }


# --- SCP 异步任务归档（T-034 混合生命周期）---


@app.post("/system/tasks/archive", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def archive_scp_tasks():
    """手动触发 SCP 异步任务归档（admin）。

    决策 D-09 混合保留策略：
    - 活跃任务永久保留
    - completed/cancelled 超过 scp_task_completed_retention_days（默认 30）归档
    - failed/timeout 超过 scp_task_failed_retention_days（默认 90）归档

    归档为 INSERT + DELETE 原子操作（单事务），数据迁至
    integrations.scp_task_archive 表，保留完整字段 + archived_at。
    """
    from .integrations.scp_task_store import SCPTaskStore
    from .config import get_config

    config = get_config()
    store = SCPTaskStore()
    try:
        stats = await asyncio.to_thread(
            store.archive_old_tasks,
            completed_retention_days=config.scp_task_completed_retention_days,
            failed_retention_days=config.scp_task_failed_retention_days,
        )
    except Exception as e:
        logger.warning("SCP task archive failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"archive_failed: {e}")
    logger.info(
        "SCP task archive triggered: archived_completed=%d archived_failed=%d",
        stats.get("archived_completed", 0),
        stats.get("archived_failed", 0),
    )
    return {
        "ok": True,
        "retention_days": {
            "completed": config.scp_task_completed_retention_days,
            "failed": config.scp_task_failed_retention_days,
        },
        **stats,
    }


@app.get("/system/tasks/archived", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_archived_scp_tasks(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """查询已归档的 SCP 异步任务（admin，分页，按归档时间倒序）。"""
    from .integrations.scp_task_store import SCPTaskStore

    store = SCPTaskStore()
    try:
        records = await asyncio.to_thread(store.list_archived_tasks, limit, offset)
    except Exception as e:
        logger.warning("List archived SCP tasks failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"list_archived_failed: {e}")
    return {
        "items": [r.to_dict() for r in records],
        "limit": limit,
        "offset": offset,
    }


@app.post("/route", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def route_material(req: RouteRequest):
    from .router.router import MaterialInput
    mi = MaterialInput(
        name=req.name, smiles=req.smiles, psmiles=req.psmiles,
        cif_path=req.cif_path, formula=req.formula,
    )
    result = agent.route(mi)
    return result.model_dump()


@app.post("/discover", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover(req: DiscoverRequest):
    target_props = req.target_properties if req.target_properties else None
    state = await asyncio.to_thread(
        agent.ecml.run, req.target, req.target_property, req.max_iterations, req.run_id,
        target_props, req.parent_run_id, req.scenario_id, req.task_id, req.project_id,
    )
    summary = agent.ecml.get_summary(state)
    summary["run_id"] = state.run_id
    # P3-1：ECML 闭环运行写入统一研发事件流水
    _log_research_event(
        event_type="ecml_run",
        run_id=state.run_id,
        title=f"闭环迭代：{state.target or req.target or '未命名目标'}",
        summary=f"目标属性 {state.target_property}，迭代 {state.iteration} 轮，"
                f"候选 {len(state.candidates or [])} 个",
        status="success" if state.is_complete else "running",
        run_source=agent.ecml.state_store._infer_run_source(state.target or req.target),
        payload={
            "target": state.target,
            "target_property": state.target_property,
            "iteration": state.iteration,
            "is_complete": state.is_complete,
            "parent_run_id": req.parent_run_id or "",
            "scenario_id": state.scenario_id or req.scenario_id or "",
        },
    )
    return summary


def _log_research_event(event_type: str, run_id: str = "", title: str = "",
                        summary: str = "", status: str = "success",
                        run_source: str = "production", payload: dict | None = None):
    """P3-1：统一研发事件流水写入入口（静默容错，不阻断主流程）。"""
    if _research_event_stream is None:
        return
    try:
        _research_event_stream.log_event(
            event_type=event_type, run_id=run_id, title=title, summary=summary,
            status=status, run_source=run_source, payload=payload,
        )
    except Exception as e:
        logger.debug("Research event log failed: %s", e)


@app.get("/research-events")
async def list_research_events(event_type: str = "", run_id: str = "",
                               include_test: bool = False, limit: int = 50):
    """查询统一研发事件流水（P3-1）。

    首页看板"最近活动"、迭代历史、控制平面运行队列均消费本接口。
    默认排除 test 垃圾数据（与 /stats 口径一致）；include_test=true 供数据治理页使用。
    """
    if _research_event_stream is None:
        return {"events": [], "count": 0}
    events = _research_event_stream.list_events(
        event_type=event_type, run_id=run_id,
        run_source="" if include_test else "production",
        limit=limit,
    )
    return {"events": events, "count": len(events)}


@app.get("/research-events/stats")
async def research_event_stats():
    """研发事件按类型聚合计数（production 口径），供看板/治理页使用。"""
    if _research_event_stream is None:
        return {"by_type": {}, "test_total": 0}
    return _research_event_stream.stats()


def _serve_spa_if_browser(request: Request):
    """SPA 路由与 API 路径冲突时的兜底：非 API 请求（浏览器直接导航）返回 index.html。

    背景：后端注册了 @app.get("/ecml/runs") 等 GET 路由，与前端 SPA 路由
    /ecml/runs 冲突。前端 axios 请求走 /api/ecml/runs（被中间件重写为
    /ecml/runs 并标记 is_api_request=True），浏览器直接导航到 /ecml/runs
    时不带 /api 前缀、无 is_api_request 标记，此时应返回 SPA 页面。
    """
    if not request.scope.get("is_api_request") and _frontend_index.is_file():
        return FileResponse(str(_frontend_index))
    return None


@app.get("/ecml/runs")
async def list_ecml_runs(request: Request, limit: int = Query(default=20, ge=1, le=500),
                         project_id: str = Query(default="")):
    """列出最近的 ECML 运行记录（来自 SQLite 持久化）。

    project_id 非空时仅返回该项目的运行记录。
    """
    spa = _serve_spa_if_browser(request)
    if spa is not None:
        return spa
    return {"runs": agent.ecml.state_store.list_runs(limit, project_id=project_id)}


@app.get("/ecml/runs/{run_id}")
async def get_ecml_run(run_id: str):
    """恢复某个 ECML 运行的完整状态。

    异步执行模式下返回运行状态（running/completed/failed/timeout），
    以及完整 state、summary 与 error 信息。扁平摘要字段保留以兼容已有调用方。
    """
    run_status = _ecml_run_status.get(run_id)
    state = agent.ecml.state_store.load(run_id)
    if state is None and run_status is None:
        raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")

    if state is not None:
        summary = agent.ecml.get_summary(state)
        summary["run_id"] = state.run_id
        # 异步运行状态优先（覆盖 timeout/failed），否则回退到 state.status
        status_val = run_status["status"] if run_status else state.status
        error_val = run_status.get("error") if run_status else None
        return {
            **summary,
            "status": status_val,
            "state": state.model_dump(),
            "summary": summary,
            "error": error_val,
        }

    # state 尚未落盘（刚启动的 running 窗口）
    return {
        "run_id": run_id,
        "status": run_status["status"] if run_status else "running",
        "state": None,
        "summary": None,
        "error": run_status.get("error") if run_status else None,
        "is_complete": False,
    }


@app.delete("/ecml/runs/{run_id}", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def delete_ecml_run(run_id: str):
    """删除某个 ECML 运行记录。"""
    ok = agent.ecml.state_store.delete(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")
    # P3-1：联动清理研发事件流水中的关联事件，保持两个视图一致
    if _research_event_stream is not None:
        try:
            _research_event_stream.delete_by_run_id(run_id)
        except Exception as e:
            logger.debug("Research event cleanup failed: %s", e)
    return {"ok": True}


class ECMLBulkDeleteRequest(BaseModel):
    run_ids: list[str]


@app.post("/ecml/runs/bulk-delete", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def bulk_delete_ecml_runs(req: ECMLBulkDeleteRequest):
    """批量删除 ECML 运行记录（P0-4 测试垃圾数据清理），保留审计日志。"""
    if not req.run_ids:
        raise HTTPException(status_code=400, detail="run_ids 不能为空")
    if len(req.run_ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多删除 500 条记录")
    deleted = agent.ecml.state_store.bulk_delete(req.run_ids)
    # P3-1：联动清理研发事件流水，保证批量清理后各视图口径一致
    if _research_event_stream is not None:
        for rid in req.run_ids:
            try:
                _research_event_stream.delete_by_run_id(rid)
            except Exception as e:
                logger.debug("Research event cleanup failed for %s: %s", rid, e)
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="ecml",
            action="bulk_delete_runs",
            detail={"run_ids": req.run_ids, "deleted": deleted},
            confirmed=True,
        ))
    except Exception:
        logger.warning("bulk-delete 审计日志写入失败", exc_info=True)
    return {"ok": True, "deleted": deleted}


@app.get("/ecml/runs/{run_id}/next-round")
async def get_ecml_next_round(run_id: str):
    """获取下一轮候选建议。如果尚未生成，触发 generate_next_round() 并返回。"""
    state = agent.ecml.state_store.load(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")

    suggestions = state.next_round_suggestions
    if not suggestions:
        # generate_next_round 已改为同步方法，用 asyncio.to_thread 避免阻塞事件循环
        suggestions = await asyncio.to_thread(agent.ecml.generate_next_round, run_id)
        state.next_round_suggestions = suggestions
        agent.ecml.state_store.save(run_id, state.target, state.target_property, state)

    return suggestions


class ECMLRunRoundRequest(BaseModel):
    """启动一轮贝叶斯优化推荐（产出推荐后停在复核门，不自动下发）。

    模型/采集函数/探索强度等策略参数由课题负责人在策略面板配置；
    num_candidates 控制本轮推荐候选数量。
    """
    material_family: str = ""
    acquisition: str = "ei"  # ei | ucb | pi | ehvi
    explore: float = 0.5  # 0=纯利用, 1=纯探索
    model_family: str = ""  # gp | gbt | mlp，空则自动推荐
    budget: float | None = None  # 本轮预算硬约束
    include_cross_project: bool = False  # 是否纳入跨项目历史数据
    project_id: str = ""
    objectives: list[dict] = Field(default_factory=list)  # 多目标配置
    num_candidates: int = 10  # 本轮推荐候选数量


class ECMLConfirmRoundRequest(BaseModel):
    """课题负责人复核确认下发：为采纳候选创建实验任务并推进状态机。"""
    adopted: list = Field(default_factory=list)  # [{formula, candidate_id, name}] 或 ["formula"]


@app.get("/ecml/runs/{run_id}/pool-stats")
async def get_ecml_pool_stats(
    run_id: str,
    material_family: str = "",
    target_property: str = "",
):
    """训练池统计预览：按"材料体系+目标属性"维度聚合，供策略配置面板展示。"""
    try:
        return await asyncio.to_thread(
            agent.ecml.pool_stats,
            run_id,
            material_family or None,
            target_property or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/ecml/runs/{run_id}/rounds", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def start_ecml_round(run_id: str, req: ECMLRunRoundRequest):
    """启动一轮 BO 推荐，产出推荐后停在"待复核门"，不自动下发实验。"""
    try:
        return await asyncio.to_thread(
            agent.ecml.run_bayesian_round,
            run_id,
            family=req.material_family or None,
            acquisition=req.acquisition,
            explore=req.explore,
            model_family_override=req.model_family or None,
            budget=req.budget,
            include_cross_project=req.include_cross_project,
            project_id=req.project_id,
            objectives=req.objectives,
            num_candidates=req.num_candidates,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/ecml/runs/{run_id}/rounds")
async def list_ecml_rounds(run_id: str):
    """列出 run 下所有 Round 记录（不含完整快照，仅元信息）。"""
    try:
        return await asyncio.to_thread(agent.ecml.list_rounds, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/ecml/rounds/{round_id}")
async def get_ecml_round(round_id: str):
    """获取单个 Round 完整记录（含训练池快照、推荐、实测回填）。"""
    rnd = await asyncio.to_thread(agent.ecml.get_round, round_id)
    if rnd is None:
        raise HTTPException(status_code=404, detail=f"Round {round_id} 不存在")
    return rnd


@app.post("/ecml/rounds/{round_id}/confirm", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def confirm_ecml_round(round_id: str, req: ECMLConfirmRoundRequest):
    """课题负责人确认下发：为采纳候选创建实验任务，推进状态机。"""
    try:
        return await asyncio.to_thread(
            agent.ecml.confirm_round, round_id, req.adopted
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ECMLResumeDataRequest(BaseModel):
    """提交真实实验数据以唤醒处于 WAITING_FOR_DATA 的 ECML run。

    两种提交方式：
    - from_order_id：传实验任务单 ID，后端自动从 result_records 表读取该单的所有数据
                    （前端推荐用此方式，无需自己构造 experiment_results）
    - experiment_results：直接传数据列表，格式 [{formula, measured_values: {prop: val}, ...}]
    """
    from_order_id: str = ""
    experiment_results: list[dict] = Field(default_factory=list)
    target: str = ""
    target_property: str = ""


def _build_experiment_results_from_order(order_id: str) -> list[dict]:
    """从 experiment_result_records 表读取指定 order 的所有数据，
    按 sample_id 分组，转成 ECML resume_from_data 期望的 experiment_results 格式。

    返回格式：[{formula, measured_values: {prop: val}, order_id, candidate_id, sample_id}]
    跳过 qc_status 非 VALID/VALID_WITH_WARNING 的记录。
    """
    if not order_id:
        return []
    try:
        order = agent.experiment_controller._store.get_order(order_id)
    except Exception:
        return []
    if order is None:
        return []

    candidate_id = order.candidate_id or ""
    formula = ""
    if candidate_id:
        try:
            cand_store = getattr(app.state, "candidate_store", None)
            if cand_store is not None:
                candidate = cand_store.get(candidate_id)
                if candidate is not None:
                    formula = (candidate.data or {}).get("formula") or candidate.name or candidate.smiles
        except Exception as e:
            logger.debug("查询 candidate 失败 candidate_id=%s: %s", candidate_id, e)

    try:
        records = agent.experiment_controller._store.list_result_records(order_id=order_id)
    except Exception as e:
        logger.debug("查询 result_records 失败 order_id=%s: %s", order_id, e)
        return []

    grouped: dict[str, dict] = {}
    for r in records:
        if r.qc_status not in ("VALID", "VALID_WITH_WARNING"):
            continue
        if not r.sample_id or not r.property_name:
            continue
        try:
            val = float(r.value) if r.value is not None else None
        except (ValueError, TypeError):
            continue
        if val is None:
            continue
        slot = grouped.setdefault(r.sample_id, {
            "formula": formula,
            "measured_values": {},
            "order_id": order_id,
            "candidate_id": candidate_id,
            "sample_id": r.sample_id,
        })
        slot["measured_values"][r.property_name] = val

    return [v for v in grouped.values() if v["measured_values"]]


@app.post("/ecml/runs/{run_id}/data", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def resume_ecml_from_data(run_id: str, req: ECMLResumeDataRequest):
    """注入真实实验数据，唤醒 WAITING_FOR_DATA 状态的 ECML run 继续 Step7 反馈。

    场景：production 模式下 Step6 创建实验任务后停在 WAITING_FOR_DATA，
    用户在前端录入数据后通过此端点提交，触发反馈分析与下一轮建议生成。
    """
    # 优先用 from_order_id 自动构造（前端推荐路径）
    if req.from_order_id:
        experiment_results = _build_experiment_results_from_order(req.from_order_id)
        if not experiment_results:
            raise HTTPException(
                status_code=400,
                detail=f"order {req.from_order_id} 无可用实验数据（需 qc_status=VALID/VALID_WITH_WARNING）",
            )
    elif req.experiment_results:
        experiment_results = req.experiment_results
    else:
        raise HTTPException(status_code=400, detail="需提供 from_order_id 或 experiment_results")

    try:
        state = await asyncio.to_thread(
            agent.ecml.resume_from_data,
            run_id,
            experiment_results,
            req.target,
            req.target_property,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("resume_from_data failed for run %s: %s", run_id, e)
        raise HTTPException(status_code=500, detail=f"恢复失败: {e}")

    summary = agent.ecml.get_summary(state)
    summary["run_id"] = state.run_id
    summary["resume_triggered"] = True
    summary["is_complete"] = state.is_complete
    summary["recommendation"] = (
        state.feedback.get("recommendation", "") if state.feedback else ""
    )
    return summary


class ParseGoalRequest(BaseModel):
    """智能目标框解析请求（Q12：一句话目标 → 结构化研发上下文）。"""

    goal: str = ""
    constraints: dict | None = None


# 材料体系关键词推断表（智能目标框）：缩写/中文名 → 领域包体系名
_GOAL_SYSTEM_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("pa66", "尼龙66", "尼龙 66"), "PA66"),
    (("pa6", "尼龙6", "尼龙 6", "聚酰胺"), "PA6"),
    (("聚碳酸酯", "pc"), "PC"),
    (("abs", "丙烯腈丁二烯苯乙烯"), "ABS"),
    (("聚丙烯", "pp "), "PP"),
    (("pbt", "聚对苯二甲酸丁二醇酯"), "PBT"),
    (("pet", "聚对苯二甲酸乙二醇酯"), "PET"),
    (("pla", "聚乳酸"), "PLA"),
    (("pbat",), "PBAT"),
    (("pps", "聚苯硫醚"), "PPS"),
    (("pom", "聚甲醛"), "POM"),
    (("peek", "聚醚醚酮"), "PEEK"),
    (("pc/abs",), "PC/ABS"),
    (("玻纤", "玻璃纤维", "gf"), "玻纤增强"),
    (("碳纤", "碳纤维", "cf"), "碳纤增强"),
    (("阻燃",), "阻燃改性"),
    (("生物降解", "可降解"), "生物降解"),
    (("增韧", "增韧改性"), "增韧改性"),
]


def _infer_goal_system(goal: str) -> str:
    """从目标文本推断材料体系（Q12 智能目标框）。"""
    import re as _re
    t = (goal or "").lower()
    matched = []
    for kws, system in _GOAL_SYSTEM_KEYWORDS:
        for kw in kws:
            if _re.match(r"^[a-z0-9/]+$", kw):
                # 英文缩写：词边界匹配（\bpc\b 不误命中 spc/process）
                if _re.search(r"\b" + _re.escape(kw) + r"\b", t):
                    matched.append(system)
                    break
            elif kw in t:
                matched.append(system)
                break
    if not matched:
        return ""
    # 基材优先（第一个命中），增强/改性作为描述后缀
    return matched[0]


@app.post("/parse-goal", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def parse_goal(req: ParseGoalRequest):
    """智能目标框：一句话研发目标 → 结构化上下文（材料类型/体系/属性约束）。

    复用 hybrid.intent_interpreter 的 NL 解析（元素约束、属性比较、锂语境推断），
    叠加材料体系关键词推断。前端据此回填表单，实现"输入一句话就能跑"。
    """
    goal = (req.goal or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="目标描述不能为空")
    from .hybrid.intent_interpreter import IntentInterpreter

    interpreter = IntentInterpreter()
    intent = await interpreter.interpret(goal, req.constraints or {})
    material_scope = intent.get("material_scope")
    material_type = getattr(material_scope, "material_type", "") or ""
    # 目标属性 → 可回填的约束形态（对齐 ResearchWorkbench 的 target_properties）
    target_properties = []
    for tp in intent.get("target_properties") or []:
        entry = {
            "name": tp.get("property"),
            "direction": tp.get("direction", "maximize"),
            "min": tp.get("min"),
            "max": tp.get("max"),
        }
        if entry["name"]:
            target_properties.append(entry)
    return {
        "goal": goal,
        "material_scope": material_type,
        "material_system": _infer_goal_system(goal),
        "target_properties": target_properties,
        "require_elements": intent.get("require_elements") or [],
        "exclude_elements": intent.get("exclude_elements") or [],
        "execution_profile": intent.get("execution_profile"),
        "suggested_capabilities": intent.get("suggested_capabilities") or [],
    }


@app.post("/discover/crystal", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover_crystal(req: DiscoverRequest):
    # 多目标优化：target_properties 非空时启用加权评分
    target_props = req.target_properties if req.target_properties else None
    # P0-4：从用户目标抽取元素包含/排除约束 + 属性比较约束
    require_elements: list[str] | None = None
    exclude_elements: list[str] | None = None
    if req.target:
        from .hybrid.intent_interpreter import (
            _parse_exclude_elements, _parse_require_elements,
            _parse_target_properties, _infer_lithium_context,
        )
        try:
            exclude_elements = _parse_exclude_elements(req.target) or None
            require_elements = _parse_require_elements(req.target) or None
            require_elements = _infer_lithium_context(req.target, require_elements, exclude_elements) or None
            # 冲突解决：require 优先于 exclude
            if require_elements and exclude_elements:
                exclude_elements = [e for e in exclude_elements if e not in require_elements] or None
            parsed_target_props = _parse_target_properties(req.target)
            # 仅在调用方未显式传入 target_properties 时填充
            if not target_props and parsed_target_props:
                target_props = parsed_target_props
        except Exception as e:
            logger.warning("P0-4 NL 约束抽取失败（忽略）: %s", e)
    result = agent.discover_crystal(
        req.elements, req.target_property, req.num_candidates,
        target_properties=target_props,
        require_elements=require_elements,
        exclude_elements=exclude_elements,
    )
    # D3(P2-003)：临时性质预测溯源——为晶体候选补充 model_version/confidence/
    # input_snapshot/generated_at ai_meta，与 /discover/polymer 对齐，支持调用链反查
    input_snapshot_hash = _compute_input_snapshot({
        "elements": req.elements or [],
        "target_property": req.target_property,
        "num_candidates": req.num_candidates,
        "scenario_id": req.scenario_id,
        "target_properties": target_props or [],
    })
    from datetime import datetime as _dt, timezone
    for c in result.get("candidates", []) if isinstance(result, dict) else []:
        if not c.get("ai_meta"):
            c["ai_meta"] = {}
        c["ai_meta"]["input_snapshot_hash"] = input_snapshot_hash
        c["ai_meta"]["model_version"] = c.get("model_version") or "materials-project-v1"
        c["ai_meta"]["confidence"] = c.get("confidence") or 0.85
        c["ai_meta"]["generated_at"] = _dt.now(timezone.utc).isoformat()
    if isinstance(result, dict):
        result.setdefault("ai_meta", {})["input_snapshot_hash"] = input_snapshot_hash
        result.setdefault("ai_meta", {})["model_version"] = "materials-project-v1"
        result.setdefault("ai_meta", {})["generated_at"] = _dt.now(timezone.utc).isoformat()
    # 持久化候选材料，打通 Discovery → SampleManager 溯源链路
    _store_candidates(
        app.state.candidate_store, result, "crystal", req.scenario_id,
        project_id=req.project_id, task_id=req.task_id,
    )
    # P3-1：材料发现写入统一研发事件流水
    elements_desc = ",".join(req.elements) if req.elements else "全元素空间"
    _log_research_event(
        event_type="discovery",
        title=f"晶体材料发现：{elements_desc}",
        summary=f"目标属性 {req.target_property}，生成候选 {result.get('count', 0)} 个",
        payload={
            "material_kind": "crystal",
            "elements": req.elements,
            "target_property": req.target_property,
            "count": result.get("count", 0),
            "scenario_id": req.scenario_id,
            "require_elements": require_elements or [],
            "exclude_elements": exclude_elements or [],
            "degraded": result.get("degraded", False),
        },
    )
    return result


@app.post("/discover/polymer", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover_polymer(req: DiscoverRequest):
    target_props = req.target_properties if req.target_properties else None
    # v4.1：target/smiles 作为体系提示透传给生成器（触发工程塑料模式）
    material_system = req.target or req.smiles
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "target_properties": req.target_properties or [],
        "num_candidates": req.num_candidates,
        "scenario_id": req.scenario_id,
        "material_system": material_system,
    })
    # 聚合物生成涉及同步 LLM 调用，放在线程池中执行，避免阻塞事件循环导致前端请求被取消
    result = await asyncio.to_thread(
        agent.discover_polymer,
        target_properties=target_props,
        num_candidates=req.num_candidates,
        material_system=material_system,
    )
    # 补充 ai_meta（每个候选 + 顶层）
    from datetime import datetime as _dt, timezone
    candidates = result.get("candidates", []) if isinstance(result, dict) else []
    for c in candidates:
        if not c.get("ai_meta"):
            c["ai_meta"] = {}
        c["ai_meta"]["input_snapshot_hash"] = input_snapshot_hash
        c["ai_meta"]["model_version"] = "internlm-v1"
        c["ai_meta"]["generated_at"] = _dt.now(timezone.utc).isoformat()
    if isinstance(result, dict):
        result.setdefault("ai_meta", {})["input_snapshot_hash"] = input_snapshot_hash
        result.setdefault("ai_meta", {})["model_version"] = "internlm-v1"
        result.setdefault("ai_meta", {})["generated_at"] = _dt.now(timezone.utc).isoformat()
    _store_candidates(
        app.state.candidate_store, result, "polymer", req.scenario_id,
        project_id=req.project_id, task_id=req.task_id,
    )
    # P3-1：材料发现写入统一研发事件流水
    _log_research_event(
        event_type="discovery",
        title="聚合物材料发现",
        summary=f"生成候选 {result.get('count', 0)} 个",
        payload={
            "material_kind": "polymer",
            "target_properties": target_props,
            "count": result.get("count", 0),
            "scenario_id": req.scenario_id,
        },
    )
    return result


def _assemble_prediction(c_dict: dict) -> dict:
    """组装 prediction 顶层字段（模型版本/置信度/预测值/预测时间/输入快照/来源谱系）。

    评测修复 P1-004 / D3(P2-003)：使预测结果可追溯到具体模型与候选记录。
    供 discover 候选落盘与临时预测转正共用，保证两处预测字段结构一致。
    """
    if isinstance(c_dict.get("prediction"), dict) and c_dict.get("prediction"):
        return c_dict["prediction"]
    _ai_meta = c_dict.get("ai_meta") if isinstance(c_dict.get("ai_meta"), dict) else {}
    _predicted_value = (
        c_dict.get("predicted_value")
        or c_dict.get("predicted_properties")
        or c_dict.get("properties")
        or {}
    )
    return {
        "model_version": _ai_meta.get("model_version") or c_dict.get("model_version") or "",
        "confidence": _ai_meta.get("confidence", c_dict.get("confidence")),
        "predicted_value": _predicted_value,
        "predicted_at": _ai_meta.get("generated_at") or c_dict.get("created_at") or "",
        # D3(P2-003)：输入快照哈希 + 来源谱系，支持调用链反查
        "input_snapshot_hash": _ai_meta.get("input_snapshot_hash")
        or c_dict.get("input_snapshot_hash") or "",
        "provenance": c_dict.get("provenance") or _ai_meta.get("provenance") or [],
    }


def _store_candidates(
    store: CandidateStore,
    result,
    candidate_type: str,
    scenario_id: str = "",
    project_id: str = "",
    task_id: str = "",
):
    """将 discover 结果中的候选材料持久化到 candidate_store。"""
    candidates = result.get("candidates", []) if isinstance(result, dict) else []
    for c in candidates:
        try:
            # 兼容 dict 和 pydantic BaseModel
            if hasattr(c, "model_dump"):
                c_dict = c.model_dump()
            elif isinstance(c, dict):
                c_dict = c
            else:
                continue
            cid = c_dict.get("candidate_id", "")
            if not cid:
                continue
            # name 优先使用 LLM 返回的 name，其次 formula/smiles，避免把 formula 当 name
            name = c_dict.get("name") or c_dict.get("formula") or c_dict.get("smiles") or ""
            smiles = c_dict.get("smiles") or c_dict.get("psmiles") or ""
            # P0-001：将 scenario_id 写入候选数据，便于跨模块追溯
            c_dict["scenario_id"] = scenario_id
            # 业务链路：写入项目/任务 ID，便于按任务查询候选
            c_dict["project_id"] = project_id or c_dict.get("project_id", "")
            c_dict["task_id"] = task_id or c_dict.get("task_id", "")
            # T-029：AI 生成候选按置信度标记 data_quality（仅在未显式指定时）
            # confidence >= 0.8 → simulated（AI 预测值）；< 0.8 → estimated
            if not c_dict.get("data_quality"):
                _conf = c_dict.get("confidence")
                if isinstance(_conf, (int, float)) and not isinstance(_conf, bool):
                    c_dict["data_quality"] = "simulated" if _conf >= 0.8 else "estimated"
                else:
                    c_dict["data_quality"] = "estimated"
            # 评测修复 P1-004：组装 prediction 顶层字段（模型版本/置信度/预测值/预测时间），
            # 使预测结果可追溯到具体模型与候选记录
            c_dict["prediction"] = _assemble_prediction(c_dict)
            # T-020：前置去重检查——化学式 + 目标应用相同时跳过创建
            dedup_formula = c_dict.get("formula") or name
            dedup_target_app = c_dict.get("target_application", "")
            if dedup_formula:
                existing = store.find_by_content_hash(dedup_formula, dedup_target_app)
                if existing is not None:
                    logger.info(
                        "候选已存在，跳过创建 formula=%s target_application=%s candidate_id=%s",
                        dedup_formula, dedup_target_app, existing.candidate_id,
                    )
                    continue
            store.save(CandidateRecord(
                candidate_id=cid,
                candidate_type=candidate_type,
                name=name,
                smiles=smiles,
                source=c_dict.get("source", ""),
                scenario_id=scenario_id,
                task_id=task_id,
                project_id=project_id,
                multi_objective_score=c_dict.get("multi_objective_score", 0.0),
                prediction=c_dict.get("prediction") if isinstance(c_dict.get("prediction"), dict) else {},
                data=c_dict,
            ))
            # Task 14.2：候选生成后自动创建实验任务草稿（如果尚无关联订单）
            try:
                _ctrl = getattr(agent, "experiment_controller", None)
                if _ctrl is not None and hasattr(_ctrl, "ensure_draft_order_for_candidate"):
                    _ctrl.ensure_draft_order_for_candidate(
                        candidate_id=cid,
                        project_id=project_id or c_dict.get("project_id", ""),
                        scenario_id=scenario_id,
                    )
            except Exception:
                logger.debug("自动创建候选实验任务草稿失败 cid=%s", cid, exc_info=True)
        except Exception:
            logger.warning("Failed to persist candidate: %s", c, exc_info=True)


class AgentGenerateRequest(BaseModel):
    """Agent 创造性生成候选配方的请求。"""
    agent_id: str = ""
    # 任务上下文（来自项目任务）
    task_title: str = ""
    deliverable: str = ""
    target_properties: list[dict] = Field(default_factory=list)
    # 'pure_llm'（纯 LLM 创造）/ 'llm_plus_retrieval'（LLM 生成 + 检索增强）
    mode: str = "pure_llm"
    num_candidates: int = 10
    # 业务链路：关联项目/任务，便于候选材料落盘到任务下
    project_id: str = ""
    task_id: str = ""
    scenario_id: str = ""
    # 材料类型：crystal（晶体，需 formula） / polymer（聚合物，需 smiles）
    material_kind: str = "crystal"


def _build_agent_generate_prompt(
    agent_persona: str, task_title: str, deliverable: str,
    target_properties: list[dict], num_candidates: int,
    material_kind: str = "crystal",
) -> tuple[str, str]:
    """构造 Agent 创造性生成的 system / user prompt。

    根据 material_kind 区分提示词：
    - crystal：要求返回 formula / space_group / structure_type
    - polymer：要求返回 smiles / polymer_type
    """
    prop_desc = ""
    if target_properties:
        parts = []
        for p in target_properties:
            name = p.get("name") or p.get("property") or ""
            direction = p.get("direction") or "maximize"
            arrow = "↑" if direction == "maximize" else "↓"
            rng = ""
            if p.get("min") is not None:
                rng += f"≥{p['min']}"
            if p.get("max") is not None:
                rng += f"≤{p['max']}"
            parts.append(f"{name}{arrow}{rng}")
        prop_desc = "；".join(parts)

    if material_kind == "polymer":
        candidate_schema = (
            "    {\n"
            '      "smiles": "聚合物的 SMILES 表示，如 CC(=O)O（乙酸）或 c1ccccc1（苯）",\n'
            '      "name": "材料名称或简称，如 PA6",\n'
            '      "polymer_type": "聚合物类型，如 聚酰胺 / 聚碳酸酯 / ABS",\n'
            '      "rationale": "选择该配方的理由（1-2 句）",\n'
            '      "predicted_properties": {"tensile_strength": 数值, "flexural_modulus": 数值},\n'
            '      "confidence": 0.0-1.0 之间的数值，表示你对该候选达到目标属性的把握程度,\n'
            '      "key_assumptions": ["该预测成立依赖的关键假设"],\n'
            '      "evidence_sources": ["支撑该判断的证据来源"]\n'
            "    }\n"
        )
        formula_constraint = "- smiles 必须是合法的 SMILES 字符串\n"
        material_desc = "聚合物候选配方"
    else:
        candidate_schema = (
            "    {\n"
            '      "formula": "单一化合物的标准化学式，如 Li7La3Zr2O12（不得是混合物/配方名/体系描述）",\n'
            '      "name": "材料名称或简称，如 LLZO",\n'
            '      "structure_type": "结构类型，如 garnet / perovskite / NASICON",\n'
            '      "space_group": "空间群符号（可选，如 Ia-3d）",\n'
            '      "components": "可选，仅复合体系使用：[{\"formula\": \"Li6.5La3Zr1.5Ta0.5O12\", \"ratio\": \"20wt%\", \"role\": \"填料\"}], 单一组分留空数组 []",\n'
            '      "rationale": "选择该配方的理由（1-2 句）",\n'
            '      "predicted_properties": {"ionic_conductivity": 数值, "band_gap": 数值},\n'
            '      "confidence": 0.0-1.0 之间的数值，表示你对该候选达到目标属性的把握程度,\n'
            '      "key_assumptions": ["该预测成立依赖的关键假设，如 假设室温石榴石结构稳定"],\n'
            '      "evidence_sources": ["支撑该判断的证据来源，如 已知 LLZO 文献规律 / 元素化学常识"]\n'
            "    }\n"
        )
        formula_constraint = (
            "- formula 必须是单一化合物的标准化学式（如 Li7La3Zr2O12），不得是混合物名/配方描述/体系简称\n"
            "- 如果候选是复合体系（如 PEO/LiTFSI/LLZO），formula 填写主要活性组分的标准化学式，"
            "并在 components 数组中描述全部组分及其比例\n"
        )
        material_desc = "晶体候选配方"

    if material_kind == "polymer":
        persona_domain = (
            "你是高分子材料研发领域的首席材料学家。请基于任务目标，创造性地提出候选材料配方。\n\n"
            "要求：\n"
            "1. 结合高分子化学、工程塑料配方（基材/增强/阻燃/增韧）已知规律进行推理，先给出思考过程（为什么选这些基材/助剂/配比）\n"
            "2. 然后给出具体候选配方列表\n"
            "3. 候选配方应覆盖不同树脂体系与助剂组合，体现创造性，而非简单复述已知材料\n\n"
        )
    else:
        persona_domain = (
            "你是晶体材料研发领域的首席材料学家。请基于任务目标，创造性地提出候选晶体材料。\n\n"
            "要求：\n"
            "1. 结合元素化学、晶体结构、空间群与材料已知规律进行推理，先给出思考过程（为什么选这些元素/结构）\n"
            "2. 然后给出具体候选晶体列表\n"
            "3. 候选应覆盖不同结构族与元素组合，体现创造性，而非简单复述已知材料\n\n"
        )

    system_prompt = (
        agent_persona
        + persona_domain
        + "输出必须是严格 JSON，不要包含 markdown 代码块标记或任何额外说明，格式如下：\n"
        "{\n"
        '  "reasoning": "你的思考过程：分析任务目标、候选元素空间、结构选择权衡、预期性能",\n'
        '  "candidates": [\n'
        + candidate_schema +
        "  ]\n"
        "}\n"
        "约束：\n"
        "- 必须返回合法 JSON\n"
        "- candidates 数量在 3-N 之间，N 为请求数量\n"
        + formula_constraint +
        "- predicted_properties 中的 key 使用英文 snake_case\n"
        "- confidence 必须诚实评估：文献充分支撑的已知材料族 0.7-0.9；合理外推 0.4-0.7； speculative 新结构 <0.4"
    )
    user_prompt = (
        f"任务标题：{task_title or '高分子改性材料研发'}\n"
        f"交付物：{deliverable or '未指定'}\n"
        f"目标属性要求：{prop_desc or '未指定'}\n"
        f"请生成 {num_candidates} 个{material_desc}"
    )
    return system_prompt, user_prompt


def _structured_evidence(val) -> list[dict]:
    """将 evidence_sources 规范化为结构化对象数组。

    每项结构：{type, id, title, url}，type 取值：
    literature / experiment / kg_node / database / tool_output / unknown。

    向后兼容：纯字符串转为 {type: "unknown", id: "", title: text, url: ""}；
    字典项按字段规范化补齐缺失键。
    """
    if not isinstance(val, (list, tuple)):
        return []
    result: list[dict] = []
    for x in val:
        if isinstance(x, dict):
            t = str(x.get("type") or "").strip() or "unknown"
            result.append({
                "type": t,
                "id": str(x.get("id") or "").strip(),
                "title": str(x.get("title") or "").strip(),
                "url": str(x.get("url") or "").strip(),
            })
        else:
            text = str(x).strip()
            if text:
                result.append({"type": "unknown", "id": "", "title": text, "url": ""})
    return result


def _parse_agent_candidates(content: str, material_kind: str = "crystal") -> tuple[str, list[dict]]:
    """解析 LLM 返回的 JSON，提取 reasoning 与 candidates。

    根据 material_kind 校验必填字段：
    - crystal：必须有 formula
    - polymer：必须有 smiles
    """
    import json as _json
    # 去除可能的 markdown 代码块标记
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 去首尾 ``` 行
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        data = _json.loads(text)
    except Exception:
        # 兜底：尝试从文本中提取第一个 JSON 对象
        import re as _re
        m = _re.search(r"\{[\s\S]*\}", text)
        if not m:
            return "", []
        try:
            data = _json.loads(m.group(0))
        except Exception:
            return "", []
    reasoning = data.get("reasoning") or ""
    raw_candidates = data.get("candidates") or []
    candidates: list[dict] = []
    for c in raw_candidates:
        if not isinstance(c, dict):
            continue
        formula = (c.get("formula") or "").strip()
        smiles = (c.get("smiles") or "").strip()
        components = c.get("components") or []
        # 规范化 components：仅接受 list，逐元素校验为 dict
        if not isinstance(components, list):
            components = []
        else:
            components = [x for x in components if isinstance(x, dict)]
        # 根据 material_kind 校验必填字段
        if material_kind == "polymer":
            if not smiles:
                continue
        else:
            # crystal：允许 formula 为空但 components 非空（复合体系）
            if not formula and not components:
                continue
        # P1-2：解析 AI 可信度元数据（置信度/关键假设/证据来源）
        try:
            confidence = float(c.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        def _str_list(val) -> list[str]:
            """仅接受 list/tuple，逐元素转字符串；其他类型（含字符串）返回 []。"""
            if not isinstance(val, (list, tuple)):
                return []
            return [s for s in (str(x).strip() for x in val) if s]

        key_assumptions = _str_list(c.get("key_assumptions"))
        # T-030：evidence_sources 升级为结构化对象数组（含 type/id/title/url）
        evidence_sources = _structured_evidence(c.get("evidence_sources"))
        candidates.append({
            "candidate_id": f"CAND-{uuid.uuid4().hex[:8].upper()}",
            "formula": formula,
            "smiles": smiles,
            "name": c.get("name") or "",
            "structure_type": c.get("structure_type") or "",
            "space_group": c.get("space_group") or "",
            "polymer_type": c.get("polymer_type") or "",
            "components": components,
            "rationale": c.get("rationale") or "",
            "predicted_properties": c.get("predicted_properties") or {},
            "confidence": round(confidence, 3),
            "key_assumptions": key_assumptions,
            "evidence_sources": evidence_sources,
            "source": "agent_creative",
        })
    return reasoning, candidates


@app.post("/discover/agent-generate", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover_agent_generate(req: AgentGenerateRequest):
    """调用 Agent（默认首席材料学家）创造性生成候选配方。

    与 /discover/crystal 的区别：
    - /discover/crystal：从 MP/GNoME 数据库检索已有材料
    - /discover/agent-generate：让 LLM 扮演 Agent，创造性地提出候选配方

    mode:
    - pure_llm：完全由 LLM 生成
    - llm_plus_retrieval：LLM 生成后，用公式去 MP/GNoME 检索相似真实材料补充属性
    """

    # 解析 Agent（默认首席材料学家）
    agent_id = req.agent_id or "builtin_material_discovery"
    _require_agent_team()
    agent_def = _registry.get_agent(agent_id)
    if agent_def is None:
        raise HTTPException(status_code=404, detail=f"Agent 不存在：{agent_id}")

    # 拼装人设
    persona_parts: list[str] = [f"你的角色是「{agent_def.name}」。"]
    if agent_def.description:
        persona_parts.append(f"角色职责：{agent_def.description}")
    if agent_def.expertise:
        persona_parts.append("专长领域：" + "、".join(agent_def.expertise))
    if agent_def.capabilities:
        persona_parts.append("具备能力：" + "、".join(agent_def.capabilities))
    agent_persona = "\n".join(persona_parts) + "\n\n"

    # 模型解析：优先 Agent 显式 llm_model；空则按 provider 路由到 InternLM / LLM 配置默认。
    # 兼容旧数据（llm_model 为空但 provider=internlm 或 internlm 已启用）。
    cfg = get_config()
    agent_model = agent_def.llm_model
    if not agent_model:
        if (agent_def.provider or "").lower() == "internlm":
            agent_model = cfg.internlm.model or ""
        else:
            agent_model = cfg.llm.model or ""

    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "agent_id": agent_id,
        "agent_model": agent_model,
        "task_title": req.task_title,
        "deliverable": req.deliverable,
        "target_properties": req.target_properties or [],
        "num_candidates": req.num_candidates,
        "mode": req.mode,
    })

    system_prompt, user_prompt = _build_agent_generate_prompt(
        agent_persona, req.task_title, req.deliverable,
        req.target_properties, req.num_candidates,
        material_kind=req.material_kind,
    )

    # 评测修复 BEMCL-AI-P2-003：通过统一 LLMProvider 调用 LLM，走审计治理链
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content = await _call_llm_provider(
            provider=agent_def.provider or "",
            llm_model=agent_def.llm_model,
            messages=messages,
            cfg=cfg,
            max_tokens=8192,
        )
    except Exception as e:
        logger.warning("Agent 创造性生成 LLM 调用失败: %s", e)
        raise HTTPException(status_code=502, detail=f"Agent 生成失败：{e}") from e

    reasoning, candidates = _parse_agent_candidates(content, material_kind=req.material_kind)
    if not candidates:
        raise HTTPException(status_code=502, detail="Agent 未能生成有效候选，请重试或调整任务描述")

    # 模式 2：LLM + 检索增强——用 LLM 给出的 formula 去 MP 检索真实材料补充属性
    if req.mode == "llm_plus_retrieval":
        try:
            for c in candidates:
                # 用 formula 检索 MP，补充 band_gap / formation_energy / energy_above_hull
                mp_results = agent.crystal_generator.search_materials_project(
                    formula=c["formula"], num_results=1,
                )
                if mp_results:
                    mp = mp_results[0]
                    c["band_gap"] = mp.band_gap
                    c["formation_energy"] = mp.formation_energy
                    c["energy_above_hull"] = mp.energy_above_hull
                    c["material_id"] = mp.material_id
                    c["retrieval_verified"] = True
                    # P1-2：检索命中真实材料，提升置信度并补充证据来源
                    c["confidence"] = round(min(0.95, c.get("confidence", 0.5) * 1.15), 3)
                    # T-030：MP 检索命中构建为结构化 database 引用
                    mp_evidence = {
                        "type": "database",
                        "id": mp.material_id,
                        "title": f"Materials Project: {c['formula']}",
                        "url": f"https://nextgen.materialsproject.org/materials/{mp.material_id}",
                    }
                    ev_list = c.setdefault("evidence_sources", [])
                    if not any(
                        e.get("type") == "database" and e.get("id") == mp.material_id
                        for e in ev_list
                    ):
                        ev_list.append(mp_evidence)
                else:
                    c["retrieval_verified"] = False
                    # P1-2：检索未命中，降低置信度
                    c["confidence"] = round(c.get("confidence", 0.5) * 0.85, 3)
        except Exception as e:
            logger.warning("检索增强失败（忽略，保留纯 LLM 结果）: %s", e)

    # P1-2：人工复核标记——低置信度或检索模式下未经验证的候选需人工复核
    for c in candidates:
        c.setdefault("confidence", 0.5)
        c.setdefault("key_assumptions", [])
        c.setdefault("evidence_sources", [])
        c["human_review_required"] = bool(
            c["confidence"] < 0.6
            or (req.mode == "llm_plus_retrieval" and c.get("retrieval_verified") is False)
        )

    # 把 predicted_properties 中的数值回填到顶层字段（便于多目标评分与展示）
    # v4.1：高分子工程性能（_SCORE_PROPS）同步回填，否则 agent-generate 路径聚合物评分恒 0
    for c in candidates:
        pp = c.get("predicted_properties") or {}
        for k in ("ionic_conductivity", "band_gap", "formation_energy",
                  "tensile_strength", "flexural_modulus", "impact_strength",
                  "heat_deflection_temp", "melt_flow_index", "elongation_at_break",
                  "thermal_stability", "crystallinity"):
            if k in pp and c.get(k) is None:
                try:
                    c[k] = float(pp[k])
                except (TypeError, ValueError):
                    pass

    # 放行门禁：human_review_required 的候选自动创建 Release Card 进入审批队列
    for c in candidates:
        if c.get("human_review_required"):
            c["release_card_required"] = True
            reason = "低置信度或检索未验证，需通过放行卡审批后才能用于实验"
            c["release_card_reason"] = reason
            card_id = _auto_create_release_card_for_candidate(
                c, project_id=req.project_id, reason=reason
            )
            if card_id:
                c["release_card_id"] = card_id

    # 补充 ai_meta（每个候选 + 顶层）
    from datetime import datetime as _dt, timezone
    for c in candidates:
        if not c.get("ai_meta"):
            c["ai_meta"] = {}
        c["ai_meta"]["input_snapshot_hash"] = input_snapshot_hash
        c["ai_meta"]["model_version"] = agent_model
        c["ai_meta"]["agent_id"] = agent_def.id
        c["ai_meta"]["generated_at"] = _dt.now(timezone.utc).isoformat()

    result = {
        "candidates": candidates,
        "count": len(candidates),
        "reasoning": reasoning,
        "agent": {
            "id": agent_def.id,
            "name": agent_def.name,
            "avatar": agent_def.avatar,
            "role": agent_def.role.value if hasattr(agent_def.role, "value") else str(agent_def.role),
        },
        "mode": req.mode,
        # P1-2：顶层 AI 元信息（模型版本 / 生成策略 / 复核统计 / 输入快照哈希）
        "ai_meta": {
            "model": agent_model,
            "agent_id": agent_def.id,
            "agent_name": agent_def.name,
            "mode": req.mode,
            "human_review_count": sum(1 for c in candidates if c.get("human_review_required")),
            "input_snapshot_hash": input_snapshot_hash,
        },
    }

    # 持久化候选，携带项目/任务/场景链路信息，便于按任务查询与下游追溯
    _store_candidates(
        app.state.candidate_store, result, req.material_kind,
        scenario_id=req.scenario_id,
        project_id=req.project_id,
        task_id=req.task_id,
    )
    # 写研发事件流水
    _log_research_event(
        event_type="discovery",
        title=f"Agent 创造性生成：{agent_def.name}",
        summary=f"模式 {req.mode}，生成候选 {len(candidates)} 个",
        payload={
            "material_kind": req.material_kind,
            "agent_id": agent_def.id,
            "agent_name": agent_def.name,
            "mode": req.mode,
            "count": len(candidates),
        },
    )
    return result


# ── Agent 创造性生成：异步模式 + 进度查询 ──────────────────────
# 内存级任务状态跟踪（LRU，最多 200 条）
from collections import OrderedDict as _ODict_for_agent_gen
_agent_gen_tasks: _ODict_for_agent_gen = _ODict_for_agent_gen()


def _set_agent_gen_status(task_id: str, status: str, progress: int = 0,
                          step_label: str = "", result: dict | None = None,
                          error: str = ""):
    from datetime import datetime as _dt, timezone as _tz
    _agent_gen_tasks[task_id] = {
        "task_id": task_id,
        "status": status,  # pending / running / completed / failed
        "progress": progress,  # 0-100
        "step_label": step_label,
        "result": result,
        "error": error,
        "updated_at": _dt.now(_tz.utc).isoformat(),
    }
    _agent_gen_tasks.move_to_end(task_id)
    # 限制内存
    while len(_agent_gen_tasks) > 200:
        _agent_gen_tasks.popitem(last=False)
    # 同步到全局后台任务注册表（供右下角 TaskNotifier 轮询展示/跳转）；
    # 端点已用业务标题预登记时不会覆盖名称。
    from .tasks import async_tasks as _async_tasks
    _async_tasks.register_with_id(
        task_id,
        name=f"Agent 生成候选材料（{task_id}）",
        type="agent",
        detail="正在启动…",
    )
    _async_tasks.update(
        task_id,
        status="running" if status in ("running", "pending") else status,
        progress=progress,
        detail=step_label or (f"失败：{error[:120]}" if error else ""),
    )


@app.post("/discover/agent-generate/async", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover_agent_generate_async(req: AgentGenerateRequest):
    """异步启动 Agent 创造性生成，立即返回 task_id 供前端轮询进度。"""
    import uuid as _uuid
    task_id = f"aggen-{_uuid.uuid4().hex[:12]}"
    # 先以业务标题登记全局后台任务（右下角 TaskNotifier 可见），状态由 _set_agent_gen_status 同步
    from .tasks import async_tasks as _async_tasks
    _async_tasks.register_with_id(
        task_id,
        name=f"Agent 生成候选材料（{req.task_title or '未命名任务'}）",
        type="agent",
        detail="正在初始化…",
    )
    _set_agent_gen_status(task_id, "running", progress=10, step_label="正在初始化 Agent…")

    async def _bg_run():
        try:
            cfg = get_config()
            _set_agent_gen_status(task_id, "running", progress=20, step_label="正在构造提示词…")

            agent_id = req.agent_id or "builtin_material_discovery"
            _require_agent_team()
            agent_def = _registry.get_agent(agent_id)
            if agent_def is None:
                raise ValueError(f"Agent 不存在：{agent_id}")

            agent_model = agent_def.llm_model
            if not agent_model:
                if (agent_def.provider or "").lower() == "internlm":
                    agent_model = cfg.internlm.model or ""
                else:
                    agent_model = cfg.llm.model or ""

            persona_parts: list[str] = [f"你的角色是「{agent_def.name}」。"]
            if agent_def.description:
                persona_parts.append(f"角色职责：{agent_def.description}")
            if agent_def.expertise:
                persona_parts.append("专长领域：" + "、".join(agent_def.expertise))
            if agent_def.capabilities:
                persona_parts.append("具备能力：" + "、".join(agent_def.capabilities))
            agent_persona = "\n".join(persona_parts) + "\n\n"

            system_prompt, user_prompt = _build_agent_generate_prompt(
                agent_persona, req.task_title, req.deliverable,
                req.target_properties, req.num_candidates,
                material_kind=req.material_kind,
            )

            _set_agent_gen_status(task_id, "running", progress=40, step_label="Agent 正在创造性地生成候选配方…")

            # 评测修复 BEMCL-AI-P2-003：通过统一 LLMProvider 调用 LLM，走审计治理链
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            content = await _call_llm_provider(
                provider=agent_def.provider or "",
                llm_model=agent_def.llm_model,
                messages=messages,
                cfg=cfg,
                max_tokens=8192,
            )

            _set_agent_gen_status(task_id, "running", progress=70, step_label="正在解析候选材料…")
            reasoning, candidates = _parse_agent_candidates(content, material_kind=req.material_kind)
            if not candidates:
                raise ValueError("Agent 未能生成有效候选")

            # 检索增强（同同步逻辑）
            if req.mode == "llm_plus_retrieval":
                _set_agent_gen_status(task_id, "running", progress=80, step_label="正在检索 Materials Project…")
                try:
                    for c in candidates:
                        mp_results = agent.crystal_generator.search_materials_project(
                            formula=c["formula"], num_results=1,
                        )
                        if mp_results:
                            mp = mp_results[0]
                            c["band_gap"] = mp.band_gap
                            c["formation_energy"] = mp.formation_energy
                            c["energy_above_hull"] = mp.energy_above_hull
                            c["material_id"] = mp.material_id
                            c["retrieval_verified"] = True
                            c["confidence"] = round(min(0.95, c.get("confidence", 0.5) * 1.15), 3)
                        else:
                            c["retrieval_verified"] = False
                            c["confidence"] = round(c.get("confidence", 0.5) * 0.85, 3)
                except Exception as e:
                    logger.warning("异步生成检索增强失败: %s", e)

            # 人工复核标记
            for c in candidates:
                c.setdefault("confidence", 0.5)
                c.setdefault("key_assumptions", [])
                c.setdefault("evidence_sources", [])
                c["human_review_required"] = bool(
                    c["confidence"] < 0.6
                    or (req.mode == "llm_plus_retrieval" and c.get("retrieval_verified") is False)
                )

            # predicted_properties 回填
            for c in candidates:
                pp = c.get("predicted_properties") or {}
                if "ionic_conductivity" in pp:
                    try:
                        c["ionic_conductivity_estimate"] = float(pp["ionic_conductivity"])
                    except (TypeError, ValueError):
                        pass
                if "band_gap" in pp and "band_gap" not in c:
                    try:
                        c["band_gap"] = float(pp["band_gap"])
                    except (TypeError, ValueError):
                        pass

            # 放行门禁
            for c in candidates:
                if c.get("human_review_required"):
                    c["release_card_required"] = True
                    reason = "低置信度或检索未验证，需通过放行卡审批后才能用于实验"
                    c["release_card_reason"] = reason
                    card_id = _auto_create_release_card_for_candidate(c, project_id=req.project_id, reason=reason)
                    if card_id:
                        c["release_card_id"] = card_id

            # AI 元信息
            from datetime import datetime as _dt, timezone
            input_snapshot_hash = _compute_input_snapshot({
                "agent_id": agent_id, "agent_model": agent_model,
                "task_title": req.task_title, "deliverable": req.deliverable,
                "target_properties": req.target_properties or [],
                "num_candidates": req.num_candidates, "mode": req.mode,
            })
            for c in candidates:
                if not c.get("ai_meta"):
                    c["ai_meta"] = {}
                c["ai_meta"]["input_snapshot_hash"] = input_snapshot_hash
                c["ai_meta"]["model_version"] = agent_model
                c["ai_meta"]["agent_id"] = agent_def.id
                c["ai_meta"]["generated_at"] = _dt.now(timezone.utc).isoformat()

            result = {
                "candidates": candidates,
                "count": len(candidates),
                "reasoning": reasoning,
                "agent": {
                    "id": agent_def.id,
                    "name": agent_def.name,
                    "avatar": agent_def.avatar,
                    "role": agent_def.role.value if hasattr(agent_def.role, "value") else str(agent_def.role),
                },
                "mode": req.mode,
                "ai_meta": {
                    "model": agent_model,
                    "agent_id": agent_def.id,
                    "agent_name": agent_def.name,
                    "mode": req.mode,
                    "human_review_count": sum(1 for c in candidates if c.get("human_review_required")),
                    "input_snapshot_hash": input_snapshot_hash,
                },
            }

            # 持久化
            _set_agent_gen_status(task_id, "running", progress=90, step_label="正在保存候选材料…")
            _store_candidates(
                app.state.candidate_store, result, req.material_kind,
                scenario_id=req.scenario_id, project_id=req.project_id, task_id=req.task_id,
            )
            _log_research_event(
                event_type="discovery",
                title=f"Agent 创造性生成（异步）：{agent_def.name}",
                summary=f"模式 {req.mode}，生成候选 {len(candidates)} 个",
                payload={"material_kind": req.material_kind, "agent_id": agent_def.id, "mode": req.mode, "count": len(candidates)},
            )

            _set_agent_gen_status(task_id, "completed", progress=100, step_label="生成完成", result=result)
        except Exception as e:
            logger.error("异步 Agent 生成失败 task=%s: %s", task_id, e, exc_info=True)
            _set_agent_gen_status(task_id, "failed", progress=0, step_label="生成失败", error=str(e))

    # 后台运行（不阻塞响应）
    # 评测修复 P2-4：统一使用 _spawn_background 持有任务强引用，避免 ensure_future 任务被 GC 回收
    _spawn_background(_bg_run())

    return {"task_id": task_id, "status": "running", "message": "Agent 生成已启动，请轮询进度"}


@app.get("/discover/agent-generate/{task_id}/status")
async def discover_agent_generate_status(task_id: str):
    """查询异步 Agent 生成任务进度。"""
    info = _agent_gen_tasks.get(task_id)
    if not info:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return info


def _validate_formula_local(formula: str) -> bool:
    """本地 pymatgen 化学式校验。"""
    if not formula:
        return False
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return comp.num_atoms > 0 and all(e.Z <= 118 for e in comp.elements)
    except Exception:
        return False


def _compute_input_snapshot(params: dict) -> str:
    """计算 AI 输入参数的哈希快照。"""
    import hashlib
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _is_demo_id(record_id: str | None) -> bool:
    """是否演示数据（SEED_ 前缀，由 seed_ecml_demo.py 写入）。"""
    return bool(record_id and str(record_id).lstrip().upper().startswith("SEED_"))


def _tag_demo(record: dict) -> dict:
    """为单条记录打上 is_demo 标记（就地返回），供前端显示"演示"徽标。"""
    ident = record.get("sample_id") or record.get("candidate_id") \
        or record.get("order_id") or record.get("material_id") \
        or record.get("result_id") or record.get("id") or ""
    record["is_demo"] = _is_demo_id(ident)
    return record


def _filter_demo(records: list[dict], include_demo: bool = False) -> list[dict]:
    """D2(P2-002)：默认过滤 SEED_ 演示数据，并打 is_demo 标记。

    统计口径同步排除演示数据：include_demo=False 时不返回演示记录。
    """
    out = []
    for r in records:
        _tag_demo(r)
        if include_demo or not r.get("is_demo"):
            out.append(r)
    return out


def _find_release_card_for_candidate(candidate_id: str) -> dict | None:
    """按候选查找放行卡（任一状态），用于放行门禁防死锁。"""
    try:
        store = app.state.release_card_store
        if store is None:
            return None
        cards = store.list(limit=200)
        items = cards if isinstance(cards, list) else (cards.get("items") or [])
        for c in items:
            cid = getattr(c, "candidate_id", None) if not isinstance(c, dict) else c.get("candidate_id")
            if cid == candidate_id:
                return c if isinstance(c, dict) else c.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        pass
    return None


def _auto_create_release_card_for_candidate(
    candidate: dict,
    project_id: str | None = None,
    reason: str = "化学式待人工审核，需通过放行卡审批后才能用于实验",
) -> str | None:
    """对 human_review_required 的候选自动创建 Release Card，状态 pending_review。

    返回创建的 card_id；若创建失败返回 None，不阻塞主流程。
    """
    try:
        import uuid
        from datetime import datetime, timezone
        from .release_card.models import ReleaseCard

        store = app.state.release_card_store
        card_id = f"rc-{uuid.uuid4().hex[:8]}"
        candidate_id = candidate.get("candidate_id") or candidate.get("id")
        candidate_name = candidate.get("name") or candidate.get("formula") or candidate.get("smiles") or "候选材料"
        now = datetime.now(timezone.utc)

        card = ReleaseCard(
            card_id=card_id,
            case_id=None,
            project_id=project_id,
            candidate_id=candidate_id,
            title=f"{candidate_name} - 化学式人工审核",
            recommendation="human_review",
            status="pending_review",
            target_window={},
            evidence_summary={},
            uncertainty={
                "data_gaps": ["化学式未通过 SCP/本地校验"],
                "key_assumptions": [reason],
            },
            suggested_experiments=[],
            stop_conditions=["放行卡审批通过后方可用于实验任务"],
            human_responsibility={
                "reviewer": None,
                "review_opinion": None,
                "final_decision": None,
                "decided_at": None,
            },
            provenance={
                "source": "auto_created_from_candidate",
                "trigger": "human_review_required",
                "ai_meta": candidate.get("ai_meta", {}),
            },
            created_at=now,
            updated_at=now,
        )
        store.create(card)
        return card_id
    except Exception as e:
        logger.warning("自动创建 Release Card 失败: %s", e)
        return None


# ── 需求7：批量预测 + 三点状态指示 ──────────────────────────────

class BatchPredictRequest(BaseModel):
    """批量预测候选材料属性请求（需求7）。

    对一组候选材料自动执行性质预测，可选执行合成可行性检查，
    返回每个候选的三点状态（预测/合成/验证）。
    """
    candidates: list[dict] = Field(default_factory=list)
    material_kind: str = "crystal"  # crystal / polymer
    target_properties: list[dict] = Field(default_factory=list)
    agent_id: str | None = None
    model_type: str | None = None
    # 三点状态：是否同时执行合成检查（DFT 验证默认关闭，较慢）
    run_synthesis_check: bool = True


def _predict_single_candidate(
    candidate: dict,
    material_kind: str,
    target_properties: list[dict],
    model_type: str | None,
) -> dict:
    """对单个候选执行性质预测（同步，CPU 密集，由 to_thread 调用）。

    返回预测状态与结果。预测失败不抛异常，返回 failed 状态。
    """
    a = app.state.agent
    predictor = a.crystal_predictor if material_kind == "crystal" else a.polymer_predictor

    # 临时切换模型类型
    overridden = False
    original_model_type = None
    if model_type:
        supported = getattr(predictor, "SUPPORTED_MODELS", None) or []
        if supported and model_type in supported:
            original_model_type = predictor.model_type
            predictor.model_type = model_type
            overridden = True

    predictions = {}
    targets_met = 0
    total_targets = 0
    try:
        # 决定预测的属性列表：优先用 target_properties，否则用预测器默认属性
        if target_properties:
            prop_names = [p.get("name", "") for p in target_properties if p.get("name")]
        else:
            prop_names = getattr(predictor, "PREDICTABLE_PROPERTIES", [])[:3]

        for prop_name in prop_names:
            if not prop_name:
                continue
            total_targets += 1
            try:
                if material_kind == "crystal":
                    features = {"formula": candidate.get("formula", ""),
                                "smiles": candidate.get("smiles", "")}
                else:
                    features = {"smiles": candidate.get("smiles") or candidate.get("psmiles", ""),
                                "psmiles": candidate.get("psmiles", ""),
                                "formula": candidate.get("formula", "")}
                result = predictor.predict(features, prop_name)
                predicted_value = float(result.value)

                # 达标判断（0 是合法目标值，不能用 or 链短路）
                target_def = next((p for p in target_properties if p.get("name") == prop_name), None)
                met = True
                if target_def:
                    direction = target_def.get("direction", "maximize")
                    target_value = target_def.get("target_value")
                    if target_value is None:
                        target_value = target_def.get("max")
                    if target_value is None:
                        target_value = target_def.get("min")
                    if target_value is not None:
                        try:
                            tv = float(target_value)
                            if direction == "minimize":
                                met = predicted_value <= tv
                            else:
                                met = predicted_value >= tv
                        except (TypeError, ValueError):
                            pass

                predictions[prop_name] = {
                    "value": predicted_value,
                    "unit": getattr(result, "unit", ""),
                    "confidence": float(getattr(result, "confidence", 0.5)),
                    "model": getattr(result, "model", ""),
                    "met": met,
                }
                if met:
                    targets_met += 1
            except Exception as e:
                predictions[prop_name] = {"error": str(e), "met": False}

        return {
            "status": "done",
            "predictions": predictions,
            "targets_met": targets_met,
            "total_targets": total_targets,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e), "predictions": predictions,
                "targets_met": 0, "total_targets": total_targets}
    finally:
        if overridden:
            predictor.model_type = original_model_type


@app.post("/discover/batch-predict", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def batch_predict_candidates(req: BatchPredictRequest):
    """批量预测候选材料属性，返回三点状态（预测/合成/可制造性）。

    用于候选列表的三点状态指示（需求7）：
    - 属性预测：对每个候选执行性质预测
    - 合成可行性：检查合成可行性评分（可选）
    - 可制造性：调用 IndustrialFeasibilityScreening 评估工业可行性
    """
    if not req.candidates:
        return {"results": [], "count": 0}

    results = []
    for c in req.candidates:
        candidate_key = c.get("candidate_id") or c.get("id") or c.get("formula") or c.get("smiles") or ""

        # 1. 属性预测（CPU 密集，用 to_thread 避免阻塞事件循环）
        pred_result = await asyncio.to_thread(
            _predict_single_candidate, c, req.material_kind,
            req.target_properties, req.model_type,
        )

        # 把预测值回填到候选顶层字段（便于列表展示，v4.1 支持高分子属性通用回填）
        predictions = pred_result.get("predictions", {})
        for prop_name, pred in predictions.items():
            if "error" in pred:
                continue
            val = pred.get("value")
            if val is None:
                continue
            if prop_name == "band_gap" and c.get("band_gap") is None:
                c["band_gap"] = val
            elif prop_name == "formation_energy" and c.get("formation_energy") is None:
                c["formation_energy"] = val
            elif prop_name == "ionic_conductivity" and c.get("ionic_conductivity_estimate") is None:
                c["ionic_conductivity_estimate"] = val
            elif c.get(prop_name) is None:
                c[prop_name] = val

        # 2. 合成可行性检查（快速评分）
        synth_status = "pending"
        synth_score = None
        if req.run_synthesis_check:
            smiles = c.get("smiles") or c.get("psmiles") or ""
            if smiles:
                try:
                    score = await asyncio.to_thread(agent.check_synthesis, smiles)
                    synth_score = float(score)
                    synth_status = "done"
                except Exception as e:
                    logger.warning("合成检查失败 %s: %s", candidate_key, e)
                    synth_status = "failed"
            elif c.get("formula") and req.material_kind == "crystal":
                # 晶体无 SMILES，跳过合成检查
                synth_status = "skipped"

        # 3. 可制造性检查（复用 IndustrialFeasibilityScreening，替换原 DFT 验证）
        # 使用公共方法 evaluate_single（不修改 candidate 对象）
        mfg_status = "pending"
        mfg_score = None
        try:
            feasibility_result = await asyncio.to_thread(
                agent.feasibility_screener.evaluate_single, c
            )
            # PASS / PASS_WITH_RISKS / REVIEW / BLOCK → done/review/failed
            if feasibility_result.status in ("PASS", "PASS_WITH_RISKS"):
                mfg_status = "done"
            elif feasibility_result.status == "REVIEW":
                mfg_status = "review"
            elif feasibility_result.status == "BLOCK":
                mfg_status = "failed"
            else:
                mfg_status = "done"
            mfg_score = float(feasibility_result.feasibility_score) / 100.0  # 归一化到 0-1
        except Exception as e:
            logger.warning("可制造性检查出错 %s: %s", candidate_key, e)
            # 工具异常用 error 状态，与 failed（评估为不可制造）区分
            mfg_status = "error"

        results.append({
            "candidate_key": candidate_key,
            "prediction_status": pred_result["status"],
            "predictions": predictions,
            "targets_met": pred_result.get("targets_met", 0),
            "total_targets": pred_result.get("total_targets", 0),
            "synthesis_status": synth_status,
            "synthesis_score": synth_score,
            "manufacturability_status": mfg_status,
            "manufacturability_score": mfg_score,
            "candidate": c,  # 回填预测值后的候选
        })

    return {
        "results": results,
        "count": len(results),
    }


@app.post("/discover/generate", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def discover_generate(req: GenerateRequest):
    """生成式分子/晶体空间探索（模板化生成）。"""
    from .generation.gen_model import GenerativeModel
    model = GenerativeModel()

    # 约束键兼容：required_elements → elements
    constraints = dict(req.constraints)
    if "required_elements" in constraints and "elements" not in constraints:
        constraints["elements"] = constraints["required_elements"]

    # 在调用 AI 生成前，计算输入参数的哈希快照
    input_snapshot_hash = _compute_input_snapshot({
        "mode": req.mode,
        "constraints": constraints,
        "count": req.count,
        "source": "internlm",
    })

    def _generate():
        if req.mode == "crystal":
            return model.generate_crystals(constraints)
        return model.generate_molecules(constraints)

    candidates = await asyncio.to_thread(_generate)

    # 标准化输出：确保每个候选都包含 name 和 smiles 字段
    for c in candidates:
        if "name" not in c:
            c["name"] = c.get("formula") or c.get("smiles") or ""
        if "smiles" not in c:
            c["smiles"] = c.get("psmiles") or ""

    # SCP 工具校验化学式（优先 SCP，失败回退到 pymatgen 本地校验）
    try:
        from .mcp_tools.scp_client import get_scp_client
        scp_client = get_scp_client()
        for c in candidates:
            if "formula" in c and c["formula"]:
                try:
                    # 调用 SCP Formula 校验工具
                    result = await asyncio.to_thread(
                        scp_client.call_tool,
                        "Formula",
                        {"formula": c["formula"]}
                    )
                    if result and result.get("valid") is False:
                        c["human_review_required"] = True
                        c["description"] = (c.get("description", "") + "；化学式待人工审核").strip("；")
                except Exception as e:
                    logger.warning("SCP Formula 校验失败，回退到本地校验: %s", e)
                    # 回退到 pymatgen 本地校验
                    if not _validate_formula_local(c.get("formula", "")):
                        c["human_review_required"] = True
                        c["description"] = (c.get("description", "") + "；化学式待人工审核").strip("；")
    except ImportError:
        logger.debug("SCP client not available, skipping SCP validation")
    except Exception as e:
        logger.warning("SCP 校验层异常: %s", e)

    # 在候选结果中补充 ai_meta（已有则补充，不覆盖已有字段）
    from datetime import datetime as _dt, timezone
    for c in candidates:
        if not c.get("ai_meta"):
            c["ai_meta"] = {}
        c["ai_meta"]["input_snapshot_hash"] = input_snapshot_hash
        c["ai_meta"]["model_version"] = "internlm-v1"
        c["ai_meta"]["generated_at"] = _dt.now(timezone.utc).isoformat()

    # 放行门禁：human_review_required 的结果自动创建 Release Card 进入审批队列
    for c in candidates:
        if c.get("human_review_required"):
            c["release_card_required"] = True
            c["release_card_reason"] = "化学式待人工审核，需通过放行卡审批后才能用于实验"
            card_id = _auto_create_release_card_for_candidate(c)
            if card_id:
                c["release_card_id"] = card_id

    return {
        "candidates": candidates[:req.count],
        "count": min(len(candidates), req.count),
        "mode": req.mode,
    }


@app.get("/candidates", dependencies=[Depends(require_login)])
async def list_candidates(candidate_type: str = "", scenario_id: str = "",
                          limit: int = 0, offset: int = 0, include_demo: bool = False):
    """列出持久化的候选材料记录，支持按类型与场景 ID 筛选。

    评测修复 P2-002：limit/offset 分页参数此前被忽略导致全量返回。
    limit<=0 表示不分页（向后兼容旧调用方），limit>0 时返回分页切片。
    D2(P2-002)：默认过滤 SEED_ 演示数据，include_demo=True 时包含。
    综合评分缺失（历史/生成时未写入）但属性齐全时按生成器方法补算，与工艺深化一致。
    """
    records = app.state.candidate_store.list_all(candidate_type, scenario_id)
    items = _filter_demo([r.model_dump() for r in records], include_demo)
    _backfill_multi_objective_scores(items)
    total = len(items)
    if limit > 0:
        items = items[max(0, offset): max(0, offset) + limit]
    return {
        "candidates": items,
        "count": len(items),
        "total": total,
    }


@app.get("/candidates/{candidate_id}", dependencies=[Depends(require_login)])
async def get_candidate(candidate_id: str):
    """获取单个候选材料详情（含完整生成数据）。"""
    record = app.state.candidate_store.get(candidate_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    return record.model_dump()


@app.post("/candidates/promote-from-temporary", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def promote_from_temporary(payload: dict = Body(...)):
    """P3：将临时性质预测结果转正为正式候选材料。

    - candidate: 临时预测候选对象（含 formula/smiles/name/预测属性等）
    - project_id / task_id: 所属项目与任务（用于业务链路追溯）
    - origin_temp_id: 临时结果来源标识（前端生成，用于谱系追溯 + 幂等去重）
    生成新 candidate_id 并持久化，返回创建的候选记录。
    """
    candidate = payload.get("candidate") or {}
    if not isinstance(candidate, dict) or not candidate:
        raise HTTPException(status_code=400, detail="candidate 不能为空")
    project_id = str(payload.get("project_id") or "")
    task_id = str(payload.get("task_id") or "")
    origin_temp_id = str(payload.get("origin_temp_id") or "")
    # 幂等：同一 origin_temp_id 重复转正返回已存在的候选，避免创建重复候选
    if origin_temp_id:
        existing = app.state.candidate_store.find_by_origin_temp_id(origin_temp_id)
        if existing is not None:
            logger.info(
                "临时预测转正已存在，幂等返回 origin_temp_id=%s candidate_id=%s",
                origin_temp_id, existing.candidate_id,
            )
            return existing.model_dump()

    candidate_id = f"CAND-{uuid.uuid4().hex[:8].upper()}"
    name = candidate.get("name") or candidate.get("formula") or candidate.get("smiles") or ""
    smiles = candidate.get("smiles") or candidate.get("psmiles") or ""
    # 推断材料类型：优先显式字段（payload.material_type / candidate 内字段），
    # 否则按 formula/smiles 特征判断（兜底，避免依赖不可靠的推断）
    candidate_type = (
        (payload.get("material_type") or payload.get("materialType"))
        or candidate.get("candidate_type")
        or candidate.get("material_type")
        or candidate.get("materialType")
        or ""
    )
    if not candidate_type:
        # 兜底判定（修复：无机锂化合物的 SMILES 无碳原子，此前被误判为 polymer）：
        # - 有化学式无 SMILES → 晶体（无机/陶瓷）
        # - SMILES 含碳 → 分子/聚合物（含 [*] 端基标记的为聚合物）
        # - SMILES 无碳（如 Li6PS5Cl 类无机盐）→ 晶体
        import re as _re
        _smiles_txt = smiles or ""
        _has_carbon = bool(_re.search(r"[Cc]", _smiles_txt))
        if candidate.get("formula") and not _smiles_txt:
            candidate_type = "crystal"
        elif _has_carbon:
            candidate_type = "polymer"
        else:
            candidate_type = "crystal"

    # 组装完整 data：写入归属与来源谱系，便于跨模块追溯
    data = {**candidate, "candidate_id": candidate_id, "project_id": project_id, "task_id": task_id}
    provenance = candidate.get("provenance")
    if not isinstance(provenance, list):
        provenance = []
    provenance.append({"step": "promote_from_temporary", "origin_temp_id": origin_temp_id})
    data["provenance"] = provenance
    # 组装 prediction 顶层字段（与 discover 候选结构一致，含模型版本/置信度/预测值/溯源）
    data["prediction"] = _assemble_prediction(data)

    record = CandidateRecord(
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        name=name,
        smiles=smiles,
        source=candidate.get("source") or "temporary_prediction",
        project_id=project_id,
        task_id=task_id,
        multi_objective_score=candidate.get("multi_objective_score", 0.0),
        prediction=data.get("prediction") if isinstance(data.get("prediction"), dict) else {},
        data=data,
    )
    # dedup=False：每个临时预测结果均创建独立候选（同公式可并存），
    # 并返回实际落库对象，避免内容哈希去重产生数据库不存在的幽灵 ID。
    saved = app.state.candidate_store.save(record, dedup=False)
    logger.info("临时预测转正为候选 candidate_id=%s type=%s task_id=%s", candidate_id, candidate_type, task_id)
    return saved.model_dump()


# ── 0040 两层流程：候选材料状态机 / 一键生成实验单 / 工艺方案状态 ─────────

class CandidateStatusRequest(BaseModel):
    """候选材料状态迁移请求。

    注意：不接收客户端传入的 actor_role —— 操作角色由服务端从认证用户推导，
    杜绝客户端伪造角色绕过状态机校验。
    """
    status: str = Field(..., description="目标状态：screening/feasible/process_planning/process_confirmed/ready_for_experiment/rejected")
    owner: str = Field(default="", description="新的责任人（用户名）")
    reason: str = Field(default="", description="迁移原因")


# 认证访问角色 → 允许执行的状态机操作角色（formulator / process_engineer）
# 访问门禁已由 require_role(UserRole.RESEARCHER) 拦截；此处将访问角色映射为
# 状态机操作角色。用户模型未内置 formulator/process_engineer 区分，故研发序列角色
# 均可执行两类操作；REVIEWER/VIEWER 无操作角色，且被 require_role 拦截。
_ACCESS_ROLE_TO_OPERATION_ROLES: dict[UserRole, set[str]] = {
    UserRole.RESEARCHER: {"formulator", "process_engineer"},
    UserRole.DATA_ENGINEER: {"formulator", "process_engineer"},
    UserRole.PROJECT_MANAGER: {"formulator", "process_engineer"},
    UserRole.ADMIN: {"formulator", "process_engineer"},
    UserRole.REVIEWER: set(),
    UserRole.VIEWER: set(),
}


@app.patch("/candidates/{candidate_id}/status",
           dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_candidate_status(candidate_id: str, req: CandidateStatusRequest,
                                  current_user: User = Depends(require_login)):
    """更新候选材料状态（两层状态机 + 角色校验）。

    操作角色从认证用户（JWT）推导，不再信任客户端传入的 actor_role。
    """
    from .experiment.candidate_store import IllegalCandidateTransitionError
    # 不存在时给 404 而非 409（此前非法迁移异常被统一报 409，误导）
    if app.state.candidate_store.get(candidate_id) is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    try:
        updated = app.state.candidate_store.update_status(
            candidate_id, req.status,
            actor_operation_roles=_ACCESS_ROLE_TO_OPERATION_ROLES.get(current_user.role, set()),
            owner=req.owner, triggered_by="user", reason=req.reason,
        )
    except IllegalCandidateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return updated.model_dump()


@app.delete("/candidates/{candidate_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_candidate(candidate_id: str):
    """删除候选材料（2B 数据治理：被业务对象引用的候选禁止删除，仅可淘汰归档；
    仅清理其派生内部数据（candidate_artifacts）。"""
    from .experiment.candidate_store import CandidateRecord
    store = app.state.candidate_store
    if store.get(candidate_id) is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    # 引用检查：实验任务 / 工艺方案 / 配方 BOM / 样品 / 放行卡
    referenced: list[str] = []
    try:
        orders = agent.experiment_controller._store.list_orders()
        if any(getattr(o, "candidate_id", "") == candidate_id for o in orders):
            referenced.append("实验任务")
    except Exception:  # noqa: BLE001
        pass
    try:
        schemes = app.state.process_scheme_store.list_by_candidate(candidate_id)
        if schemes:
            referenced.append("工艺方案")
    except Exception:  # noqa: BLE001
        pass
    try:
        boms = app.state.bom_store.list_by_candidate(candidate_id)
        if boms:
            referenced.append("配方 BOM")
    except Exception:  # noqa: BLE001
        pass
    try:
        samples = app.state.sample_store.list_all()
        if any(getattr(s, "source_candidate_id", "") == candidate_id for s in samples):
            referenced.append("样品")
    except Exception:  # noqa: BLE001
        pass
    try:
        cards = app.state.release_card_store.list()
        if any(getattr(c, "candidate_id", "") == candidate_id for c in cards):
            referenced.append("放行卡")
    except Exception:  # noqa: BLE001
        pass
    if referenced:
        raise HTTPException(
            status_code=409,
            detail=f"候选材料已被{'、'.join(referenced)}引用，无法删除；请先改用「淘汰」状态归档",
        )
    # 清理候选的派生内部数据（候选快照/合规检查等），避免 FK 约束
    try:
        from .experiment.candidate_artifact_store import CandidateArtifact
        store_art = app.state.candidate_artifact_store
        for art in store_art.list_by_candidate(candidate_id):
            store_art.delete(candidate_id, art.artifact_type or "")
    except Exception:  # noqa: BLE001
        pass
    if not store.delete(candidate_id):
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    return {"deleted": True, "candidate_id": candidate_id}


class OneClickExperimentRequest(BaseModel):
    """一键生成实验单请求（配方来源 + 工艺路径双引用）。"""
    project_id: str = ""
    scenario_id: str = ""
    process_id: str = Field(default="", description="工艺方案 ID（须已确认 confirmed）")
    notes: str = ""


@app.post("/candidates/{candidate_id}/one-click-experiment",
          dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_one_click_experiment(candidate_id: str, req: OneClickExperimentRequest):
    """一键生成实验任务单：自动关联确定的配方与已确认的工艺路径。"""
    record = app.state.candidate_store.get(candidate_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    # 放行门禁校验：关联候选若有 release_card_required 且未通过审批，拒绝下达实验。
    # 防死锁：若候选标记了放行要求但不存在任何放行卡（历史/建卡失败），自动补建待审批卡，
    # 确保审批队列可见，而不是静默永久阻断。
    cand_data = record.data or {}
    if cand_data.get("release_card_required") and not cand_data.get("release_card_approved"):
        existing_card = _find_release_card_for_candidate(candidate_id)
        if existing_card is None:
            _card_id = _auto_create_release_card_for_candidate(
                {**cand_data, "candidate_id": candidate_id, "name": record.name or ""},
                project_id=req.project_id or record.project_id,
                reason="候选要求放行审批但未发现放行卡，已自动补建",
            )
            if _card_id:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"候选材料 {candidate_id} 需要通过放行卡审批后才能创建实验任务；"
                        f"已自动生成放行卡 {_card_id}，请到「我的待办 → 放行卡」完成审批后重试"
                    ),
                )
        raise HTTPException(
            status_code=403,
            detail=f"候选材料 {candidate_id} 需要通过放行卡审批后才能创建实验任务",
        )
    try:
        order = agent.experiment_controller.create_order_for_candidate_and_process(
            candidate_id=candidate_id,
            process_id=req.process_id,
            project_id=req.project_id,
            scenario_id=req.scenario_id or record.scenario_id,
            notes=req.notes,
        )
    except ValueError as e:
        # T10：实验创建失败补偿——写入 notifications 供运维对账，幂等防重复
        try:
            _failed_order_id = f"FAILED-{candidate_id}-{req.process_id or 'none'}"
            if not agent.experiment_controller.notification_exists(
                order_id=_failed_order_id, assignee="admin"
            ):
                _msg = (f"实验创建失败需人工补偿：候选 {candidate_id} 工艺 {req.process_id or '未关联'}，"
                        f"原因：{e}")
                agent.experiment_controller.save_notification(
                    order_id=_failed_order_id,
                    assignee="admin",
                    message=_msg,
                )
                logger.warning("实验创建失败已记录补偿通知：%s", _msg)
            else:
                logger.info("实验创建失败补偿通知已存在，跳过重复通知：%s", _failed_order_id)
        except Exception as ne:
            logger.error("实验创建失败补偿通知写入失败：%s", ne)
        raise HTTPException(status_code=400, detail=str(e)) from e
    _log_research_event(
        event_type="experiment",
        run_id=order.order_id,
        title=f"一键生成实验任务单：{order.order_id}",
        summary=f"候选 {candidate_id}，工艺 {req.process_id or '未关联'}",
        status="running",
        payload={"order_id": order.order_id, "candidate_id": candidate_id,
                 "process_id": req.process_id},
    )
    return order.model_dump()


class ProcessSchemeStatusRequest(BaseModel):
    """工艺方案状态迁移请求。"""
    status: str = Field(..., description="目标状态：draft/reviewing/confirmed/abandoned")
    owner: str = Field(default="", description="新的责任人（工艺人员用户名）")
    require_role: str = Field(default="process_engineer", description="操作者角色（默认 process_engineer）")
    reason: str = Field(default="", description="迁移原因")


@app.patch("/process-schemes/{process_id}/status",
           dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_process_scheme_status(process_id: str, req: ProcessSchemeStatusRequest):
    """更新工艺方案状态（draft → reviewing → confirmed / abandoned）。"""
    from .experiment.process_scheme_store import IllegalProcessSchemeTransitionError
    try:
        updated = app.state.process_scheme_store.update_status(
            process_id, req.status, owner=req.owner,
            triggered_by="user", reason=req.reason,
            require_role=req.require_role,
        )
    except IllegalProcessSchemeTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return updated.model_dump()


@app.delete("/process-schemes/{process_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_process_scheme(process_id: str):
    """删除工艺方案（2B 数据治理：已被配方 BOM 引用的方案禁止删除，仅可归档为 abandoned）。"""

    store = app.state.process_scheme_store
    if store.get(process_id) is None:
        raise HTTPException(status_code=404, detail=f"工艺方案 {process_id} 不存在")
    # 引用检查：配方 BOM 通过 process_id 关联该方案
    referenced_bom = None
    try:
        for b in app.state.bom_store.list_all():
            if b.process_id == process_id:
                referenced_bom = b.bom_id or b.process_id or ""
                break
    except Exception:  # noqa: BLE001
        pass
    if referenced_bom:
        raise HTTPException(
            status_code=409,
            detail=f"工艺方案已被配方 {referenced_bom} 引用，无法删除；请先将方案状态改为「已放弃」归档",
        )
    if not store.delete(process_id):
        raise HTTPException(status_code=404, detail=f"工艺方案 {process_id} 不存在")
    return {"deleted": True, "process_id": process_id}


class ProcessDeepeningRequest(BaseModel):
    """工艺深化请求（process_engineer 角色，SCP 优先 + 本地回退）。"""
    candidate_id: str = Field(..., description="候选材料 ID")
    owner: str = Field(default="", description="工艺人员用户名")
    process_id: str = Field(default="", description="既有工艺方案 ID（留空则新建/复用候选草稿）")
    max_routes: int = Field(default=5, ge=1, le=20, description="最大候选路线数")
    max_depth: int = Field(default=3, ge=1, le=8, description="逆合成搜索深度")
    notes: str = Field(default="", description="深化说明")


@app.post("/candidates/{candidate_id}/process-deepening",
          dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_process_deepening(candidate_id: str, req: ProcessDeepeningRequest):
    """对候选配方执行工艺深化（第二层工艺深化阶段）。

    高级能力（合成路径规划 / DFT 校验）采用 SCP 优先 + 本地回退策略，
    产出/更新工艺方案（ProcessScheme），能力来源记录于 evidence_refs。
    """
    service = getattr(app.state, "process_deepening_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="工艺深化服务未初始化")
    try:
        scheme = await service.deepen(
            candidate_id=candidate_id,
            owner=req.owner,
            triggered_by="user",
            max_routes=req.max_routes,
            max_depth=req.max_depth,
            process_id=req.process_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _log_research_event(
        event_type="process_deepening",
        run_id=scheme.process_id,
        title=f"工艺深化：候选 {candidate_id}",
        summary=req.notes or f"生成 {len(scheme.routes)} 条候选工艺路线",
        status="running",
        payload={"candidate_id": candidate_id, "process_id": scheme.process_id,
                 "routes": len(scheme.routes)},
    )
    return scheme.model_dump()


# ── 工艺人员工作台：初筛通过的候选配方与工艺方案 ───────────────────

# 综合评分补算属性（与 generator 的 min-max 归一化方法一致，等权重）
_SCORE_PROPS = [
    ("tensile_strength", "maximize"),
    ("flexural_modulus", "maximize"),
    ("impact_strength", "maximize"),
    ("heat_deflection_temp", "maximize"),
]


def _backfill_multi_objective_scores(records: list[dict]) -> None:
    """为缺失综合评分的候选补算评分（原地修改）。

    历史/种子/转正候选可能未写入 multi_objective_score（为 0），
    但属性齐全时按**绝对规格基准**归一化补算（ADR-0003），
    与候选生成器同源（material_properties.REFERENCE_RANGES），
    保证跨列表/跨轮次可比。
    属性优先取候选顶层字段，其次取 data JSONB（旧数据属性存于嵌套结构）。
    """
    from .material_properties import REFERENCE_RANGES, normalize_by_reference

    def _prop(r, key):
        v = r.get(key)
        if v is None:
            v = (r.get("data") or {}).get(key)
        return v

    def _num(v):
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0

    targets = [
        r for r in records
        if not _num(r.get("multi_objective_score"))
        and any(_num(_prop(r, p)) != 0.0 for p, _ in _SCORE_PROPS)
    ]
    if not targets:
        return
    total_weight = float(len(_SCORE_PROPS))
    for prop, direction in _SCORE_PROPS:
        ref = REFERENCE_RANGES.get(prop)
        # 无参考范围时回退池内相对（罕见）：池值预先取好传给共享归一化
        pool_vals = None
        if ref is None:
            pool_vals = [_num(_prop(x, prop)) for x in targets]
        for r in targets:
            v = _num(_prop(r, prop))
            normalized = normalize_by_reference(v, ref, direction=direction, pool_values=pool_vals)
            r["multi_objective_score"] = _num(r.get("multi_objective_score")) + (1.0 / total_weight) * normalized


@app.get("/process-engineer/workbench",
         dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def process_engineer_workbench(status: str = "", limit: int = Query(100, ge=1, le=500)):
    """工艺人员工作台：列出进入工艺深化流水线的候选配方及其工艺方案。

    属于候选状态机第二层（feasible → process_planning → process_confirmed）。
    可按候选状态过滤；每个候选附带其工艺方案列表（routes / evidence_refs / status）。
    候选综合评分缺失（历史数据为 0）但属性齐全时，按生成器同方法补算返回。
    """
    from .experiment.candidate_store import CandidateStatus
    records = app.state.candidate_store.list_all()
    # 工艺深化流水线状态：初筛通过后的候选
    pipeline = {
        CandidateStatus.FEASIBLE.value,
        CandidateStatus.PROCESS_PLANNING.value,
        CandidateStatus.PROCESS_CONFIRMED.value,
        CandidateStatus.READY_FOR_EXPERIMENT.value,
    }
    items = []
    for r in records:
        if r.status not in pipeline:
            continue
        if status and r.status != status:
            continue
        schemes = app.state.process_scheme_store.list_by_candidate(r.candidate_id)
        items.append({
            "candidate": r.model_dump(),
            "process_schemes": [s.model_dump() for s in schemes],
            "scheme_count": len(schemes),
        })
        if len(items) >= limit:
            break
    # 综合评分补算（仅当缺失且属性齐全）
    _backfill_multi_objective_scores([it["candidate"] for it in items])
    return {"items": items, "count": len(items), "pipeline_statuses": sorted(pipeline)}


# ── 业务链路 MDM：任务 → 候选材料 → BOM 方案 → 测试任务 ─────────────

@app.get("/tasks/{task_id}/candidates")
async def list_task_candidates(task_id: str):
    """查询任务下的所有候选材料（业务链路：任务 1 → N 候选材料）。"""
    records = app.state.candidate_store.list_all(task_id=task_id)
    items = [r.model_dump() for r in records]
    # 综合评分缺失但属性齐全时按生成器方法补算，保证与工作台/工艺深化评分一致
    _backfill_multi_objective_scores(items)
    return {
        "task_id": task_id,
        "candidates": items,
        "count": len(items),
    }


@app.get("/candidates/{candidate_id}/bom", dependencies=[Depends(require_login)])
async def get_candidate_bom(candidate_id: str):
    """查询候选材料对应的 BOM 方案（业务链路：候选材料 1:N BOM 方案，0021 迁移放宽）。

    Returns:
        200: 返回 BOM 方案列表（若无则为空列表）；为向后兼容同时返回最新一条 bom 字段。
    """
    bom_list = app.state.bom_store.list_by_candidate(candidate_id)
    latest = bom_list[0] if bom_list else None
    return {
        "candidate_id": candidate_id,
        "bom_list": [b.model_dump() for b in bom_list],
        "count": len(bom_list),
        # 向后兼容：返回最新一条 BOM（旧前端可能直接读 bom 字段）
        "bom": latest.model_dump() if latest else None,
    }


class BomCreateRequest(BaseModel):
    """创建 BOM 方案请求。"""
    task_id: str = ""
    formulation: dict = Field(default_factory=dict)
    process_route: dict = Field(default_factory=dict)
    test_protocol: dict = Field(default_factory=dict)
    version: str = "v1"
    status: str = "draft"
    created_by: str = ""


@app.post("/candidates/{candidate_id}/bom", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_candidate_bom(candidate_id: str, req: BomCreateRequest):
    """为候选材料创建 BOM 方案（业务链路：候选材料 1:1 BOM 方案）。

    Raises:
        404: 候选材料不存在
        409: 候选材料已存在 BOM 方案
    """
    # 校验候选材料存在
    cand = app.state.candidate_store.get(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")

    from .experiment.bom_store import BomScheme
    bom = BomScheme(
        candidate_id=candidate_id,
        task_id=req.task_id or cand.task_id,
        formulation=req.formulation,
        process_route=req.process_route,
        test_protocol=req.test_protocol,
        version=req.version,
        status=req.status,
        created_by=req.created_by,
    )
    try:
        created = app.state.bom_store.create(bom)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return created.model_dump()


class BomUpdateRequest(BaseModel):
    """更新 BOM 方案请求。"""
    task_id: str | None = None
    formulation: dict | None = None
    process_route: dict | None = None
    test_protocol: dict | None = None
    version: str | None = None
    status: str | None = None
    created_by: str | None = None


@app.put("/bom/{bom_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_bom(bom_id: str, req: BomUpdateRequest):
    """更新 BOM 方案。"""
    existing = app.state.bom_store.get(bom_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"BOM 方案 {bom_id} 不存在")

    # 仅更新非 None 字段
    if req.task_id is not None:
        existing.task_id = req.task_id
    if req.formulation is not None:
        existing.formulation = req.formulation
    if req.process_route is not None:
        existing.process_route = req.process_route
    if req.test_protocol is not None:
        existing.test_protocol = req.test_protocol
    if req.version is not None:
        existing.version = req.version
    if req.status is not None:
        existing.status = req.status
    if req.created_by is not None:
        existing.created_by = req.created_by

    updated = app.state.bom_store.update(existing)
    return updated.model_dump()


@app.get("/bom/{bom_id}/test-tasks")
async def list_bom_test_tasks(bom_id: str):
    """查询 BOM 方案下的所有测试任务（业务链路：BOM 方案 1 → N 测试任务）。

    注：测试任务通过 bom_id 关联到 BOM 方案。
    """
    bom = app.state.bom_store.get(bom_id)
    if bom is None:
        raise HTTPException(status_code=404, detail=f"BOM 方案 {bom_id} 不存在")
    tasks = app.state.test_task_store.list_by_bom(bom_id)
    return {
        "bom_id": bom_id,
        "test_tasks": [t.model_dump() for t in tasks],
        "count": len(tasks),
    }


# ===========================================================================
# 0021 新增：候选详情 Tab 数据持久化与从合成路径生成 BOM+工艺方案
# ===========================================================================

@app.get("/candidates/{candidate_id}/artifacts", dependencies=[Depends(require_login)])
async def list_candidate_artifacts(candidate_id: str):
    """返回候选所有产出物（性质预测 + 合规检查 + 最新合成任务）。

    用于前端刷新页面时恢复候选详情各 Tab 的持久化数据。
    """
    artifacts = app.state.candidate_artifact_store.list_by_candidate(candidate_id)
    # 同时返回最新一条成功的合成任务（便于前端恢复合成路径 Tab）
    synth_task = _get_synthesis_task_store().get_latest_success_by_candidate(candidate_id)
    # P3-B2：返回候选持久化的合成可行性摘要（最佳路线可行性，仅展示）
    synth_feas = {}
    try:
        cand = app.state.candidate_store.get(candidate_id)
        if cand is not None:
            synth_feas = cand.synthesis_feasibility or {}
    except Exception as e:  # noqa: BLE001
        logger.debug("读取候选合成可行性失败 candidate_id=%s: %s", candidate_id, e)
    return {
        "candidate_id": candidate_id,
        "artifacts": [a.model_dump() for a in artifacts],
        "latest_synthesis_task": synth_task,
        "synthesis_feasibility": synth_feas,
    }


@app.get("/candidates/{candidate_id}/artifacts/{artifact_type}", dependencies=[Depends(require_login)])
async def get_candidate_artifact(candidate_id: str, artifact_type: str):
    """返回候选特定类型产出物（artifact_type: prediction / compliance）。"""
    artifact = app.state.candidate_artifact_store.get(candidate_id, artifact_type)
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 {artifact_type} 类型的产出物",
        )
    return artifact.model_dump()


@app.get("/candidates/{candidate_id}/synthesis-tasks", dependencies=[Depends(require_login)])
async def list_candidate_synthesis_tasks(candidate_id: str):
    """返回候选的合成任务历史（按创建时间倒序）。"""
    tasks = _get_synthesis_task_store().list_by_candidate(candidate_id)
    return {
        "candidate_id": candidate_id,
        "tasks": tasks,
        "count": len(tasks),
    }


class BomFromRouteRequest(BaseModel):
    """从合成路径生成 BOM + 工艺方案请求（0021 新增；0727b 重命名 quantity_kg → quantity）。"""
    route_id: str  # 如 "R1"，对应 task.result.routes 数组中的某条路径
    synthesis_task_id: str = ""  # 来源合成任务 ID（用于追溯）
    name: str = ""  # BOM 名称，如未提供则自动生成 "BOM - 路径1"
    created_by: str = ""
    quantity: float = 1.0  # 0727b：BOM 用量，传递给 FormulaAgent 计算成本


class BomFromProcessRequest(BaseModel):
    """从已确认的工艺方案生成配方（BOM）请求（打通 深化→配方 链路）。

    工艺人员确认工艺方案（status=confirmed）后，系统据此生成 BOM 配方，
    复用 FormulaAgent 的配方生成能力，并回填 BomScheme.process_id 关联工艺方案。
    route_id 可选：指定以哪条候选工艺路线为准；留空则取方案中可行性最高的一条。
    """
    process_id: str  # 已确认的工艺方案 ID
    route_id: str = ""  # 可选，指定工艺方案中的某条候选路线
    name: str = ""  # BOM 名称，留空自动生成
    created_by: str = ""
    quantity: float = 1.0  # BOM 用量，传递给 FormulaAgent 计算成本


def _match_route_by_id(routes: list[dict], route_id: str) -> tuple[dict | None, int]:
    """在 routes 列表中按 route_id 匹配，支持 "R1" 和 "1" 两种格式。

    Returns:
        (matched_route, index) 或 (None, -1)
    """
    if not route_id:
        return None, -1
    rid_norm = route_id.strip().upper()
    rid_num = rid_norm.lstrip("R") if rid_norm.startswith("R") else rid_norm
    for idx, r in enumerate(routes or []):
        cur = str(r.get("route_id", "")).strip().upper()
        cur_num = cur.lstrip("R") if cur.startswith("R") else cur
        if cur and (cur == rid_norm or (rid_num and cur_num == rid_num)):
            return r, idx
    # 退化：若 route_id 是纯数字，按 index+1 匹配
    if rid_num.isdigit():
        i = int(rid_num) - 1
        if 0 <= i < len(routes or []):
            return routes[i], i
    return None, -1


def _resolve_target_property(domain_pack: dict | None = None) -> str:
    """从领域包读取默认目标属性；未配置时回退 v4.1 默认高分子属性。

    用于候选生成与 BOM 生成时传递 target_property，避免在多个接口中写死。
    """
    _dp = domain_pack
    if not isinstance(_dp, dict):
        _fa = getattr(agent, "formula_agent", None)
        _dp = getattr(_fa, "domain_pack", None) if _fa else None
    if isinstance(_dp, dict):
        props = _dp.get("default_target_properties") or []
        if props and props[0]:
            return str(props[0])
    return "tensile_strength"


def _resolve_material_domain(cfg, domain_key: str = "") -> dict:
    """统一材料体系配置：优先从领域包 data 读取，AgentConfig 仅作回退。

    消除"材料体系双源"：/config 与 /api/config 改由领域包 Store 提供权威值，
    AgentConfig.material_domain 只在领域包未提供某项时回退，保证新领域（如金发
    科技聚合物配方）无需改 AgentConfig 即可反映在体系模板上。

    domain_key 指定时精确解析该领域包（如请求带 kingfa 时返回改性塑料体系）；
    留空则取默认活跃包。

    返回结构与 AgentConfig.material_domain 对齐：
    {material_systems, default_target_properties, example_formulas}

    跨域防串数据：领域包一旦激活，各字段由该领域包权威决定；领域包未声明的
    字段返回空列表，**不再回退**到 AgentConfig 默认（AgentConfig 仅在没有活跃
    领域包时兜底），避免把其他领域（如默认电池）的体系/属性串入当前领域。
    """
    domain_data = {}
    try:
        from .industrialization.domain_pack_store import DomainPackStore
        store = DomainPackStore()
        pack = store.resolve_active_pack(domain_key=domain_key)
        if pack is not None and isinstance(pack.data, dict):
            domain_data = pack.data
    except Exception:
        logger.debug("resolve material_domain from domain pack failed, fallback to config", exc_info=True)

    fallback = getattr(cfg, "material_domain", None)

    def _pick(key: str) -> list:
        if domain_data:
            # 领域包已激活：未声明字段即返回空，避免跨域串入默认（电池）配置。
            return domain_data.get(key) or []
        # 无活跃领域包：回退 AgentConfig 默认。
        if fallback is None:
            return []
        return getattr(fallback, key, None) or []

    return {
        "material_systems": _pick("material_systems"),
        "default_target_properties": _pick("default_target_properties"),
        "example_formulas": _pick("example_formulas"),
    }


def _assert_bom_system_consistency(
    cand_type: str,
    target_label: str,
    bom_materials: list[dict],
    consistency: dict | None = None,
) -> list[str]:
    """C2(P1-004)：BOM 明细物料体系与目标材料体系一致性校验。

    目标为晶体体系时，BOM 不得含聚合物体系物料（如 PEO/PVDF/PAN）；
    目标为聚合物体系时，BOM 不得含晶体/无机物物料（如 LIFEPO4/NCM/硫化物）。
    返回跨体系错配的物料名列表；为空表示一致。

    consistency 为领域包中的一致性规则（含 polymer_kw/crystal_kw），
    未传入时使用内置默认关键词，保证旧行为不回归。
    """
    _cons = consistency or {}
    _poly_kw = tuple(_cons.get("polymer_kw") or ("peo", "polymer", "pvdf", "pan ", "pan-", "pmma", "psmiles", "[*]"))
    _crystal_kw = tuple(_cons.get("crystal_kw") or ("lpscl", "lgps", "li6ps5cl", "lifepo4", "ncm", "sulfide", "li2s", "p2s5"))
    _type = (cand_type or "").lower()
    _label = (target_label or "").lower()
    if "polymer" in _type:
        is_crystal_target = False
    elif "crystal" in _type:
        is_crystal_target = True
    else:
        is_crystal_target = not (_label and any(k in _label for k in _poly_kw))
    crossed = []
    for _m in bom_materials or []:
        _name = str(_m.get("material_name") or _m.get("material_id") or "").lower()
        if not _name:
            continue
        if is_crystal_target:
            if any(k in _name for k in _poly_kw):
                crossed.append(_name)
        else:
            if any(k in _name for k in _crystal_kw):
                crossed.append(_name)
    return crossed


def _extract_route_to_bom(route: dict) -> tuple[dict, list[dict], list[dict]]:
    """将合成路径转换为 BOM formulation / process_route / 工艺步骤 / 原料清单。

    Returns:
        (formulation, process_route, process_steps, raw_materials)
    """
    steps_in = route.get("steps") or []
    # 原料清单：合并所有步骤的 reactants，去重保序
    material_names: list[str] = []
    seen: set[str] = set()
    for s in steps_in:
        for r in s.get("reactants") or []:
            if r and r not in seen:
                seen.add(r)
                material_names.append(r)
    # 晶体路径：provenance.precursors 可能含原料
    for prov in route.get("provenance") or []:
        for p in prov.get("precursors") or []:
            if p and p not in seen:
                seen.add(p)
                material_names.append(p)
    # 兜底：route 顶层 reactants（聚合字段）
    for r in route.get("reactants") or []:
        if r and r not in seen:
            seen.add(r)
            material_names.append(r)

    raw_materials = [
        {"material_name": name, "amount": "", "role": "reactant"}
        for name in material_names
    ]
    formulation = {
        "materials": raw_materials,
        "target_smiles": route.get("target_smiles", ""),
    }
    # 工艺步骤：从 steps[*].conditions 提取
    process_steps = []
    for i, s in enumerate(steps_in, start=1):
        process_steps.append({
            "step": i,
            "conditions": s.get("conditions", ""),
            "reaction_type": s.get("reaction_type", ""),
            "reaction_smiles": s.get("reaction_smiles", ""),
            "difficulty": s.get("difficulty", ""),
        })
    process_route = {
        "steps": process_steps,
        "feasibility_score": route.get("feasibility_score", 0.0),
        "confidence": route.get("confidence", 0.0),
    }
    return formulation, process_route, process_steps, raw_materials


@app.post("/candidates/{candidate_id}/bom-from-route", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_bom_from_route(candidate_id: str, req: BomFromRouteRequest):
    """从合成路径生成 BOM + 工艺方案（0021 新增；0727 重构为调用 FormulaAgent）。

    流程：
    1. 校验候选存在
    2. 获取合成任务结果，按 route_id 匹配路径
    3. 调用 FormulaAgent（builtin_industrialization）生成完整 BOM/BOP/成本/EHS
       —— 字段对齐前端 FormulaDesign.vue 的 bomColumns / bopColumns
    4. 合成路径的 reactants 与 FormulaAgent 输出合并（保留来源追溯）
    5. 事务性创建 BomScheme 与 ProcessScheme（BomScheme.process_id 回填）
    """
    # 1. 校验候选存在
    cand = app.state.candidate_store.get(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")

    # 2. 获取合成任务结果
    if not req.synthesis_task_id:
        raise HTTPException(status_code=400, detail="synthesis_task_id 不能为空")
    task = _get_synthesis_task_store().get_task(req.synthesis_task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"合成任务 {req.synthesis_task_id} 不存在",
        )
    if task.get("status") != "success":
        raise HTTPException(
            status_code=400,
            detail=f"合成任务状态为 {task.get('status')}，无法生成 BOM",
        )
    result = task.get("result") or {}
    routes = result.get("routes") or []
    if not routes:
        raise HTTPException(status_code=400, detail="合成任务结果中无 routes")

    route, _idx = _match_route_by_id(routes, req.route_id)
    if route is None:
        raise HTTPException(
            status_code=400,
            detail=f"未在合成任务 {req.synthesis_task_id} 中匹配到 route_id={req.route_id}",
        )

    # 3. 调用 FormulaAgent 生成完整 BOM/BOP/成本/EHS
    #    target_material.candidate 传候选名称，FormulaAgent 会优先从物料库匹配
    target_material = {
        "candidate": cand.name or cand.formula or cand.smiles or candidate_id,
        "target_property": _resolve_target_property(),
    }
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "candidate_id": candidate_id,
        "synthesis_task_id": req.synthesis_task_id,
        "route_id": req.route_id,
        "quantity": req.quantity or 1.0,
        "name": req.name,
    })
    try:
        recipe_result = agent._handle_design_formula(
            target_material=target_material,
            quantity=float(req.quantity or 1.0),
            cand_type=cand.candidate_type or "",
        )
    except Exception as exc:
        logger.exception("调用 FormulaAgent 生成 BOM 失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"调用配方工艺 agent 失败：{exc}",
        ) from exc
    if "error" in recipe_result:
        raise HTTPException(
            status_code=500,
            detail=f"配方工艺 agent 返回错误：{recipe_result['error']}",
        )

    bom_list = recipe_result.get("bom") or []
    bop_list = recipe_result.get("bop") or []
    ehs = recipe_result.get("ehs") or {}
    # C2(P1-004)：BOM 明细物料体系与目标材料体系一致性校验，跨体系错配直接阻断
    # 一致性关键词从领域包读取；不可用时回退内置默认
    _cons_rules = {}
    _fa = getattr(agent, "formula_agent", None)
    _dp = getattr(_fa, "domain_pack", None) if _fa else None
    if isinstance(_dp, dict):
        _cons_rules = _dp.get("consistency") or {}
    _crossed = _assert_bom_system_consistency(
        cand.candidate_type, cand.name or cand.formula or "", bom_list, _cons_rules
    )
    if _crossed:
        raise HTTPException(
            status_code=400,
            detail=(
                "BOM 物料与目标材料体系不一致，已阻断生成："
                f"目标体系为「{cand.candidate_type or cand.name or '未知'}」，"
                f"但 BOM 含跨体系物料 {sorted(set(_crossed))}"
            ),
        )
    material_cost = float(recipe_result.get("material_cost") or 0.0)
    process_cost = float(recipe_result.get("process_cost") or 0.0)
    total_unit_cost = float(recipe_result.get("total_unit_cost") or 0.0)
    process_cost_breakdown = recipe_result.get("process_cost_breakdown") or []

    # 4. 合成路径原料与 FormulaAgent BOM 合并：将合成路径 reactants 标记为 source
    route_reactants = []
    for s in (route.get("steps") or []):
        for r in (s.get("reactants") or []):
            if r and r not in route_reactants:
                route_reactants.append(r)
    for r in (route.get("reactants") or []):
        if r and r not in route_reactants:
            route_reactants.append(r)

    # 构造 formulation（含完整 BOM 列表 + 合成路径原料追溯）
    formulation = {
        "materials": bom_list,  # 完整 BOM（对齐前端 bomColumns）
        "route_reactants": route_reactants,  # 合成路径原料（追溯用）
        "target_smiles": route.get("target_smiles", ""),
    }
    # 构造 process_route（含完整 BOP + 合成路径条件）
    process_route = {
        "steps": bop_list,  # 完整 BOP（对齐前端 bopColumns）
        "route_steps": _extract_route_to_bom(route)[2],  # 合成路径原始步骤（追溯用）
        "feasibility_score": route.get("feasibility_score", 0.0),
        "confidence": route.get("confidence", 0.0),
        "ehs": ehs,
        "material_cost": material_cost,
        "process_cost": process_cost,
        "total_unit_cost": total_unit_cost,
        "process_cost_breakdown": process_cost_breakdown,
    }
    # BOM 名称：优先使用前端传入，否则按 route_id 生成（如 "BOM - 路径1"）
    rid_num = req.route_id.strip().lstrip("Rr") if req.route_id else "1"
    bom_name = req.name or f"BOM - 路径{rid_num or '1'}"

    # 5. 事务性创建 BomScheme 与 ProcessScheme
    from .experiment.bom_store import BomScheme
    from .experiment.process_scheme_store import ProcessScheme

    bom = BomScheme(
        candidate_id=candidate_id,
        task_id=cand.task_id or "",
        formulation=formulation,
        process_route=process_route,
        test_protocol={},
        version="v1",
        status="draft",
        created_by=req.created_by,
        source_route_id=req.route_id,
        source_synthesis_task_id=req.synthesis_task_id,
        name=bom_name,
    )
    try:
        created_bom = app.state.bom_store.create(bom)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    scheme = ProcessScheme(
        candidate_id=candidate_id,
        bom_id=created_bom.bom_id,
        source_route_id=req.route_id,
        source_synthesis_task_id=req.synthesis_task_id,
        steps=bop_list,
        raw_materials=bom_list,
        metadata={
            "feasibility_score": route.get("feasibility_score", 0.0),
            "confidence": route.get("confidence", 0.0),
            "target_smiles": route.get("target_smiles", ""),
            "ehs": ehs,
            "material_cost": material_cost,
            "process_cost": process_cost,
            "total_unit_cost": total_unit_cost,
            "process_cost_breakdown": process_cost_breakdown,
            "route_reactants": route_reactants,
            "agent_id": "builtin_industrialization",
        },
        created_by=req.created_by,
    )
    try:
        created_scheme = app.state.process_scheme_store.create(scheme)
        # 回填 BomScheme.process_id
        created_bom.process_id = created_scheme.process_id
        app.state.bom_store.update(created_bom)
    except Exception as exc:
        # 回滚：删除已创建的 BOM（ProcessScheme 未创建成功）
        logger.exception("创建 ProcessScheme 失败，回滚 BOM %s: %s", created_bom.bom_id, exc)
        try:
            app.state.bom_store.delete(created_bom.bom_id)
        except Exception:  # noqa: BLE001
            logger.warning("回滚 BOM %s 失败", created_bom.bom_id)
        raise HTTPException(
            status_code=500,
            detail=f"创建工艺方案失败：{exc}",
        ) from exc

    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    ai_meta = {
        "input_snapshot_hash": input_snapshot_hash,
        "model_version": "internlm-v1",
        "generated_at": _dt.now(timezone.utc).isoformat(),
    }

    return {
        "bom": created_bom.model_dump(),
        "process_scheme": created_scheme.model_dump(),
        "ai_meta": ai_meta,
    }


@app.post("/candidates/{candidate_id}/bom-from-process",
          dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_bom_from_process(candidate_id: str, req: BomFromProcessRequest):
    """从已确认的工艺方案生成配方（BOM）（打通 深化→配方 链路）。

    流程：
    1. 校验候选存在，且工艺方案存在、状态为 confirmed
    2. 从工艺方案的候选路线中选定一条（指定 route_id 或取可行性最高者）
    3. 调用 FormulaAgent（builtin_industrialization）生成完整 BOM/BOP/成本/EHS
    4. 跨体系一致性校验（复用领域包规则）
    5. 创建 BomScheme 并回填 process_id 关联既有工艺方案
    """
    # 1. 校验候选与工艺方案
    cand = app.state.candidate_store.get(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")
    scheme = app.state.process_scheme_store.get(req.process_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail=f"工艺方案 {req.process_id} 不存在")
    if scheme.candidate_id != candidate_id:
        raise HTTPException(
            status_code=400,
            detail=f"工艺方案 {req.process_id} 不属于候选材料 {candidate_id}",
        )
    if scheme.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=f"工艺方案状态为 {scheme.status}，须确认（confirmed）后才能生成配方",
        )

    # 2. 选定工艺路线：优先指定 route_id，否则取可行性最高者
    routes = scheme.routes or []
    if not routes:
        raise HTTPException(status_code=400, detail="工艺方案中无候选路线，无法生成配方")
    route = None
    if req.route_id:
        route, _idx = _match_route_by_id(routes, req.route_id)
        if route is None:
            raise HTTPException(
                status_code=400,
                detail=f"工艺方案 {req.process_id} 中未匹配到 route_id={req.route_id}",
            )
    else:
        route = max(routes, key=lambda r: float(r.get("feasibility_score") or 0.0))

    # 3. 调用 FormulaAgent 生成完整 BOM/BOP/成本/EHS
    target_material = {
        "candidate": cand.name or cand.formula or candidate_id,
        "target_property": _resolve_target_property(),
    }
    input_snapshot_hash = _compute_input_snapshot({
        "candidate_id": candidate_id,
        "process_id": req.process_id,
        "route_id": route.get("route_id", ""),
        "quantity": req.quantity or 1.0,
        "name": req.name,
    })
    try:
        recipe_result = agent._handle_design_formula(
            target_material=target_material,
            quantity=float(req.quantity or 1.0),
            cand_type=cand.candidate_type or "",
        )
    except Exception as exc:
        logger.exception("从工艺方案生成 BOM 失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"调用配方工艺 agent 失败：{exc}",
        ) from exc
    if "error" in recipe_result:
        raise HTTPException(
            status_code=500,
            detail=f"配方工艺 agent 返回错误：{recipe_result['error']}",
        )

    bom_list = recipe_result.get("bom") or []
    bop_list = recipe_result.get("bop") or []
    ehs = recipe_result.get("ehs") or {}

    # 4. 跨体系一致性校验（复用领域包规则）
    _cons_rules = {}
    _fa = getattr(agent, "formula_agent", None)
    _dp = getattr(_fa, "domain_pack", None) if _fa else None
    if isinstance(_dp, dict):
        _cons_rules = _dp.get("consistency") or {}
    _crossed = _assert_bom_system_consistency(
        cand.candidate_type, cand.name or cand.formula or "", bom_list, _cons_rules
    )
    if _crossed:
        raise HTTPException(
            status_code=400,
            detail=(
                "BOM 物料与目标材料体系不一致，已阻断生成："
                f"目标体系为「{cand.candidate_type or cand.name or '未知'}」，"
                f"但 BOM 含跨体系物料 {sorted(set(_crossed))}"
            ),
        )
    material_cost = float(recipe_result.get("material_cost") or 0.0)
    process_cost = float(recipe_result.get("process_cost") or 0.0)
    total_unit_cost = float(recipe_result.get("total_unit_cost") or 0.0)
    process_cost_breakdown = recipe_result.get("process_cost_breakdown") or []

    # 合成路径原料（工艺路线 reactants）合并进 BOM 追溯
    route_reactants = []
    for s in (route.get("steps") or []):
        for r in (s.get("reactants") or []):
            if r and r not in route_reactants:
                route_reactants.append(r)

    formulation = {
        "materials": bom_list,
        "route_reactants": route_reactants,
        "target_smiles": route.get("target_smiles", ""),
    }
    process_route = {
        "steps": bop_list,
        "route_steps": [s for s in (scheme.steps or [])],
        "feasibility_score": route.get("feasibility_score", 0.0),
        "confidence": route.get("confidence", 0.0),
        "ehs": ehs,
        "material_cost": material_cost,
        "process_cost": process_cost,
        "total_unit_cost": total_unit_cost,
        "process_cost_breakdown": process_cost_breakdown,
    }
    rid_num = (route.get("route_id") or "").strip().lstrip("Rr") or "1"
    bom_name = req.name or f"配方 - 工艺方案{rid_num or '1'}"

    # 5. 创建 BomScheme 并回填 process_id（关联既有工艺方案）
    from .experiment.bom_store import BomScheme

    bom = BomScheme(
        candidate_id=candidate_id,
        task_id=cand.task_id or "",
        formulation=formulation,
        process_route=process_route,
        test_protocol={},
        version="v1",
        status="draft",
        created_by=req.created_by,
        source_route_id=route.get("route_id", ""),
        source_synthesis_task_id=scheme.source_synthesis_task_id or "",
        process_id=scheme.process_id,
        name=bom_name,
    )
    try:
        created_bom = app.state.bom_store.create(bom)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    from datetime import datetime as _dt2, timezone
    ai_meta = {
        "input_snapshot_hash": input_snapshot_hash,
        "model_version": "internlm-v1",
        "generated_at": _dt2.now(timezone.utc).isoformat(),
    }
    return {
        "bom": created_bom.model_dump(),
        "process_scheme": scheme.model_dump(),
        "ai_meta": ai_meta,
    }


@app.get("/bom/{bom_id}/process")
async def get_bom_process(bom_id: str):
    """获取 BOM 关联的工艺方案（业务链路：BOM 1 ↔ 1 工艺方案，0021 新增）。"""
    scheme = app.state.process_scheme_store.get_by_bom(bom_id)
    return {
        "bom_id": bom_id,
        "process_scheme": scheme.model_dump() if scheme else None,
    }


@app.get("/orders/{order_id}/test-tasks")
async def list_order_test_tasks(order_id: str):
    """查询实验任务单下的所有测试任务（业务链路：实验任务 1 → N 测试任务）。"""
    tasks = app.state.test_task_store.list_by_order(order_id)
    return {
        "order_id": order_id,
        "test_tasks": [t.model_dump() for t in tasks],
        "count": len(tasks),
    }


class TestTaskCreateRequest(BaseModel):
    """创建测试任务请求。"""
    bom_id: str = ""
    test_type: str = ""
    test_method: str = ""
    priority: str = "P2"
    assignee: str = ""
    notes: str = ""
    planned_start: str | None = None
    planned_end: str | None = None


@app.post("/orders/{order_id}/test-tasks", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_order_test_task(order_id: str, req: TestTaskCreateRequest):
    """为实验任务单创建测试任务（业务链路：实验任务 1 → N 测试任务）。

    Raises:
        404: 实验任务单不存在
    """
    # 校验实验任务单存在
    order = agent.experiment_controller._store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"实验任务单 {order_id} 不存在")

    from .experiment.test_task_store import TestTask
    tt = TestTask(
        order_id=order_id,
        bom_id=req.bom_id,
        test_type=req.test_type,
        test_method=_normalize_test_method(req.test_method),
        priority=req.priority,
        assignee=req.assignee,
        notes=req.notes,
        planned_start=req.planned_start,
        planned_end=req.planned_end,
    )
    created = app.state.test_task_store.create(tt)
    return created.model_dump()


class TestTaskUpdateRequest(BaseModel):
    """更新测试任务请求。"""
    bom_id: str | None = None
    test_type: str | None = None
    test_method: str | None = None
    priority: str | None = None
    assignee: str | None = None
    status: str | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    notes: str | None = None


@app.put("/test-tasks/{test_task_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_test_task(test_task_id: str, req: TestTaskUpdateRequest):
    """更新测试任务全字段（status 单独走 update_status 接口更佳）。"""
    existing = app.state.test_task_store.get(test_task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"测试任务 {test_task_id} 不存在")

    if req.bom_id is not None:
        existing.bom_id = req.bom_id
    if req.test_type is not None:
        existing.test_type = req.test_type
    if req.test_method is not None:
        existing.test_method = _normalize_test_method(req.test_method)
    if req.priority is not None:
        existing.priority = req.priority
    if req.assignee is not None:
        existing.assignee = req.assignee
    if req.status is not None:
        existing.status = req.status
    if req.planned_start is not None:
        existing.planned_start = req.planned_start
    if req.planned_end is not None:
        existing.planned_end = req.planned_end
    if req.started_at is not None:
        existing.started_at = req.started_at
    if req.completed_at is not None:
        existing.completed_at = req.completed_at
    if req.notes is not None:
        existing.notes = req.notes

    updated = app.state.test_task_store.update(existing)
    return updated.model_dump()


class TestTaskStatusUpdateRequest(BaseModel):
    """更新测试任务状态请求。"""
    status: str
    started_at: str | None = None
    completed_at: str | None = None


@app.post("/test-tasks/{test_task_id}/status", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_test_task_status(test_task_id: str, req: TestTaskStatusUpdateRequest):
    """仅更新测试任务状态（自动填充 started_at / completed_at）。"""
    from .experiment.experiment_controller import IllegalStateTransitionError
    try:
        ok = app.state.test_task_store.update_status(
            test_task_id, req.status, req.started_at, req.completed_at
        )
    except IllegalStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail=f"测试任务 {test_task_id} 不存在")
    return {"test_task_id": test_task_id, "status": req.status}


@app.post("/synthesis/check", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def check_synthesis(req: SynthesisRequest):
    score = agent.check_synthesis(req.smiles)
    return {"smiles": req.smiles, "feasibility_score": score}


@app.post("/verify", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def verify_material(req: VerifyRequest):
    result = agent.verify(req.smiles, req.property_name)
    return result.model_dump()


@app.post("/experiments/query", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def query_experiments(req: ExperimentQueryRequest):
    records = agent.query_experiments(
        req.formula, req.experiment_type, req.project_id, req.sample_id,
        req.batch_id, req.source_type, req.operator, req.order_id,
        req.date_from, req.date_to,
    )
    return {"records": [r.model_dump() for r in records], "count": len(records)}


class ExperimentRecordUpdate(BaseModel):
    """实验记录可更新字段。"""
    sample_id: str | None = None
    formula: str | None = None
    experiment_type: str | None = None
    conditions: dict | None = None
    measured_values: dict | None = None
    source: str | None = None
    batch_id: str | None = None
    operator: str | None = None
    created_at: str | None = None
    order_id: str | None = None
    candidate_id: str | None = None


@app.put("/experiments/{record_id}")
async def update_experiment_record(
    record_id: str,
    req: ExperimentRecordUpdate,
    user: User | None = Depends(require_role(UserRole.RESEARCHER)),
):
    """更新指定实验记录。P1-105：补全编辑弹窗字段后的写入端点。"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="无更新字段")
    ok = agent.middleware.update_record(record_id, updates)
    if not ok:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    return {"record_id": record_id, "updated": True}


@app.delete("/experiments/{record_id}")
async def delete_experiment_record(
    record_id: str,
    user: User | None = Depends(require_role(UserRole.RESEARCHER)),
):
    """删除指定实验记录。"""
    ok = agent.middleware.delete_record(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="实验记录不存在")
    return {"record_id": record_id, "deleted": True}


@app.get("/mcp/manifest")
async def mcp_manifest():
    return agent.get_mcp_manifest()


@app.get("/tools")
async def list_tools(
    keyword: str | None = Query(None, description="按工具名称/描述模糊搜索（大小写不敏感）"),
    category: str | None = Query(None, description="按分类筛选，对应 tool.source（local/scp/internlm）"),
):
    """工具清单（支持按名称模糊搜索与按分类筛选）。

    category 对应 MCPTool.source 字段：local（本地）/ scp / internlm。
    """
    tools = agent.tools.list_tools()
    if keyword:
        kw = keyword.lower()
        tools = [t for t in tools
                 if kw in t.name.lower() or kw in (t.description or "").lower()]
    if category:
        tools = [t for t in tools if t.source == category]
    return {"tools": [t.model_dump() for t in tools]}


class SCPBindingUpdateRequest(BaseModel):
    enabled: bool | None = None
    risk_level: RiskLevel | None = None
    timeout_seconds: int | None = None


@app.get("/tools/scp-bindings", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_scp_bindings():
    """返回 SCPCatalog 中所有工具绑定（含内置 SCP 与默认 SCP server 绑定）。"""
    if _scp_catalog is None:
        raise HTTPException(status_code=503, detail="SCP 目录未初始化，请启用 SCP_ENABLED=true")
    bindings = _scp_catalog.list_all()
    return {
        "bindings": [b.model_dump() for b in bindings],
        "count": len(bindings),
    }


@app.put("/tools/scp-bindings/{internal_name}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_scp_binding(internal_name: str, req: SCPBindingUpdateRequest):
    """更新指定 SCP 工具绑定的启用状态、风险等级或超时时间。"""
    global _scp_client_pool
    if _scp_catalog is None:
        raise HTTPException(status_code=503, detail="SCP 目录未初始化")

    binding = _scp_catalog.get(internal_name)
    if binding is None:
        raise HTTPException(status_code=404, detail=f"工具绑定 '{internal_name}' 不存在")

    if req.enabled is not None:
        _scp_catalog.set_enabled(internal_name, req.enabled)
        agent.config.scp.binding_enabled[internal_name] = req.enabled

    update_kwargs = {}
    if req.risk_level is not None:
        update_kwargs["risk_level"] = req.risk_level
    if req.timeout_seconds is not None:
        update_kwargs["timeout_seconds"] = req.timeout_seconds
    if update_kwargs:
        _scp_catalog.update(internal_name, **update_kwargs)

    try:
        save_config_to_env(agent.config)
    except Exception as exc:
        # 持久化失败不应阻断内存更新
        logger.warning("save_config_to_env failed for SCP binding %s: %s", internal_name, exc)

    # 启用状态变化后重新注册 SCP 工具
    if _scp_client_pool is not None and _scp_audit_store is not None and req.enabled is not None:
        agent.tools.register_scp_tools(
            _scp_catalog, _scp_client_pool, _scp_policy,
            _scp_adapters, _scp_audit_store,
        )

    return _scp_catalog.get(internal_name).model_dump()


# --- SKILL 端点 ---

@app.get("/tools/skills", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_skills():
    """返回所有已注册的 SKILL（声明式组合能力）。"""
    if _skill_catalog is None:
        raise HTTPException(status_code=503, detail="SKILL 目录未初始化")
    skills = _skill_catalog.list_all()
    return {
        "skills": [s.model_dump() for s in skills],
        "count": len(skills),
    }


class SkillTestRequest(BaseModel):
    skill_id: str
    arguments: dict = Field(default_factory=dict)
    ecml_step: int | None = None


@app.post("/tools/skills/test", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def test_skill(req: SkillTestRequest):
    """自检一个 SKILL：使用 test_input 或传入的 arguments 执行 pipeline。

    可选 ecml_step 参数用于触发门禁检查；不传则跳过门禁（管理员自检场景）。
    """
    if _skill_catalog is None or _skill_executor is None:
        raise HTTPException(status_code=503, detail="SKILL 基础设施未初始化")
    skill = _skill_catalog.get(req.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"SKILL '{req.skill_id}' 不存在")
    if not skill.enabled:
        raise HTTPException(status_code=400, detail=f"SKILL '{req.skill_id}' 未启用")
    # 优先使用传入参数，回退到 test_input
    user_input = req.arguments if req.arguments else skill.test_input
    result = await _skill_executor.execute(skill, user_input, ecml_step=req.ecml_step)
    return result




# 本地工具的最小有效自测负载
_TOOL_TEST_ARGS: dict[str, dict] = {
    "route_material": {"material_input": {"name": "LiCoO2"}},
    # 空 elements：跳过 InternLM 元素解析（最慢环节），仅验证 MP/GNoME/本地库连通性
    "generate_crystal_candidates": {"elements": [], "num_candidates": 1},
    "generate_polymer_candidates": {"num_candidates": 1},
    "predict_crystal_properties": {"features": {"formula": "LiCoO2"}, "property_name": "band_gap"},
    "predict_polymer_properties": {"features": {"smiles": "CC(=O)O"}, "property_name": "tensile_strength"},
    "check_synthesis_feasibility": {"smiles": "CCO"},
    "verify_dft": {"smiles": "CCO", "property_name": "total_energy"},
    "get_experiment_results": {},
    # 空 callback_url：handler 会跳过实际订阅，仅验证调用链路且无订阅副作用
    "subscribe_experiment_updates": {"callback_url": ""},
    "design_formula": {},
}

# SCP 智能体工具的自测查询：schema 中 query 类字符串参数填此值
_SCP_TEST_QUERIES: dict[str, str] = {
    "scp_scitool_chem": "查询乙醇（SMILES: CCO）的分子量与 logP",
    "scp_scigraph_material": "查询 PA6 的基本材料信息",
    "scp_scitool_mat": "查询玻纤增强 PA6 的拉伸强度性能",
    "scp_chem_reaction": "计算 25°C 下 1 mol/L NaCl 水溶液的物质的量浓度",
    "scp_origene_pubchem": "检索化合物 ethanol 的 PubChem 信息",
    "scp_origene_chembl": "检索 aspirin 的 ChEMBL 生物活性信息",
    "scp_materials_mechanics": "计算软木（比重 0.20）的材料密度",
}

_QUERY_PARAM_HINTS = ("query", "task", "question", "prompt", "input", "instruction", "request", "text", "message")


def _sample_value_for_schema(param_name: str, schema: dict, tool_name: str):
    """按 JSON Schema 为参数生成最小有效示例值（用于 SCP 工具自测）。"""
    if not isinstance(schema, dict):
        schema = {}
    if schema.get("default") is not None:
        return schema["default"]
    ptype = schema.get("type", "string")
    if ptype == "string":
        lname = param_name.lower()
        if any(h in lname for h in _QUERY_PARAM_HINTS):
            return _SCP_TEST_QUERIES.get(tool_name, "ping")
        if "smiles" in lname:
            return "CCO"
        if "formula" in lname or "composition" in lname:
            return "LiCoO2"
        if "name" in lname or "keyword" in lname or "compound" in lname:
            return "ethanol"
        return "test"
    if ptype == "integer":
        return 1
    if ptype == "number":
        return 1.0
    if ptype == "boolean":
        return True
    if ptype == "array":
        return []
    if ptype == "object":
        return {}
    return "test"


# SCP 服务器级绑定的首选自测工具：均为已实测可用的只读工具（2026-07 探测验证）
# internal_name -> (remote_tool_name, arguments)
_SCP_TEST_TOOLS: dict[str, tuple[str, dict]] = {
    # 7 个 server 级绑定
    "scp_scitool_chem": ("SMILESToWeight", {"smiles": "CCO"}),
    "scp_scigraph_material": ("query_cypher", {"cypher": "MATCH (n) RETURN count(n) AS c", "limit": 1}),
    "scp_scitool_mat": ("SMILESToCAS", {"smiles": "CCO"}),
    "scp_chem_reaction": ("calculate_pH_from_pOH", {"pOH": 7}),
    "scp_origene_pubchem": ("search_pubchem_by_name", {"name": "ethanol"}),
    "scp_origene_chembl": ("search_assay", {"query_str": "aspirin"}),
    "scp_materials_mechanics": ("calculate_material_density", {"specific_gravity": 0.20, "water_density_kg_m3": 1000}),
    # 4 个能力级绑定（映射到对应 server 的已知可用工具）
    "scp_molecule_descriptors": ("SMILESToWeight", {"smiles": "CCO"}),
    "scp_toxicity_assessment": ("SMILESToWeight", {"smiles": "CCO"}),
    "scp_literature_search": ("search_pubchem_by_name", {"name": "ethanol"}),
    "scp_material_transform": ("SMILESToCAS", {"smiles": "CCO"}),
    # 4 个新增 server 级绑定（材料专题网页完整覆盖）
    "scp_unit_conversion": ("convert_length_to_meters", {"length_km": 1}),
    "scp_data_analysis": ("calculate_absolute_error", {"measured_value": 10.2, "true_value": 10.0}),
    "scp_intern_agent": ("ChemicalStructureAnalyzer", {"compound_name": "ethanol"}),
    "scp_scigraph": ("query_cypher", {"kg_name": "ElementKG", "cypher": "MATCH (n) RETURN count(n) AS c", "limit": 1}),
}


async def _build_scp_test_args(tool_name: str) -> tuple[str, dict]:
    """为 SCP 工具自测选择远端工具并按其 inputSchema 构造有效参数。

    返回 (remote_tool_name, args)。选择顺序：
    1. _SCP_TEST_TOOLS 中已验证的首选工具（参数固定有效）；
    2. 远端 tools/list 中 schema 与绑定 remote_tool_name 匹配的工具；
    3. 远端 tools/list 中第一个带 properties 的工具，按 schema 采样必填参数；
    4. 回退：绑定 remote_tool_name + 通用 query 参数。
    """
    if _scp_catalog is None or _scp_client_pool is None:
        return tool_name, {}
    binding = _scp_catalog.get(tool_name)
    if binding is None:
        return tool_name, {}
    # 无 server 映射的能力级绑定（如 scp_protocol_draft）不能走 SCP 远程测试
    if not binding.server_id or not binding.remote_tool_name:
        raise ValueError(
            f"工具 '{tool_name}' 未绑定 SCP 远端服务器（server_id 为空），"
            "无法执行远程自测。请先在能力契约页面为其配置 server 映射。"
        )
    preferred = _SCP_TEST_TOOLS.get(tool_name)
    if preferred is not None:
        return preferred[0], dict(preferred[1])
    try:
        remote_tools = await _scp_client_pool.list_tools(binding.server_id, binding.server_url or None)
    except Exception as e:
        # schema 拉取失败不阻断测试：回退到通用 query 参数
        logger.warning("SCP list_tools failed for %s: %s", tool_name, e)
        remote_tools = []
    chosen_name = ""
    chosen_schema: dict = {}
    fallback_name = ""
    fallback_schema: dict = {}
    for rt in remote_tools or []:
        if not isinstance(rt, dict) or rt.get("_error"):
            continue
        s = rt.get("inputSchema") or rt.get("input_schema") or {}
        if not isinstance(s, dict):
            s = {}
        if rt.get("name") == binding.remote_tool_name:
            chosen_name = rt["name"]
            chosen_schema = s
            break
        if not fallback_name and s.get("properties"):
            fallback_name = rt.get("name", "")
            fallback_schema = s
    if not chosen_name:
        chosen_name, chosen_schema = fallback_name, fallback_schema
    if chosen_name:
        props = chosen_schema.get("properties", {})
        args: dict = {}
        for pname in (chosen_schema.get("required", []) or []):
            args[pname] = _sample_value_for_schema(pname, props.get(pname, {}), tool_name)
        # 无 required 时，为 query 类可选参数填值
        if not args:
            for pname, pschema in props.items():
                if any(h in pname.lower() for h in _QUERY_PARAM_HINTS):
                    args[pname] = _sample_value_for_schema(pname, pschema, tool_name)
        return chosen_name, args
    # schema 获取失败或无可用信息时退回通用 query 参数
    return binding.remote_tool_name, {"query": _SCP_TEST_QUERIES.get(tool_name, "ping")}


@app.post("/tools/{tool_name}/test", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def test_tool_availability(tool_name: str, request: Request):
    """自测指定工具：构造最小有效参数并真实调用一次，返回可用状态。

    - 本地工具：使用内置最小负载（_TOOL_TEST_ARGS）。
    - SCP 工具：先拉取远端 tools/list 的 inputSchema，按规范构造参数，
      再经 SCPToolProxy 完整链路（授权→校验→调用→归一化→审计）调用。
    返回 {tool, available, latency_ms, arguments, message, result}。
    """
    tool = agent.tools.get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_name}' 未注册")

    start = time.monotonic()
    args: dict = {}
    remote_tool = ""
    # 自测目的是验证工具的物理连通性，不是验证当前用户业务权限；
    # C/D 级 SCP 工具的权限校验在真实业务调用路径中执行。
    # 此处统一用 admin 角色发起自测，避免非 admin 用户看到"不可用"的误导结果。
    test_role = "admin"
    try:
        if tool.source == "scp":
            remote_tool, args = await _build_scp_test_args(tool_name)
            args["_user_role"] = test_role
            args["_remote_tool_name"] = remote_tool
            result = await agent.tools.execute_async(tool_name, args)
        else:
            args = dict(_TOOL_TEST_ARGS.get(tool_name, {}))
            # 同步 handler 可能发起网络/LLM 调用，放到线程中执行避免阻塞事件循环
            result = await asyncio.to_thread(agent.tools.execute, tool_name, **args)
            if asyncio.iscoroutine(result):
                result = await result
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning("tool test failed: %s error=%s", tool_name, e)
        return {
            "tool": tool_name, "available": False, "latency_ms": latency_ms,
            "arguments": {k: v for k, v in args.items() if not k.startswith("_")},
            "message": str(e), "result": None,
        }

    latency_ms = int((time.monotonic() - start) * 1000)
    available = True
    message = "调用成功"
    # blocked：SCP 策略拒绝（如 C 级工具需管理员），同样视为不可用
    if isinstance(result, dict) and (result.get("status") in ("error", "blocked") or result.get("error")):
        available = False
        message = str(result.get("message") or result.get("error") or "工具返回错误")
    # C 级 SCP 工具连通性正常但实际调用需 admin 权限，在 message 中标注
    if available and tool.source == "scp" and _scp_catalog is not None:
        binding = _scp_catalog.get(tool_name)
        if binding is not None and binding.risk_level == RiskLevel.C:
            message = "调用成功（C 级工具，实际调用需 admin 权限）"
    return {
        "tool": tool_name, "available": available, "latency_ms": latency_ms,
        "remote_tool": remote_tool or None,
        "arguments": {k: v for k, v in args.items() if not k.startswith("_")},
        "message": message, "result": result,
    }


# ── 智能体工具调用端点（决策 7-A：业务活动通过 AgentProxy 调用工具） ──

class AgentToolInvokeRequest(BaseModel):
    """通过智能体调用工具请求。

    设计理念：业务活动/前端 UI 不直接调用服务，而是指定匹配的智能体与能力，
    由 AgentProxy 完成 智能体→主工具选择→白名单→执行 的完整链路。
    """
    agent_id: str = Field(..., description="智能体 ID，如 builtin_battery_oracle / builtin_synthesis_planner")
    capability: str = Field(..., description="能力标签，如 sci_mpa / sci_synthesis_planning")
    params: dict = Field(default_factory=dict, description="工具入参（project_id + 服务参数）")
    activity_id: str = Field(default="", description="业务活动 ID（可选）")
    timeout: float = Field(default=180.0, description="超时秒数")


@app.post("/v1/agent-tools/invoke", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def invoke_agent_tool(req: AgentToolInvokeRequest):
    """通过匹配的智能体调用工具（含 12 个原生科学服务工具 sci_*）。

    返回 AgentInvocationResult：
    {invocation_id, agent_id, tool_id, capability, success, used_fallback,
     fallback_from, sync_mode, result, error, duration_ms}
    """
    if _agent_proxy is None:
        raise HTTPException(status_code=503, detail="AgentProxy 未初始化")
    _init_hybrid_stack()  # 确保 CapabilityRouter 已注入 AgentProxy（sci_* 能力需经其路由）
    from dataclasses import asdict
    try:
        result = await asyncio.to_thread(
            _agent_proxy.invoke_tool,
            req.agent_id,
            req.capability,
            req.params,
            req.activity_id,
            req.timeout,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能体工具调用异常: {e}")
    return asdict(result)


@app.get("/v1/agent-tools/agents/{agent_id}/tools", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def list_agent_tools(agent_id: str):
    """返回指定智能体可调用的工具列表（能力关联 + 白名单）。"""
    if _agent_proxy is None:
        raise HTTPException(status_code=503, detail="AgentProxy 未初始化")
    tool_ids = _agent_proxy.get_agent_tool_whitelist(agent_id)
    store = _activity_mapping_store
    tools = []
    if store is not None:
        for tid in tool_ids:
            reg = store.get_tool_registration(tid)
            if reg:
                tools.append(reg.model_dump())
    return {"agent_id": agent_id, "tools": tools, "total": len(tools)}


# --- New endpoints for progressive UI ---

@app.get("/stats")
async def get_stats():
    """Real stats for Dashboard（P0-1 统一统计口径）.

    所有指标与其二级页面数据源保持强一致：
    - candidates: 全局候选库计数（candidate_store），附本周新增
    - experiments: 实验任务单（experiment_orders），附进行中/待审批
    - iterations: ECML 运行计数，排除 test 垃圾数据（与迭代历史"正式"视图同口径）
    - routes: 合成路线累计生成数（synthesis_tasks 持久化），附 ASKCOS 服务可用率
    """
    from datetime import datetime, timezone
    try:
        # --- ECML 运行：排除 test 数据，与二级页面"正式"视图口径一致 ---
        iterations = 0
        iterations_active = 0
        iterations_completed_30d = 0
        iterations_test_total = 0
        if hasattr(agent, "ecml") and agent.ecml is not None and agent.ecml.state_store is not None:
            try:
                run_stats = agent.ecml.state_store.get_run_stats()
                iterations = run_stats["total"]
                iterations_active = run_stats["active"]
                iterations_completed_30d = run_stats["completed_30d"]
                iterations_test_total = run_stats["test_total"]
            except Exception as e:
                logger.debug("dashboard ecml stats subquery failed: %s", e, exc_info=True)
        # --- 候选材料 ---
        candidates = 0
        candidates_new_this_week = 0
        candidate_store = getattr(app.state, "candidate_store", None)
        if candidate_store is not None:
            try:
                all_candidates = candidate_store.list_all()
                candidates = len(all_candidates)
                now_dt = datetime.now(timezone.utc)
                for c in all_candidates:
                    try:
                        created = datetime.fromisoformat((c.created_at or "").replace("Z", "+00:00"))
                        if (now_dt - created).days < 7:
                            candidates_new_this_week += 1
                    except (ValueError, AttributeError):
                        continue
            except Exception as e:
                logger.debug("dashboard candidates subquery failed: %s", e, exc_info=True)
        # --- 实验任务单：与 /dashboard/overview 一致，避免 middleware 500 截断导致不一致 ---
        experiments = 0
        experiments_active = 0
        experiments_pending_approval = 0
        try:
            orders = agent.experiment_controller._store.list_orders()
            experiments = len(orders)
            for o in orders:
                if o.status == "PENDING_APPROVAL":
                    experiments_pending_approval += 1
                if o.status not in ("COMPLETED", "CANCELLED"):
                    experiments_active += 1
        except Exception as e:
            logger.debug("dashboard experiments subquery failed: %s", e, exc_info=True)
        # --- 合成路线：来自 synthesis_tasks 持久化（每次尝试均记录，含失败） ---
        routes = 0
        synthesis_success_rate = None
        try:
            syn_stats = _get_synthesis_task_store().get_stats()
            routes = syn_stats["routes_generated"]
            synthesis_success_rate = syn_stats["success_rate"]
        except Exception as e:
            logger.debug("dashboard synthesis stats subquery failed: %s", e, exc_info=True)
        return {
            "candidates": candidates,
            "candidates_new_this_week": candidates_new_this_week,
            "experiments": experiments,
            "experiments_active": experiments_active,
            "experiments_pending_approval": experiments_pending_approval,
            "iterations": iterations,
            "iterations_active": iterations_active,
            "iterations_completed_30d": iterations_completed_30d,
            "iterations_test_total": iterations_test_total,
            "routes": routes,
            "synthesis_success_rate": synthesis_success_rate,
        }
    except Exception as e:
        return {"candidates": 0, "experiments": 0, "iterations": 0, "routes": 0, "error": str(e)}


# 评测修复 P2-001（synthesis）：同步合成规划端点的超时阈值（秒）。
# 超时或 ASKCOS 不可用时自动回退为异步任务（202 + task_id），不再 503 中断流程。
_SYNTHESIS_SYNC_TIMEOUT_SECONDS = float(os.getenv("SYNTHESIS_SYNC_TIMEOUT", "25"))


@app.post("/synthesis/plan", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
@require_capability("synthesis_planning_askcos_v1")
async def plan_synthesis(req: SynthesisPlanRequest):
    """Real multi-step synthesis route planning."""
    from .synthesis.synthesis_planner import SynthesisServiceError
    from fastapi.responses import JSONResponse
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "smiles": req.smiles,
        "max_depth": req.max_depth,
        "num_routes": req.num_routes,
    })

    # 评测修复 P2-001（synthesis）：同步端点超时或服务不可用时，
    # 自动回退为异步任务（202 + task_id），前端通过 /synthesis/tasks/{id} 轮询，
    # 不再直接 503 中断业务流程
    async def _fallback_to_async(reason: str):
        store = _get_synthesis_task_store()
        task_id = store.create_task(
            req.smiles.strip(), num_routes=req.num_routes,
            scenario_id=req.scenario_id or "",
        )
        _spawn_background(_run_synthesis_task(
            task_id,
            smiles=req.smiles.strip(),
            num_routes=req.num_routes,
            scenario_id=req.scenario_id or "",
            engine_type="askcos",
        ))
        logger.warning("同步合成规划回退为异步任务 task_id=%s 原因: %s", task_id, reason)
        return JSONResponse(
            status_code=202,
            content={
                "task_id": task_id,
                "status": "pending",
                "fallback": "async",
                "reason": reason,
                "hint": "同步规划超时/服务暂不可用，已转为异步任务，请轮询 /synthesis/tasks/{task_id}",
            },
        )

    # 使用 async 版本以正确调用 ASKCOS，避免在事件循环中走本地回退
    try:
        routes = await asyncio.wait_for(
            agent.synthesis_planner.plan_synthesis_async(
                req.smiles, max_depth=req.max_depth, num_routes=req.num_routes,
            ),
            timeout=_SYNTHESIS_SYNC_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return await _fallback_to_async(
            f"sync timeout > {_SYNTHESIS_SYNC_TIMEOUT_SECONDS:.0f}s"
        )
    except SynthesisServiceError as e:
        return await _fallback_to_async(f"{e.service} unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    ai_meta = {
        "input_snapshot_hash": input_snapshot_hash,
        "model_version": "internlm-v1",
        "generated_at": _dt.now(timezone.utc).isoformat(),
    }
    if not routes:
        return {"routes": [], "count": 0, "ai_meta": ai_meta}
    return {
        "routes": [r.model_dump() for r in routes],
        "count": len(routes),
        "best_route": routes[0].model_dump(),
        "ai_meta": ai_meta,
    }


@app.post("/synthesis/plan/multi", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def plan_multiple_routes(req: MultiSynthesisPlanRequest):
    """E1.2: 多路径并行探索。并行调用 ASKCOS 不同搜索深度，返回去重后的多条候选路线。"""
    from .synthesis.synthesis_planner import SynthesisServiceError
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "smiles": req.smiles,
        "num_routes": req.num_routes,
    })
    try:
        routes = await agent.synthesis_planner.plan_multiple_routes(req.smiles, num_routes=req.num_routes)
    except SynthesisServiceError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "synthesis_service_unavailable",
                "message": str(e),
                "service": e.service,
                "hint": (
                    f"请检查 {e.service} 服务是否正在运行。"
                    "如使用 ASKCOS，确认 Docker 容器已启动且 MongoDB 中反应模板数据已导入。"
                ),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 补充 ai_meta（用于 AI 输出溯源）
    # planner 返回 {routes, count, best_route, ...} dict，端点补充 ai_meta 后直接透传，
    # 不能按 list 索引（否则 KeyError: 0）
    from datetime import datetime as _dt, timezone
    return {
        **routes,
        "ai_meta": {
            "input_snapshot_hash": input_snapshot_hash,
            "model_version": "internlm-v1",
            "generated_at": _dt.now(timezone.utc).isoformat(),
        },
    }


@app.get("/synthesis/network/{smiles}")
async def get_reaction_network(smiles: str):
    """E2.2: 反应机理网络解析。基于合成树提取中间体与反应节点，构建网络图数据。"""
    try:
        network = await agent.synthesis_planner.build_reaction_network(smiles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return network


@app.post("/synthesis/verify-dft", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def verify_route_with_dft(req: DFTVerifyRequest):
    """E3: DFT 可行性校验联动。对合成路线关键步骤进行 DFT 校验，回写置信度评分。"""
    if not req.route:
        raise HTTPException(status_code=400, detail="route 字段不能为空")
    try:
        result = await agent.synthesis_planner.verify_with_dft(req.route)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ===========================================================================
# 异步合成规划任务（P0：解决 ASKCOS 响应慢导致前端 15s 超时的问题）
# 提交后立即返回 task_id，后台执行，前端轮询；每次尝试均持久化用于统计。
# ===========================================================================

_SYNTHESIS_TASK_TIMEOUT = 600  # 后台任务整体超时（秒），InternLM 推理模型响应较慢，留 10 分钟


def _get_synthesis_task_store():
    """惰性初始化合成任务存储（测试环境下 startup 被覆盖时仍可用）。"""
    store = getattr(app.state, "synthesis_task_store", None)
    if store is None:
        from .synthesis.task_store import SynthesisTaskStore
        store = SynthesisTaskStore()
        app.state.synthesis_task_store = store
    return store


def _write_synthesis_feasibility_to_candidate(task_id: str, routes: list) -> None:
    """P3-B2：合成任务成功后，将最佳可行性分数回写候选材料。

    仅当合成任务关联了 candidate_id 时写入；写入失败仅记录日志，不阻断流程。
    分数仅持久化展示，不纳入多目标评分。
    """
    from datetime import datetime as _dt, timezone as _tz
    try:
        store = _get_synthesis_task_store()
        task = store.get_task(task_id)
        candidate_id = (task or {}).get("candidate_id", "")
        if not candidate_id:
            return
        best = max(routes, key=lambda r: float(r.get("feasibility_score") or 0.0)) if routes else None
        feasibility = {
            "feasibility_score": round(float(best.get("feasibility_score") or 0.0), 4) if best else 0.0,
            "route_id": (best or {}).get("route_id", ""),
            "task_id": task_id,
            "updated_at": _dt.now(_tz.utc).isoformat(),
        }
        # 走专用更新通道：save() 的 content-hash 去重会短路并丢弃对已存在候选的更新
        app.state.candidate_store.update_synthesis_feasibility(candidate_id, feasibility)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回写合成可行性到候选失败 task_id=%s: %s", task_id, exc)


async def _probe_askcos() -> bool:
    """快速探测逆合成服务可达性（3s 超时），用于快速失败与服务健康展示。"""
    import httpx
    base_url = agent.synthesis_planner.askcos_url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0), follow_redirects=True) as client:
            resp = await client.get(f"{base_url}/")
            return resp.status_code < 500
    except Exception as e:
        logger.debug("ASKCOS probe failed: %s", e)
        return False


def _extract_scp_text(raw: any) -> str:
    """从 MCP 结果中提取文本内容。"""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # 标准 MCP result: {"content": [{"type": "text", "text": "..."}]}
        content = raw.get("content") or []
        if isinstance(content, list):
            texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
            text = "\n".join(texts).strip()
            if text:
                return text
        # 某些 tool 直接返回字符串字段
        for key in ("text", "result", "output", "answer", "data"):
            val = raw.get(key)
            if isinstance(val, str):
                return val
            if val is not None:
                return json.dumps(val, ensure_ascii=False)
    return str(raw)


def _parse_scp_result_to_routes(raw, target_smiles: str, num_routes: int) -> list[dict]:
    """将 SCP 工具返回解析为标准 route 字典列表。

    由于不同远端 tool 返回格式未知，采用保守解析：
    - 若 MCP result.content[].text 包含 JSON list，尝试提取 reactants/score；
    - 否则构造一个包含原始返回信息的兜底 route。
    """
    from .synthesis.synthesis_planner import SynthesisRoute, RouteStep

    text = _extract_scp_text(raw)
    data = raw
    # 优先从文本中解析 JSON list / object
    if isinstance(text, str) and text:
        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
            else:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(text[start:end])
        except Exception:
            data = raw

    routes: list[SynthesisRoute] = []
    if isinstance(data, list):
        for item in data[:num_routes]:
            reactants = []
            score = 0.5
            if isinstance(item, dict):
                r = item.get("reactants") or item.get("reactant") or []
                if isinstance(r, str):
                    r = [r]
                reactants = [x for x in r if x]
                try:
                    score = float(item.get("score", 0.5))
                except (TypeError, ValueError):
                    score = 0.5
            elif isinstance(item, str):
                reactants = [item]
            steps = [
                RouteStep(
                    reaction_smiles=f"{r}>>{target_smiles}",
                    reactants=[r],
                    products=[target_smiles],
                    score=score,
                    reaction_type="retrosynthesis",
                )
                for r in reactants
            ]
            routes.append(SynthesisRoute(
                target_smiles=target_smiles,
                steps=steps,
                num_steps=len(steps),
                overall_score=score,
                feasibility_score=score,
                is_feasible=score > 0.3,
                confidence=score,
            ))

    if not routes:
        display_text = text or str(raw)
        if len(display_text) > 500:
            display_text = display_text[:500] + "..."
        routes.append(SynthesisRoute(
            target_smiles=target_smiles,
            steps=[RouteStep(
                reaction_smiles=f">> {target_smiles}",
                reactants=[],
                products=[target_smiles],
                conditions=f"SCP 返回：{display_text}",
                score=0.5,
                reaction_type="scp_fallback",
            )],
            num_steps=1,
            overall_score=0.5,
            feasibility_score=0.5,
            is_feasible=True,
            confidence=0.5,
        ))

    return [r.model_dump() for r in routes[:num_routes]]


async def _plan_with_scp(
    smiles: str,
    num_routes: int,
    material_type: str = "molecule",
    formula: str = "",
) -> dict:
    """使用 SCP SciToolAgent-Chem 进行逆合成/合成规划。

    流程：
    1. 获取 scp_scitool_chem 绑定；
    2. 列出远端工具，查找与 retro/synthesis/reaction 相关的工具；
    3. 按 inputSchema 构造参数并调用；
    4. 解析结果并转换为标准 route 格式返回。

    支持两种输入：
    - material_type="molecule"：用 smiles 作为查询输入
    - material_type="crystal"：用 formula 作为查询输入（SCP 工具通常按名称/化学式检索）
    """
    from .synthesis.synthesis_planner import SynthesisServiceError

    if _scp_catalog is None or _scp_client_pool is None:
        raise SynthesisServiceError(
            "SCP 客户端未初始化，请检查 .env 中 SCP_ENABLED=true 与 SCP_HUB_API_KEY 配置。",
            service="SCP",
        )

    binding = _scp_catalog.get("scp_scitool_chem")
    if binding is None or not binding.enabled:
        raise SynthesisServiceError(
            "SCP 科学工具 Chem 绑定未启用。",
            service="SCP",
        )

    # 根据材料类型选择查询输入：分子用 SMILES，晶体用化学式
    is_crystal = material_type == "crystal"
    query_input = formula.strip() if is_crystal else smiles.strip()
    if not query_input:
        raise SynthesisServiceError(
            f"SCP 调用缺少输入：{'化学式 formula' if is_crystal else 'SMILES'} 为空。",
            service="SCP",
        )

    server_id = binding.server_id
    server_url = binding.server_url
    tools = await _scp_client_pool.list_tools(server_id, server_url)
    tools = [t for t in tools if isinstance(t, dict) and not t.get("_error")]

    keywords = ["retro", "synthesis", "synthesi", "reaction", "route", "pathway", "retro_syn"]
    target_tool = None
    for t in tools:
        name = (t.get("name") or "").lower()
        desc = (t.get("description") or "").lower()
        if any(k in name or k in desc for k in keywords):
            target_tool = t
            break

    if target_tool is None:
        raise SynthesisServiceError(
            "SCP SciToolAgent-Chem 中未找到逆合成/合成规划相关工具（已尝试匹配 retro/synthesis/reaction/route 等关键词）。",
            service="SCP",
        )

    tool_name = target_tool.get("name")
    schema = target_tool.get("inputSchema") or target_tool.get("input_schema") or {}
    properties = schema.get("properties", {})
    required = schema.get("required", []) or []

    args: dict = {}
    for key in required:
        key_lower = key.lower()
        if "smiles" in key_lower:
            # 晶体路径无 SMILES，用 formula 兜底填入 smiles 字段
            args[key] = query_input
        elif any(k in key_lower for k in ["query", "input", "structure", "formula", "name"]):
            args[key] = query_input
        elif any(k in key_lower for k in ["num", "count", "routes", "depth", "max"]):
            args[key] = num_routes
        else:
            args[key] = ""
    for key in properties:
        if key in args:
            continue
        key_lower = key.lower()
        if "smiles" in key_lower:
            args[key] = query_input
        elif any(k in key_lower for k in ["query", "formula", "name"]):
            args[key] = query_input

    logger.info(
        "SCP synthesis call: server_id=%s tool=%s material_type=%s args=%s",
        server_id, tool_name, material_type, args,
    )
    result = await _scp_client_pool.call_tool(server_id, tool_name, args, server_url)
    if result.get("status") == "error":
        raise SynthesisServiceError(
            f"SCP 工具调用失败: {result.get('error', 'unknown error')}",
            service="SCP",
        )

    # call_tool 成功时返回字段为 data，对应 JSON-RPC result
    scp_data = result.get("data") or result
    routes = _parse_scp_result_to_routes(scp_data, query_input, num_routes)
    return {
        "routes": routes,
        "count": len(routes),
        "best_route": routes[0] if routes else None,
        "agent_info": {
            "agent_id": "scp_scitool_chem",
            "name": "SCP 科学工具",
            "role": "thinker",
            "model": "SciToolAgent-Chem",
            "capabilities": ["synthesis_evidence", "scp"],
        },
        "engine": "scp",
        "material_type": material_type,
    }


async def _run_synthesis_task(
    task_id: str,
    smiles: str,
    num_routes: int,
    scenario_id: str = "",
    engine_type: str = "askcos",
    agent_id: str = "",
    material_type: str = "molecule",
    formula: str = "",
    space_group: str = "",
):
    """后台执行合成规划：先探测服务可达性快速失败，再执行多路并行规划。

    engine_type 透传给 planner，支持运行时切换 ASKCOS/InternLM，不修改全局 config。
    agent_id 仅作日志标注，实际引擎调用由 planner 完成。
    material_type=crystal 时走 InternLM 固相合成路线，formula 必填。
    """
    from .synthesis.synthesis_planner import SynthesisServiceError
    store = _get_synthesis_task_store()
    store.mark_running(task_id)
    started = time.monotonic()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def _on_task_finished(status: str, error: str = "", route_count: int = 0):
        """P1-2：记录合成规划师 Agent 调用事件；连续失败超阈值时触发系统健康案件。"""
        actual_agent_id = agent_id or "builtin_synthesis_planner"
        if _agent_event_log is not None:
            try:
                _agent_event_log.log_event(
                    agent_id=actual_agent_id,
                    agent_name="合成路线规划师",
                    step="synthesis_plan",
                    input_summary={"smiles": smiles, "formula": formula, "material_type": material_type, "num_routes": num_routes, "task_id": task_id, "scenario_id": scenario_id or "", "engine_type": engine_type},
                    output_summary={"route_count": route_count, "error": error[:200]},
                    duration_ms=_elapsed_ms(),
                    status=status,
                )
            except Exception as e:
                logger.debug("Agent event log failed: %s", e)
        # P3-1：合成规划写入统一研发事件流水
        target_label = formula if material_type == "crystal" else smiles
        _log_research_event(
            event_type="synthesis",
            run_id=task_id,
            title=f"合成路径规划：{target_label}",
            summary=(f"生成路线 {route_count} 条" if status == "success"
                     else f"规划失败：{error[:100]}"),
            status="success" if status == "success" else "failed",
            payload={
                "smiles": smiles,
                "formula": formula,
                "material_type": material_type,
                "num_routes": num_routes,
                "scenario_id": scenario_id or "",
                "engine_type": engine_type,
                "agent_id": agent_id,
                "route_count": route_count,
                "task_status": status,
                "error": error[:200],
            },
        )
        if status != "success" and _committee_coordinator is not None:
            try:
                from .committee.triggers import trigger_synthesis_health_case
                streak = store.count_consecutive_failures()
                trigger_synthesis_health_case(_committee_coordinator, streak, latest_error=error)
            except Exception as e:
                logger.debug("Synthesis health trigger failed: %s", e)

    try:
        # 晶体路径或分子路径选 InternLM/SCP 时，不依赖 ASKCOS 服务可达性
        effective_engine = (engine_type or "askcos").lower()
        is_crystal = material_type == "crystal"
        needs_askcos_probe = not is_crystal and effective_engine not in ("logos", "internlm", "scp")
        if needs_askcos_probe:
            if not await _probe_askcos():
                raise SynthesisServiceError(
                    "逆合成规划服务当前无法连接。可能原因：后端服务未启动或网络异常。",
                    service="ASKCOS",
                )
        if effective_engine == "scp":
            result_dict = await asyncio.wait_for(
                _plan_with_scp(
                    smiles, num_routes,
                    material_type=material_type,
                    formula=formula,
                ),
                timeout=_SYNTHESIS_TASK_TIMEOUT,
            )
        else:
            result_dict = await asyncio.wait_for(
                agent.synthesis_planner.plan_multiple_routes(
                    smiles=smiles,
                    num_routes=num_routes,
                    engine_type=effective_engine,
                    material_type=material_type,
                    formula=formula,
                    space_group=space_group,
                ),
                timeout=_SYNTHESIS_TASK_TIMEOUT,
            )
        routes = result_dict.get("routes", []) if isinstance(result_dict, dict) else []
        if not routes:
            # 根据实际引擎选择 service 标签
            if effective_engine == "scp":
                svc = "SCP"
            elif is_crystal:
                svc = "InternLM"
            else:
                svc = "ASKCOS"
            raise SynthesisServiceError(
                "合成规划服务未能生成候选路线，可能是输入结构过于简单或超出模板覆盖范围。",
                service=svc,
            )
        # 回传完整 dict（含晶体路径的 agent_info / reasoning）
        result = result_dict if isinstance(result_dict, dict) else {
            "routes": routes,
            "count": len(routes),
            "best_route": routes[0],
        }
        # 兜底确保必要字段存在
        result.setdefault("routes", routes)
        result.setdefault("count", len(routes))
        result.setdefault("best_route", routes[0] if routes else None)
        # 如果指定了 agent_id，用该 agent 的真实信息覆盖默认 agent_info
        if agent_id and isinstance(result.get("agent_info"), dict):
            try:
                _require_agent_team()
                agent_def = _registry.get_agent(agent_id)
                if agent_def is not None:
                    role_str = agent_def.role.value if hasattr(agent_def.role, "value") else str(agent_def.role)
                    result["agent_info"] = {
                        "agent_id": agent_def.id or agent_id,
                        "name": agent_def.name or agent_id,
                        "role": role_str,
                        "model": agent_def.llm_model or "unknown",
                        "capabilities": agent_def.capabilities or [],
                    }
                    result["executed_by"] = agent_def.id or agent_id
            except Exception as e:
                logger.debug("覆盖 agent_info 失败: %s", e)
        store.complete_task(task_id, result, _elapsed_ms())
        _on_task_finished("success", route_count=len(routes))
        # P3-B2：合成成功后，将最佳可行性分数回写候选材料（若任务关联候选）
        _write_synthesis_feasibility_to_candidate(task_id, routes)
    except SynthesisServiceError as e:
        store.fail_task(task_id, str(e), _elapsed_ms())
        _on_task_finished("failed", error=str(e))
    except asyncio.TimeoutError:
        err = f"规划计算超过 {_SYNTHESIS_TASK_TIMEOUT} 秒仍未完成，服务可能负载过高。"
        store.fail_task(task_id, err, _elapsed_ms())
        _on_task_finished("timeout", error=err)
    except Exception as e:  # noqa: BLE001 - 兜底记录一切异常，避免任务永久 running
        logger.warning("Synthesis task %s failed: %s", task_id, e, exc_info=True)
        # 某些异常（如 httpx.ReadTimeout）str() 可能为空，补充类型名
        err_msg = str(e) or type(e).__name__
        detail = f"规划过程发生异常：{err_msg}"
        # 网络读超时单独给出可操作提示
        if "ReadTimeout" in type(e).__name__ or "Timeout" in type(e).__name__:
            detail = f"大模型推理超时（{type(e).__name__}）。InternLM 服务响应过慢或网络异常，请稍后重试或检查 INTERNLM_BASE_URL 配置。"
        store.fail_task(task_id, detail, _elapsed_ms())
        _on_task_finished("failed", error=detail)


@app.post("/synthesis/plan/async", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
@require_capability("synthesis_planning_askcos_v1")
async def plan_synthesis_async_task(req: SynthesisAsyncRequest):
    """提交异步合成规划任务，立即返回 task_id。前端通过 /synthesis/tasks/{id} 轮询。"""
    # 晶体路径要求 formula；分子路径要求 smiles
    is_crystal = req.material_type == "crystal"
    if is_crystal:
        if not req.formula or not req.formula.strip():
            raise HTTPException(status_code=400, detail="晶体合成规划需要化学式 formula")
    else:
        if not req.smiles or not req.smiles.strip():
            raise HTTPException(status_code=400, detail="SMILES 不能为空")

    # 校验 engine_type 合法性
    effective_engine = (req.engine_type or ("internlm" if is_crystal else "askcos")).lower()
    if effective_engine not in ("askcos", "legacy", "logos", "internlm", "scp"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 engine_type: {req.engine_type}，可选: askcos / internlm / scp",
        )
    # 晶体路径：ASKCOS 不支持无机晶体，强制走 InternLM/SCP
    if is_crystal and effective_engine not in ("logos", "internlm", "scp"):
        effective_engine = "internlm"

    # 若前端指定了 agent_id，校验该 agent 是否具备 synthesis_evidence 能力
    a_actual_id = ""
    if req.agent_id:
        try:
            _require_agent_team()
            agent_def = _registry.get_agent(req.agent_id)
            if agent_def is None:
                raise HTTPException(status_code=404, detail=f"未找到 agent: {req.agent_id}")
            caps = agent_def.capabilities or []
            if "synthesis_evidence" not in caps:
                raise HTTPException(
                    status_code=400,
                    detail=f"agent {req.agent_id} 不具备 synthesis_evidence 能力",
                )
            a_actual_id = agent_def.id or req.agent_id
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # agent_team 未启用时不阻断，仅记录日志
            a_actual_id = req.agent_id
            logger.warning("agent_id 校验跳过: %s", exc)

    store = _get_synthesis_task_store()
    scenario_id = req.scenario_id or ""
    target_label = req.formula.strip() if is_crystal else req.smiles.strip()
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "material_type": req.material_type,
        "formula": req.formula,
        "smiles": req.smiles,
        "engine_type": req.engine_type,
        "num_routes": req.num_routes,
        "candidate_id": req.candidate_id,
    })
    # 修复 500：创建任务时捕获异常并返回具体错误信息
    try:
        task_id = store.create_task(
            target_label,
            num_routes=req.num_routes,
            scenario_id=scenario_id,
            candidate_id=req.candidate_id or "",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("创建合成任务失败: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                f"创建合成任务失败：{exc}。常见原因："
                "MDM 主数据缺少 synthesis_task/pending 状态码，或数据库表未初始化。"
            ),
        )
    _spawn_background(_run_synthesis_task(
        task_id,
        smiles=(req.smiles.strip() if req.smiles else ""),
        num_routes=req.num_routes,
        scenario_id=scenario_id,
        engine_type=effective_engine,
        agent_id=a_actual_id,
        material_type=req.material_type,
        formula=(req.formula.strip() if req.formula else ""),
        space_group=(req.space_group.strip() if req.space_group else ""),
    ))
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    return {
        "task_id": task_id,
        "status": "pending",
        "ai_meta": {
            "input_snapshot_hash": input_snapshot_hash,
            "model_version": "internlm-v1",
            "generated_at": _dt.now(timezone.utc).isoformat(),
        },
    }


@app.get("/synthesis/tasks/{task_id}")
async def get_synthesis_task(task_id: str):
    """查询异步合成规划任务状态与结果。"""
    task = _get_synthesis_task_store().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="规划任务不存在或已被清理")
    return task


@app.get("/synthesis/tasks")
async def list_synthesis_tasks(limit: int = 50):
    """列出最近的合成规划任务（含失败尝试），供历史记录与健康度统计使用。"""
    return {"tasks": _get_synthesis_task_store().list_tasks(limit)}


@app.get("/synthesis/stats")
async def synthesis_stats():
    """合成规划统计：路线产出数与服务成功率，供首页 KPI 卡片使用。"""
    stats = _get_synthesis_task_store().get_stats()
    stats["service_available"] = await _probe_askcos()
    return stats


@app.get("/synthesis/health")
async def synthesis_health():
    """逆合成服务健康探测（供控制平面 Provider 健康看板）。"""
    available = await _probe_askcos()
    return {
        "service": "ASKCOS",
        "available": available,
        "base_url": agent.synthesis_planner.askcos_url,
    }


# ── P1-2：统一 Agent 调用事件日志查询 ─────────────────────────

@app.get("/agent-events")
async def list_agent_events(run_id: str = "", agent_id: str = "", limit: int = 100):
    """查询 Agent 调用事件（ECML 各步骤、合成规划等均写入同一事件表）。

    控制平面运行队列、Agent 管理页统计、委员会案件证据均消费本接口数据。
    """
    if _agent_event_log is None:
        return {"events": [], "count": 0}
    events = _agent_event_log.list_events(run_id=run_id, agent_id=agent_id, limit=limit)
    return {"events": events, "count": len(events)}


@app.get("/agent-events/stats")
async def agent_event_stats():
    """按 Agent 聚合调用统计：调用次数、成功率、平均耗时、Token 成本。"""
    if _agent_event_log is None:
        return {"stats": {}}
    return {"stats": _agent_event_log.stats_by_agent()}


@app.post("/synthesis/manual", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_manual_route(req: ManualRouteRequest):
    """手动填写合成路线：逆合成服务不可用时的业务兜底，保证核心流程不中断。"""
    smiles = req.smiles.strip()
    if not smiles:
        raise HTTPException(status_code=400, detail="目标分子 SMILES 不能为空")
    if not req.steps:
        raise HTTPException(status_code=400, detail="至少需要填写一步反应")
    for idx, step in enumerate(req.steps):
        if not step.reactants or not any(r.strip() for r in step.reactants):
            raise HTTPException(status_code=400, detail=f"第 {idx + 1} 步反应物不能为空")

    steps = [
        {
            "reaction_smiles": f"{'.'.join(r.strip() for r in s.reactants if r.strip())}>>{smiles}",
            "reactants": [r.strip() for r in s.reactants if r.strip()],
            "products": [smiles],
            "conditions": s.conditions,
            "score": s.score,
            "template_score": 0.0,
            "difficulty": "medium",
            "reaction_type": "manual",
        }
        for s in req.steps
    ]
    avg_score = round(sum(s.score for s in req.steps) / len(req.steps), 4)
    route = {
        "route_id": "M1",
        "target_smiles": smiles,
        "steps": steps,
        "feasibility_score": avg_score,
        "step_count": len(steps),
        "confidence": avg_score,
        "reactants": sorted({r for s in steps for r in s["reactants"]}),
        "conditions": [s["conditions"] for s in steps if s["conditions"]],
        "is_feasible": True,
        "overall_score": avg_score,
        "estimated_cost": 0.0,
    }
    result = {"routes": [route], "count": 1, "best_route": route, "note": req.note}
    store = _get_synthesis_task_store()
    task_id = store.create_task(smiles, num_routes=1, source="manual", scenario_id=req.scenario_id or "")
    store.complete_task(task_id, result, 0)
    return {"task_id": task_id, "status": "success", "result": result}


# 异步 ECML 运行状态跟踪：补充 state_store，覆盖首次落盘前的窗口
# 以及超时/失败状态的即时记录，供 GET /ecml/runs/{run_id} 轮询读取。
# 使用 OrderedDict 实现 LRU：保留最近 1000 条状态，避免长期运行内存泄漏。
from collections import OrderedDict as _OrderedDict
_EVML_RUN_STATUS_MAX = 1000
_ecml_run_status: _OrderedDict[str, dict] = _OrderedDict()


def _set_ecml_run_status(run_id: str, status: dict) -> None:
    """更新 ECML 运行状态，超限时淘汰最旧条目。"""
    _ecml_run_status[run_id] = status
    _ecml_run_status.move_to_end(run_id)
    while len(_ecml_run_status) > _EVML_RUN_STATUS_MAX:
        _ecml_run_status.popitem(last=False)


async def _run_ecml_background(run_id: str, target: str, target_property: str,
                                max_iterations: int, target_props, parent_run_id,
                                scenario_id, task_id, project_id=""):
    """后台运行 ECML 闭环，360 秒超时保护（与 engine 内部 300s 优雅超时协调）。

    成功时由 state_store 落盘；超时/失败时更新内存状态供轮询查询。
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                agent.ecml.run, target, target_property, max_iterations, run_id,
                target_props, parent_run_id, scenario_id, task_id, project_id,
            ),
            timeout=360,
        )
        _set_ecml_run_status(run_id, {"status": "completed", "error": None})
    except asyncio.TimeoutError:
        logger.error("ECML run %s timed out after 360s", run_id)
        _set_ecml_run_status(run_id, {"status": "timeout", "error": "ECML 运行超时（360秒）"})
    except Exception as e:
        logger.error("ECML run %s failed: %s", run_id, e)
        _set_ecml_run_status(run_id, {"status": "failed", "error": str(e)})


@app.post("/ecml/run_step", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def ecml_run_step(req: ECMLRunStepRequest):
    """异步启动 ECML 闭环，立即返回 run_id 供前端轮询状态。"""
    # 前置校验
    if not req.target or not req.target.strip():
        raise HTTPException(status_code=400, detail="目标(target)不能为空")
    if not req.target_property or not req.target_property.strip():
        raise HTTPException(status_code=400, detail="目标属性不能为空")

    # v9 §14.5 前置数据检查：至少需要 1 条实验数据，否则 10 秒内返回提示
    try:
        counts = agent.experiment_controller.count_result_records()
        total = sum(counts.values()) if isinstance(counts, dict) else (counts or 0)
        if total < 1:
            raise HTTPException(
                status_code=400,
                detail="至少需要 1 条实验数据才能启动 ECML 闭环。请先在「实验工作台」录入实验结果。",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("ECML 前置数据量检查失败（放行）: %s", e)

    # 外部服务连通性探测（3 秒超时）
    cfg = agent.config
    if cfg.internlm.enabled and cfg.internlm.base_url:
        try:
            import httpx
            probe_url = cfg.internlm.base_url.rstrip("/") + "/models"
            headers = {}
            if cfg.internlm.api_key:
                headers["Authorization"] = f"Bearer {cfg.internlm.api_key.get_secret_value()}"
            async with httpx.AsyncClient(timeout=3.0) as probe:
                resp = await probe.get(probe_url, headers=headers)
                if resp.status_code == 401:
                    raise HTTPException(status_code=503, detail="API key 无效或权限不足，请检查配置")
                if resp.status_code == 403:
                    raise HTTPException(status_code=503, detail="无权限访问 AI 服务，请检查 API key 权限")
                if resp.status_code not in (200, 404):
                    raise HTTPException(status_code=503, detail="外部 AI 服务不可用，请稍后重试")
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="外部 AI 服务连接超时，请稍后重试")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="外部 AI 服务不可达，请稍后重试")

    target_props = req.target_properties if req.target_properties else None
    # run_id 清理特殊字符（目标含 / 空格等会破坏 URL 路径）
    import re as _rid_re
    run_slug = _rid_re.sub(r"[^A-Za-z0-9_-]", "_", req.target)[:8] or "polymer"
    run_id = req.parent_run_id or f"ecml_{int(time.time())}_{run_slug}"

    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "target": req.target,
        "target_property": req.target_property,
        "target_properties": req.target_properties or [],
        "max_iterations": req.max_iterations,
        "scenario_id": req.scenario_id,
    })
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    ai_meta = {
        "input_snapshot_hash": input_snapshot_hash,
        "model_version": "internlm-v1",
        "generated_at": _dt.now(timezone.utc).isoformat(),
    }

    # 标记为运行中，供 GET /ecml/runs/{run_id} 立即可查
    _set_ecml_run_status(run_id, {"status": "running", "error": None, "ai_meta": ai_meta})

    # 启动后台任务
    _spawn_background(_run_ecml_background(
        run_id, req.target, req.target_property, req.max_iterations,
        target_props, req.parent_run_id, req.scenario_id, req.task_id, req.project_id,
    ))

    return {"run_id": run_id, "status": "running", "message": "ECML 运行已启动，请轮询状态", "ai_meta": ai_meta}


@app.get("/config")
async def get_runtime_config(domain_key: str = ""):
    """Return current runtime config (masking secrets).

    domain_key 可选：指定时按领域包解析 material_domain（如 kingfa 返回改性塑料
    体系模板），留空则取默认活跃包。
    """
    cfg = agent.config
    internlm_key = ""
    if cfg.internlm.api_key is not None:
        internlm_key = cfg.internlm.api_key.get_secret_value()
    scp_key = ""
    if cfg.scp.api_key is not None:
        scp_key = cfg.scp.api_key.get_secret_value()
    # Probe InternLM endpoint connectivity with a short timeout. We only check
    # reachability (HTTP 4xx from the API root still means the host is up and
    # the API is serving — a missing-token error is fine). Network errors or
    # timeouts → connected=false so the UI can surface the failure honestly.
    internlm_connected = False
    if cfg.internlm.enabled and cfg.internlm.base_url:
        try:
            import httpx
            probe_url = cfg.internlm.base_url.rstrip("/") + "/models"
            headers = {}
            if internlm_key:
                headers["Authorization"] = f"Bearer {internlm_key}"
            async with httpx.AsyncClient(timeout=3.0) as probe_client:
                resp = await probe_client.get(probe_url, headers=headers)
                # 200 = fully reachable & auth ok; 401 = reachable but auth issue.
                # Either way the endpoint itself is connected.
                internlm_connected = resp.status_code in (200, 401, 403, 404)
        except Exception:
            internlm_connected = False
    return {
        "engine_mode": cfg.engine_mode.value,
        "run_mode": cfg.run_mode.value,
        "mp_api_key_set": bool(cfg.materials_project.api_key),
        "llm_api_key_set": bool(cfg.llm.api_key),
        "llm_model": cfg.llm.model,
        "llm_base_url": cfg.llm.base_url,
        "llm_max_tokens": cfg.llm.max_tokens,
        "llm_context_window": cfg.llm.context_window,
        "askcos_url": cfg.askcos.base_url,
        "internlm": {
            "enabled": cfg.internlm.enabled,
            "api_key_set": bool(internlm_key),
            "base_url": cfg.internlm.base_url,
            "model": cfg.internlm.model,
            "timeout_seconds": cfg.internlm.timeout_seconds,
            "thinking_mode": cfg.internlm.thinking_mode,
            "max_concurrency": cfg.internlm.max_concurrency,
            "connected": internlm_connected,
        },
        "scp": {
            "enabled": cfg.scp.enabled,
            "api_key_set": bool(scp_key),
            "base_url": cfg.scp.base_url,
            "allowed_servers": cfg.scp.allowed_servers,
            "allowed_tools": cfg.scp.allowed_tools,
            "max_concurrency": cfg.scp.max_concurrency,
            "bindings": [b.model_dump() for b in _scp_catalog.list_all()] if _scp_catalog is not None else [],
        },
        # 当前预测模型类型（供前端读取系统设置中默认选中的模型）
        "prediction_models": {
            "crystal": getattr(app.state.agent.crystal_predictor, "model_type", "cgcnn"),
            "polymer": getattr(app.state.agent.polymer_predictor, "model_type", "polymernn"),
        },
        # Task 4：材料体系可配置（前端候选生成/性质预测页体系模板）
        # 统一双源：优先领域包 Store，AgentConfig 仅作回退
        "material_domain": _resolve_material_domain(cfg, domain_key=domain_key),
    }


@app.get("/settings/model_catalog")
async def get_model_catalog():
    """返回专家模型与 DFT 方法的目录，含可用性状态与扩展说明。

    决策 14a-14e：模型矩阵
    - 可用模型（enabled=true）：ASE-EMT、InternLM、Descriptor+InternLM
    - 灰色不可选（enabled=false, grayed_out=true）：CGCNN/MT-CGCNN/M3GNet/PolymerGNN/MatterSim
    - 晶体 DFT 为可扩展灰色功能
    """
    # 探测本地依赖真实可用性
    try:
        from battery_materials_agent.prediction.crystal_property_predictor import _ASE_AVAILABLE, _MATGL_AVAILABLE
        ase_ok = _ASE_AVAILABLE
        matgl_ok = _MATGL_AVAILABLE
    except Exception:
        ase_ok = False
        matgl_ok = False

    # InternLM 连通性复用 /config 的探测逻辑（简化版：只看 enabled + key）
    cfg = agent.config
    internlm_ok = bool(cfg.internlm.enabled and cfg.internlm.api_key)

    return {
        "expert_models": [
            {
                "id": "ase_emt",
                "name": "ASE-EMT",
                "category": "crystal",
                "enabled": ase_ok,
                "grayed_out": not ase_ok,
                "available": ase_ok,
                "note": "本地半经验势计算，适用于金属/合金体系的 band_gap 预测" if ase_ok else "ASE 未安装",
                "supported_properties": ["band_gap"],
                "provider": "local",
            },
            {
                "id": "internlm",
                "name": "InternLM",
                "category": "universal",
                "enabled": internlm_ok,
                "grayed_out": not internlm_ok,
                "available": internlm_ok,
                "note": "大语言模型预测，覆盖拉伸强度、弯曲模量、冲击强度等多种高分子性质" if internlm_ok else "InternLM 未配置 API Key",
                "supported_properties": ["tensile_strength", "flexural_modulus", "impact_strength", "heat_deflection_temp"],
                "provider": "intern-ai",
            },
            {
                "id": "descriptor_internlm",
                "name": "Descriptor+InternLM",
                "category": "polymer",
                "enabled": internlm_ok,
                "grayed_out": not internlm_ok,
                "available": internlm_ok,
                "note": "RDKit 描述符 + InternLM 联合预测，专为聚合物材料设计" if internlm_ok else "依赖 InternLM 配置",
                "supported_properties": ["tensile_strength", "flexural_modulus", "impact_strength",
                                         "heat_deflection_temp", "melt_flow_index", "glass_transition_temp"],
                "provider": "local+intern-ai",
            },
            {
                "id": "m3gnet",
                "name": "M3GNet",
                "category": "crystal",
                "enabled": False,
                "grayed_out": True,
                "available": matgl_ok,
                "note": "通用材料势函数，需安装 matgl 扩展包后启用",
                "supported_properties": ["formation_energy", "band_gap", "e_above_hull"],
                "provider": "local",
                "extension_required": "pip install matgl",
            },
            {
                "id": "cgcnn",
                "name": "CGCNN",
                "category": "crystal",
                "enabled": False,
                "grayed_out": True,
                "available": False,
                "note": "晶体图卷积网络，扩展功能",
                "supported_properties": ["band_gap", "formation_energy"],
                "provider": "local",
                "extension_required": "需训练/加载预训练权重",
            },
            {
                "id": "mt_cgcnn",
                "name": "MT-CGCNN",
                "category": "crystal",
                "enabled": False,
                "grayed_out": True,
                "available": False,
                "note": "多任务 CGCNN，扩展功能",
                "supported_properties": ["band_gap", "formation_energy", "bulk_modulus"],
                "provider": "local",
                "extension_required": "需训练/加载预训练权重",
            },
            {
                "id": "polymernn",
                "name": "PolymerGNN",
                "category": "polymer",
                "enabled": False,
                "grayed_out": True,
                "available": False,
                "note": "聚合物图神经网络，扩展功能",
                "supported_properties": ["tensile_strength", "flexural_modulus", "glass_transition_temp", "dielectric_constant"],
                "provider": "local",
                "extension_required": "需训练/加载预训练权重",
            },
            {
                "id": "mattersim",
                "name": "MatterSim",
                "category": "crystal",
                "enabled": False,
                "grayed_out": True,
                "available": False,
                "note": "深势能模型，扩展功能；当前请使用 M3GNet 作为替代",
                "supported_properties": ["formation_energy", "band_gap"],
                "provider": "local",
                "extension_required": "需安装 mattersim",
            },
        ],
        "dft_methods": {
            "enabled": False,
            "grayed_out": True,
            "note": "晶体 DFT 为可扩展灰色功能，当前未启用；PBE/6-31G* 为默认规划",
            "functionals": [
                {"id": "pbe", "name": "PBE", "available": False, "note": "GGA 泛函，默认推荐"},
                {"id": "b3lyp", "name": "B3LYP", "available": False, "note": "杂化泛函"},
                {"id": "hf", "name": "HF", "available": False, "note": "Hartree-Fock"},
            ],
            "basis_sets": [
                {"id": "6-31g", "name": "6-31G*", "available": False, "note": "默认基组"},
                {"id": "6-311g", "name": "6-311G**", "available": False, "note": "三 zeta 基组"},
                {"id": "sto-3g", "name": "STO-3G", "available": False, "note": "最小基组"},
            ],
        },
    }


@app.post("/config", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_config(req: ConfigUpdateRequest):
    """Update runtime config (in-memory only; for persistence use .env file)."""
    global _scp_client_pool
    cfg = agent.config
    updated = []
    if req.mp_api_key is not None:
        cfg.materials_project.api_key = req.mp_api_key
        agent.crystal_generator.api_key = req.mp_api_key
        updated.append("mp_api_key")
    if req.llm_api_key is not None:
        cfg.llm.api_key = req.llm_api_key
        agent.polymer_generator.llm_api_key = req.llm_api_key
        updated.append("llm_api_key")
    if req.llm_model is not None:
        cfg.llm.model = req.llm_model
        agent.polymer_generator.llm_model = req.llm_model
        updated.append("llm_model")
    if req.llm_base_url is not None:
        cfg.llm.base_url = req.llm_base_url
        agent.polymer_generator.llm_base_url = req.llm_base_url.rstrip("/")
        updated.append("llm_base_url")
    if req.llm_max_tokens is not None:
        cfg.llm.max_tokens = req.llm_max_tokens
        agent.polymer_generator.llm_max_tokens = req.llm_max_tokens
        updated.append("llm_max_tokens")
    if req.askcos_url is not None:
        cfg.askcos.base_url = req.askcos_url
        agent.synthesis_planner.askcos_url = req.askcos_url.rstrip("/")
        updated.append("askcos_url")
    if req.crystal_model is not None:
        agent.crystal_predictor.model_type = req.crystal_model
        updated.append("crystal_model")
    if req.polymer_model is not None:
        agent.polymer_predictor.model_type = req.polymer_model
        updated.append("polymer_model")
    if req.dft_method is not None:
        agent.verifier.method = req.dft_method
        updated.append("dft_method")
    if req.basis_set is not None:
        agent.verifier.basis = req.basis_set
        updated.append("basis_set")
    # Engine mode (legacy / internlm; "logos" auto-maps to internlm via EngineMode._missing_)
    if req.engine_mode is not None:
        try:
            cfg.engine_mode = EngineMode(req.engine_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"engine_mode 非法值「{req.engine_mode}」") from e
        updated.append("engine_mode")
    # Run mode (demo / production) — admin only, persisted to .env
    if req.run_mode is not None:
        from .config import RunMode
        try:
            cfg.run_mode = RunMode(req.run_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"run_mode 非法值「{req.run_mode}」") from e
        updated.append("run_mode")
        # 同步运行时实例（demo/production 切换立即生效，无需重启）
        try:
            agent.experiment_controller.run_mode = req.run_mode
        except Exception as e:
            logger.warning("同步 experiment_controller.run_mode 失败: %s", e)
    # InternLM
    if req.internlm_enabled is not None:
        cfg.internlm.enabled = req.internlm_enabled
        updated.append("internlm_enabled")
    if req.internlm_api_key is not None:
        cfg.internlm.api_key = SecretStr(req.internlm_api_key)
        updated.append("internlm_api_key")
    if req.internlm_base_url is not None:
        cfg.internlm.base_url = req.internlm_base_url
        updated.append("internlm_base_url")
    if req.internlm_model is not None:
        cfg.internlm.model = req.internlm_model
        updated.append("internlm_model")
    if req.internlm_timeout is not None:
        cfg.internlm.timeout_seconds = req.internlm_timeout
        updated.append("internlm_timeout")
    if req.internlm_thinking_mode is not None:
        cfg.internlm.thinking_mode = req.internlm_thinking_mode
        updated.append("internlm_thinking_mode")
    if req.internlm_max_concurrency is not None:
        cfg.internlm.max_concurrency = req.internlm_max_concurrency
        updated.append("internlm_max_concurrency")
    # SCP
    if req.scp_enabled is not None:
        cfg.scp.enabled = req.scp_enabled
        updated.append("scp_enabled")
    if req.scp_api_key is not None:
        cfg.scp.api_key = SecretStr(req.scp_api_key)
        updated.append("scp_api_key")
    if req.scp_base_url is not None:
        cfg.scp.base_url = req.scp_base_url
        updated.append("scp_base_url")
    if req.scp_allowed_servers is not None:
        cfg.scp.allowed_servers = req.scp_allowed_servers
        updated.append("scp_allowed_servers")
    if req.scp_allowed_tools is not None:
        cfg.scp.allowed_tools = req.scp_allowed_tools
        updated.append("scp_allowed_tools")
    if req.scp_max_concurrency is not None:
        cfg.scp.max_concurrency = req.scp_max_concurrency
        updated.append("scp_max_concurrency")
    # Persist changes to .env so they survive restarts (engine_mode, keys, etc.)
    try:
        save_config_to_env(cfg)
    except Exception as exc:
        # Persistence failure should not break the in-memory update
        updated.append(f"save_config_to_env_failed: {exc}")
    return {"updated": updated, "count": len(updated), "engine_mode": cfg.engine_mode.value}


def _serialize_agent_config(cfg, domain_key: str = ""):
    """Serialize AgentConfig to a JSON-friendly dict for /api/config.

    Secrets are NEVER returned. Each secret-bearing section exposes only a
    boolean `*_api_key_set` flag so callers can show "已配置/未配置" status
    without ever receiving the raw key. This complies with the system
    specification: "任何响应均不得返回 API Key".
    """
    return {
        "engine_mode": cfg.engine_mode.value,
        "run_mode": cfg.run_mode.value,
        "logos": {
            "base_url": cfg.logos.base_url,
            "model_name": cfg.logos.model_name,
            "api_key_set": bool(cfg.logos.api_key),
            "timeout": cfg.logos.timeout,
        },
        "llm": {
            "api_key_set": bool(cfg.llm.api_key),
            "model": cfg.llm.model,
            "base_url": cfg.llm.base_url,
            "max_tokens": cfg.llm.max_tokens,
        },
        "askcos": {
            "base_url": cfg.askcos.base_url,
            "timeout": cfg.askcos.timeout,
        },
        "materials_project": {
            "api_key_set": bool(cfg.materials_project.api_key),
            "base_url": cfg.materials_project.base_url,
            "gnome_use_mp_mirror": cfg.materials_project.gnome_use_mp_mirror,
            "gnome_data_dir": str(cfg.materials_project.gnome_data_dir),
        },
        "middleware": {
            "db_url": cfg.middleware.db_url,
            "poll_interval": cfg.middleware.poll_interval,
        },
        # Task 4：材料体系可配置（前端候选生成/性质预测页体系模板）
        # 统一双源：优先领域包 Store，AgentConfig 仅作回退
        "material_domain": _resolve_material_domain(cfg, domain_key=domain_key),
    }


@app.get("/api/config")
async def get_api_config(domain_key: str = ""):
    """Return current runtime config for LOGOS dual-engine integration."""
    return _serialize_agent_config(app.state.agent.config, domain_key=domain_key)


@app.put("/api/config", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_api_config(req: ConfigUpdatePayload):
    """Update runtime config and persist key values to .env."""
    cfg = app.state.agent.config
    if req.engine_mode is not None:
        if req.engine_mode not in ("legacy", "logos"):
            raise HTTPException(status_code=400, detail="engine_mode must be 'legacy' or 'logos'")
        cfg.engine_mode = EngineMode(req.engine_mode)
    if req.logos_base_url is not None:
        cfg.logos.base_url = req.logos_base_url
    if req.logos_model_name is not None:
        cfg.logos.model_name = req.logos_model_name
    if req.logos_api_key is not None:
        cfg.logos.api_key = req.logos_api_key
    if req.logos_timeout is not None:
        cfg.logos.timeout = req.logos_timeout
    if req.llm_api_key is not None:
        cfg.llm.api_key = req.llm_api_key
    if req.llm_model is not None:
        cfg.llm.model = req.llm_model
    if req.llm_base_url is not None:
        cfg.llm.base_url = req.llm_base_url
    if req.llm_max_tokens is not None:
        cfg.llm.max_tokens = req.llm_max_tokens

    try:
        save_config_to_env(cfg)
    except Exception as exc:
        logger.warning("save_config_to_env 失败（内存配置已生效，.env 未持久化）: %s", exc)
    return _serialize_agent_config(cfg)


# --- Agent Team endpoints ---

def _resolve_effective_model(provider: str, llm_model: str, cfg) -> str:
    """根据 provider 和 llm_model 计算实际使用的模型名（用于展示）。"""
    provider = (provider or "").lower()
    llm_model_cfg = cfg.llm.model if cfg.llm.model else None
    internlm_model = cfg.internlm.model if cfg.internlm.enabled and cfg.internlm.model else None
    if provider == "internlm":
        return internlm_model or "AI 引擎默认"
    if provider == "llm":
        return llm_model or llm_model_cfg or "—"
    # 自动：llm_model 非空走 LLM，否则走 InternLM
    if llm_model:
        return llm_model
    return internlm_model or "—"


@app.get("/agents")
async def list_agents():
    """列出所有 agent（内置 + 自定义）。

    返回字段：
    - effective_model：兼容旧前端的展示字段（等于优先模型名）
    - effective_model_primary：优先模型名
    - effective_model_secondary：备选模型名（无备选时为空字符串）
    """
    _require_agent_team()
    agents = _registry.list_agents()
    cfg = get_config()
    result = []
    for a in agents:
        d = a.model_dump()
        primary = _resolve_effective_model(a.provider, a.llm_model, cfg)
        secondary = ""
        if a.provider_secondary:
            secondary = _resolve_effective_model(a.provider_secondary, a.llm_model_secondary, cfg)
        d["effective_model"] = primary
        d["effective_model_primary"] = primary
        d["effective_model_secondary"] = secondary
        result.append(d)
    return {"agents": result, "count": len(result)}


@app.get("/agents/llm-options")
async def agent_llm_options():
    """返回智能体可选的模型提供方及其服务地址、模型名。

    用于前端编辑下拉选择：
    - llm：通用 LLM（config.llm.base_url + config.llm.model）
    - internlm：AI 引擎（config.internlm.base_url + config.internlm.model）
    """
    cfg = get_config()
    options = [
        {
            "provider": "llm",
            "label": "LLM 大模型",
            "base_url": cfg.llm.base_url,
            "model": cfg.llm.model,
            "available": bool(cfg.llm.api_key),
        },
        {
            "provider": "internlm",
            "label": "AI 引擎（InternLM）",
            "base_url": cfg.internlm.base_url,
            "model": cfg.internlm.model,
            "available": bool(cfg.internlm.enabled and cfg.internlm.api_key),
        },
    ]
    return {"options": options}


def _normalize_provider_model(provider: str, llm_model: str, cfg) -> tuple[str, str]:
    """根据 provider 规整 llm_model，避免不一致（如 provider=internlm 但 llm_model=LongCat）。

    返回 (规整后的 llm_model, 规整后的 provider)。
    - provider="internlm"：llm_model 置空
    - provider="llm"：llm_model 用传入值或 LLM 配置默认模型
    - provider=""（自动）：保留传入值
    """
    p = (provider or "").lower()
    if p == "internlm":
        return "", p
    if p == "llm":
        return llm_model or cfg.llm.model or "LongCat-2.0", p
    return llm_model, p


@app.post("/agents", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_agent(req: CreateAgentRequest):
    """创建自定义 agent。

    根据 provider 自动同步 llm_model 字段，保证存储一致性。
    支持备选模型：provider_secondary 非空时，优先模型失败自动 fallback。
    """
    _require_agent_team()
    try:
        role = AgentRole(req.role)
    except ValueError:
        role = AgentRole.CUSTOM
    cfg = get_config()
    llm_model, provider = _normalize_provider_model(req.provider, req.llm_model, cfg)
    llm_model_secondary, provider_secondary = _normalize_provider_model(
        req.provider_secondary, req.llm_model_secondary, cfg
    )
    # 备选模型与优先模型相同则视为无备选
    if provider_secondary and provider_secondary == provider:
        provider_secondary = ""
        llm_model_secondary = ""
    agent_def = AgentDefinition(
        id="",
        name=req.name,
        role=role,
        description=req.description,
        expertise=req.expertise,
        tools=req.tools,
        avatar=req.avatar,
        is_builtin=False,
        llm_model=llm_model,
        provider=req.provider,
        provider_secondary=provider_secondary,
        llm_model_secondary=llm_model_secondary,
    )
    created = _registry.create_custom_agent(agent_def)
    return {"agent": created.model_dump()}


@app.put("/agents/{agent_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_agent(agent_id: str, req: CreateAgentRequest):
    """更新 agent（自定义 agent 直接更新；内置 agent 写入覆盖表）。

    同 create_agent，按 provider 规整 llm_model 字段，支持备选模型。
    """
    _require_agent_team()
    try:
        role = AgentRole(req.role)
    except ValueError:
        role = AgentRole.CUSTOM
    cfg = get_config()
    llm_model, provider = _normalize_provider_model(req.provider, req.llm_model, cfg)
    llm_model_secondary, provider_secondary = _normalize_provider_model(
        req.provider_secondary, req.llm_model_secondary, cfg
    )
    if provider_secondary and provider_secondary == provider:
        provider_secondary = ""
        llm_model_secondary = ""
    updates = {
        "name": req.name,
        "role": role,
        "description": req.description,
        "expertise": req.expertise,
        "tools": req.tools,
        "avatar": req.avatar,
        "llm_model": llm_model,
        "provider": req.provider,
        "provider_secondary": provider_secondary,
        "llm_model_secondary": llm_model_secondary,
    }
    try:
        updated = _registry.update_agent(agent_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"agent": updated.model_dump()}


async def _call_llm_provider(
    provider: str,
    llm_model: str,
    messages: list[dict],
    cfg,
    max_tokens: int = 1024,
) -> str:
    """调用指定的 LLM provider 完成对话，返回回复文本。

    - provider="internlm"：走 AI 引擎（InternLM），关闭深度思考加速响应
    - provider="llm"：走通用 LLM（OpenAI-compatible）
    - provider=""（自动）：llm_model 非空走 LLM，否则走 InternLM

    失败时抛异常，由调用方决定是否 fallback。
    """
    p = (provider or "").lower()
    if not p:
        p = "llm" if llm_model else "internlm"

    if p == "internlm":
        if not (cfg.internlm.enabled and cfg.internlm.api_key):
            raise RuntimeError("AI 引擎（InternLM）未启用或未配置 API Key")
        from .llm.schemas import ChatMessage, ChatRequest
        from .llm.internlm_provider import InternLMProvider
        # 不修改全局配置：用 model_copy 派生一份关闭深度思考的配置，避免变异共享 cfg。
        chat_cfg = cfg.internlm.model_copy(update={"thinking_mode": False})
        provider_inst = InternLMProvider(chat_cfg)
        try:
            chat_req = ChatRequest(
                model=chat_cfg.model,
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
                temperature=0.7,
                max_tokens=max_tokens,
            )
            resp = await provider_inst.complete(chat_req)
            return resp.content
        finally:
            close_fn = getattr(provider_inst, "close", None)
            if close_fn:
                try:
                    await close_fn()
                except Exception:
                    pass

    # 走通用 LLM（通过统一 LLMProvider 调用，走审计治理链）
    if not cfg.llm.api_key:
        raise RuntimeError("LLM 大模型未配置 API Key")
    from .llm.schemas import ChatRequest, ChatMessage
    effective_model = llm_model or cfg.llm.model
    chat_req = ChatRequest(
        model=effective_model,
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    resp = await _llm_provider.complete(chat_req)
    return resp.content


@app.post("/agents/{agent_id}/chat", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def agent_chat(agent_id: str, req: AgentChatRequest):
    """与指定智能体进行测试对话。

    支持双模型 fallback：
    1. 优先调用 agent.provider / agent.llm_model（优先模型）
    2. 优先模型失败（网络/认证/服务异常）时，若配置了 provider_secondary，
       自动 fallback 到备选模型
    3. 备选也失败则返回错误

    返回字段：
    - provider：实际成功响应的 provider 名
    - fallback_used：是否使用了备选模型
    """
    _require_agent_team()
    agent = _registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    cfg = get_config()

    # 构造 system prompt：基于 agent 的人设
    system_prompt = (
        f"你是「{agent.name}」。{agent.description or ''}\n"
        f"角色：{agent.role.value if hasattr(agent.role, 'value') else agent.role}\n"
    )
    if agent.expertise:
        system_prompt += f"专长领域：{'、'.join(agent.expertise)}\n"
    system_prompt += "请以该智能体的身份简洁、专业地回答用户问题。"

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in (req.history or [])[-20:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message})

    # 构造调用链：优先 + 备选
    attempts: list[tuple[str, str]] = [(agent.provider, agent.llm_model)]
    if agent.provider_secondary:
        attempts.append((agent.provider_secondary, agent.llm_model_secondary))

    last_error: str = ""
    for idx, (prov, model) in enumerate(attempts):
        try:
            reply = await _call_llm_provider(prov, model, messages, cfg)
            return {
                "agent_id": agent_id,
                "agent_name": agent.name,
                "provider": (prov or "").lower() or ("llm" if model else "internlm"),
                "fallback_used": idx > 0,
                "reply": reply,
            }
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if idx == 0 and len(attempts) > 1:
                # 优先模型失败，尝试 fallback
                continue
            # 无 fallback 或 fallback 也失败
            raise HTTPException(
                status_code=500,
                detail=f"对话失败（{last_error}）",
            )

    raise HTTPException(status_code=500, detail=f"对话失败：{last_error}")


@app.delete("/agents/{agent_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_agent(agent_id: str):
    """删除自定义 agent（内置 agent 不可删除）。"""
    _require_agent_team()
    deleted = _registry.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="无法删除：agent 不存在或为内置 agent")
    return {"deleted": True, "agent_id": agent_id}


# P0-010: 智能体心跳检测
import time as _time

_agent_health_store: dict[str, dict] = {}  # agent_id -> {last_heartbeat, last_status, latency_ms, history}


@app.post("/agents/{agent_id}/heartbeat", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def agent_heartbeat(agent_id: str, payload: dict | None = None):
    """接收智能体心跳上报，记录健康状态。"""
    _require_agent_team()
    now = _time.time()
    body = payload or {}
    status = body.get("status", "healthy")
    latency_ms = body.get("latency_ms", 0)

    entry = _agent_health_store.get(agent_id, {"history": []})
    entry["last_heartbeat"] = now
    entry["last_status"] = status
    entry["latency_ms"] = latency_ms
    # 保留最近 20 条历史
    entry["history"].append({"ts": now, "status": status, "latency_ms": latency_ms})
    if len(entry["history"]) > 20:
        entry["history"] = entry["history"][-20:]
    _agent_health_store[agent_id] = entry

    return {"agent_id": agent_id, "recorded": True, "timestamp": now}


@app.get("/agents/health")
async def agents_health():
    """返回所有智能体的健康状态汇总。"""
    _require_agent_team()
    now = _time.time()
    result = {}
    for agent in _registry.list_agents():
        aid = agent.id
        entry = _agent_health_store.get(aid)
        if entry:
            elapsed = now - entry.get("last_heartbeat", 0)
            if elapsed < 60:
                health = "healthy"
            elif elapsed < 300:
                health = "degraded"
            else:
                health = "unknown"
            result[aid] = {
                "health": health,
                "last_heartbeat": entry.get("last_heartbeat"),
                "last_status": entry.get("last_status", "unknown"),
                "latency_ms": entry.get("latency_ms", 0),
                "elapsed_seconds": round(elapsed, 1),
            }
        else:
            # 无心跳记录的内置 agent，基于 agent 定义状态推断
            result[aid] = {
                "health": "unknown" if agent.status == "development" else "healthy",
                "last_heartbeat": None,
                "last_status": "unknown",
                "latency_ms": 0,
                "elapsed_seconds": None,
            }
    return {"health": result}


@app.get("/topology", dependencies=[Depends(require_login)])
async def get_topology():
    """聚合返回调用关系拓扑（T-036）。

    一次返回 agents / capabilities / scp_bindings / tools / activity_mappings
    及显式 edges 关系列表，供前端调用关系视图单次拉取渲染。
    每类数据获取失败时返回空数组而非 500，保证部分依赖缺失时仍可展示。
    """
    # --- agents ---
    agents: list[dict] = []
    try:
        if _registry is not None:
            for a in _registry.list_agents():
                agents.append({
                    "agent_id": a.id,
                    "name": a.name,
                    "version": "",
                    "status": a.status,
                    "capabilities": list(a.capabilities or []),
                })
    except Exception as exc:
        logger.warning("topology: agents load failed: %s", exc)

    # --- capabilities ---
    capabilities: list[dict] = []
    try:
        cap_registry = _get_capability_registry()
        for c in cap_registry.list_all():
            capabilities.append({
                "capability_id": c.capability_id,
                "name": c.name,
                "version": c.version,
                "category": c.supported_domains[0] if c.supported_domains else "",
            })
    except Exception as exc:
        logger.warning("topology: capabilities load failed: %s", exc)

    # --- scp_bindings ---
    scp_bindings: list[dict] = []
    try:
        if _scp_catalog is not None:
            for b in _scp_catalog.list_all():
                scp_bindings.append({
                    "binding_id": b.internal_name,
                    "tool_name": b.internal_name,
                    "scp_id": b.server_id,
                    "risk_level": b.risk_level.value if b.risk_level else "",
                    "enabled": b.enabled,
                })
    except Exception as exc:
        logger.warning("topology: scp_bindings load failed: %s", exc)

    # --- tools（合并 MCP 工具 + 注册工具，按 name 去重） ---
    tools: list[dict] = []
    try:
        seen_tool_names: set[str] = set()
        if agent is not None:
            for t in agent.tools.list_tools():
                if t.name in seen_tool_names:
                    continue
                seen_tool_names.add(t.name)
                tools.append({
                    "tool_name": t.name,
                    "version": "",
                    "category": t.source,
                    "risk_level": t.risk_level or "",
                })
        if _activity_mapping_store is not None:
            for reg in _activity_mapping_store.list_tool_registrations():
                if reg.name in seen_tool_names:
                    continue
                seen_tool_names.add(reg.name)
                tools.append({
                    "tool_name": reg.name,
                    "version": "",
                    "category": reg.source,
                    "risk_level": reg.risk_level or "",
                })
    except Exception as exc:
        logger.warning("topology: tools load failed: %s", exc)

    # --- activity_mappings（业务活动 → 智能体 → 工具） ---
    activity_mappings: list[dict] = []
    activity_bindings: list = []
    tool_bindings: list = []
    tools_by_agent: dict[str, list[str]] = {}
    try:
        if _activity_mapping_store is not None:
            activity_bindings = _activity_mapping_store.list_activity_bindings()
            tool_bindings = _activity_mapping_store.list_tool_bindings()
            for tb in tool_bindings:
                tools_by_agent.setdefault(tb.agent_id, []).append(tb.primary_tool_id)
            for ab in activity_bindings:
                agent_tools = tools_by_agent.get(ab.agent_id, [])
                if agent_tools:
                    for tname in agent_tools:
                        activity_mappings.append({
                            "activity_code": ab.activity_id,
                            "agent_id": ab.agent_id,
                            "tool_name": tname,
                        })
                else:
                    activity_mappings.append({
                        "activity_code": ab.activity_id,
                        "agent_id": ab.agent_id,
                        "tool_name": "",
                    })
    except Exception as exc:
        logger.warning("topology: activity_mappings load failed: %s", exc)

    # --- edges（显式关系列表） ---
    edges: list[dict] = []
    # agent → capability (provides)
    for a in agents:
        for cap_id in a.get("capabilities", []):
            edges.append({
                "from": f"agent:{a['agent_id']}",
                "to": f"capability:{cap_id}",
                "type": "provides",
            })
    # activity → agent (binds)
    for ab in activity_bindings:
        edges.append({
            "from": f"activity:{ab.activity_id}",
            "to": f"agent:{ab.agent_id}",
            "type": "binds",
        })
    # activity → tool (uses)：由 activity→agent→tool 派生
    for ab in activity_bindings:
        for tname in tools_by_agent.get(ab.agent_id, []):
            edges.append({
                "from": f"activity:{ab.activity_id}",
                "to": f"tool:{tname}",
                "type": "uses",
            })
    # tool → scp (bound_to)
    scp_tool_names = {b["tool_name"] for b in scp_bindings}
    for t in tools:
        if t["tool_name"] in scp_tool_names:
            edges.append({
                "from": f"tool:{t['tool_name']}",
                "to": f"scp:{t['tool_name']}",
                "type": "bound_to",
            })

    return {
        "agents": agents,
        "capabilities": capabilities,
        "scp_bindings": scp_bindings,
        "tools": tools,
        "activity_mappings": activity_mappings,
        "edges": edges,
    }


@app.post("/orchestrate/analyze", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def analyze_task(req: AnalyzeTaskRequest):
    """用 LLM 分析任务，推荐 agent 小队和执行步骤。"""
    _require_agent_team()
    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "target": req.target,
        "constraints": req.constraints,
    })
    plan = await _orchestrator.analyze_task(req.target, req.constraints)
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    result = plan.model_dump()
    result.setdefault("ai_meta", {})["input_snapshot_hash"] = input_snapshot_hash
    result.setdefault("ai_meta", {})["model_version"] = "internlm-v1"
    result.setdefault("ai_meta", {})["generated_at"] = _dt.now(timezone.utc).isoformat()
    return result


@app.post("/orchestrate/execute", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def execute_plan(req: ExecutePlanRequest):
    """执行编排方案，返回 record_id 供前端轮询进度。"""
    _require_agent_team()
    _init_hybrid_stack()  # 确保 capability_router 已注入 executor
    try:
        team = [AgentDefinition.model_validate(t) for t in req.team]
        steps = [TaskStep.model_validate(s) for s in req.steps]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"编排计划参数非法：{e}") from e
    plan = OrchestrationPlan(team=team, steps=steps)

    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "target": req.target,
        "team": req.team,
        "steps": req.steps,
    })
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    ai_meta = {
        "input_snapshot_hash": input_snapshot_hash,
        "model_version": "internlm-v1",
        "generated_at": _dt.now(timezone.utc).isoformat(),
    }

    # 预先创建 record，获取 record_id（避免竞态条件）
    record_id = await _executor.create_record(req.target, plan)

    # 启动后台执行任务，传入已有 record_id 避免重复创建
    async def _run():
        async for _ in _executor.execute(req.target, plan, record_id=record_id):
            pass

    _spawn_background(_run())

    return {"record_id": record_id, "ai_meta": ai_meta}


@app.get("/orchestrate/record/{record_id}")
async def get_record(record_id: str):
    """获取执行记录（含所有事件）。"""
    _require_agent_team()
    record = _executor.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record.model_dump()


@app.get("/orchestrate/history")
async def orchestration_history():
    """获取最近的编排历史。"""
    _require_agent_team()
    records = _executor.list_records(limit=20)
    return {"history": [r.model_dump() for r in records], "count": len(records)}


# --- 企业物料规格库 ---

@app.get("/raw-materials")
async def list_raw_materials(category: str = "", include_demo: bool = False):
    """查询企业物料规格库，支持按分类筛选。

    D2(P2-002)：默认过滤 SEED_ 演示物料，include_demo=True 时包含。
    """
    if category:
        materials = agent.raw_material_db.query_category(category)
    else:
        materials = agent.raw_material_db.get_all()
    items = _filter_demo([m.model_dump() for m in materials], include_demo)
    return {"materials": items, "count": len(items)}


@app.get("/raw-materials/{material_id}")
async def get_raw_material(material_id: str):
    """查询单个物料规格。"""
    spec = agent.raw_material_db.get_spec(material_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"物料 {material_id} 不存在")
    return spec.model_dump()


@app.get("/raw-materials/{material_id}/compliance")
async def get_raw_material_compliance(material_id: str):
    """查询物料的结构化合规状态与关联证据（Task 13）。

    返回 {status, evidence}，status 为 compliant / pending_evidence / non_compliant。
    """
    status = agent.raw_material_db.get_compliance_status(material_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"物料 {material_id} 不存在")
    return status


class MaterialAvailabilityRequest(BaseModel):
    """候选材料 → 物料库可得性检查请求。"""
    candidates: list[dict] = Field(default_factory=list)  # [{id, formula, smiles, name}]
    quantity: float = 1.0  # 0727b：需求量（单位由上下文物料分类决定）


class RawMaterialUpsertRequest(BaseModel):
    """物料规格新增/编辑请求。material_id 为空时自动生成。"""
    material_id: str = ""
    name: str = ""
    smiles: str = ""
    category: str = ""
    inventory_quantity: float = 0.0  # 0727b：库存数量（单位由 inventory_unit 决定）
    inventory_unit: str = ""  # 0727：库存单位，空则从 MDM material_categories.default_unit 获取
    unit_cost: float = 0.0  # 0727b：单位成本（货币+单位由 inventory_unit 决定）
    supplier: str = ""
    reach_compliant: bool = False
    is_toxic: bool = False
    batch_number: str = ""
    expiry_date: str = ""
    coa_uri: str = ""
    # Task 13：合规证据字段
    sds_uri: str = ""
    test_report_uri: str = ""
    test_institution: str = ""
    test_date: str = ""
    min_order_quantity: float = 0.0
    updated_by: str = ""
    update_reason: str = ""
    data_source: str = "measured"  # measured / predicted
    prediction_meta: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)  # 按属性字典模板录入的属性值


@app.post("/raw-materials/check-availability", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def check_materials_availability(req: MaterialAvailabilityRequest):
    """检查候选材料所需原料在企业物料库中的可得性。

    对每个候选材料：
    1. 反查物料库中匹配的原料（元素/SMILES 相似度）
    2. 估算采购成本与库存缺口
    3. 标注：已入库 / 需新采购 / 预估综合成本

    返回 [{candidate_id, formula, smiles, matched_materials, cost_estimate, status}]
    """
    results = []
    for cand in req.candidates:
        formula = cand.get("formula", "")
        smiles = cand.get("smiles", "")
        cand_id = cand.get("candidate_id") or cand.get("id") or formula or smiles
        matched = agent.raw_material_db.find_raw_materials_for_candidate(formula=formula, smiles=smiles)
        matched_ids = [m.material_id for m in matched]
        cost_estimate = agent.raw_material_db.estimate_cost(matched_ids, quantity=req.quantity)

        if not matched:
            status = "no_match"  # 物料库中无匹配原料，需新采购
        elif cost_estimate["shortage"] > 0:
            status = "partial_in_stock"  # 部分入库，部分需采购
        else:
            status = "in_stock"  # 全部已入库

        results.append({
            "candidate_id": cand_id,
            "formula": formula,
            "smiles": smiles,
            "name": cand.get("name", ""),
            "matched_materials": [m.model_dump() for m in matched],
            "cost_estimate": cost_estimate,
            "status": status,
        })
    return {"results": results, "count": len(results)}


class IndustrializationCheckRequest(BaseModel):
    """候选材料 → 工业化合规与可制造性检查请求。"""
    formula: str = ""
    smiles: str = ""
    target_material: dict = Field(default_factory=dict)
    # 0021：关联候选材料 ID，用于持久化合规检查结果到 candidate_artifacts
    candidate_id: str = ""


@app.post("/industrialization/check", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def industrialization_check(req: IndustrializationCheckRequest):
    """候选材料的工业化合规与可制造性检查。

    流程：
    1. 用 formula / smiles 反查物料库，构建 BOM
    2. 调用 ComplianceAndCostNode.evaluate(bom) 执行 SMARTS/REACH/成本检查
    3. 汇总成前端期望的 {overall_score, estimated_cost, supply_risk, checks}
    """
    formula = req.formula or req.target_material.get("formula", "")
    smiles = req.smiles or req.target_material.get("smiles", "")

    # 1. 反查物料库，构建 BOM（等权分配）
    matched = agent.raw_material_db.find_raw_materials_for_candidate(
        formula=formula, smiles=smiles,
    )
    if not matched:
        result = {
            "overall_score": 0.0,
            "estimated_cost": 0.0,
            "supply_risk": "无匹配物料",
            "checks": [
                {"name": "物料匹配", "passed": False, "detail": "物料库中未找到匹配原料，无法进行工业化评估"},
            ],
            # 执行过程透明化（#3）：步骤链 + 引擎说明
            "process": [
                {"step": "候选材料解析", "status": "done", "detail": f"化学式 {formula or '—'} / SMILES {smiles or '—'}"},
                {"step": "物料库匹配", "status": "failed", "detail": "物料库中未找到匹配原料"},
                {"step": "合规规则检查", "status": "skipped", "detail": "无匹配物料，跳过规则评估"},
                {"step": "成本与供应链评估", "status": "skipped", "detail": "无匹配物料，跳过评估"},
                {"step": "报告生成", "status": "done", "detail": "评估基于本地规则引擎 + 企业物料库，非 LLM 生成"},
            ],
        }
        # 0021：若关联候选，持久化合规检查结果（含未匹配场景）
        if req.candidate_id:
            from .experiment.candidate_artifact_store import CandidateArtifact
            app.state.candidate_artifact_store.upsert(CandidateArtifact(
                candidate_id=req.candidate_id,
                artifact_type="compliance",
                artifact_data=result,
            ))
            result["persisted"] = True
        return result

    # 等权 BOM（每个物料均分）
    weight = 1.0 / len(matched)
    bom = {m.material_id: weight for m in matched}

    # 2. 合规检查
    report = agent.compliance_node.evaluate(bom)

    # 3. 汇总结果
    checks = []
    # SMARTS 硬阻断
    smart_errors = [e for e in report.fatal_errors if "禁用结构" in e]
    checks.append({
        "name": "SMARTS 结构安全",
        "passed": len(smart_errors) == 0,
        "detail": "；".join(smart_errors) if smart_errors else "未发现禁用结构",
    })
    # REACH 合规
    reach_errors = [e for e in report.fatal_errors if "REACH" in e]
    reach_warnings = [w for w in report.warnings if "REACH" in w or "证据" in w]
    checks.append({
        "name": "REACH 合规",
        "passed": len(reach_errors) == 0,
        "detail": "；".join(reach_errors + reach_warnings) if (reach_errors or reach_warnings) else "所有物料符合 REACH",
    })
    # 成本熔断
    cost_errors = [e for e in report.fatal_errors if "成本熔断" in e]
    checks.append({
        "name": "成本控制",
        "passed": len(cost_errors) == 0,
        "detail": f"估算成本 {report.estimated_unit_cost:.2f} 元/kg" + (f"（{cost_errors[0]}）" if cost_errors else ""),
    })
    # 毒性 / EHS
    toxic_warnings = [w for w in report.warnings if "毒性" in w or "EHS" in w]
    checks.append({
        "name": "EHS 毒性",
        "passed": len(toxic_warnings) == 0,
        "detail": "；".join(toxic_warnings) if toxic_warnings else "无毒性风险",
    })

    # 综合得分：通过检查项数 / 总检查项数
    passed_count = sum(1 for c in checks if c["passed"])
    overall_score = passed_count / len(checks) if checks else 0.0

    # 供应链风险：基于匹配物料数量
    if len(matched) >= 3:
        supply_risk = "低"
    elif len(matched) == 2:
        supply_risk = "中"
    else:
        supply_risk = "高"

    result = {
        "overall_score": round(overall_score, 2),
        "estimated_cost": round(report.estimated_unit_cost, 2),
        "supply_risk": supply_risk,
        "checks": checks,
        # 执行过程透明化（#3）：步骤链 + 引擎说明
        "process": [
            {"step": "候选材料解析", "status": "done", "detail": f"化学式 {formula or '—'} / SMILES {smiles or '—'}"},
            {"step": "物料库匹配", "status": "done", "detail": f"匹配到 {len(matched)} 个物料：" + "、".join(m.material_id for m in matched[:6])},
            {"step": "合规规则检查", "status": "done", "detail": f"SMARTS 禁用结构 / REACH / 成本熔断 / EHS 毒性 共 {len(checks)} 项检查"},
            {"step": "成本与供应链评估", "status": "done", "detail": f"估算成本 {round(report.estimated_unit_cost, 2)} 元/kg，供应链风险：{supply_risk}"},
            {"step": "报告生成", "status": "done", "detail": "评估基于本地规则引擎 + 企业物料库，非 LLM 生成"},
        ],
    }
    # 0021：若关联候选，持久化合规检查结果
    if req.candidate_id:
        from .experiment.candidate_artifact_store import CandidateArtifact
        app.state.candidate_artifact_store.upsert(CandidateArtifact(
            candidate_id=req.candidate_id,
            artifact_type="compliance",
            artifact_data=result,
        ))
        result["persisted"] = True
    return result


@app.post("/raw-materials", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_raw_material(req: RawMaterialUpsertRequest):
    """新增物料规格。material_id 为空时自动生成 RM-xxx 格式。"""
    from .industrialization.raw_material_db import MaterialSpec
    import uuid as _uuid
    # 0727：inventory_unit 优先取请求值，空则从 MDM material_categories.default_unit 获取
    inv_unit = req.inventory_unit or ""
    if not inv_unit and req.category:
        try:
            from .mdm.master_data import MaterialCategoryStore
            cat_store = MaterialCategoryStore()
            cat = cat_store.get_by_code(req.category)
            if cat and cat.default_unit:
                inv_unit = cat.default_unit
        except Exception:
            # 查询失败与"主数据无默认单位"必须可区分，禁止静默吞掉后伪造单位
            logger.warning("MDM 物料类别默认单位查询失败 category=%s", req.category, exc_info=True)
    if not inv_unit:
        # 库存单位是主数据语义（影响库存统计与扣减口径），
        # 不得伪造默认值掩盖——要求调用方显式指定或先补齐 MDM 类别默认单位
        raise HTTPException(
            status_code=400,
            detail=(f"无法确定库存单位：请求未传 inventory_unit，"
                    f"且物料类别 {req.category or '(空)'} 在 MDM 中无 default_unit。"
                    f"请显式传入 inventory_unit 或先维护物料类别主数据"),
        )
    spec = MaterialSpec(
        material_id=req.material_id or f"RM-{_uuid.uuid4().hex[:6].upper()}",
        name=req.name,
        smiles=req.smiles,
        category=req.category,
        inventory_quantity=req.inventory_quantity,
        inventory_unit=inv_unit,
        unit_cost=req.unit_cost,
        supplier=req.supplier,
        reach_compliant=req.reach_compliant,
        is_toxic=req.is_toxic,
        batch_number=req.batch_number,
        expiry_date=req.expiry_date,
        coa_uri=req.coa_uri,
        sds_uri=req.sds_uri,
        test_report_uri=req.test_report_uri,
        test_institution=req.test_institution,
        test_date=req.test_date,
        min_order_quantity=req.min_order_quantity,
        version=1,
        updated_by=req.updated_by,
        update_reason=req.update_reason or "新增物料",
        data_source=req.data_source,
        prediction_meta=req.prediction_meta,
        properties=req.properties,
    )
    # 检查是否已存在
    if req.material_id and agent.raw_material_db.get_spec(req.material_id):
        raise HTTPException(status_code=409, detail=f"物料 {req.material_id} 已存在，请使用 PUT 编辑")
    agent.raw_material_db.upsert_spec(spec)
    return spec.model_dump()


@app.put("/raw-materials/{material_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_raw_material(material_id: str, req: RawMaterialUpsertRequest):
    """编辑物料规格。版本号自动递增，记录修改人与原因。

    部分更新：仅请求中显式传入的字段生效（exclude_unset），
    未传字段保留原值——修复此前数值/布尔字段被默认值静默清零的数据丢失。
    """
    from .industrialization.raw_material_db import MaterialSpec
    existing = agent.raw_material_db.get_spec(material_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"物料 {material_id} 不存在")
    _set = req.model_dump(exclude_unset=True)
    spec = MaterialSpec(
        material_id=material_id,
        name=_set.get("name") or existing.name,
        smiles=_set.get("smiles") or existing.smiles,
        category=_set.get("category") or existing.category,
        inventory_quantity=_set.get("inventory_quantity", existing.inventory_quantity),
        inventory_unit=_set.get("inventory_unit") or existing.inventory_unit or "",
        unit_cost=_set.get("unit_cost", existing.unit_cost),
        supplier=_set.get("supplier") or existing.supplier,
        reach_compliant=_set.get("reach_compliant", existing.reach_compliant),
        is_toxic=_set.get("is_toxic", existing.is_toxic),
        batch_number=_set.get("batch_number") or existing.batch_number,
        expiry_date=_set.get("expiry_date") or existing.expiry_date,
        coa_uri=_set.get("coa_uri") or existing.coa_uri,
        sds_uri=_set.get("sds_uri") or existing.sds_uri,
        test_report_uri=_set.get("test_report_uri") or existing.test_report_uri,
        test_institution=_set.get("test_institution") or existing.test_institution,
        test_date=_set.get("test_date") or existing.test_date,
        min_order_quantity=_set.get("min_order_quantity", existing.min_order_quantity),
        version=existing.version + 1,
        updated_by=req.updated_by,
        update_reason=req.update_reason or "编辑物料",
        data_source=_set.get("data_source") or existing.data_source,
        prediction_meta=_set.get("prediction_meta") or existing.prediction_meta,
        properties=_set.get("properties") if _set.get("properties") else existing.properties,
    )
    agent.raw_material_db.upsert_spec(spec)
    return spec.model_dump()


@app.delete("/raw-materials/{material_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_raw_material(material_id: str):
    """删除物料（2B 数据治理：被配方 BOM 引用的物料禁止删除，须先归档处理）。"""
    existing = agent.raw_material_db.get_spec(material_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"物料 {material_id} 不存在")
    # 引用检查：配方 BOM 明细引用了该物料则禁止删除
    # BOM formulation 结构：{materials: [{material_name, amount, role}], target_smiles}
    # 物料引用键为 material_name（物料库的 name 或 material_id 均可能）
    try:
        boms = app.state.bom_store.list_all()
    except Exception:  # noqa: BLE001 - BOM 存储不可用时放宽引用检查
        boms = []
    referenced_bom_ids = []
    for b in boms:
        form = b.formulation or {}
        materials = form.get("materials") or []
        hit = False
        for it in materials:
            nm = (it.get("material_name") or it.get("material") or "").strip()
            if nm and (nm == material_id or nm == existing.name):
                hit = True
                break
        if hit:
            referenced_bom_ids.append(b.bom_id or b.process_id or "")
    if referenced_bom_ids:
        raise HTTPException(
            status_code=409,
            detail=f"物料已被配方 {referenced_bom_ids[0]} 引用，无法删除；请先修改对应配方后再操作",
        )
    if not agent.raw_material_db.delete(material_id):
        raise HTTPException(status_code=404, detail=f"物料 {material_id} 不存在")
    return {"deleted": True, "material_id": material_id}


# ===========================================================================
# 物料申请审批流程 API（G2.2）
# ===========================================================================

class MaterialRequestCreateRequest(BaseModel):
    """提交物料申请。"""
    material_data: dict = Field(default_factory=dict)
    request_type: str = "add"  # add / update / delete
    requester: str = ""


class MaterialRequestReviewRequest(BaseModel):
    """审批物料申请。"""
    reviewed_by: str = ""
    review_comment: str = ""


@app.post("/material-requests", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_material_request(req: MaterialRequestCreateRequest):
    """提交物料申请（新增/修改/删除）。审批通过后才写入物料库。"""
    from .industrialization.material_request import MaterialRequest, get_request_store
    if req.request_type not in ("add", "update", "delete"):
        raise HTTPException(status_code=400, detail="request_type 必须为 add / update / delete")
    if not req.material_data:
        raise HTTPException(status_code=400, detail="material_data 不能为空")
    store = get_request_store()
    request = MaterialRequest(
        material_data=req.material_data,
        request_type=req.request_type,
        requester=req.requester,
    )
    saved = store.save(request)
    return saved.model_dump()


@app.get("/material-requests")
async def list_material_requests(status: str = ""):
    """查询物料申请列表，可选按状态筛选。"""
    from .industrialization.material_request import RequestStatus, get_request_store
    store = get_request_store()
    if status:
        try:
            req_status = RequestStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")
        all_reqs = store.list_all()
        items = [r for r in all_reqs if r.status == req_status]
    else:
        items = store.list_all()
    return {"requests": [r.model_dump() for r in items], "count": len(items)}


@app.post("/material-requests/{request_id}/approve", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def approve_material_request(request_id: str, req: MaterialRequestReviewRequest):
    """审批通过物料申请：自动写入物料库 + 创建版本快照。

    - add/update：将 material_data 写入物料库（版本号递增），创建版本快照
    - delete：从物料库删除该物料
    审批通过后状态置为 WRITTEN。
    """
    from .industrialization.material_request import RequestStatus, get_request_store
    from .industrialization.raw_material_db import MaterialSpec
    from .version_store import Version, VersionType, get_version_store

    store = get_request_store()
    request = store.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"申请 {request_id} 不存在")
    if request.status != RequestStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail=f"申请 {request_id} 当前状态为 {request.status.value}，无法审批")

    data = request.material_data or {}
    material_id = data.get("material_id", "")

    if request.request_type == "delete":
        if not material_id:
            raise HTTPException(status_code=400, detail="删除申请缺少 material_id")
        # 创建删除前快照
        existing = agent.raw_material_db.get_spec(material_id)
        if existing:
            vs = get_version_store()
            vs.save(Version(
                entity_type=VersionType.MATERIAL,
                entity_id=material_id,
                snapshot=existing.model_dump(),
                change_summary=f"物料申请 {request_id} 审批通过：删除前快照",
                created_by=req.reviewed_by or "system",
                is_active=False,
            ))
            # 通过 SQLAlchemy Engine 删除 industrialization.raw_materials 记录
            with agent.raw_material_db.engine.begin() as conn:
                conn.execute(
                    text(
                        "DELETE FROM industrialization.raw_materials WHERE material_id = :material_id"
                    ),
                    {"material_id": material_id},
                )
    else:
        # add / update：写入物料库
        # M12: 写入前校验必填字段
        validation_error = store.validate_material_data(data)
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error["error"])

        existing = agent.raw_material_db.get_spec(material_id) if material_id else None
        # M2: add 时检查物料ID是否已存在
        if request.request_type == "add" and existing:
            raise HTTPException(status_code=409, detail="物料ID已存在，请使用修改申请")
        version_num = (existing.version + 1) if existing else 1
        # float 转换防御：非法字符串转 400（此前 ValueError 500）
        try:
            inv_qty = float(data.get("inventory_quantity") or 0.0)
            u_cost = float(data.get("unit_cost") or 0.0)
            min_qty = float(data.get("min_order_quantity", 0.0) or 0.0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="inventory_quantity/unit_cost/min_order_quantity 必须为数值")
        spec = MaterialSpec(
            material_id=material_id or f"RM-{uuid.uuid4().hex[:6].upper()}",
            name=data.get("name", ""),
            smiles=data.get("smiles", ""),
            category=data.get("category", ""),
            inventory_quantity=inv_qty,
            unit_cost=u_cost,
            supplier=data.get("supplier", ""),
            reach_compliant=bool(data.get("reach_compliant", False)),
            is_toxic=bool(data.get("is_toxic", False)),
            batch_number=data.get("batch_number", ""),
            expiry_date=data.get("expiry_date", ""),
            coa_uri=data.get("coa_uri", ""),
            sds_uri=data.get("sds_uri", ""),
            test_report_uri=data.get("test_report_uri", ""),
            test_institution=data.get("test_institution", ""),
            test_date=data.get("test_date", ""),
            min_order_quantity=min_qty,
            version=version_num,
            updated_by=req.reviewed_by or request.requester,
            update_reason=data.get("update_reason", f"申请审批通过 {request_id}"),
            data_source=data.get("data_source", "measured"),
            prediction_meta=data.get("prediction_meta", {}),
        )
        agent.raw_material_db.upsert_spec(spec)

        # 创建版本快照（复用 VersionStore）
        vs = get_version_store()
        vs.save(Version(
            entity_type=VersionType.MATERIAL,
            entity_id=spec.material_id,
            snapshot=spec.model_dump(),
            change_summary=f"物料申请 {request_id} 审批通过：{request.request_type}",
            created_by=req.reviewed_by or "system",
            is_active=True,
        ))

    # 状态置为 WRITTEN
    updated = store.update_status(
        request_id, RequestStatus.WRITTEN,
        reviewed_by=req.reviewed_by,
        review_comment=req.review_comment or "审批通过，已写入物料库",
    )
    return updated.model_dump() if updated else {"status": "written", "request_id": request_id}


@app.post("/material-requests/{request_id}/reject", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def reject_material_request(request_id: str, req: MaterialRequestReviewRequest):
    """审批驳回物料申请。"""
    from .industrialization.material_request import RequestStatus, get_request_store
    store = get_request_store()
    request = store.get(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"申请 {request_id} 不存在")
    if request.status != RequestStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail=f"申请 {request_id} 当前状态为 {request.status.value}，无法审批")
    updated = store.update_status(
        request_id, RequestStatus.REJECTED,
        reviewed_by=req.reviewed_by,
        review_comment=req.review_comment or "审批驳回",
    )
    return updated.model_dump() if updated else {"status": "rejected", "request_id": request_id}


# --- 通用 MCP 工具调用端点 ---

class MCPToolCallRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


@app.post("/mcp/tools/{tool_name}/call", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def call_mcp_tool(tool_name: str, req: MCPToolCallRequest, request: Request):
    """通用 MCP 工具调用入口。

    支持 design_formula / route_material / generate_crystal_candidates 等所有已注册工具。
    通过 Agent 工具注册表（MCPToolRegistry）调用，确保走 handler 链路；同时写入审计日志便于追溯。
    """
    user = getattr(request.state, "current_user", None)
    user_id = user.user_id if user else "anonymous"
    try:
        # 记录工具调用审计（who/what/when），便于追溯直接 API 调用工具的行为
        try:
            get_audit_logger().log(AuditEntry(
                event_type="tool_call",
                module="mcp_tools",
                action=tool_name,
                detail={"user_id": user_id, "arguments_keys": list(req.arguments.keys())},
                confirmed=True,
            ))
        except Exception:
            logger.debug("mcp tool call audit log failed", exc_info=True)
        result = agent.tools.execute(tool_name, **req.arguments)
        # 工具内部捕获异常后以 {"error": ...} 返回时，转为 HTTP 500，
        # 避免调用方把失败结果误判为成功（如 design_formula 生成失败）
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=500, detail=f"工具执行失败: {result['error']}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"工具 {tool_name} 未注册或无 handler: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工具执行失败: {e}")


# --- 配方与工艺版本管理 ---

def _user_name_from_request(request: Request) -> str:
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return user.display_name or user.username or user.user_id
    return "system"


@app.post("/formulas", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_formula(request: Request):
    """保存配方新版本，或基于目标材料自动生成配方草案。

    支持两种请求体：
    1. auto_draft=true：{target_material: {formula, smiles, name}, auto_draft: true}
       → 调用 FormulaAgent 生成 BOM/BOP/成本/EHS 并保存为配方版本
    2. 标准 FormulaVersion 字段：直接保存配方版本（若传 formula_id 则追加版本）
    """
    body = await request.json()

    store = get_formula_store()

    if body.get("auto_draft"):
        target_info = body.get("target_material") or {}
        if not isinstance(target_info, dict):
            target_info = {"candidate": str(target_info)}
        target_name = (
            target_info.get("name")
            or target_info.get("formula")
            or target_info.get("smiles")
            or ""
        )
        try:
            quantity = float(body.get("quantity") or body.get("quantity_kg") or 1.0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantity 必须为数值")

        # 计算输入参数哈希快照（用于 AI 输出溯源）
        input_snapshot_hash = _compute_input_snapshot({
            "target_material": body.get("target_material"),
            "auto_draft": True,
            "quantity": body.get("quantity") or body.get("quantity_kg") or 1.0,
        })

        # 通过 Agent 工具注册表调用 design_formula（不直接调用 agent 私有方法）
        result = agent.tools.execute(
            "design_formula", target_material=target_info, quantity=quantity
        )
        if "error" in result:
            raise HTTPException(
                status_code=500,
                detail=f"配方草案生成失败：{result['error']}",
            )

        # 补充 ai_meta（用于 AI 输出溯源）
        from datetime import datetime as _dt, timezone
        result.setdefault("ai_meta", {})["input_snapshot_hash"] = input_snapshot_hash
        result.setdefault("ai_meta", {})["model_version"] = "internlm-v1"
        result.setdefault("ai_meta", {})["generated_at"] = _dt.now(timezone.utc).isoformat()

        formula = FormulaVersion(
            target_material=target_name,
            quantity=quantity,
            bom=result.get("bom", []),
            bop=result.get("bop", []),
            ehs=result.get("ehs", {}),
            material_cost=result.get("material_cost", 0.0),
            process_cost=result.get("process_cost", 0.0),
            total_unit_cost=result.get("total_unit_cost") or result.get("total_cost_per_kg") or 0.0,
            process_cost_breakdown=result.get("process_cost_breakdown", []),
            change_summary=body.get("change_summary") or "自动生成配方草案",
            created_by=_user_name_from_request(request),
            # P1-2：持久化 AI 可信度元信息，前端统一展示
            ai_meta=result.get("ai_meta", {}),
        )
        saved = store.save(formula)
        return saved.model_dump()

    # 标准 FormulaVersion 保存路径
    req = FormulaVersion(**body)
    formula = req.model_copy(
        update={"created_by": req.created_by or _user_name_from_request(request)}
    )
    saved = store.save(formula)
    return saved.model_dump()


def _normalize_bom_item(item) -> dict:
    """将 BOM 项归一化为前端 bomColumns 期望的格式。

    dict key 不含单位（amount），单位由上下文 metadata 携带。
    旧格式（合成路径 reactants）：{role, amount, material_name}
    新格式（FormulaAgent 生成）：{material_id, material_name, cas_number, amount, unit_price, cost, supplier, in_stock}
    """
    if not isinstance(item, dict):
        return {"material_name": str(item), "amount": 0, "unit_price": 0, "cost": 0, "in_stock": False}
    # 已是新格式
    if "amount" in item or "material_id" in item:
        return item
    # 旧格式转换
    return {
        "material_id": "",
        "material_name": item.get("material_name") or item.get("name") or "",
        "cas_number": "",
        "amount": 0,
        "unit_price": 0,
        "cost": 0,
        "supplier": "",
        "in_stock": False,
    }


def _normalize_bop_step(step, idx: int) -> dict:
    """将 BOP 步骤归一化为前端 bopColumns 期望的格式。

    dict key 不含单位（duration），单位由上下文 metadata 携带。
    旧格式（合成路径 steps）：{step:数字, conditions:"高温固相法 / 900°C / 6h / air", difficulty, reaction_type, reaction_smiles}
    新格式（FormulaAgent 生成）：{step:名称, equipment, temperature, duration, key_params}
    """
    if not isinstance(step, dict):
        return {"step": f"步骤{idx+1}", "equipment": "", "temperature": 0, "duration": 0, "key_params": ""}
    # 已是新格式
    if "equipment" in step or "duration" in step:
        return step
    # 旧格式转换：解析 conditions 字段 "反应类型 / 温度 / 时间 / 气氛"
    conditions = step.get("conditions") or ""
    parts = [p.strip() for p in conditions.split("/")]
    reaction_type = parts[0] if parts else (step.get("reaction_type") or "")
    temperature = 0
    duration = 0
    for p in parts[1:]:
        p_stripped = p.strip()
        # 先尝试解析时间（如 "6h", "12h", "0.5h"）
        if "h" in p_stripped.lower():
            num_str = p_stripped.lower().replace("h", "").strip()
            try:
                duration = float(num_str)
                continue
            except (ValueError, TypeError):
                pass
        # 再尝试解析温度（如 "900°C", "25°C"）
        p_clean = p_stripped.replace("°C", "").replace("°c", "").replace("℃", "").strip()
        try:
            temperature = float(p_clean)
        except (ValueError, TypeError):
            pass
    step_name = step.get("step")
    if isinstance(step_name, int):
        step_name = f"步骤{step_name}"
    elif not step_name:
        step_name = reaction_type or f"步骤{idx+1}"
    return {
        "step": str(step_name),
        "equipment": reaction_type,
        "temperature": temperature,
        "duration": duration,
        "key_params": conditions,
    }


def _bom_to_formula_view(bom, candidate=None, process_scheme=None) -> dict:
    """将 BomScheme 转换为 FormulaView dict（伪 FormulaVersion 形式）。

    用于在 /formulas 接口中聚合候选材料生成的 BOM，使前端"配方与工艺"
    页面无需改动即可展示。source="candidate_bom" 标识来源便于区分。

    0727 重构：从 BomScheme.formulation.materials / process_route.steps
    直接读取完整 BOM/BOP（对齐前端 bomColumns/bopColumns 字段），
    同时回填成本/EHS 字段供前端展示。
    0727 补丁：对旧格式数据（合成路径原始 reactants/steps）做归一化转换。
    """
    formulation = bom.formulation if isinstance(bom.formulation, dict) else {}
    raw_materials = formulation.get("materials") or []
    # 归一化 BOM 项（兼容旧格式）
    materials = [_normalize_bom_item(m) for m in raw_materials]
    process_route = bom.process_route if isinstance(bom.process_route, dict) else {}
    # BOP 优先从 process_route.steps 取（含完整字段），fallback 到 process_scheme.steps
    raw_bop = process_route.get("steps") or []
    if not raw_bop and process_scheme is not None and process_scheme.steps:
        raw_bop = process_scheme.steps
    # 归一化 BOP 步骤（兼容旧格式）
    bop = [_normalize_bop_step(s, i) for i, s in enumerate(raw_bop)]
    # 成本/EHS 从 process_route 取（0727 重构后已持久化）
    ehs = process_route.get("ehs") or {}
    material_cost = float(process_route.get("material_cost") or 0.0)
    process_cost = float(process_route.get("process_cost") or 0.0)
    total_unit_cost = float(process_route.get("total_unit_cost") or 0.0)
    process_cost_breakdown = process_route.get("process_cost_breakdown") or []
    target = ""
    project_id = ""
    task_id = bom.task_id or ""
    if candidate is not None:
        target = getattr(candidate, "name", "") or bom.candidate_id
        project_id = getattr(candidate, "project_id", "") or ""
        if not task_id:
            task_id = getattr(candidate, "task_id", "") or ""
    else:
        target = bom.candidate_id
    return {
        "formula_id": bom.bom_id,
        "version_id": bom.bom_id,  # BOM 单版本，复用 ID
        "version_number": 1,
        "target_material": target,
        "quantity": 1.0,
        "bom": materials,
        "bop": bop,
        "ehs": ehs,
        "material_cost": material_cost,
        "process_cost": process_cost,
        "total_unit_cost": total_unit_cost,
        "process_cost_breakdown": process_cost_breakdown,
        "created_by": bom.created_by,
        "created_at": bom.created_at,
        "change_summary": f"从合成路径 {bom.source_route_id} 生成",
        "is_active": bom.status == "active",
        "scenario_id": "",
        # 以下额外字段用于前端区分来源与反查
        "source": "candidate_bom",
        "bom_id": bom.bom_id,
        "candidate_id": bom.candidate_id,
        "project_id": project_id,
        "task_id": task_id,
        "source_route_id": bom.source_route_id,
        "source_synthesis_task_id": bom.source_synthesis_task_id,
        "process_id": bom.process_id,
        "name": bom.name,
    }


@app.get("/formulas")
async def list_formulas(target_material: str = ""):
    """列出配方活跃版本，可为目标材料过滤。

    0021 后聚合 BomStore 数据：候选材料从合成路径生成的 BOM 也在此返回，
    通过 source="candidate_bom" 字段标识来源，便于前端区分展示。
    """
    store = get_formula_store()
    formulas = store.list_all(target_material=target_material or None)
    formula_dicts = [f.model_dump() for f in formulas]

    # 聚合 BomStore（候选材料生成 BOM）
    try:
        bom_store = app.state.bom_store
        boms = bom_store.list_all()
        # 预取 candidate 与 process_scheme，避免 N+1
        cand_cache: dict[str, Any] = {}
        proc_cache: dict[str, Any] = {}
        for b in boms:
            if b.candidate_id and b.candidate_id not in cand_cache:
                cand_cache[b.candidate_id] = app.state.candidate_store.get(b.candidate_id)
            if b.process_id and b.process_id not in proc_cache:
                proc_cache[b.process_id] = app.state.process_scheme_store.get(b.process_id)
            elif not b.process_id:
                # 兜底：按 bom_id 反查
                proc_cache.setdefault(b.bom_id, app.state.process_scheme_store.get_by_bom(b.bom_id))
        for b in boms:
            cand = cand_cache.get(b.candidate_id)
            # process_scheme 优先按 process_id 取，否则按 bom_id 取
            proc = proc_cache.get(b.process_id) if b.process_id else proc_cache.get(b.bom_id)
            fv = _bom_to_formula_view(b, candidate=cand, process_scheme=proc)
            # target_material 过滤
            if target_material and target_material.lower() not in (fv["target_material"] or "").lower():
                continue
            formula_dicts.append(fv)
    except Exception as exc:  # noqa: BLE001
        logger.warning("聚合 BomStore 数据到 /formulas 失败: %s", exc)

    return {"formulas": formula_dicts, "count": len(formula_dicts)}


@app.get("/formulas/{formula_id}")
async def get_formula(formula_id: str, version_id: str = ""):
    """获取配方最新或指定版本。

    0021 后支持 BOM- 前缀 ID：若 FormulaStore 找不到，回退查 BomStore。
    """
    store = get_formula_store()
    formula = store.get(formula_id, version_id=version_id or None)
    if formula is not None:
        return formula.model_dump()

    # 回退查 BomStore（候选材料生成 BOM）
    try:
        bom = app.state.bom_store.get(formula_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("回退查 BomStore 失败 formula_id=%s: %s", formula_id, exc)
        bom = None
    if bom is None:
        raise HTTPException(status_code=404, detail=f"配方 {formula_id} 不存在")
    cand = app.state.candidate_store.get(bom.candidate_id) if bom.candidate_id else None
    proc = None
    if bom.process_id:
        proc = app.state.process_scheme_store.get(bom.process_id)
    if proc is None:
        proc = app.state.process_scheme_store.get_by_bom(bom.bom_id)
    return _bom_to_formula_view(bom, candidate=cand, process_scheme=proc)


@app.get("/formulas/{formula_id}/history")
async def get_formula_history(formula_id: str):
    """获取配方全部历史版本。"""
    store = get_formula_store()
    history = store.list_history(formula_id)
    return {"formula_id": formula_id, "versions": [f.model_dump() for f in history], "count": len(history)}


@app.post("/formulas/{formula_id}/versions/{version_id}/activate", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def activate_formula_version(
    formula_id: str,
    version_id: str,
    payload: dict | None = Body(None),
    current: User | None = Depends(get_current_user),
    request: Request = None,
):
    """将指定版本设为配方当前活跃版本。"""
    ai_initiated = bool(payload.get("ai_initiated")) if payload else False
    # T-031：AI 发布配方需先经 Committee 人工确认（三段式：提交→审核→放行）
    # 服务端判定优先：验签 Agent 凭证 > 请求体自报标志
    if _is_ai_initiated(request, ai_initiated):
        return _require_high_risk_review_or_raise(
            "auto_publish_formula",
            {"formula_id": formula_id, "version_id": version_id, **(payload or {})},
            initiator="ai",
        )
    store = get_formula_store()
    formula = store.set_active(formula_id, version_id)
    if formula is None:
        raise HTTPException(status_code=404, detail="配方或版本不存在")
    # 发布即审计：操作者绑定登录身份（payload 自报不作为审计主体）
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="formula",
            action="activate_version",
            detail={"formula_id": formula_id, "version_id": version_id},
            operator=(current.username if current else "") or "unknown",
            confirmed=True,
            resource_type="formula",
            resource_id=formula_id,
        ))
    except Exception:
        logger.warning("配方激活审计写入失败 formula_id=%s", formula_id, exc_info=True)
    return formula.model_dump()


# --- 分子结构图谱 ---

@app.get("/molecule/svg")
async def molecule_svg(smiles: str = Query(..., description="SMILES 字符串")):
    """用 RDKit 生成 2D 分子结构 SVG 图谱。"""
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise HTTPException(status_code=400, detail=f"无效的 SMILES: {smiles}")

    drawer = rdMolDraw2D.MolDraw2DSVG(300, 200)
    opts = drawer.drawOptions()
    opts.clearBackground = False
    opts.bondLineWidth = 2
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/molecule/sdf")
async def molecule_sdf(smiles: str = Query(..., description="SMILES 字符串")):
    """用 RDKit 生成 3D 分子结构 SDF（用于 3Dmol.js 降级渲染）。"""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise HTTPException(status_code=400, detail=f"无效的 SMILES: {smiles}")

    mol = Chem.AddHs(mol)
    # 3D 嵌入可能失败（大分子/聚合物/复杂环系会触发 Invariant Violation）
    try:
        params = AllChem.ETKDGv3()
        params.useRandomCoords = True  # 对复杂分子更稳健
        if AllChem.EmbedMolecule(mol, params) != 0:
            raise RuntimeError("EmbedMolecule 返回非零")
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:
            pass  # 优化失败不影响已有 3D 坐标
    except Exception as e:
        # 降级：用 2D 坐标生成伪 3D（至少能展示原子连接关系）
        try:
            AllChem.Compute2DCoords(mol)
        except Exception:
            pass
        # 仍允许返回，但带 warning（前端可识别）
        sdf = Chem.MolToMolBlock(mol)
        if not sdf:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "sdf_generation_failed",
                    "message": f"无法为该 SMILES 生成 3D 结构：{e}",
                    "smiles": smiles,
                    "hint": "该分子可能过于复杂或不适合 3D 嵌入，建议查看 2D 结构",
                },
            )
        return Response(content=sdf, media_type="chemical/x-mdl-sdfile")

    sdf = Chem.MolToMolBlock(mol)
    return Response(content=sdf, media_type="chemical/x-mdl-sdfile")


# --- 材料属性字段管理 ---

from .material_properties import get_registry, PropertyField

_property_registry = get_registry()


class CustomFieldRequest(BaseModel):
    # 键名必须以字母开头，仅含字母/数字/下划线，长度 1-64
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    label_cn: str = Field(min_length=1, max_length=64)
    label_en: str = Field(default="", max_length=128)
    unit: str = Field(default="", max_length=32)
    # Literal 自动限制枚举并生成 OpenAPI schema 枚举
    value_type: Literal["float", "int", "str", "list", "dict"] = "float"
    description: str = Field(default="", max_length=512)
    category: str = "custom"

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        # 分类须在 registry 中存在，但此处仅做格式校验，存在性由端点检查
        v = (v or "").strip()
        if not v:
            raise ValueError("category 不能为空")
        if len(v) > 64 or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("category 格式非法（仅允许字母/数字/下划线/连字符）")
        return v


@app.get("/properties/categories")
async def list_property_categories():
    """列出所有属性分类及其字段。"""
    cats = _property_registry.list_categories()
    return {
        "categories": [c.model_dump() for c in cats],
        "count": len(cats),
    }


@app.get("/properties/fields")
async def list_property_fields(category: str = "", usable_in: str = ""):
    """列出属性字段（扁平列表）。

    可选查询参数：
    - category: 按分类过滤（identification/physicochemical/safety/classification/battery/custom）
    - usable_in: 按用途过滤（predictable/ecml_target/experimental/identification）
    """
    if usable_in == "predictable":
        keys = _property_registry.get_predictable_keys()
        fields = [_property_registry.get_field(k) for k in keys]
        fields = [f for f in fields if f is not None]
    elif usable_in == "ecml_target":
        keys = _property_registry.get_ecml_target_keys()
        fields = [_property_registry.get_field(k) for k in keys]
        fields = [f for f in fields if f is not None]
    elif usable_in == "experimental":
        keys = _property_registry.get_experimental_keys()
        fields = [_property_registry.get_field(k) for k in keys]
        fields = [f for f in fields if f is not None]
    elif category:
        cat = _property_registry.get_category(category)
        fields = cat.fields if cat else []
    else:
        fields = _property_registry.list_all_fields()
    return {
        "fields": [f.model_dump() for f in fields],
        "count": len(fields),
    }


@app.get("/properties/options")
async def property_select_options(usable_in: str = "predictable"):
    """返回前端下拉选项格式（label/value）。"""
    if usable_in == "predictable":
        keys = _property_registry.get_predictable_keys()
    elif usable_in == "ecml_target":
        keys = _property_registry.get_ecml_target_keys()
    elif usable_in == "experimental":
        keys = _property_registry.get_experimental_keys()
    else:
        keys = _property_registry.get_predictable_keys()
    return {"options": _property_registry.to_select_options(keys), "count": len(keys)}


@app.get("/properties/stats")
async def property_stats():
    """返回属性字段统计信息。"""
    return _property_registry.get_stats()


@app.post("/properties/custom", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def add_custom_field(req: CustomFieldRequest):
    """添加自定义属性字段（可指定分类，默认 custom）。"""
    # 校验分类存在（custom 分类始终存在，其它需在 registry 中注册）
    if req.category != "custom" and not _property_registry.get_category(req.category):
        raise HTTPException(status_code=400, detail=f"分类 '{req.category}' 不存在")
    field = PropertyField(
        key=req.key,
        label_cn=req.label_cn,
        label_en=req.label_en,
        category=req.category,
        unit=req.unit,
        value_type=req.value_type,
        description=req.description,
        is_custom=True,
    )
    ok = _property_registry.add_custom_field(field)
    if not ok:
        raise HTTPException(status_code=400, detail=f"字段 '{req.key}' 已存在")
    return {"ok": True, "field": field.model_dump()}


@app.delete("/properties/custom/{key}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def remove_custom_field(key: str = FastApiPath(..., pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")):
    """删除自定义属性字段。"""
    ok = _property_registry.remove_custom_field(key)
    if not ok:
        raise HTTPException(status_code=404, detail=f"自定义字段 '{key}' 不存在或不可删除")
    return {"ok": True}


# ===========================================================================
# 物料类型属性模板（属性字典闭环）
# ===========================================================================

@app.get("/properties/material-type-templates")
async def list_material_type_templates():
    """列出所有物料类型关联的属性字段模板。"""
    templates = agent.raw_material_db.list_material_type_templates()
    return {"templates": templates, "count": len(templates)}


@app.get("/properties/material-type-templates/{material_type}")
async def get_material_type_template(material_type: str):
    """获取指定物料类型关联的属性字段 key 列表。"""
    field_keys = agent.raw_material_db.get_material_type_template(material_type)
    fields = []
    for k in field_keys:
        f = _property_registry.get_field(k)
        if f:
            fields.append(f.model_dump())
    return {
        "material_type": material_type,
        "field_keys": field_keys,
        "fields": fields,
        "count": len(fields),
    }


class MaterialTypeTemplateRequest(BaseModel):
    """设置物料类型属性模板请求。"""
    field_keys: list[str] = Field(default_factory=list)


@app.put("/properties/material-type-templates/{material_type}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def set_material_type_template(material_type: str, req: MaterialTypeTemplateRequest):
    """设置物料类型关联的属性字段 key 列表。"""
    # 校验字段 key 必须在属性字典中存在
    invalid = [k for k in req.field_keys if not _property_registry.is_supported(k)]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"以下字段在属性字典中不存在: {', '.join(invalid)}"
        )
    agent.raw_material_db.set_material_type_template(material_type, req.field_keys)
    return {"ok": True, "material_type": material_type, "field_keys": req.field_keys}


# ===========================================================================
# 属性字段模板（按实验类型）
# ===========================================================================

# 实验类型 → 表单字段模板映射
_EXPERIMENT_TYPE_TEMPLATES: dict[str, list[dict]] = {
    # ── 改性塑料领域测试模板（v4.1：全系统切换改性塑料，替换电池电化学模板） ──
    "tensile": [
        {"key": "tensile_strength", "label_cn": "拉伸强度", "value_type": "float", "unit": "MPa", "required": True},
        {"key": "elongation_at_break", "label_cn": "断裂伸长率", "value_type": "float", "unit": "%", "required": False},
        {"key": "tensile_modulus", "label_cn": "拉伸模量", "value_type": "float", "unit": "MPa", "required": False},
        {"key": "test_speed", "label_cn": "测试速度", "value_type": "float", "unit": "mm/min", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 1040", "ISO 527", "ASTM D638"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "impact": [
        {"key": "impact_strength", "label_cn": "冲击强度", "value_type": "float", "unit": "kJ/m²", "required": True},
        {"key": "notch_type", "label_cn": "缺口类型", "value_type": "str", "unit": "", "required": False, "options": ["无缺口", "A 型缺口", "C 型缺口"]},
        {"key": "test_temperature", "label_cn": "测试温度", "value_type": "float", "unit": "°C", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 1843", "ISO 180", "ASTM D256"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "flexural": [
        {"key": "flexural_modulus", "label_cn": "弯曲模量", "value_type": "float", "unit": "MPa", "required": True},
        {"key": "flexural_strength", "label_cn": "弯曲强度", "value_type": "float", "unit": "MPa", "required": False},
        {"key": "test_speed", "label_cn": "测试速度", "value_type": "float", "unit": "mm/min", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 9341", "ISO 178", "ASTM D790"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "hdt": [
        {"key": "heat_deflection_temp", "label_cn": "热变形温度", "value_type": "float", "unit": "°C", "required": True},
        {"key": "load_stress", "label_cn": "载荷应力", "value_type": "float", "unit": "MPa", "required": False, "options": []},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 1634", "ISO 75", "ASTM D648"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "mfi": [
        {"key": "melt_flow_index", "label_cn": "熔体流动速率", "value_type": "float", "unit": "g/10min", "required": True},
        {"key": "test_temperature", "label_cn": "测试温度", "value_type": "float", "unit": "°C", "required": False},
        {"key": "test_load", "label_cn": "载荷", "value_type": "float", "unit": "kg", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 3682", "ISO 1133", "ASTM D1238"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "flame_retardancy": [
        {"key": "flame_retardancy", "label_cn": "阻燃等级", "value_type": "str", "unit": "", "required": True, "options": ["V-0", "V-1", "V-2", "HB"]},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 2408", "UL94", "ISO 1210"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "density": [
        {"key": "density", "label_cn": "密度", "value_type": "float", "unit": "g/cm³", "required": True},
        {"key": "test_temperature", "label_cn": "测试温度", "value_type": "float", "unit": "°C", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 1033", "ISO 1183", "ASTM D792"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "dsc": [
        {"key": "glass_transition_temp", "label_cn": "玻璃化转变温度", "value_type": "float", "unit": "°C", "required": False},
        {"key": "melting_point", "label_cn": "熔点", "value_type": "float", "unit": "°C", "required": False},
        {"key": "crystallinity", "label_cn": "结晶度", "value_type": "float", "unit": "%", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 19466", "ISO 11357"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "tga": [
        {"key": "thermal_stability", "label_cn": "热稳定温度（5% 失重）", "value_type": "float", "unit": "°C", "required": True},
        {"key": "weight_loss", "label_cn": "失重率", "value_type": "float", "unit": "%", "required": False},
        {"key": "residual_mass", "label_cn": "残余质量", "value_type": "float", "unit": "%", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["GB/T 33047", "ISO 11358"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "xrd": [
        {"key": "crystallinity", "label_cn": "结晶度", "value_type": "float", "unit": "%", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["XRD"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
    "sem": [
        {"key": "filler_dispersion", "label_cn": "填料分散性评价", "value_type": "str", "unit": "", "required": False},
        {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False, "options": ["SEM"]},
        {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
    ],
}

# 元数据字段（所有实验类型通用）
_COMMON_META_FIELDS: list[dict] = [
    {"key": "sample_id", "label_cn": "样品 ID", "value_type": "str", "unit": "", "required": True},
    {"key": "sample_batch_id", "label_cn": "批次 ID", "value_type": "str", "unit": "", "required": False},
    {"key": "uploaded_by", "label_cn": "录入人", "value_type": "str", "unit": "", "required": False},
    {"key": "raw_file_uri", "label_cn": "原始数据文件", "value_type": "file", "unit": "", "required": False},
]


@app.get("/properties/templates/{experiment_type}")
async def get_property_template(experiment_type: str):
    """按实验类型返回字段模板。
    
    如 ionic_conductivity 类型返回 [离子电导率, 测试温度, 测试方法, 仪器编号] 等字段。
    如果实验类型不在预定义列表中，返回通用模板（所有实验可测量字段）。
    """
    template = _EXPERIMENT_TYPE_TEMPLATES.get(experiment_type)
    if template is None:
        # 回退：使用 PropertyRegistry 的实验可测量字段
        experimental_keys = _property_registry.get_experimental_keys()
        fields = []
        for k in experimental_keys:
            f = _property_registry.get_field(k)
            if f:
                fields.append({
                    "key": f.key,
                    "label_cn": f.label_cn,
                    "value_type": f.value_type,
                    "unit": f.unit,
                    "required": False,
                })
        template = fields + [
            {"key": "test_method", "label_cn": "测试方法", "value_type": "str", "unit": "", "required": False},
            {"key": "instrument_id", "label_cn": "仪器编号", "value_type": "str", "unit": "", "required": False},
        ]
    return {
        "experiment_type": experiment_type,
        "fields": template,
        "meta_fields": _COMMON_META_FIELDS,
        "count": len(template),
    }


@app.get("/properties/templates")
async def list_property_templates():
    """列出所有实验类型及其模板。"""
    return {
        "experiment_types": list(_EXPERIMENT_TYPE_TEMPLATES.keys()),
        "count": len(_EXPERIMENT_TYPE_TEMPLATES),
    }


class CrossScaleRequest(BaseModel):
    material_type: str = "crystal"  # crystal / molecule
    formula: str = ""
    smiles: str = ""
    scales: list[str] = ["molecular", "reaction", "continuum"]
    # 0727：允许前端显式指定预测模型（覆盖系统设置中的默认值）
    model_type: str | None = None
    # 0727：允许前端指定由哪个有 property_prediction 能力的 agent 执行
    agent_id: str | None = None
    # 0021：关联候选材料 ID，用于持久化跨尺度预测结果到 candidate_artifacts
    candidate_id: str = ""


@app.post("/properties/cross_scale", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def cross_scale_predict(req: CrossScaleRequest):
    """跨尺度建模：分子性质 → 反应过程 → 多物理场串联。"""
    from .cross_scale.engine import CrossScaleEngine

    valid_scales = {"molecular", "reaction", "continuum"}
    scales = [s for s in req.scales if s in valid_scales]
    if not scales:
        raise HTTPException(status_code=400, detail="scales 至少包含一个有效值: molecular/reaction/continuum")

    material = {
        "type": req.material_type,
        "formula": req.formula,
        "smiles": req.smiles,
    }
    if req.material_type not in ("crystal", "molecule"):
        raise HTTPException(status_code=400, detail="material_type 必须为 crystal 或 molecule")

    # 若前端指定了模型类型，临时切换 predictor 的 model_type（仅本次请求）
    a = app.state.agent
    overridden = False
    original_model_type = None
    if req.model_type:
        predictor = a.crystal_predictor if req.material_type == "crystal" else a.polymer_predictor
        supported = getattr(predictor, "SUPPORTED_MODELS", None) or []
        if supported and req.model_type in supported:
            original_model_type = predictor.model_type
            predictor.model_type = req.model_type
            overridden = True
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的模型类型: {req.model_type}，可选: {supported}",
            )

    # 若前端指定了 agent_id，校验该 agent 是否具备 property_prediction 能力
    a_actual_id: str | None = None
    a_actual_name: str | None = None
    if req.agent_id:
        try:
            _require_agent_team()
            agent_def = _registry.get_agent(req.agent_id)
            if agent_def is None:
                raise HTTPException(status_code=404, detail=f"未找到 agent: {req.agent_id}")
            caps = agent_def.capabilities or []
            if "property_prediction" not in caps:
                raise HTTPException(
                    status_code=400,
                    detail=f"agent {req.agent_id} 不具备 property_prediction 能力",
                )
            # 用实际 agent id 回填，避免前端传入空值
            a_actual_id = agent_def.id or req.agent_id
            # 可读展示名（供 result.executed_by 使用，避免向前端暴露内部标识符）
            a_actual_name = agent_def.name or a_actual_id
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # agent_team 未启用时不阻断，仅记录日志
            import logging
            a_actual_id = req.agent_id
            a_actual_name = req.agent_id
            logging.getLogger(__name__).warning("agent_id 校验跳过: %s", exc)

    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "material_type": req.material_type,
        "formula": req.formula,
        "smiles": req.smiles,
        "scales": req.scales,
        "model_type": req.model_type,
        "candidate_id": req.candidate_id,
    })

    try:
        engine = CrossScaleEngine(agent=a)
        result = await engine.run_cross_scale(material, scales, agent_id=a_actual_id)
        # executed_by 保持稳定 agent 标识符（与合成等其他路径一致），
        # 可读展示名单独用 executed_by_name 提供，避免同一字段语义分叉
        if a_actual_name:
            result["executed_by_name"] = a_actual_name
    finally:
        # 恢复原来的 model_type，避免污染全局状态
        if overridden:
            predictor.model_type = original_model_type

    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    if not isinstance(result, dict):
        result = {"value": result}
    result.setdefault("ai_meta", {})["input_snapshot_hash"] = input_snapshot_hash
    result.setdefault("ai_meta", {})["model_version"] = "internlm-v1"
    result.setdefault("ai_meta", {})["generated_at"] = _dt.now(timezone.utc).isoformat()

    # 0021：若关联候选，持久化预测结果到 candidate_artifacts
    if req.candidate_id and result is not None:
        from .experiment.candidate_artifact_store import CandidateArtifact
        try:
            app.state.candidate_artifact_store.upsert(CandidateArtifact(
                candidate_id=req.candidate_id,
                artifact_type="prediction",
                artifact_data=result if isinstance(result, dict) else {"value": result},
            ))
            if isinstance(result, dict):
                result["persisted"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("持久化预测结果失败 candidate_id=%s: %s", req.candidate_id, exc)
    return result


# ── 跨尺度求解异步任务（真实 LAMMPS/FEniCSx 通常耗时较长，走异步+轮询） ──
from collections import OrderedDict as _ODict_for_cross_scale      # noqa: E402
_cross_scale_tasks: _ODict_for_cross_scale = _ODict_for_cross_scale()  # noqa: E402


def _set_cross_scale_status(task_id: str, status: str, progress: int = 0,
                            step_label: str = "", result: dict | None = None,
                            error: str = ""):
    from datetime import datetime as _dt2, timezone as _tz2
    _cross_scale_tasks[task_id] = {
        "task_id": task_id,
        "status": status,  # pending / running / completed / failed
        "progress": progress,
        "step_label": step_label,
        "result": result,
        "error": error,
        "updated_at": _dt2.now(_tz2.utc).isoformat(),
    }
    _cross_scale_tasks.move_to_end(task_id)
    while len(_cross_scale_tasks) > 200:
        _cross_scale_tasks.popitem(last=False)


@app.post("/properties/cross_scale/async", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def cross_scale_predict_async(req: CrossScaleRequest):
    """异步提交跨尺度建模任务，立即返回 task_id 供前端轮询。

    与同步版本一致地解析 material/scales/agent，但执行放到后台任务，
    真实 LAMMPS/FEniCSx 求解在中途完成时更新进度。
    """
    import uuid as _uuid
    task_id = f"csx-{_uuid.uuid4().hex[:12]}"
    _set_cross_scale_status(task_id, "pending", progress=0, step_label="队列中…")

    async def _bg_cross_scale():
        from .cross_scale.engine import CrossScaleEngine
        try:
            valid_scales = {"molecular", "reaction", "continuum"}
            scales = [s for s in req.scales if s in valid_scales]
            if not scales:
                raise ValueError("scales 至少包含一个有效值")

            material = {
                "type": req.material_type,
                "formula": req.formula,
                "smiles": req.smiles,
            }
            if req.material_type not in ("crystal", "molecule"):
                raise ValueError("material_type 必须为 crystal 或 molecule")

            _set_cross_scale_status(task_id, "running", progress=10, step_label="构造跨尺度引擎…")
            a = app.state.agent

            overridden = False
            original_model_type = None
            if req.model_type:
                predictor = a.crystal_predictor if req.material_type == "crystal" else a.polymer_predictor
                supported = getattr(predictor, "SUPPORTED_MODELS", None) or []
                if req.model_type in supported:
                    original_model_type = predictor.model_type
                    predictor.model_type = req.model_type
                    overridden = True

            a_actual_id: str | None = None
            if req.agent_id:
                try:
                    _require_agent_team()
                    agent_def = _registry.get_agent(req.agent_id)
                    if agent_def is not None and "property_prediction" in (agent_def.capabilities or []):
                        a_actual_id = agent_def.id or req.agent_id
                except Exception:  # noqa: BLE001
                    a_actual_id = req.agent_id

            try:
                engine = CrossScaleEngine(agent=a)
                solver_status = engine.solver_status()
                _set_cross_scale_status(
                    task_id, "running", progress=30,
                    step_label=f"求解器：LAMMPS={'可用' if solver_status['lammps']['available'] else '降级'}，"
                               f"FEniCSx={'可用' if solver_status['fenicsx']['available'] else '降级'}",
                )
                result = await engine.run_cross_scale(material, scales, agent_id=a_actual_id)
                _set_cross_scale_status(task_id, "completed", progress=100,
                                        step_label="跨尺度建模完成", result=result)
            finally:
                if overridden:
                    predictor.model_type = original_model_type
        except Exception as exc:  # noqa: BLE001
            _set_cross_scale_status(task_id, "failed", error=str(exc)[:500])

    _spawn_background(_bg_cross_scale())
    return {"task_id": task_id, "status": "pending"}


@app.get("/properties/cross_scale/status", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def cross_scale_status(task_id: str):
    """轮询跨尺度异步任务状态。"""
    entry = _cross_scale_tasks.get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未找到跨尺度任务: {task_id}")
    return entry



# --- Workflow Schema ---

@app.get("/workflow/schema")
async def get_workflow_schema():
    """返回当前工作流定义。"""
    loader = get_schema_loader()
    return loader.to_dict()


@app.get("/workflow/nodes")
async def get_workflow_nodes():
    """返回工作流节点列表。"""
    loader = get_schema_loader()
    return loader.get_nodes()


@app.get("/workflow/states/{category}")
async def get_workflow_states(category: str):
    """返回指定分类的状态列表。"""
    loader = get_schema_loader()
    return loader.get_states(category)


# ===========================================================================
# 实验任务单 API
# ===========================================================================

def _resolve_candidate_formula_smiles(candidate_id: str) -> tuple[str, str]:
    """从 ECML 运行记录中按 candidate_id 反查真实 formula / smiles。

    candidate_id 是候选标识（如 CAND-XXXXXXXX），不应直接当作化学式使用。
    遍历最近的 ECML 运行状态，匹配 candidates 列表中的 candidate_id / id 字段。
    """
    if not candidate_id:
        return "", ""
    _agent = getattr(app.state, "agent", None) or agent
    if _agent is None or getattr(_agent, "ecml", None) is None:
        return "", ""
    state_store = getattr(_agent.ecml, "state_store", None)
    if state_store is None:
        return "", ""
    try:
        for run in state_store.list_runs(limit=50):
            state = state_store.load(run.get("run_id", ""))
            if state is None:
                continue
            for c in state.candidates:
                cid = c.get("candidate_id") or c.get("id") or ""
                if cid == candidate_id:
                    return c.get("formula", "") or c.get("name", ""), c.get("smiles", "")
    except Exception as e:
        logger.warning("_resolve_candidate_formula_smiles 查询失败: %s", e)
    return "", ""


async def _ai_generate_experiment_procedure(
    candidate_id: str,
    project_id: str,
    material_requirements: list[dict],
) -> list[dict]:
    """AI 辅助生成实验步骤（基于候选材料信息调用 InternLM）。

    返回标准化的实验步骤列表，每步包含 step/name/description/parameters/expected_duration。
    """
    formula, smiles = _resolve_candidate_formula_smiles(candidate_id)
    material_name = formula or smiles or candidate_id

    # 构建 prompt
    material_info = f"候选材料: {material_name}"
    if formula:
        material_info += f"（化学式: {formula}）"
    if smiles:
        material_info += f"（SMILES: {smiles}）"
    if material_requirements:
        mat_names = [m.get("name", "") for m in material_requirements[:5] if m.get("name")]
        if mat_names:
            material_info += f"\n可用物料: {', '.join(mat_names)}"

    prompt = (
        f"你是高分子改性塑料实验专家。请为以下材料设计一套标准实验测试步骤（用于力学性能/热学性能测试）。\n"
        f"{material_info}\n\n"
        f"请返回 JSON 数组，每个步骤包含以下字段：\n"
        f'- "step": 步骤序号（整数）\n'
        f'- "name": 步骤名称（中文）\n'
        f'- "description": 步骤详细描述（中文，包含关键参数）\n'
        f'- "parameters": 关键参数字典（如温度、时间、气氛等）\n'
        f'- "expected_duration": 预计耗时（小时，浮点数）\n\n'
        f"只返回 JSON 数组，不要其他文字。步骤数量 5-8 步。"
    )

    cfg = agent.config
    provider = None
    try:
        from .llm.internlm_provider import InternLMProvider
        if cfg.internlm.enabled:
            provider = InternLMProvider(cfg.internlm)
    except Exception:
        provider = None

    if provider is None:
        from .llm.factory import ProviderFactory
        provider = ProviderFactory.create(cfg)

    from .llm.schemas import ChatRequest, ChatMessage
    request = ChatRequest(
        model=cfg.internlm.model if cfg.internlm.enabled else cfg.llm.model,
        messages=[ChatMessage(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=2048,
    )
    resp = await provider.complete(request)
    content = resp.content.strip()

    # 解析 JSON 响应
    import json as _json
    import re as _re
    # 去除可能的 markdown 代码块标记
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # 容错：LLM 可能返回不完整 JSON，尝试提取最外层数组
    try:
        steps = _json.loads(content)
    except _json.JSONDecodeError:
        # 尝试找到第一个 [ 和最后一个 ] 之间的内容
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            steps = _json.loads(content[start:end + 1])
        else:
            logger.warning("_ai_generate_experiment_procedure: JSON 解析失败，content=%s", content[:300])
            return []
    if not isinstance(steps, list):
        steps = [steps]

    # 校验并补全字段
    validated: list[dict] = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        validated.append({
            "step": s.get("step", i + 1),
            "name": s.get("name", f"步骤{i + 1}"),
            "description": s.get("description", ""),
            "parameters": s.get("parameters", {}),
            "expected_duration": s.get("expected_duration", 1.0),
        })
    return validated


@app.post("/experiments/orders", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_experiment_order(req: ExperimentOrderRequest, request: Request):
    """创建实验任务单。"""
    import uuid as _uuid

    # 评测修复 P1：禁止创建无项目归属的孤儿任务单（溯源链断裂）
    if not req.project_id:
        raise HTTPException(
            status_code=400,
            detail="project_id 不能为空：实验任务单必须归属研发项目以保证数据可溯源",
        )
    if _project_store.get(req.project_id) is None:
        raise HTTPException(status_code=400, detail=f"项目 {req.project_id} 不存在")

    # T-031：AI 自动创建实验任务单需先经 Committee 人工确认（三段式：提交→审核→放行）
    # 服务端判定优先：验签 Agent 凭证 > 请求体自报标志
    if _is_ai_initiated(request, req.ai_initiated):
        return _require_high_risk_review_or_raise(
            "auto_create_experiment_order",
            req.model_dump(),
            initiator="ai",
        )

    # 评测修复 P1：幂等保护 — 同一 idempotency_key 重复提交直接返回首次创建的订单
    if req.idempotency_key:
        existing = agent.experiment_controller._store.get_order_by_idempotency_key(req.idempotency_key)
        if existing is not None:
            result = existing.model_dump()
            result["duplicated"] = True
            return result

    # 放行门禁校验：关联候选若有 release_card_required 且未通过审批，拒绝创建实验任务。
    # 防死锁：无对应放行卡时自动补建待审批卡，避免审批队列为空导致的永久阻断。
    if req.candidate_id:
        record = app.state.candidate_store.get(req.candidate_id)
        # 评测修复 P1-3：candidate_id 不存在时直接 404，避免数据库层 FK 违反抛 500
        if record is None:
            raise HTTPException(status_code=404, detail=f"候选材料 {req.candidate_id} 不存在")
        cand_data = record.data or {}
        if cand_data.get("release_card_required") and not cand_data.get("release_card_approved"):
            existing_card = _find_release_card_for_candidate(req.candidate_id)
            if existing_card is None:
                _card_id = _auto_create_release_card_for_candidate(
                    {**cand_data, "candidate_id": req.candidate_id, "name": record.name or ""},
                    project_id=req.project_id or record.project_id,
                    reason="候选要求放行审批但未发现放行卡，已自动补建",
                )
                if _card_id:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"候选材料 {req.candidate_id} 需要通过放行卡审批后才能创建实验任务；"
                            f"已自动生成放行卡 {_card_id}，请到「我的待办 → 放行卡」完成审批后重试"
                        ),
                    )
            raise HTTPException(
                status_code=403,
                detail=f"候选材料 {req.candidate_id} 需要通过放行卡审批后才能创建实验任务",
            )

    # 自动从物料库反查填充 material_requirements
    material_requirements = req.material_requirements
    if not material_requirements and req.candidate_id:
        try:
            from .industrialization.raw_material_db import RawMaterialDB
            db = getattr(agent, 'raw_material_db', None)
            if db is None:
                logger.warning(
                    "create_experiment_order: agent.raw_material_db 未初始化，"
                    "回退到默认路径的 RawMaterialDB 实例，可能与生产数据不一致"
                )
                db = RawMaterialDB()
            # candidate_id 是候选标识而非化学式，需先从 ECML 运行记录中解析出真实 formula/smiles
            formula, smiles = _resolve_candidate_formula_smiles(req.candidate_id)
            if not formula and not smiles:
                # 未在 ECML 记录中找到候选，退化为用 candidate_id 作为 formula（向后兼容）
                formula = req.candidate_id
            specs = db.find_raw_materials_for_candidate(formula=formula, smiles=smiles)
            material_requirements = [
                {
                    "material_id": s.material_id,
                    "name": s.name,
                    "category": s.category,
                    "required_quantity": 1.0,
                    "inventory": s.inventory_quantity,
                    "supplier": s.supplier,
                    "unit_cost": s.unit_cost,
                }
                for s in specs
            ]
        except Exception as e:
            logger.warning("create_experiment_order: 物料反查失败 candidate_id=%s: %s", req.candidate_id, e)

    # AI 辅助模式：procedure 为空时自动生成实验步骤
    procedure = req.procedure
    if not procedure and req.execution_mode == "ai_assisted":
        try:
            procedure = await _ai_generate_experiment_procedure(
                candidate_id=req.candidate_id,
                project_id=req.project_id,
                material_requirements=material_requirements,
            )
        except Exception as e:
            logger.warning("create_experiment_order: AI 生成实验步骤失败: %s", e)

    # 候选估算属性 → 订单预期值（供实验录入后的偏差分析使用，闭环"估算 vs 实测"）
    acceptance_criteria = dict(req.acceptance_criteria or {})
    if req.candidate_id and not acceptance_criteria.get("expected_values"):
        cand_rec = app.state.candidate_store.get(req.candidate_id)
        if cand_rec is not None:
            cand_data = cand_rec.data or {}
            expected = {
                k: cand_rec.model_dump().get(k) if cand_rec.model_dump().get(k) is not None
                else cand_data.get(k)
                for k in (
                    "tensile_strength", "elongation_at_break", "flexural_modulus",
                    "flexural_strength", "impact_strength", "heat_deflection_temp",
                    "melt_flow_index", "crystallinity",
                )
            }
            expected = {k: v for k, v in expected.items() if isinstance(v, (int, float))}
            if expected:
                acceptance_criteria["expected_values"] = expected

    order = ExperimentOrder(
        order_id=f"EXP_{_uuid.uuid4().hex[:8]}",
        project_id=req.project_id,
        rd_package_id=req.rd_package_id,
        candidate_id=req.candidate_id,
        process_id=req.process_id,
        formulation_version=req.formulation_version,
        process_version=req.process_version,
        test_protocol_version=req.test_protocol_version,
        execution_mode=req.execution_mode,
        priority=req.priority,
        assignee=req.assignee,
        material_requirements=material_requirements,
        procedure=procedure,
        required_results=req.required_results,
        acceptance_criteria=acceptance_criteria,
        notes=req.notes,
        scenario_id=req.scenario_id or "",
        bom_id=req.bom_id or "",
        task_id=req.task_id or "",
        idempotency_key=req.idempotency_key or "",
    )
    try:
        agent.experiment_controller._store.save_order(order)
    except IntegrityError:
        # 并发竞态：另一请求已用同一 idempotency_key 写入，回查返回已有订单
        if req.idempotency_key:
            existing = agent.experiment_controller._store.get_order_by_idempotency_key(req.idempotency_key)
            if existing is not None:
                result = existing.model_dump()
                result["duplicated"] = True
                return result
        raise
    # P3-1：实验任务单写入统一研发事件流水
    _log_research_event(
        event_type="experiment",
        run_id=order.order_id,
        title=f"实验任务单：{order.order_id}",
        summary=f"候选 {req.candidate_id or '未关联'}，项目 {req.project_id or '未关联'}",
        status="running",
        payload={
            "order_id": order.order_id,
            "project_id": req.project_id,
            "candidate_id": req.candidate_id,
            "execution_mode": req.execution_mode,
            "priority": req.priority,
            "scenario_id": req.scenario_id or "",
        },
    )
    return order.model_dump()


@app.get("/experiments/orders", dependencies=[Depends(require_login)])
async def list_experiment_orders(
    status: str | None = None,
    project_id: str | None = None,
    include_result_count: bool = False,
    include_demo: bool = False,
):
    """查询实验任务列表。可选 include_result_count 返回每条任务关联的实验数据条数。

    D2(P2-002)：默认过滤 SEED_ 演示任务，include_demo=True 时包含。
    """
    orders = agent.experiment_controller._store.list_orders(status=status, project_id=project_id)
    result = _filter_demo([o.model_dump() for o in orders], include_demo)
    if include_result_count:
        counts = agent.experiment_controller._store.count_result_records()
        for item in result:
            item["result_count"] = counts.get(item.get("order_id") or "", 0)
    return result


@app.get("/experiments/orders/{order_id}", dependencies=[Depends(require_login)])
async def get_experiment_order(order_id: str):
    """获取单个实验任务详情。"""
    order = agent.experiment_controller._store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="实验任务不存在")
    return order.model_dump()


@app.post("/experiments/orders/{order_id}/approve", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def approve_experiment_order(order_id: str, req: OrderApprovalRequest):
    """审批通过实验任务。"""
    try:
        agent.experiment_controller._store.update_order_status(
            order_id, "APPROVED", approved_by=req.approved_by,
            triggered_by=req.approved_by or "system",
            reason="manual approval" + (f": {req.notes}" if req.notes else ""),
        )
    except IllegalStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    get_audit_logger().log(AuditEntry(
        event_type="decision",
        module="experiment_order",
        action="approve",
        detail={"order_id": order_id, "approved_by": req.approved_by, "notes": req.notes},
        operator=req.approved_by or "system",
    ))
    return {"status": "approved", "order_id": order_id}


class OrderMetaRequest(BaseModel):
    """实验任务单元数据更新请求。"""
    assignee: str = ""
    priority: str = ""
    notes: str = ""


@app.patch("/experiments/orders/{order_id}",
           dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_experiment_order_meta(order_id: str, req: OrderMetaRequest):
    """编辑实验任务（负责人/优先级/备注）；仅草稿/待审批/已审批状态可编辑。"""
    try:
        ok = agent.experiment_controller.update_order_meta(
            order_id, assignee=req.assignee, priority=req.priority, notes=req.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"实验任务 {order_id} 不存在")
    return {"order_id": order_id, "status": "updated"}


@app.delete("/experiments/orders/{order_id}",
            dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_experiment_order(order_id: str):
    """删除实验任务（仅草稿/待审批状态；已有实验数据或已审批的禁止删除）。"""
    try:
        ok = agent.experiment_controller.delete_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail=f"实验任务 {order_id} 不存在")
    get_audit_logger().log(AuditEntry(
        event_type="decision",
        module="experiment_order",
        action="delete",
        detail={"order_id": order_id},
        operator="system",
    ))
    return {"status": "deleted", "order_id": order_id}


@app.post("/experiments/orders/{order_id}/reject", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def reject_experiment_order(order_id: str, req: OrderApprovalRequest):
    """审批拒绝实验任务。"""
    try:
        agent.experiment_controller._store.update_order_status(
            order_id, "REJECTED", approved_by=req.approved_by,
            triggered_by=req.approved_by or "system",
            reason="manual rejection" + (f": {req.notes}" if req.notes else ""),
        )
    except IllegalStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    get_audit_logger().log(AuditEntry(
        event_type="decision",
        module="experiment_order",
        action="reject",
        detail={"order_id": order_id, "approved_by": req.approved_by, "notes": req.notes},
        operator=req.approved_by or "system",
    ))
    return {"status": "rejected", "order_id": order_id}


@app.get("/experiments/orders/{order_id}/audit", dependencies=[Depends(require_login)])
async def get_order_audit(order_id: str):
    """获取任务单的审计日志。"""
    logger = get_audit_logger()
    return [e.model_dump() for e in logger.query_by_detail("experiment_order", "order_id", order_id)]


# ===========================================================================
# 实验结果 API
# ===========================================================================

def _ensure_sample_for_result(sample_id: str, source_type: str = "experiment",
                              order_id: str = "", candidate_id: str = ""):
    """写入实验结果时联动创建样品记录，打通 samples.db 与 experiments.db。

    委托到 experiment.sample_guard（注册式注入 sample_store / order 查询），
    避免其他模块反向 import api。
    """
    ensure_sample_for_result(sample_id, source_type=source_type,
                             order_id=order_id, candidate_id=candidate_id)


def _save_single_result_record(req: ExperimentResultManualRequest) -> ExperimentResultRecord:
    """保存单条实验结果记录，自动打时间戳与录入人标签。"""
    import uuid as _uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    # 评测修复 P0-001（严格模式）：实验结果必须携带溯源关联，
    # experiment_order_id（项目→任务单→候选链路）或 sample_id（样品链路）至少一项，
    # 否则拒绝入库，阻断无溯源数据进入学习闭环
    if not (req.experiment_order_id or "").strip() and not (req.sample_id or "").strip():
        raise ValueError(
            "缺少溯源关联：experiment_order_id 或 sample_id 至少填写一项，"
            "无溯源数据禁止入库"
        )
    # 评测修复 P0：模板裸值（EIS/CV 等）映射为 mdm.test_methods 的 method_id，避免 FK 失败
    test_method = _normalize_test_method(req.test_method)
    # 同类修复：property_name / unit 也需匹配 MDM 主数据（fk_results_property / fk_results_unit）
    property_name = _normalize_property_name(req.property_name)
    unit = _normalize_unit(req.unit)
    # T-016：按属性名做数值范围校验（超出白名单范围抛 ValueError，由调用方转为 400）
    _validate_value_range(property_name, req.value, req.test_conditions)
    # P0-001：未显式传入 scenario_id 时，从关联实验任务单反查填充，保证结果可溯源
    scenario_id = req.scenario_id or ""
    if not scenario_id and req.experiment_order_id:
        try:
            _order = agent.experiment_controller._store.get_order(req.experiment_order_id)
            if _order is not None:
                scenario_id = _order.scenario_id or ""
        except Exception:
            pass
    # T-029：AI 预测结果（非人工录入）根据 confidence 自动标记 data_quality；
    # 人工录入（ai_generated=False）保持显式 data_quality 不受影响。
    if req.ai_generated and req.confidence is not None:
        data_quality = "simulated" if req.confidence >= 0.8 else "estimated"
    else:
        data_quality = req.data_quality or "estimated"
    # ADR-0002：人工录入路径写入溯源（evidence_level 与 data_quality 对齐）
    provenance = [
        {
            "source_type": "manual_entry",
            "provider": "local_db",
            "model_or_tool": "experiment_controller",
            "evidence_level": data_quality,
            "recorded_by": req.uploaded_by or "",
        }
    ]
    record = ExperimentResultRecord(
        result_id=f"RES_{_uuid.uuid4().hex[:8]}",
        experiment_order_id=req.experiment_order_id,
        sample_id=req.sample_id,
        sample_batch_id=req.sample_batch_id,
        source_type="MANUAL_ENTRY",
        uploaded_by=req.uploaded_by,
        uploaded_at=now,
        property_name=property_name,
        value=req.value,
        unit=unit,
        test_method=test_method,
        test_conditions=req.test_conditions,
        instrument_id=req.instrument_id,
        raw_file_uri=req.raw_file_uri,
        qc_status="PENDING",
        scenario_id=scenario_id,
        data_quality=data_quality,
        provenance=provenance,
    )
    # 联动创建样品记录（必须先于 save_result_record：fk_results_sample 要求样品已存在）
    _ensure_sample_for_result(req.sample_id, source_type="manual_entry",
                               order_id=req.experiment_order_id)
    agent.experiment_controller._store.save_result_record(record)
    if scenario_id and req.sample_id:
        try:
            _sample_store = getattr(app.state, "sample_store", None)
            if _sample_store is not None:
                _existing = _sample_store.get(req.sample_id)
                if _existing is not None and not _existing.scenario_id:
                    _existing.scenario_id = scenario_id
                    _sample_store.save(_existing)
        except Exception:
            pass

    # 自动触发 QC 检查
    from .middleware.wet_data.quality import QCEngine
    try:
        engine = QCEngine()
        qc_result = engine.check(record)
        agent.experiment_controller._store.update_result_qc(
            record.result_id, qc_result.qc_status, qc_result.issues,
            reviewed_by="QC_ENGINE",
            learning_eligible=qc_result.learning_eligible,
        )
        record.qc_status = qc_result.qc_status
        record.qc_issues = qc_result.issues
        # Task 12.4：写入 QC 决策审计日志
        try:
            from .qc_service import write_audit_log
            write_audit_log(record.result_id, qc_result)
        except Exception:
            pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("自动 QC 检查失败: %s", e)

    # 录入数据后推进任务状态：APPROVED → IN_EXECUTION（实验执行中，不再倒退到 WAITING_FOR_DATA）
    # 若状态已是 IN_EXECUTION 或 COMPLETED，不重复更新
    if req.experiment_order_id:
        order = agent.experiment_controller._store.get_order(req.experiment_order_id)
        if order and order.status == "APPROVED":
            try:
                agent.experiment_controller._store.update_order_status(
                    req.experiment_order_id, "IN_EXECUTION",
                    triggered_by=req.uploaded_by or "system",
                    reason="data entry started",
                )
            except IllegalStateTransitionError as e:
                logger.warning("Failed to advance order %s to IN_EXECUTION: %s",
                               req.experiment_order_id, e)

    return record


def _find_pending_ecml_runs_for_order(order_id: str) -> list[dict]:
    """查询与实验任务单关联的 WAITING_FOR_DATA 状态 ECML run。

    反查策略（综合多线索，提高命中率）：
    1. order_id 形如 ORD-ECML-{run_id前8位}-{iter} → 用 run_id 前缀 LIKE 匹配
    2. order.scenario_id 反查 ecml_runs_index.scenario_id
    3. order.task_id 反查 ecml_runs_index.task_id

    返回匹配且未完成的 WAITING_FOR_DATA run 列表，按创建时间倒序，最多 5 条。
    """
    if not order_id:
        return []
    try:
        order = agent.experiment_controller._store.get_order(order_id)
    except Exception:
        return []
    if order is None:
        return []

    try:
        engine = agent.ecml.state_store.engine
    except Exception:
        return []

    clauses: list[str] = []
    params: dict = {"status": "waiting_for_data"}

    # 策略 1：ECML 自动生成的 order_id 形如 ORD-ECML-{run_id[:8]}-{iter}
    if order_id.startswith("ORD-ECML-"):
        parts = order_id.split("-", 3)  # ['ORD', 'ECML', 'run_prefix', 'iter']
        if len(parts) >= 3 and parts[2]:
            clauses.append("run_id LIKE :run_prefix")
            params["run_prefix"] = f"{parts[2]}%"

    # 策略 2：scenario_id 关联
    if order.scenario_id:
        clauses.append("(scenario_id = :scenario_id)")
        params["scenario_id"] = order.scenario_id

    # 策略 3：task_id 关联
    if order.task_id:
        clauses.append("(task_id = :task_id)")
        params["task_id"] = order.task_id

    if not clauses:
        return []

    try:
        with engine.connect() as conn:
            # 安全说明：clauses 元素全部为硬编码字符串（如 "run_id LIKE :run_prefix"），
            # 用户输入通过 params 命名参数绑定，不存在 SQL 注入风险
            or_clause = " OR ".join(clauses)
            sql = text(f"""SELECT run_id, scenario_id, task_id, status, iteration_id, is_complete
                          FROM ecml.ecml_runs_index
                          WHERE status = :status AND is_complete = FALSE
                            AND ({or_clause})
                          ORDER BY created_at DESC
                          LIMIT 5""")
            rows = conn.execute(sql, params).fetchall()
    except Exception as e:
        logger.debug("查询 WAITING_FOR_DATA ECML run 失败 order=%s: %s", order_id, e)
        return []

    return [{
        "run_id": r[0],
        "scenario_id": r[1] or "",
        "task_id": r[2] or "",
        "step": r[3] or "",
        "iteration_id": r[4] or 1,
    } for r in rows if r[0]]


@app.post("/experiments/results/manual", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_experiment_result_manual(req: ExperimentResultManualRequest):
    """人工录入实验结果（单条）。

    若关联的实验任务单存在 WAITING_FOR_DATA 状态的 ECML run，
    返回 pending_resume 字段提示前端可触发反馈分析（半自动：不自动唤醒）。
    """
    try:
        record = _save_single_result_record(req)
    except ValueError as e:
        # T-016：数值范围/录入校验失败属请求错误，返回 400 而非 409
        raise HTTPException(status_code=400, detail=str(e)) from e
    data = record.model_dump()
    pending_runs = _find_pending_ecml_runs_for_order(req.experiment_order_id)
    if pending_runs:
        data["pending_resume"] = {
            "runs": pending_runs,
            "hint": f"检测到 {len(pending_runs)} 个等待数据的 ECML run，可触发反馈分析",
        }
    return data


@app.post("/experiments/results", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_experiment_results_batch(reqs: list[ExperimentResultManualRequest]):
    """批量录入实验结果。接受 ExperimentResultManualRequest 列表，写入 experiment_result_records 表。"""
    if not reqs:
        raise HTTPException(status_code=400, detail="请求列表不能为空")
    saved = []
    errors = []
    for idx, req in enumerate(reqs):
        try:
            record = _save_single_result_record(req)
            saved.append(record.model_dump())
        except ValueError as e:
            errors.append({"index": idx, "error": str(e)})
    if errors and not saved:
        # 录入校验失败（含溯源缺失）属请求错误，返回 400 而非 409（与单条端点一致）
        raise HTTPException(status_code=400, detail=errors[0]["error"])
    return {"imported": len(saved), "records": saved, "errors": errors}


def _enrich_qc_record(record: ExperimentResultRecord) -> dict:
    """为 QC 队列记录附加关联的实验任务与样品信息，便于前端展示与跳转。"""
    data = record.model_dump()
    # 关联实验任务单：order_id / assignee / project_id / candidate_id / status
    order_info = None
    if record.experiment_order_id:
        order = agent.experiment_controller._store.get_order(record.experiment_order_id)
        if order:
            order_info = {
                "order_id": order.order_id,
                "assignee": order.assignee,
                "project_id": order.project_id,
                "candidate_id": order.candidate_id,
                "status": order.status,
            }
    data["experiment_order"] = order_info
    # 关联样品：name / status / storage_location
    sample_info = None
    if record.sample_id:
        try:
            sample_store = getattr(app.state, "sample_store", None)
            sample = sample_store.get(record.sample_id) if sample_store is not None else None
            if sample:
                sample_info = {
                    "sample_id": sample.sample_id,
                    "name": sample.name,
                    "status": sample.status.value,
                    "storage_location": sample.storage_location,
                }
        except Exception as e:
            logger.debug("enrich_qc_record: 样品信息查询失败 sample_id=%s: %s", record.sample_id, e)
    data["sample"] = sample_info
    # Task 12.6：附加 QC 可解释字段（rule_results / decision_path / rule_version 等）
    # 实时调用 qc_service.check_record() 取回结构化规则结果，便于前端展开详情。
    try:
        from .qc_service import check_record
        qc_view = check_record(record)
        data["qc_rule_results"] = [r.to_dict() for r in qc_view.rule_results]
        data["qc_decision_path"] = qc_view.decision_path
        data["qc_rule_version"] = qc_view.rule_version
        data["qc_severity"] = qc_view.severity
        data["qc_confidence"] = qc_view.confidence
        data["qc_suggested_action"] = qc_view.suggested_action
        data["qc_primary_rule_id"] = qc_view.rule_id
    except Exception as e:
        logger.debug("enrich_qc_record: QC 可解释字段计算失败 result_id=%s: %s",
                     record.result_id, e)
    return data


@app.get("/experiments/results", dependencies=[Depends(require_login)])
async def list_experiment_results(qc_status: str | None = None, order_id: str | None = None,
                                  include_demo: bool = False):
    """查询实验结果。

    D2(P2-002)：默认过滤 SEED_ 演示结果，include_demo=True 时包含。
    """
    records = agent.experiment_controller._store.list_result_records(
        qc_status=qc_status, order_id=order_id,
    )
    return _filter_demo([_enrich_qc_record(r) for r in records], include_demo)


@app.get("/experiments/types")
async def list_experiment_types():
    """实验类型筛选项枚举。

    评测修复 P2-5：替代前端硬编码枚举。/experiments/query 的 experiment_type
    实际匹配 experiment_result_records.test_method 列，因此选项取自
    结果记录中真实出现的 test_method 去重值，中文名关联 mdm.test_methods；
    无记录时回退到 MDM 检测方法全集，保证新环境筛选项可用。
    """
    engine = agent.experiment_controller._store.engine
    types: list[dict] = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT DISTINCT r.test_method AS value, "
                "COALESCE(m.name, r.test_method) AS label "
                "FROM experiment.experiment_result_records r "
                "LEFT JOIN mdm.test_methods m ON m.method_id = r.test_method "
                "WHERE r.test_method IS NOT NULL AND r.test_method != '' "
                "ORDER BY label"
            )).fetchall()
            types = [{"label": r[1], "value": r[0]} for r in rows]
            if not types:
                rows = conn.execute(text(
                    "SELECT method_id, name FROM mdm.test_methods "
                    "WHERE is_active = TRUE ORDER BY name"
                )).fetchall()
                types = [{"label": r[1], "value": r[0]} for r in rows]
    except Exception as e:
        logger.warning("查询实验类型枚举失败: %s", e)
    return {"types": types, "count": len(types)}


@app.post("/experiments/results/upload", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def upload_experiment_results_file(request: Request):
    """上传 CSV/Excel 文件导入实验数据。"""
    import tempfile
    import os

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=400, detail="需要 multipart/form-data 格式")

    form = await request.form()
    file = form.get("file")
    if file is None:
        raise HTTPException(status_code=400, detail="缺少文件")

    # 文件大小校验：最大 50MB，防止内存爆炸
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    file_data = await file.read()
    if len(file_data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB 限制",
        )

    filename = file.filename or "upload.csv"
    # 文件后缀白名单校验，防止路径遍历与不安全文件
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail="不支持的文件格式，仅允许 .csv / .xlsx / .xls")

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        from .middleware.wet_data.adapters import CSVAdapter, ExcelAdapter

        if filename.endswith(".csv"):
            adapter = CSVAdapter()
        elif filename.endswith((".xlsx", ".xls")):
            adapter = ExcelAdapter()
        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式，仅支持 .csv 和 .xlsx")

        records = adapter.parse_file(tmp_path)
        saved = []
        for record in records:
            agent.experiment_controller._store.save_result_record(record)
            _ensure_sample_for_result(record.sample_id, source_type="csv_import",
                                       order_id=record.experiment_order_id)
            saved.append(record.model_dump())

        return {"imported": len(saved), "records": saved}
    finally:
        os.unlink(tmp_path)


# ===========================================================================
# QC API
# ===========================================================================

@app.post("/qc/check/{result_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def trigger_qc_check(result_id: str):
    """触发 QC 检查。"""
    record = agent.experiment_controller._store.get_result_record(result_id)
    if not record:
        raise HTTPException(status_code=404, detail="实验结果不存在")

    from .middleware.wet_data.quality import QCEngine
    engine = QCEngine()
    qc_result = engine.check(record)
    agent.experiment_controller._store.update_result_qc(
        result_id, qc_result.qc_status, qc_result.issues,
        reviewed_by="QC_ENGINE",
        learning_eligible=qc_result.learning_eligible,
    )
    # Task 12.4：写入 QC 决策审计日志
    try:
        from .qc_service import write_audit_log
        write_audit_log(result_id, qc_result)
    except Exception as e:
        logger.error("QC audit log write failed result_id=%s: %s", result_id, e, exc_info=True)
    return qc_result.model_dump()


@app.get("/qc/pending")
async def list_qc_pending():
    """列出待审核数据。"""
    records = agent.experiment_controller._store.list_result_records(qc_status="PENDING")
    return [_enrich_qc_record(r) for r in records]


@app.post("/qc/{result_id}/approve", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def approve_qc_result(result_id: str, req: QCApproveRequest):
    """确认 QC 结果。"""
    record = agent.experiment_controller._store.get_result_record(result_id)
    if not record:
        raise HTTPException(status_code=404, detail="实验结果不存在")

    # 评测修复 P0-001：verified 数据必须具备溯源链（experiment_order_id 关联
    # 项目→任务单→候选，或 sample_id 关联样品）。无溯源记录禁止审批为 verified，
    # 防止来源不明的数据进入学习闭环。
    has_order = bool((record.experiment_order_id or "").strip())
    has_sample = bool((record.sample_id or "").strip())
    if not (has_order or has_sample):
        raise HTTPException(
            status_code=400,
            detail="缺少溯源链（experiment_order_id / sample_id 均为空），禁止审批为 verified",
        )
    # learning_eligible 是审计确认后的放行标志：必须具备任务单级溯源链，
    # 否则强制留在学习闭环之外
    learning_eligible = bool(req.learning_eligible) and has_order
    if req.learning_eligible and not has_order:
        logger.warning(
            "QC 审批 result_id=%s: 请求 learning_eligible 但缺少 experiment_order_id，已强制为 false",
            result_id,
        )

    # 评测修复 P2-5：QC 审批通过，数据质量标记升级为 verified
    agent.experiment_controller._store.update_result_qc(
        result_id, "VALID", record.qc_issues,
        reviewed_by=req.reviewed_by or "QC_REVIEWER",
        learning_eligible=learning_eligible,
        data_quality="verified",
    )

    # QC 通过后检查任务下是否还有未完成结果，全部通过则推进任务为 COMPLETED
    analysis_id = ""
    analysis_error = ""
    if record.experiment_order_id:
        all_results = agent.experiment_controller._store.list_result_records(
            order_id=record.experiment_order_id
        )
        all_done = all(r.qc_status in ("VALID", "VALID_WITH_WARNING") for r in all_results)
        if all_done and all_results:
            try:
                agent.experiment_controller._store.update_order_status(
                    record.experiment_order_id, "COMPLETED",
                    raw_material_db=getattr(agent, 'raw_material_db', None),
                    triggered_by=req.reviewed_by or "QC_REVIEWER",
                    reason="all results passed QC",
                )
            except IllegalStateTransitionError as e:
                logger.warning("Failed to advance order %s to COMPLETED: %s",
                               record.experiment_order_id, e)

        # 触发 ExperimentAnalystAgent 对该任务单历史结果进行统计分析
        try:
            analysis = _experiment_analyst.analyze(all_results)
            analysis_id = agent.experiment_controller._store.save_analysis(
                record.experiment_order_id, analysis,
            )
        except Exception as exc:
            logger.warning(
                "ExperimentAnalystAgent 分析失败 order_id=%s: %s",
                record.experiment_order_id, exc,
            )
            analysis_error = str(exc)

    return {"status": "VALID", "result_id": result_id, "analysis_id": analysis_id, "analysis_error": analysis_error}


@app.post("/qc/{result_id}/reject", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def reject_qc_result(result_id: str, req: QCApproveRequest):
    """拒绝 QC 结果，记录驳回原因并通知实验任务负责人。"""
    record = agent.experiment_controller._store.get_result_record(result_id)
    if not record:
        raise HTTPException(status_code=404, detail="实验结果不存在")

    # 保留既有 QC 问题，并追加审核驳回原因
    reject_issues = list(record.qc_issues or [])
    if req.reason:
        reject_issues.append(f"审核驳回：{req.reason}")

    agent.experiment_controller._store.update_result_qc(
        result_id, "REJECTED", reject_issues,
        reviewed_by=req.reviewed_by,
        learning_eligible=False,
    )

    # 通知原实验任务负责人
    if record.experiment_order_id:
        notify_msg = f"实验结果 {result_id} 被 QC 驳回"
        if req.reason:
            notify_msg += f"：{req.reason}"
        agent.experiment_controller.notify_assignee(record.experiment_order_id, notify_msg)

    return {"status": "REJECTED", "result_id": result_id}


@app.get("/experiments/analysis/{order_id}")
async def get_experiment_analysis(order_id: str):
    """获取指定任务单的最新分析简报（由 QC 通过钩子触发 ExperimentAnalystAgent 生成）。

    无简报时返回 200 + 空结构（而非 404），避免前端控制台出现 404 网络错误。
    """
    stored = agent.experiment_controller._store.get_analysis_by_order(order_id)
    if not stored:
        return {"order_id": order_id, "analysis": None}
    return stored


@app.post("/experiments/deviation-check", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def check_experiment_deviation(req: dict, request: Request):
    """过程反思：检测实测值与预测值的偏差。

    请求体：{order_id, predicted_values, threshold?}
    返回：{deviations, total_checked, anomaly_count, threshold}
    """
    order_id = req.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="order_id 必填")
    predicted_values = req.get("predicted_values") or {}
    if not isinstance(predicted_values, dict):
        raise HTTPException(status_code=400, detail="predicted_values 必须为字典")
    # 校验值为数值类型，非数值拒绝
    for k, v in predicted_values.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise HTTPException(
                status_code=400,
                detail=f"predicted_values.{k} 必须为数值类型",
            )
    try:
        threshold = float(req.get("threshold", 0.2))
    except (TypeError, ValueError):
        threshold = 0.2
    if threshold <= 0 or threshold > 1:
        raise HTTPException(status_code=400, detail="threshold 必须在 (0, 1] 区间内")
    deviations = agent.experiment_controller.detect_prediction_deviation(
        order_id=order_id,
        predicted_values=predicted_values,
        threshold=threshold,
    )
    anomaly_count = sum(1 for d in deviations if d.get("is_anomaly"))
    operator = _user_role_from_request(request)
    logger.info(
        "Deviation check by user=%s (order_id=%s, threshold=%.2f, total=%d, anomaly=%d)",
        operator, order_id, threshold, len(deviations), anomaly_count,
    )
    return {
        "deviations": deviations,
        "total_checked": len(deviations),
        "anomaly_count": anomaly_count,
        "threshold": threshold,
    }


@app.post("/experiments/anomaly-mark", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def mark_experiment_anomalies(req: dict, request: Request):
    """过程反思：将异常样本标记为 REQUIRES_REVIEW，并附交叉验证分析。

    请求体：{anomalies: [{result_id, ...}]}
    返回：{marked, analysis, not_found?}
    """
    # 写操作必须鉴权：仅 researcher/admin 可执行
    user = getattr(request.state, "current_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录后再执行异常标记")
    if user.role.value not in ("researcher", "admin"):
        raise HTTPException(status_code=403, detail="此操作需要 researcher 或 admin 权限")
    anomalies = req.get("anomalies") or []
    if not isinstance(anomalies, list) or not anomalies:
        raise HTTPException(status_code=400, detail="anomalies 必须为非空数组")
    result_ids: list[str] = []
    for item in anomalies:
        if not isinstance(item, dict):
            continue
        rid = item.get("result_id")
        if rid:
            result_ids.append(str(rid))
    if not result_ids:
        raise HTTPException(status_code=400, detail="未提供有效的 result_id")
    # 生成模板化交叉验证分析（避免调用 LLM）
    analysis_lines = [
        f"共检测 {len(result_ids)} 个异常样本，可能原因：",
        "1. 测量误差：仪器校准漂移、操作差异、环境扰动",
        "2. 模型外推：候选材料超出训练分布、性质区间未覆盖",
        "3. 材料降解：合成条件偏差、杂质引入、相变发生",
        "4. 数据问题：样品混淆、单位换算错误、记录转录错误",
    ]
    analysis = "\n".join(analysis_lines)
    marked = agent.experiment_controller.mark_anomaly_samples(
        result_ids=result_ids,
        analysis=analysis,
        reviewed_by=user.user_id,
    )
    not_found = [rid for rid in result_ids if not agent.experiment_controller._store.get_result_record(rid)]
    # 审计日志：记录写操作便于追溯
    get_audit_logger().log(AuditEntry(
        event_type="decision",
        module="experiment_qc",
        action="mark_anomaly",
        detail={
            "result_ids": result_ids,
            "marked": marked,
            "not_found": not_found,
            "analysis_summary": analysis[:200],
        },
        operator=user.user_id,
    ))
    logger.info(
        "Anomaly mark by user=%s (marked=%d, not_found=%d)",
        user.user_id, marked, len(not_found),
    )
    response: dict = {"marked": marked, "analysis": analysis}
    if not_found:
        response["not_found"] = not_found
    return response


# ===========================================================================
# 实验审批门 API
# ===========================================================================

@app.post("/experiments/approval/judge", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def judge_experiment_approval(req: ApprovalJudgeRequest):
    """判断实验是否需要人工审批。"""
    engine = ApprovalEngine()
    decision = engine.judge(
        req.candidate,
        estimated_cost=req.estimated_cost,
        model_confidence=req.model_confidence,
    )
    return decision.model_dump()


@app.get("/experiments/approval/rules")
async def list_approval_rules():
    """列出所有审批规则。"""
    engine = ApprovalEngine()
    return [r.model_dump() for r in engine.list_rules()]


# ===========================================================================
# 统一审批中心 API
# ===========================================================================

@app.get("/approvals/pending")
async def list_pending_approvals():
    """统一审批中心：合并实验任务审批、QC 审核队列。"""
    items = []
    # 实验任务审批（status=PENDING_APPROVAL）
    orders = agent.experiment_controller._store.list_orders(status="PENDING_APPROVAL")
    for o in orders:
        # 审批通道：默认实验审批；若订单 notes 标记为委员会评审（如高风险/委员会案件）则归入该通道
        channel_label = "委员会评审" if "委员会" in (o.notes or "") else "实验审批"
        items.append({
            "type": "experiment_order",
            "id": o.order_id,
            "title": f"实验任务 {o.order_id}",
            "requester": o.assignee,
            "created_at": o.created_at,
            "status": o.status,
            "channel": channel_label,
            "details": {
                "candidate_id": o.candidate_id,
                "priority": o.priority,
                "project_id": o.project_id,
                "channel": channel_label,
            },
        })
    # QC 审核队列（qc_status=PENDING）
    records = agent.experiment_controller._store.list_result_records(qc_status="PENDING")
    for r in records:
        items.append({
            "type": "qc_review",
            "id": r.result_id,
            "title": f"QC审核 {r.result_id}",
            "requester": r.uploaded_by,
            "created_at": r.uploaded_at,
            "status": r.qc_status,
            "details": {
                "property_name": r.property_name,
                "value": r.value,
                "unit": r.unit,
                "order_id": r.experiment_order_id,
            },
        })
    return {"items": items, "count": len(items)}


@app.get("/approvals/rules")
async def list_unified_approval_rules():
    """统一审批规则列表。"""
    engine = ApprovalEngine()
    return [r.model_dump() for r in engine.list_rules()]


class ApprovalCreateRequest(BaseModel):
    """通用审批创建请求（候选材料采纳等业务审批）。"""
    title: str = ""
    type: str = "material_adoption"  # material_adoption / experiment_order / qc_review ...
    payload: dict = Field(default_factory=dict)
    requester: str = ""


@app.post("/approvals", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def create_approval(req: ApprovalCreateRequest):
    """发起通用审批。当前实现：创建一个 PENDING_APPROVAL 状态的实验订单草稿，
    使其在审批中心可见；后续可扩展为独立审批记录表。

    审批通道（channel）：material_adoption 等材料采纳流程默认进入「实验审批」通道，
    返回结果中携带 channel / channel_label，并写入订单 notes 供审批中心区分通道。
    """
    payload = req.payload or {}
    candidate = payload.get("candidate", {}) if isinstance(payload, dict) else {}
    candidate_id = candidate.get("candidate_id") or candidate.get("id") or ""
    formula = candidate.get("formula") or candidate.get("name") or ""
    project_id = payload.get("project_id", "") if isinstance(payload, dict) else ""
    task_id = payload.get("task_id", "") if isinstance(payload, dict) else ""
    channel = "experiment"  # 材料采纳流程的目标审批通道：实验审批
    channel_label = "实验审批"
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    try:
        from datetime import datetime, timezone
        from .experiment.experiment_controller import ExperimentOrder
        order = ExperimentOrder(
            order_id=order_id,
            # candidate_id 留空避免 FK 约束失败，候选信息存入 notes
            candidate_id="",
            project_id=project_id,
            task_id=task_id,
            notes=f"{req.title} | 候选: {formula or candidate_id} | 审批通道: {channel_label}",
            status="PENDING_APPROVAL",
            priority="P2",
            assignee=req.requester or "system",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        agent.experiment_controller._store.save_order(order)
    except Exception:
        logger.warning("创建审批订单失败", exc_info=True)
        raise HTTPException(status_code=500, detail="审批创建失败，请重试")
    return {
        "approval_id": order_id,
        "status": "PENDING_APPROVAL",
        "title": req.title,
        "channel": channel,
        "channel_label": channel_label,
        "message": f"已发起审批，本次将提交至「{channel_label}」，可在「审批中心」跟踪进度",
    }


# ===========================================================================
# 工具调用审批 API（requires_human_review 触发的阻塞式审批）
# ===========================================================================

@app.get("/tool-approvals/pending")
async def list_pending_tool_approvals():
    """列出所有待审批的工具调用。"""
    _require_agent_team()
    items = _executor.list_pending_approvals()
    return {"items": items, "count": len(items)}


@app.post("/tool-approvals/{approval_id}/approve", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def approve_tool_call(approval_id: str):
    """批准待审批的工具调用。"""
    _require_agent_team()
    ok = _executor.resolve_approval(approval_id, approved=True)
    if not ok:
        raise HTTPException(status_code=404, detail="审批请求不存在或已处理")
    return {"approval_id": approval_id, "status": "approved"}


@app.post("/tool-approvals/{approval_id}/reject", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def reject_tool_call(approval_id: str):
    """拒绝待审批的工具调用。"""
    _require_agent_team()
    ok = _executor.resolve_approval(approval_id, approved=False)
    if not ok:
        raise HTTPException(status_code=404, detail="审批请求不存在或已处理")
    return {"approval_id": approval_id, "status": "rejected"}


# ===========================================================================
# 高风险 AI 操作人工确认 API（T-031：触发条件D，三段式扩展）
# 决策 D-04：物理执行/资源消耗类 AI 操作需人工确认，纯建议类仅标记置信度
# ===========================================================================

def _enrich_high_risk_case(case) -> dict:
    """从 case 事件流中提取 action_type / action_payload，组装成前端可读条目。"""
    item = case.model_dump()
    item["action_type"] = ""
    item["action_payload"] = {}
    try:
        for ev in _committee_event_store.get_events(case.case_id):
            if ev.get("event_type") == "auto_triggered":
                data = ev.get("data", {}) or {}
                item["action_type"] = data.get("action_type", "")
                item["action_payload"] = data.get("action_payload", {})
                break
    except Exception:  # noqa: BLE001
        pass
    return item


@app.get("/committee/high-risk-actions/pending")
async def list_pending_high_risk_actions():
    """查询待审核的高风险 AI 操作（status 为 pending / human_review）。"""
    _require_committee()
    from .committee.enums import CommitteeType, CaseStatus
    cases = _committee_repository.list_cases(
        committee_type=CommitteeType.HIGH_RISK_AI_ACTION, limit=500,
    )
    pending = [
        _enrich_high_risk_case(c) for c in cases
        if c.status in (CaseStatus.PENDING, CaseStatus.HUMAN_REVIEW)
    ]
    return {"items": pending, "count": len(pending)}


@app.post(
    "/committee/high-risk-actions/{case_id}/approve",
    dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))],
)
async def approve_high_risk_action(case_id: str, payload: dict | None = Body(None),
                                   current: User | None = Depends(get_current_user)):
    """批准高风险 AI 操作：将 case 置为 pass，记录审批事件。

    批准仅完成治理侧放行；原业务操作的实质执行由调用方在收到批准后再次发起
    （ai_initiated 不再置位），与现有 committee 审核语义一致。
    """
    _require_committee()
    from .committee.enums import CommitteeType, CaseStatus
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    if case.committee_type != CommitteeType.HIGH_RISK_AI_ACTION:
        raise HTTPException(status_code=400, detail=f"Case {case_id} 不是高风险 AI 操作案件")
    if case.status not in (CaseStatus.PENDING, CaseStatus.HUMAN_REVIEW):
        raise HTTPException(
            status_code=400,
            detail=f"Case 当前状态为 {case.status.value}，仅 pending/human_review 状态可审批",
        )
    _committee_repository.update_case_status(case_id, CaseStatus.PASS)
    reviewer = (payload or {}).get("reviewer", "")
    comment = (payload or {}).get("comment", "")
    _committee_event_store.append(case_id, "human_review_resolved", {
        "decision": "approve",
        "reviewer": reviewer,
        "comment": comment,
    })
    # 高危放行即审计：操作者绑定登录身份
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="committee",
            action="high_risk_approve",
            detail={"case_id": case_id, "decision": "approve", "comment": comment},
            operator=(current.username if current else "") or reviewer or "unknown",
            confirmed=True,
            resource_type="committee_case",
            resource_id=case_id,
        ))
    except Exception:
        logger.warning("高危审批审计写入失败 case_id=%s", case_id, exc_info=True)
    logger.info(
        "High-risk AI action approved (case_id=%s, reviewer=%s)", case_id, reviewer or "pm",
    )
    return {"case_id": case_id, "status": "pass", "decision": "approve"}


@app.post(
    "/committee/high-risk-actions/{case_id}/reject",
    dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))],
)
async def reject_high_risk_action(case_id: str, payload: dict | None = Body(None),
                                  current: User | None = Depends(get_current_user)):
    """拒绝高风险 AI 操作：将 case 置为 reject，记录审批事件。"""
    _require_committee()
    from .committee.enums import CommitteeType, CaseStatus
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    if case.committee_type != CommitteeType.HIGH_RISK_AI_ACTION:
        raise HTTPException(status_code=400, detail=f"Case {case_id} 不是高风险 AI 操作案件")
    if case.status not in (CaseStatus.PENDING, CaseStatus.HUMAN_REVIEW):
        raise HTTPException(
            status_code=400,
            detail=f"Case 当前状态为 {case.status.value}，仅 pending/human_review 状态可审批",
        )
    _committee_repository.update_case_status(case_id, CaseStatus.REJECT)
    reviewer = (payload or {}).get("reviewer", "")
    comment = (payload or {}).get("comment", "")
    _committee_event_store.append(case_id, "human_review_resolved", {
        "decision": "reject",
        "reviewer": reviewer,
        "comment": comment,
    })
    # 高危否决即审计：操作者绑定登录身份
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="committee",
            action="high_risk_reject",
            detail={"case_id": case_id, "decision": "reject", "comment": comment},
            operator=(current.username if current else "") or reviewer or "unknown",
            confirmed=True,
            resource_type="committee_case",
            resource_id=case_id,
        ))
    except Exception:
        logger.warning("高危否决审计写入失败 case_id=%s", case_id, exc_info=True)
    logger.info(
        "High-risk AI action rejected (case_id=%s, reviewer=%s)", case_id, reviewer or "pm",
    )
    return {"case_id": case_id, "status": "reject", "decision": "reject"}


# ===========================================================================
# 项目管理 API
# ===========================================================================

_project_store = ProjectStore()
_experiment_analyst = ExperimentAnalystAgent()
_literature_researcher = LiteratureResearcherAgent(enable_web_api=True)

@app.post("/projects", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_project(req: ProjectCreateRequest):
    # 拒绝空值与 "????" 类占位符，防止脏数据进入项目主档
    for label, value in (("目标应用", req.target_application), ("负责人", req.owner)):
        v = (value or "").strip()
        if not v or set(v) <= {"?"}:
            raise HTTPException(status_code=400, detail=f"{label}不能为空，也不能是占位符")
    if req.start_date and req.end_date and req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="计划结束日期不能早于开始日期")
    if _project_store.get_by_name(req.name):
        raise HTTPException(status_code=409, detail=f"项目名称「{req.name}」已存在，请更换名称")
    # 评测修复 BEMCL-VAL-P3-003：target_properties/tasks 结构校验，非法返回 400
    clean_props = _validate_target_properties(req.target_properties)
    clean_tasks = _validate_project_tasks(req.tasks)
    project = Project(
        name=req.name,
        target_application=req.target_application,
        current_stage=req.current_stage,
        target_properties=clean_props,
        owner=req.owner,
        notes=req.notes,
        department=req.department,
        start_date=req.start_date,
        end_date=req.end_date,
        budget=req.budget,
        iteration_progress=req.iteration_progress,
        tasks=clean_tasks,
    )
    return _project_store.create(project).model_dump()


@app.put("/projects/{project_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_project(project_id: str, req: ProjectCreateRequest):
    existing = _project_store.get(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="项目不存在")
    if req.start_date and req.end_date and req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="计划结束日期不能早于开始日期")
    dup = _project_store.get_by_name(req.name)
    if dup and dup.project_id != project_id:
        raise HTTPException(status_code=409, detail=f"项目名称「{req.name}」已存在，请更换名称")
    # 评测修复 BEMCL-VAL-P3-003：target_properties/tasks 结构校验，非法返回 400
    clean_props = _validate_target_properties(req.target_properties)
    clean_tasks = _validate_project_tasks(req.tasks)
    updated = existing.model_copy(update={
        "name": req.name,
        "target_application": req.target_application,
        "current_stage": req.current_stage,
        "target_properties": clean_props,
        "owner": req.owner,
        "notes": req.notes,
        "department": req.department,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "budget": req.budget,
        "iteration_progress": req.iteration_progress,
        "tasks": clean_tasks,
    })
    return _project_store.update(updated).model_dump()


@app.post("/projects/decompose", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def decompose_project(req: ProjectDecomposeRequest):
    """调用 AI 拆解项目目标为具体任务列表。

    每个任务包含：标题、交付物（材料）、目标属性（含优化方向与阈值）。
    若请求中携带 agent_id，则使用该 Agent（通常为项目经理）的 llm_model 与
    人设（description / expertise / capabilities）进行调用，使产出更贴合该 Agent 的角色定位。
    """
    from .agent_team.agents.literature_researcher import _LLMClient

    # 解析触发拆解的 Agent 信息（人设 + llm_model）
    agent_persona = ""
    agent_model: str | None = None
    if req.agent_id:
        _require_agent_team()
        agent_def = _registry.get_agent(req.agent_id)
        if agent_def is None:
            raise HTTPException(status_code=404, detail=f"Agent 不存在：{req.agent_id}")
        # 拼装人设片段：角色描述 + 专长 + 能力
        persona_parts: list[str] = [f"你的角色是「{agent_def.name}」。"]
        if agent_def.description:
            persona_parts.append(f"角色职责：{agent_def.description}")
        if agent_def.expertise:
            persona_parts.append("专长领域：" + "、".join(agent_def.expertise))
        if agent_def.capabilities:
            persona_parts.append("具备能力：" + "、".join(agent_def.capabilities))
        if agent_def.max_autonomy_level:
            persona_parts.append(f"自主等级：{agent_def.max_autonomy_level}")
        agent_persona = "\n".join(persona_parts) + "\n\n"
        # 必须使用 Agent 显式配置的 llm_model，禁止 None 或空字符串，避免静默走默认路径
        if not agent_def.llm_model:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"智能体「{agent_def.name}」未配置 llm_model，无法执行 LLM 调用。"
                    "请在「智能体管理」中为该智能体显式设置大模型。"
                ),
            )
        agent_model = agent_def.llm_model

    system_prompt = (
        agent_persona
        + "你是高分子改性塑料研发项目的任务拆解专家。请根据项目名称和研发目标，"
        "拆解出 1-3 个具体可执行的任务。每个任务对应一个交付物（某种材料），"
        "并给出该材料的目标属性（含优化方向与阈值）。\n\n"
        "输出必须是严格 JSON 数组，不要包含 markdown 代码块标记或任何额外说明。"
        "数组中每个元素格式如下：\n"
        "{\n"
        '  "task_id": "唯一标识，UUID 格式字符串",\n'
        '  "title": "任务标题，简洁描述要做什么",\n'
        '  "deliverable": "交付物名称，即最终要产出的材料",\n'
        '  "target_properties": [\n'
        '    {"name": "属性名（英文 key，如 tensile_strength）", '
        '"direction": "maximize 或 minimize", "min": 数值或 null, "max": 数值或 null}\n'
        "  ]\n"
        "}\n"
        "要求：\n"
        "1. 必须返回合法 JSON 数组。\n"
        "2. task_id 必须是合法 UUID 字符串。\n"
        "3. direction 只能是 maximize 或 minimize。\n"
        "4. 属性名使用英文 snake_case，参考高分子改性塑料常见属性："
        "tensile_strength / flexural_modulus / impact_strength / heat_deflection_temp / "
        "melt_flow_index / elongation_at_break / thermal_stability / crystallinity 等。"
    )
    user_prompt = (
        f"项目名称：{req.name}\n"
        f"研发目标：{req.goal}\n"
        f"项目截止日期：{req.end_date or '未指定'}"
    )

    # 计算输入参数哈希快照（用于 AI 输出溯源）
    input_snapshot_hash = _compute_input_snapshot({
        "name": req.name,
        "goal": req.goal,
        "end_date": req.end_date,
        "agent_id": req.agent_id,
    })

    llm = _LLMClient()
    try:
        content = await llm.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
            model=agent_model,
        )
    except Exception as e:
        logger.warning("项目目标拆解 LLM 调用失败: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 拆解失败：{e}") from e

    tasks = _parse_decompose_response(content)
    if not tasks:
        raise HTTPException(status_code=502, detail="AI 未能生成有效任务，请重试或调整目标描述")
    # 补充 ai_meta（用于 AI 输出溯源）
    from datetime import datetime as _dt, timezone
    return {
        "tasks": tasks,
        "ai_meta": {
            "input_snapshot_hash": input_snapshot_hash,
            "model_version": agent_model or "internlm-v1",
            "generated_at": _dt.now(timezone.utc).isoformat(),
        },
    }


def _parse_decompose_response(content: str) -> list[dict]:
    """解析 LLM 返回的任务列表 JSON，做基本校验与补全。"""
    import uuid as _uuid

    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("项目拆解 JSON 解析失败: %s (raw=%r)", e, text[:200])
        return []

    # 兼容 LLM 把数组包成对象的情况
    if isinstance(data, dict):
        for key in ("tasks", "task_list", "result"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
    if not isinstance(data, list):
        logger.warning("项目拆解输出不是数组: %r", type(data))
        return []

    tasks: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        task_id = item.get("task_id") or ""
        try:
            _uuid.UUID(task_id)
        except (ValueError, TypeError):
            task_id = str(_uuid.uuid4())
        props = item.get("target_properties") or []
        clean_props = []
        if isinstance(props, list):
            for p in props:
                if not isinstance(p, dict):
                    continue
                name = (p.get("name") or "").strip()
                if not name:
                    continue
                direction = p.get("direction") or "maximize"
                if direction not in ("maximize", "minimize"):
                    direction = "maximize"
                clean_props.append({
                    "name": name,
                    "direction": direction,
                    "min": p.get("min"),
                    "max": p.get("max"),
                })
        tasks.append({
            "task_id": task_id,
            "title": title,
            "deliverable": (item.get("deliverable") or "").strip(),
            "target_properties": clean_props,
        })
    return tasks


@app.delete("/projects/{project_id}", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def delete_project(project_id: str):
    """删除项目。存在下游引用（候选材料/实验任务）时拒绝删除，保护数据链路。

    守卫同时检查 projects.projects 表的缓存字段（candidate_ids /
    experiment_order_ids）与 experiment.candidates / experiment.experiment_orders
    实际表数据，避免缓存过期导致 DB FK 拒绝（ERR-MS322YDF-01）。
    """
    existing = _project_store.get(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 1. 实际表直查：experiment_orders（FK RESTRICT，最关键）
    actual_orders = agent.experiment_controller._store.list_orders(project_id=project_id)
    # 2. 实际表直查：candidates（FK ON DELETE SET NULL，但仍提示用户）
    actual_candidates = app.state.candidate_store.list_all(project_id=project_id)

    linked = []
    if actual_candidates:
        linked.append(f"{len(actual_candidates)} 个候选材料")
    if actual_orders:
        linked.append(f"{len(actual_orders)} 个实验任务单")
    tasks = _project_store.get_project_tasks(project_id)
    if tasks:
        linked.append(f"{len(tasks)} 个项目任务")
    if linked:
        raise HTTPException(
            status_code=409,
            detail=f"项目存在下游引用（{'、'.join(linked)}），不允许删除；请先解除关联或归档",
        )
    _project_store.delete(project_id)
    return {"status": "deleted", "project_id": project_id}

# 评测修复 BEMCL-AUTH-P3-001：项目数据匿名不可访问，未登录返回 401
@app.get("/projects", dependencies=[Depends(require_login)])
async def list_projects():
    return [p.model_dump() for p in _project_store.list_all()]

@app.get("/projects/{project_id}", dependencies=[Depends(require_login)])
async def get_project(project_id: str):
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return p.model_dump()


@app.get("/projects/{project_id}/progress", dependencies=[Depends(require_login)])
async def get_project_progress(project_id: str):
    """自动计算项目进度，联动下游任务（实验工作台任务完成率 + 候选材料筛选进度）。

    进度构成：
    - 实验任务完成率（权重 60%）：completed_orders / total_orders
    - 候选材料筛选进度（权重 40%）：min(candidate_count / 10, 1.0)
    - 若无任何下游任务数据，回退到手动填写的 iteration_progress
    """
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 统计实验任务单完成情况
    orders = agent.experiment_controller._store.list_orders(project_id=project_id)
    total_orders = len(orders)
    completed_orders = sum(1 for o in orders if o.status == "COMPLETED")
    experiment_rate = (completed_orders / total_orders) if total_orders > 0 else 0.0

    candidate_count = len(p.candidate_ids)
    candidate_progress = min(candidate_count / 10.0, 1.0)

    has_downstream = total_orders > 0 or candidate_count > 0
    if has_downstream:
        auto_progress = round(experiment_rate * 60 + candidate_progress * 40)
    else:
        # 无下游数据时回退到手动值
        auto_progress = p.iteration_progress

    return {
        "project_id": project_id,
        "auto_progress": auto_progress,
        "manual_progress": p.iteration_progress,
        "using_auto": has_downstream,
        "experiment_completion": {
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "rate": round(experiment_rate, 3),
        },
        "candidate_count": candidate_count,
        "stage": p.current_stage,
    }


@app.get("/projects/{project_id}/tasks", dependencies=[Depends(require_login)])
async def get_project_tasks(project_id: str):
    """获取项目关联的任务列表。"""
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _project_store.get_project_tasks(project_id)


class ProjectTaskRequest(BaseModel):
    """新增/编辑项目任务的请求体。"""
    title: str = Field(..., min_length=1)
    deliverable: str = ""
    target_properties: list[dict] = Field(default_factory=list)
    status: str = "draft"
    assignee: str = ""


@app.post("/projects/{project_id}/tasks", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_project_task(project_id: str, req: ProjectTaskRequest):
    """为项目手工新增一个任务。"""
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    # 校验 target_properties 字段（评测修复 P3-3：非法结构返回 400）
    clean_props = _validate_target_properties(req.target_properties)
    # sort_order 取当前项目任务数（追加到末尾）
    existing = _project_store.list_tasks(project_id)
    task = ProjectTask(
        task_id=str(uuid.uuid4()),
        project_id=project_id,
        title=req.title.strip(),
        deliverable=req.deliverable.strip(),
        target_properties=clean_props,
        status=req.status or "draft",
        assignee=req.assignee or "",
        sort_order=len(existing),
    )
    saved = _project_store.create_task(task)
    return saved.model_dump()


@app.put("/projects/{project_id}/tasks/{task_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_project_task(project_id: str, task_id: str, req: ProjectTaskRequest):
    """编辑项目下的指定任务。"""
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = _project_store.get_task(task_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    clean_props = _validate_target_properties(req.target_properties)
    updated = existing.model_copy(update={
        "title": req.title.strip(),
        "deliverable": req.deliverable.strip(),
        "target_properties": clean_props,
        "status": req.status or existing.status,
        "assignee": req.assignee or existing.assignee,
    })
    saved = _project_store.update_task(updated)
    return saved.model_dump()


@app.delete("/projects/{project_id}/tasks/{task_id}", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def delete_project_task(project_id: str, task_id: str):
    """删除项目下的指定任务。"""
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = _project_store.get_task(task_id)
    if not existing or existing.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    _project_store.delete_task(task_id)
    return {"ok": True, "task_id": task_id}


def _allowed_property_units() -> set[str]:
    """从 MDM 特性主数据收集单位白名单（default_unit 去重）。

    评测修复 BEMCL-VAL-P3-003：MDM 无特性数据或查询失败时返回空集合，
    调用方据此跳过单位白名单校验，避免新环境无法创建项目。
    """
    try:
        store = app.state.cimc_store
        return {
            p.default_unit.strip()
            for p in store.list_properties()
            if p.default_unit and p.default_unit.strip()
        }
    except Exception as e:
        logger.warning("读取 MDM 单位白名单失败: %s", e)
        return set()


def _validate_target_properties(props: list[dict], field_label: str = "target_properties") -> list[dict]:
    """校验并规范化 target_properties 结构，非法时抛 400。

    评测修复 BEMCL-VAL-P3-003：
    - 每项必须为含非空 name 的对象（property 作为 name 的兼容别名）
    - direction 白名单：maximize / minimize（缺省 maximize）
    - min/max/threshold/target_value 必须为数字或空；min ≤ max
    - unit 若提供，必须在 MDM 特性单位白名单内（MDM 无数据时跳过）
    属性名不做 MDM 白名单：前端与 AI 拆解允许自由命名，MDM 特性库未必全覆盖。
    """
    if props is None:
        return []
    if not isinstance(props, list):
        raise HTTPException(status_code=400, detail=f"{field_label} 必须是数组")
    result: list[dict] = []
    for i, p in enumerate(props):
        if not isinstance(p, dict):
            raise HTTPException(status_code=400, detail=f"{field_label}[{i}] 必须是对象")
        name = (p.get("name") or p.get("property") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail=f"{field_label}[{i}] 缺少属性名 name")
        direction = p.get("direction") or "maximize"
        if direction not in ("maximize", "minimize"):
            raise HTTPException(
                status_code=400,
                detail=f"{field_label}[{i}].direction 必须是 maximize 或 minimize，当前值: {direction}",
            )
        entry: dict = {"name": name, "direction": direction}
        for num_field in ("min", "max", "threshold", "target_value"):
            v = p.get(num_field)
            if v is None or v == "":
                entry[num_field] = None
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                try:
                    v = float(str(v))
                except (TypeError, ValueError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"{field_label}[{i}].{num_field} 必须是数字，当前值: {p.get(num_field)!r}",
                    )
            entry[num_field] = v
        if entry["min"] is not None and entry["max"] is not None and entry["min"] > entry["max"]:
            raise HTTPException(
                status_code=400,
                detail=f"{field_label}[{i}] 的 min({entry['min']}) 不能大于 max({entry['max']})",
            )
        unit = (p.get("unit") or "").strip()
        if unit:
            allowed = _allowed_property_units()
            if allowed and unit not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_label}[{i}].unit 单位「{unit}」不在 MDM 白名单内，可选: {sorted(allowed)}",
                )
            entry["unit"] = unit
        result.append(entry)
    return result


def _validate_project_tasks(tasks: list[dict]) -> list[dict]:
    """校验并规范化项目内嵌任务列表结构，非法时抛 400。

    评测修复 BEMCL-VAL-P3-003：每项必须含非空 title（name 作为兼容别名），
    target_properties 递归走结构校验；其余字段（task_id/deliverable/status/
    assignee/milestone/owner 等）原样保留。
    """
    if tasks is None:
        return []
    if not isinstance(tasks, list):
        raise HTTPException(status_code=400, detail="tasks 必须是数组")
    result: list[dict] = []
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            raise HTTPException(status_code=400, detail=f"tasks[{i}] 必须是对象")
        title = (t.get("title") or t.get("name") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail=f"tasks[{i}] 缺少任务标题 title")
        entry = dict(t)
        entry["title"] = title
        entry["target_properties"] = _validate_target_properties(
            t.get("target_properties") or [], f"tasks[{i}].target_properties"
        )
        result.append(entry)
    return result


# ECMLStep → 中文阶段标签映射（用于任务卡片显示当前所处阶段）
_ECML_STEP_LABELS = {
    "step1_route": "材料路由",
    "step2_generate": "生成候选",
    "step3_synthesis_check": "合成可行性校验",
    "step3_industrialization": "可制造性论证",
    "step4_predict": "性能预测",
    "step5_verify": "DFT 验证",
    "step6_experiment": "实验阶段",
    "waiting_for_data": "等待实验数据",
    "step7_feedback": "反馈学习",
}


@app.get("/projects/{project_id}/stage-status", dependencies=[Depends(require_login)])
async def get_project_stage_status(project_id: str):
    """聚合返回项目当前所处阶段（含每个 task 的 ECML 细粒度 step + 第几轮 + 实验任务单汇总）。

    数据来源：
    - projects.current_stage：项目级粗粒度阶段（立项/筛选/中试/验证/定型）
    - projects.tasks：项目下所有任务
    - ecml.ecml_runs_index（按 task_id 关联）：每个 task 的 ECML 闭环细粒度 step 与 iteration_id
    - experiment.experiment_orders（按 task_id 关联）：每个 task 的实验任务单状态分布
    """
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    engine = _project_store.engine

    # 1. 取项目下所有任务（projects.tasks 关系表）
    tasks = _project_store.list_tasks(project_id)

    # 2. 按 task_id 维度聚合 ECML run 信息
    task_ids = [t.task_id for t in tasks if t.task_id]
    task_ecml_map: dict[str, dict] = {}
    if task_ids:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT DISTINCT ON (task_id)
                            task_id, run_id, scenario_id, status, iteration_id,
                            is_complete, run_status, created_at
                       FROM ecml.ecml_runs_index
                       WHERE task_id = ANY(:task_ids)
                       ORDER BY task_id, created_at DESC NULLS LAST"""),
                {"task_ids": task_ids},
            ).fetchall()
        for r in rows:
            tid = r[0]
            step_raw = r[3] or ""
            task_ecml_map[tid] = {
                "run_id": r[1],
                "scenario_id": r[2],
                "step": step_raw,
                "step_label": _ECML_STEP_LABELS.get(step_raw, step_raw or "未知"),
                "iteration_id": r[4] or 1,
                "is_complete": bool(r[5]),
                "run_status": r[6] or "",
                "updated_at": _iso(r[7]) if r[7] else "",
            }

    # 3. 按 task_id 维度聚合实验任务单
    task_orders_map: dict[str, list] = {}
    if task_ids:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT task_id, order_id, status
                       FROM experiment.experiment_orders
                       WHERE task_id = ANY(:task_ids)"""),
                {"task_ids": task_ids},
            ).fetchall()
        for r in rows:
            tid = r[0] or ""
            if not tid:
                continue
            task_orders_map.setdefault(tid, []).append({
                "order_id": r[1],
                "status": r[2] or "",
            })

    # 4. 组装每个 task 的阶段信息
    task_stages = []
    for t in tasks:
        ecml_info = task_ecml_map.get(t.task_id)
        orders = task_orders_map.get(t.task_id, [])
        by_status: dict[str, int] = {}
        for o in orders:
            by_status[o["status"]] = by_status.get(o["status"], 0) + 1

        # 推断 task 当前所处阶段标签（无 ECML run 时按实验任务单状态推断）
        if ecml_info:
            stage_label = ecml_info["step_label"]
            iteration_id = ecml_info["iteration_id"]
        elif orders:
            # 有实验任务单但无 ECML run：视为已进入实验阶段
            stage_label = "实验阶段"
            iteration_id = 1
        else:
            stage_label = "未启动"
            iteration_id = 0

        task_stages.append({
            "task_id": t.task_id,
            "title": t.title,
            "deliverable": t.deliverable,
            "stage_label": stage_label,
            "iteration_id": iteration_id,
            "ecml": ecml_info,
            "experiment_orders_summary": {
                "total": len(orders),
                "by_status": by_status,
            },
        })

    # 5. 兼容旧字段：保留项目级聚合（取最新一条 ECML run）
    project_ecml = None
    if task_ecml_map:
        # 取 updated_at 最新的
        project_ecml = max(task_ecml_map.values(),
                           key=lambda x: x.get("updated_at") or "")

    # 6. 全项目实验任务单汇总（兼容旧字段）
    all_orders = agent.experiment_controller._store.list_orders(project_id=project_id)
    project_by_status: dict[str, int] = {}
    for o in all_orders:
        project_by_status[o.status] = project_by_status.get(o.status, 0) + 1

    return {
        "project_id": project_id,
        "current_stage": p.current_stage,
        "ecml": project_ecml,  # 兼容旧字段
        "experiment_orders_summary": {  # 兼容旧字段
            "total": len(all_orders),
            "by_status": project_by_status,
        },
        "tasks": task_stages,  # 新字段：按 task 维度返回
    }


# ── 实体关联图谱 ─────────────────────────────────────────
# 节点类型常量（前端着色与图标映射依据）
_ENTITY_NODE_TYPES = {
    "project": "项目",
    "task": "任务",
    "candidate": "候选材料",
    "bom": "BOM 方案",
    "process": "工艺方案",
    "experiment_order": "实验任务单",
    "test_task": "测试任务",
    "sample": "样品",
    "result_record": "实验数据",
    "ecml_run": "ECML 迭代",
}

# 节点分层（用于前端分层布局：layer 越大越靠下）
_ENTITY_NODE_LAYER = {
    "project": 0,
    "task": 1,
    "candidate": 2,
    "ecml_run": 2,  # ECML run 与候选同层（task → ecml_run 也常见）
    "experiment_order": 2,  # 实验任务单是 task 的直接子节点
    "bom": 3,
    "process": 4,
    "test_task": 3,
    "sample": 4,
    "result_record": 5,
}


@app.get("/projects/{project_id}/entity-graph", dependencies=[Depends(require_login)])
async def get_project_entity_graph(project_id: str, task_id: str = ""):
    """聚合返回项目下所有业务实体的关联图谱（节点 + 边 + 状态）。

    用于前端"实体图谱"Tab 可视化：把 Project / Task / Candidate / BOM / Process /
    ExperimentOrder / TestTask / Sample / ResultRecord / ECMLRun 串成一张图。

    查询参数：
    - task_id：可选，按任务过滤，实现任务级追踪

    返回格式：
    - nodes: [{id, label, type, status, layer, parent_id, ...metadata}]
    - edges: [{source, target, label}]
    - stats: 各类型节点数量统计
    - partial: 是否为部分数据（某些 store 查询失败时为 True）
    """
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")

    engine = _project_store.engine
    nodes: list[dict] = []
    edges: list[dict] = []
    partial = False  # 标记是否有部分查询失败

    # 0. 项目根节点
    nodes.append({
        "id": f"project:{project_id}",
        "label": p.name or project_id,
        "type": "project",
        "status": p.current_stage or "",
        "layer": _ENTITY_NODE_LAYER["project"],
        "project_id": project_id,
    })

    # 1. 任务节点
    tasks = _project_store.list_tasks(project_id)
    if task_id:
        tasks = [t for t in tasks if t.task_id == task_id]
    for t in tasks:
        nodes.append({
            "id": f"task:{t.task_id}",
            "label": t.title or t.task_id,
            "type": "task",
            "status": t.status or "",
            "layer": _ENTITY_NODE_LAYER["task"],
            "parent_id": f"project:{project_id}",
            "task_id": t.task_id,
            "deliverable": t.deliverable or "",
        })
        edges.append({
            "source": f"project:{project_id}",
            "target": f"task:{t.task_id}",
            "label": "包含任务",
        })

    task_ids = [t.task_id for t in tasks if t.task_id]

    # 2. 候选材料节点（批量：list_all 一次查全量，按 task_id 过滤）
    candidate_store = getattr(app.state, "candidate_store", None)
    if candidate_store is not None:
        try:
            if task_id:
                # 单任务：直接按 task_id 查
                candidates = candidate_store.list_all(task_id=task_id)
            elif task_ids:
                # 多任务：查全量后按 task_id 集合过滤
                all_candidates = candidate_store.list_all()
                task_id_set = set(task_ids)
                candidates = [c for c in all_candidates if c.task_id in task_id_set]
            else:
                candidates = []
            for c in candidates:
                tid = c.task_id or ""
                nodes.append({
                    "id": f"candidate:{c.candidate_id}",
                    "label": c.name or c.smiles or c.candidate_id,
                    "type": "candidate",
                    "status": c.source or "",
                    "layer": _ENTITY_NODE_LAYER["candidate"],
                    "parent_id": f"task:{tid}" if tid else "",
                    "candidate_id": c.candidate_id,
                    "candidate_type": c.candidate_type,
                    "score": c.multi_objective_score,
                })
                if tid:
                    edges.append({
                        "source": f"task:{tid}",
                        "target": f"candidate:{c.candidate_id}",
                        "label": "候选材料",
                    })
        except Exception as e:
            logger.warning("entity-graph: 候选材料查询失败 project=%s: %s", project_id, e)
            partial = True

    # 3. ECML 迭代节点（按 task_id 反查 ecml_runs_index）
    if task_ids:
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("""SELECT run_id, task_id, status, iteration_id, is_complete, parent_run_id
                           FROM ecml.ecml_runs_index
                           WHERE task_id = ANY(:task_ids)
                           ORDER BY created_at DESC"""),
                    {"task_ids": task_ids},
                ).fetchall()
            for r in rows:
                rid = r[0] or ""
                tid = r[1] or ""
                if not rid:
                    continue
                step_raw = r[2] or ""
                nodes.append({
                    "id": f"ecml:{rid}",
                    "label": f"ECML {rid[:12]}{'…' if len(rid) > 12 else ''}",
                    "type": "ecml_run",
                    "status": _ECML_STEP_LABELS.get(step_raw, step_raw or ""),
                    "layer": _ENTITY_NODE_LAYER["ecml_run"],
                    "parent_id": f"task:{tid}" if tid else "",
                    "run_id": rid,
                    "step": step_raw,
                    "iteration_id": r[3] or 1,
                    "is_complete": bool(r[4]),
                    "parent_run_id": r[5] or "",
                })
                if tid:
                    edges.append({
                        "source": f"task:{tid}",
                        "target": f"ecml:{rid}",
                        "label": "ECML 闭环",
                    })
        except Exception as e:
            logger.warning("entity-graph: ECML run 查询失败 project=%s: %s", project_id, e)
            partial = True

    # 4. BOM 方案节点（批量：查全量后按 task_id 集合过滤）
    bom_store = getattr(app.state, "bom_store", None)
    bom_ids_seen: set[str] = set()
    if bom_store is not None and task_ids:
        try:
            all_boms = bom_store.list_all()
            task_id_set = set(task_ids)
            boms = [b for b in all_boms if b.task_id in task_id_set]
            for b in boms:
                bom_ids_seen.add(b.bom_id)
                nodes.append({
                    "id": f"bom:{b.bom_id}",
                    "label": b.name or b.bom_id,
                    "type": "bom",
                    "status": b.status or "",
                    "layer": _ENTITY_NODE_LAYER["bom"],
                    "parent_id": f"candidate:{b.candidate_id}" if b.candidate_id else "",
                    "bom_id": b.bom_id,
                    "candidate_id": b.candidate_id,
                })
                if b.candidate_id:
                    edges.append({
                        "source": f"candidate:{b.candidate_id}",
                        "target": f"bom:{b.bom_id}",
                        "label": "BOM 方案",
                    })
        except Exception as e:
            logger.warning("entity-graph: BOM 查询失败 project=%s: %s", project_id, e)
            partial = True

    # 5. 工艺方案节点（按 bom_id 反查，1:1）— 使用 app.state.process_scheme_store
    process_scheme_store = getattr(app.state, "process_scheme_store", None)
    if process_scheme_store is not None and bom_ids_seen:
        try:
            for bid in bom_ids_seen:
                ps = process_scheme_store.get_by_bom(bid)
                if ps is None:
                    continue
                nodes.append({
                    "id": f"process:{ps.process_id}",
                    "label": f"工艺 {ps.process_id[:8]}",
                    "type": "process",
                    "status": "",
                    "layer": _ENTITY_NODE_LAYER["process"],
                    "parent_id": f"bom:{bid}",
                    "process_id": ps.process_id,
                    "bom_id": bid,
                })
                edges.append({
                    "source": f"bom:{bid}",
                    "target": f"process:{ps.process_id}",
                    "label": "工艺方案",
                })
        except Exception as e:
            logger.warning("entity-graph: 工艺方案查询失败 project=%s: %s", project_id, e)
            partial = True

    # 6. 实验任务单节点（按 project_id/task_id 反查）
    try:
        orders = agent.experiment_controller._store.list_orders(
            project_id=project_id,
            task_id=task_id or None,
        )
    except Exception as e:
        logger.warning("entity-graph: 实验任务单查询失败 project=%s: %s", project_id, e)
        orders = []
        partial = True
    for o in orders:
        # 评测修复：实验任务单的 parent_id 优先用 task_id（任务下方），
        # 其次 candidate_id（候选材料下方），最后才 project（项目下方）
        if o.task_id:
            _order_parent = f"task:{o.task_id}"
        elif o.candidate_id:
            _order_parent = f"candidate:{o.candidate_id}"
        elif o.bom_id:
            _order_parent = f"bom:{o.bom_id}"
        else:
            _order_parent = f"project:{project_id}"
        nodes.append({
            "id": f"order:{o.order_id}",
            "label": o.order_id,
            "type": "experiment_order",
            "status": o.status or "",
            "layer": _ENTITY_NODE_LAYER["experiment_order"],
            "parent_id": _order_parent,
            "order_id": o.order_id,
            "candidate_id": o.candidate_id,
            "bom_id": o.bom_id,
            "task_id": o.task_id,
            "execution_mode": o.execution_mode,
            "priority": o.priority,
        })
        edges.append({
            "source": _order_parent,
            "target": f"order:{o.order_id}",
            "label": "实验任务单",
        })

    # 7. 测试任务节点（批量：list_all 一次查全量，按 order_id 过滤）
    test_task_store = getattr(app.state, "test_task_store", None)
    if test_task_store is not None and orders:
        try:
            order_id_set = {o.order_id for o in orders}
            all_tts = test_task_store.list_all()
            tts = [t for t in all_tts if t.order_id in order_id_set]
            for tt in tts:
                nodes.append({
                    "id": f"test_task:{tt.test_task_id}",
                    "label": f"{tt.test_type or '测试'}",
                    "type": "test_task",
                    "status": tt.status or "",
                    "layer": _ENTITY_NODE_LAYER["test_task"],
                    "parent_id": f"order:{tt.order_id}",
                    "test_task_id": tt.test_task_id,
                    "order_id": tt.order_id,
                    "test_type": tt.test_type,
                })
                edges.append({
                    "source": f"order:{tt.order_id}",
                    "target": f"test_task:{tt.test_task_id}",
                    "label": "测试任务",
                })
        except Exception as e:
            logger.warning("entity-graph: 测试任务查询失败 project=%s: %s", project_id, e)
            partial = True

    # 8. 样品节点（批量：list_all 一次查全量，按 order_id 过滤）
    sample_store = getattr(app.state, "sample_store", None)
    if sample_store is not None and orders:
        try:
            all_samples = sample_store.list_all()
            order_id_set = {o.order_id for o in orders}
            samples_by_order: dict[str, list] = {}
            for s in all_samples:
                if s.source_order_id and s.source_order_id in order_id_set:
                    samples_by_order.setdefault(s.source_order_id, []).append(s)
            for o in orders:
                for s in samples_by_order.get(o.order_id, []):
                    nodes.append({
                        "id": f"sample:{s.sample_id}",
                        "label": s.name or s.sample_id,
                        "type": "sample",
                        "status": s.status.value if hasattr(s.status, 'value') else str(s.status),
                        "layer": _ENTITY_NODE_LAYER["sample"],
                        "parent_id": f"order:{o.order_id}",
                        "sample_id": s.sample_id,
                        "order_id": o.order_id,
                        "candidate_id": s.source_candidate_id or "",
                    })
                    edges.append({
                        "source": f"order:{o.order_id}",
                        "target": f"sample:{s.sample_id}",
                        "label": "样品",
                    })
        except Exception as e:
            logger.warning("entity-graph: 样品查询失败 project=%s: %s", project_id, e)
            partial = True

    # 9. 实验数据节点（按 order_id 反查，简化为按 order 聚合统计，避免节点过多）
    for o in orders:
        try:
            records = agent.experiment_controller._store.list_result_records(order_id=o.order_id)
        except Exception:
            records = []
        if not records:
            continue
        valid_count = sum(1 for r in records if r.qc_status in ("VALID", "VALID_WITH_WARNING"))
        nodes.append({
            "id": f"results:{o.order_id}",
            "label": f"实验数据 {len(records)} 条",
            "type": "result_record",
            "status": f"有效 {valid_count}/{len(records)}",
            "layer": _ENTITY_NODE_LAYER["result_record"],
            "parent_id": f"order:{o.order_id}",
            "order_id": o.order_id,
            "total": len(records),
            "valid": valid_count,
        })
        edges.append({
            "source": f"order:{o.order_id}",
            "target": f"results:{o.order_id}",
            "label": "实验数据",
        })

    # 统计
    stats: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "")
        stats[t] = stats.get(t, 0) + 1

    return {
        "project_id": project_id,
        "task_id_filter": task_id or "",
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "node_types": _ENTITY_NODE_TYPES,
        "partial": partial,
    }


# --- 项目子资源 API（评测修复 BEMCL-PROJ-P3-002）---

@app.get("/projects/{project_id}/candidates", dependencies=[Depends(require_login)])
async def list_project_candidates(project_id: str):
    """项目子资源：候选材料列表。

    主口径为 experiment.candidates.project_id 列；同时合并项目主档缓存
    candidate_ids 中 project_id 列未回填的历史数据，保证聚合视图完整。
    """
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    records = app.state.candidate_store.list_all(project_id=project_id)
    known = {r.candidate_id for r in records}
    for cid in (p.candidate_ids or []):
        if cid and cid not in known:
            extra = app.state.candidate_store.get(cid)
            if extra is not None:
                records.append(extra)
                known.add(cid)
    return {
        "project_id": project_id,
        "candidates": [r.model_dump() for r in records],
        "count": len(records),
    }


@app.get("/projects/{project_id}/samples", dependencies=[Depends(require_login)])
async def list_project_samples(project_id: str):
    """项目子资源：样品列表。

    样品表无 project_id 列，按业务链路反查：
    source_order_id ∈ 项目实验任务单 或 source_candidate_id ∈ 项目候选材料。
    """
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    orders = agent.experiment_controller._store.list_orders(project_id=project_id)
    order_ids = {o.order_id for o in orders if o.order_id}
    cand_ids = {c.candidate_id for c in app.state.candidate_store.list_all(project_id=project_id)}
    cand_ids |= {cid for cid in (p.candidate_ids or []) if cid}
    samples = [
        s for s in app.state.sample_store.list_all()
        if (s.source_order_id and s.source_order_id in order_ids)
        or (s.source_candidate_id and s.source_candidate_id in cand_ids)
    ]
    return {
        "project_id": project_id,
        "samples": [s.model_dump() for s in samples],
        "count": len(samples),
    }


@app.get("/projects/{project_id}/results", dependencies=[Depends(require_login)])
async def list_project_results(project_id: str):
    """项目子资源：实验结果列表（经 experiment_orders 关联反查项目）。"""
    p = _project_store.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    records = agent.query_experiments(project_id=project_id)
    return {
        "project_id": project_id,
        "results": [r.model_dump() for r in records],
        "count": len(records),
    }


# --- 设备台账 API ---

class EquipmentUpsertRequest(BaseModel):
    equipment_id: str = ""
    name: str = ""
    model: str = ""
    category: str = ""
    serial_number: str = ""
    location: str = ""
    status: str = "idle"
    last_calibration: str = ""
    next_calibration: str = ""
    responsible_person: str = ""
    purchase_date: str = ""
    notes: str = ""


@app.post("/equipment", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_equipment(req: EquipmentUpsertRequest):
    """创建设备。"""
    import uuid as _uuid
    store: EquipmentStore = app.state.equipment_store
    if req.equipment_id and store.get(req.equipment_id):
        raise HTTPException(status_code=409, detail=f"设备 {req.equipment_id} 已存在")
    # C3(P3-001)：设备序列号唯一性校验，杜绝同一仪器重复登记（型号+序列号相同视为重复）
    if req.serial_number:
        dup = store.find_by_serial(req.serial_number, exclude_id=req.equipment_id)
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"序列号 {req.serial_number} 已被设备 {dup.equipment_id} 登记（型号 {dup.model}），请勿重复登记",
            )
    eq = Equipment(
        equipment_id=req.equipment_id or f"EQUIP-{_uuid.uuid4().hex[:6].upper()}",
        name=req.name,
        model=req.model,
        category=req.category,
        serial_number=req.serial_number,
        location=req.location,
        status=EquipmentStatus(req.status),
        last_calibration=req.last_calibration,
        next_calibration=req.next_calibration,
        responsible_person=req.responsible_person,
        purchase_date=req.purchase_date,
        notes=req.notes,
    )
    # 评测修复 P2-1：存储层 MDM 校验失败（category/status 不存在）转为 400，而非 500
    try:
        store.save(eq)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return eq.model_dump()


@app.get("/equipment", dependencies=[Depends(require_login)])
async def list_equipment(category: str = "", status: str = ""):
    """查询设备列表，支持按类别和状态筛选。"""
    store: EquipmentStore = app.state.equipment_store
    items = store.list_all(category=category, status=status)
    return [e.model_dump() for e in items]


@app.get("/equipment/{equipment_id}", dependencies=[Depends(require_login)])
async def get_equipment(equipment_id: str):
    """查询单个设备。"""
    store: EquipmentStore = app.state.equipment_store
    eq = store.get(equipment_id)
    if eq is None:
        raise HTTPException(status_code=404, detail=f"设备 {equipment_id} 不存在")
    return eq.model_dump()


@app.put("/equipment/{equipment_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_equipment(equipment_id: str, req: EquipmentUpsertRequest):
    """更新设备信息。"""
    store: EquipmentStore = app.state.equipment_store
    existing = store.get(equipment_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"设备 {equipment_id} 不存在")
    eq = Equipment(
        equipment_id=equipment_id,
        name=req.name or existing.name,
        model=req.model or existing.model,
        category=req.category or existing.category,
        serial_number=req.serial_number or existing.serial_number,
        location=req.location or existing.location,
        status=EquipmentStatus(req.status) if req.status else existing.status,
        last_calibration=req.last_calibration or existing.last_calibration,
        next_calibration=req.next_calibration or existing.next_calibration,
        responsible_person=req.responsible_person or existing.responsible_person,
        purchase_date=req.purchase_date or existing.purchase_date,
        notes=req.notes if req.notes else existing.notes,
    )
    # 评测修复 P2-1：存储层 MDM 校验失败（category/status 不存在）转为 400，而非 500
    try:
        store.save(eq)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return eq.model_dump()


@app.delete("/equipment/{equipment_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_equipment(equipment_id: str):
    """删除设备（2B 数据治理：被实验任务引用的设备禁止删除，须先改为退役状态）。"""
    store: EquipmentStore = app.state.equipment_store
    if store.get(equipment_id) is None:
        raise HTTPException(status_code=404, detail=f"设备 {equipment_id} 不存在")
    # 引用检查：实验任务（订单）引用了该设备则禁止删除
    try:
        orders = agent.experiment_controller._store.list_orders()
    except Exception:  # noqa: BLE001 - 实验控制器不可用时放宽引用检查
        orders = []
    referenced = [o for o in orders if getattr(o, "equipment_id", "") == equipment_id]
    if referenced:
        raise HTTPException(
            status_code=409,
            detail=f"设备已被 {len(referenced)} 个实验任务引用，无法删除；请先将设备状态改为「退役」归档",
        )
    if not store.delete(equipment_id):
        raise HTTPException(status_code=404, detail=f"设备 {equipment_id} 不存在")
    return {"deleted": True, "equipment_id": equipment_id}


# --- 样品管理 API ---

class SampleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source_type: str = ""
    source_order_id: str = ""
    source_candidate_id: str = ""
    batch_number: str = ""
    quantity: float = Field(default=0.0, ge=0)
    unit: str = "g"
    status: str = "created"
    storage_location: str = ""
    storage_condition: str = ""
    notes: str = ""
    sample_code: str = ""  # 业务编号（可选，唯一）
    chemical_formula: str = ""
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    test_task_id: str = ""  # 业务链路：关联 experiment.test_tasks(test_task_id)


class SampleTransferRequest(BaseModel):
    to_status: str = ""
    to_location: str = ""
    transferred_by: str = ""
    notes: str = ""
    ai_initiated: bool = False  # T-031：AI 发起的"放行"流转进入人工确认三段式


@app.post("/samples", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_sample(req: SampleCreateRequest):
    """创建样品。"""
    import uuid as _uuid
    store: SampleStore = app.state.sample_store
    try:
        status = SampleStatus(req.status)
    except ValueError:
        status = SampleStatus.CREATED
    if req.sample_code and store.get_by_code(req.sample_code):
        raise HTTPException(status_code=409, detail=f"业务编号「{req.sample_code}」已存在")
    # 评测修复 P1-3：FK 前置校验，避免数据库层 IntegrityError 抛 500
    if req.source_candidate_id and app.state.candidate_store.get(req.source_candidate_id) is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {req.source_candidate_id} 不存在")
    if req.source_order_id and agent.experiment_controller._store.get_order(req.source_order_id) is None:
        raise HTTPException(status_code=404, detail=f"实验任务单 {req.source_order_id} 不存在")
    sample = Sample(
        sample_id=f"SMP_{_uuid.uuid4().hex[:8]}",
        name=req.name,
        source_type=req.source_type,
        source_order_id=req.source_order_id,
        source_candidate_id=req.source_candidate_id,
        batch_number=req.batch_number,
        quantity=req.quantity,
        unit=req.unit or "g",
        status=status,
        storage_location=req.storage_location,
        storage_condition=req.storage_condition,
        notes=req.notes,
        sample_code=req.sample_code,
        chemical_formula=req.chemical_formula,
        scenario_id=req.scenario_id or "",
        test_task_id=req.test_task_id or "",
    )
    store.save(sample)
    return sample.model_dump()


@app.put("/samples/{sample_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_sample(sample_id: str, req: SampleCreateRequest):
    """编辑样品基础信息（不改变状态，状态变更请走 /transfer 保留审计）。"""
    store: SampleStore = app.state.sample_store
    sample = store.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"样品 {sample_id} 不存在")
    if req.sample_code:
        dup = store.get_by_code(req.sample_code)
        if dup and dup.sample_id != sample_id:
            raise HTTPException(status_code=409, detail=f"业务编号「{req.sample_code}」已存在")
    # 评测修复 P1-3：FK 前置校验，避免数据库层 IntegrityError 抛 500
    if req.source_candidate_id and app.state.candidate_store.get(req.source_candidate_id) is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {req.source_candidate_id} 不存在")
    if req.source_order_id and agent.experiment_controller._store.get_order(req.source_order_id) is None:
        raise HTTPException(status_code=404, detail=f"实验任务单 {req.source_order_id} 不存在")
    sample.name = req.name
    sample.source_type = req.source_type
    sample.source_order_id = req.source_order_id
    sample.source_candidate_id = req.source_candidate_id
    sample.batch_number = req.batch_number
    sample.quantity = req.quantity
    sample.unit = req.unit or "g"
    sample.storage_location = req.storage_location
    sample.storage_condition = req.storage_condition
    sample.notes = req.notes
    sample.sample_code = req.sample_code
    sample.chemical_formula = req.chemical_formula
    sample.scenario_id = req.scenario_id or sample.scenario_id or ""
    sample.test_task_id = req.test_task_id or sample.test_task_id or ""
    store.save(sample)
    return sample.model_dump()


@app.delete("/samples/{sample_id}", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def delete_sample(sample_id: str):
    """删除样品。已发生流转的样品保留审计链，不允许物理删除。"""
    store: SampleStore = app.state.sample_store
    sample = store.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"样品 {sample_id} 不存在")
    if store.has_transfers(sample_id):
        raise HTTPException(
            status_code=409,
            detail="样品已存在流转记录，为保证审计可追溯不允许删除；可将其状态流转为「已废弃」",
        )
    store.delete(sample_id)
    return {"status": "deleted", "sample_id": sample_id}


@app.get("/samples", dependencies=[Depends(require_login)])
async def list_samples(include_demo: bool = False):
    """查询样品列表。

    D2(P2-002)：默认过滤 SEED_ 演示样品，include_demo=True 时包含。
    """
    store: SampleStore = app.state.sample_store
    samples = store.list_all()
    return _filter_demo([s.model_dump() for s in samples], include_demo)


@app.get("/samples/{sample_id}", dependencies=[Depends(require_login)])
async def get_sample(sample_id: str):
    """查询单个样品。"""
    store: SampleStore = app.state.sample_store
    sample = store.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"样品 {sample_id} 不存在")
    return sample.model_dump()


@app.put("/samples/{sample_id}/transfer", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def transfer_sample(sample_id: str, req: SampleTransferRequest, request: Request):
    """流转样品（更新状态和位置）。"""
    store: SampleStore = app.state.sample_store
    # T-031：AI 发起的样品"放行"(released) 流转需先经 Committee 人工确认
    # 注：released 不在 SampleStatus 枚举内，AI 放行属业务语义，由人工确认后处理
    # 服务端判定优先：验签 Agent 凭证 > 请求体自报标志
    if req.to_status == "released" and _is_ai_initiated(request, req.ai_initiated):
        return _require_high_risk_review_or_raise(
            "auto_release_sample",
            {"sample_id": sample_id, **req.model_dump()},
            initiator="ai",
        )
    try:
        to_status = SampleStatus(req.to_status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态值: {req.to_status}")
    # 区分"样品不存在"（404）与"非法迁移"（400）——store.transfer 对两者都返回 None
    if store.get(sample_id) is None:
        raise HTTPException(status_code=404, detail=f"样品 {sample_id} 不存在")
    transfer = store.transfer(
        sample_id=sample_id,
        to_status=to_status,
        to_location=req.to_location,
        transferred_by=req.transferred_by,
        notes=req.notes,
    )
    if transfer is None:
        raise HTTPException(
            status_code=400,
            detail=f"样品状态迁移未在 MDM 主数据中登记：{to_status.value}",
        )
    sample = store.get(sample_id)
    return {"sample": sample.model_dump(), "transfer": transfer.model_dump()}


@app.get("/samples/{sample_id}/transfers", dependencies=[Depends(require_login)])
async def list_sample_transfers(sample_id: str):
    """查询样品流转记录。"""
    store: SampleStore = app.state.sample_store
    sample = store.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"样品 {sample_id} 不存在")
    transfers = store.list_transfers(sample_id)
    return [t.model_dump() for t in transfers]


# --- 假设（Idea）并行验证 API ---

class IdeaCreateRequest(BaseModel):
    name: str = ""
    description: str = ""
    material_type: str = "molecule"  # molecule / crystal
    smiles: str = ""
    formula: str = ""
    target_properties: list[dict] = Field(default_factory=list)  # [{name, direction, target_value}]
    notes: str = ""


class IdeaStatusUpdateRequest(BaseModel):
    status: str = ""  # draft/verifying/verified/failed/preferred/eliminated
    notes: str = ""


class ParallelVerifyRequest(BaseModel):
    idea_ids: list[str] = Field(default_factory=list)


def _check_target_met(predicted: float, target_value, direction: str) -> bool:
    """判断预测值是否达标。target_value 为空时视为达标。"""
    if target_value is None or target_value == "":
        return True
    try:
        target = float(target_value)
    except (TypeError, ValueError):
        return True
    if direction == "minimize":
        return predicted <= target
    return predicted >= target


def _run_prediction_for_idea(idea: Idea) -> dict:
    """对单个 IDEA 执行性质预测（同步，CPU 密集）。

    根据 material_type 选择对应预测器，对每个目标属性运行预测，
    记录预测值/置信度/达标状态，并计算综合评分。
    """
    predictions = {}
    targets_met = 0
    total_targets = len(idea.target_properties)

    for target in idea.target_properties:
        prop_name = target.get("name", "")
        if not prop_name:
            continue
        direction = target.get("direction", "maximize")
        target_value = target.get("target_value")

        try:
            if idea.material_type == "crystal":
                features = {"formula": idea.formula, "smiles": idea.smiles}
                result = agent.crystal_predictor.predict(features, prop_name)
            else:
                features = {"smiles": idea.smiles, "formula": idea.formula}
                result = agent.polymer_predictor.predict(features, prop_name)

            predicted_value = float(result.value)
            met = _check_target_met(predicted_value, target_value, direction)
            predictions[prop_name] = {
                "value": predicted_value,
                "unit": result.unit,
                "confidence": float(result.confidence),
                "model": result.model,
                "target_value": target_value,
                "direction": direction,
                "met": met,
            }
            if met:
                targets_met += 1
        except Exception as e:
            predictions[prop_name] = {
                "error": str(e),
                "target_value": target_value,
                "direction": direction,
                "met": False,
            }

    score = (targets_met / total_targets) if total_targets > 0 else 0.0
    return {
        "predictions": predictions,
        "targets_met": targets_met,
        "total_targets": total_targets,
        "score": round(score, 4),
    }


async def verify_single_idea(idea_id: str) -> dict:
    """验证单个 IDEA：标记为 VERIFYING → 并行预测 → 更新状态与评分。"""
    store: IdeaStore = app.state.idea_store
    idea = store.get(idea_id)
    if not idea:
        return {"idea_id": idea_id, "status": "failed", "error": "idea not found"}

    store.update_status(idea_id, IdeaStatus.VERIFYING)

    try:
        result = await asyncio.to_thread(_run_prediction_for_idea, idea)
        idea.verification_result = result
        idea.score = result.get("score", 0.0)
        # 至少有一个属性达标即视为 VERIFIED，否则 FAILED
        idea.status = IdeaStatus.VERIFIED if result.get("targets_met", 0) > 0 else IdeaStatus.FAILED
        store.save(idea)
        return {
            "idea_id": idea_id,
            "status": idea.status.value,
            "score": idea.score,
            "result": result,
        }
    except Exception as e:
        idea.status = IdeaStatus.FAILED
        idea.verification_result = {"error": str(e)}
        store.save(idea)
        return {"idea_id": idea_id, "status": "failed", "error": str(e)}


@app.post("/ideas", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_idea(req: IdeaCreateRequest):
    """创建假设（Idea）。"""
    import uuid as _uuid
    store: IdeaStore = app.state.idea_store
    idea = Idea(
        idea_id=f"IDEA_{_uuid.uuid4().hex[:8]}",
        name=req.name,
        description=req.description,
        material_type=req.material_type or "molecule",
        smiles=req.smiles,
        formula=req.formula,
        target_properties=req.target_properties,
        notes=req.notes,
    )
    store.save(idea)
    return idea.model_dump()


@app.get("/ideas")
async def list_ideas(status: str = ""):
    """查询假设列表，可按状态筛选。"""
    store: IdeaStore = app.state.idea_store
    if status:
        try:
            idea_status = IdeaStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")
        ideas = store.list_by_status(idea_status)
    else:
        ideas = store.list_all()
    return [i.model_dump() for i in ideas]


@app.get("/ideas/{idea_id}")
async def get_idea(idea_id: str):
    """查询单个假设。"""
    store: IdeaStore = app.state.idea_store
    idea = store.get(idea_id)
    if idea is None:
        raise HTTPException(status_code=404, detail=f"假设 {idea_id} 不存在")
    return idea.model_dump()


@app.put("/ideas/{idea_id}/status", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_idea_status(idea_id: str, req: IdeaStatusUpdateRequest):
    """更新假设状态（如标记为 preferred / eliminated）。"""
    store: IdeaStore = app.state.idea_store
    try:
        idea_status = IdeaStatus(req.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态值: {req.status}")
    ok = store.update_status(idea_id, idea_status, notes=req.notes)
    if not ok:
        raise HTTPException(status_code=404, detail=f"假设 {idea_id} 不存在")
    idea = store.get(idea_id)
    return idea.model_dump()


@app.post("/ideas/parallel_verify", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def parallel_verify_ideas(req: ParallelVerifyRequest):
    """并行验证多个假设。

    对每个 IDEA 调用性质预测器（crystal_predictor / polymer_predictor），
    记录验证结果到 verification_result，更新状态为 VERIFIED 或 FAILED，
    计算综合评分（达标属性占比）。
    """
    if not req.idea_ids:
        raise HTTPException(status_code=400, detail="idea_ids 不能为空")
    tasks = [verify_single_idea(idea_id) for idea_id in req.idea_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 将异常对象转换为可序列化的字典
    serialized = []
    for idea_id, res in zip(req.idea_ids, results):
        if isinstance(res, Exception):
            serialized.append({
                "idea_id": idea_id,
                "status": "failed",
                "error": f"{type(res).__name__}: {res}",
            })
        else:
            serialized.append(res)
    return {"results": serialized, "count": len(serialized)}


# ===========================================================================
# 管理看板 API（F4：管理看板与资源监控）
# ===========================================================================

# 计算资源单价：每次 ECML 运行的成本（元），可按需调整
_ECML_RUN_UNIT_COST = 5.0
# 物料库存预警阈值（单位同 inventory_unit，默认 kg）
_MATERIAL_LOW_STOCK_THRESHOLD = 10.0


def _to_iso_str(value) -> str:
    """将 datetime / str / None 统一转为 ISO 字符串，供日期切片与比较使用。

    ExperimentDataStore.list_orders 返回的 created_at 为 datetime 对象，
    而 ECML state_store 返回 dict 中的时间戳为字符串，需统一后再切片。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _in_date_range(date_str: str | None, start_date: str | None, end_date: str | None) -> bool:
    """判断 ISO 日期字符串（如 '2024-01-15T10:30:00+00:00'）是否落在 [start_date, end_date] 区间内。

    start_date/end_date 为 'YYYY-MM-DD' 格式；任一为 None 表示该侧不限制。
    date_str 为空或非法时返回 True（保守策略：不剔除无时间戳的记录）。
    """
    if not start_date and not end_date:
        return True
    date_str = _to_iso_str(date_str)
    if not date_str:
        return True
    # 取前 10 位作为 YYYY-MM-DD 比较键
    day = date_str[:10]
    if len(day) < 10:
        return True
    if start_date and day < start_date:
        return False
    if end_date and day > end_date:
        return False
    return True


@app.get("/dashboard/overview")
async def dashboard_overview(
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD（含）"),
):
    """总览数据：项目/任务/候选/ECML/用户计数与状态分布（支持时间范围筛选）。"""
    # --- 项目 ---
    projects = [p for p in _project_store.list_all()
                if _in_date_range(p.created_at, start_date, end_date)]
    active_stages = {"立项", "筛选", "中试", "验证"}
    active_projects = sum(1 for p in projects if p.current_stage in active_stages)

    # --- 实验任务 ---
    orders = [o for o in agent.experiment_controller._store.list_orders()
              if _in_date_range(o.created_at, start_date, end_date)]
    status_counts: dict[str, int] = {}
    for o in orders:
        status_counts[o.status] = status_counts.get(o.status, 0) + 1

    # --- 候选材料（全局候选库计数，与 /stats 口径一致，避免多面板矛盾）---
    candidate_count = 0
    candidate_store = getattr(app.state, "candidate_store", None)
    if candidate_store is not None:
        try:
            candidate_count = sum(
                1 for c in candidate_store.list_all()
                if _in_date_range(getattr(c, "created_at", None), start_date, end_date)
            )
        except Exception:
            pass
    else:
        # 回退：按项目 candidate_ids 汇总去重
        candidate_ids: set[str] = set()
        for p in projects:
            for cid in p.candidate_ids:
                candidate_ids.add(cid)
        candidate_count = len(candidate_ids)

    # --- ECML 运行 ---
    try:
        runs = [r for r in agent.ecml.state_store.list_runs(limit=10000)
                if _in_date_range(r.get("updated_at") or r.get("created_at"), start_date, end_date)]
    except Exception:
        runs = []
    active_runs = sum(
        1 for r in runs
        if not r.get("is_complete") and r.get("status") != "timeout"
    )

    # --- 用户 ---
    users = [u for u in app.state.user_store.list_all()
             if _in_date_range(u.created_at, start_date, end_date)]
    role_counts: dict[str, int] = {}
    for u in users:
        role_counts[u.role.value] = role_counts.get(u.role.value, 0) + 1

    # 项目阶段分布（用于图表）
    stage_counts: dict[str, int] = {}
    for p in projects:
        stage_counts[p.current_stage] = stage_counts.get(p.current_stage, 0) + 1

    return {
        "projects": {
            "total": len(projects),
            "active": active_projects,
            "by_stage": stage_counts,
        },
        "experiments": {
            "total": len(orders),
            "by_status": status_counts,
        },
        "candidates": candidate_count,
        "ecml": {
            "total": len(runs),
            "active": active_runs,
        },
        "users": {
            "total": len(users),
            "by_role": role_counts,
        },
    }


@app.get("/dashboard/cost")
async def dashboard_cost(
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD（含）"),
):
    """成本分析：项目物料成本 + 计算资源成本 + 月度趋势（支持时间范围筛选）。"""
    # 各项目物料成本（按其实验任务 material_requirements 汇总）
    projects = _project_store.list_all()
    project_costs: list[dict] = []
    monthly_material: dict[str, float] = {}
    monthly_compute: dict[str, float] = {}

    for p in projects:
        orders = [o for o in agent.experiment_controller._store.list_orders(project_id=p.project_id)
                  if _in_date_range(o.created_at, start_date, end_date)]
        material_total = 0.0
        for o in orders:
            for item in o.material_requirements or []:
                qty = float(item.get("required_quantity") or 0)
                unit_price = float(item.get("unit_cost") or 0)
                material_total += qty * unit_price
            # 按月归集
            if o.created_at:
                month = _to_iso_str(o.created_at)[:7]  # YYYY-MM
                monthly_material[month] = monthly_material.get(month, 0.0) + sum(
                    float(i.get("required_quantity") or 0)
                    * float(i.get("unit_cost") or 0)
                    for i in (o.material_requirements or [])
                )
        project_costs.append({
            "project_id": p.project_id,
            "name": p.name,
            "material_cost": round(material_total, 2),
            "order_count": len(orders),
        })

    # 计算资源成本：ECML 运行次数 × 单价
    try:
        runs = [r for r in agent.ecml.state_store.list_runs(limit=10000)
                if _in_date_range(r.get("updated_at") or r.get("created_at"), start_date, end_date)]
    except Exception:
        runs = []
    compute_total = len(runs) * _ECML_RUN_UNIT_COST
    for r in runs:
        # 优先用 updated_at，回退 created_at
        ts = _to_iso_str(r.get("updated_at") or r.get("created_at"))
        if ts:
            month = ts[:7]
            monthly_compute[month] = monthly_compute.get(month, 0.0) + _ECML_RUN_UNIT_COST

    # 合并月度趋势
    months = sorted(set(list(monthly_material.keys()) + list(monthly_compute.keys())))
    monthly_trend = [
        {
            "month": m,
            "material_cost": round(monthly_material.get(m, 0.0), 2),
            "compute_cost": round(monthly_compute.get(m, 0.0), 2),
            "total": round(monthly_material.get(m, 0.0) + monthly_compute.get(m, 0.0), 2),
        }
        for m in months
    ]

    return {
        "project_costs": project_costs,
        "compute": {
            "total_runs": len(runs),
            "unit_cost": _ECML_RUN_UNIT_COST,
            "total_cost": round(compute_total, 2),
        },
        "monthly_trend": monthly_trend,
        "total_cost": round(
            sum(p["material_cost"] for p in project_costs) + compute_total, 2,
        ),
    }


@app.get("/dashboard/resources")
async def dashboard_resources(
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD（含）"),
):
    """资源使用：设备使用率/样品库存/物料预警/计算队列。

    设备/样品/物料为当前快照状态，不随时间范围变化；
    计算队列基于 ECML 运行记录，受时间范围筛选影响。
    """
    # 设备使用率（当前快照，不按时间筛选）
    equipment = app.state.equipment_store.list_all()
    equip_total = len(equipment)
    equip_in_use = sum(1 for e in equipment if e.status.value == "in_use")

    # 样品库存统计（按状态分组，当前快照）
    samples = app.state.sample_store.list_all()
    sample_by_status: dict[str, int] = {}
    for s in samples:
        sample_by_status[s.status.value] = sample_by_status.get(s.status.value, 0) + 1

    # 物料库存预警（当前快照）
    try:
        materials = agent.raw_material_db.get_all()
    except Exception:
        materials = []
    low_stock = [
        {
            "material_id": m.material_id,
            "name": m.name,
            "category": m.category,
            "inventory": m.inventory_quantity,
            "inventory_unit": m.inventory_unit,
            "threshold": _MATERIAL_LOW_STOCK_THRESHOLD,
            "supplier": m.supplier,
            # D4(P2-004)：告警附上下文解释与建议动作，避免只看数字无法行动
            "context": (
                f"当前库存 {(m.inventory_quantity or 0)}{m.inventory_unit or 'kg'}，"
                f"低于阈值 {_MATERIAL_LOW_STOCK_THRESHOLD}{m.inventory_unit or 'kg'}，"
                f"可能影响进行中的实验/配方投料。"
            ),
            "action": (
                f"联系供应商{m.supplier or '（未登记）'}补充采购，"
                f"或核对现有{int(_MATERIAL_LOW_STOCK_THRESHOLD) - int(m.inventory_quantity or 0)}"
                f"{m.inventory_unit or 'kg'}缺口并在物料规格库登记到货。"
            ),
        }
        for m in materials
        if (m.inventory_quantity or 0) < _MATERIAL_LOW_STOCK_THRESHOLD
    ]
    # D4(P2-004)：按 material_id 去重，避免看板出现重复预警条目
    _seen: set[str] = set()
    low_stock = [
        item for item in low_stock
        if not (item["material_id"] in _seen or _seen.add(item["material_id"]))
    ]

    # 计算任务队列长度（运行中的 ECML 任务，受时间范围筛选）
    try:
        runs = [r for r in agent.ecml.state_store.list_runs(limit=10000)
                if _in_date_range(r.get("updated_at") or r.get("created_at"), start_date, end_date)]
    except Exception:
        runs = []
    queue_length = sum(
        1 for r in runs
        if not r.get("is_complete") and r.get("status") != "timeout"
    )

    return {
        "equipment": {
            "total": equip_total,
            "in_use": equip_in_use,
            "usage_rate": round(equip_in_use / equip_total, 3) if equip_total else 0.0,
            "by_status": _count_by(equipment, lambda e: e.status.value),
        },
        "samples": {
            "total": len(samples),
            "by_status": sample_by_status,
        },
        "material_alerts": {
            "threshold": _MATERIAL_LOW_STOCK_THRESHOLD,
            "items": low_stock,
            "count": len(low_stock),
        },
        "compute_queue": {
            "length": queue_length,
        },
    }


# T-022：数据质量分布看板的标准 4 个 data_quality 桶
_DATA_QUALITY_BUCKETS = ["verified", "estimated", "simulated", "literature"]


def _normalize_data_quality(value: str | None) -> str:
    """统一 NULL/空字符串为 'estimated'，与 ExperimentResultRecord 默认值一致。"""
    if not value or value not in _DATA_QUALITY_BUCKETS:
        return "estimated"
    return value


def _rows_to_distribution(rows) -> list[dict]:
    """将 (data_quality, count) 行集合补齐为 4 个标准桶的列表。"""
    counts = {b: 0 for b in _DATA_QUALITY_BUCKETS}
    for r in rows:
        dq = _normalize_data_quality(r[0])
        counts[dq] += int(r[1])
    return [{"data_quality": b, "count": counts[b]} for b in _DATA_QUALITY_BUCKETS]


@app.get("/dashboard/data-quality")
async def dashboard_data_quality(
    project_id: str | None = Query(None, description="按项目筛选"),
):
    """数据质量分布看板：按 data_quality 分组统计实验结果记录。

    返回 distribution（全局）/ total / by_project（按项目细分）。
    data_quality 取值：verified / estimated / simulated / literature；
    NULL 或空字符串统一按 estimated 处理。
    """
    engine = agent.experiment_controller._store.engine

    # --- 全局分布（可选按 project_id 过滤）---
    if project_id:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT COALESCE(NULLIF(r.data_quality, ''), 'estimated') AS dq, COUNT(*) AS cnt
                FROM experiment.experiment_result_records r
                JOIN experiment.experiment_orders o ON o.order_id = r.experiment_order_id
                WHERE o.project_id = :project_id
                GROUP BY COALESCE(NULLIF(r.data_quality, ''), 'estimated')
            """), {"project_id": project_id}).fetchall()
    else:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT COALESCE(NULLIF(data_quality, ''), 'estimated') AS dq, COUNT(*) AS cnt
                FROM experiment.experiment_result_records
                GROUP BY COALESCE(NULLIF(data_quality, ''), 'estimated')
            """)).fetchall()

    distribution = _rows_to_distribution(rows)
    total = sum(d["count"] for d in distribution)

    # --- 按项目分布：仅统计关联到具体项目的记录 ---
    if project_id:
        sql_proj = text("""
            SELECT o.project_id,
                   COALESCE(NULLIF(r.data_quality, ''), 'estimated') AS dq,
                   COUNT(*) AS cnt
            FROM experiment.experiment_result_records r
            JOIN experiment.experiment_orders o ON o.order_id = r.experiment_order_id
            WHERE o.project_id IS NOT NULL AND o.project_id <> ''
              AND o.project_id = :project_id
            GROUP BY o.project_id, COALESCE(NULLIF(r.data_quality, ''), 'estimated')
        """)
        with engine.connect() as conn:
            proj_rows = conn.execute(sql_proj, {"project_id": project_id}).fetchall()
    else:
        sql_proj = text("""
            SELECT o.project_id,
                   COALESCE(NULLIF(r.data_quality, ''), 'estimated') AS dq,
                   COUNT(*) AS cnt
            FROM experiment.experiment_result_records r
            JOIN experiment.experiment_orders o ON o.order_id = r.experiment_order_id
            WHERE o.project_id IS NOT NULL AND o.project_id <> ''
            GROUP BY o.project_id, COALESCE(NULLIF(r.data_quality, ''), 'estimated')
        """)
        with engine.connect() as conn:
            proj_rows = conn.execute(sql_proj).fetchall()

    # 按 project_id 聚合
    proj_counts: dict[str, dict[str, int]] = {}
    for r in proj_rows:
        pid = r[0]
        dq = _normalize_data_quality(r[1])
        proj_counts.setdefault(pid, {b: 0 for b in _DATA_QUALITY_BUCKETS})[dq] += int(r[2])

    # 项目名称映射
    project_names = {p.project_id: p.name for p in _project_store.list_all()}

    by_project = [
        {
            "project_id": pid,
            "project_name": project_names.get(pid, ""),
            "distribution": [
                {"data_quality": b, "count": counts[b]} for b in _DATA_QUALITY_BUCKETS
            ],
        }
        for pid, counts in proj_counts.items()
    ]

    return {
        "distribution": distribution,
        "total": total,
        "by_project": by_project,
    }


def _count_by(items, key_fn) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = key_fn(it)
        out[k] = out.get(k, 0) + 1
    return out


# T-056：系统监控看板 —— P0/P1 复发率 / 操作成功率 / AI 采纳率
@app.get("/dashboard/monitoring")
async def dashboard_monitoring(
    days: int = Query(30, ge=1, le=365, description="统计窗口天数（默认 30 天）"),
):
    """系统监控看板：三大健康度指标。

    - p0_p1_recurrence：基于 integrations.external_invocations 统计失败调用的复发情况
    - operation_success_rate：基于 audit.audit_log 统计用户操作成功率
    - ai_adoption_rate：基于 candidate/formula/prediction 的采纳记录统计 AI 输出采纳率

    各统计独立 try/except，失败时返回空对象而非 500。
    """
    from datetime import datetime, timezone, timedelta
    from .db import get_engine as _get_engine

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cutoff_7d = now - timedelta(days=7)

    result: dict = {
        "days": days,
        "p0_p1_recurrence": {},
        "operation_success_rate": {},
        "ai_adoption_rate": {},
    }

    # --- 1. P0/P1 复发率：integrations.external_invocations 中 status='failed' 的调用 ---
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            # 近 N 天失败调用按 error_message 分组
            rows = conn.execute(text("""
                SELECT COALESCE(NULLIF(error_message, ''), '(unknown)') AS err,
                       COUNT(*) AS cnt
                FROM integrations.external_invocations
                WHERE status = 'failed'
                  AND created_at >= :cutoff
                GROUP BY COALESCE(NULLIF(error_message, ''), '(unknown)')
                ORDER BY cnt DESC
                LIMIT 20
            """), {"cutoff": cutoff}).fetchall()
            error_types = [{"error_message": r[0], "count": int(r[1])} for r in rows]
            total_errors = sum(e["count"] for e in error_types)
            recurring = sum(e["count"] for e in error_types if e["count"] > 1)
            recurrence_rate = round(recurring / total_errors, 3) if total_errors else 0.0

            # 近 7 天错误数（用于趋势对比）
            row_7d = conn.execute(text("""
                SELECT COUNT(*) FROM integrations.external_invocations
                WHERE status = 'failed' AND created_at >= :cutoff
            """), {"cutoff": cutoff_7d}).fetchone()
            errors_7d = int(row_7d[0]) if row_7d else 0

            result["p0_p1_recurrence"] = {
                "errors_7d": errors_7d,
                "errors_30d": total_errors,
                "recurrence_rate": recurrence_rate,
                "error_types": error_types,
            }
    except Exception as e:
        logger.warning("dashboard_monitoring p0_p1_recurrence 失败: %s", e)

    # --- 2. 操作成功率：audit.audit_log ---
    # 成功 = detail->>'status'='success' 或 decision 类且 confirmed=true
    # 失败 = detail->>'status'='failed' 或 decision 类且 confirmed=false
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT event_type,
                       COALESCE(action, '') AS action,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (
                           WHERE detail->>'status' = 'success'
                              OR (detail->>'status' IS NULL AND event_type = 'decision' AND confirmed = TRUE)
                       ) AS success,
                       COUNT(*) FILTER (
                           WHERE detail->>'status' = 'failed'
                              OR (detail->>'status' IS NULL AND event_type = 'decision' AND confirmed = FALSE)
                       ) AS failed
                FROM audit.audit_log
                WHERE event_type IN ('ai_suggestion', 'human_edit', 'decision', 'agent_action', 'tool_call')
                  AND created_at >= :cutoff
                GROUP BY event_type, action
                ORDER BY total DESC
            """), {"cutoff": cutoff}).fetchall()
            by_type = []
            total_ops = 0
            total_success = 0
            total_failed = 0
            for r in rows:
                event_type, action, total, success, failed = r[0], r[1], int(r[2]), int(r[3]), int(r[4])
                by_type.append({
                    "event_type": event_type,
                    "action": action,
                    "total": total,
                    "success": success,
                    "failed": failed,
                    "success_rate": round(success / total, 3) if total else 0.0,
                })
                total_ops += total
                total_success += success
                total_failed += failed
            overall_rate = round(total_success / total_ops, 3) if total_ops else 0.0
            result["operation_success_rate"] = {
                "total": total_ops,
                "success": total_success,
                "failed": total_failed,
                "success_rate": overall_rate,
                "by_type": by_type,
            }
    except Exception as e:
        logger.warning("dashboard_monitoring operation_success_rate 失败: %s", e)

    # --- 3. AI 采纳率：candidate + formula + prediction 三类 ---
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            # 3.1 candidate：data->>'source' 或 source 字段含 LLM/AI 视为 AI 生成；
            #     被 experiment_orders 引用视为已采纳
            cand_row = conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                           WHERE EXISTS (
                               SELECT 1 FROM experiment.experiment_orders o
                               WHERE o.candidate_id = c.candidate_id
                           )
                       ) AS adopted
                FROM experiment.candidates c
                WHERE c.created_at >= :cutoff
                  AND (
                      c.data->>'source' ILIKE '%llm%'
                      OR c.data->>'source' ILIKE '%ai%'
                      OR c.source ILIKE '%llm%'
                      OR c.source ILIKE '%ai%'
                  )
            """), {"cutoff": cutoff}).fetchone()
            cand_total = int(cand_row[0]) if cand_row else 0
            cand_adopted = int(cand_row[1]) if cand_row else 0

            # 3.2 formula：control_plane.versions 中 entity_type='formula'
            #     snapshot->ai_meta 非空视为 AI 生成；is_active=true 视为已发布采纳
            formula_row = conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE is_active = TRUE) AS adopted
                FROM control_plane.versions
                WHERE entity_type = 'formula'
                  AND created_at >= :cutoff
                  AND snapshot ? 'ai_meta'
                  AND snapshot->'ai_meta' != '{}'::jsonb
            """), {"cutoff": cutoff}).fetchone()
            formula_total = int(formula_row[0]) if formula_row else 0
            formula_adopted = int(formula_row[1]) if formula_row else 0

            # 3.3 prediction：audit.audit_log 中 module='prediction' 视为 AI 预测；
            #     confirmed=true 视为已采纳
            pred_row = conn.execute(text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE confirmed = TRUE) AS adopted
                FROM audit.audit_log
                WHERE module = 'prediction'
                  AND created_at >= :cutoff
            """), {"cutoff": cutoff}).fetchone()
            pred_total = int(pred_row[0]) if pred_row else 0
            pred_adopted = int(pred_row[1]) if pred_row else 0

            ai_total = cand_total + formula_total + pred_total
            ai_adopted = cand_adopted + formula_adopted + pred_adopted
            adoption_rate = round(ai_adopted / ai_total, 3) if ai_total else 0.0

            def _sub_rate(adopted, total):
                return round(adopted / total, 3) if total else 0.0

            result["ai_adoption_rate"] = {
                "total": ai_total,
                "adopted": ai_adopted,
                "adoption_rate": adoption_rate,
                "by_type": [
                    {"type": "candidate", "total": cand_total, "adopted": cand_adopted,
                     "adoption_rate": _sub_rate(cand_adopted, cand_total)},
                    {"type": "formula", "total": formula_total, "adopted": formula_adopted,
                     "adoption_rate": _sub_rate(formula_adopted, formula_total)},
                    {"type": "prediction", "total": pred_total, "adopted": pred_adopted,
                     "adoption_rate": _sub_rate(pred_adopted, pred_total)},
                ],
            }
    except Exception as e:
        logger.warning("dashboard_monitoring ai_adoption_rate 失败: %s", e)

    return result


# ===========================================================================
# 知识资产版本追溯 API（F5：版本 CRUD）
# ===========================================================================

class VersionCreateRequest(BaseModel):
    entity_type: str  # material / workflow / knowledge / formula
    entity_id: str = ""
    version_number: int = 0  # 0 → 自动递增
    snapshot: dict = Field(default_factory=dict)
    change_summary: str = ""
    created_by: str = ""
    is_active: bool = True


@app.post("/versions", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_version(req: VersionCreateRequest):
    """创建版本快照。"""
    try:
        vtype = VersionType(req.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 entity_type: {req.entity_type}（支持: {[t.value for t in VersionType]})",
        )
    if not req.entity_id:
        raise HTTPException(status_code=400, detail="entity_id 不能为空")

    store = get_version_store()
    version = Version(
        entity_type=vtype,
        entity_id=req.entity_id,
        version_number=req.version_number,
        snapshot=req.snapshot,
        change_summary=req.change_summary,
        created_by=req.created_by,
        is_active=req.is_active,
    )
    saved = store.save(version)
    return saved.model_dump()


@app.get("/versions/{entity_type}/{entity_id}")
async def list_versions(entity_type: str, entity_id: str):
    """获取实体的版本历史（按版本号倒序）。"""
    try:
        vtype = VersionType(entity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 entity_type: {entity_type}")
    store = get_version_store()
    versions = store.list_by_entity(vtype.value, entity_id)
    return {
        "entity_type": vtype.value,
        "entity_id": entity_id,
        "versions": [v.model_dump() for v in versions],
        "count": len(versions),
    }


@app.get("/versions/{entity_type}/{entity_id}/latest")
async def get_latest_version(entity_type: str, entity_id: str):
    """获取最新版本（优先活跃版本，否则最大版本号）。"""
    try:
        vtype = VersionType(entity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 entity_type: {entity_type}")
    store = get_version_store()
    version = store.get_latest(vtype.value, entity_id)
    if version is None:
        raise HTTPException(status_code=404, detail="该实体暂无版本记录")
    return version.model_dump()


@app.put("/versions/{version_id}/activate", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def activate_version(version_id: str):
    """设置为活跃版本（同实体其他版本自动失活）。"""
    store = get_version_store()
    version = store.set_active(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"版本 {version_id} 不存在")
    return version.model_dump()


@app.get("/versions")
async def list_all_versions(entity_type: str = ""):
    """列出所有实体的活跃版本（可选 entity_type 过滤）。"""
    store = get_version_store()
    if entity_type:
        try:
            vtype = VersionType(entity_type)
            versions = store.list_latest(vtype.value)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的 entity_type: {entity_type}")
    else:
        versions = store.list_latest()
    return {
        "versions": [v.model_dump() for v in versions],
        "count": len(versions),
    }


# ===========================================================================
# 技术情报聚合与知识图谱 API（G1）
# ===========================================================================

class LiteratureSearchRequest(BaseModel):
    query: str = ""
    limit: int = 10


class KnowledgeGraphBuildRequest(BaseModel):
    papers: list[dict] = Field(default_factory=list)


class KnowledgeGraphSaveRequest(BaseModel):
    graph: dict = Field(default_factory=dict)
    name: str = ""
    query: str = ""
    created_by: str = ""
    paper_count: int = 0


class KnowledgeGraphUpdateRequest(BaseModel):
    graph: dict = Field(default_factory=dict)
    name: str = ""
    query: str = ""
    created_by: str = ""
    paper_count: int = 0


@app.post("/knowledge/search", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def search_literature(req: LiteratureSearchRequest):
    """按关键词搜索电池材料领域文献（LLM/SCP/WebAPI/本地知识库/模板库多源检索）。"""
    papers = await _literature_researcher.search(req.query, req.limit)
    return {"papers": papers, "count": len(papers), "query": req.query}


@app.post("/knowledge/entities", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def extract_entities(req: KnowledgeGraphBuildRequest):
    """从文献列表抽取实体（材料/性能/方法/应用/机构）。"""
    entities = _literature_researcher.extract_entities(req.papers)
    return entities


@app.post("/knowledge/graph", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def build_knowledge_graph(req: KnowledgeGraphBuildRequest):
    """从文献列表构建知识图谱（节点 + 边）。"""
    graph = _literature_researcher.build_knowledge_graph(req.papers)
    return graph


@app.post("/knowledge/graphs", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def save_knowledge_graph(req: KnowledgeGraphSaveRequest):
    """保存知识图谱快照到 SQLite。"""
    store = get_knowledge_graph_store()
    saved = await asyncio.to_thread(
        store.save_graph,
        req.graph,
        req.name,
        req.query,
        req.created_by,
        req.paper_count,
    )
    return saved


@app.put("/knowledge/graphs/{graph_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def update_knowledge_graph(graph_id: str, req: KnowledgeGraphUpdateRequest):
    """增量更新已有知识图谱（合并节点/边而非覆盖）。"""
    store = get_knowledge_graph_store()
    updated = await asyncio.to_thread(
        store.update_graph,
        graph_id,
        req.graph,
        req.name,
        req.query,
        req.created_by,
        req.paper_count,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"知识图谱 {graph_id} 不存在")
    return updated


@app.get("/knowledge/graphs")
async def list_knowledge_graphs(skip: int = 0, limit: int = 50):
    """列出已保存的知识图谱（按创建时间倒序，支持分页）。"""
    store = get_knowledge_graph_store()
    graphs = await asyncio.to_thread(store.list_graphs, skip + limit)
    paged = graphs[skip:skip + limit]
    return {"graphs": paged, "count": len(paged)}


@app.get("/knowledge/graphs/{graph_id}")
async def get_knowledge_graph(graph_id: str):
    """获取单个知识图谱详情（含完整节点与边）。"""
    store = get_knowledge_graph_store()
    graph = await asyncio.to_thread(store.get_graph, graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"知识图谱 {graph_id} 不存在")
    return graph


@app.delete("/knowledge/graphs/{graph_id}", dependencies=[Depends(require_role(UserRole.PROJECT_MANAGER))])
async def delete_knowledge_graph(graph_id: str):
    """删除指定知识图谱。"""
    store = get_knowledge_graph_store()
    deleted = await asyncio.to_thread(store.delete_graph, graph_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"知识图谱 {graph_id} 不存在")
    return {"deleted": True, "graph_id": graph_id}


# ===========================================================================
# 材料知识资产库 API（papers / materials / claims）
# ===========================================================================


class PaperSearchRequest(BaseModel):
    query: str = ""
    source: str = ""
    source_tier: str = ""
    limit: int = 50
    offset: int = 0


class PaperUpsertRequest(BaseModel):
    doi: str = ""
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    year: int | None = None
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    source: str = "internal"
    source_tier: str = "internal"
    url: str = ""
    citation_count: int = 0
    extra: dict = Field(default_factory=dict)


class MaterialUpsertRequest(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: str = ""
    description: str = ""
    properties: dict = Field(default_factory=dict)
    source_tier: str = "journal"
    evidence_level: str = "literature"


class ClaimUpsertRequest(BaseModel):
    material_name: str
    claim_text: str
    claim_type: str = "general"
    subject: str = ""
    predicate: str = ""
    value: str = ""
    unit: str = ""
    numeric_value: float | None = None
    source_paper_id: str = ""
    source_tier: str = "journal"
    evidence_level: str = "literature"


class IngestPapersRequest(BaseModel):
    papers: list[dict] = Field(default_factory=list)
    default_source: str = "unknown"
    query: str = ""


# ── 文献资产 ──────────────────────────────────────────────────────────────

@app.get("/knowledge/papers")
async def list_papers(
    query: str = "",
    source: str = "",
    source_tier: str = "",
    limit: int = 50,
    offset: int = 0,
    semantic: bool = False,
):
    """检索文献资产（支持关键词/来源/可信度筛选；semantic=true 走 pgvector 语义检索）。

    语义检索依赖 pgvector 扩展 + embedding vector 列 + InternLM embeddings 接口，
    任一不可用时退化为空检索（不静默回退关键词）。
    """
    store = get_paper_store()
    if semantic:
        from .knowledge.vector_search import semantic_paper_search
        papers = await asyncio.to_thread(
            semantic_paper_search, query, source, source_tier, limit,
        )
        return {"papers": papers, "count": len(papers), "total": len(papers), "semantic": True}
    papers = await asyncio.to_thread(
        store.search, query, source, source_tier, limit, offset
    )
    total = await asyncio.to_thread(store.count, query, source, source_tier)
    return {"papers": papers, "count": len(papers), "total": total}


@app.get("/knowledge/papers/{paper_id}")
async def get_paper(paper_id: str):
    """获取单篇文献详情。"""
    store = get_paper_store()
    paper = await asyncio.to_thread(store.get, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
    return paper


@app.post("/knowledge/papers", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_paper(req: PaperUpsertRequest):
    """手动录入文献（用于内部资料/专利等）。"""
    store = get_paper_store()
    saved = await asyncio.to_thread(store.upsert, req.model_dump())
    return saved


@app.delete("/knowledge/papers/{paper_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_paper(paper_id: str):
    """删除文献。"""
    store = get_paper_store()
    deleted = await asyncio.to_thread(store.delete, paper_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"文献 {paper_id} 不存在")
    return {"deleted": True, "paper_id": paper_id}


# ── 材料卡片 ──────────────────────────────────────────────────────────────

@app.get("/knowledge/materials")
async def list_materials(
    query: str = "",
    category: str = "",
    limit: int = 50,
    offset: int = 0,
):
    """列出材料卡片（支持关键词/类别筛选）。"""
    store = get_material_store()
    materials = await asyncio.to_thread(store.list, query, category, limit, offset)
    return {"materials": materials, "count": len(materials)}


@app.get("/knowledge/materials/{material_id}")
async def get_material(material_id: str):
    """获取材料卡片详情（含关联文献与主张）。"""
    store = get_material_store()
    material = await asyncio.to_thread(store.get, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail=f"材料 {material_id} 不存在")

    # 附带关联文献和主张
    papers = await asyncio.to_thread(store.list_papers, material_id, 50)
    claim_store = get_claim_store()
    claims = await asyncio.to_thread(claim_store.list_by_material, material_id, "", 100)
    material["papers"] = papers
    material["claims"] = claims
    return material


@app.post("/knowledge/materials", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_material(req: MaterialUpsertRequest):
    """创建/更新材料卡片。"""
    store = get_material_store()
    saved = await asyncio.to_thread(store.upsert, req.model_dump())
    return saved


@app.delete("/knowledge/materials/{material_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_material(material_id: str):
    """删除材料卡片（级联删除关联的主张和文献关联）。"""
    store = get_material_store()
    deleted = await asyncio.to_thread(store.delete, material_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"材料 {material_id} 不存在")
    return {"deleted": True, "material_id": material_id}


# ── 主张/数据点 ────────────────────────────────────────────────────────────

@app.get("/knowledge/claims")
async def list_claims(
    material_id: str = "",
    claim_type: str = "",
    limit: int = 100,
):
    """列出主张（按材料或类型筛选）。"""
    store = get_claim_store()
    if not material_id:
        raise HTTPException(status_code=400, detail="必须提供 material_id 参数")
    claims = await asyncio.to_thread(store.list_by_material, material_id, claim_type, limit)
    return {"claims": claims, "count": len(claims)}


@app.post("/knowledge/claims", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_claim(req: ClaimUpsertRequest):
    """手动添加一条主张（供内部资料录入/用户标注使用）。"""
    pipeline = get_ingestion_pipeline()
    saved = await asyncio.to_thread(
        pipeline.add_claim,
        req.material_name,
        req.claim_text,
        req.claim_type,
        req.subject,
        req.predicate,
        req.value,
        req.unit,
        req.numeric_value,
        req.source_paper_id,
        req.source_tier,
        req.evidence_level,
    )
    return saved


@app.delete("/knowledge/claims/{claim_id}", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def delete_claim(claim_id: str):
    """删除主张。"""
    store = get_claim_store()
    deleted = await asyncio.to_thread(store.delete, claim_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"主张 {claim_id} 不存在")
    return {"deleted": True, "claim_id": claim_id}


# ── 知识采集管道 ───────────────────────────────────────────────────────────

@app.post("/knowledge/ingest", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def ingest_papers(req: IngestPapersRequest):
    """将检索结果批量入库为知识资产（自动建立材料卡片和关联）。"""
    pipeline = get_ingestion_pipeline()
    stats = await asyncio.to_thread(
        pipeline.ingest_papers_for_query,
        req.query,
        req.papers,
        req.default_source,
    )
    return stats


@app.post("/knowledge/search_and_ingest", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def search_and_ingest(req: LiteratureSearchRequest):
    """一体化：检索 + 入库。返回检索结果和入库统计。"""
    papers = await _literature_researcher.search(req.query, req.limit)
    pipeline = get_ingestion_pipeline()
    stats = await asyncio.to_thread(
        pipeline.ingest_papers_for_query,
        req.query,
        papers,
        "search",
    )
    return {
        "papers": papers,
        "count": len(papers),
        "query": req.query,
        "ingestion": stats,
    }


class ExtractClaimsRequest(BaseModel):
    """从指定材料的关联文献中自动抽取主张。"""
    material_id: str
    paper_limit: int = 10


@app.post("/knowledge/extract_claims", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def extract_claims(req: ExtractClaimsRequest):
    """LLM 驱动的主张抽取：从材料关联文献的摘要中自动提取结构化主张。"""
    material_store = get_material_store()
    material = await asyncio.to_thread(material_store.get, req.material_id)
    if material is None:
        raise HTTPException(status_code=404, detail=f"材料 {req.material_id} 不存在")

    papers = await asyncio.to_thread(
        material_store.list_papers, req.material_id, req.paper_limit
    )
    if not papers:
        raise HTTPException(status_code=400, detail="该材料暂无关联文献，无法抽取主张")

    pipeline = get_ingestion_pipeline()
    result = await pipeline.extract_claims_batch(
        papers, material["canonical_name"]
    )
    return result


# ===========================================================================
# 集成管理 API（InternLM / SCP 健康检查、目录、审计）
# ===========================================================================

class SCPCatalogUpdateRequest(BaseModel):
    enabled: bool | None = None
    server_id: str | None = None
    remote_tool_name: str | None = None
    allowed_roles: list[str] | None = None
    ecml_steps: list[int] | None = None
    timeout_seconds: int | None = None


class SCPTestRequest(BaseModel):
    internal_name: str = ""
    arguments: dict = Field(default_factory=dict)


@app.get("/integrations/health")
async def get_integrations_health():
    """返回 InternLM 和 SCP 健康状态。"""
    cfg = agent.config
    internlm_healthy = cfg.internlm.enabled and cfg.internlm.api_key is not None
    scp_healthy = cfg.scp.enabled and cfg.scp.api_key is not None
    return {
        "internlm": {
            "enabled": cfg.internlm.enabled,
            "healthy": internlm_healthy,
            "base_url": cfg.internlm.base_url,
            "model": cfg.internlm.model,
        },
        "scp": {
            "enabled": cfg.scp.enabled,
            "healthy": scp_healthy,
            "base_url": cfg.scp.base_url,
            "allowed_servers": cfg.scp.allowed_servers,
            "allowed_tools": cfg.scp.allowed_tools,
        },
    }


@app.get("/integrations/scp/catalog", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_scp_catalog():
    """返回所有 SCP 工具绑定。"""
    if _scp_catalog is None:
        raise HTTPException(status_code=503, detail="SCP 目录未初始化，请启用 SCP_ENABLED=true")
    bindings = _scp_catalog.list_all()
    return {
        "bindings": [b.model_dump() for b in bindings],
        "count": len(bindings),
    }


@app.put("/integrations/scp/catalog/{internal_name}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def update_scp_catalog(internal_name: str, req: SCPCatalogUpdateRequest):
    """启用/禁用/配置一个 SCP 工具绑定。"""
    global _scp_client_pool
    if _scp_catalog is None:
        raise HTTPException(status_code=503, detail="SCP 目录未初始化")

    binding = _scp_catalog.get(internal_name)
    if binding is None:
        raise HTTPException(status_code=404, detail=f"工具绑定 '{internal_name}' 不存在")

    if req.enabled is not None:
        if req.enabled:
            server_id = req.server_id or binding.server_id
            remote_tool_name = req.remote_tool_name or binding.remote_tool_name
            if not server_id or not remote_tool_name:
                raise HTTPException(status_code=400, detail="启用工具需要 server_id 和 remote_tool_name")
            _scp_catalog.enable(internal_name, server_id, remote_tool_name)
        else:
            _scp_catalog.disable(internal_name)
        # 持久化绑定启用状态到 .env
        agent.config.scp.binding_enabled[internal_name] = req.enabled
        try:
            save_config_to_env(agent.config)
        except Exception as exc:
            # 持久化失败不应阻断内存更新
            logger.warning("save_config_to_env failed for SCP binding %s: %s", internal_name, exc)

    update_kwargs = {}
    if req.allowed_roles is not None:
        update_kwargs["allowed_roles"] = req.allowed_roles
    if req.ecml_steps is not None:
        update_kwargs["ecml_steps"] = req.ecml_steps
    if req.timeout_seconds is not None:
        update_kwargs["timeout_seconds"] = req.timeout_seconds
    if update_kwargs:
        _scp_catalog.update(internal_name, **update_kwargs)

    # Re-register SCP tools if client pool is available
    if _scp_client_pool is not None and _scp_audit_store is not None:
        agent.tools.register_scp_tools(
            _scp_catalog, _scp_client_pool, _scp_policy,
            _scp_adapters, _scp_audit_store,
        )

    return _scp_catalog.get(internal_name).model_dump()


@app.post("/integrations/scp/test", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def test_scp_tool(req: SCPTestRequest):
    """测试一个白名单 SCP 工具。"""
    if _scp_client_pool is None or _scp_catalog is None or _scp_policy is None:
        raise HTTPException(status_code=503, detail="SCP 基础设施未初始化")

    binding = _scp_catalog.get(req.internal_name)
    if binding is None:
        raise HTTPException(status_code=404, detail=f"工具绑定 '{req.internal_name}' 不存在")
    if not binding.enabled:
        raise HTTPException(status_code=400, detail=f"工具 '{req.internal_name}' 未启用")

    try:
        _scp_policy.authorize(req.internal_name, "admin")
    except PolicyDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    result = await _scp_client_pool.call_tool(
        binding.server_id, binding.remote_tool_name, req.arguments,
        server_url=binding.server_url or None,
    )
    # Surface SCP call failures as HTTP errors so the frontend interceptor
    # can display the error message to the user.
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502,
            detail=f"SCP 调用失败: {result.get('error', '未知错误')}",
        )
    return result


@app.get("/integrations/invocations", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_invocations(
    project_id: str | None = None,
    run_id: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """查询审计记录（含过滤条件）。"""
    if _scp_audit_store is None:
        raise HTTPException(status_code=503, detail="审计存储未初始化，请启用 SCP_ENABLED=true")
    records = _scp_audit_store.query(
        project_id=project_id,
        run_id=run_id,
        provider=provider,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"invocations": records, "count": len(records)}


@app.get("/integrations/invocations/{invocation_id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def get_invocation_detail(invocation_id: str):
    """获取审计记录详情。"""
    if _scp_audit_store is None:
        raise HTTPException(status_code=503, detail="审计存储未初始化")
    record = _scp_audit_store.get_by_id(invocation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"审计记录 '{invocation_id}' 不存在")
    return record


# ===========================================================================
# Committee API（委员会审核系统）
# ===========================================================================

class CommitteeCaseCreateRequest(BaseModel):
    committee_type: str = ""  # crystal_construction / experimental_readiness / candidate_priority / deviation_review / external_evidence
    project_id: str = ""
    ecml_run_id: str = ""
    candidate_id: str = ""
    trigger_code: str = ""
    risk_level: str = "medium"
    created_by: str = ""


class CommitteeCaseReviewRequest(BaseModel):
    reviewer: str = ""
    decision: str = ""  # approve / reject / request_evidence
    comment: str = ""


class CommitteePolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    default_mode: str | None = None
    max_evidence_rounds: int | None = None
    max_parallel_evidence_tasks: int | None = None
    case_timeout_seconds: int | None = None
    crystal_enabled: bool | None = None
    experiment_enabled: bool | None = None
    candidate_priority_enabled: bool | None = None
    deviation_review_enabled: bool | None = None
    external_evidence_enabled: bool | None = None
    require_human_for_high_risk: bool | None = None
    crystal_min_score_for_dft: float | None = None
    experiment_min_score_for_submit: float | None = None
    prediction_disagreement_ratio: float | None = None
    top_k_score_proximity_ratio: float | None = None
    experiment_relative_deviation_trigger: float | None = None
    external_conflict_requires_review: bool | None = None
    dft_cost_trigger: float | None = None


def _require_committee():
    """守卫：Committee 模块未初始化时抛出 503。"""
    if _committee_coordinator is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Committee 模块未初始化。请在项目根目录的 .env 中设置 "
                "COMMITTEE_ENABLED=true，并重启后端服务（须从项目根目录启动，"
                "否则 .env 可能无法被加载）。"
            ),
        )


def _user_role_from_request(request: Request) -> str:
    """从请求中提取用户角色，匿名用户默认 viewer（最小权限原则）。"""
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return user.role.value
    return "viewer"


def _check_committee_access(request: Request, case, action: str) -> None:
    """Committee 权限检查。

    case 参数可传入 CommitteeCase 或 dict（含 project_id）。
    先做角色级检查，再做对象级（项目成员）权限校验（fail-closed）。
    """
    role = _user_role_from_request(request)
    if role == "admin":
        return
    if role == "viewer" and action not in ("view",):
        raise HTTPException(status_code=403, detail="viewer 角色仅可查看已完成的评估结果")
    if role == "researcher" and action in ("admin_manage",):
        raise HTTPException(status_code=403, detail="researcher 角色无权管理全局策略")
    # Project-scoped access check: 当 case 携带 project_id 时，校验调用者是否
    # 有权访问该项目（fail-closed，与 memory card 检索端点同一套 check_project_access）。
    if case is not None:
        project_id = (
            case.get("project_id") if isinstance(case, dict)
            else getattr(case, "project_id", None)
        )
        if project_id:
            user = getattr(request.state, "current_user", None)
            user_id = getattr(user, "user_id", "") if user else ""
            store = getattr(request.app.state, "user_store", None)
            if not user_id or store is None or not check_project_access(user_id, project_id, store):
                raise HTTPException(status_code=403, detail="无权访问该项目")


# ── T-031 高风险 AI 操作人工确认门禁 ──────────────────────────────────────────

def _gate_high_risk_ai_action(action_type: str, action_payload: dict, initiator: str) -> str | None:
    """T-031：高风险 AI 操作触发人工确认三段式。

    调用 committee 触发器创建 high_risk_ai_action 案件（立即进入 HUMAN_REVIEW）。
    返回 case_id 供端点阻塞返回 202；Committee 未启用、去重命中或创建失败时返回 None。
    """
    if _committee_coordinator is None:
        return None
    from .committee.triggers import trigger_high_risk_ai_action
    return trigger_high_risk_ai_action(_committee_coordinator, action_type, action_payload, initiator)


def _require_high_risk_review_or_raise(action_type: str, action_payload: dict, initiator: str):
    """高风险 AI 操作门禁：触发 committee 审核。

    - Committee 未初始化 → 503（fail-closed：无审核基础设施则不允许 AI 执行）
    - 去重命中（已有未结案案件） → 409
    - 触发成功 → 返回 JSONResponse(202) 含 case_id，调用方应直接 return 该响应
    """
    if _committee_coordinator is None:
        raise HTTPException(
            status_code=503,
            detail="高风险 AI 操作需要 Committee 人工确认，但 Committee 模块未初始化（请设置 COMMITTEE_ENABLED=true）",
        )
    case_id = _gate_high_risk_ai_action(action_type, action_payload, initiator)
    if case_id is None:
        raise HTTPException(
            status_code=409,
            detail="该高风险操作已有未结案的人工确认案件，请等待审核结果后再重试",
        )
    return JSONResponse(
        status_code=202,
        content={
            "status": "pending_review",
            "case_id": case_id,
            "action_type": action_type,
            "message": "高风险 AI 操作已进入人工确认流程，等待审核",
        },
    )


# ── POST /committees/cases ──

@app.post("/committees/cases")
async def create_committee_case(req: CommitteeCaseCreateRequest, request: Request):
    """创建或预览一个 committee case。"""
    _require_committee()
    _check_committee_access(request, None, "create")
    from .committee.enums import CommitteeType, RiskLevel, CaseStatus
    from .committee.models import CommitteeCase
    import uuid as _uuid

    try:
        committee_type = CommitteeType(req.committee_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 committee_type: {req.committee_type}")

    try:
        risk_level = RiskLevel(req.risk_level)
    except ValueError:
        risk_level = RiskLevel.MEDIUM

    case = CommitteeCase(
        case_id=f"cmt-{_uuid.uuid4().hex[:8]}",
        committee_type=committee_type,
        project_id=req.project_id or None,
        ecml_run_id=req.ecml_run_id or None,
        candidate_id=req.candidate_id or None,
        trigger_code=req.trigger_code,
        risk_level=risk_level,
        status=CaseStatus.PENDING,
        created_by=req.created_by or _user_role_from_request(request),
    )
    try:
        _committee_policy.assert_authorized(case, user_role=_user_role_from_request(request))
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))

    _committee_repository.create_case(case)
    _committee_event_store.append(case.case_id, "case_created", {"case_id": case.case_id})
    logger.info(
        "Committee case created by user=%s (case_id=%s, type=%s)",
        _user_role_from_request(request), case.case_id, req.committee_type,
    )
    return case.model_dump()


# ── GET /committees/cases ──

@app.get("/committees/cases")
async def list_committee_cases(
    project_id: str | None = None,
    committee_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """列出 cases，可按 project_id / committee_type / status 过滤。"""
    _require_committee()
    from .committee.enums import CommitteeType, CaseStatus

    ct = None
    if committee_type:
        try:
            ct = CommitteeType(committee_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的 committee_type: {committee_type}")

    cs = None
    if status:
        try:
            cs = CaseStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的 status: {status}")

    cases = _committee_repository.list_cases(
        committee_type=ct, status=cs, project_id=project_id, limit=limit, offset=offset,
    )
    return {"cases": [c.model_dump() for c in cases], "count": len(cases)}


# ── GET /committees/cases/{case_id} ──

@app.get("/committees/cases/{case_id}")
async def get_committee_case(case_id: str, request: Request):
    """获取 case 详情（含 proposal、evidence summary、verdict）。"""
    _require_committee()
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    _check_committee_access(request, case, "view")

    evidence = _committee_repository.get_evidence_by_case(case_id)
    verdicts = _committee_repository.get_verdict_by_case(case_id)
    proposal = _committee_repository.get_proposal_by_case(case_id)
    events = _committee_event_store.get_events(case_id)

    return {
        "case": case.model_dump(),
        "evidence": [e.model_dump() for e in evidence],
        "verdict": verdicts.model_dump() if verdicts else None,
        "proposal": proposal.model_dump() if proposal else None,
        "events": events,
    }


# ── POST /committees/cases/{case_id}/run ──

@app.post("/committees/cases/{case_id}/run")
async def run_committee_case(case_id: str, request: Request):
    """异步执行 committee case。"""
    _require_committee()
    _check_committee_access(request, None, "execute")
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")

    if case.status.value not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Case {case_id} 当前状态为 {case.status.value}，无法执行")

    user_role = _user_role_from_request(request)
    from .committee.enums import CaseStatus as _RunCaseStatus

    async def _run():
        try:
            await _committee_coordinator.assess(case, user_role=user_role)
        except Exception as e:
            logger.error("Committee assessment failed: %s", e, exc_info=True)
            try:
                await asyncio.to_thread(_committee_repository.update_case_status, case_id, _RunCaseStatus.FAILED)
                await asyncio.to_thread(_committee_event_store.append, case_id, "case_failed", {"reason": str(e)})
            except Exception as update_err:
                logger.error("Failed to mark case %s as FAILED: %s", case_id, update_err)

    _spawn_background(_run())
    logger.info(
        "Committee case run triggered by user=%s (case_id=%s)",
        user_role, case_id,
    )
    return {"status": "running", "case_id": case_id}


# ── POST /committees/cases/{case_id}/review ──

@app.post("/committees/cases/{case_id}/review")
async def review_committee_case(case_id: str, req: CommitteeCaseReviewRequest, request: Request):
    """人工审核：approve / reject / request_evidence。"""
    _require_committee()
    _check_committee_access(request, None, "review")
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")

    # 仅允许对处于 HUMAN_REVIEW 状态的 case 进行人工审核，避免跳过评估流程。
    from .committee.enums import CaseStatus
    if case.status != CaseStatus.HUMAN_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Case 当前状态为 {case.status.value}，仅 human_review 状态可执行人工审核",
        )

    valid_decisions = {"approve", "reject", "request_evidence"}
    if req.decision not in valid_decisions:
        raise HTTPException(status_code=400, detail=f"decision 必须为 {valid_decisions}")

    from .committee.enums import CaseStatus
    decision_map = {
        "approve": CaseStatus.PASS,
        "reject": CaseStatus.REJECT,
        "request_evidence": CaseStatus.REQUEST_EVIDENCE,
    }
    new_status = decision_map[req.decision]
    _committee_repository.update_case_status(case_id, new_status)
    _committee_event_store.append(case_id, "human_review_requested", {
        "reviewer": req.reviewer,
        "decision": req.decision,
        "comment": req.comment,
    })
    logger.info(
        "Committee case reviewed by user=%s (case_id=%s, decision=%s)",
        req.reviewer or _user_role_from_request(request), case_id, req.decision,
    )
    return {"status": new_status.value, "case_id": case_id}


# ── POST /committees/cases/{case_id}/cancel ──

@app.post("/committees/cases/{case_id}/cancel")
async def cancel_committee_case(case_id: str, request: Request):
    """取消 pending 状态的 case。"""
    _require_committee()
    _check_committee_access(request, None, "cancel")
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")

    from .committee.enums import CaseStatus
    cancellable = {CaseStatus.PENDING, CaseStatus.THINKING}
    if case.status not in cancellable:
        raise HTTPException(status_code=400, detail=f"Case {case_id} 当前状态为 {case.status.value}，无法取消")

    _committee_repository.update_case_status(case_id, CaseStatus.CANCELLED)
    _committee_event_store.append(case_id, "case_closed", {"reason": "cancelled"})
    logger.info(
        "Committee case cancelled by user=%s (case_id=%s)",
        _user_role_from_request(request), case_id,
    )
    return {"status": "cancelled", "case_id": case_id}


# ── GET /committees/cases/{case_id}/events ──

@app.get("/committees/cases/{case_id}/events")
async def get_committee_events(case_id: str, request: Request):
    """获取 case 的事件流。"""
    _require_committee()
    # 加载 case 用于项目级权限校验（若不存在则用 None，仍执行角色级校验）。
    case = _committee_repository.get_case(case_id)
    _check_committee_access(request, case, "view")
    events = _committee_event_store.get_events(case_id)
    return {"events": events, "case_id": case_id, "count": len(events)}


# ── GET /committees/metrics ──

@app.get("/committees/metrics")
async def get_committee_metrics():
    """延迟、通过率、拒绝率、人工升级率。"""
    _require_committee()
    cases = _committee_repository.list_cases(limit=1000)
    if not cases:
        return {"latency_avg_ms": 0, "pass_rate": 0, "reject_rate": 0, "human_escalation_rate": 0, "total_cases": 0}

    total = len(cases)
    passed = sum(1 for c in cases if c.status.value == "pass")
    rejected = sum(1 for c in cases if c.status.value == "reject")
    escalated = sum(1 for c in cases if c.status.value == "human_review")

    # Calculate average latency
    latencies = []
    for c in cases:
        # Skip cases with missing timestamps to avoid TypeError on subtraction.
        if c.updated_at is None or c.created_at is None:
            continue
        delta = (c.updated_at - c.created_at).total_seconds() * 1000
        if delta > 0:
            latencies.append(delta)

    return {
        "latency_avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "pass_rate": round(passed / total, 4) if total else 0,
        "reject_rate": round(rejected / total, 4) if total else 0,
        "human_escalation_rate": round(escalated / total, 4) if total else 0,
        "total_cases": total,
    }


# ── GET /committees/cases/{case_id}/priority-queue ──

@app.get("/committees/cases/{case_id}/priority-queue")
async def get_priority_queue(case_id: str, request: Request):
    """获取 priority committee 的 DFT 队列。"""
    _require_committee()
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    _check_committee_access(request, case, "view")

    from .committee.enums import CommitteeType
    if case.committee_type != CommitteeType.CANDIDATE_PRIORITY:
        raise HTTPException(status_code=400, detail="此端点仅适用于 candidate_priority 类型的 case")

    evidence = _committee_repository.get_evidence_by_case(case_id)
    return {
        "case_id": case_id,
        "dft_queue": [],
        "retention_pool": [],
        "pareto_relations": [],
        "resource_constraints": {},
        "note": "Priority queue requires assess_candidate_priority() execution",
    }


# ── GET /committees/cases/{case_id}/feedback-actions ──

@app.get("/committees/cases/{case_id}/feedback-actions")
async def get_feedback_actions(case_id: str, request: Request):
    """获取 deviation review 的反馈动作。"""
    _require_committee()
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    _check_committee_access(request, case, "view")

    from .committee.enums import CommitteeType
    if case.committee_type != CommitteeType.DEVIATION_REVIEW:
        raise HTTPException(status_code=400, detail="此端点仅适用于 deviation_review 类型的 case")

    return {
        "case_id": case_id,
        "feedback_actions": [],
        "decomposition": {},
        "note": "Feedback actions require assess_deviation_review() execution",
    }


# ── GET /committees/cases/{case_id}/evidence-adoption ──

@app.get("/committees/cases/{case_id}/evidence-adoption")
async def get_evidence_adoption(case_id: str, request: Request):
    """获取 external evidence adoption 状态。"""
    _require_committee()
    case = _committee_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} 不存在")
    _check_committee_access(request, case, "view")

    from .committee.enums import CommitteeType
    if case.committee_type != CommitteeType.EXTERNAL_EVIDENCE:
        raise HTTPException(status_code=400, detail="此端点仅适用于 external_evidence 类型的 case")

    evidence = _committee_repository.get_evidence_by_case(case_id)
    return {
        "case_id": case_id,
        "adopted": len([e for e in evidence if e.status == "success"]),
        "rejected": len([e for e in evidence if e.status == "failed"]),
        "evidence": [e.model_dump() for e in evidence],
    }


# ── GET /committee/policies ──

@app.get("/committee/policies")
async def view_committee_policies(request: Request):
    """查看委员会策略配置。"""
    _require_committee()
    _check_committee_access(request, None, "view_policies")
    cfg = _committee_coordinator.config
    return {
        "enabled": cfg.enabled,
        "default_mode": cfg.default_mode.value,
        "max_evidence_rounds": cfg.max_evidence_rounds,
        "max_parallel_evidence_tasks": cfg.max_parallel_evidence_tasks,
        "case_timeout_seconds": cfg.case_timeout_seconds,
        "crystal_enabled": cfg.crystal_enabled,
        "experiment_enabled": cfg.experiment_enabled,
        "candidate_priority_enabled": cfg.candidate_priority_enabled,
        "deviation_review_enabled": cfg.deviation_review_enabled,
        "external_evidence_enabled": cfg.external_evidence_enabled,
        "require_human_for_high_risk": cfg.require_human_for_high_risk,
        "crystal_min_score_for_dft": cfg.crystal_min_score_for_dft,
        "experiment_min_score_for_submit": cfg.experiment_min_score_for_submit,
        "prediction_disagreement_ratio": cfg.prediction_disagreement_ratio,
        "top_k_score_proximity_ratio": cfg.top_k_score_proximity_ratio,
        "experiment_relative_deviation_trigger": cfg.experiment_relative_deviation_trigger,
        "external_conflict_requires_review": cfg.external_conflict_requires_review,
        "dft_cost_trigger": cfg.dft_cost_trigger,
    }


# ── PUT /committee/policies ──

@app.put("/committee/policies")
async def update_committee_policies(req: CommitteePolicyUpdateRequest, request: Request):
    """更新委员会策略（仅 admin）。"""
    _require_committee()
    _check_committee_access(request, None, "admin_manage")

    # Validate threshold bounds to prevent bypassing hard constraints.
    if req.crystal_min_score_for_dft is not None:
        if req.crystal_min_score_for_dft < 0.5 or req.crystal_min_score_for_dft > 1.0:
            raise HTTPException(status_code=400, detail="crystal_min_score_for_dft must be between 0.5 and 1.0")
    if req.experiment_min_score_for_submit is not None:
        if req.experiment_min_score_for_submit < 0.5 or req.experiment_min_score_for_submit > 1.0:
            raise HTTPException(status_code=400, detail="experiment_min_score_for_submit must be between 0.5 and 1.0")
    if req.prediction_disagreement_ratio is not None:
        if req.prediction_disagreement_ratio < 0.0 or req.prediction_disagreement_ratio > 1.0:
            raise HTTPException(status_code=400, detail="prediction_disagreement_ratio must be between 0.0 and 1.0")
    if req.top_k_score_proximity_ratio is not None:
        if req.top_k_score_proximity_ratio < 0.0 or req.top_k_score_proximity_ratio > 1.0:
            raise HTTPException(status_code=400, detail="top_k_score_proximity_ratio must be between 0.0 and 1.0")
    if req.experiment_relative_deviation_trigger is not None:
        if req.experiment_relative_deviation_trigger < 0.0 or req.experiment_relative_deviation_trigger > 5.0:
            raise HTTPException(status_code=400, detail="experiment_relative_deviation_trigger must be between 0.0 and 5.0")

    cfg = _committee_coordinator.config
    updated = []
    if req.enabled is not None:
        cfg.enabled = req.enabled
        updated.append("enabled")
    if req.default_mode is not None:
        from .config import CommitteeMode
        cfg.default_mode = CommitteeMode(req.default_mode)
        updated.append("default_mode")
    if req.max_evidence_rounds is not None:
        cfg.max_evidence_rounds = req.max_evidence_rounds
        updated.append("max_evidence_rounds")
    if req.max_parallel_evidence_tasks is not None:
        cfg.max_parallel_evidence_tasks = req.max_parallel_evidence_tasks
        updated.append("max_parallel_evidence_tasks")
    if req.case_timeout_seconds is not None:
        cfg.case_timeout_seconds = req.case_timeout_seconds
        updated.append("case_timeout_seconds")
    if req.crystal_enabled is not None:
        cfg.crystal_enabled = req.crystal_enabled
        updated.append("crystal_enabled")
    if req.experiment_enabled is not None:
        cfg.experiment_enabled = req.experiment_enabled
        updated.append("experiment_enabled")
    if req.candidate_priority_enabled is not None:
        cfg.candidate_priority_enabled = req.candidate_priority_enabled
        updated.append("candidate_priority_enabled")
    if req.deviation_review_enabled is not None:
        cfg.deviation_review_enabled = req.deviation_review_enabled
        updated.append("deviation_review_enabled")
    if req.external_evidence_enabled is not None:
        cfg.external_evidence_enabled = req.external_evidence_enabled
        updated.append("external_evidence_enabled")
    if req.require_human_for_high_risk is not None:
        cfg.require_human_for_high_risk = req.require_human_for_high_risk
        updated.append("require_human_for_high_risk")
    if req.crystal_min_score_for_dft is not None:
        cfg.crystal_min_score_for_dft = req.crystal_min_score_for_dft
        updated.append("crystal_min_score_for_dft")
    if req.experiment_min_score_for_submit is not None:
        cfg.experiment_min_score_for_submit = req.experiment_min_score_for_submit
        updated.append("experiment_min_score_for_submit")
    if req.prediction_disagreement_ratio is not None:
        cfg.prediction_disagreement_ratio = req.prediction_disagreement_ratio
        updated.append("prediction_disagreement_ratio")
    if req.top_k_score_proximity_ratio is not None:
        cfg.top_k_score_proximity_ratio = req.top_k_score_proximity_ratio
        updated.append("top_k_score_proximity_ratio")
    if req.experiment_relative_deviation_trigger is not None:
        cfg.experiment_relative_deviation_trigger = req.experiment_relative_deviation_trigger
        updated.append("experiment_relative_deviation_trigger")
    if req.external_conflict_requires_review is not None:
        cfg.external_conflict_requires_review = req.external_conflict_requires_review
        updated.append("external_conflict_requires_review")
    if req.dft_cost_trigger is not None:
        cfg.dft_cost_trigger = req.dft_cost_trigger
        updated.append("dft_cost_trigger")
    # Persist policy changes back to .env so they survive restarts.
    # `cfg` is the in-memory CommitteeConfig on the coordinator; we mirror it
    # onto a freshly loaded AgentConfig and write the full file.
    if updated:
        try:
            full_cfg = get_config(refresh=True)
            full_cfg.committee = cfg
            save_config_to_env(full_cfg)
        except Exception as e:
            logger.warning("Failed to persist committee policy changes: %s", e)
    logger.info(
        "Committee policies updated by user=%s (fields=%s)",
        _user_role_from_request(request), updated,
    )
    return {"updated": updated, "count": len(updated)}


# ===========================================================================
# Phase 7: Agent Control Plane API
# ===========================================================================

def _require_control_plane(*components):
    """守卫：Control Plane 未初始化时抛出 503。

    传入端点实际所需的组件按需校验，避免某组件为 None 时后续抛 AttributeError；
    无参数调用时回退到检查 ``_tool_catalog``（向后兼容）。
    """
    to_check = components if components else (_tool_catalog,)
    for comp in to_check:
        if comp is None:
            raise HTTPException(
                status_code=503,
                detail="Control Plane 未初始化，请启用 CONTROL_PLANE_ENABLED=true",
            )


# ── Run Management ────────────────────────────────────────────────────────

@app.get("/control-plane/runs")
async def list_control_plane_runs(
    request: Request,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """获取运行列表。"""
    _require_control_plane(_run_manager)
    role = _user_role_from_request(request)
    # H6: 非 admin 用户按可访问项目隔离（fail-closed）。
    accessible_projects: list[str] | None = None
    if role != "admin":
        user = getattr(request.state, "current_user", None)
        user_projects = getattr(user, "project_ids", None) if user else None
        if user_projects:  # 非空列表 = 仅这些项目可访问
            accessible_projects = user_projects
            if project_id and project_id not in user_projects:
                raise HTTPException(status_code=403, detail="无权访问该项目")
    run_status = None
    if status:
        try:
            run_status = RunStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的 status: {status}")
    runs = _run_manager.get_runs(
        project_id=project_id, status=run_status, limit=limit, offset=offset,
    )
    # 合并 ECML 历史运行记录（control_plane.db 中不存在的），
    # 让控制平面与闭环迭代页面显示一致的运行总数
    try:
        ecml_runs = agent.ecml.state_store.list_runs(limit=10000)
        existing_ids = {r.run_id for r in runs}
        _ecml_status_map = {
            "completed": RunStatus.SUCCEEDED,
            "running": RunStatus.RUNNING,
            "failed": RunStatus.FAILED,
            "timeout": RunStatus.FAILED,
        }
        from datetime import datetime, timezone
        for er in ecml_runs:
            eid = er.get("run_id")
            if not eid or eid in existing_ids:
                continue
            # 按 status 过滤（如果指定了 status）
            ecml_status = _ecml_status_map.get(er.get("run_status", ""), RunStatus.RUNNING)
            if run_status is not None and ecml_status != run_status:
                continue
            ts_str = er.get("updated_at", "")
            try:
                ts_dt = (ts_str if isinstance(ts_str, datetime) else datetime.fromisoformat(ts_str)) if ts_str else datetime.now(timezone.utc)
            except Exception:
                ts_dt = datetime.now(timezone.utc)
            runs.append(ControlPlaneRun(
                run_id=eid,
                run_type="ecml",
                status=ecml_status,
                created_at=ts_dt,
                updated_at=ts_dt,
                metadata={
                    "target": er.get("target", ""),
                    "target_property": er.get("target_property", ""),
                    "iteration": er.get("iteration", 0),
                },
            ))
            existing_ids.add(eid)
    except Exception as e:
        logger.debug("合并 ECML 运行记录失败: %s", e)
    # P1-2：合并统一 Agent 调用事件，控制平面运行队列直接消费事件表
    try:
        if _agent_event_log is not None:
            from datetime import datetime as _dt, timezone
            _agent_status_map = {
                "success": ControlPlaneRunStatus.SUCCEEDED,
                "failed": ControlPlaneRunStatus.FAILED,
                "timeout": ControlPlaneRunStatus.FAILED,
            }
            for ev in _agent_event_log.list_events(limit=100):
                ts_str = ev.get("invoked_at", "")
                try:
                    ts_dt = _dt.fromisoformat(ts_str) if ts_str else _dt.now(timezone.utc)
                except Exception:
                    ts_dt = _dt.now(timezone.utc)
                ev_status = _agent_status_map.get(ev.get("status", ""), ControlPlaneRunStatus.SUCCEEDED)
                if run_status is not None and ev_status != run_status:
                    continue
                runs.append(ControlPlaneRun(
                    run_id=f"evt_{ev['event_id']}",
                    run_type="agent",
                    parent_run_id=ev.get("related_run_id") or None,
                    status=ev_status,
                    created_at=ts_dt,
                    updated_at=ts_dt,
                    metadata={
                        "agent_id": ev.get("agent_id", ""),
                        "agent_name": ev.get("agent_name", ""),
                        "step": ev.get("step", ""),
                        "duration_ms": ev.get("duration_ms", 0),
                    },
                ))
    except Exception as e:
        logger.debug("合并 Agent 事件记录失败: %s", e)
    # P3-1：合并统一研发事件流水（材料发现/合成规划/实验任务等业务事件），
    # 使控制平面运行队列与各模块历史、首页看板共享同一事件数据源。
    # 按 run_id 去重：ecml_run 类事件与上方 ECML 运行记录同源，不重复入队。
    try:
        if _research_event_stream is not None:
            from datetime import datetime as _dt2, timezone
            _revt_status_map = {
                "success": ControlPlaneRunStatus.SUCCEEDED,
                "failed": ControlPlaneRunStatus.FAILED,
                "running": ControlPlaneRunStatus.RUNNING,
            }
            for ev in _research_event_stream.list_events(limit=100):
                dedup_key = ev.get("run_id") or f"revt_{ev['event_id']}"
                if dedup_key in existing_ids:
                    continue
                ts_str = ev.get("created_at", "")
                try:
                    ts_dt = _dt2.fromisoformat(ts_str) if ts_str else _dt2.now(timezone.utc)
                except Exception:
                    ts_dt = _dt2.now(timezone.utc)
                ev_status = _revt_status_map.get(ev.get("status", ""), ControlPlaneRunStatus.SUCCEEDED)
                if run_status is not None and ev_status != run_status:
                    continue
                runs.append(ControlPlaneRun(
                    run_id=dedup_key,
                    run_type=ev.get("event_type", "research"),
                    status=ev_status,
                    created_at=ts_dt,
                    updated_at=ts_dt,
                    metadata={
                        "title": ev.get("title", ""),
                        "summary": ev.get("summary", ""),
                        "event_type_label": ev.get("event_type_label", ""),
                        "source": "research_events",
                    },
                ))
                existing_ids.add(dedup_key)
    except Exception as e:
        logger.debug("合并研发事件流水失败: %s", e)
    # 受限用户未指定 project_id 时，按可访问项目过滤结果。
    if accessible_projects is not None and not project_id:
        runs = [r for r in runs if getattr(r, "project_id", None) in accessible_projects]
    return {"runs": [r.model_dump() for r in runs], "count": len(runs)}


@app.get("/control-plane/runs/{run_id}")
async def get_control_plane_run(run_id: str):
    """获取运行详情。"""
    _require_control_plane(_run_manager)
    run = _run_manager.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} 不存在")
    return run.model_dump()


@app.post("/control-plane/runs/{run_id}/resume", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def resume_control_plane_run(run_id: str, request: Request):
    """恢复运行。"""
    _require_control_plane(_run_manager)
    try:
        run = _run_manager.resume(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(
        "Control plane run resumed by user=%s (run_id=%s)",
        _user_role_from_request(request), run_id,
    )
    return run.model_dump()


@app.post("/control-plane/runs/{run_id}/cancel", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def cancel_control_plane_run(run_id: str, request: Request):
    """取消运行。"""
    _require_control_plane(_run_manager)
    try:
        run = _run_manager.cancel(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(
        "Control plane run cancelled by user=%s (run_id=%s)",
        _user_role_from_request(request), run_id,
    )
    return run.model_dump()


# ── Trace ─────────────────────────────────────────────────────────────────

@app.get("/control-plane/traces/{correlation_id}")
async def get_trace(correlation_id: str, request: Request):
    """获取脱敏调用链。"""
    _require_control_plane(_observability_service)
    # H5: 调用链含敏感运行信息，仅 admin/pm 可查看。
    role = _user_role_from_request(request)
    if role not in ("admin", "pm"):
        raise HTTPException(status_code=403, detail="此操作需要 admin 或 pm 权限")
    events = _observability_service.get_trace(correlation_id)
    sanitized = _observability_service.sanitize_for_display(events)
    return {
        "correlation_id": correlation_id,
        "events": sanitized,
        "count": len(sanitized),
    }


# ── Budget ────────────────────────────────────────────────────────────────

@app.get("/control-plane/budgets")
async def get_budgets(scope: str | None = None, scope_id: str | None = None):
    """查询预算。

    - 无参数：返回所有预算信封列表（含用量）。
    - 仅 scope：返回该 scope 下所有预算信封。
    - scope + scope_id：返回单个 scope 的预算信封与用量详情。
    """
    _require_control_plane(_budget_manager)

    # 列表模式：无 scope_id 时返回所有信封
    if not scope_id:
        try:
            budget_scope = BudgetScope(scope) if scope else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的 scope: {scope}")
        envelopes = _budget_manager.list_envelopes(budget_scope)
        items = []
        for env in envelopes:
            usage = _budget_manager.get_usage(env.scope, env.scope_id)
            # 按 category 拆分为多行，便于前端表格展示
            categories = {c.value for c in BudgetCategory}
            used_keys = set(usage.keys())
            # 用量类别集合 = 已使用的类别 ∪ 该 envelope 有限制的类别
            limit_fields = {
                "token": env.token_limit,
                "external_call": env.external_call_limit,
                "dft_cpu_hour": env.dft_cpu_hour_limit,
                "cost": env.cost_limit,
                "concurrency": env.concurrency_limit,
            }
            for cat, limit in limit_fields.items():
                if limit is None and cat not in used_keys:
                    continue
                items.append({
                    "scope": env.scope.value,
                    "scope_id": env.scope_id,
                    "category": cat,
                    "limit": limit,
                    "reserved": 0.0,  # 列表模式不区分 reserved/settled
                    "settled": usage.get(cat, 0.0),
                    "action_on_exhaustion": env.action_on_exhaustion,
                })
        return {"budgets": items, "total": len(items)}

    # 详情模式：scope + scope_id
    try:
        budget_scope = BudgetScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 scope: {scope}")
    envelope = _budget_manager.get_envelope(budget_scope, scope_id)
    usage = _budget_manager.get_usage(budget_scope, scope_id)
    if envelope is None:
        return {
            "scope": scope,
            "scope_id": scope_id,
            "envelope": None,
            "usage": usage,
            "budgets": [],
        }
    # 同时返回单条详情和列表格式，前端可二选一使用
    items = []
    limit_fields = {
        "token": envelope.token_limit,
        "external_call": envelope.external_call_limit,
        "dft_cpu_hour": envelope.dft_cpu_hour_limit,
        "cost": envelope.cost_limit,
        "concurrency": envelope.concurrency_limit,
    }
    for cat, limit in limit_fields.items():
        if limit is None and cat not in usage:
            continue
        items.append({
            "scope": scope,
            "scope_id": scope_id,
            "category": cat,
            "limit": limit,
            "reserved": 0.0,
            "settled": usage.get(cat, 0.0),
            "action_on_exhaustion": envelope.action_on_exhaustion,
        })
    return {
        "scope": scope,
        "scope_id": scope_id,
        "envelope": envelope.model_dump(),
        "usage": usage,
        "budgets": items,
        "total": len(items),
    }


@app.put("/control-plane/budgets/{scope}")
async def update_budget(scope: str, data: dict, request: Request):
    """配置预算 (admin only)。"""
    _require_control_plane(_budget_manager)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    try:
        budget_scope = BudgetScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 scope: {scope}")
    scope_id = data.get("scope_id")
    if not scope_id:
        raise HTTPException(status_code=400, detail="data.scope_id 必填")
    envelope = BudgetEnvelope(
        scope=budget_scope,
        scope_id=scope_id,
        token_limit=data.get("token_limit"),
        external_call_limit=data.get("external_call_limit"),
        dft_cpu_hour_limit=data.get("dft_cpu_hour_limit"),
        cost_limit=data.get("cost_limit"),
        concurrency_limit=data.get("concurrency_limit"),
        action_on_exhaustion=data.get("action_on_exhaustion", "pause"),
    )
    _budget_manager.set_envelope(budget_scope, scope_id, envelope)
    logger.info(
        "Budget updated by user=%s (scope=%s, scope_id=%s)",
        role, scope, scope_id,
    )
    return envelope.model_dump()


@app.get("/budgets/token-usage")
async def get_token_usage_endpoint(project_id: str = ""):
    """查询 LLM token 用量统计。"""
    from .llm.token_tracker import get_token_usage
    return get_token_usage(project_id)


# ── Tool Catalog ──────────────────────────────────────────────────────────

@app.get("/control-plane/tools")
async def get_tools():
    """获取工具目录。"""
    _require_control_plane(_tool_catalog)
    tools = _tool_catalog.list_tools()
    return {"tools": [t.model_dump() for t in tools], "count": len(tools)}


@app.post("/control-plane/tools/{tool_id}/contract-test")
async def contract_test_tool(tool_id: str, request: Request):
    """执行工具契约测试 (admin only)。"""
    _require_control_plane(_tool_catalog)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    tool = _tool_catalog.get(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"工具 '{tool_id}' 不存在")
    checks = [
        {"name": "has_tool_id", "passed": bool(tool.tool_id)},
        {"name": "has_source", "passed": bool(tool.source)},
        {"name": "has_description", "passed": bool(tool.description)},
        {"name": "has_allowed_roles", "passed": len(tool.allowed_roles) > 0},
        {"name": "timeout_positive", "passed": tool.timeout_seconds > 0},
        {"name": "max_concurrency_positive", "passed": tool.max_concurrency > 0},
    ]
    all_passed = all(c["passed"] for c in checks)
    logger.info(
        "Contract test for tool=%s by user=%s (passed=%s)",
        tool_id, role, all_passed,
    )
    return {"tool_id": tool_id, "passed": all_passed, "checks": checks}


# ── Provider Registry ─────────────────────────────────────────────────────

@app.get("/control-plane/providers")
async def get_providers(request: Request):
    """获取 Provider 健康/版本/配额状态 (admin only)。"""
    _require_control_plane(_provider_registry)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    providers = _provider_registry.list_providers()
    import os as _os
    items = []
    for p in providers:
        d = p.model_dump(mode="json")
        # D5(P2-005)：未配置 = 需要密钥但对应环境变量未设置（local:// 无需密钥视为已配置）
        _ref = (d.get("auth_secret_ref") or "").strip()
        d["configured"] = (not _ref) or bool(_os.environ.get(_ref))
        items.append(d)
    return {
        "providers": items,
        "count": len(items),
    }


# ── Policy Registry ───────────────────────────────────────────────────────

@app.get("/control-plane/policies")
async def list_control_plane_policies(request: Request):
    """获取策略版本列表 (admin only)。"""
    _require_control_plane(_policy_store)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    versions = _policy_store.list_versions()
    return {
        "policies": [v.model_dump(mode="json") for v in versions],
        "count": len(versions),
    }


# ── Memory Cards ──────────────────────────────────────────────────────────

@app.get("/memory/cards")
async def get_memory_cards(
    request: Request,
    project_id: str | None = None,
    card_type: str | None = None,
    entity_type: str | None = None,
    query: str | None = None,
    limit: int = 20,
):
    """按权限检索决策/科学记忆卡片。"""
    _require_control_plane(_memory_service)
    role = _user_role_from_request(request)
    # H4: project_id 来自查询参数，校验调用者是否有权访问该项目（fail-closed）。
    if project_id:
        _user = getattr(request.state, "current_user", None)
        _user_id = getattr(_user, "user_id", "") if _user else ""
        _store = getattr(request.app.state, "user_store", None)
        if not _user_id or _store is None or not check_project_access(_user_id, project_id, _store):
            raise HTTPException(status_code=403, detail="无权访问该项目")
    ct = None
    if card_type:
        try:
            ct = MemoryCardType(card_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"无效的 card_type: {card_type}"
            )
    cards = _memory_service.search(
        project_id=project_id,
        query=query,
        card_type=ct,
        entity_type=entity_type,
        limit=limit,
        user_role=role,
    )
    filtered = _memory_service.filter_by_access(cards, role, project_id)
    return {
        "cards": [c.model_dump(mode="json") for c in filtered],
        "count": len(filtered),
    }


# ── Eval ──────────────────────────────────────────────────────────────────

@app.post("/evals/runs")
async def create_eval_run(data: dict, request: Request):
    """发起离线评测 (admin only)。"""
    _require_control_plane(_eval_runner)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    target_type = data.get("target_type")
    if not target_type:
        raise HTTPException(status_code=400, detail="data.target_type 必填")
    target_id = data.get("target_id", "")
    target_version = data.get("target_version", "v1")
    datasets = data.get("datasets")
    try:
        timeout_seconds = float(data.get("timeout_seconds", 600))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="timeout_seconds 必须为数值")
    baseline_version = data.get("baseline_version")
    try:
        run = await _eval_runner.run_eval(
            target_type=target_type,
            target_id=target_id,
            target_version=target_version,
            datasets=datasets,
            timeout_seconds=timeout_seconds,
            baseline_version=baseline_version,
        )
    except Exception as e:
        logger.error("Eval run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(
        "Eval run created by user=%s (eval_run_id=%s, target=%s/%s)",
        role, run.eval_run_id, target_type, target_id,
    )
    return run.model_dump(mode="json")


@app.get("/evals/runs")
async def list_eval_runs(limit: int = 50):
    """列出最近的评估运行（默认 50 条，按 started_at 倒序）。"""
    _require_control_plane(_eval_runner)
    if limit <= 0 or limit > 500:
        limit = 50
    runs = _eval_runner.list_runs(limit=limit)
    return {"eval_runs": [r.model_dump(mode="json") for r in runs], "count": len(runs)}


@app.get("/evals/runs/{eval_run_id}")
async def get_eval_run(eval_run_id: str):
    """获取评估结果。"""
    _require_control_plane(_eval_runner)
    run = _eval_runner.get_result(eval_run_id)
    if run is None:
        raise HTTPException(
            status_code=404, detail=f"评估运行 {eval_run_id} 不存在"
        )
    return run.model_dump(mode="json")


@app.post("/evals/promote")
async def promote_eval(data: dict, request: Request):
    """推广模型/策略/工具版本 (admin only)。"""
    _require_control_plane(_eval_runner)
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    eval_run_id = data.get("eval_run_id")
    if not eval_run_id:
        raise HTTPException(status_code=400, detail="data.eval_run_id 必填")
    run = _eval_runner.get_result(eval_run_id)
    if run is None:
        raise HTTPException(
            status_code=404, detail=f"评估运行 {eval_run_id} 不存在"
        )
    gate = run.metrics.get("gate", {}) if run.metrics else {}
    if not gate.get("passed", False):
        raise HTTPException(
            status_code=400,
            detail=f"评估门禁未通过，不可推广: {gate.get('violations', [])}",
        )
    promotion = {
        "eval_run_id": eval_run_id,
        "target_type": run.target_type,
        "target_id": run.target_id,
        "target_version": run.target_version,
        "promoted_by": role,
        "gate_passed": True,
    }
    logger.info(
        "Eval promoted by user=%s (eval_run_id=%s, target=%s/%s@%s)",
        role, eval_run_id, run.target_type, run.target_id, run.target_version,
    )
    return promotion


@app.post("/evals/audit")
async def run_coe_audit(data: dict | None = None, request: Request = None):
    """手动触发 CoE Audit「证据链完整性」审计 (admin only)。

    立即审计最近已产出的声明证据链，返回审计报告（含报告路径）。
    """
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    if _coe_auditor is None:
        raise HTTPException(status_code=503, detail="CoE 审计器未初始化（控制平面未启用）")
    data = data or {}
    try:
        limit = int(data.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    if limit <= 0 or limit > 1000:
        limit = 100
    try:
        report = _coe_auditor.run(limit=limit)
    except Exception as e:
        logger.error("CoE Audit failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return report


@app.get("/evals/audit")
async def list_coe_audits(request: Request = None):
    """列出 evals/reports 下的 CoE 审计报告（admin only）。"""
    role = _user_role_from_request(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要 admin 权限")
    reports = []
    report_dir = _coe_auditor.report_dir if _coe_auditor else None
    if report_dir and report_dir.is_dir():
        for fname in sorted(report_dir.glob("audit-*.json"), reverse=True)[:50]:
            reports.append({"file": fname.name, "path": str(fname)})
    return {"audit_reports": reports, "count": len(reports)}


# ── Task 9: Hybrid Orchestrator & Routing Admin API ────────────────

# Hybrid Orchestrator 全局实例（延迟初始化）
_hybrid_orchestrator = None
_research_store = None
_eligibility_store = None
_alias_registry = None
_capability_router = None
_model_router = None

# 运行中研发任务的实时事件流（run_id -> {events, status, plan, error}）
_research_run_events: dict[str, dict] = {}


def _init_hybrid_stack() -> None:
    """延迟初始化 HybridOrchestrator 及其依赖（AliasRegistry / EligibilityStore /
    CapabilityRouter / ModelRouter / ResearchStore）。幂等：已初始化则直接返回。"""
    global _hybrid_orchestrator, _research_store, _eligibility_store
    global _alias_registry, _capability_router, _model_router
    if _hybrid_orchestrator is not None:
        return
    from .hybrid.orchestrator import HybridOrchestrator
    from .hybrid.intent_interpreter import IntentInterpreter
    from .hybrid.plan_validator import PlanValidator
    from .hybrid.research_store import ResearchStore
    from .control_plane.capability_router import CapabilityRouter
    from .control_plane.model_router import ModelRouter
    from .mcp_tools.alias_registry import AliasRegistry
    from .agent_team.eligibility_store import (
        EligibilityStore, seed_default_eligibility_rules,
    )

    _alias_registry = AliasRegistry()
    _eligibility_store = EligibilityStore()
    seed_default_eligibility_rules(_eligibility_store)
    # 把 11 个原生科学服务注册为可路由能力（单一数据源派生，可经
    # SCIENTIFIC_CAPABILITIES_ENABLED 配置），使 CapabilityRouter 可解析到对应服务。
    from .services.capability_catalog import register_scientific_capabilities

    register_scientific_capabilities(_alias_registry, _eligibility_store)
    # CA3 风险门禁：将科学服务注册进 ToolCatalog，并把 tool_catalog 注入路由器，
    # 否则本地风险恒为最低 0.1，max_risk_level 过滤对科学服务形同虚设。
    if _tool_catalog is not None:
        from .services.capability_catalog import register_scientific_tools

        register_scientific_tools(_tool_catalog)
    # 注入 capability_registry 启用契约门禁：deprecated/pending_high_risk 的能力
    # 会被自动过滤，主能力不可调用时走 fallback_chain
    from .capability.registry import CapabilityRegistry as _CapRegistry
    _cap_registry = _CapRegistry()
    _capability_router = CapabilityRouter(
        _alias_registry, _eligibility_store,
        tool_catalog=_tool_catalog,
        capability_registry=_cap_registry,
    )
    # 将路由器注入 AgentProxy，使 sci_* 科学能力调用经 CapabilityRouter 路由
    if _agent_proxy is not None:
        _agent_proxy.set_capability_router(_capability_router)
    _model_router = ModelRouter()
    _research_store = ResearchStore()
    # 解析活跃领域包，注入 orchestrator 使研发流水线随领域包可插拔；
    # 库不可用或无线领域包时回退内置默认。
    domain_pack = None
    domain_pack_provider = None
    try:
        from .industrialization.domain_pack_store import DomainPackStore

        _dp_store = DomainPackStore()
        _active_pack = _dp_store.resolve_active_pack()
        if _active_pack is not None:
            domain_pack = _active_pack.data

        def _resolve_pack_by_key(key: str) -> dict | None:
            try:
                pack = _dp_store.resolve_active_pack(domain_key=key)
                return pack.data if pack is not None else None
            except Exception:
                return None

        domain_pack_provider = _resolve_pack_by_key
    except Exception:
        domain_pack = None
        domain_pack_provider = None
    _hybrid_orchestrator = HybridOrchestrator(
        _capability_router, _model_router, IntentInterpreter(), PlanValidator(),
        domain_pack=domain_pack,
        domain_pack_provider=domain_pack_provider,
        tool_executor=lambda action, **kw: agent.tools.execute(action, **kw),
    )
    # 把 capability_router 注入 executor，让策略检查（prohibited/risk/human_review）生效
    if _executor is not None:
        _executor._capability_router = _capability_router
        _executor._execution_profile = "standard"


class CreateResearchRequest(BaseModel):
    goal: str
    material_scope: str = ""  # 材料类型枚举（crystal/polymer/molecule）
    material_system: str = ""  # 材料体系名（领域包 material_systems.name）
    target_properties: list[dict] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    preference: str = "balanced"
    domain_key: str = ""  # 领域包关键字（如 battery/kingfa）；空则用默认
    project_id: str = ""
    task_id: str = ""  # 业务链路：关联 projects.tasks(task_id)
    scenario_id: str = ""  # P0-001：前端传入的全局场景 ID


# ── 领域注册表：暴露材料领域包，前端据此识别材料类型 ──────────────

@app.get("/domain-packs")
async def list_domain_packs():
    """列出活跃领域包（领域注册表）。

    前端据此识别候选材料所属领域 / 材料表示法，避免对交付物文本做
    硬编码关键词猜测（如 deliverable.includes('聚合物') → polymer）。

    返回的 material_kind 由领域包 data.pipeline 键推断：优先声明所支持的
    材料类型（crystal/polymer/molecule），供前端选择对应生成/预测通道。
    """
    packs = []
    try:
        from .industrialization.domain_pack_store import DomainPackStore
        store = DomainPackStore()
        for p in store.list_packs():
            data = p.data or {}
            packs.append({
                "domain_key": p.domain_key,
                "name": p.name,
                "description": p.description,
                "material_representation": p.material_representation,
                "material_kind": _infer_domain_material_kind(data),
                "default_target_properties": data.get("default_target_properties") or [],
                "is_active": p.is_active,
            })
    except Exception:
        packs = []
    return {"packs": packs, "count": len(packs)}


@app.get("/settings/domain")
async def get_active_domain():
    """获取当前生效的研发领域（DB 持久化，系统启动时读取并按其执行）。"""
    from .industrialization.domain_pack_store import DomainPackStore
    store = DomainPackStore()
    pack = store.resolve_active_pack()
    packs = store.list_packs()
    return {
        "active_domain_key": pack.domain_key if pack else "",
        "active_domain_name": pack.name if pack else "",
        "packs": [
            {
                "domain_key": p.domain_key,
                "name": p.name,
                "description": p.description,
                "material_kind": _infer_domain_material_kind(p.data or {}),
                "is_active": p.is_active,
            }
            for p in packs
        ],
    }


@app.post("/settings/domain", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def set_active_domain(payload: dict = Body(...)):
    """设置系统默认研发领域（DB 持久化）。

    将指定领域包置为活跃、其余置为非活跃；系统重启后按该领域执行
    （_resolve_material_domain 启动时读取活跃包）。
    """
    domain_key = str(payload.get("domain_key") or "").strip()
    if not domain_key:
        raise HTTPException(status_code=400, detail="domain_key 不能为空")
    from .industrialization.domain_pack_store import DomainPackStore
    store = DomainPackStore()
    target = store.get_pack(domain_key)
    if target is None:
        raise HTTPException(status_code=404, detail=f"领域包 {domain_key} 不存在")
    for p in store.list_packs():
        store.set_active(p.domain_key, p.domain_key == domain_key)
    updated = store.get_pack(domain_key)
    return {
        "domain_key": domain_key,
        "name": updated.name if updated else "",
        "is_active": True,
        "message": f"研发领域已切换为「{updated.name if updated else domain_key}」，后续请求按该领域执行",
    }


def _infer_domain_material_kind(data: dict) -> str:
    """从领域包 data.pipeline 键推断主材料类型（crystal/polymer/molecule）。

    规则：pipeline 中除 "*" 外的键作为候选；含 crystal 则优先 crystal，
    否则按 polymer > molecule > 默认 crystal 的顺序取第一个。
    """
    pipeline = data.get("pipeline") or {}
    keys = [k for k in pipeline.keys() if k != "*"]
    if "crystal" in keys:
        return "crystal"
    for preferred in ("polymer", "molecule"):
        if preferred in keys:
            return preferred
    return "crystal"


# ── SubTask 9.1: Research Request API ──────────────────────────────

@app.post("/research/requests")
async def create_research_request(
    req: CreateResearchRequest,
    user: User | None = Depends(require_role(UserRole.PROJECT_MANAGER)),
):
    """创建研发请求并生成计划。"""
    _init_hybrid_stack()
    from .hybrid.orchestrator import ResearchRequest
    request = ResearchRequest(
        scenario_id=req.scenario_id,
        goal=req.goal,
        material_scope=req.material_scope,
        material_system=req.material_system,
        target_properties=req.target_properties,
        constraints=req.constraints,
        preference=req.preference,
        domain_key=req.domain_key,
        project_id=req.project_id,
        task_id=req.task_id,
        user_id=user.user_id if user else "",
    )
    request_id = _research_store.create_request(request)
    request.request_id = request_id
    # P0-001：若后端生成 scenario_id，与 request_id 保持一致并返回给前端
    scenario_id = request.scenario_id or request_id
    plan = await _hybrid_orchestrator.plan(request)
    _research_store.create_plan(plan)
    return {"request_id": request_id, "scenario_id": scenario_id, "plan": plan.model_dump()}


@app.get("/research/requests/{request_id}")
async def get_research_request(request_id: str):
    """获取研发请求详情（含关联计划列表）。"""
    _init_hybrid_stack()
    request = _research_store.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"研发请求 {request_id} 不存在")
    plans = _research_store.get_plans_by_request(request_id)
    return {"request": request, "plans": plans}


@app.get("/research/requests")
async def list_research_requests(limit: int = Query(default=50, ge=1, le=500), status: str | None = None):
    """列出研发请求，支持按 status 过滤。"""
    _init_hybrid_stack()
    requests = _research_store.list_requests(limit=limit, status=status)
    return {"requests": requests, "count": len(requests)}


@app.post("/research/requests/{request_id}/start")
async def start_research_run(
    request_id: str,
    user: User | None = Depends(require_role(UserRole.PROJECT_MANAGER)),
):
    """开始执行研发请求（异步：立即返回 run_id，事件通过轮询获取）。"""
    _init_hybrid_stack()
    from .hybrid.orchestrator import ResearchPlan, ResearchRequest
    request = _research_store.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"研发请求 {request_id} 不存在")
    plans = _research_store.get_plans_by_request(request_id)
    if not plans:
        raise HTTPException(status_code=400, detail="研发请求尚未生成计划，无法启动")
    plan = ResearchPlan.model_validate(plans[-1])
    req = ResearchRequest.model_validate(request)
    _research_store.update_request_status(request_id, "running")
    _research_store.update_plan_status(plan.plan_id, "running")

    run_id = request_id
    _research_run_events[run_id] = {
        "events": [],
        "status": "running",
        "plan": plan.model_dump(),
        "request_id": request_id,
        "plan_id": plan.plan_id,
    }

    async def _run():
        try:
            async for event in _hybrid_orchestrator.execute(plan, req):
                _research_run_events[run_id]["events"].append(event)
            _research_run_events[run_id]["status"] = "completed"
            _research_run_events[run_id]["completed_steps"] = [
                s.step_id for s in plan.steps if s.status == "completed"
            ]
            _research_store.update_request_status(request_id, plan.status)
            _research_store.update_plan_status(plan.plan_id, plan.status)
        except Exception as e:  # noqa: BLE001
            _research_run_events[run_id]["status"] = "failed"
            _research_run_events[run_id]["error"] = str(e)

    _spawn_background(_run())
    return {"run_id": run_id, "status": "running"}


@app.get("/research/runs/{run_id}/events")
async def get_research_run_events(run_id: str):
    """轮询获取研发运行的事件流和状态。"""
    data = _research_run_events.get(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"运行 {run_id} 不存在")
    return {
        "run_id": run_id,
        "status": data["status"],
        "events": data["events"],
        "plan": data.get("plan", {}),
        "request_id": data.get("request_id", ""),
        "plan_id": data.get("plan_id", ""),
        "completed_steps": data.get("completed_steps", []),
        "error": data.get("error", ""),
    }


# ── SubTask 9.2: Research Run API ──────────────────────────────────

@app.post("/research/runs/{plan_id}/replan")
async def replan_research_run(
    plan_id: str,
    user: User | None = Depends(require_role(UserRole.PROJECT_MANAGER)),
):
    """基于已完成步骤重新规划。"""
    _init_hybrid_stack()
    from .hybrid.orchestrator import ResearchPlan
    plan_dict = _research_store.get_plan(plan_id)
    if plan_dict is None:
        raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
    plan = ResearchPlan.model_validate(plan_dict)
    completed = [s.step_id for s in plan.steps if s.status == "completed"]
    new_plan = await _hybrid_orchestrator.replan(plan, completed)
    _research_store.create_plan(new_plan)
    return {"plan_id": new_plan.plan_id, "plan": new_plan.model_dump()}


@app.get("/research/runs/{request_id}/explain")
async def explain_research_run(request_id: str):
    """获取业务级运行解释（步骤、进度、等待原因）。

    不暴露 Secret、思维链或原始工具配置，仅返回业务可读的执行摘要。
    """
    _init_hybrid_stack()
    request = _research_store.get_request(request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"研发请求 {request_id} 不存在")
    plans = _research_store.get_plans_by_request(request_id)
    if not plans:
        return {
            "request_id": request_id,
            "goal": request["goal"],
            "status": request["status"],
            "explanation": "尚未生成执行计划",
            "steps": [],
            "progress": {"completed": 0, "total": 0},
        }
    latest = plans[-1]
    steps = latest["steps"]
    completed = sum(1 for s in steps if s.get("status") == "completed")
    total = len(steps)
    step_explanations = [
        {
            "step_id": s.get("step_id"),
            "action": s.get("action"),
            "agent_id": s.get("agent_id"),
            "status": s.get("status"),
            "autonomy_level": s.get("autonomy_level"),
        }
        for s in steps
    ]
    plan_status = latest["status"]
    if plan_status == "completed":
        explanation = f"研发流程已完成，共 {total} 个步骤全部执行成功。"
    elif plan_status == "running":
        explanation = f"研发流程执行中，已完成 {completed}/{total} 个步骤。"
    elif plan_status == "draft":
        explanation = f"已生成执行计划（{total} 个步骤），等待启动。"
    elif plan_status == "invalid":
        explanation = f"计划校验失败：{latest['rationale']}"
    else:
        explanation = f"研发流程状态：{plan_status}（{completed}/{total} 步完成）。"
    return {
        "request_id": request_id,
        "goal": request["goal"],
        "status": plan_status,
        "explanation": explanation,
        "steps": step_explanations,
        "progress": {"completed": completed, "total": total},
        "risk_summary": latest.get("risk_summary") or {},
    }


# ── SubTask 9.3: Agent Eligibility API ─────────────────────────────

@app.get("/agents/{agent_id}/eligibility")
async def get_agent_eligibility(
    agent_id: str,
    user: User | None = Depends(require_role(UserRole.PROJECT_MANAGER)),
):
    """查看 Agent 的能力到 alias/binding 的策略化路由规则。"""
    _init_hybrid_stack()
    rules = _eligibility_store.list_by_agent(agent_id)
    return {
        "agent_id": agent_id,
        "rules": [r.model_dump() for r in rules],
        "count": len(rules),
    }


@app.put("/agents/{agent_id}/eligibility")
async def update_agent_eligibility(
    agent_id: str,
    rules: list[dict],
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """维护 ToolEligibilityRule（存在则更新，不存在则创建）。"""
    _init_hybrid_stack()
    from .agent_team.models import ToolEligibilityRule
    results = []
    for rule_data in rules:
        rule_data = {**rule_data, "agent_id": agent_id}
        try:
            rule = ToolEligibilityRule.model_validate(rule_data)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"规则格式错误: {exc}",
            )
        if rule.rule_id and _eligibility_store.update(rule.rule_id, rule):
            results.append({"rule_id": rule.rule_id, "action": "updated"})
        else:
            rule_id = _eligibility_store.create(rule)
            results.append({"rule_id": rule_id, "action": "created"})
    return {"agent_id": agent_id, "results": results}


# ── SubTask 9.4: Model Route API ───────────────────────────────────

@app.get("/model-routes")
async def list_model_routes(
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """列出所有模型路由。"""
    _init_hybrid_stack()
    routes = _model_router.list_all()
    return {"routes": [r.model_dump() for r in routes], "count": len(routes)}


@app.patch("/model-routes/{route_id}")
async def update_model_route(
    route_id: str,
    updates: dict,
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """修改模型路由（部分更新）。"""
    _init_hybrid_stack()
    from .control_plane.model_router import ModelRoute
    route = _model_router.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"模型路由 {route_id} 不存在")
    updated_data = route.model_dump()
    updated_data.update(updates)
    try:
        new_route = ModelRoute.model_validate(updated_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模型路由参数错误: {exc}")
    if not _model_router.update(route_id, new_route):
        raise HTTPException(status_code=404, detail=f"模型路由 {route_id} 更新失败")
    return new_route.model_dump()


# ── SubTask 9.5: Routing Admin API ──────────────────────────────────

@app.get("/admin/routing/outcomes")
async def list_routing_outcomes(
    request_id: str | None = None,
    limit: int = 50,
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """查看路由质量数据（按 request_id 过滤）。"""
    _init_hybrid_stack()
    if request_id:
        outcomes = _research_store.get_outcomes_by_request(request_id)
    else:
        outcomes = []
    outcomes = outcomes[:limit]
    return {"outcomes": outcomes, "count": len(outcomes)}


@app.post("/admin/routing/proposals")
async def create_routing_proposal(
    proposal: dict,
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """创建路由策略提案（生成 draft 状态的策略版本）。"""
    _init_hybrid_stack()
    version = proposal.get("version") or f"v-{uuid.uuid4().hex[:8]}"
    weights = proposal.get("weights") or {}
    version_id = _research_store.create_policy_version(version, weights)
    return {
        "version_id": version_id,
        "version": version,
        "weights": weights,
        "status": "draft",
    }


@app.post("/admin/routing/policies/{version_id}/promote")
async def promote_routing_policy(
    version_id: str,
    user: User | None = Depends(require_role(UserRole.ADMIN)),
):
    """提升路由策略版本为激活版本（其余激活版本归档）。"""
    _init_hybrid_stack()
    _research_store.promote_policy_version(version_id)
    return {"version_id": version_id, "status": "active"}


# ===========================================================================
# P1: MDM 参考字典中心 API
# ===========================================================================

@app.get("/mdm/status-codes")
async def list_mdm_status_codes(domain: str = ""):
    """列出状态码主数据。可选 domain 过滤（sample/equipment/order/test_task/task/idea/material_request/case/run/tool_health）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_status_codes(domain=domain)
    return {"status_codes": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/status-codes/{domain}/{code}")
async def get_mdm_status_code(domain: str, code: str):
    """按 domain + code 查询单条状态码。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.get_status_code(domain, code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"状态码 {domain}.{code} 不存在")
    return item.model_dump()


@app.get("/mdm/classifications")
async def list_mdm_classifications(domain: str = "", parent_code: str = ""):
    """列出分类码主数据。支持 domain 与 parent_code 过滤。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_classifications(domain=domain, parent_code=parent_code)
    return {"classifications": [c.model_dump() for c in items], "count": len(items)}


@app.get("/mdm/classifications/{code}")
async def get_mdm_classification(code: str):
    """按 code 查询单条分类码。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.get_classification(code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"分类码 {code} 不存在")
    return item.model_dump()


@app.get("/mdm/units")
async def list_mdm_units(dimension: str = ""):
    """列出标准单位主数据。可选 dimension 过滤（mass/volume/concentration/temperature/pressure/conductivity/voltage/specific_capacity/energy/density/time/rotational_speed）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_units(dimension=dimension)
    return {"units": [u.model_dump() for u in items], "count": len(items)}


@app.get("/mdm/units/{unit_code}")
async def get_mdm_unit(unit_code: str):
    """按 unit_code 查询单条单位。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.get_unit(unit_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"单位 {unit_code} 不存在")
    return item.model_dump()


@app.get("/mdm/unit-conversions")
async def list_mdm_unit_conversions(from_unit: str = ""):
    """列出单位换算规则。可选 from_unit 过滤。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_conversions(from_unit=from_unit)
    return {"conversions": [c.model_dump() for c in items], "count": len(items)}


class UnitConvertRequest(BaseModel):
    value: float
    from_unit: str
    to_unit: str


@app.post("/mdm/units/convert")
async def convert_unit(req: UnitConvertRequest):
    """单位换算。返回换算后的值；若无换算路径返回 422。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    result = store.convert(req.value, req.from_unit, req.to_unit)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"未找到 {req.from_unit} → {req.to_unit} 的换算路径",
        )
    return {
        "value": req.value,
        "from_unit": req.from_unit,
        "to_unit": req.to_unit,
        "converted_value": result,
    }


@app.get("/mdm/standards")
async def list_mdm_standards(issuer: str = ""):
    """列出方法标准主数据。可选 issuer 过滤（国标/ISO/ASTM/IEC/企业/SOP）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_standards(issuer=issuer)
    return {"standards": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/standards/{standard_code}")
async def get_mdm_standard(standard_code: str):
    """按 standard_code 查询单条方法标准。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.get_standard(standard_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"方法标准 {standard_code} 不存在")
    return item.model_dump()


@app.get("/mdm/ghs-classes")
async def list_mdm_ghs_classes():
    """列出 GHS 危害分类主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_ghs_classes()
    return {"ghs_classes": [g.model_dump() for g in items], "count": len(items)}


@app.get("/mdm/dimensions")
async def list_mdm_dimensions(domain: str = ""):
    """列出通用维度主数据。可选 domain 过滤（priority/project_type/target_application/supplier_type/role）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    items = store.list_dimensions(domain=domain)
    return {"dimensions": [d.model_dump() for d in items], "count": len(items)}


@app.get("/mdm/dimensions/{domain}/{code}")
async def get_mdm_dimension(domain: str, code: str):
    """按 domain + code 查询单条通用维度。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.get_dimension(domain, code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"维度 {domain}.{code} 不存在")
    return item.model_dump()


# ──────────────────────────────────────────────────────────────────────────────
# P2 主数据：物料/样品类型/设备模板/位置
# ──────────────────────────────────────────────────────────────────────────────
from .mdm.master_data import MasterDataStore  # noqa: E402


@app.get("/mdm/sample-types")
async def list_mdm_sample_types(is_active: bool | None = None):
    """列出样品类型模板主数据。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_sample_types(is_active=is_active)
    return {"sample_types": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/sample-types/{type_code}")
async def get_mdm_sample_type(type_code: str):
    """按 type_code 查询单条样品类型。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_sample_type(type_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"样品类型 {type_code} 不存在")
    return item.model_dump()


@app.get("/mdm/sample-status-transitions")
async def list_mdm_sample_status_transitions(from_status: str = ""):
    """列出样品状态迁移规则。可选 from_status 过滤。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_sample_status_transitions(from_status=from_status)
    return {"transitions": [t.model_dump() for t in items], "count": len(items)}


@app.get("/mdm/sample-status-transitions/check")
async def check_mdm_sample_status_transition(from_status: str, to_status: str):
    """检查样品状态迁移是否允许及是否需要审批。"""
    store: MasterDataStore = app.state.master_data_store
    is_allowed = store.is_transition_allowed(from_status, to_status)
    requires_approval = store.transition_requires_approval(from_status, to_status) if is_allowed else False
    return {
        "from_status": from_status,
        "to_status": to_status,
        "is_allowed": is_allowed,
        "requires_approval": requires_approval,
    }


@app.get("/mdm/locations")
async def list_mdm_locations(parent_id: str = "", location_type: str = ""):
    """列出位置主数据。支持 parent_id / location_type 过滤。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_locations(parent_id=parent_id, location_type=location_type)
    return {"locations": [l.model_dump() for l in items], "count": len(items)}


@app.get("/mdm/locations/{location_id}")
async def get_mdm_location(location_id: str):
    """按 location_id 查询单条位置。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_location(location_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"位置 {location_id} 不存在")
    return item.model_dump()


@app.get("/mdm/locations/{location_id}/tree")
async def get_mdm_location_tree(location_id: str):
    """获取指定位置及其子位置树。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.get_location_tree(root_id=location_id)
    return {"locations": [l.model_dump() for l in items], "count": len(items)}


@app.get("/mdm/containers")
async def list_mdm_containers(container_type: str = ""):
    """列出容器与包装主数据。可选 container_type 过滤。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_containers(container_type=container_type)
    return {"containers": [c.model_dump() for c in items], "count": len(items)}


@app.get("/mdm/containers/{container_code}")
async def get_mdm_container(container_code: str):
    """按 container_code 查询单条容器。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_container(container_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"容器 {container_code} 不存在")
    return item.model_dump()


@app.get("/mdm/logistics-types")
async def list_mdm_logistics_types(direction: str = ""):
    """列出物流类型主数据。可选 direction 过滤（IN/OUT/INTERNAL）。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_logistics_types(direction=direction)
    return {"logistics_types": [l.model_dump() for l in items], "count": len(items)}


@app.get("/mdm/logistics-types/{type_code}")
async def get_mdm_logistics_type(type_code: str):
    """按 type_code 查询单条物流类型。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_logistics_type(type_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"物流类型 {type_code} 不存在")
    return item.model_dump()


@app.get("/mdm/equipment-templates")
async def list_mdm_equipment_templates(category_code: str = ""):
    """列出设备模板主数据。可选 category_code 过滤。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_equipment_templates(category_code=category_code)
    return {"equipment_templates": [e.model_dump() for e in items], "count": len(items)}


@app.get("/mdm/equipment-templates/{template_code}")
async def get_mdm_equipment_template(template_code: str):
    """按 template_code 查询单条设备模板。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_equipment_template(template_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"设备模板 {template_code} 不存在")
    return item.model_dump()


@app.get("/mdm/equipment-templates/{template_code}/capabilities")
async def list_mdm_template_capabilities(template_code: str):
    """列出指定设备模板的能力关联。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_template_capabilities(template_code=template_code)
    return {"template_capabilities": [t.model_dump() for t in items], "count": len(items)}


@app.get("/mdm/equipment-capabilities")
async def list_mdm_equipment_capabilities(capability_type: str = ""):
    """列出设备能力主数据。可选 capability_type 过滤（range/accuracy/throughput/process_window）。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_equipment_capabilities(capability_type=capability_type)
    return {"equipment_capabilities": [e.model_dump() for e in items], "count": len(items)}


@app.get("/mdm/equipment-capabilities/{capability_code}")
async def get_mdm_equipment_capability(capability_code: str):
    """按 capability_code 查询单条设备能力。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_equipment_capability(capability_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"设备能力 {capability_code} 不存在")
    return item.model_dump()


@app.get("/mdm/material-categories")
async def list_mdm_material_categories():
    """列出物料分类治理主数据。"""
    store: MasterDataStore = app.state.master_data_store
    items = store.list_material_categories()
    return {"material_categories": [m.model_dump() for m in items], "count": len(items)}


@app.get("/mdm/material-categories/{category_code}")
async def get_mdm_material_category(category_code: str):
    """按 category_code 查询单条物料分类。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.get_material_category(category_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"物料分类 {category_code} 不存在")
    return item.model_dump()


# ──────────────────────────────────────────────────────────────────────────────
# P3 CIMC：特性-指标-方法-能力
# ──────────────────────────────────────────────────────────────────────────────
from .mdm.cimc import CimcStore  # noqa: E402


@app.get("/mdm/properties")
async def list_mdm_properties(property_type: str = ""):
    """列出特性主数据。可选 property_type 过滤（electrochemical/morphological/physical/chemical）。"""
    store: CimcStore = app.state.cimc_store
    items = store.list_properties(property_type=property_type)
    return {"properties": [p.model_dump() for p in items], "count": len(items)}


@app.get("/mdm/properties/{property_id}")
async def get_mdm_property(property_id: str):
    """按 property_id 查询单条特性。"""
    store: CimcStore = app.state.cimc_store
    item = store.get_property(property_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"特性 {property_id} 不存在")
    return item.model_dump()


@app.get("/mdm/properties-with-units")
async def list_mdm_properties_with_units():
    """返回所有特性及其可选单位映射列表（前端用于属性名→单位自动联动，一次性加载）。

    每项含 property_id / property_name / default_unit / units。
    mdm.properties 暂无 allowed_units 字段，units 取 [default_unit]；default_unit 为空时 units 为空数组。
    """
    store: CimcStore = app.state.cimc_store
    items = store.list_properties()
    result = []
    for p in items:
        default = (p.default_unit or "").strip()
        result.append({
            "property_id": p.property_id,
            "property_name": p.name,
            "default_unit": default,
            "units": [default] if default else [],
        })
    return {"properties": result, "count": len(result)}


@app.get("/mdm/test-methods")
async def list_mdm_test_methods(standard_code: str = ""):
    """列出检测方法主数据。可选 standard_code 过滤。"""
    store: CimcStore = app.state.cimc_store
    items = store.list_test_methods(standard_code=standard_code)
    return {"test_methods": [m.model_dump() for m in items], "count": len(items)}


@app.get("/mdm/test-methods/{method_id}")
async def get_mdm_test_method(method_id: str):
    """按 method_id 查询单条检测方法。"""
    store: CimcStore = app.state.cimc_store
    item = store.get_test_method(method_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"检测方法 {method_id} 不存在")
    return item.model_dump()


@app.get("/mdm/test-items")
async def list_mdm_test_items(property_id: str = "", test_method_id: str = ""):
    """列出指标项目主数据。支持 property_id / test_method_id 过滤。"""
    store: CimcStore = app.state.cimc_store
    items = store.list_test_items(property_id=property_id, test_method_id=test_method_id)
    return {"test_items": [i.model_dump() for i in items], "count": len(items)}


@app.get("/mdm/test-items/{item_id}")
async def get_mdm_test_item(item_id: str):
    """按 item_id 查询单条指标项目。"""
    store: CimcStore = app.state.cimc_store
    item = store.get_test_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"指标项目 {item_id} 不存在")
    return item.model_dump()


@app.get("/mdm/specifications")
async def list_mdm_specifications(item_id: str = ""):
    """列出规格与判定主数据。可选 item_id 过滤。"""
    store: CimcStore = app.state.cimc_store
    items = store.list_specifications(item_id=item_id)
    return {"specifications": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/specifications/{spec_id}")
async def get_mdm_specification(spec_id: str):
    """按 spec_id 查询单条规格。"""
    store: CimcStore = app.state.cimc_store
    item = store.get_specification(spec_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"规格 {spec_id} 不存在")
    return item.model_dump()


@app.get("/mdm/inspection-capabilities")
async def list_mdm_inspection_capabilities(method_id: str = ""):
    """列出检查能力主数据。可选 method_id 过滤。"""
    store: CimcStore = app.state.cimc_store
    items = store.list_inspection_capabilities(method_id=method_id)
    return {"inspection_capabilities": [i.model_dump() for i in items], "count": len(items)}


@app.get("/mdm/inspection-capabilities/{capability_id}")
async def get_mdm_inspection_capability(capability_id: str):
    """按 capability_id 查询单条检查能力。"""
    store: CimcStore = app.state.cimc_store
    item = store.get_inspection_capability(capability_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"检查能力 {capability_id} 不存在")
    return item.model_dump()


# ──────────────────────────────────────────────────────────────────────────────
# P4 工艺路线-步骤-参数-设备能力
# ──────────────────────────────────────────────────────────────────────────────
from .mdm.process import ProcessStore  # noqa: E402


@app.get("/mdm/process-routes")
async def list_mdm_process_routes(route_type: str = ""):
    """列出工艺路线模板主数据。可选 route_type 过滤。"""
    store: ProcessStore = app.state.process_store
    items = store.list_process_routes(route_type=route_type)
    return {"process_routes": [r.model_dump() for r in items], "count": len(items)}


@app.get("/mdm/process-routes/{route_id}")
async def get_mdm_process_route(route_id: str):
    """按 route_id 查询单条工艺路线。"""
    store: ProcessStore = app.state.process_store
    item = store.get_process_route(route_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"工艺路线 {route_id} 不存在")
    return item.model_dump()


@app.get("/mdm/process-routes/{route_id}/steps")
async def list_mdm_route_steps(route_id: str):
    """列出指定工艺路线的步骤序列。"""
    store: ProcessStore = app.state.process_store
    items = store.list_route_steps(route_id=route_id)
    return {"route_steps": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/process-steps")
async def list_mdm_process_steps(step_type: str = ""):
    """列出工艺步骤模板主数据。可选 step_type 过滤。"""
    store: ProcessStore = app.state.process_store
    items = store.list_process_steps(step_type=step_type)
    return {"process_steps": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/process-steps/{step_id}")
async def get_mdm_process_step(step_id: str):
    """按 step_id 查询单条工艺步骤。"""
    store: ProcessStore = app.state.process_store
    item = store.get_process_step(step_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"工艺步骤 {step_id} 不存在")
    return item.model_dump()


@app.get("/mdm/process-steps/{step_id}/parameters")
async def list_mdm_step_parameters(step_id: str):
    """列出指定工艺步骤的参数关联。"""
    store: ProcessStore = app.state.process_store
    items = store.list_step_parameters(step_id=step_id)
    return {"step_parameters": [p.model_dump() for p in items], "count": len(items)}


@app.get("/mdm/process-steps/{step_id}/equipment-templates")
async def list_mdm_step_equipment_templates(step_id: str):
    """列出指定工艺步骤关联的设备模板。"""
    store: ProcessStore = app.state.process_store
    items = store.list_step_equipment_templates(step_id=step_id)
    return {"step_equipment_templates": [e.model_dump() for e in items], "count": len(items)}


@app.get("/mdm/process-parameters")
async def list_mdm_process_parameters(parameter_type: str = ""):
    """列出工艺参数字典主数据。可选 parameter_type 过滤。"""
    store: ProcessStore = app.state.process_store
    items = store.list_process_parameters(parameter_type=parameter_type)
    return {"process_parameters": [p.model_dump() for p in items], "count": len(items)}


@app.get("/mdm/process-parameters/{parameter_id}")
async def get_mdm_process_parameter(parameter_id: str):
    """按 parameter_id 查询单条工艺参数。"""
    store: ProcessStore = app.state.process_store
    item = store.get_process_parameter(parameter_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"工艺参数 {parameter_id} 不存在")
    return item.model_dump()


# ──────────────────────────────────────────────────────────────────────────────
# P5 文档版本与执行快照
# ──────────────────────────────────────────────────────────────────────────────
from .mdm.documents import DocumentStore  # noqa: E402


@app.get("/mdm/documents")
async def list_mdm_documents(document_type: str = ""):
    """列出文档主数据。可选 document_type 过滤。"""
    store: DocumentStore = app.state.document_store
    items = store.list_documents(document_type=document_type)
    return {"documents": [d.model_dump() for d in items], "count": len(items)}


@app.get("/mdm/documents/{document_id}")
async def get_mdm_document(document_id: str):
    """按 document_id 查询单条文档。"""
    store: DocumentStore = app.state.document_store
    item = store.get_document(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"文档 {document_id} 不存在")
    return item.model_dump()


@app.get("/mdm/documents/{document_id}/versions")
async def list_mdm_document_versions(document_id: str):
    """列出指定文档的版本列表。"""
    store: DocumentStore = app.state.document_store
    items = store.list_document_versions(document_id=document_id)
    return {"document_versions": [v.model_dump() for v in items], "count": len(items)}


@app.get("/mdm/document-versions/{version_id}")
async def get_mdm_document_version(version_id: str):
    """按 version_id 查询单条文档版本。"""
    store: DocumentStore = app.state.document_store
    item = store.get_document_version(version_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"文档版本 {version_id} 不存在")
    return item.model_dump()


@app.get("/experiment/orders/{order_id}/snapshots")
async def list_order_snapshots(order_id: str):
    """列出指定实验订单的版本快照。"""
    store: DocumentStore = app.state.document_store
    items = store.list_order_snapshots(order_id=order_id)
    return {"order_snapshots": [s.model_dump() for s in items], "count": len(items)}


@app.get("/mdm/order-snapshots/{snapshot_id}")
async def get_order_snapshot(snapshot_id: str):
    """按 snapshot_id 查询单条订单版本快照。"""
    store: DocumentStore = app.state.document_store
    item = store.get_order_snapshot(snapshot_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"订单快照 {snapshot_id} 不存在")
    return item.model_dump()


# ===========================================================================
# MDM 写入接口：create (POST) / toggle_active (PATCH)
# ===========================================================================

# ── P1 参考字典中心 ──────────────────────────────────────
@app.post("/mdm/status-codes")
async def create_mdm_status_code(payload: dict = Body(...)):
    """创建状态码主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_status_code(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/status-codes/{domain}/{code}/active")
async def set_mdm_status_code_active(domain: str, code: str, is_active: bool = Query(...)):
    """启用/停用状态码。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_status_code_active(domain, code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/classifications")
async def create_mdm_classification(payload: dict = Body(...)):
    """创建分类码主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_classification(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/classifications/{code}/active")
async def set_mdm_classification_active(code: str, is_active: bool = Query(...)):
    """启用/停用分类码。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_classification_active(code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/units")
async def create_mdm_unit(payload: dict = Body(...)):
    """创建标准单位主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_unit(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/units/{unit_code}/active")
async def set_mdm_unit_active(unit_code: str, is_active: bool = Query(...)):
    """启用/停用标准单位。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_unit_active(unit_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


# ── MDM 单位版本管理（T-018 / T-019）─────────────────────────────
@app.get("/mdm/units/{unit_code}/versions")
async def list_mdm_unit_versions(unit_code: str):
    """列出指定单位的历史版本列表（按版本号倒序）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    # 校验单位存在
    if store.get_unit(unit_code) is None:
        raise HTTPException(status_code=404, detail=f"单位 {unit_code} 不存在")
    versions = store.list_unit_versions(unit_code)
    return {"unit_code": unit_code, "versions": versions, "count": len(versions)}


@app.get("/mdm/units/{unit_code}/versions/compare")
async def compare_mdm_unit_versions(unit_code: str, v1: str = Query(...), v2: str = Query(...)):
    """对比指定单位的两个版本，返回字段级 diff（T-019）。

    - v1/v2 为 version_id
    - 返回 {version_a, version_b, diff: [{field, old_value, new_value, change_type}]}
    - change_type: 'added' / 'removed' / 'modified' / 'unchanged'
    """
    store: ReferenceDictStore = app.state.reference_dict_store
    if store.get_unit(unit_code) is None:
        raise HTTPException(status_code=404, detail=f"单位 {unit_code} 不存在")
    va = store.get_unit_version(v1)
    vb = store.get_unit_version(v2)
    if va is None:
        raise HTTPException(status_code=404, detail=f"版本 {v1} 不存在")
    if vb is None:
        raise HTTPException(status_code=404, detail=f"版本 {v2} 不存在")
    if va.get("entity_id") != unit_code or vb.get("entity_id") != unit_code:
        raise HTTPException(status_code=400, detail="版本与单位不匹配")

    snap_a = va.get("snapshot") or {}
    snap_b = vb.get("snapshot") or {}
    # 以 v1 为 old、v2 为 new 计算字段级 diff
    all_fields = sorted(set(snap_a.keys()) | set(snap_b.keys()))
    diff = []
    for field in all_fields:
        in_a = field in snap_a
        in_b = field in snap_b
        old_value = snap_a.get(field)
        new_value = snap_b.get(field)
        if in_a and not in_b:
            change_type = "removed"
        elif not in_a and in_b:
            change_type = "added"
        elif old_value != new_value:
            change_type = "modified"
        else:
            change_type = "unchanged"
        diff.append({
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "change_type": change_type,
        })
    return {"version_a": va, "version_b": vb, "diff": diff}


@app.get("/mdm/units/{unit_code}/versions/{version_id}")
async def get_mdm_unit_version(unit_code: str, version_id: str):
    """返回指定版本的快照数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    if store.get_unit(unit_code) is None:
        raise HTTPException(status_code=404, detail=f"单位 {unit_code} 不存在")
    version = store.get_unit_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"版本 {version_id} 不存在")
    if version.get("entity_id") != unit_code:
        raise HTTPException(status_code=400, detail="版本与单位不匹配")
    return version


@app.post("/mdm/units/{unit_code}/versions/{version_id}/activate")
async def activate_mdm_unit_version(unit_code: str, version_id: str):
    """激活旧版本：用旧版本快照数据覆盖当前 mdm.units 记录。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.activate_unit_version(unit_code, version_id)
    if item is None:
        raise HTTPException(status_code=404, detail="单位或版本不存在，或版本与单位不匹配")
    return item.model_dump()


@app.post("/mdm/unit-conversions")
async def create_mdm_unit_conversion(payload: dict = Body(...)):
    """创建单位换算规则（无 is_active 列，不提供 toggle）。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_unit_conversion(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.post("/mdm/standards")
async def create_mdm_standard(payload: dict = Body(...)):
    """创建方法标准主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_standard(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/standards/{standard_code}/active")
async def set_mdm_standard_active(standard_code: str, is_active: bool = Query(...)):
    """启用/停用方法标准。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_standard_active(standard_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/ghs-classes")
async def create_mdm_ghs_class(payload: dict = Body(...)):
    """创建 GHS 危害分类主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_ghs_class(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/ghs-classes/{ghs_code}/active")
async def set_mdm_ghs_class_active(ghs_code: str, is_active: bool = Query(...)):
    """启用/停用 GHS 危害分类。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_ghs_class_active(ghs_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/dimensions")
async def create_mdm_dimension(payload: dict = Body(...)):
    """创建通用维度主数据。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    try:
        item = store.create_dimension(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/dimensions/{domain}/{code}/active")
async def set_mdm_dimension_active(domain: str, code: str, is_active: bool = Query(...)):
    """启用/停用通用维度。"""
    store: ReferenceDictStore = app.state.reference_dict_store
    item = store.set_dimension_active(domain, code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


# ── P2 物料/样品类型/设备模板/位置 ───────────────────────
@app.post("/mdm/sample-types")
async def create_mdm_sample_type(payload: dict = Body(...)):
    """创建样品类型模板主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_sample_type(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/sample-types/{type_code}/active")
async def set_mdm_sample_type_active(type_code: str, is_active: bool = Query(...)):
    """启用/停用样品类型。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_sample_type_active(type_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/locations")
async def create_mdm_location(payload: dict = Body(...)):
    """创建位置主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_location(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/locations/{location_id}/active")
async def set_mdm_location_active(location_id: str, is_active: bool = Query(...)):
    """启用/停用位置。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_location_active(location_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/containers")
async def create_mdm_container(payload: dict = Body(...)):
    """创建容器与包装主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_container(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/containers/{container_code}/active")
async def set_mdm_container_active(container_code: str, is_active: bool = Query(...)):
    """启用/停用容器。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_container_active(container_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/logistics-types")
async def create_mdm_logistics_type(payload: dict = Body(...)):
    """创建物流类型主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_logistics_type(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/logistics-types/{type_code}/active")
async def set_mdm_logistics_type_active(type_code: str, is_active: bool = Query(...)):
    """启用/停用物流类型。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_logistics_type_active(type_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/equipment-templates")
async def create_mdm_equipment_template(payload: dict = Body(...)):
    """创建设备模板主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_equipment_template(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/equipment-templates/{template_code}/active")
async def set_mdm_equipment_template_active(template_code: str, is_active: bool = Query(...)):
    """启用/停用设备模板。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_equipment_template_active(template_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/equipment-capabilities")
async def create_mdm_equipment_capability(payload: dict = Body(...)):
    """创建设备能力主数据。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_equipment_capability(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/equipment-capabilities/{capability_code}/active")
async def set_mdm_equipment_capability_active(capability_code: str, is_active: bool = Query(...)):
    """启用/停用设备能力。"""
    store: MasterDataStore = app.state.master_data_store
    item = store.set_equipment_capability_active(capability_code, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/material-categories")
async def create_mdm_material_category(payload: dict = Body(...)):
    """创建物料分类治理主数据（无 is_active 列，不提供 toggle）。"""
    store: MasterDataStore = app.state.master_data_store
    try:
        item = store.create_material_category(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


# ── P3 CIMC：特性-指标-方法-能力 ────────────────────────
@app.post("/mdm/properties")
async def create_mdm_property(payload: dict = Body(...)):
    """创建特性主数据。"""
    store: CimcStore = app.state.cimc_store
    try:
        item = store.create_property(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/properties/{property_id}/active")
async def set_mdm_property_active(property_id: str, is_active: bool = Query(...)):
    """启用/停用特性。"""
    store: CimcStore = app.state.cimc_store
    item = store.set_property_active(property_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/test-methods")
async def create_mdm_test_method(payload: dict = Body(...)):
    """创建检测方法主数据。"""
    store: CimcStore = app.state.cimc_store
    try:
        item = store.create_test_method(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/test-methods/{method_id}/active")
async def set_mdm_test_method_active(method_id: str, is_active: bool = Query(...)):
    """启用/停用检测方法。"""
    store: CimcStore = app.state.cimc_store
    item = store.set_test_method_active(method_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/test-items")
async def create_mdm_test_item(payload: dict = Body(...)):
    """创建指标项目主数据。"""
    store: CimcStore = app.state.cimc_store
    try:
        item = store.create_test_item(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/test-items/{item_id}/active")
async def set_mdm_test_item_active(item_id: str, is_active: bool = Query(...)):
    """启用/停用指标项目。"""
    store: CimcStore = app.state.cimc_store
    item = store.set_test_item_active(item_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/specifications")
async def create_mdm_specification(payload: dict = Body(...)):
    """创建规格与判定主数据。"""
    store: CimcStore = app.state.cimc_store
    try:
        item = store.create_specification(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/specifications/{spec_id}/active")
async def set_mdm_specification_active(spec_id: str, is_active: bool = Query(...)):
    """启用/停用规格。"""
    store: CimcStore = app.state.cimc_store
    item = store.set_specification_active(spec_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/inspection-capabilities")
async def create_mdm_inspection_capability(payload: dict = Body(...)):
    """创建检查能力主数据。"""
    store: CimcStore = app.state.cimc_store
    try:
        item = store.create_inspection_capability(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/inspection-capabilities/{capability_id}/active")
async def set_mdm_inspection_capability_active(capability_id: str, is_active: bool = Query(...)):
    """启用/停用检查能力。"""
    store: CimcStore = app.state.cimc_store
    item = store.set_inspection_capability_active(capability_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


# ── P4 工艺路线-步骤-参数 ────────────────────────────────
@app.post("/mdm/process-routes")
async def create_mdm_process_route(payload: dict = Body(...)):
    """创建工艺路线模板主数据。"""
    store: ProcessStore = app.state.process_store
    try:
        item = store.create_process_route(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/process-routes/{route_id}/active")
async def set_mdm_process_route_active(route_id: str, is_active: bool = Query(...)):
    """启用/停用工艺路线。"""
    store: ProcessStore = app.state.process_store
    item = store.set_process_route_active(route_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/process-steps")
async def create_mdm_process_step(payload: dict = Body(...)):
    """创建工艺步骤模板主数据。"""
    store: ProcessStore = app.state.process_store
    try:
        item = store.create_process_step(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/process-steps/{step_id}/active")
async def set_mdm_process_step_active(step_id: str, is_active: bool = Query(...)):
    """启用/停用工艺步骤。"""
    store: ProcessStore = app.state.process_store
    item = store.set_process_step_active(step_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


@app.post("/mdm/process-parameters")
async def create_mdm_process_parameter(payload: dict = Body(...)):
    """创建工艺参数字典主数据。"""
    store: ProcessStore = app.state.process_store
    try:
        item = store.create_process_parameter(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/process-parameters/{parameter_id}/active")
async def set_mdm_process_parameter_active(parameter_id: str, is_active: bool = Query(...)):
    """启用/停用工艺参数。"""
    store: ProcessStore = app.state.process_store
    item = store.set_process_parameter_active(parameter_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


# ── P5 文档 ──────────────────────────────────────────────
@app.post("/mdm/documents")
async def create_mdm_document(payload: dict = Body(...)):
    """创建文档主数据。"""
    store: DocumentStore = app.state.document_store
    try:
        item = store.create_document(payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    return item.model_dump()


@app.patch("/mdm/documents/{document_id}/active")
async def set_mdm_document_active(document_id: str, is_active: bool = Query(...)):
    """启用/停用文档。"""
    store: DocumentStore = app.state.document_store
    item = store.set_document_active(document_id, is_active)
    if item is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item.model_dump()


# ===========================================================================
# AI 助手（Copilot）路由 — 右侧悬浮抽屉的薄封装后端
# 能力：会话 CRUD + 消息持久化 + NDJSON 流式对话（复用现有 LLM/Agent 薄封装）
# ===========================================================================
from fastapi.responses import StreamingResponse  # noqa: E402


def _get_ai_store():
    """惰性初始化 AiSessionStore（挂载在 app.state，避免 import 期依赖 DB）。"""
    if not hasattr(app.state, "ai_store"):
        app.state.ai_store = AiSessionStore()
    return app.state.ai_store


class AiCreateSessionRequest(BaseModel):
    """创建 AI 助手会话请求。"""
    title: str = "新会话"
    project_id: str = ""
    mode: str = "global"   # global / task（可聚焦）
    focus: dict = Field(default_factory=dict)    # 聚焦：{agent_id?, task?, ...}
    context: dict = Field(default_factory=dict)  # 当前页上下文感知 + @提及资源


class AiSendRequest(BaseModel):
    """发送 AI 消息请求。"""
    message: str = Field(..., min_length=1, max_length=8000)  # 超长消息会放大 prompt 并污染会话
    context: dict = Field(default_factory=dict)  # 本次消息附带的页面上下文/@提及


@app.post("/ai/sessions")
async def ai_create_session(req: AiCreateSessionRequest, user: User = Depends(require_login)):
    """创建 AI 助手会话（user_id 隔离 + project_id 项目隔离）。"""
    store = _get_ai_store()
    return store.create_session(
        user_id=user.user_id,
        project_id=req.project_id,
        title=req.title,
        mode=req.mode,
        focus=req.focus,
        context=req.context,
    )


@app.get("/ai/sessions")
async def ai_list_sessions(
    user: User = Depends(require_login),
    project_id: str = "",
    limit: int = Query(default=50, ge=1, le=200),
):
    """列出当前用户会话；project_id 非空时做项目隔离。"""
    store = _get_ai_store()
    sessions = store.list_sessions(user_id=user.user_id, project_id=project_id, limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.delete("/ai/sessions/{session_id}")
async def ai_delete_session(session_id: str, user: User = Depends(require_login)):
    """删除会话及其全部消息（仅限本人）。"""
    store = _get_ai_store()
    session = store.get_session(session_id)
    if session is None or session["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    store.delete_session(session_id)
    return {"ok": True}


@app.get("/ai/sessions/{session_id}/messages")
async def ai_list_messages(
    session_id: str,
    user: User = Depends(require_login),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """列出会话消息（仅限本人）。"""
    store = _get_ai_store()
    session = store.get_session(session_id)
    if session is None or session["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = store.list_messages(session_id, limit=limit)
    return {"messages": messages, "count": len(messages)}


class AiFeedbackRequest(BaseModel):
    """消息反馈请求。"""
    value: int = Field(..., ge=-1, le=1)  # 1 有帮助 / -1 没帮助 / 0 取消


@app.post("/ai/messages/{message_id}/feedback")
async def ai_message_feedback(message_id: str, req: AiFeedbackRequest, user: User = Depends(require_login)):
    """持久化单条消息的用户反馈（仅限本人会话内的消息）。"""
    store = _get_ai_store()
    msg = store.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    session = store.get_session(msg["session_id"])
    if session is None or session["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    store.update_message_feedback(message_id, req.value)
    return {"ok": True, "value": req.value}


def _build_copilot_messages(session: dict) -> list[dict]:
    """构造 Copilot 对话消息：system（人设 + 上下文 + 聚焦）+ 历史 + 当前问题。

    薄封装：聚焦 agent 时沿用该 agent 人设；否则为通用研发助手。
    """
    focus = session.get("focus") or {}
    context = session.get("context") or {}
    system_parts = [
        "你是「MaterialsPEML」新材料研发平台内置的 AI 研发助手（Copilot）。",
        "能力边界：默认可读当前页面上下文与平台数据；涉及执行/写入操作时需得到用户确认，不擅自改动平台数据。",
        "回复要求：简洁、专业、使用中文；引用平台数据时标注来源；不确定时明确说明，不臆造。",
    ]
    # 聚焦模式：有 agent_id 时以该智能体人设作答
    agent = None
    if focus.get("agent_id") and _registry is not None:
        agent = _registry.get_agent(focus["agent_id"])
    if agent:
        persona = f"你是「{agent.name}」。{agent.description or ''}"
        if getattr(agent, "expertise", None):
            persona += f"。专长领域：{'、'.join(agent.expertise)}"
        system_parts[0] = persona
    if focus.get("task"):
        system_parts.append(f"当前聚焦任务：{focus['task']}")
    # 当前页面上下文
    page = context.get("page") or {}
    if page:
        system_parts.append(
            f"当前页面上下文：页面={page.get('title', '')}（路径 {page.get('path', '')}），"
            f"描述={page.get('description', '')}"
        )
    if context.get("project"):
        system_parts.append(f"当前项目：{context['project']}")
    mentions = context.get("mentions") or []
    if mentions:
        desc = "；".join(
            f"[{m.get('type', '资源')}] {m.get('name', '')}：{(m.get('snippet') or '')[:120]}"
            for m in mentions[:5]
        )
        system_parts.append(f"用户提及的资源：{desc}")
    return [{"role": "system", "content": "\n".join(system_parts)}]


def _build_conv_messages(
    session: dict,
    history: list[dict],
    current_user_msg_id: str,
    current_message: str,
) -> list[dict]:
    """构造 Copilot 对话消息：system + 历史（最近 20 条）+ 当前问题。

    关键：当前用户消息已先写入存储并出现在 history 中，必须按 message_id 排除，
    否则会在 prompt 中重复出现（修复回归点）。
    """
    messages = _build_copilot_messages(session)
    for m in history[-20:]:
        if m["message_id"] == current_user_msg_id:
            continue
        if m["role"] in ("user", "assistant") and m["content"]:
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": current_message})
    return messages


def _resolve_attempts(session: dict) -> list[tuple[str, str | None, str]]:
    """解析 LLM 调用链尝试序列：聚焦 agent 时双模型；否则 通用 LLM → InternLM 回退。

    通用分支必须返回 ("llm", None) 而非 ("", None)，否则 _call_llm_provider 会把
    空 provider 解析为 internlm，导致回退链失效（修复回归点）。
    """
    focus = session.get("focus") or {}
    attempts: list[tuple[str, str | None, str]] = []
    if focus.get("agent_id") and _registry is not None:
        agent = _registry.get_agent(focus["agent_id"])
        if agent:
            attempts = [(agent.provider, agent.llm_model, agent.name)]
            if agent.provider_secondary:
                attempts.append((agent.provider_secondary, agent.llm_model_secondary, agent.name))
    if not attempts:
        attempts = [("llm", None, ""), ("internlm", None, "")]
    return attempts


@app.post("/ai/sessions/{session_id}/messages")
async def ai_send_message(session_id: str, req: AiSendRequest, user: User = Depends(require_login)):
    """发送一条消息并流式返回回复（NDJSON：start / delta / done / error）。

    薄封装：优先复用现有 LLM/Agent 双模型调用链；聚焦 agent 时以其人设作答，
    否则为通用 Copilot（通用 LLM 失败自动回退 InternLM）。
    """
    store = _get_ai_store()
    session = store.get_session(session_id)
    if session is None or session["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    cfg = get_config()
    # 会话维度 context 与本次消息 context 合并（本次优先）
    merged_context = {**(session.get("context") or {}), **(req.context or {})}
    session["context"] = merged_context

    user_msg = store.add_message(session_id, "user", req.message)
    asst_msg = store.add_message(session_id, "assistant", "", status="streaming")

    # 构造消息（system + 历史去重 + 当前问题）与调用链尝试序列（见纯函数 _build_conv_messages / _resolve_attempts）
    history = store.list_messages(session_id, limit=200)
    messages = _build_conv_messages(session, history, user_msg["message_id"], req.message)
    attempts = _resolve_attempts(session)

    async def _stream_reply():
        """生成器：start →（回填完成后 分块 delta）→ done；异常时发 error。

        说明：当前为薄封装对话，回复在 provider 侧同步完成后分块回放（打字机效果），
        NDJSON 传输层确实是流式的；未做 token 级增量生成（需 provider 支持流式接口）。
        meta 不含置信度——无真实信号支撑时不下发无依据的数值化置信度。
        """
        try:
            yield json.dumps({"type": "start", "message_id": asst_msg["message_id"]}, ensure_ascii=False) + "\n"
        except Exception:
            logger.warning("AI 助手：发送 start 事件失败（连接可能已断开）")
            return
        meta = {
            "provider": "",
            "model": "",
            "fallback_used": False,
            "duration_ms": 0,
            "sources": [],
            "chips": [],
        }
        t0 = time.monotonic()
        reply = ""
        provider = ""
        actual_model = ""
        fallback_used = False
        last_error = ""
        for idx, (prov, mdl, _agent_name) in enumerate(attempts):
            try:
                reply = await _call_llm_provider(prov, mdl, messages, cfg)
                provider = (prov or "").lower() or ("llm" if mdl else "internlm")
                actual_model = mdl or provider
                fallback_used = idx > 0
                break
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning("AI 助手：第 %d 次尝试失败（%s）", idx + 1, last_error)
                if idx == 0 and len(attempts) > 1:
                    continue
                # 全部尝试失败
                store.update_message_status(asst_msg["message_id"], "error")
                try:
                    yield json.dumps(
                        {"type": "error", "message_id": asst_msg["message_id"], "detail": f"对话失败（{last_error}）"},
                        ensure_ascii=False,
                    ) + "\n"
                except Exception:
                    logger.warning("AI 助手：发送 error 事件失败（连接可能已断开）")
                return
        duration_ms = int((time.monotonic() - t0) * 1000)
        # 回填完整回复
        store.update_message_status(asst_msg["message_id"], "done", reply)
        meta.update({
            "provider": provider,
            "model": actual_model,
            "fallback_used": fallback_used,
            "duration_ms": duration_ms,
        })
        # 分块发送（打字机效果）
        chunk_size = 24
        for i in range(0, len(reply), chunk_size):
            piece = reply[i : i + chunk_size]
            try:
                yield json.dumps({"type": "delta", "content": piece}, ensure_ascii=False) + "\n"
            except Exception:
                logger.warning("AI 助手：发送 delta 事件中断（连接可能已断开）")
                break
        # 仅当会话仍是默认标题时，用首条消息作为标题，避免后续消息污染会话名
        default_title = (session.get("title") or "").strip() in ("", "新会话")
        store.touch_session(session_id, title=req.message[:40] if default_title else None)
        try:
            yield json.dumps(
                {"type": "done", "message_id": asst_msg["message_id"], "reply": reply, "meta": meta},
                ensure_ascii=False,
            ) + "\n"
        except Exception:
            logger.warning("AI 助手：发送 done 事件失败（连接可能已断开）")
            pass

    return StreamingResponse(
        _stream_reply(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 报表导出 / 定时报表（report.export 权限） ──

class ReportExportRequest(BaseModel):
    format: str
    report_type: str
    title: str | None = None


class ReportScheduleRequest(BaseModel):
    report_type: str
    format: str
    cron_expr: str = "daily"
    owner: str | None = None


@app.post("/report/export", dependencies=[Depends(require_permission("report.export"))])
async def report_export(
    req: ReportExportRequest,
    current: User | None = Depends(get_current_user),
):
    """导出指定类型的报表（Excel/PDF），并记录导出审计。"""
    if req.format not in VALID_FORMATS:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {req.format}")
    if req.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的报表类型: {req.report_type}")
    data = build_report({"report_type": req.report_type})
    title = req.title or data["title"]
    if req.format == "excel":
        content = export_excel(data["rows"], data["columns"])
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        content = export_pdf(data["rows"], data["columns"], title)
        media_type = "application/pdf"
        ext = "pdf"
    operator = current.user_id if current else "system"
    get_audit_logger().log(AuditEntry(
        event_type="data_change",
        module="report",
        action="export",
        operator=operator,
        user_id=operator,
        resource_type="report",
        resource_id=f"{req.report_type}:{req.format}",
        detail={"title": title, "rows": len(data["rows"])},
    ))
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="report.{ext}"'},
    )


@app.get("/report/last", dependencies=[Depends(require_permission("report.export"))])
async def report_last():
    """返回最近一次报表导出记录，无则返回 {empty: true}。"""
    page = get_audit_logger().query_paged(module="report", action="export", page=1, page_size=1)
    items = page.get("items") or []
    if not items:
        return {"empty": True}
    entry = items[0]
    rid = entry.get("resource_id") or ""
    parts = rid.split(":")
    return {
        "type": parts[0] if parts else "",
        "format": parts[1] if len(parts) > 1 else "",
        "operator": entry.get("operator"),
        "created_at": entry.get("created_at"),
    }


@app.post("/report/schedule", dependencies=[Depends(require_permission("report.export"))])
async def report_schedule(
    req: ReportScheduleRequest,
    current: User | None = Depends(get_current_user),
):
    """注册一个持久化定时报表（APScheduler + PostgreSQL，重启后恢复）。"""
    try:
        result = schedule_report({
            "report_type": req.report_type,
            "format": req.format,
            "cron_expr": req.cron_expr,
            "owner": req.owner or (current.user_id if current else "system"),
            "tenant_id": get_tenant(),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(request: Request, full_path: str):
        # rewrite_api_prefix_middleware 重写后，未匹配到已注册路由的 API 请求
        # 会落到此处；通过 scope 上的 is_api_request 标记识别并返回 404 JSON，
        # 避免被误当作 SPA 路由返回 index.html。错误信息含原始路径便于排查。
        if request.scope.get("is_api_request"):
            original = request.scope.get("__api_original_path") or request.url.path
            raise HTTPException(status_code=404, detail=f"请求的接口不存在: {original}")
        # 路径遍历防护：解析后必须仍位于 _frontend_dist 内
        safe_root = _frontend_dist.resolve()
        target = (_frontend_dist / full_path).resolve()
        try:
            target.relative_to(safe_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="资源不存在")
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(_frontend_index))

    @app.api_route(
        "/{full_path:path}",
        methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def api_fallback_non_get(request: Request, full_path: str):
        """非 GET 请求的兜底：避免未匹配的 API 请求暴露 405 'Method Not Allowed'。

        SPA 页面路由只支持 GET；对 /api/ 下的非 GET 请求返回 404 JSON，
        前端错误拦截层会将其转译为用户可读提示。非 API 路径返回 405。
        """
        if request.scope.get("is_api_request"):
            original = request.scope.get("__api_original_path") or request.url.path
            raise HTTPException(status_code=404, detail=f"请求的接口不存在或暂未开放: {original}")
        raise HTTPException(status_code=405, detail="Method Not Allowed")
