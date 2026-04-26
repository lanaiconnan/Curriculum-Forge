"""
敏感信息脱敏模块

提供 API Key 掩码、用户信息脱敏、日志脱敏、安全响应头等功能。
"""

import hashlib
import re
from typing import Any, Dict, List, Optional, Set


# ── API Key 掩码 ──────────────────────────────────────────────────────────────

def mask_api_key(api_key: str, visible_prefix: int = 7, visible_suffix: int = 4) -> str:
    """
    对 API Key 进行掩码处理

    cf_live_abc123xyz789 → cf_live_abc****789

    Args:
        api_key: 原始 API Key
        visible_prefix: 保留前缀字符数（含前缀标识）
        visible_suffix: 保留后缀字符数

    Returns:
        掩码后的 API Key
    """
    if not api_key or len(api_key) <= visible_prefix + visible_suffix:
        return "****"

    return api_key[:visible_prefix] + "****" + api_key[-visible_suffix:]


def hash_api_key(api_key: str) -> str:
    """
    对 API Key 进行 SHA-256 哈希（用于存储）

    仅存储哈希值，验证时对传入 key 做同样哈希后比对。

    Args:
        api_key: 原始 API Key

    Returns:
        SHA-256 哈希的十六进制字符串
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


# ── 用户信息脱敏 ──────────────────────────────────────────────────────────────

# UserRecord 中不应暴露给前端的安全字段
USER_SENSITIVE_FIELDS: Set[str] = {
    "password_hash",
    "failed_login_attempts",
    "locked_until",
}

# API Key 响应中不应暴露的字段（列表场景）
APIKEY_LIST_SENSITIVE_FIELDS: Set[str] = {
    "api_key",  # 列表和查询时不返回完整 key
}

# API Key 响应中不应暴露的字段（单条查询场景）
APIKEY_GET_SENSITIVE_FIELDS: Set[str] = {
    "api_key",  # 查询时只返回掩码
}


def sanitize_user_dict(user_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    脱敏用户字典：移除安全敏感字段

    Args:
        user_dict: 原始用户字典（可能来自 UserRecord.to_dict()）

    Returns:
        脱敏后的用户字典
    """
    return {k: v for k, v in user_dict.items() if k not in USER_SENSITIVE_FIELDS}


def sanitize_user_response(
    user_id: str,
    username: str,
    email: Optional[str],
    full_name: Optional[str],
    roles: List[str],
    enabled: bool = True,
    last_login_at: Optional[float] = None,
    created_at: Optional[float] = None,
    updated_at: Optional[float] = None,
) -> Dict[str, Any]:
    """
    构建安全的用户响应字典（显式字段，不包含敏感信息）

    Returns:
        脱敏后的用户响应
    """
    resp = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "full_name": full_name,
        "roles": roles,
        "enabled": enabled,
    }
    if last_login_at is not None:
        resp["last_login_at"] = last_login_at
    if created_at is not None:
        resp["created_at"] = created_at
    if updated_at is not None:
        resp["updated_at"] = updated_at
    return resp


def sanitize_apikey_response(
    key_id: str,
    api_key: Optional[str],
    client_id: str,
    name: str,
    scopes: List[str],
    enabled: bool = True,
    expires_at: Optional[float] = None,
    last_used_at: Optional[float] = None,
    rate_limit: int = 1000,
    created_at: Optional[float] = None,
    mask_key: bool = True,
) -> Dict[str, Any]:
    """
    构建安全的 API Key 响应字典

    Args:
        mask_key: True → 掩码显示（列表/查询），False → 完整显示（仅创建时）

    Returns:
        脱敏后的 API Key 响应
    """
    resp = {
        "key_id": key_id,
        "client_id": client_id,
        "name": name,
        "scopes": scopes,
        "enabled": enabled,
        "rate_limit": rate_limit,
    }
    if api_key is not None:
        resp["api_key"] = mask_api_key(api_key) if mask_key else api_key
    if expires_at is not None:
        resp["expires_at"] = expires_at
    if last_used_at is not None:
        resp["last_used_at"] = last_used_at
    if created_at is not None:
        resp["created_at"] = created_at
    return resp


