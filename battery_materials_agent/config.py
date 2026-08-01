"""Central configuration for the battery materials agent."""

from __future__ import annotations
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr

from .db import DatabaseConfig


# 项目根目录（本文件所在 package 的上级目录），所有相对路径的锚点
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class EngineMode(str, Enum):
    LEGACY = "legacy"
    INTERNLM = "internlm"
    # NOTE: 'logos' is intentionally NOT declared as a member so that
    # EngineMode("logos") falls through to _missing_, which maps it to
    # INTERNLM with a deprecation warning. Declaring LOGOS = "logos" here
    # would short-circuit _missing_ and break the migration path.

    def __str__(self) -> str:
        return self.value

    @classmethod
    def _missing_(cls, value):
        """兼容旧值 logos -> internlm（带弃用提示）"""
        if isinstance(value, str) and value.lower() == "logos":
            import warnings
            warnings.warn(
                "EngineMode 'logos' is deprecated and has been mapped to 'internlm'. "
                "Update your configuration to ENGINE_MODE=internlm.",
                DeprecationWarning,
                stacklevel=2,
            )
            return cls.INTERNLM
        return None


class ExecutionProfile(str, Enum):
    """后端内部执行策略标签，由系统按场景自动选择，不再向研发用户暴露切换。"""

    STANDARD = "standard"
    INTERNLM_ASSISTED = "internlm_assisted"
    COMMITTEE_GOVERNED = "committee_governed"

    def __str__(self) -> str:
        return self.value


def engine_mode_to_execution_profile(engine_mode: EngineMode | str) -> ExecutionProfile:
    """将旧 EngineMode 映射为 ExecutionProfile。"""
    if isinstance(engine_mode, str):
        engine_mode = EngineMode(engine_mode)  # 触发 _missing_ 兼容
    if engine_mode == EngineMode.LEGACY:
        return ExecutionProfile.STANDARD
    if engine_mode == EngineMode.INTERNLM:
        return ExecutionProfile.INTERNLM_ASSISTED
    return ExecutionProfile.STANDARD  # 默认


class RunMode(str, Enum):
    DEMO = "demo"
    PRODUCTION = "production"

    def __str__(self) -> str:
        return self.value


DEFAULT_SCP_BINDING_NAMES = [
    "scp_scitool_chem",
    "scp_scigraph_material",
    "scp_scitool_mat",
    "scp_chem_reaction",
    "scp_origene_pubchem",
    "scp_origene_chembl",
    "scp_materials_mechanics",
]


class MaterialsProjectConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.materialsproject.org"
    cache_dir: Path = Path("data/mp_cache")
    gnome_use_mp_mirror: bool = True  # 通过 MP 镜像查询 GNoME 数据
    gnome_data_dir: Path = Path("data/gnome")  # 本地 GNoME 静态数据集目录


class ASKCOSConfig(BaseModel):
    base_url: str = "http://localhost:5000"
    timeout: int = 60


class MiddlewareConfig(BaseModel):
    db_url: str = "sqlite:///data/experiment_data.db"
    watch_dirs: list[str] = Field(default_factory=list)
    poll_interval: int = 5


class LLMConfig(BaseModel):
    api_key: str = ""
    model: str = "LongCat-2.0"
    base_url: str = "https://api.longcat.chat/openai"
    max_tokens: int = 128000  # 128K tokens max output
    context_window: int = 1000000  # 1M tokens context
    temperature: float = 0.8


class LogosConfig(BaseModel):
    """保留兼容：已弃用，请使用 InternLMConfig。"""
    base_url: str = "http://localhost:8080/v1"
    model_name: str = "logos-1b"
    api_key: str = ""
    timeout: int = 60


class InternLMConfig(BaseModel):
    enabled: bool = True
    base_url: str = "https://chat.intern-ai.org.cn/api/v1"
    api_key: SecretStr | None = None
    model: str = "intern-s2-preview-397b"
    timeout_seconds: float = 90.0
    connect_timeout_seconds: float = 10.0
    max_retries: int = 2
    thinking_mode: bool = True
    max_concurrency: int = 4
    json_repair_retries: int = 1


class SCPConfig(BaseModel):
    enabled: bool = False
    base_url: str = "https://scp.intern-ai.org.cn/api/v1/mcp"
    api_key: SecretStr | None = None
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    max_retries: int = 1
    max_concurrency: int = 6
    allowed_servers: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    tool_overrides: dict[str, dict] = Field(default_factory=dict)
    # key: internal_name, value: 是否启用；用于覆盖 catalog 中默认绑定状态
    binding_enabled: dict[str, bool] = Field(default_factory=dict)

    def apply_binding_overrides(self, catalog: "SCPCatalog") -> None:
        """根据环境变量覆盖 SCP catalog 中对应绑定的启用状态。"""
        for name, enabled in self.binding_enabled.items():
            binding = catalog.get(name)
            if binding is not None:
                binding.enabled = enabled


