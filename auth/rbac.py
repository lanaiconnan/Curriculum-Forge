"""
RBAC (Role-Based Access Control) 模块

提供基于角色的权限控制功能。
权限格式: resource.action, 如 jobs.read, jobs.write
支持通配符: *.read, *.*
"""

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Set, Optional, Dict, Any


# ── 数据模型 ───────────────────────────────────────────────────────────

@dataclass
class Permission:
    """权限定义"""
    resource: str          # 资源名, 如 "jobs", "users", "auth"
    action: str            # 操作名, 如 "read", "write", "delete", "admin"
    description: str = ""  # 可读描述

    def to_string(self) -> str:
        return f"{self.resource}.{self.action}"

    @staticmethod
    def from_string(s: str) -> "Permission":
        parts = s.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid permission string: {s}")
        return Permission(resource=parts[0], action=parts[1])

    def matches(self, required: "Permission") -> bool:
        """检查是否匹配（支持通配符）"""
        r_match = self.resource == "*" or self.resource == required.resource
        a_match = self.action == "*" or self.action == required.action
        return r_match and a_match


@dataclass
class Role:
    """角色定义"""
    name: str                          # 角色名, 如 "admin", "operator", "viewer"
    display_name: str                  # 显示名
    description: str = ""              # 描述
    permissions: List[str] = field(default_factory=list)  # 权限列表, 如 ["jobs.read", "jobs.write"]
    is_system: bool = False           # 是否系统内置（不可删除）

    def has_permission(self, permission_str: str) -> bool:
        """检查是否拥有指定权限（支持通配符）"""
        try:
            required = Permission.from_string(permission_str)
        except ValueError:
            return False

        for p_str in self.permissions:
            try:
                p = Permission.from_string(p_str)
                if p.matches(required):
                    return True
            except ValueError:
                continue
        return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Role":
        return Role(**d)


# ── 系统默认角色 ───────────────────────────────────────────────────────

SYSTEM_ROLES: Dict[str, Role] = {
    "admin": Role(
        name="admin",
        display_name="管理员",
        description="完全访问权限",
        permissions=["*.*"],
        is_system=True,
    ),
    "operator": Role(
        name="operator",
        display_name="操作员",
        description="任务管理和操作权限（不含用户和认证管理）",
        permissions=[
            "jobs.read", "jobs.write", "jobs.delete", "jobs.abort",
            "templates.read", "templates.write", "templates.delete",
            "schedules.read", "schedules.write", "schedules.delete",
            "workspace.read", "workspace.write",
            "audit.read", "stats.read",
        ],
        is_system=True,
    ),
    "viewer": Role(
        name="viewer",
        display_name="查看者",
        description="只读权限",
        permissions=[
            "jobs.read",
            "templates.read",
            "schedules.read",
            "workspace.read",
            "audit.read",
            "stats.read",
        ],
        is_system=True,
    ),
}

# ── 路由默认权限表 ─────────────────────────────────────────────────────

DEFAULT_ROUTE_PERMISSIONS: Dict[str, Dict[str, str]] = {
    # Jobs
    "GET /jobs":       "jobs.read",
    "POST /jobs":      "jobs.write",
    "POST /jobs/batch": "jobs.write",
    "GET /jobs/{job_id}": "jobs.read",
    "DELETE /jobs/{job_id}": "jobs.delete",
    "POST /jobs/{job_id}/abort": "jobs.abort",
    "POST /jobs/{job_id}/retry": "jobs.write",
    "GET /jobs/{job_id}/metrics": "jobs.read",
    "GET /jobs/compare": "jobs.read",
    "GET /jobs/stats": "stats.read",
    # Templates
    "GET /templates":        "templates.read",
    "POST /templates":       "templates.write",
    "GET /templates/{name}": "templates.read",
    "PUT /templates/{name}": "templates.write",
    "DELETE /templates/{name}": "templates.delete",
    # Schedules
    "GET /schedules":      "schedules.read",
    "POST /schedules":     "schedules.write",
    "GET /schedules/{id}": "schedules.read",
    "DELETE /schedules/{id}": "schedules.delete",
    # ACP
    "GET /acp/tasks":         "acp.read",
    "POST /acp/tasks/{id}/claim": "acp.write",
    "POST /acp/tasks/{id}/complete": "acp.write",
    "GET /acp/events":        "acp.read",
    # Audit & Stats
    "GET /audit":       "audit.read",
    "GET /audit/stats": "stats.read",
    "GET /stats":       "stats.read",
    "GET /stats/timeseries": "stats.read",
    # Users
    "GET /users":    "users.read",
    "POST /users":   "users.write",
    "GET /users/{user_id}": "users.read",
    "PUT /users/{user_id}": "users.write",
    "DELETE /users/{user_id}": "users.delete",
    # Roles
    "GET /roles":              "roles.read",
    "GET /roles/{name}":       "roles.read",
    "POST /roles":             "roles.write",
    "PUT /roles/{name}":       "roles.write",
    "DELETE /roles/{name}":   "roles.delete",
    "POST /roles/{name}/permissions": "roles.write",
}


# ── RoleStore ──────────────────────────────────────────────────────────

