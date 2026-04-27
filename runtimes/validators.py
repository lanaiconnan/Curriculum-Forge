"""
Gateway 请求验证器（Pydantic models）
集中所有端点请求格式校验，统一错误信息，提高 API 健壮性。
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 通用辅助 ─────────────────────────────────────────────────────────

def _strip(value: str) -> str:
    return value.strip() if isinstance(value, str) else value


# ── 权限格式校验 ──────────────────────────────────────────────────────

PERMISSION_RE = re.compile(r"^(\*|[a-z][a-z0-9_-]*)\.(\*|[a-z][a-z0-9_-]*)$")

ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


# ── 基础校验类 ───────────────────────────────────────────────────────

class BaseValidator(BaseModel):
    """所有请求模型的基类：统一 JSON body 解析"""

    model_config = ConfigDict(
        extra="forbid",          # 默认禁止未知字段
        str_strip_whitespace=True,
    )


# ── Jobs ─────────────────────────────────────────────────────────────

class JobCreateRequest(BaseValidator):
    """POST /jobs — 创建任务"""
    profile: Optional[str] = None
    proposal: Optional[Dict[str, Any]] = None
    config_overrides: Optional[Dict[str, Any]] = Field(None, description="运行时配置覆盖")
    description: Optional[str] = Field(None, max_length=512)

    @field_validator("profile")
    @classmethod
    def profile_name(cls, v):
        if v is not None:
            v = _strip(v)
            if not v:
                return None
            if not ROLE_NAME_RE.match(v) and not v.replace("_", "").isalnum():
                raise ValueError("Invalid profile name format")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v):
        if v is not None and not v.strip():
            return None
        return v

    @field_validator("proposal")
    @classmethod
    def proposal_or_profile(cls, v, info):
        # 业务层校验：proposal 或 profile 至少有一个
        if v is None and info.data.get("profile") is None:
            raise ValueError("Either 'profile' or 'proposal' is required")
        return v

    model_config = ConfigDict(extra="allow")


class BatchJobRequest(BaseValidator):
    """POST /jobs/batch — 批量创建任务"""
    jobs: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)

    @field_validator("jobs")
    @classmethod
    def each_job_has_profile_or_proposal(cls, v):
        for i, job in enumerate(v):
            if "profile" not in job and "proposal" not in job:
                raise ValueError(f"Job[{i}]: must have 'profile' or 'proposal'")
        return v


class JobConfigUpdateRequest(BaseValidator):
    """PATCH /jobs/{job_id}/config — 更新运行时配置"""
    config_overrides: Dict[str, Any] = Field(..., min_length=1)
    merge_strategy: Optional[str] = Field("replace", description="replace | merge")


class JobCompareRequest(BaseValidator):
    """POST /jobs/compare — 比较任务"""
    job_ids: List[str] = Field(..., min_length=1, max_length=10)

    @field_validator("job_ids")
    @classmethod
    def unique_job_ids(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate job IDs in list")
        return v


# ── Schedules ────────────────────────────────────────────────────────

class ScheduleCreateRequest(BaseValidator):
    """POST /schedules"""
    name: str = Field(..., min_length=1, max_length=64)
    profile: str = Field(..., min_length=1, max_length=128)
    config_overrides: Optional[Dict[str, Any]] = None
    interval_seconds: int = Field(..., gt=0, le=86400 * 30)
    enabled: bool = True
    description: Optional[str] = Field(None, max_length=512)


class ScheduleUpdateRequest(BaseValidator):
    """PATCH /schedules/{schedule_id}"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    interval_seconds: Optional[int] = Field(None, gt=0, le=86400 * 30)
    enabled: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=512)


# ── Templates ───────────────────────────────────────────────────────

class TemplateCreateRequest(BaseValidator):
    """POST /templates"""
    name: str = Field(..., min_length=1, max_length=64)
    profile: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    config_overrides: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate tags")
        return list(set(v))

    @field_validator("tags")
    @classmethod
    def tag_format(cls, v):
        for tag in v:
            if not re.match(r"^[a-z0-9_-]{1,32}$", tag):
                raise ValueError(f"Invalid tag format: '{tag}'")
        return v


