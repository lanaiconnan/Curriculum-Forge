"""API Client with Retry & Error Classification

Reference: Claude Code src/services/api/client.ts

Implements:
- Retry with exponential backoff
- Error classification (rate limit / timeout / auth / server)
- Request ID tracking for debugging
- Timeout handling

For Curriculum-Forge:
- LLM API calls with automatic retry
- Error recovery strategies
- Request/response logging

Usage:
    client = APIClient(
        base_url="https://api.anthropic.com",
        api_key="...",
        max_retries=3,
        timeout_ms=600_000,
    )
    
    response = await client.request(
        method="POST",
        path="/v1/messages",
        body={...},
    )
    
    # Error classification
    if response.error:
        if response.error.is_rate_limit:
            # Wait and retry
        elif response.error.is_auth_error:
            # Refresh credentials
"""

import os
import time
import uuid
import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


# ─── Error Classification ─────────────────────────────────────────────────────

class ErrorType(Enum):
    UNKNOWN = "unknown"
    RATE_LIMIT = "rate_limit"        # 429
    AUTH = "auth"                    # 401, 403
    NOT_FOUND = "not_found"          # 404
    SERVER = "server"                # 500, 502, 503, 504
    TIMEOUT = "timeout"              # Request timeout
    NETWORK = "network"              # Connection error
    VALIDATION = "validation"        # 400
    CANCELLED = "cancelled"          # Request cancelled


@dataclass
class APIError:
    """Classified API error"""
    type: ErrorType
    message: str
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    retry_after_ms: Optional[int] = None  # For rate limits
    raw_error: Optional[Exception] = None
    
    @property
    def is_retryable(self) -> bool:
        """Can this error be retried?"""
        return self.type in (
            ErrorType.RATE_LIMIT,
            ErrorType.SERVER,
            ErrorType.TIMEOUT,
            ErrorType.NETWORK,
        )
    
    @property
    def is_rate_limit(self) -> bool:
        return self.type == ErrorType.RATE_LIMIT
    
    @property
    def is_auth_error(self) -> bool:
        return self.type == ErrorType.AUTH
    
    @property
    def is_server_error(self) -> bool:
        return self.type == ErrorType.SERVER
    
    @property
    def is_timeout(self) -> bool:
        return self.type == ErrorType.TIMEOUT
    
    @classmethod
    def from_status_code(
        cls,
        status_code: int,
        message: str,
        request_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> "APIError":
        """Classify error from HTTP status code"""
        if status_code == 429:
            retry_after = None
            if headers:
                # Parse Retry-After header
                ra = headers.get("retry-after") or headers.get("Retry-After")
                if ra:
                    try:
                        retry_after = int(ra) * 1000  # seconds to ms
                    except ValueError:
                        pass
            return cls(
                type=ErrorType.RATE_LIMIT,
                message=message,
                status_code=status_code,
                request_id=request_id,
                retry_after_ms=retry_after,
            )
        elif status_code in (401, 403):
            return cls(
                type=ErrorType.AUTH,
                message=message,
                status_code=status_code,
                request_id=request_id,
            )
        elif status_code == 404:
            return cls(
                type=ErrorType.NOT_FOUND,
                message=message,
                status_code=status_code,
                request_id=request_id,
            )
        elif status_code == 400:
            return cls(
                type=ErrorType.VALIDATION,
                message=message,
                status_code=status_code,
                request_id=request_id,
            )
        elif status_code >= 500:
            return cls(
                type=ErrorType.SERVER,
                message=message,
                status_code=status_code,
                request_id=request_id,
            )
        else:
            return cls(
                type=ErrorType.UNKNOWN,
                message=message,
                status_code=status_code,
                request_id=request_id,
            )
    
    @classmethod
    def from_exception(cls, exc: Exception) -> "APIError":
        """Classify error from exception"""
        import asyncio
        
        if isinstance(exc, asyncio.TimeoutError):
            return cls(type=ErrorType.TIMEOUT, message=str(exc), raw_error=exc)
        elif isinstance(exc, asyncio.CancelledError):
            return cls(type=ErrorType.CANCELLED, message=str(exc), raw_error=exc)
        elif isinstance(exc, ConnectionError):
            return cls(type=ErrorType.NETWORK, message=str(exc), raw_error=exc)
        else:
            return cls(type=ErrorType.UNKNOWN, message=str(exc), raw_error=exc)


# ─── Retry Configuration ──────────────────────────────────────────────────────

@dataclass
class RetryConfig:
    """Retry configuration"""
    max_retries: int = 3
    initial_delay_ms: int = 1000      # 1 second
    max_delay_ms: int = 60_000        # 60 seconds
    backoff_multiplier: float = 2.0
    jitter: bool = True               # Add random jitter to prevent thundering herd
    
    # Which error types to retry
    retryable_types: List[ErrorType] = field(default_factory=lambda: [
        ErrorType.RATE_LIMIT,
        ErrorType.SERVER,
        ErrorType.TIMEOUT,
        ErrorType.NETWORK,
    ])
    
    def get_delay_ms(self, attempt: int) -> int:
        """Calculate delay for given attempt (0-indexed)"""
        import random
        
        delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)
        delay = min(delay, self.max_delay_ms)
        
        if self.jitter:
            # Add 0-25% jitter
            delay = delay * (1 + random.random() * 0.25)
        
        return int(delay)


