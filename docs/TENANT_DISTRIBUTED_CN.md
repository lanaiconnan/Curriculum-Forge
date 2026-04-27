# 多租户与分布式部署指南

本文档介绍 Curriculum-Forge 的多租户支持和分布式部署能力。

---

## 多租户支持

### 概述

多租户（Multi-tenancy）支持允许系统为不同组织/团队提供隔离的环境，每个租户拥有独立的：

- 资源配额（任务数、并发数、存储空间）
- 使用统计
- 功能开关

### 租户识别优先级

系统按以下顺序识别租户：

1. **X-Tenant-ID 请求头** — 显式指定租户 ID
2. **API Key 元数据** — API Key 创建时绑定的租户
3. **JWT Claims** — 用户登录时所属租户

### 租户状态

| 状态 | 说明 |
|------|------|
| `ACTIVE` | 正常使用 |
| `SUSPENDED` | 已暂停（超出配额或违规） |
| `TRIAL` | 试用期 |
| `EXPIRED` | 已过期 |

---

## 租户 API

### 创建租户

```bash
POST /tenants
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "name": "acme-corp",
  "display_name": "ACME 公司",
  "plan": "enterprise",
  "quota": {
    "jobs_per_day": 1000,
    "max_concurrent_jobs": 50,
    "max_api_calls_per_hour": 10000,
    "max_storage_mb": 10240
  },
  "features": ["distributed", "plugins", "audit"]
}
```

**响应：**

```json
{
  "id": "tenant_abc123",
  "name": "acme-corp",
  "display_name": "ACME 公司",
  "status": "ACTIVE",
  "plan": "enterprise",
  "created_at": "2026-04-28T10:00:00Z"
}
```

### 列出租户

```bash
GET /tenants
Authorization: Bearer <admin-jwt-token>
```

### 获取租户详情

```bash
GET /tenants/{tenant_id}
Authorization: Bearer <admin-jwt-token>
```

### 更新租户配额

```bash
PUT /tenants/{tenant_id}/quota
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "jobs_per_day": 2000,
  "max_concurrent_jobs": 100
}
```

### 更新租户状态

```bash
PUT /tenants/{tenant_id}/status
Authorization: Bearer <admin-jwt-token>
Content-Type: application/json

{
  "status": "SUSPENDED",
  "reason": "Exceeded quota limit"
}
```

### 获取租户使用统计

```bash
GET /tenants/{tenant_id}/usage
Authorization: Bearer <admin-jwt-token>
```

**响应：**

```json
{
  "tenant_id": "tenant_abc123",
  "period": "2026-04-28",
  "jobs_created": 156,
  "jobs_completed": 142,
  "jobs_failed": 3,
  "api_calls": 4521,
  "storage_used_mb": 2048,
  "quota_usage": {
    "jobs_per_day": 0.156,
    "concurrent_jobs": 0.24,
    "api_calls_per_hour": 0.45,
    "storage": 0.2
  }
}
```

### 检查功能可用性

```bash
GET /tenants/{tenant_id}/features/{feature}
Authorization: Bearer <jwt-token>
```

### 删除租户

```bash
DELETE /tenants/{tenant_id}
Authorization: Bearer <admin-jwt-token>
```

---

## 租户中间件

### 使用方法

在 FastAPI 应用中启用租户中间件：

```python
from tenant import TenantMiddleware, get_current_tenant, require_tenant
from fastapi import Depends, FastAPI

app = FastAPI()
app.add_middleware(TenantMiddleware)

@app.get("/my-jobs")
async def my_jobs(tenant = Depends(get_current_tenant)):
    if tenant:
        return {"tenant": tenant.name, "jobs": [...]}
    return {"tenant": None, "jobs": [...]}
```

### 强制租户

某些端点必须要求租户上下文：

```python
@app.post("/jobs")
async def create_job(tenant = Depends(require_tenant)):
    # tenant 必须存在，否则返回 400
    pass
```

### 功能检查

```python
from tenant import check_tenant_feature

@app.post("/distributed-task")
async def distributed_task(
    tenant = Depends(require_tenant),
    _: None = Depends(check_tenant_feature("distributed"))
):
    # 租户必须有 distributed 功能，否则返回 403
    pass
```

---

## 配额管理

### 配额类型

| 配额项 | 说明 | 默认值 |
|--------|------|--------|
| `jobs_per_day` | 每日任务数 | 100 |
| `max_concurrent_jobs` | 最大并发任务 | 10 |
| `max_api_calls_per_hour` | 每小时 API 调用 | 1000 |
| `max_storage_mb` | 最大存储空间 (MB) | 1024 |

### 配额检查

```python
from tenant import TenantRegistry

registry = TenantRegistry()
tenant = registry.get_tenant("tenant_abc123")

# 检查是否可以创建任务
if tenant.can_create_job():
    # 允许创建
    pass

# 检查是否可以增加存储
if tenant.can_use_storage(size_mb=100):
    # 允许存储
    pass
```

### 使用追踪

```python
# 记录任务创建
tenant.record_job_created()

# 记录存储使用
tenant.record_storage_used(mb=50)

# 获取使用统计
stats = tenant.get_usage_stats()
```

---

## 分布式部署

### 概述

分布式部署支持多个节点协同工作，提供：

- **节点注册与健康检查** — 自动发现和管理节点
- **主节点选举** — 租约式选举，自动故障转移
- **分布式锁** — 防止任务重复执行
- **任务分发** — 多种负载均衡策略

### 架构