class CommitteeMode(str, Enum):
    OBSERVE = "observe"
    ENFORCE = "enforce"

    def __str__(self) -> str:
        return self.value


class CommitteeConfig(BaseModel):
    enabled: bool = False
    default_mode: CommitteeMode = CommitteeMode.OBSERVE
    max_evidence_rounds: int = 2
    max_parallel_evidence_tasks: int = 4
    case_timeout_seconds: int = 300
    crystal_enabled: bool = True
    experiment_enabled: bool = True
    candidate_priority_enabled: bool = True
    deviation_review_enabled: bool = True
    external_evidence_enabled: bool = True
    require_human_for_high_risk: bool = True
    thresholds_version: str = "committee-v1"
    crystal_min_score_for_dft: float = 0.70
    experiment_min_score_for_submit: float = 0.75
    prediction_disagreement_ratio: float = 0.30
    top_k_score_proximity_ratio: float = 0.05
    experiment_relative_deviation_trigger: float = 0.30
    experiment_absolute_deviation_by_property: dict[str, float] = Field(default_factory=dict)
    external_conflict_requires_review: bool = True
    dft_cost_trigger: float = 0.0


class ControlPlaneMode(str, Enum):
    OBSERVE = "observe"
    ENFORCE = "enforce"


class ControlPlaneConfig(BaseModel):
    enabled: bool = False
    default_mode: ControlPlaneMode = ControlPlaneMode.OBSERVE
    tool_gateway_enforce: bool = False
    context_ttl_seconds: int = 3600
    policy_version: str = "cp-v1"
    shadow_mode: bool = True
    # Budget defaults
    default_token_limit: int | None = None
    default_external_call_limit: int | None = None
    default_dft_cpu_hour_limit: float | None = None
    default_cost_limit: float | None = None
    default_concurrency_limit: int = 4
    # Checkpoint
    checkpoint_interval_seconds: int = 30
    # Outbox
    outbox_retry_max: int = 5
    outbox_retry_delay_seconds: float = 5.0
    # Observability
    enable_tracing: bool = True
    trace_retention_days: int = 30


class EvalConfig(BaseModel):
    enabled: bool = False
    golden_set_dir: str = "evals/datasets"
    baseline_dir: str = "evals/baselines"
    report_dir: str = "evals/reports"
    # Safety zero-tolerance metrics
    safety_metrics: list[str] = Field(default_factory=lambda: [
        "invalid_structure_leak_rate",
        "hard_rule_bypass_rate",
        "unauthorized_access_rate",
        "key_exposure_count",
    ])
    # Business metrics that must not regress
    business_metrics: list[str] = Field(default_factory=lambda: [
        "valid_candidate_rejection_rate",
        "ndcg_score",
        "qc_misattribution_rate",
        "evidence_conflict_interception_rate",
    ])
    # Promotion gates
    safety_zero_tolerance: bool = True
    business_no_regression: bool = True
    # Eval run defaults
    default_timeout_seconds: int = 600
    parallel_workers: int = 2


class IndustrializationConfig(BaseModel):
    cost_threshold: float = 500.0  # 0727b：成本熔断阈值（货币+单位由上下文决定）
    db_path: Path = Path("data/raw_materials.db")  # 物料数据库路径
    blacklist_smarts: list[str] = Field(default_factory=lambda: [
        "[N+](=O)[O-]",   # 硝基化合物（高爆炸风险）
        "P(=S)(F)(F)F",    # 剧毒神经毒剂特征
    ])


