"""
认证模块

提供 API Key 认证、JWT 认证等安全功能。
"""

from .api_key import APIKeyAuth, APIKeyMiddleware
from .store import APIKeyStore, APIKeyRecord
from .jwt import JWTAuth, JWTConfig, TokenPair, UserPayload, create_jwt_auth_from_env
from .user_store import UserStore, UserRecord, create_default_admin_user

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
]
