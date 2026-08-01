"""P1 seed 修正：让 MDM 主数据与业务代码枚举值完全一致。

修正内容：
1. ProjectTask.status：in_progress → active
2. IdeaStatus：完全替换为代码的 6 个值
3. CaseStatus：完全替换为代码的 10 个值
4. RunStatus：完全替换为代码的 9 个值
5. UserRole：ADMIN/PROJECT_MANAGER/... → admin/pm/...
6. EquipmentStatus：IDLE/IN_USE/... → idle/in_use/...
7. 温度单位：统一 unit_code=C，symbol=°C

同时补充业务代码中存在但 MDM 缺失的 domain：
- project_stage / execution_mode / qc_status / data_source_type
- storage_condition / agent_role / autonomy_level / version_type
- cost_category / material_request_type / data_source

Revision ID: 0016_mdm_seed_fix
Revises: 0015_mdm_p5_fk_lineage
Create Date: 2026-07-27

详见 .trae/specs/mdm-governance/spec.md
"""
from __future__ import annotations

from alembic import op

revision = "0016_mdm_seed_fix"
down_revision = "0015_mdm_p5_fk_lineage"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    _fix_task_status()
    _fix_idea_status()
    _fix_case_status()
    _fix_run_status()
    _fix_user_role()
    _fix_equipment_status()
    _fix_temperature_unit()
    _seed_missing_dimensions()


