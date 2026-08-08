"""科学服务注册中心 — 统一创建和注册全部 12 个原生科学服务实例。

供 CPU Worker 和 WorkflowExecutor 使用，确保生产环境中所有服务可被发现和调用。
"""
from __future__ import annotations

import logging
from functools import lru_cache

from ..domain.runtime import ScientificExecutionKernel
from ..workflow.executor import WorkflowExecutor
from ..workers.cpu_worker import ScientificCPUWorker
from .base_service import NativeScientificService

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_service_registry() -> dict[str, NativeScientificService]:
    """创建并返回全部 12 个原生科学服务的注册表。

    Returns:
        dict[str, NativeScientificService]: capability_id → 服务实例
    """
    from .mpa.application import MPAApplication
    from .chemical_property.application import ChemicalPropertyApplication
    from .materials_structure.application import StructureApplication
    from .formulation_packing.application import FormulationPackingApplication
    from .molecular_simulation.application import MolecularSimulationApplication
    from .synthesis_planning.application import SynthesisPlanningApplication
    from .process_modeling.application import ProcessModelingApplication
    from .reaction_network.application import ReactionNetworkApplication
    from .wavefunction_analysis.application import WavefunctionAnalysisApplication
    from .fluid_simulation.application import FluidSimulationApplication
    from .molecular_docking.application import MolecularDockingApplication

    kernel = ScientificExecutionKernel()
    services: list[NativeScientificService] = [
        MPAApplication(kernel),
        ChemicalPropertyApplication(kernel),
        StructureApplication(kernel),
        FormulationPackingApplication(kernel),
        MolecularSimulationApplication(kernel),
        SynthesisPlanningApplication(kernel),
        ProcessModelingApplication(kernel),
        ReactionNetworkApplication(kernel),
        WavefunctionAnalysisApplication(kernel),
        FluidSimulationApplication(kernel),
        MolecularDockingApplication(kernel),
    ]

    registry = {svc.capability_id: svc for svc in services}
    logger.info("Service registry initialized: %d services", len(registry))
    return registry


def get_workflow_executor() -> WorkflowExecutor:
    """创建已注册全部 12 个服务的 WorkflowExecutor。"""
    registry = get_service_registry()
    executor = WorkflowExecutor(service_registry=registry)
    return executor


def setup_cpu_worker(worker: ScientificCPUWorker | None = None) -> ScientificCPUWorker:
    """将全部 12 个服务注册到 CPU Worker。

    Args:
        worker: 已有 Worker 实例；为 None 时获取全局单例。

    Returns:
        注册完成后的 Worker 实例。
    """
    from ..workers.cpu_worker import get_worker

    worker = worker or get_worker()
    registry = get_service_registry()
    for capability_id, service in registry.items():
        worker.register_service(capability_id, service)
    logger.info("CPU Worker registered: %d services", len(registry))
    return worker
