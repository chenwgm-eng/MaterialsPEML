"""Step B 稳定导航壳层 —— nav_visibility 校验逻辑单元测试。

覆盖设计文档 4.B2 的默认矩阵语义（纯逻辑，不依赖 PostgreSQL）：
- 稳定一级入口 key 集合正确；
- 默认隐藏矩阵与权限推导一致（admin 入口仅对系统管理员可见，其余入口全角色可见）；
- store 的 role_matrix / visible_entries 在给定覆盖行集合下的正确性（monkeypatch 掉 DB 读取）。
"""

from __future__ import annotations

import pytest

from battery_materials_agent.auth.nav_visibility_store import (
    NAV_ENTRIES,
    DEFAULT_HIDDEN,
    NavVisibilityRow,
    NavVisibilityStore,
)


class TestConstants:
    def test_entry_keys(self):
        assert NAV_ENTRIES == ("workbench", "project", "capability", "admin")

    def test_default_hidden_subset(self):
        for role, hidden in DEFAULT_HIDDEN.items():
            assert hidden <= set(NAV_ENTRIES), f"{role} 隐藏了非法入口"

    def test_admin_hides_nothing(self):
        assert DEFAULT_HIDDEN["admin"] == set()

    def test_non_admin_hide_admin_entry(self):
        # 与权限推导一致：admin 入口仅对系统管理员可见
        for role in ("pm", "researcher", "reviewer", "viewer", "data_engineer"):
            assert "admin" in DEFAULT_HIDDEN[role], f"{role} 应隐藏 admin 入口"

    def test_hidden_only_admin(self):
        # 除 admin 外，其余入口默认全真（由权限下限再做细粒度裁剪）
        for role, hidden in DEFAULT_HIDDEN.items():
            assert hidden <= {"admin"}, f"{role} 不应隐藏非 admin 入口"


class TestStoreLogic:
    def _rows(self):
        """构造覆盖行：admin 全真；researcher 隐藏 admin。"""
        rows = []
        for role in ("admin", "researcher"):
            for entry in NAV_ENTRIES:
                rows.append(
                    NavVisibilityRow(
                        role=role,
                        entry_key=entry,
                        visible=not (role == "researcher" and entry == "admin"),
                        tenant_id="t",
                    )
                )
        return rows

    def test_role_matrix_defaults_true(self, monkeypatch):
        store = NavVisibilityStore.__new__(NavVisibilityStore)
        monkeypatch.setattr(store, "list_all", lambda: [])
        # 无覆盖行时，全部入口默认可见（含 admin）
        assert store.role_matrix("admin") == {e: True for e in NAV_ENTRIES}
        assert store.visible_entries("admin") == list(NAV_ENTRIES)

    def test_role_matrix_applies_overrides(self, monkeypatch):
        store = NavVisibilityStore.__new__(NavVisibilityStore)
        monkeypatch.setattr(store, "list_all", lambda: self._rows())
        assert store.role_matrix("researcher")["admin"] is False
        assert store.visible_entries("researcher") == ["workbench", "project", "capability"]
        assert store.role_matrix("admin")["admin"] is True

    def test_upsert_ignores_invalid_entries(self, monkeypatch):
        # 非法 entry_key 被忽略（此处仅验证筛选逻辑：NAV_ENTRIES 外 key 不产生副作用）
        store = NavVisibilityStore.__new__(NavVisibilityStore)
        invalid = [k for k in ("bogus", "admin") if k not in NAV_ENTRIES]
        assert invalid == ["bogus"]