class RoleStore:
    """
    角色存储（线程安全，JSON 持久化）
    
    存储位置: data/auth/roles.json
    """

    def __init__(self, persist_file: Optional[str] = None, data_dir: Optional[str] = None):
        if persist_file:
            self._file = Path(persist_file)
        elif data_dir:
            self._file = Path(data_dir) / "roles.json"
        else:
            # 默认: 项目根目录的 data/auth/roles.json
            project_root = Path(__file__).parent.parent
            self._file = project_root / "data" / "auth" / "roles.json"

        self._roles: Dict[str, Role] = {}
        self._lock = threading.RLock()
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """从磁盘加载角色"""
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for rd in data.get("roles", []):
                    role = Role.from_dict(rd)
                    self._roles[role.name] = role
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                print(f"[RBAC] Failed to load roles.json: {e}, using defaults")
                self._roles = {}
        else:
            self._roles = {}

        # 合并系统默认角色（不覆盖用户自定义）
        for name, role in SYSTEM_ROLES.items():
            if name not in self._roles:
                self._roles[name] = role

        self._persist()

    def _persist(self):
        """持久化到磁盘"""
        data = {"roles": [r.to_dict() for r in self._roles.values()]}
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[RBAC] Failed to persist roles.json: {e}")

    # ── CRUD ───────────────────────────────────────────────────────────

    def list_roles(self) -> List[Role]:
        """列出所有角色"""
        with self._lock:
            return list(self._roles.values())

    def get_role(self, name: str) -> Optional[Role]:
        """获取指定角色"""
        with self._lock:
            return self._roles.get(name)

    def create_role(self, role: Role) -> Role:
        """创建角色（名称唯一）"""
        with self._lock:
            if role.name in self._roles:
                raise ValueError(f"Role already exists: {role.name}")
            self._roles[role.name] = role
            self._persist()
            return role

    def update_role(self, name: str, updates: Dict[str, Any]) -> Role:
        """更新角色"""
        with self._lock:
            if name not in self._roles:
                raise KeyError(f"Role not found: {name}")
            role = self._roles[name]
            if role.is_system:
                # 系统角色只能更新 display_name 和 description
                if "permissions" in updates:
                    raise ValueError("Cannot change permissions of system role")
                if "name" in updates:
                    raise ValueError("Cannot change name of system role")
                updatable = {"display_name", "description"}
                updates = {k: v for k, v in updates.items() if k in updatable}
            for k, v in updates.items():
                setattr(role, k, v)
            self._persist()
            return role

    def delete_role(self, name: str):
        """删除角色（系统角色不可删除）"""
        with self._lock:
            if name not in self._roles:
                raise KeyError(f"Role not found: {name}")
            if self._roles[name].is_system:
                raise ValueError(f"Cannot delete system role: {name}")
            del self._roles[name]
            self._persist()

    def add_permissions(self, name: str, permissions: List[str]) -> Role:
        """批量添加权限到角色"""
        with self._lock:
            if name not in self._roles:
                raise KeyError(f"Role not found: {name}")
            role = self._roles[name]
            existing = set(role.permissions)
            for p in permissions:
                if p not in existing:
                    role.permissions.append(p)
            self._persist()
            return role

    def remove_permissions(self, name: str, permissions: List[str]) -> Role:
        """批量移除角色权限"""
        with self._lock:
            if name not in self._roles:
                raise KeyError(f"Role not found: {name}")
            role = self._roles[name]
            to_remove = set(permissions)
            role.permissions = [p for p in role.permissions if p not in to_remove]
            self._persist()
            return role

    # ── 权限检查 ────────────────────────────────────────────────────────

    def get_permissions_for_roles(self, roles: List[str]) -> Set[str]:
        """获取角色列表对应的所有权限集合"""
        permissions: Set[str] = set()
        with self._lock:
            for role_name in roles:
                role = self._roles.get(role_name)
                if role:
                    permissions.update(role.permissions)
        return permissions

    def check_permission(self, roles: List[str], permission_str: str) -> bool:
        """检查角色列表是否拥有指定权限"""
        try:
            required = Permission.from_string(permission_str)
        except ValueError:
            return False

        permissions = self.get_permissions_for_roles(roles)
        for p_str in permissions:
            if p_str == "*.*":
                return True
            try:
                p = Permission.from_string(p_str)
                if p.matches(required):
                    return True
            except ValueError:
                continue
        return False

    def list_permissions(self) -> List[str]:
        """列出所有已知的权限（去重合并）"""
        permissions: Set[str] = set()
        for role in self._roles.values():
            permissions.update(role.permissions)
        return sorted(list(permissions))


# ── 单例 ───────────────────────────────────────────────────────────────

_role_store: Optional[RoleStore] = None
_role_store_lock = threading.Lock()


def get_role_store() -> RoleStore:
    """获取全局 RoleStore 单例"""
    global _role_store
    if _role_store is None:
        with _role_store_lock:
            if _role_store is None:
                _role_store = RoleStore()
    return _role_store


def reset_role_store():
    """重置单例（测试用）"""
    global _role_store
    with _role_store_lock:
        _role_store = None
