---
name: knowledge-logger
version: 1.0.0
description: Logs knowledge layer events for debugging and audit
author: Curriculum Forge Team
hooks:
  - knowledge:experience_stored
  - knowledge:experience_retrieved
  - knowledge:page_created
  - knowledge:page_updated
  - knowledge:page_deleted
config:
  log_dir: data/knowledge_logs
  max_entries: 10000
---

# Knowledge Logger Plugin

## 功能

监听知识层所有事件并记录到 JSONL 日志文件，用于调试和审计。

## 监听的 Hook

| Hook | 触发时机 |
|------|----------|
| `knowledge:experience_stored` | 经验存储完成 |
| `knowledge:experience_retrieved` | 经验检索完成 |
| `knowledge:page_created` | 知识页面创建 |
| `knowledge:page_updated` | 知识页面更新 |
| `knowledge:page_deleted` | 知识页面删除 |

## 配置

```yaml
log_dir: data/knowledge_logs  # 日志目录
max_entries: 10000            # 单文件最大条目数
```

## 日志格式

每条日志为 JSON 对象：

```json
{
  "timestamp": "2026-04-28T03:00:00.000000",
  "hook": "knowledge:page_created",
  "context": {
    "title": "如何优化 Agent 协作",
    "tags": ["agent", "协作"],
    ...
  }
}
```

## 使用场景

- 调试知识层事件流
- 审计知识库变更历史
- 统计知识库使用频率