# ─── API Response ─────────────────────────────────────────────────────────────

@dataclass
class APIResponse:
    """API response with error handling"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[APIError] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    duration_ms: int = 0
    attempts: int = 1
    
    @classmethod
    def ok(
        cls,
        data: Dict[str, Any],
        status_code: int = 200,
        request_id: Optional[str] = None,
        duration_ms: int = 0,
        attempts: int = 1,
    ) -> "APIResponse":
        return cls(
            success=True,
            data=data,
            status_code=status_code,
            request_id=request_id,
            duration_ms=duration_ms,
            attempts=attempts,
        )
    
    @classmethod
    def fail(
        cls,
        error: APIError,
        duration_ms: int = 0,
        attempts: int = 1,
    ) -> "APIResponse":
        return cls(
            success=False,
            error=error,
            status_code=error.status_code,
            request_id=error.request_id,
            duration_ms=duration_ms,
            attempts=attempts,
        )


# ─── API Client ───────────────────────────────────────────────────────────────

class APIClient:
    """
    HTTP API client with retry and error classification.
    
    Features:
    - Exponential backoff with jitter
    - Error classification from status codes and exceptions
    - Request ID tracking
    - Timeout handling
    - Async support
    
    Usage:
        client = APIClient(
            base_url="https://api.example.com",
            api_key="...",
            max_retries=3,
        )
        
        response = await client.post("/v1/messages", body={...})
        
        if response.success:
            print(response.data)
        else:
            print(f"Error: {response.error.message}")
    """
    
    REQUEST_ID_HEADER = "x-client-request-id"
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        max_retries: int = 3,
        timeout_ms: int = 600_000,  # 10 minutes
        retry_config: Optional[RetryConfig] = None,
        default_headers: Optional[Dict[str, str]] = None,
        on_retry: Optional[Callable[[int, APIError], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.auth_token = auth_token
        self.timeout_ms = timeout_ms
        self.retry_config = retry_config or RetryConfig(max_retries=max_retries)
        self.default_headers = default_headers or {}
        self._on_retry = on_retry
    
    def _get_headers(self, request_id: Optional[str] = None) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "curriculum-forge/1.0",
            **self.default_headers,
        }
        
        if self.api_key:
            headers["x-api-key"] = self.api_key
        elif self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        if request_id:
            headers[self.REQUEST_ID_HEADER] = request_id
        
        return headers
    
    async def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_ms: Optional[int] = None,
    ) -> APIResponse:
        """
        Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (will be joined with base_url)
            body: Request body (will be JSON encoded)
            params: Query parameters
            headers: Additional headers
            timeout_ms: Override default timeout
        
        Returns:
            APIResponse with success/error
        """
        import aiohttp
        
        url = f"{self.base_url}{path}"
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        all_headers = self._get_headers(request_id)
        if headers:
            all_headers.update(headers)
        
        timeout = (timeout_ms or self.timeout_ms) / 1000  # ms to seconds
        
        attempt = 0
        last_error: Optional[APIError] = None
        
        while attempt <= self.retry_config.max_retries:
            try:
                async with aiohttp.ClientSession() as session:
                    kwargs = {
                        "headers": all_headers,
                        "timeout": aiohttp.ClientTimeout(total=timeout),
                    }
                    if body:
                        kwargs["json"] = body
                    if params:
                        kwargs["params"] = params
                    
                    async with session.request(method, url, **kwargs) as resp:
                        duration_ms = int((time.time() - start_time) * 1000)
                        
                        # Get response body
                        try:
                            data = await resp.json()
                        except Exception:
                            text = await resp.text()
                            data = {"raw": text}
                        
                        # Success
                        if 200 <= resp.status < 300:
                            return APIResponse.ok(
                                data=data,
                                status_code=resp.status,
                                request_id=request_id,
                                duration_ms=duration_ms,
                                attempts=attempt + 1,
                            )
                        
                        # Error - classify
                        error = APIError.from_status_code(
                            status_code=resp.status,
                            message=data.get("error", {}).get("message", str(data)),
                            request_id=request_id,
                            headers=dict(resp.headers),
                        )
                        
                        # Check if retryable
                        if error.type in self.retry_config.retryable_types and attempt < self.retry_config.max_retries:
                            last_error = error
                            delay_ms = self.retry_config.get_delay_ms(attempt)
                            
                            # Use retry_after from rate limit if available
                            if error.retry_after_ms:
                                delay_ms = max(delay_ms, error.retry_after_ms)
                            
                            logger.warning(
                                f"API error (attempt {attempt + 1}): {error.message}. "
                                f"Retrying in {delay_ms}ms..."
                            )
                            
                            if self._on_retry:
                                self._on_retry(attempt + 1, error)
                            
                            await asyncio.sleep(delay_ms / 1000)
                            attempt += 1
                            continue
                        
                        # Non-retryable or max retries reached
                        return APIResponse.fail(
                            error=error,
                            duration_ms=duration_ms,
                            attempts=attempt + 1,
                        )
            
            except asyncio.TimeoutError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                error = APIError.from_exception(e)
                
                if attempt < self.retry_config.max_retries:
                    last_error = error
                    delay_ms = self.retry_config.get_delay_ms(attempt)
                    logger.warning(f"Timeout (attempt {attempt + 1}). Retrying in {delay_ms}ms...")
                    await asyncio.sleep(delay_ms / 1000)
                    attempt += 1
                    continue
                
                return APIResponse.fail(error=error, duration_ms=duration_ms, attempts=attempt + 1)
            
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                error = APIError.from_exception(e)
                
                if error.type in self.retry_config.retryable_types and attempt < self.retry_config.max_retries:
                    last_error = error
                    delay_ms = self.retry_config.get_delay_ms(attempt)
                    logger.warning(f"Error (attempt {attempt + 1}): {e}. Retrying in {delay_ms}ms...")
                    await asyncio.sleep(delay_ms / 1000)
                    attempt += 1
                    continue
                
                return APIResponse.fail(error=error, duration_ms=duration_ms, attempts=attempt + 1)
        
        # Should not reach here, but just in case
        duration_ms = int((time.time() - start_time) * 1000)
        return APIResponse.fail(
            error=last_error or APIError(type=ErrorType.UNKNOWN, message="Max retries exceeded"),
            duration_ms=duration_ms,
            attempts=attempt,
        )
    
    # Convenience methods
    async def get(self, path: str, **kwargs) -> APIResponse:
        return await self.request("GET", path, **kwargs)
    
    async def post(self, path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> APIResponse:
        return await self.request("POST", path, body=body, **kwargs)
    
    async def put(self, path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> APIResponse:
        return await self.request("PUT", path, body=body, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> APIResponse:
        return await self.request("DELETE", path, **kwargs)


# ─── Sync Wrapper ─────────────────────────────────────────────────────────────

class SyncAPIClient:
    """
    Synchronous wrapper for APIClient.
    
    For environments without async support.
    """
    
    def __init__(self, *args, **kwargs):
        self._client = APIClient(*args, **kwargs)
    
    def request(self, *args, **kwargs) -> APIResponse:
        return asyncio.run(self._client.request(*args, **kwargs))
    
    def get(self, path: str, **kwargs) -> APIResponse:
        return asyncio.run(self._client.get(path, **kwargs))
    
    def post(self, path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> APIResponse:
        return asyncio.run(self._client.post(path, body=body, **kwargs))
    
    def put(self, path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> APIResponse:
        return asyncio.run(self._client.put(path, body=body, **kwargs))
    
    def delete(self, path: str, **kwargs) -> APIResponse:
        return asyncio.run(self._client.delete(path, **kwargs))


# ─── Decorators ───────────────────────────────────────────────────────────────

def with_retry(
    max_retries: int = 3,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
):
    """
    Decorator to add retry logic to any function.
    
    Usage:
        @with_retry(max_retries=3)
        def flaky_operation():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            config = RetryConfig(max_retries=max_retries)
            attempt = 0
            
            while attempt <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    if attempt >= max_retries:
                        raise
                    
                    delay_ms = config.get_delay_ms(attempt)
                    if on_retry:
                        on_retry(attempt + 1, e)
                    
                    await asyncio.sleep(delay_ms / 1000)
                    attempt += 1
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            config = RetryConfig(max_retries=max_retries)
            attempt = 0
            
            while attempt <= max_retries:
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    if attempt >= max_retries:
                        raise
                    
                    delay_ms = config.get_delay_ms(attempt)
                    if on_retry:
                        on_retry(attempt + 1, e)
                    
                    time.sleep(delay_ms / 1000)
                    attempt += 1
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
