"""
Tenant Middleware for Multi-tenancy Support

提供请求级别的租户识别和上下文注入。

识别方式:
1. X-Tenant-ID header (推荐)
2. API Key 隐式绑定 (从 API Key 元数据中获取 tenant_id)
3. JWT claims 中的 tenant_id 字段
"""

from __future__ import annotations

import logging
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from tenant import TenantRegistry, TenantContext, Tenant

logger = logging.getLogger("tenant")


class TenantMiddleware:
    """
    多租户中间件
    
    从请求中识别租户，注入到 TenantContext。
    支持 X-Tenant-ID header、API Key 元数据、JWT claims。
    
    使用方式:
        app.add_middleware(TenantMiddleware, registry=tenant_registry)
    """
    
    def __init__(
        self,
        app,
        registry: Optional[TenantRegistry] = None,
        require_tenant: bool = False,
        public_paths: Optional[list] = None,
    ):
        self.app = app
        self.registry = registry or TenantRegistry()
        self.require_tenant = require_tenant
        self.public_paths = public_paths or [
            "/health",
            "/metrics",
            "/tenants",
            "/auth/login",
            "/auth/refresh",
            "/docs",
            "/openapi.json",
        ]
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive, send)
        path = request.url.path
        
        # Skip public paths
        if self._is_public_path(path):
            await self.app(scope, receive, send)
            return
        
        tenant = await self._identify_tenant(request)
        
        if tenant:
            # Valid tenant found
            TenantContext.set(tenant)
            request.state.tenant = tenant
            request.state.tenant_id = tenant.tenant_id
        elif self.require_tenant:
            # Tenant required but not found
            response = JSONResponse(
                {"error": "tenant_required", "detail": "Tenant identification required"},
                status_code=400,
            )
            await response(scope, receive, send)
            return
        
        try:
            await self.app(scope, receive, send)
        finally:
            TenantContext.clear()
    
    def _is_public_path(self, path: str) -> bool:
        """检查是否为公开路径"""
        for public in self.public_paths:
            if path == public or path.startswith(public + "/"):
                return True
        return False
    
    async def _identify_tenant(self, request: Request) -> Optional[Tenant]:
        """
        从请求中识别租户
        
        优先级: X-Tenant-ID > API Key > JWT
        """
        # 1. X-Tenant-ID header (直接指定)
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            tenant = self.registry.get_tenant(tenant_id)
            if tenant and tenant.is_active():
                return tenant
            logger.warning(f"Invalid or inactive tenant: {tenant_id}")
        
        # 2. API Key metadata (隐式绑定)
        if hasattr(request.state, "client_id"):
            # API Key 认证已通过，从元数据获取 tenant_id
            client_id = request.state.client_id
            tenant_id_from_key = request.state.api_key_metadata.get("tenant_id")
            if tenant_id_from_key:
                tenant = self.registry.get_tenant(tenant_id_from_key)
                if tenant and tenant.is_active():
                    return tenant
        
        # 3. JWT claims
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # JWT 认证情况下，从 token claims 中获取
            # 注意: JWT 解析在后续依赖中，这里检查 request.state
            if hasattr(request.state, "jwt_claims"):
                tenant_id_from_jwt = request.state.jwt_claims.get("tenant_id")
                if tenant_id_from_jwt:
                    tenant = self.registry.get_tenant(tenant_id_from_jwt)
                    if tenant and tenant.is_active():
                        return tenant
        
        # 4. 默认租户 (可选，用于开发环境)
        # 返回 None 表示使用默认权限
        
        return None


def get_current_tenant(request: Request) -> Optional[Tenant]:
    """
    从请求中获取当前租户
    
    用于 FastAPI Depends:
        async def handler(tenant: Tenant = Depends(get_current_tenant)):
            ...
    """
    return getattr(request.state, "tenant", None) or TenantContext.get()


def require_tenant(request: Request) -> Tenant:
    """
    要求必须有租户
    
    用于 FastAPI Depends:
        async def handler(tenant: Tenant = Depends(require_tenant)):
            ...
    """
    tenant = get_current_tenant(request)
    if not tenant:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail={"error": "tenant_required", "message": "Tenant context required"},
        )
    return tenant


def check_tenant_feature(feature: str):
    """
    检查租户是否有特定功能
    
    用于 FastAPI Depends:
        async def handler(tenant: Tenant = Depends(check_tenant_feature("analytics"))):
            ...
    """
    async def checker(request: Request) -> Tenant:
        tenant = require_tenant(request)
        if not tenant.has_feature(feature):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "feature": feature,
                    "message": f"Tenant does not have access to feature: {feature}",
                },
            )
        return tenant
    
    return checker
