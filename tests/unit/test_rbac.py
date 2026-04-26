"""
RBAC 单元测试
覆盖: Permission, Role, RoleStore, 权限匹配, 通配符, 系统角色保护
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from auth.rbac import (
    Permission, Role, RoleStore, SYSTEM_ROLES,
    DEFAULT_ROUTE_PERMISSIONS, get_role_store, reset_role_store,
)


# ── Permission ────────────────────────────────────────────────────────

class TestPermission:
    def test_to_string(self):
        p = Permission(resource="jobs", action="read")
        assert p.to_string() == "jobs.read"

    def test_from_string(self):
        p = Permission.from_string("users.write")
        assert p.resource == "users"
        assert p.action == "write"

    def test_from_string_invalid(self):
        with pytest.raises(ValueError):
            Permission.from_string("invalid")

    def test_matches_exact(self):
        p = Permission(resource="jobs", action="read")
        req = Permission(resource="jobs", action="read")
        assert p.matches(req) is True

    def test_matches_different_resource(self):
        p = Permission(resource="jobs", action="read")
        req = Permission(resource="users", action="read")
        assert p.matches(req) is False

    def test_matches_wildcard_resource(self):
        p = Permission(resource="*", action="read")
        req = Permission(resource="jobs", action="read")
        assert p.matches(req) is True

    def test_matches_wildcard_action(self):
        p = Permission(resource="jobs", action="*")
        req = Permission(resource="jobs", action="delete")
        assert p.matches(req) is True

    def test_matches_full_wildcard(self):
        p = Permission(resource="*", action="*")
        req = Permission(resource="users", action="admin")
        assert p.matches(req) is True


# ── Role ──────────────────────────────────────────────────────────────

class TestRole:
    def test_has_permission_exact(self):
        role = Role(name="test", display_name="Test", permissions=["jobs.read", "jobs.write"])
        assert role.has_permission("jobs.read") is True
        assert role.has_permission("jobs.delete") is False

    def test_has_permission_wildcard(self):
        role = Role(name="admin", display_name="Admin", permissions=["*.*"])
        assert role.has_permission("anything.anything") is True

    def test_has_permission_partial_wildcard(self):
        role = Role(name="reader", display_name="Reader", permissions=["*.read"])
        assert role.has_permission("jobs.read") is True
        assert role.has_permission("jobs.write") is False

    def test_has_permission_invalid_string(self):
        role = Role(name="test", display_name="Test", permissions=["jobs.read"])
        assert role.has_permission("invalid") is False

    def test_to_dict_from_dict_roundtrip(self):
        role = Role(name="test", display_name="Test", description="desc",
                    permissions=["a.read", "b.write"], is_system=False)
        d = role.to_dict()
        restored = Role.from_dict(d)
        assert restored.name == role.name
        assert restored.permissions == role.permissions


# ── System Roles ──────────────────────────────────────────────────────

class TestSystemRoles:
    def test_admin_has_all_permissions(self):
        admin = SYSTEM_ROLES["admin"]
        assert admin.has_permission("jobs.read") is True
        assert admin.has_permission("users.delete") is True
        assert admin.has_permission("anything.anything") is True
        assert admin.is_system is True

    def test_operator_permissions(self):
        op = SYSTEM_ROLES["operator"]
        assert op.has_permission("jobs.read") is True
        assert op.has_permission("jobs.write") is True
        assert op.has_permission("templates.write") is True
        assert op.has_permission("users.delete") is False
        assert op.has_permission("auth.admin") is False
        assert op.is_system is True

    def test_viewer_readonly(self):
        viewer = SYSTEM_ROLES["viewer"]
        assert viewer.has_permission("jobs.read") is True
        assert viewer.has_permission("jobs.write") is False
        assert viewer.has_permission("templates.write") is False
        assert viewer.is_system is True

    def test_all_system_roles_exist(self):
        assert set(SYSTEM_ROLES.keys()) == {"admin", "operator", "viewer"}


# ── RoleStore ─────────────────────────────────────────────────────────

class TestRoleStore:
    @pytest.fixture
    def store(self, tmp_path):
        """创建临时存储，避免影响生产数据"""
        reset_role_store()
        persist_file = str(tmp_path / "roles.json")
        s = RoleStore(persist_file=persist_file)
        return s

    def test_init_loads_system_roles(self, store):
        roles = store.list_roles()
        names = [r.name for r in roles]
        assert "admin" in names
        assert "operator" in names
        assert "viewer" in names

    def test_get_role(self, store):
        admin = store.get_role("admin")
        assert admin is not None
        assert admin.name == "admin"

    def test_get_role_nonexistent(self, store):
        assert store.get_role("nonexistent") is None

    def test_create_custom_role(self, store):
        role = Role(name="custom", display_name="Custom", permissions=["custom.read"])
        created = store.create_role(role)
        assert created.name == "custom"
        assert store.get_role("custom") is not None

    def test_create_duplicate_role_fails(self, store):
        role = Role(name="dup", display_name="Dup", permissions=[])
        store.create_role(role)
        with pytest.raises(ValueError, match="already exists"):
            store.create_role(role)

    def test_update_role(self, store):
        custom = Role(name="updatable", display_name="Old", description="old desc")
        store.create_role(custom)
        updated = store.update_role("updatable", {"display_name": "New", "description": "new desc"})
        assert updated.display_name == "New"
        assert updated.description == "new desc"

    def test_update_system_role_permissions_denied(self, store):
        with pytest.raises(ValueError, match="Cannot change permissions"):
            store.update_role("admin", {"permissions": ["only.this"]})

    def test_update_system_role_name_denied(self, store):
        with pytest.raises(ValueError, match="Cannot change name"):
            store.update_role("admin", {"name": "superadmin"})

    def test_delete_custom_role(self, store):
        custom = Role(name="deleteme", display_name="Delete Me")
        store.create_role(custom)
        store.delete_role("deleteme")
        assert store.get_role("deleteme") is None

    def test_delete_system_role_denied(self, store):
        with pytest.raises(ValueError, match="Cannot delete system role"):
            store.delete_role("admin")

    def test_delete_nonexistent_role(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.delete_role("ghost")

    def test_add_permissions(self, store):
        custom = Role(name="partial", display_name="Partial", permissions=["jobs.read"])
        store.create_role(custom)
        updated = store.add_permissions("partial", ["jobs.write", "jobs.delete"])
        assert "jobs.write" in updated.permissions
        assert "jobs.delete" in updated.permissions
        # 不重复添加
        assert updated.permissions.count("jobs.read") == 1

    def test_add_permissions_nonexistent_role(self, store):
        with pytest.raises(KeyError):
            store.add_permissions("ghost", ["x.y"])

    def test_remove_permissions(self, store):
        custom = Role(name="trimme", display_name="Trim Me", permissions=["a.read", "a.write", "a.delete"])
        store.create_role(custom)
        updated = store.remove_permissions("trimme", ["a.write", "a.delete"])
        assert updated.permissions == ["a.read"]

    def test_check_permission_admin(self, store):
        assert store.check_permission(["admin"], "anything.anything") is True

    def test_check_permission_operator(self, store):
        assert store.check_permission(["operator"], "jobs.read") is True
        assert store.check_permission(["operator"], "users.delete") is False

    def test_check_permission_viewer(self, store):
        assert store.check_permission(["viewer"], "jobs.read") is True
        assert store.check_permission(["viewer"], "jobs.write") is False

    def test_check_permission_multi_role(self, store):
        # 同时拥有 viewer + operator → operator 的权限生效
        assert store.check_permission(["viewer", "operator"], "jobs.write") is True
        assert store.check_permission(["viewer", "operator"], "users.delete") is False

    def test_check_permission_empty_roles(self, store):
        assert store.check_permission([], "jobs.read") is False

    def test_check_permission_invalid_format(self, store):
        assert store.check_permission(["admin"], "invalid") is False

    def test_get_permissions_for_roles(self, store):
        perms = store.get_permissions_for_roles(["viewer"])
        assert "jobs.read" in perms

    def test_list_permissions(self, store):
        perms = store.list_permissions()
        assert "jobs.read" in perms
        assert "*.*" in perms  # admin 的通配符权限

    def test_persistence(self, tmp_path):
        """测试角色持久化到磁盘"""
        reset_role_store()
        persist_file = str(tmp_path / "roles.json")
        store1 = RoleStore(persist_file=persist_file)
        custom = Role(name="persist_test", display_name="Persist", permissions=["test.read"])
        store1.create_role(custom)

        # 新建 store 从同一文件加载
        reset_role_store()
        store2 = RoleStore(persist_file=persist_file)
        loaded = store2.get_role("persist_test")
        assert loaded is not None
        assert loaded.permissions == ["test.read"]


# ── DEFAULT_ROUTE_PERMISSIONS ─────────────────────────────────────────

class TestRoutePermissions:
    def test_jobs_routes_exist(self):
        assert "GET /jobs" in DEFAULT_ROUTE_PERMISSIONS
        assert "POST /jobs" in DEFAULT_ROUTE_PERMISSIONS
        assert "DELETE /jobs/{job_id}" in DEFAULT_ROUTE_PERMISSIONS

    def test_auth_routes_not_in_default(self):
        # auth 端点由 RBAC dependency 直接保护，不走默认路由表
        assert "POST /auth/login" not in DEFAULT_ROUTE_PERMISSIONS

    def test_all_permissions_valid_format(self):
        for route, perm in DEFAULT_ROUTE_PERMISSIONS.items():
            parts = perm.split(".", 1)
            assert len(parts) == 2, f"Invalid permission format for {route}: {perm}"


# ── Singleton ─────────────────────────────────────────────────────────

class TestSingleton:
    def test_get_role_store_singleton(self):
        reset_role_store()
        s1 = get_role_store()
        s2 = get_role_store()
        assert s1 is s2
        reset_role_store()  # cleanup

    def test_reset_role_store(self):
        reset_role_store()
        s1 = get_role_store()
        reset_role_store()
        s2 = get_role_store()
        assert s1 is not s2
