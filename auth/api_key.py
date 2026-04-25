"""
API Key 认证中间件

验证请求中的 API Key，保护 Gateway 端点。
"""

import time
import hashlib
from typing import Callable, Optional, Set, Dict, Tuple
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .store import APIKeyStore, APIKeyRecord


# 不需要认证的公开端点
PUBLIC_PATHS: Set[str] = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
}

# 前端静态资源路径前缀（不需要认证）
PUBLIC_PREFIXES: Set[str] = {
    "/static/",
    "/assets/",
}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    API Key 认证中间件

    功能：
    - 验证请求头中的 API Key
    - 注入 client_id 到 request.state
    - 可选的速率限制
    - 排除公开端点
    """

    def __init__(
        self,
        app,
        store: APIKeyStore,
        public_paths: Optional[Set[str]] = None,
        public_prefixes: Optional[Set[str]] = None,
        header_name: str = "X-API-Key",
        allow_bearer: bool = True,
    ):
        """
        初始化中间件

        Args:
            app: FastAPI 应用
            store: API Key 存储
            public_paths: 公开路径集合（不需要认证）
            public_prefixes: 公开路径前缀集合
            header_name: API Key 请求头名称
            allow_bearer: 是否支持 Authorization: Bearer <key> 格式
        """
        super().__init__(app)
        self.store = store
        self.public_paths = public_paths or PUBLIC_PATHS
        self.public_prefixes = public_prefixes or PUBLIC_PREFIXES
        self.header_name = header_name
        self.allow_bearer = allow_bearer

        # 速率限制追踪（内存中，生产环境应用 Redis）
        self._rate_limits: Dict[str, list] = {}  # key_id -> [timestamps]

    def _is_public_path(self, path: str) -> bool:
        """检查路径是否为公开路径"""
        # 精确匹配
        if path in self.public_paths:
            return True

        # 前缀匹配
        for prefix in self.public_prefixes:
            if path.startswith(prefix):
                return True

        return False

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API Key"""
        # 方式1: X-API-Key 请求头
        api_key = request.headers.get(self.header_name)
        if api_key:
            return api_key

        # 方式2: Authorization: Bearer <key>
        if self.allow_bearer:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:]  # 去掉 "Bearer " 前缀

        return None

    def _check_rate_limit(self, record: APIKeyRecord) -> bool:
        """
        检查速率限制

        Returns:
            True 如果通过，False 如果超限
        """
        now = time.time()
        hour_ago = now - 3600

        key_id = record.key_id

        # 获取或创建时间戳列表
        if key_id not in self._rate_limits:
            self._rate_limits[key_id] = []

        timestamps = self._rate_limits[key_id]

        # 清理过期的时间戳
        self._rate_limits[key_id] = [t for t in timestamps if t > hour_ago]

        # 检查是否超限
        if len(self._rate_limits[key_id]) >= record.rate_limit:
            return False

        # 记录本次请求
        self._rate_limits[key_id].append(now)
        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """中间件分发方法"""

        # 检查是否为公开路径
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # OPTIONS 预检请求不需要认证
        if request.method == "OPTIONS":
            return await call_next(request)

        # 提取 API Key
        api_key = self._extract_api_key(request)

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "API Key required. Use X-API-Key header or Authorization: Bearer <key>"
                }
            )

        # 验证 API Key
        is_valid, record = self.store.verify_key(api_key)

        if not is_valid:
            status_code = 403 if record and not record.is_valid() else 401
            message = "API Key expired or disabled" if record else "Invalid API Key"

            return JSONResponse(
                status_code=status_code,
                content={
                    "error": "forbidden" if status_code == 403 else "unauthorized",
                    "message": message
                }
            )

        # 检查速率限制
        if not self._check_rate_limit(record):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Limit: {record.rate_limit}/hour"
                }
            )

        # 注入认证信息到 request.state
        request.state.api_key_record = record
        request.state.client_id = record.client_id
        request.state.key_id = record.key_id
        request.state.scopes = set(record.scopes)

        # 继续处理请求
        return await call_next(request)


class APIKeyAuth:
    """
    API Key 认证管理器

    提供便捷的认证配置和管理接口。
    """

    def __init__(
        self,
        store: Optional[APIKeyStore] = None,
        persist_file: Optional[str] = None
    ):
        """
        初始化认证管理器

        Args:
            store: API Key 存储（None 时自动创建）
            persist_file: 持久化文件路径
        """
        self.store = store or APIKeyStore(persist_file=persist_file)

    def get_middleware(
        self,
        public_paths: Optional[Set[str]] = None,
        public_prefixes: Optional[Set[str]] = None,
        **kwargs
    ) -> APIKeyMiddleware:
        """
        获取配置好的中间件

        Usage:
            auth = APIKeyAuth(persist_file="data/api_keys.json")
            app.add_middleware(APIKeyMiddleware, **auth.get_middleware_config())
        """
        class ConfiguredMiddleware(APIKeyMiddleware):
            def __init__(self, app):
                super().__init__(
                    app,
                    store=self.store,
                    public_paths=public_paths,
                    public_prefixes=public_prefixes,
                    **kwargs
                )

        return ConfiguredMiddleware

    def get_middleware_config(self, **kwargs) -> dict:
        """获取中间件配置参数"""
        return {
            "store": self.store,
            **kwargs
        }

    def create_key(self, client_id: str, name: str, **kwargs) -> APIKeyRecord:
        """创建新的 API Key"""
        return self.store.create_key(client_id, name, **kwargs)

    def verify_key(self, api_key: str) -> Tuple[bool, Optional[APIKeyRecord]]:
        """验证 API Key"""
        return self.store.verify_key(api_key)

    def list_keys(self, client_id: Optional[str] = None) -> list:
        """列出 API Keys"""
        return self.store.list_keys(client_id, enabled_only=False)

    def revoke_key(self, key_id: str) -> bool:
        """吊销 API Key"""
        return self.store.update_key(key_id, enabled=False) is not None

    def delete_key(self, key_id: str) -> bool:
        """删除 API Key"""
        return self.store.delete_key(key_id)


def require_scope(*required_scopes: str):
    """
    装饰器：检查请求是否具有所需权限范围

    Usage:
        @app.get("/admin/stats")
        @require_scope("admin", "stats")
        async def admin_stats(request: Request):
            ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            # 检查是否有认证信息
            if not hasattr(request.state, "scopes"):
                raise HTTPException(status_code=401, detail="Authentication required")

            # 检查权限范围
            request_scopes: Set[str] = request.state.scopes
            missing = set(required_scopes) - request_scopes

            # 如果有 "admin" 权限，跳过其他检查
            if "admin" in request_scopes:
                return await func(request, *args, **kwargs)

            if missing:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing required scopes: {missing}"
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_client_id(request: Request) -> Optional[str]:
    """从请求中获取 client_id"""
    return getattr(request.state, "client_id", None)


def get_key_id(request: Request) -> Optional[str]:
    """从请求中获取 key_id"""
    return getattr(request.state, "key_id", None)


def get_scopes(request: Request) -> Set[str]:
    """从请求中获取权限范围"""
    return getattr(request.state, "scopes", set())
