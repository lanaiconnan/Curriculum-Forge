# Claude Code-1 学习优先级排序

> 创建时间：2026-04-03
> 参考项目：https://github.com/lanaiconnan/Claude-Code-1
> 用途：指导 Curriculum-Forge 后续功能实现

---

## 🥇 P0 — 已完成

| 模块 | 对应实现 | 版本 | 核心收获 |
|------|---------|------|---------|
| `coordinator/` | `services/coordinator.py` + `dual_agent.py` | v1.6 | Task/Workflow 依赖图、Agent 注册、消息传递 |
| `skills/` (插件系统) | `services/plugin_loader.py` + `plugins/` | v1.7 | PLUGIN.md 自描述、文件系统发现、动态加载 |
| `QueryEngine.ts` | `services/query_engine.py` | v1.8 | tool-use 循环、消息历史、token budget、retry |

---

## 🥈 P1 — 已完成 ✅

| 模块 | 对应实现 | 版本 | 核心收获 |
|------|---------|------|---------|
| `harness/` | `services/harness.py` | v1.9 | HarnessCase/Runner/Report，工具行为验证 |
| `tools/` | `services/tools.py` | v2.0 | ToolPermission/RateLimit/ManagedToolRegistry |
| `context/` | `services/context.py` | v2.1 | ContextCompactor/CompactableQueryEngine |
| `compact/` | `services/compact.py` | v2.2 | ImportanceScorer/MicroCompactor/CompactArchive |

---

## 🥉 P2 — 全部完成 ✅

| 模块 | 对应实现 | 状态 | 核心收获 |
|------|---------|------|---------|
| `services/compact/` | `services/compact.py` | ✅ 完成 | 重要度评分 + 微压缩 + 搜索存档 |
| `memdir/` | `services/memdir.py` | ✅ 完成 | 4类记忆 + MEMORY.md索引 + 搜索 + 记忆老化 |
| `bootstrap/` | `services/bootstrap.py` | ✅ 完成 | 会话初始化 + checkpoint/resume + 历史追踪 |
| `services/api/` | `services/api.py` | ✅ 完成 | 错误分类 + 指数退避重试 + 请求ID追踪 |
| `utils/tokens.ts` | `utils/tokens.py` | ✅ 完成 | Token计数 + 预估 + Budget追踪 + 成本估算 |

---

## 📊 实现进度总览

```
P0 ████████████████████ 100% (3/3 完成)
P1 ████████████████████ 100% (3/3 完成) ✅
P2 ████████████████████ 100% (5/5 完成) ✅ 全部完成！
```

---

## 🗓️ 实现进度

```
Week 1 (2026-04-03)
  ✅ v1.6 coordinator/
  ✅ v1.7 skills/ (plugin system)
  ✅ v1.8 QueryEngine.ts
  ✅ v1.9 harness/
  ✅ v2.0 tools/ (权限控制)
  ✅ v2.1 context/ (压缩)    ← P1 全部完成！

Week 2 (2026-04-03)
  ✅ v2.2 compact/ (增强压缩 + 搜索)
  ✅ v2.3 memdir/ (持久化记忆)
  ✅ v2.4 bootstrap/ (会话初始化 + checkpoint)
  ✅ v2.5 api/ (错误分类 + 重试)  ← 刚完成！

  → utils/tokens (最后一个 P2)
```

---

## 💡 关键洞察

### harness/ 与 reward 的关系

```
harness 测试的是：
  actual_tool == expected_tool  →  rname 奖励
  actual_params ≈ expected_params  →  rparam 奖励

这正是 ToolRL 论文的核心奖励设计！
harness = 离线评估版的 reward calculator
```

### QueryEngine → harness 的自然延伸

```
QueryEngine.submit(prompt)
    ↓ 返回 QueryResult（含 tool_calls）
HarnessRunner.evaluate(result, expected)
    ↓ 对比 actual vs expected
HarnessReport（pass/fail + 详细分数）
```

---

*文件路径：`/Users/lanaiconan/.qclaw/workspace/dual-agent-tool-rl/shared/CLAUDE_CODE_PRIORITIES.md`*
*最后更新：2026-04-03*