# ── 日志脱敏 ───────────────────────────────────────────────────────────────────

# 需要脱敏的 key 模式
_SENSITIVE_KEY_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"apikey", re.IGNORECASE),
    re.compile(r"api-key", re.IGNORECASE),
    re.compile(r"access_key", re.IGNORECASE),
    re.compile(r"private_key", re.IGNORECASE),
    re.compile(r"credentials?", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
]

# 需要脱敏的 value 模式（如 API Key 格式）
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"cf_live_[A-Za-z0-9_\-]{20,}"),  # Curriculum-Forge API Key
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"),    # Bearer token
    re.compile(r"sk-[A-Za-z0-9]{20,}"),           # OpenAI-style key
]


def sanitize_log_value(key: str, value: Any) -> Any:
    """
    脱敏日志中的单个值

    Args:
        key: 字段名
        value: 字段值

    Returns:
        脱敏后的值
    """
    if value is None:
        return None

    # 检查 key 是否匹配敏感模式
    for pattern in _SENSITIVE_KEY_PATTERNS:
        if pattern.search(str(key)):
            str_val = str(value)
            if len(str_val) <= 8:
                return "****"
            return str_val[:3] + "****"

    # 检查 value 是否匹配敏感值模式
    str_val = str(value)
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        if pattern.search(str_val):
            return mask_api_key(str_val)

    return value


def sanitize_log_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    脱敏日志字典中的敏感字段

    Args:
        data: 原始字典

    Returns:
        脱敏后的字典
    """
    return {k: sanitize_log_value(k, v) for k, v in data.items()}


def sanitize_log_message(message: str) -> str:
    """
    脱敏日志消息中的敏感信息

    Args:
        message: 原始日志消息

    Returns:
        脱敏后的消息
    """
    result = message
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        result = pattern.sub("****", result)
    return result


# ── 错误信息脱敏 ───────────────────────────────────────────────────────────────

# 需要从错误信息中移除的路径模式
_PATH_PATTERNS = [
    re.compile(r"/Users/[^/\s]+"),     # macOS 用户路径
    re.compile(r"/home/[^/\s]+"),      # Linux 用户路径
    re.compile(r"C:\\Users\\[^\\\s]+"), # Windows 用户路径
    re.compile(r"/var/[^/\s]+"),        # 服务器路径
]

_INTERNAL_ERROR_PATTERNS = [
    re.compile(r"Traceback[\s\S]*?(?=\n\n|\Z)"),     # Python traceback
    re.compile(r"File\s+\"[^\"]+\"", re.MULTILINE),  # File references
    re.compile(r"Error:\s*.*at\s+\w+", re.IGNORECASE),  # Stack traces
]


def sanitize_error_message(message: str) -> str:
    """
    脱敏错误信息：移除内部路径、堆栈跟踪等

    Args:
        message: 原始错误信息

    Returns:
        脱敏后的错误信息
    """
    result = message

    # 替换用户路径
    for pattern in _PATH_PATTERNS:
        result = pattern.sub("[PATH]", result)

    # 移除堆栈跟踪
    for pattern in _INTERNAL_ERROR_PATTERNS:
        result = pattern.sub("[INTERNAL_ERROR]", result)

    return result


# ── 安全响应头 ─────────────────────────────────────────────────────────────────

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",  # 防止敏感 API 响应被缓存
    "Pragma": "no-cache",
}


def get_security_headers() -> Dict[str, str]:
    """获取安全响应头字典"""
    return dict(SECURITY_HEADERS)


# ── Email 脱敏 ─────────────────────────────────────────────────────────────────

def mask_email(email: str) -> str:
    """
    对 Email 进行掩码处理

    user@example.com → u***@example.com

    Args:
        email: 原始 Email

    Returns:
        掩码后的 Email
    """
    if not email or "@" not in email:
        return email

    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"{local}@{domain}"

    return f"{local[0]}***@{domain}"
