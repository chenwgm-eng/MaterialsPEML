"""NativeScientificService 基类 — 所有原生科学服务的抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..contracts.task import Task
from ..contracts.run import Run, RunStatus
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..domain.runtime import ScientificExecutionKernel
from ..control_plane.tool_catalog import ToolRiskLevel


class NativeScientificService(ABC):
    """原生科学服务基类。

    所有 12 个科学能力域的原生服务都继承此类。
    子类只需实现 validate / prepare / execute / postprocess 四个抽象方法，
    生命周期管理由 ScientificExecutionKernel 统一处理。
    """

    kernel: ScientificExecutionKernel

    # 服务固有风险等级（ToolRiskLevel：A=最高风险，D=最低风险）。
    # 作为风险单一数据源：CapabilityCatalog 据此注册 ToolCatalog 工具描述，
    # 并派生对应能力的 max_risk_level 门禁，使路由层能真正做风险过滤（CA3）。
    # 原生科学服务均为本地 CPU 计算，默认 C（中等风险，同 pymatgen 本地计算）。
    risk_level: ToolRiskLevel = ToolRiskLevel.C

    @property
    @abstractmethod
    def capability_id(self) -> str:
        """能力域标识，如 'mpa', 'chem_properties'。"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """展示名称。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """服务描述。"""
        ...

    def __init__(self, kernel: ScientificExecutionKernel | None = None):
        self.kernel = kernel or ScientificExecutionKernel()

    @abstractmethod
    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """验证任务输入，返回校验结果（含错误信息）。"""
        ...

    @abstractmethod
    def prepare(self, task: Task) -> Run:
        """根据任务创建一次 Run 实例。"""
        ...

    @abstractmethod
    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行科学计算，返回产生的工件列表。"""
        ...

    @abstractmethod
    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将工件转换为证据包。"""
        ...

    def run_full_cycle(self, task: Task, context: dict[str, Any] | None = None) -> list[EvidencePackage]:
        """完整生命周期：validate → prepare → execute → postprocess。"""
        context = context or {}
        validation = self.validate(task, context)
        if validation.get("errors"):
            raise ValueError(f"Validation failed: {validation['errors']}")

        run = self.prepare(task)
        self.kernel.create_task(task)
        run = self.kernel.submit_run(run)

        run = self.kernel.update_run_status(run.run_id, RunStatus.RUNNING)
        try:
            artifacts = self.execute(run, context)
            for art in artifacts:
                self.kernel.store_artifact(art)
            evidence = self.postprocess(run, artifacts)
            for ev in evidence:
                self.kernel.store_evidence(ev)
            self.kernel.update_run_status(run.run_id, RunStatus.SUCCEEDED)
            return evidence
        except Exception as exc:
            self.kernel.update_run_status(run.run_id, RunStatus.FAILED)
            raise