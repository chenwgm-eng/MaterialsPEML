"""统一工作流 Schema 加载器。"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import logging
import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SCHEMA_PATH = _PROJECT_ROOT / "config" / "workflows" / "ecml_v2.yaml"


class WorkflowSchemaLoader:
    """加载并验证工作流 YAML Schema。"""

    def __init__(self, schema_path: str | Path | None = None):
        self.schema_path = Path(schema_path) if schema_path else _DEFAULT_SCHEMA_PATH
        self._schema: dict | None = None

    def load(self) -> dict:
        """加载并缓存工作流 Schema。"""
        if self._schema is not None:
            return self._schema

        if not self.schema_path.exists():
            logger.warning("Workflow schema not found at %s", self.schema_path)
            return {}

        with open(self.schema_path, "r", encoding="utf-8") as f:
            self._schema = yaml.safe_load(f) or {}

        self._validate(self._schema)
        return self._schema

    def _validate(self, schema: dict) -> None:
        """基础校验。"""
        wf = schema.get("workflow", {})
        if not wf.get("id"):
            raise ValueError("Workflow schema missing 'id'")
        if not wf.get("nodes"):
            raise ValueError("Workflow schema missing 'nodes'")

    def get_nodes(self) -> list[dict]:
        """返回节点列表。"""
        return self.load().get("workflow", {}).get("nodes", [])

    def get_node(self, node_id: str) -> dict | None:
        """按 ID 查找节点。"""
        for node in self.get_nodes():
            if node.get("id") == node_id:
                return node
        return None

    def get_states(self, category: str = "candidate") -> list[str]:
        """返回指定分类的状态列表。"""
        return self.load().get("workflow", {}).get("states", {}).get(category, [])

    def get_events(self) -> list[str]:
        """返回事件类型列表。"""
        return self.load().get("workflow", {}).get("events", [])

    def get_timeout_policy(self) -> dict:
        """返回超时策略。"""
        return self.load().get("workflow", {}).get("timeout_policy", {})

    def to_dict(self) -> dict:
        """返回完整 Schema 字典。"""
        return self.load()


# 全局单例
_loader: WorkflowSchemaLoader | None = None


def get_schema_loader() -> WorkflowSchemaLoader:
    global _loader
    if _loader is None:
        _loader = WorkflowSchemaLoader()
    return _loader