class TemplateUpdateRequest(BaseValidator):
    """PUT /templates/{template_id}"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=512)
    config_overrides: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

    @field_validator("tags")
    @classmethod
    def tag_format(cls, v):
        if v is None:
            return v
        for tag in v:
            if not re.match(r"^[a-z0-9_-]{1,32}$", tag):
                raise ValueError(f"Invalid tag format: '{tag}'")
        return list(set(v))


# ── Roles ───────────────────────────────────────────────────────────

class RoleCreateRequest(BaseValidator):
    """POST /roles"""
    name: str = Field(..., min_length=1, max_length=32)
    display_name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    permissions: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def role_name_format(cls, v):
        v = _strip(v)
        if not ROLE_NAME_RE.match(v):
            raise ValueError(
                "Role name must be 1-32 chars, lowercase letters/digits/hyphens/underscores, "
                "starting with a letter"
            )
        return v

    @field_validator("permissions")
    @classmethod
    def permissions_format(cls, v):
        for p in v:
            if not PERMISSION_RE.match(p):
                raise ValueError(f"Invalid permission format: '{p}' (expected resource.action)")
        return v


class RoleUpdateRequest(BaseValidator):
    """PUT /roles/{name}"""
    display_name: Optional[str] = Field(None, max_length=64)
    description: Optional[str] = Field(None, max_length=256)


class RolePermissionRequest(BaseValidator):
    """POST|DELETE /roles/{name}/permissions"""
    permissions: List[str] = Field(..., min_length=1)

    @field_validator("permissions")
    @classmethod
    def permissions_format(cls, v):
        for p in v:
            if not PERMISSION_RE.match(p):
                raise ValueError(f"Invalid permission format: '{p}'")
        return v


# ── Users ───────────────────────────────────────────────────────────

class UserCreateRequest(BaseValidator):
    """POST /users — 创建用户（JSON body 替代 query params）"""
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[str] = Field(None, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    roles: List[str] = Field(default_factory=lambda: ["viewer"])

    @field_validator("username")
    @classmethod
    def username_format(cls, v):
        v = _strip(v)
        if not re.match(r"^[a-z][a-z0-9_-]{1,62}$", v):
            raise ValueError(
                "Username must be 2-64 chars, lowercase letters/digits/hyphens/underscores, "
                "starting with a letter"
            )
        return v

    @field_validator("email")
    @classmethod
    def email_format(cls, v):
        if v is None:
            return v
        v = _strip(v)
        if v and not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        # 简单强度检查
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("roles")
    @classmethod
    def roles_valid(cls, v):
        for r in v:
            if not ROLE_NAME_RE.match(r):
                raise ValueError(f"Invalid role name: '{r}'")
        return v


class UserUpdateRequest(BaseValidator):
    """PATCH /users/{user_id}"""
    email: Optional[str] = Field(None, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    enabled: Optional[bool] = None
    roles: Optional[List[str]] = None

    @field_validator("email")
    @classmethod
    def email_format(cls, v):
        if v is None:
            return v
        v = _strip(v)
        if v and not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("roles")
    @classmethod
    def roles_valid(cls, v):
        if v is None:
            return v
        for r in v:
            if not ROLE_NAME_RE.match(r):
                raise ValueError(f"Invalid role name: '{r}'")
        return v


class UserPasswordChangeRequest(BaseValidator):
    """POST /users/{user_id}/password"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError("New password must be at least 6 characters")
        return v


# ── API Keys ─────────────────────────────────────────────────────────

class APIKeyCreateRequest(BaseValidator):
    """POST /auth/keys"""
    client_id: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    scope: Optional[str] = Field(None)  # Accept single scope like "write"
    rate_limit_per_hour: int = Field(default=1000, ge=1, le=10000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyUpdateRequest(BaseValidator):
    """PUT /auth/keys/{key_id}"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    scopes: Optional[List[str]] = None
    enabled: Optional[bool] = None


# ── Feishu Webhook ───────────────────────────────────────────────────

class FeishuWebhookRequest(BaseValidator):
    """POST /webhooks/feishu — 飞书事件回调"""
    event: Dict[str, Any] = Field(...)
    schema_version: Optional[str] = Field("2.0", alias="schema")  # 飞书事件订阅版本


# ── Config Overrides ─────────────────────────────────────────────────

class ConfigOverrideRequest(BaseValidator):
    """PUT /config/overrides — 全局配置覆盖"""
    config_overrides: Dict[str, Any] = Field(..., min_length=1)
    profile: Optional[str] = Field(None, max_length=128)


# ── Response Models（可选，用于 OpenAPI 文档） ─────────────────────────

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    detail: List[Dict[str, Any]]  # Pydantic 错误列表格式


# ── ACP Requests ────────────────────────────────────────────────────

class RefreshRequest(BaseModel):
    """POST /auth/refresh — 刷新 access token"""
    refresh_token: str


class ACPRegisterRequest(BaseModel):
    """POST /acp/register — 注册 ACP agent"""
    agent_id: str
    name: Optional[str] = None
    role: Optional[str] = "general"
    capabilities: List[str] = Field(default_factory=list)


class ACPHeartbeatRequest(BaseModel):
    """POST /acp/{agent_id}/heartbeat"""
    progress_pct: Optional[float] = Field(None, ge=0, le=100)
    message: Optional[str] = ""


class ACPCompleteTaskRequest(BaseModel):
    """POST /acp/{agent_id}/tasks/{task_id}/complete"""
    result: Dict[str, Any] = Field(default_factory=dict)


class PluginConfigRequest(BaseModel):
    """PUT /plugins/{name}/config — 更新插件配置"""
    pass  # 动态 schema，由 plugin 自己定义


class WorkflowCreateRequest(BaseModel):
    """POST /workflows — 创建工作流"""
    name: Optional[str] = None
    description: Optional[str] = ""
    tasks: List[Dict[str, Any]] = Field(default_factory=list)

