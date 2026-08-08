"""统一阶段执行器（StageExecutor）—— 按 PipelineStage.executor_kind 分派执行。

让研发流水线可插拔：同一套编排骨架可把不同阶段交给本地函数（native）、SCP
能力（scp）、SKILL（skill）或 Agent 小队（agent）执行，具体由领域包 pipeline
阶段声明的 executor_kind 决定，新增执行引擎时无需改动编排代码。
"""
from __future__ import annotations

import inspect
from typing import Any


class StageExecutor:
    """统一阶段分派器。

    用法：:

        executor = StageExecutor()
        executor.register("native", native_fn)      # callable(stage, context)
        executor.register("scp", scp_adapter)       # 对象带 .execute(stage, context)
        result = await executor.execute(stage, context)

    每个执行器接收 (stage, context)，返回 dict 或可被 dict 包装的值。
    """

    # 预置的执行器类型，便于校验与展示
    SUPPORTED_KINDS = ("native", "scp", "skill", "agent")

    def __init__(self, kind_executors: dict[str, Any] | None = None):
        self._kind_executors: dict[str, Any] = dict(kind_executors or {})

    def register(self, kind: str, executor: Any) -> None:
        """注册某类执行器；kind 为 native/scp/skill/agent 之一。"""
        self._kind_executors[kind] = executor

    def unregister(self, kind: str) -> None:
        self._kind_executors.pop(kind, None)

    def has_executor(self, kind: str) -> bool:
        return kind in self._kind_executors

    def kinds(self) -> list[str]:
        return list(self._kind_executors.keys())

    async def execute(self, stage, context: dict | None = None) -> dict:
        """按阶段 executor_kind 分派执行并返回结果 dict。"""
        kind = getattr(stage, "executor_kind", "native")
        executor = self._kind_executors.get(kind)
        if executor is None:
            return {
                "status": "error",
                "stage": getattr(stage, "action", ""),
                "kind": kind,
                "error": f"未注册 {kind} 类型执行器",
            }
        try:
            result = self._invoke(executor, stage, context or {})
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                return result
            return {
                "status": "success",
                "stage": getattr(stage, "action", ""),
                "kind": kind,
                "result": result,
            }
        except Exception as e:  # noqa: BLE001 - 分派异常统一收敛为结果 dict
            return {
                "status": "error",
                "stage": getattr(stage, "action", ""),
                "kind": kind,
                "error": f"{type(e).__name__}: {e}",
            }

    @staticmethod
    def _invoke(executor: Any, stage, context: dict) -> Any:
        """调用执行器：支持 callable 或带 .execute 方法的对象。"""
        if callable(executor):
            return executor(stage, context)
        method = getattr(executor, "execute", None)
        if callable(method):
            return method(stage, context)
        raise TypeError(f"执行器类型不可调用：{type(executor).__name__}")