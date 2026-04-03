"""Unit tests for services/api.py — API Client with Retry & Error Classification

Run: pytest tests/unit/test_api.py -v
"""

import pytest
import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api import (
    ErrorType,
    APIError,
    RetryConfig,
    APIResponse,
    APIClient,
    SyncAPIClient,
    with_retry,
)


# ─── APIError ─────────────────────────────────────────────────────────────────

class TestAPIError:
    def test_from_status_code_rate_limit(self):
        error = APIError.from_status_code(429, "Too many requests")
        assert error.type == ErrorType.RATE_LIMIT
        assert error.is_rate_limit
        assert error.is_retryable

    def test_from_status_code_auth(self):
        error = APIError.from_status_code(401, "Unauthorized")
        assert error.type == ErrorType.AUTH
        assert error.is_auth_error
        assert not error.is_retryable

    def test_from_status_code_server(self):
        error = APIError.from_status_code(503, "Service unavailable")
        assert error.type == ErrorType.SERVER
        assert error.is_server_error
        assert error.is_retryable

    def test_from_status_code_validation(self):
        error = APIError.from_status_code(400, "Bad request")
        assert error.type == ErrorType.VALIDATION
        assert not error.is_retryable

    def test_from_status_code_unknown(self):
        error = APIError.from_status_code(418, "I'm a teapot")
        assert error.type == ErrorType.UNKNOWN

    def test_retry_after_header(self):
        error = APIError.from_status_code(
            429, "Rate limited", headers={"retry-after": "30"}
        )
        assert error.retry_after_ms == 30_000

    def test_from_exception_timeout(self):
        error = APIError.from_exception(asyncio.TimeoutError())
        assert error.type == ErrorType.TIMEOUT
        assert error.is_timeout
        assert error.is_retryable

    def test_from_exception_connection(self):
        error = APIError.from_exception(ConnectionError("Network unreachable"))
        assert error.type == ErrorType.NETWORK
        assert error.is_retryable

    def test_from_exception_unknown(self):
        error = APIError.from_exception(ValueError("Bad value"))
        assert error.type == ErrorType.UNKNOWN
        assert not error.is_retryable


# ─── RetryConfig ──────────────────────────────────────────────────────────────

class TestRetryConfig:
    def test_default_config(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay_ms == 1000
        assert config.max_delay_ms == 60_000

    def test_get_delay_exponential(self):
        config = RetryConfig(jitter=False)
        assert config.get_delay_ms(0) == 1000
        assert config.get_delay_ms(1) == 2000
        assert config.get_delay_ms(2) == 4000

    def test_get_delay_max_cap(self):
        config = RetryConfig(
            initial_delay_ms=10_000,
            max_delay_ms=30_000,
            jitter=False,
        )
        assert config.get_delay_ms(0) == 10_000
        assert config.get_delay_ms(1) == 20_000
        assert config.get_delay_ms(2) == 30_000  # capped
        assert config.get_delay_ms(3) == 30_000  # still capped

    def test_jitter_adds_randomness(self):
        config = RetryConfig(jitter=True)
        delays = [config.get_delay_ms(0) for _ in range(10)]
        # All should be around 1000 but with jitter
        assert all(1000 <= d <= 1250 for d in delays)  # 0-25% jitter


# ─── APIResponse ─────────────────────────────────────────────────────────────

class TestAPIResponse:
    def test_ok_response(self):
        resp = APIResponse.ok(
            data={"result": "success"},
            status_code=200,
            request_id="req-123",
        )
        assert resp.success
        assert resp.data["result"] == "success"
        assert resp.error is None

    def test_fail_response(self):
        error = APIError(type=ErrorType.SERVER, message="Internal error")
        resp = APIResponse.fail(error=error)
        assert not resp.success
        assert resp.error.message == "Internal error"
        assert resp.data is None


# ─── APIClient (Mock Tests) ───────────────────────────────────────────────────

class TestAPIClient:
    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Test successful request (no actual network call)"""
        # This test would require mocking aiohttp
        # For now, just test the configuration
        client = APIClient(
            base_url="https://api.example.com",
            api_key="test-key",
            max_retries=2,
        )
        
        assert client.base_url == "https://api.example.com"
        assert client.api_key == "test-key"
        assert client.retry_config.max_retries == 2

    def test_headers_with_api_key(self):
        client = APIClient(
            base_url="https://api.example.com",
            api_key="my-key",
        )
        headers = client._get_headers(request_id="req-1")
        
        assert headers["x-api-key"] == "my-key"
        assert headers["Content-Type"] == "application/json"
        assert headers[client.REQUEST_ID_HEADER] == "req-1"

    def test_headers_with_auth_token(self):
        client = APIClient(
            base_url="https://api.example.com",
            auth_token="my-token",
        )
        headers = client._get_headers()
        
        assert headers["Authorization"] == "Bearer my-token"

    def test_default_headers_merged(self):
        client = APIClient(
            base_url="https://api.example.com",
            default_headers={"X-Custom": "value"},
        )
        headers = client._get_headers()
        
        assert headers["X-Custom"] == "value"


# ─── SyncAPIClient ────────────────────────────────────────────────────────────

class TestSyncAPIClient:
    def test_wrapper_creation(self):
        client = SyncAPIClient(
            base_url="https://api.example.com",
            api_key="test-key",
        )
        
        assert client._client.base_url == "https://api.example.com"


# ─── with_retry Decorator ─────────────────────────────────────────────────────

class TestWithRetry:
    def test_sync_success(self):
        call_count = [0]
        
        @with_retry(max_retries=3)
        def operation():
            call_count[0] += 1
            return "success"
        
        result = operation()
        assert result == "success"
        assert call_count[0] == 1

    def test_sync_retry_then_success(self):
        call_count = [0]
        
        @with_retry(max_retries=3, retryable_exceptions=(ValueError,))
        def operation():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = operation()
        assert result == "success"
        assert call_count[0] == 3

    def test_sync_max_retries_exceeded(self):
        call_count = [0]
        
        @with_retry(max_retries=2, retryable_exceptions=(ValueError,))
        def operation():
            call_count[0] += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            operation()
        
        assert call_count[0] == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_async_success(self):
        call_count = [0]
        
        @with_retry(max_retries=3)
        async def operation():
            call_count[0] += 1
            return "success"
        
        result = await operation()
        assert result == "success"
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_async_retry_then_success(self):
        call_count = [0]
        
        @with_retry(max_retries=3, retryable_exceptions=(ValueError,))
        async def operation():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Temporary error")
            return "success"
        
        result = await operation()
        assert result == "success"
        assert call_count[0] == 2

    def test_on_retry_callback(self):
        call_count = [0]
        retry_events = []
        
        def on_retry(attempt, exc):
            retry_events.append((attempt, str(exc)))
        
        @with_retry(max_retries=2, retryable_exceptions=(ValueError,), on_retry=on_retry)
        def operation():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Error")
            return "success"
        
        result = operation()
        assert result == "success"
        assert len(retry_events) == 2
        assert retry_events[0][0] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