```
┌─────────────────┐     ┌─────────────────┐
│   Gateway #1    │     │   Gateway #2    │
│   (Leader)      │     │   (Follower)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │    NodeRegistry       │
         │  (节点注册与健康检查)  │
         └───────────────────────┘
```

---

## 节点管理

### 注册节点

```python
from distributed import NodeRegistry

registry = NodeRegistry()

# 注册当前节点
node = registry.register(
    host="192.168.1.100",
    port=8765,
    capacity=100  # 处理能力
)

print(f"Node ID: {node.node_id}")
print(f"Status: {node.status}")
```

### 心跳与健康检查

```python
# 发送心跳（定期执行，如每 10 秒）
registry.heartbeat(node.node_id, load=30)

# 检查节点健康
health = registry.check_health()
print(f"Healthy: {health['healthy']}")
print(f"Unhealthy: {health['unhealthy']}")
```

### 列出节点

```python
nodes = registry.list_nodes(status_filter="ACTIVE")
for node in nodes:
    print(f"{node.node_id}: {node.host}:{node.port} (load: {node.current_load}%)")
```

### 注销节点

```python
registry.unregister(node.node_id)
```

---

## 主节点选举

### 获取领导权

```python
from distributed import LeaderElection

election = LeaderElection(
    node_id="node_001",
    lease_duration=30  # 租约时长（秒）
)

# 尝试获取领导权
if election.try_acquire_leadership():
    print("I am the leader now!")
else:
    print("Another node is the leader")
```

### 检查状态

```python
# 是否是主节点
if election.is_leader():
    # 执行主节点专属任务
    pass

# 获取当前主节点 ID
leader_id = election.get_leader()
```

### 续约

```python
# 主节点需要定期续约
if election.is_leader():
    election.renew_lease()
```

### 释放领导权

```python
# 主动释放（如优雅关闭）
election.release_leadership()
```

### 选举回调

```python
def on_elected():
    print("Elected as leader!")

def on_demoted():
    print("No longer leader")

election.set_callbacks(
    on_elected=on_elected,
    on_demoted=on_demoted
)
```

---

## 分布式锁

### 获取锁

```python
from distributed import DistributedLock

lock = DistributedLock(
    name="task_123_execution",
    ttl=60  # 锁过期时间（秒）
)

# 尝试获取锁
if lock.acquire(holder_id="node_001"):
    try:
        # 执行需要互斥的操作
        execute_task()
    finally:
        lock.release(holder_id="node_001")
else:
    print("Task is being executed by another node")
```

### 等待锁

```python
# 阻塞等待获取锁
if lock.acquire(holder_id="node_001", wait=True, timeout=5.0):
    try:
        execute_task()
    finally:
        lock.release(holder_id="node_001")
```

### 可重入锁

```python
# 同一 holder 可以多次获取
lock.acquire(holder_id="node_001")  # True
lock.acquire(holder_id="node_001")  # True (re-entrant)
lock.release(holder_id="node_001")
lock.release(holder_id="node_001")
```

### 锁管理器

```python
from distributed import LockManager

manager = LockManager()

# 获取或创建锁（自动缓存）
lock = manager.get_lock("my_resource_lock")
```

---

## 任务分发

### 分发策略

| 策略 | 说明 |
|------|------|
| `ROUND_ROBIN` | 轮询，依次分配 |
| `LEAST_LOADED` | 选择负载最低的节点 |
| `RANDOM` | 随机选择 |
| `CONSISTENT_HASH` | 一致性哈希（相同任务 ID 总是分配到同一节点） |

### 使用分发器

```python
from distributed import TaskDistributor, TaskDistributionStrategy

distributor = TaskDistributor(
    registry=registry,
    strategy=TaskDistributionStrategy.LEAST_LOADED
)

# 选择目标节点
target_node = distributor.select_node()
if target_node:
    print(f"Task assigned to {target_node.node_id}")

# 分发任务
target = distributor.distribute(
    task={"type": "training", "params": {...}},
    task_id="task_abc123"
)
```

### 批量分发

```python
tasks = [
    {"id": "task_1", "type": "inference"},
    {"id": "task_2", "type": "training"},
    {"id": "task_3", "type": "inference"},
]

assignments = distributor.distribute_batch(tasks)
for task_id, node in assignments.items():
    print(f"{task_id} -> {node.node_id}")
```

---

## 生产部署建议

### 1. 节点配置

```yaml
# node-config.yaml
node:
  id: node_001
  host: 192.168.1.100
  port: 8765
  capacity: 100

election:
  lease_duration: 30
  heartbeat_interval: 10

registry:
  heartbeat_timeout: 60
```

### 2. 健康检查端点

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "is_leader": election.is_leader(),
        "nodes": registry.check_health()
    }
```

### 3. 优雅关闭

```python
import signal

def graceful_shutdown(signum, frame):
    # 释放领导权
    if election.is_leader():
        election.release_leadership()
    
    # 注销节点
    registry.unregister(node.node_id)
    
    # 等待任务完成
    wait_for_pending_tasks()

signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)
```

### 4. 监控告警

```yaml
# alert.rules.yml
groups:
  - name: distributed
    rules:
      - alert: NodeDown
        expr: cf_node_status == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Node {{ $labels.node_id }} is down"
      
      - alert: NoLeader
        expr: cf_leader_election_leader == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "No leader elected"
```

---

## 相关文档

- [部署指南](./DEPLOYMENT_CN.md) — 生产环境部署
- [安全指南](./SECURITY_GUIDE_CN.md) — 认证与权限
- [Gateway API](./GATEWAY_API_CN.md) — 完整 API 参考
