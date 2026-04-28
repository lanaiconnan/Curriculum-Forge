---
name: tenant-monitor
version: 1.0.0
description: Monitors tenant lifecycle and quota events
author: Curriculum Forge Team
hooks:
  - tenant:created
  - tenant:updated
  - tenant:suspended
  - tenant:quota_check
config:
  alert_threshold: 0.8
  log_file: data/tenant_monitor.jsonl
---

# Tenant Monitor Plugin

## 功能

监听租户生命周期事件和配额检查，提供配额告警。

## 监听的 Hook

| Hook | 触发时机 |
|------|----------|
| `tenant:created` | 租户创建 |
| `tenant:updated` | 租户更新 |
| `tenant:suspended` | 租户暂停 |
| `tenant:quota_check` | 配额检查 |

## 配置

```yaml
alert_threshold: 0.8    # 配额告警阈值（80%）
log_file: data/tenant_monitor.jsonl
```

## 告警机制

当 `tenant:quota_check` 事件的 usage/limit ≥ alert_threshold 时，生成告警：

```json
{
  "timestamp": "2026-04-28T03:00:00.000000",
  "type": "quota_warning",
  "tenant_id": "tenant-001",
  "usage": 8000,
  "limit": 10000,
  "ratio": 0.8
}
```

## 使用场景

- 监控租户资源使用
- 配额预警通知
- 租户生命周期审计
