"""
Governance Layer Prometheus Metrics

Metrics for Keeper, Mayor, and FrontDesk components.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ============================================================
# Keeper Metrics - 资源管理
# ============================================================

# Agent 注册
KEEPER_AGENTS_REGISTERED = Gauge(
    'keeper_agents_registered',
    'Number of currently registered agents',
    ['role']
)

KEEPER_AGENTS_TOTAL = Counter(
    'keeper_agents_total',
    'Total number of agent registrations',
    ['role', 'status']  # status: registered, deregistered
)

# 资源使用
KEEPER_RESOURCE_TOTAL = Gauge(
    'keeper_resource_total',
    'Total resource capacity',
    ['agent_id', 'resource_type']
)

KEEPER_RESOURCE_USED = Gauge(
    'keeper_resource_used',
    'Used resources',
    ['agent_id', 'resource_type']
)

KEEPER_RESOURCE_RESERVED = Gauge(
    'keeper_resource_reserved',
    'Reserved resources',
    ['agent_id', 'resource_type']
)

# 任务调度
KEEPER_TASKS_ASSIGNED = Counter(
    'keeper_tasks_assigned_total',
    'Total number of tasks assigned by Keeper',
    ['agent_id', 'policy']
)

KEEPER_TASKS_REJECTED = Counter(
    'keeper_tasks_rejected_total',
    'Total number of tasks rejected by Keeper',
    ['reason']
)

KEEPER_ASSIGNMENT_DURATION = Histogram(
    'keeper_assignment_duration_seconds',
    'Time taken to assign a task',
    ['policy'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

# 健康检查
KEEPER_HEALTH_CHECKS_TOTAL = Counter(
    'keeper_health_checks_total',
    'Total number of health checks performed',
    ['result']  # healthy, unhealthy
)

KEEPER_AGENTS_UNHEALTHY = Gauge(
    'keeper_agents_unhealthy',
    'Number of unhealthy agents',
    []
)

# ============================================================
# Mayor Metrics - 规则与声誉
# ============================================================

# 规则评估
MAYOR_RULES_EVALUATED = Counter(
    'mayor_rules_evaluated_total',
    'Total number of rule evaluations',
    ['rule_type', 'result']  # result: passed, violated
)

MAYOR_RULE_VIOLATIONS = Counter(
    'mayor_rule_violations_total',
    'Total number of rule violations',
    ['rule_id', 'severity']
)

MAYOR_EVALUATION_DURATION = Histogram(
    'mayor_evaluation_duration_seconds',
    'Time taken to evaluate rules',
    ['rule_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

# 声誉系统
MAYOR_REPUTATION_SCORE = Gauge(
    'mayor_reputation_score',
    'Current reputation score for an agent',
    ['agent_id']
)

MAYOR_REPUTATION_CHANGES = Counter(
    'mayor_reputation_changes_total',
    'Total number of reputation changes',
    ['agent_id', 'direction']  # direction: up, down
)

MAYOR_AGENTS_TRUSTED = Gauge(
    'mayor_agents_trusted',
    'Number of trusted agents (reputation >= 50)',
    []
)

MAYOR_AGENTS_BANNED = Gauge(
    'mayor_agents_banned',
    'Number of banned agents (reputation < 10)',
    []
)

# 提案投票
MAYOR_PROPOSALS_TOTAL = Counter(
    'mayor_proposals_total',
    'Total number of proposals created',
    ['proposal_type']
)

MAYOR_PROPOSALS_RESOLVED = Counter(
    'mayor_proposals_resolved_total',
    'Total number of proposals resolved',
    ['proposal_type', 'result']  # result: passed, rejected, expired
)

MAYOR_VOTES_CAST = Counter(
    'mayor_votes_cast_total',
    'Total number of votes cast',
    ['agent_id', 'vote']  # vote: for, against, abstain
)

# ============================================================
# FrontDesk Metrics - 用户前台
# ============================================================

# 请求处理
FRONTDESK_REQUESTS_RECEIVED = Counter(
    'frontdesk_requests_received_total',
    'Total number of user requests received',
    ['priority']
)

FRONTDESK_REQUESTS_COMPLETED = Counter(
    'frontdesk_requests_completed_total',
    'Total number of requests completed',
    ['status']  # completed, failed, cancelled
)

FRONTDESK_REQUESTS_IN_QUEUE = Gauge(
    'frontdesk_requests_in_queue',
    'Number of requests currently in queue',
    ['priority']
)

FRONTDESK_REQUEST_DURATION = Histogram(
    'frontdesk_request_duration_seconds',
    'Total request processing time',
    ['priority'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 3600]
)

# 会话管理
FRONTDESK_SESSIONS_ACTIVE = Gauge(
    'frontdesk_sessions_active',
    'Number of active user sessions',
    []
)

FRONTDESK_SESSIONS_TOTAL = Counter(
    'frontdesk_sessions_total',
    'Total number of sessions created',
    []
)

# 批量操作
FRONTDESK_BATCH_OPERATIONS = Counter(
    'frontdesk_batch_operations_total',
    'Total number of batch operations',
    ['operation']  # receive_batch, get_batch_results
)

FRONTDESK_BATCH_SIZE = Histogram(
    'frontdesk_batch_size',
    'Size of batch operations',
    ['operation'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500]
)


# ============================================================
# Helper Functions
# ============================================================

def track_agent_registered(role: str, is_new: bool = True):
    """Track agent registration."""
    KEEPER_AGENTS_REGISTERED.labels(role=role).inc()
    if is_new:
        KEEPER_AGENTS_TOTAL.labels(role=role, status='registered').inc()


def track_agent_deregistered(role: str):
    """Track agent deregistration."""
    KEEPER_AGENTS_REGISTERED.labels(role=role).dec()
    KEEPER_AGENTS_TOTAL.labels(role=role, status='deregistered').inc()


def track_task_assigned(agent_id: str, policy: str, duration: float):
    """Track task assignment."""
    KEEPER_TASKS_ASSIGNED.labels(agent_id=agent_id, policy=policy).inc()
    KEEPER_ASSIGNMENT_DURATION.labels(policy=policy).observe(duration)


def track_rule_evaluation(rule_type: str, passed: bool):
    """Track rule evaluation."""
    result = 'passed' if passed else 'violated'
    MAYOR_RULES_EVALUATED.labels(rule_type=rule_type, result=result).inc()


def track_rule_violation(rule_id: str, severity: str):
    """Track rule violation."""
    MAYOR_RULE_VIOLATIONS.labels(rule_id=rule_id, severity=severity).inc()


def track_reputation_change(agent_id: str, old_score: float, new_score: float):
    """Track reputation score change."""
    MAYOR_REPUTATION_SCORE.labels(agent_id=agent_id).set(new_score)
    direction = 'up' if new_score > old_score else 'down'
    MAYOR_REPUTATION_CHANGES.labels(agent_id=agent_id, direction=direction).inc()


def track_request_received(priority: str):
    """Track request received."""
    FRONTDESK_REQUESTS_RECEIVED.labels(priority=priority).inc()


def track_request_completed(priority: str, status: str, duration: float):
    """Track request completion."""
    FRONTDESK_REQUESTS_COMPLETED.labels(status=status).inc()
    FRONTDESK_REQUEST_DURATION.labels(priority=priority).observe(duration)


def track_session_created():
    """Track session creation."""
    FRONTDESK_SESSIONS_TOTAL.inc()
    FRONTDESK_SESSIONS_ACTIVE.inc()


def track_session_ended():
    """Track session end."""
    FRONTDESK_SESSIONS_ACTIVE.dec()
