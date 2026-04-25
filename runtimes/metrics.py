"""
Prometheus metrics for Curriculum-Forge Gateway.

Exposes standard RED metrics (Request, Error, Duration) plus
domain-specific metrics for jobs, agents, and coordination.
"""

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# Standard HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    ['method', 'endpoint']
)

# Job metrics
JOBS_TOTAL = Counter(
    'jobs_total',
    'Total number of jobs created',
    ['profile', 'state']
)

JOBS_ACTIVE = Gauge(
    'jobs_active',
    'Number of currently active jobs (PENDING or RUNNING)',
    []
)

JOBS_COMPLETED_TOTAL = Counter(
    'jobs_completed_total',
    'Total number of jobs completed (SUCCESS or FAILED)',
    ['profile', 'state']
)

JOB_DURATION_SECONDS = Histogram(
    'job_duration_seconds',
    'Duration of job execution in seconds',
    ['profile'],
    buckets=[10, 30, 60, 120, 300, 600, 1200, 3600]
)

JOB_ITERATIONS_TOTAL = Counter(
    'job_iterations_total',
    'Total iterations across all jobs',
    ['profile']
)

# Task metrics (Coordinator)
TASKS_TOTAL = Counter(
    'coordinator_tasks_total',
    'Total number of tasks processed by coordinator',
    ['type', 'status']
)

TASKS_QUEUED = Gauge(
    'coordinator_tasks_queued',
    'Number of tasks currently in queue',
    ['type']
)

# Agent metrics (ACP)
AGENTS_REGISTERED = Gauge(
    'acp_agents_registered',
    'Number of currently registered ACP agents',
    []
)

AGENT_HEARTBEATS = Counter(
    'acp_agent_heartbeats_total',
    'Total number of agent heartbeats received',
    ['agent_id']
)

AGENT_TASKS_CLAIMED = Counter(
    'acp_tasks_claimed_total',
    'Total number of tasks claimed by agents',
    ['agent_id']
)

AGENT_TASKS_COMPLETED = Counter(
    'acp_tasks_completed_total',
    'Total number of tasks completed by agents',
    ['agent_id', 'status']
)

# Channel metrics
CHANNEL_WEBHOOKS_TOTAL = Counter(
    'channel_webhooks_total',
    'Total number of webhooks received from channels',
    ['channel', 'status']
)

CHANNEL_MESSAGES_SENT_TOTAL = Counter(
    'channel_messages_sent_total',
    'Total number of messages sent to channels',
    ['channel', 'status']
)

# SSE metrics
SSE_CONNECTIONS_ACTIVE = Gauge(
    'sse_connections_active',
    'Number of active SSE connections',
    ['type']  # 'coordinator', 'job', 'agent'
)

SSE_EVENTS_SENT_TOTAL = Counter(
    'sse_events_sent_total',
    'Total number of SSE events sent',
    ['type', 'event']
)

# Cache metrics
CACHE_HITS_TOTAL = Counter(
    'cache_hits_total',
    'Total number of cache hits',
    ['cache_name']
)

CACHE_MISSES_TOTAL = Counter(
    'cache_misses_total',
    'Total number of cache misses',
    ['cache_name']
)

CACHE_EVICTIONS_TOTAL = Counter(
    'cache_evictions_total',
    'Total number of cache evictions',
    ['cache_name']
)

# Plugin metrics
PLUGIN_HOOK_INVOCATIONS_TOTAL = Counter(
    'plugin_hook_invocations_total',
    'Total number of plugin hook invocations',
    ['hook_name', 'plugin_name']
)

PLUGIN_HOOK_DURATION_SECONDS = Histogram(
    'plugin_hook_duration_seconds',
    'Duration of plugin hook execution in seconds',
    ['hook_name'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

# System info
SYSTEM_INFO = Info(
    'curriculum_forge',
    'Curriculum-Forge system information'
)


def get_metrics():
    """Return Prometheus metrics in text format."""
    return generate_latest()


def get_content_type():
    """Return Prometheus content type."""
    return CONTENT_TYPE_LATEST


def track_request(method: str, endpoint: str, status: int, duration: float):
    """Track HTTP request metrics."""
    HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)


def track_job_created(profile: str):
    """Track job creation."""
    JOBS_TOTAL.labels(profile=profile, state='CREATED').inc()


def track_job_state_change(profile: str, old_state: str, new_state: str):
    """Track job state transition."""
    if new_state in ('SUCCESS', 'FAILED'):
        JOBS_COMPLETED_TOTAL.labels(profile=profile, state=new_state).inc()


def track_job_duration(profile: str, duration_seconds: float):
    """Track job execution duration."""
    JOB_DURATION_SECONDS.labels(profile=profile).observe(duration_seconds)


def track_agent_registered():
    """Track agent registration."""
    AGENTS_REGISTERED.inc()


def track_agent_deregistered():
    """Track agent deregistration."""
    AGENTS_REGISTERED.dec()


def track_sse_connect(sse_type: str):
    """Track SSE connection."""
    SSE_CONNECTIONS_ACTIVE.labels(type=sse_type).inc()


def track_sse_disconnect(sse_type: str):
    """Track SSE disconnection."""
    SSE_CONNECTIONS_ACTIVE.labels(type=sse_type).dec()


def track_sse_event(sse_type: str, event: str):
    """Track SSE event sent."""
    SSE_EVENTS_SENT_TOTAL.labels(type=sse_type, event=event).inc()


def track_cache_hit(cache_name: str):
    """Track cache hit."""
    CACHE_HITS_TOTAL.labels(cache_name=cache_name).inc()


def track_cache_miss(cache_name: str):
    """Track cache miss."""
    CACHE_MISSES_TOTAL.labels(cache_name=cache_name).inc()


def track_plugin_hook(hook_name: str, plugin_name: str, duration: float):
    """Track plugin hook invocation."""
    PLUGIN_HOOK_INVOCATIONS_TOTAL.labels(hook_name=hook_name, plugin_name=plugin_name).inc()
    PLUGIN_HOOK_DURATION_SECONDS.labels(hook_name=hook_name).observe(duration)
