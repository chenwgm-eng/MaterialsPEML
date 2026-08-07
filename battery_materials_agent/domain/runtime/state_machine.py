"""Run 状态机 — 管理科学服务 Run 的生命周期转换。"""
from __future__ import annotations

from ...contracts.run import RunStatus, is_terminal


class InvalidTransitionError(ValueError):
    """非法状态转换。"""
    pass


# 允许的状态转换映射
_ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.PREPARING, RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.PREPARING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLING},
    RunStatus.CANCELLING: {RunStatus.CANCELLED, RunStatus.FAILED},
    # 终态无出边
    RunStatus.SUCCEEDED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


class RunStateMachine:
    """Run 状态机 — 校验并执行状态转换。"""

    @staticmethod
    def can_transition(current: RunStatus, target: RunStatus) -> bool:
        """检查是否允许从 current 转换到 target。"""
        if current == target:
            return True
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        return target in allowed

    @staticmethod
    def transition(current: RunStatus, target: RunStatus) -> RunStatus:
        """执行状态转换，非法时抛出 InvalidTransitionError。"""
        if current == target:
            return target
        if not RunStateMachine.can_transition(current, target):
            raise InvalidTransitionError(
                f"不允许从 {current.value} 转换到 {target.value}"
            )
        return target

    @staticmethod
    def valid_transitions_from(current: RunStatus) -> list[RunStatus]:
        """返回从当前状态允许的所有转换目标。"""
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        return sorted(allowed, key=lambda s: s.value)