# ──────────────────────────────────────────────────────────────────────────────
# downgrade：数据修正不可逆，仅占位
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    """seed 数据修正不可逆，不恢复原值。"""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# 1. ProjectTask.status：in_progress → active
# ──────────────────────────────────────────────────────────────────────────────
def _fix_task_status() -> None:
    """修正 task domain：in_progress → active，与代码 ProjectTask.status 一致。"""
    # 删除错误的 in_progress，插入正确的 active
    op.execute(
        "DELETE FROM mdm.status_codes WHERE code_id = 'task.in_progress'"
    )
    op.execute(
        "INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        "VALUES ('task.active', 'task', 'active', '进行中', 20, TRUE, '') "
        "ON CONFLICT (code_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. IdeaStatus：完全替换为代码的 6 个值
# ──────────────────────────────────────────────────────────────────────────────
def _fix_idea_status() -> None:
    """修正 idea domain：与代码 IdeaStatus 完全一致。"""
    # 删除旧的 5 个值
    op.execute("DELETE FROM mdm.status_codes WHERE domain = 'idea'")
    # 插入代码实际的 6 个值
    rows = [
        ("idea.draft",      "idea", "draft",      "草稿",     10),
        ("idea.verifying",  "idea", "verifying",  "验证中",   20),
        ("idea.verified",   "idea", "verified",   "已验证",   30),
        ("idea.failed",     "idea", "failed",     "验证失败", 40),
        ("idea.preferred",  "idea", "preferred",  "优选",     50),
        ("idea.eliminated", "idea", "eliminated", "淘汰",     60),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. CaseStatus：完全替换为代码的 10 个值
# ──────────────────────────────────────────────────────────────────────────────
def _fix_case_status() -> None:
    """修正 case domain：与代码 CaseStatus 完全一致。"""
    op.execute("DELETE FROM mdm.status_codes WHERE domain = 'case'")
    rows = [
        ("case.pending",            "case", "pending",            "待处理",         10),
        ("case.thinking",           "case", "thinking",           "思考中",         20),
        ("case.executing_evidence", "case", "executing_evidence", "执行证据收集",   30),
        ("case.verifying",          "case", "verifying",          "验证中",         40),
        ("case.pass",               "case", "pass",               "通过",           50),
        ("case.reject",             "case", "reject",             "拒绝",           60),
        ("case.request_evidence",   "case", "request_evidence",   "请求人工证据",   70),
        ("case.human_review",       "case", "human_review",       "人工复审",       80),
        ("case.failed",             "case", "failed",             "失败",           90),
        ("case.cancelled",          "case", "cancelled",          "已取消",        100),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. RunStatus：完全替换为代码的 9 个值
# ──────────────────────────────────────────────────────────────────────────────
def _fix_run_status() -> None:
    """修正 run domain：与代码 RunStatus 完全一致。"""
    op.execute("DELETE FROM mdm.status_codes WHERE domain = 'run'")
    rows = [
        ("run.queued",            "run", "queued",            "排队中",       10),
        ("run.running",           "run", "running",           "运行中",       20),
        ("run.waiting_external",  "run", "waiting_external",  "等待外部资源", 30),
        ("run.waiting_human",     "run", "waiting_human",     "等待人工介入", 40),
        ("run.paused_budget",     "run", "paused_budget",     "预算暂停",     50),
        ("run.recovery_required", "run", "recovery_required", "需恢复",       60),
        ("run.succeeded",         "run", "succeeded",         "成功",         70),
        ("run.failed",            "run", "failed",            "失败",         80),
        ("run.cancelled",         "run", "cancelled",         "已取消",       90),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. UserRole：ADMIN/PROJECT_MANAGER/... → admin/pm/...
# ──────────────────────────────────────────────────────────────────────────────
def _fix_user_role() -> None:
    """修正 role domain：与代码 UserRole 完全一致（小写短名）。"""
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'role'")
    rows = [
        ("role.admin",      "role", "admin",      "系统管理员", 40),
        ("role.pm",         "role", "pm",         "项目经理",   30),
        ("role.researcher", "role", "researcher", "研究员",     20),
        ("role.reviewer",   "role", "reviewer",   "审核员",     10),
        ("role.viewer",     "role", "viewer",     "只读访客",    0),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 6. EquipmentStatus：IDLE/IN_USE/... → idle/in_use/...
# ──────────────────────────────────────────────────────────────────────────────
def _fix_equipment_status() -> None:
    """修正 equipment domain：与代码 EquipmentStatus 完全一致（小写）。"""
    op.execute("DELETE FROM mdm.status_codes WHERE domain = 'equipment'")
    rows = [
        ("equipment.idle",        "equipment", "idle",        "空闲",     10),
        ("equipment.in_use",      "equipment", "in_use",      "在用",     20),
        ("equipment.maintenance", "equipment", "maintenance", "维护中",   30),
        ("equipment.calibration", "equipment", "calibration", "校准中",   40),
        ("equipment.retired",     "equipment", "retired",     "已退役",   50),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 7. 温度单位：统一 unit_code=C，symbol=°C
# ──────────────────────────────────────────────────────────────────────────────
def _fix_temperature_unit() -> None:
    """修正温度单位：unit_code 保持 C，symbol 设为 °C。

    业务代码中 material_properties.py 用 '°C'，这里统一 unit_code='C'，
    前端展示用 symbol 字段（°C）。后续阶段3会修正 material_properties.py 改用 'C'。
    """
    # 如果存在 unit_code='°C' 的记录，合并到 'C'
    op.execute(
        "DELETE FROM mdm.units WHERE unit_code = '°C'"
    )
    # 确保 C 的 symbol 是 °C
    op.execute(
        "UPDATE mdm.units SET symbol = '°C', name = '摄氏度' WHERE unit_code = 'C'"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 8. 补充业务代码中存在但 MDM 缺失的 domain
# ──────────────────────────────────────────────────────────────────────────────
def _seed_missing_dimensions() -> None:
    """补充缺失的 domain 数据。"""
    # ── project_stage：项目阶段 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'project_stage'")
    rows = [
        ("project_stage.initiation", "project_stage", "立项", "立项",   10),
        ("project_stage.screening",  "project_stage", "筛选", "筛选",   20),
        ("project_stage.pilot",      "project_stage", "中试", "中试",   30),
        ("project_stage.verification", "project_stage", "验证", "验证", 40),
        ("project_stage.finalization", "project_stage", "定型", "定型", 50),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── execution_mode：执行模式 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'execution_mode'")
    rows = [
        ("execution_mode.auto_device",      "execution_mode", "AUTO_DEVICE",     "自动设备",     10),
        ("execution_mode.semi_auto",        "execution_mode", "SEMI_AUTO",       "半自动",       20),
        ("execution_mode.external_lims",    "execution_mode", "EXTERNAL_LIMS",   "外部LIMS",     30),
        ("execution_mode.external_ln",      "execution_mode", "EXTERNAL_LN",     "外部ELN",      40),
        ("execution_mode.manual_entry",     "execution_mode", "MANUAL_ENTRY",    "手动录入",     50),
        ("execution_mode.simulation_only",  "execution_mode", "SIMULATION_ONLY", "仅仿真",       60),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── qc_status：质检状态 ──────────────────────────────
    op.execute("DELETE FROM mdm.status_codes WHERE domain = 'qc_status'")
    rows = [
        ("qc_status.pending",             "qc_status", "PENDING",            "待处理",       10),
        ("qc_status.valid",               "qc_status", "VALID",              "有效",         20),
        ("qc_status.valid_with_warning",  "qc_status", "VALID_WITH_WARNING", "有效(有警告)", 30),
        ("qc_status.invalid",             "qc_status", "INVALID",            "无效",         40),
        ("qc_status.requires_review",     "qc_status", "REQUIRES_REVIEW",    "需复审",       50),
        ("qc_status.rejected",            "qc_status", "REJECTED",           "已拒绝",       60),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )

    # ── data_source_type：数据来源类型 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'data_source_type'")
    rows = [
        ("data_source_type.manual_entry", "data_source_type", "MANUAL_ENTRY", "手动录入", 10),
        ("data_source_type.csv_import",   "data_source_type", "CSV_IMPORT",   "CSV导入",  20),
        ("data_source_type.excel_import", "data_source_type", "EXCEL_IMPORT", "Excel导入", 30),
        ("data_source_type.api_push",     "data_source_type", "API_PUSH",     "API推送",  40),
        ("data_source_type.device",       "data_source_type", "DEVICE",       "设备",     50),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── storage_condition：存储条件 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'storage_condition'")
    rows = [
        ("storage_condition.room_temp",      "storage_condition", "常温",     "常温",       10),
        ("storage_condition.cold",           "storage_condition", "冷藏",     "冷藏",       20),
        ("storage_condition.frozen",         "storage_condition", "冷冻",     "冷冻",       30),
        ("storage_condition.inert_atmos",    "storage_condition", "惰性气氛", "惰性气氛",   40),
        ("storage_condition.dark",           "storage_condition", "避光",     "避光",       50),
        ("storage_condition.dry",            "storage_condition", "干燥",     "干燥",       60),
        ("storage_condition.vacuum",         "storage_condition", "真空",     "真空",       70),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── agent_role：智能体角色 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'agent_role'")
    rows = [
        ("agent_role.material_discovery",   "agent_role", "material_discovery",   "材料发现",   10),
        ("agent_role.synthesis_planning",   "agent_role", "synthesis_planning",   "合成规划",   20),
        ("agent_role.dft_verification",     "agent_role", "dft_verification",     "DFT验证",    30),
        ("agent_role.experiment_analysis",  "agent_role", "experiment_analysis",  "实验分析",   40),
        ("agent_role.project_manager",      "agent_role", "project_manager",      "项目管理",   50),
        ("agent_role.literature_research",  "agent_role", "literature_research",  "文献调研",   60),
        ("agent_role.quality_review",       "agent_role", "quality_review",       "质量评审",   70),
        ("agent_role.industrialization",    "agent_role", "industrialization",    "产业化",     80),
        ("agent_role.custom",               "agent_role", "custom",               "自定义",     90),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── autonomy_level：自治级别 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'autonomy_level'")
    rows = [
        ("autonomy_level.l0", "autonomy_level", "L0", "L0-人工", 10),
        ("autonomy_level.l1", "autonomy_level", "L1", "L1-辅助", 20),
        ("autonomy_level.l2", "autonomy_level", "L2", "L2-半自治", 30),
        ("autonomy_level.l3", "autonomy_level", "L3", "L3-全自治", 40),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── version_type：版本类型 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'version_type'")
    rows = [
        ("version_type.material",  "version_type", "material",  "材料版本",   10),
        ("version_type.workflow",  "version_type", "workflow",  "工作流版本", 20),
        ("version_type.knowledge", "version_type", "knowledge", "知识版本",   30),
        ("version_type.formula",   "version_type", "formula",   "配方版本",   40),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── cost_category：成本类别 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'cost_category'")
    rows = [
        ("cost_category.material",     "cost_category", "material",     "物料成本",   10),
        ("cost_category.equipment",    "cost_category", "equipment",    "设备成本",   20),
        ("cost_category.labor",        "cost_category", "labor",        "人工成本",   30),
        ("cost_category.outsourced",   "cost_category", "outsourced",   "外协成本",   40),
        ("cost_category.energy",       "cost_category", "energy",       "能源成本",   50),
        ("cost_category.waste",        "cost_category", "waste",        "废料成本",   60),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── material_request_type：物料申请类型 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'material_request_type'")
    rows = [
        ("material_request_type.add",    "material_request_type", "add",    "新增", 10),
        ("material_request_type.update", "material_request_type", "update", "更新", 20),
        ("material_request_type.delete", "material_request_type", "delete", "删除", 30),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── data_source：数据来源（measured/predicted）──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'data_source'")
    rows = [
        ("data_source.measured",  "data_source", "measured",  "实测", 10),
        ("data_source.predicted", "data_source", "predicted", "预测", 20),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── sample_source_type：样品来源类型 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'sample_source_type'")
    rows = [
        ("sample_source_type.synthesis", "sample_source_type", "synthesis", "合成",   10),
        ("sample_source_type.purchase",  "sample_source_type", "purchase",  "采购",   20),
        ("sample_source_type.candidate", "sample_source_type", "candidate", "候选",   30),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── committee_type：委员会类型 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'committee_type'")
    rows = [
        ("committee_type.crystal_construction",   "committee_type", "crystal_construction",   "晶体构建",     10),
        ("committee_type.experimental_readiness", "committee_type", "experimental_readiness", "实验就绪",     20),
        ("committee_type.candidate_priority",     "committee_type", "candidate_priority",     "候选优先级",   30),
        ("committee_type.deviation_review",       "committee_type", "deviation_review",       "偏差评审",     40),
        ("committee_type.external_evidence",      "committee_type", "external_evidence",      "外部证据",     50),
        ("committee_type.candidate_quality",      "committee_type", "candidate_quality",      "候选质量",     60),
        ("committee_type.system_health",          "committee_type", "system_health",          "系统健康",     70),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── evidence_source：证据来源 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'evidence_source'")
    rows = [
        ("evidence_source.local_tool",  "evidence_source", "local_tool",  "本地工具", 10),
        ("evidence_source.model",       "evidence_source", "model",       "模型",     20),
        ("evidence_source.scp",         "evidence_source", "scp",         "SCP",      30),
        ("evidence_source.database",    "evidence_source", "database",    "数据库",   40),
        ("evidence_source.experiment",  "evidence_source", "experiment",  "实验",     50),
        ("evidence_source.human",       "evidence_source", "human",       "人工",     60),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )

    # ── trigger_code：触发码 ──────────────────────────────
    op.execute("DELETE FROM mdm.dimensions WHERE domain = 'trigger_code'")
    rows = [
        ("trigger_code.crystal_generated",          "trigger_code", "crystal_generated",          "晶体已生成",       10),
        ("trigger_code.crystal_conflict",           "trigger_code", "crystal_conflict",           "晶体冲突",         20),
        ("trigger_code.dft_resource_scarce",        "trigger_code", "dft_resource_scarce",        "DFT资源紧张",      30),
        ("trigger_code.experiment_new",             "trigger_code", "experiment_new",             "新实验",           40),
        ("trigger_code.prediction_conflict",        "trigger_code", "prediction_conflict",        "预测冲突",         50),
        ("trigger_code.external_conflict",          "trigger_code", "external_conflict",          "外部冲突",         60),
        ("trigger_code.experiment_deviation",       "trigger_code", "experiment_deviation",       "实验偏差",         70),
        ("trigger_code.candidate_quality_invalid",  "trigger_code", "candidate_quality_invalid",  "候选质量无效",     80),
        ("trigger_code.synthesis_service_failure",  "trigger_code", "synthesis_service_failure",  "合成服务失败",     90),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )
