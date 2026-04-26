"""
认证模块

提供 API Key 认证、JWT 认证等安全功能。
"""

from .api_key import APIKeyAuth, APIKeyMiddleware
from .store import APIKeyStore, APIKeyRecord
from .jwt import JWTAuth, JWTConfig, TokenPair, UserPayload, create_jwt_auth_from_env
from .user_store import UserStore, UserRecord, create_default_admin_user
from .rbac import (
    Role, Permission, RoleStore,
    SYSTEM_ROLES, DEFAULT_ROUTE_PERMISSIONS,
    get_role_store, reset_role_store,
)

__all__ = [
    "APIKeyAuth",
    "APIKeyMiddleware",
    "APIKeyStore",
    "APIKeyRecord",
    "JWTAuth",
    "JWTConfig",
    "TokenPair",
    "UserPayload",
    "create_jwt_auth_from_env",
    "UserStore",
    "UserRecord",
    "create_default_admin_user",
    # RBAC
    "Role", "Permission", "RoleStore",
    "SYSTEM_ROLES", "DEFAULT_ROUTE_PERMISSIONS",
    "get_role_store", "reset_role_store",
]
