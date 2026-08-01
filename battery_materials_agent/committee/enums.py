from enum import Enum


class CommitteeType(str, Enum):
    CRYSTAL_CONSTRUCTION = "crystal_construction"
    EXPERIMENTAL_READINESS = "experimental_readiness"
    CANDIDATE_PRIORITY = "candidate_priority"
    DEVIATION_REVIEW = "deviation_review"
    EXTERNAL_EVIDENCE = "external_evidence"
    # P1-2 触发条件B：候选材料化学式/数据质量未通过校验
    CANDIDATE_QUALITY = "candidate_quality"
    # P1-2 触发条件C：关键服务（如 ASKCOS）连续失败引发的系统健康告警
    SYSTEM_HEALTH = "system_health"
    # T-031 触发条件D：高风险 AI 操作（物理执行/资源消耗类）需人工确认
    HIGH_RISK_AI_ACTION = "high_risk_ai_action"


class CaseStatus(str, Enum):
    PENDING = "pending"
    THINKING = "thinking"
    EXECUTING_EVIDENCE = "executing_evidence"
    VERIFYING = "verifying"
    PASS = "pass"
    REJECT = "reject"
    REQUEST_EVIDENCE = "request_evidence"
    HUMAN_REVIEW = "human_review"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Decision(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    REQUEST_EVIDENCE = "request_evidence"
    HUMAN_REVIEW = "human_review"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceSource(str, Enum):
    LOCAL_TOOL = "local_tool"
    MODEL = "model"
    SCP = "scp"
    DATABASE = "database"
    EXPERIMENT = "experiment"
    HUMAN = "human"


class TriggerCode(str, Enum):
    CRYSTAL_GENERATED = "crystal_generated"
    CRYSTAL_CONFLICT = "crystal_conflict"
    DFT_RESOURCE_SCARCE = "dft_resource_scarce"
    EXPERIMENT_NEW = "experiment_new"
    PREDICTION_CONFLICT = "prediction_conflict"
    EXTERNAL_CONFLICT = "external_conflict"
    EXPERIMENT_DEVIATION = "experiment_deviation"
    # P1-2 触发条件B：AI 生成候选未通过化学式/SMILES 合法性校验
    CANDIDATE_QUALITY_INVALID = "candidate_quality_invalid"
    # P1-2 触发条件C：合成路径规划服务连续失败超过阈值
    SYNTHESIS_SERVICE_FAILURE = "synthesis_service_failure"
    # T-031 触发条件D：高风险 AI 操作（自动创建实验任务单/放行样品/发布配方/下单采购）
    HIGH_RISK_AI_ACTION = "high_risk_ai_action"