class ChemistryRuleSetConfig(BaseModel):
    """Task 15：化学规则引擎配置（候选生成阶段硬过滤）。

    所有字段可选，默认空（不做硬过滤）。可通过 ``config/workflows/ecml_v2.yaml``
    的 ``chemistry_rules`` 段配置，或通过环境变量
    ``CHEMISTRY_REQUIRED_ELEMENTS`` / ``CHEMISTRY_FORBIDDEN_ELEMENTS``
    （逗号分隔）/ ``CHEMISTRY_MAX_ELEMENTS_COUNT`` / ``CHEMISTRY_REQUIRED_STRUCTURE_TYPES``
    （逗号分隔）覆盖。
    """
    required_elements: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)
    max_elements_count: int | None = None
    required_structure_types: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    materials_project: MaterialsProjectConfig = Field(default_factory=MaterialsProjectConfig)
    askcos: ASKCOSConfig = Field(default_factory=ASKCOSConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    data_dir: Path = Path("data")
    engine_mode: EngineMode = Field(default=EngineMode.LEGACY)
    execution_profile: ExecutionProfile = Field(default=ExecutionProfile.STANDARD)
    run_mode: RunMode = Field(default=RunMode.DEMO)
    logos: LogosConfig = Field(default_factory=LogosConfig)
    internlm: InternLMConfig = Field(default_factory=InternLMConfig)
    scp: SCPConfig = Field(default_factory=SCPConfig)
    industrialization: IndustrializationConfig = Field(default_factory=IndustrializationConfig)
    committee: CommitteeConfig = Field(default_factory=CommitteeConfig)
    control_plane: ControlPlaneConfig = Field(default_factory=ControlPlaneConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    chemistry_rules: ChemistryRuleSetConfig = Field(default_factory=ChemistryRuleSetConfig)
    # T-034 SCP 异步任务混合生命周期归档（决策 D-09）
    scp_task_completed_retention_days: int = 30
    scp_task_failed_retention_days: int = 90


def _resolve_execution_profile(
    raw: str | None, engine_mode_raw: str
) -> ExecutionProfile:
    """优先读取 EXECUTION_PROFILE 环境变量；为空时从 engine_mode 映射。"""
    if raw and raw.strip():
        try:
            return ExecutionProfile(raw.strip())
        except ValueError:
            import warnings
            warnings.warn(
                f"EXECUTION_PROFILE='{raw}' 不是合法值，回退到 engine_mode 映射。",
                stacklevel=2,
            )
    return engine_mode_to_execution_profile(engine_mode_raw)


def ensure_project_root() -> Path:
    """确保进程从项目根目录运行。

    如果当前工作目录不是项目根目录，自动 ``os.chdir`` 过去，保证所有相对路径
    （``data/``、``.env``、``cache`` 等）都落到正确位置。幂等可重复调用。

    返回项目根目录 Path。
    """
    import os
    cwd = Path.cwd()
    if cwd == PROJECT_ROOT:
        return PROJECT_ROOT
    # 校验目标确实是项目根（包含本 package 目录），否则不动 CWD
    if not (PROJECT_ROOT / "battery_materials_agent").is_dir():
        return PROJECT_ROOT
    os.chdir(PROJECT_ROOT)
    import logging
    logging.getLogger(__name__).info(
        "Working directory switched to project root: %s", PROJECT_ROOT
    )
    return PROJECT_ROOT


# 全局单例缓存，避免每次调用都重新读 .env + 构造 AgentConfig
_config_cache: AgentConfig | None = None


def get_config(env_file: str | None = None, refresh: bool = False) -> AgentConfig:
    """获取全局单例配置。

    首次调用通过 :func:`load_config` 构造并缓存；后续调用直接返回缓存。
    设置 ``refresh=True`` 可强制重新加载（例如 ``.env`` 被外部修改后）。
    """
    global _config_cache
    if _config_cache is None or refresh:
        _config_cache = load_config(env_file)
    return _config_cache


def _load_chemistry_rules_config() -> ChemistryRuleSetConfig:
    """Task 15：加载化学规则引擎配置。

    优先级（后者覆盖前者）：
    1. ``config/workflows/ecml_v2.yaml`` 的 ``chemistry_rules`` 段（若文件存在）
    2. 环境变量 ``CHEMISTRY_REQUIRED_ELEMENTS`` / ``CHEMISTRY_FORBIDDEN_ELEMENTS``
       / ``CHEMISTRY_MAX_ELEMENTS_COUNT`` / ``CHEMISTRY_REQUIRED_STRUCTURE_TYPES``

    任何一步失败都回退到空配置（``ChemistryRuleSetConfig()`` 默认值），保持向后兼容。
    """
    import os
    import logging

    log = logging.getLogger(__name__)

    required: list[str] = []
    forbidden: list[str] = []
    max_elements: int | None = None
    structures: list[str] = []

    # 1. 从 config/workflows/ecml_v2.yaml 读取默认值
    yaml_path = PROJECT_ROOT / "config" / "workflows" / "ecml_v2.yaml"
    if yaml_path.is_file():
        try:
            import yaml  # type: ignore[import-untyped]

            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            rules_section = data.get("chemistry_rules") or {}
            if isinstance(rules_section, dict):
                req = rules_section.get("required_elements")
                if isinstance(req, list):
                    required = [str(x) for x in req if x]
                forb = rules_section.get("forbidden_elements")
                if isinstance(forb, list):
                    forbidden = [str(x) for x in forb if x]
                me = rules_section.get("max_elements_count")
                if me is not None:
                    max_elements = int(me)
                sts = rules_section.get("required_structure_types")
                if isinstance(sts, list):
                    structures = [str(x) for x in sts if x]
            log.info(
                "Loaded chemistry_rules from %s: required=%s forbidden=%s max=%s structures=%s",
                yaml_path, required, forbidden, max_elements, structures,
            )
        except Exception as e:
            log.warning("Failed to load chemistry_rules from %s: %s", yaml_path, e)

    # 2. 环境变量覆盖
    env_req = os.getenv("CHEMISTRY_REQUIRED_ELEMENTS", "")
    if env_req:
        required = [s.strip() for s in env_req.split(",") if s.strip()]
    env_forb = os.getenv("CHEMISTRY_FORBIDDEN_ELEMENTS", "")
    if env_forb:
        forbidden = [s.strip() for s in env_forb.split(",") if s.strip()]
    env_max = os.getenv("CHEMISTRY_MAX_ELEMENTS_COUNT", "")
    if env_max.strip():
        try:
            max_elements = int(env_max)
        except ValueError:
            log.warning("CHEMISTRY_MAX_ELEMENTS_COUNT='%s' 不是合法整数，忽略", env_max)
    env_sts = os.getenv("CHEMISTRY_REQUIRED_STRUCTURE_TYPES", "")
    if env_sts:
        structures = [s.strip() for s in env_sts.split(",") if s.strip()]

    return ChemistryRuleSetConfig(
        required_elements=required,
        forbidden_elements=forbidden,
        max_elements_count=max_elements,
        required_structure_types=structures,
    )


def load_config(env_file: str | None = None) -> AgentConfig:
    """Load configuration from environment variables and optional .env file.

    If env_file is not provided, auto-loads .env from the project root
    directory (based on this module's location) so the config is picked up
    regardless of the server's current working directory.

    注意：此函数每次都会重新读取并构造配置。运行时请优先使用
    :func:`get_config` 单例入口；如需在 ``.env`` 改动后强制刷新，调用
    ``get_config(refresh=True)``。
    """
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    if env_file:
        load_dotenv(env_file)
    else:
        # Resolve .env relative to the project root (parent of this package),
        # falling back to CWD. This avoids config being silently ignored when
        # the server is started from a different working directory.
        candidates = [
            PROJECT_ROOT / ".env",  # project root
            Path.cwd() / ".env",    # current working dir
        ]
        loaded = False
        for candidate in candidates:
            if candidate.is_file():
                try:
                    load_dotenv(candidate, override=False)
                    loaded = True
                    break
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Failed to load .env from %s: %s", candidate, exc
                    )
        if not loaded:
            import logging
            logging.getLogger(__name__).info(
                "No .env file found in project root or CWD; relying on OS environment variables."
            )

    engine_mode_raw = os.getenv("ENGINE_MODE", "legacy")
    # 兼容旧值 logos -> internlm
    if engine_mode_raw.lower() == "logos":
        import warnings
        warnings.warn(
            "ENGINE_MODE=logos 已弃用，自动映射为 internlm。请更新配置为 ENGINE_MODE=internlm。",
            DeprecationWarning,
            stacklevel=2,
        )
        engine_mode_raw = "internlm"

    internlm_api_key = os.getenv("INTERNLM_API_KEY", "")
    scp_api_key = os.getenv("SCP_HUB_API_KEY", "")

    # 读取 SCP 绑定启用状态覆盖（SCP_BINDING_<NAME>_ENABLED=true/false）
    scp_binding_enabled: dict[str, bool] = {}
    for key, value in os.environ.items():
        if key.startswith("SCP_BINDING_") and key.endswith("_ENABLED"):
            internal_name = key[len("SCP_BINDING_") : -len("_ENABLED")].lower()
            if internal_name:
                scp_binding_enabled[internal_name] = value.lower() == "true"

    return AgentConfig(
        materials_project=MaterialsProjectConfig(
            api_key=os.getenv("MP_API_KEY", ""),
            gnome_use_mp_mirror=os.getenv("GNOME_USE_MP_MIRROR", "true").lower() == "true",
            gnome_data_dir=Path(os.getenv("GNOME_DATA_DIR", "data/gnome")),
        ),
        askcos=ASKCOSConfig(
            base_url=os.getenv("ASKCOS_BASE_URL", "http://localhost:5000"),
            timeout=int(os.getenv("ASKCOS_TIMEOUT", "60")),
        ),
        middleware=MiddlewareConfig(
            db_url=os.getenv("MIDDLEWARE_DB_URL", "sqlite:///data/experiment_data.db"),
        ),
        llm=LLMConfig(
            api_key=os.getenv("LLM_API_KEY", ""),
            model=os.getenv("LLM_MODEL", "LongCat-2.0"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.longcat.chat/openai"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "128000")),
        ),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        engine_mode=EngineMode(engine_mode_raw),
        execution_profile=_resolve_execution_profile(os.getenv("EXECUTION_PROFILE"), engine_mode_raw),
        run_mode=RunMode(os.getenv("RUN_MODE", "demo")),
        logos=LogosConfig(
            base_url=os.getenv("LOGOS_BASE_URL", "http://localhost:8080/v1"),
            model_name=os.getenv("LOGOS_MODEL_NAME", "logos-8b"),
            api_key=os.getenv("LOGOS_API_KEY", ""),
            timeout=int(os.getenv("LOGOS_TIMEOUT", "60")),
        ),
        internlm=InternLMConfig(
            enabled=os.getenv("INTERNLM_ENABLED", "true").lower() == "true",
            base_url=os.getenv("INTERNLM_BASE_URL", "https://chat.intern-ai.org.cn/api/v1"),
            api_key=SecretStr(internlm_api_key) if internlm_api_key else None,
            model=os.getenv("INTERNLM_MODEL", "intern-s2-preview-397b"),
            timeout_seconds=float(os.getenv("INTERNLM_TIMEOUT_SECONDS", "90")),
            connect_timeout_seconds=float(os.getenv("INTERNLM_CONNECT_TIMEOUT", "10")),
            max_retries=int(os.getenv("INTERNLM_MAX_RETRIES", "2")),
            thinking_mode=os.getenv("INTERNLM_THINKING_MODE", "true").lower() == "true",
            max_concurrency=int(os.getenv("INTERNLM_MAX_CONCURRENCY", "4")),
            json_repair_retries=int(os.getenv("INTERNLM_JSON_REPAIR_RETRIES", "1")),
        ),
        scp=SCPConfig(
            enabled=os.getenv("SCP_ENABLED", "false").lower() == "true",
            base_url=os.getenv("SCP_BASE_URL", "https://scp.intern-ai.org.cn/api/v1/mcp"),
            api_key=SecretStr(scp_api_key) if scp_api_key else None,
            connect_timeout_seconds=float(os.getenv("SCP_CONNECT_TIMEOUT", "10")),
            read_timeout_seconds=float(os.getenv("SCP_READ_TIMEOUT", "60")),
            max_retries=int(os.getenv("SCP_MAX_RETRIES", "1")),
            max_concurrency=int(os.getenv("SCP_MAX_CONCURRENCY", "6")),
            allowed_servers=[s.strip() for s in os.getenv("SCP_ALLOWED_SERVERS", "").split(",") if s.strip()],
            allowed_tools=[s.strip() for s in os.getenv("SCP_ALLOWED_TOOLS", "").split(",") if s.strip()],
            binding_enabled=scp_binding_enabled,
        ),
        industrialization=IndustrializationConfig(
            cost_threshold=float(os.getenv("INDUSTRIALIZATION_COST_THRESHOLD", "500.0")),
            db_path=Path(os.getenv("INDUSTRIALIZATION_DB_PATH", "data/raw_materials.db")),
        ),
        committee=CommitteeConfig(
            enabled=os.getenv("COMMITTEE_ENABLED", "false").lower() == "true",
            default_mode=CommitteeMode(os.getenv("COMMITTEE_DEFAULT_MODE", "observe")),
            max_evidence_rounds=int(os.getenv("COMMITTEE_MAX_EVIDENCE_ROUNDS", "2")),
            max_parallel_evidence_tasks=int(os.getenv("COMMITTEE_MAX_PARALLEL_EVIDENCE_TASKS", "4")),
            case_timeout_seconds=int(os.getenv("COMMITTEE_CASE_TIMEOUT_SECONDS", "300")),
            crystal_enabled=os.getenv("COMMITTEE_CRYSTAL_ENABLED", "true").lower() == "true",
            experiment_enabled=os.getenv("COMMITTEE_EXPERIMENT_ENABLED", "true").lower() == "true",
            candidate_priority_enabled=os.getenv("COMMITTEE_CANDIDATE_PRIORITY_ENABLED", "true").lower() == "true",
            deviation_review_enabled=os.getenv("COMMITTEE_DEVIATION_REVIEW_ENABLED", "true").lower() == "true",
            external_evidence_enabled=os.getenv("COMMITTEE_EXTERNAL_EVIDENCE_ENABLED", "true").lower() == "true",
            require_human_for_high_risk=os.getenv("COMMITTEE_REQUIRE_HUMAN_FOR_HIGH_RISK", "true").lower() == "true",
            crystal_min_score_for_dft=float(os.getenv("COMMITTEE_CRYSTAL_MIN_SCORE_FOR_DFT", "0.70")),
            experiment_min_score_for_submit=float(os.getenv("COMMITTEE_EXPERIMENT_MIN_SCORE_FOR_SUBMIT", "0.75")),
            prediction_disagreement_ratio=float(os.getenv("COMMITTEE_PREDICTION_DISAGREEMENT_RATIO", "0.30")),
            top_k_score_proximity_ratio=float(os.getenv("COMMITTEE_TOP_K_SCORE_PROXIMITY_RATIO", "0.05")),
            experiment_relative_deviation_trigger=float(os.getenv("COMMITTEE_EXPERIMENT_RELATIVE_DEVIATION_TRIGGER", "0.30")),
            external_conflict_requires_review=os.getenv("COMMITTEE_EXTERNAL_CONFLICT_REQUIRES_REVIEW", "true").lower() == "true",
            dft_cost_trigger=float(os.getenv("COMMITTEE_DFT_COST_TRIGGER", "0.0")),
        ),
        control_plane=ControlPlaneConfig(
            enabled=os.getenv("CONTROL_PLANE_ENABLED", "false").lower() == "true",
            default_mode=ControlPlaneMode(os.getenv("CONTROL_PLANE_MODE", "observe")),
            tool_gateway_enforce=os.getenv("CONTROL_PLANE_TOOL_GATEWAY_ENFORCE", "false").lower() == "true",
            context_ttl_seconds=int(os.getenv("CONTROL_PLANE_CONTEXT_TTL_SECONDS", "3600")),
            policy_version=os.getenv("CONTROL_PLANE_POLICY_VERSION", "cp-v1"),
            shadow_mode=os.getenv("CONTROL_PLANE_SHADOW_MODE", "true").lower() == "true",
            default_concurrency_limit=int(os.getenv("CONTROL_PLANE_DEFAULT_CONCURRENCY_LIMIT", "4")),
            checkpoint_interval_seconds=int(os.getenv("CONTROL_PLANE_CHECKPOINT_INTERVAL_SECONDS", "30")),
            enable_tracing=os.getenv("CONTROL_PLANE_ENABLE_TRACING", "true").lower() == "true",
        ),
        eval=EvalConfig(
            enabled=os.getenv("EVAL_ENABLED", "false").lower() == "true",
            golden_set_dir=os.getenv("EVAL_GOLDEN_SET_DIR", "evals/datasets"),
            baseline_dir=os.getenv("EVAL_BASELINE_DIR", "evals/baselines"),
            report_dir=os.getenv("EVAL_REPORT_DIR", "evals/reports"),
        ),
        chemistry_rules=_load_chemistry_rules_config(),
        scp_task_completed_retention_days=int(os.getenv("SCP_TASK_COMPLETED_RETENTION_DAYS", "30")),
        scp_task_failed_retention_days=int(os.getenv("SCP_TASK_FAILED_RETENTION_DAYS", "90")),
    )


def save_config_to_env(config: AgentConfig, env_path: str = ".env") -> None:
    """Write key runtime config values back to a .env file.

    Preserves any existing lines that are not in the managed key set.
    Creates the file (and its parent directory) if it does not exist.
    """
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    base_managed_keys = {
        "ENGINE_MODE",
        "EXECUTION_PROFILE",
        "RUN_MODE",
        "LOGOS_BASE_URL",
        "LOGOS_MODEL_NAME",
        "LOGOS_API_KEY",
        "LOGOS_TIMEOUT",
        "INTERNLM_ENABLED",
        "INTERNLM_API_KEY",
        "INTERNLM_BASE_URL",
        "INTERNLM_MODEL",
        "INTERNLM_TIMEOUT_SECONDS",
        "INTERNLM_THINKING_MODE",
        "INTERNLM_MAX_CONCURRENCY",
        "SCP_ENABLED",
        "SCP_HUB_API_KEY",
        "SCP_BASE_URL",
        "SCP_ALLOWED_SERVERS",
        "SCP_ALLOWED_TOOLS",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_MAX_TOKENS",
        "ASKCOS_BASE_URL",
        "ASKCOS_TIMEOUT",
        "INDUSTRIALIZATION_COST_THRESHOLD",
        "INDUSTRIALIZATION_DB_PATH",
        "COMMITTEE_ENABLED",
        "COMMITTEE_DEFAULT_MODE",
        "COMMITTEE_MAX_EVIDENCE_ROUNDS",
        "COMMITTEE_MAX_PARALLEL_EVIDENCE_TASKS",
        "COMMITTEE_CASE_TIMEOUT_SECONDS",
        "COMMITTEE_CRYSTAL_ENABLED",
        "COMMITTEE_EXPERIMENT_ENABLED",
        "COMMITTEE_CANDIDATE_PRIORITY_ENABLED",
        "COMMITTEE_DEVIATION_REVIEW_ENABLED",
        "COMMITTEE_EXTERNAL_EVIDENCE_ENABLED",
        "COMMITTEE_REQUIRE_HUMAN_FOR_HIGH_RISK",
        "COMMITTEE_CRYSTAL_MIN_SCORE_FOR_DFT",
        "COMMITTEE_EXPERIMENT_MIN_SCORE_FOR_SUBMIT",
        "COMMITTEE_PREDICTION_DISAGREEMENT_RATIO",
        "COMMITTEE_TOP_K_SCORE_PROXIMITY_RATIO",
        "COMMITTEE_EXPERIMENT_RELATIVE_DEVIATION_TRIGGER",
        "COMMITTEE_EXTERNAL_CONFLICT_REQUIRES_REVIEW",
        "COMMITTEE_DFT_COST_TRIGGER",
        "CONTROL_PLANE_ENABLED",
        "CONTROL_PLANE_MODE",
        "CONTROL_PLANE_TOOL_GATEWAY_ENFORCE",
        "CONTROL_PLANE_CONTEXT_TTL_SECONDS",
        "CONTROL_PLANE_POLICY_VERSION",
        "CONTROL_PLANE_SHADOW_MODE",
        "CONTROL_PLANE_DEFAULT_CONCURRENCY_LIMIT",
        "CONTROL_PLANE_CHECKPOINT_INTERVAL_SECONDS",
        "CONTROL_PLANE_ENABLE_TRACING",
        "EVAL_ENABLED",
        "EVAL_GOLDEN_SET_DIR",
        "EVAL_BASELINE_DIR",
        "EVAL_REPORT_DIR",
    }

    internlm_key = config.internlm.api_key.get_secret_value() if config.internlm.api_key else ""
    scp_key = config.scp.api_key.get_secret_value() if config.scp.api_key else ""

    # SCP 绑定启用状态按内部名称生成环境变量键（默认值 true，可被 binding_enabled 覆盖）
    scp_binding_values = {
        f"SCP_BINDING_{name.upper()}_ENABLED": str(
            config.scp.binding_enabled.get(name, True)
        ).lower()
        for name in DEFAULT_SCP_BINDING_NAMES
    }
    managed_keys = base_managed_keys | set(scp_binding_values.keys())

    values = {
        "ENGINE_MODE": config.engine_mode.value,
        "EXECUTION_PROFILE": config.execution_profile.value,
        "RUN_MODE": config.run_mode.value,
        "LOGOS_BASE_URL": config.logos.base_url,
        "LOGOS_MODEL_NAME": config.logos.model_name,
        "LOGOS_API_KEY": config.logos.api_key,
        "LOGOS_TIMEOUT": str(config.logos.timeout),
        "INTERNLM_ENABLED": str(config.internlm.enabled).lower(),
        "INTERNLM_API_KEY": internlm_key,
        "INTERNLM_BASE_URL": config.internlm.base_url,
        "INTERNLM_MODEL": config.internlm.model,
        "INTERNLM_TIMEOUT_SECONDS": str(config.internlm.timeout_seconds),
        "INTERNLM_THINKING_MODE": str(config.internlm.thinking_mode).lower(),
        "INTERNLM_MAX_CONCURRENCY": str(config.internlm.max_concurrency),
        "SCP_ENABLED": str(config.scp.enabled).lower(),
        "SCP_HUB_API_KEY": scp_key,
        "SCP_BASE_URL": config.scp.base_url,
        "SCP_ALLOWED_SERVERS": ",".join(config.scp.allowed_servers),
        "SCP_ALLOWED_TOOLS": ",".join(config.scp.allowed_tools),
        **scp_binding_values,
        "LLM_API_KEY": config.llm.api_key,
        "LLM_MODEL": config.llm.model,
        "LLM_BASE_URL": config.llm.base_url,
        "LLM_MAX_TOKENS": str(config.llm.max_tokens),
        "ASKCOS_BASE_URL": config.askcos.base_url,
        "ASKCOS_TIMEOUT": str(config.askcos.timeout),
        "INDUSTRIALIZATION_COST_THRESHOLD": str(config.industrialization.cost_threshold),
        "INDUSTRIALIZATION_DB_PATH": str(config.industrialization.db_path),
        "COMMITTEE_ENABLED": str(config.committee.enabled).lower(),
        "COMMITTEE_DEFAULT_MODE": config.committee.default_mode.value,
        "COMMITTEE_MAX_EVIDENCE_ROUNDS": str(config.committee.max_evidence_rounds),
        "COMMITTEE_MAX_PARALLEL_EVIDENCE_TASKS": str(config.committee.max_parallel_evidence_tasks),
        "COMMITTEE_CASE_TIMEOUT_SECONDS": str(config.committee.case_timeout_seconds),
        "COMMITTEE_CRYSTAL_ENABLED": str(config.committee.crystal_enabled).lower(),
        "COMMITTEE_EXPERIMENT_ENABLED": str(config.committee.experiment_enabled).lower(),
        "COMMITTEE_CANDIDATE_PRIORITY_ENABLED": str(config.committee.candidate_priority_enabled).lower(),
        "COMMITTEE_DEVIATION_REVIEW_ENABLED": str(config.committee.deviation_review_enabled).lower(),
        "COMMITTEE_EXTERNAL_EVIDENCE_ENABLED": str(config.committee.external_evidence_enabled).lower(),
        "COMMITTEE_REQUIRE_HUMAN_FOR_HIGH_RISK": str(config.committee.require_human_for_high_risk).lower(),
        "COMMITTEE_CRYSTAL_MIN_SCORE_FOR_DFT": str(config.committee.crystal_min_score_for_dft),
        "COMMITTEE_EXPERIMENT_MIN_SCORE_FOR_SUBMIT": str(config.committee.experiment_min_score_for_submit),
        "COMMITTEE_PREDICTION_DISAGREEMENT_RATIO": str(config.committee.prediction_disagreement_ratio),
        "COMMITTEE_TOP_K_SCORE_PROXIMITY_RATIO": str(config.committee.top_k_score_proximity_ratio),
        "COMMITTEE_EXPERIMENT_RELATIVE_DEVIATION_TRIGGER": str(config.committee.experiment_relative_deviation_trigger),
        "COMMITTEE_EXTERNAL_CONFLICT_REQUIRES_REVIEW": str(config.committee.external_conflict_requires_review).lower(),
        "COMMITTEE_DFT_COST_TRIGGER": str(config.committee.dft_cost_trigger),
        "CONTROL_PLANE_ENABLED": str(config.control_plane.enabled).lower(),
        "CONTROL_PLANE_MODE": config.control_plane.default_mode.value,
        "CONTROL_PLANE_TOOL_GATEWAY_ENFORCE": str(config.control_plane.tool_gateway_enforce).lower(),
        "CONTROL_PLANE_CONTEXT_TTL_SECONDS": str(config.control_plane.context_ttl_seconds),
        "CONTROL_PLANE_POLICY_VERSION": config.control_plane.policy_version,
        "CONTROL_PLANE_SHADOW_MODE": str(config.control_plane.shadow_mode).lower(),
        "CONTROL_PLANE_DEFAULT_CONCURRENCY_LIMIT": str(config.control_plane.default_concurrency_limit),
        "CONTROL_PLANE_CHECKPOINT_INTERVAL_SECONDS": str(config.control_plane.checkpoint_interval_seconds),
        "CONTROL_PLANE_ENABLE_TRACING": str(config.control_plane.enable_tracing).lower(),
        "EVAL_ENABLED": str(config.eval.enabled).lower(),
        "EVAL_GOLDEN_SET_DIR": config.eval.golden_set_dir,
        "EVAL_BASELINE_DIR": config.eval.baseline_dir,
        "EVAL_REPORT_DIR": config.eval.report_dir,
    }

    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0]
        if key in managed_keys:
            new_lines.append(f"{key}={values[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key in managed_keys:
        if key not in updated_keys:
            new_lines.append(f"{key}={values[key]}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # 失效单例缓存：.env 已被改写，下次 get_config() 必须重新加载
    global _config_cache
    _config_cache = None
