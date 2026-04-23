# SPEC: Channel → Job 闭环

## 背景

Phase 1 第一件事（Provider 真正执行）已完成，38 个测试全绿。

当前 Phase 1 第二件事：Channel 收到消息 → Gateway 创建 Job → 执行 → 回复结果。

## 现状

- **FeishuAdapter** — 有 `on_message` 回调接口，但无默认实现
- **WeixinAdapter** — 有 `on_message` 回调接口，但无默认实现
- **Gateway** — POST /jobs 已能创建 CheckpointRecord 并后台执行

## 缺口

Channel 收到消息后，不知道怎么：
1. 解析消息中的 topic/config 参数
2. 调用 Gateway 创建 Job
3. 回复用户 job_id 或执行状态

## 设计方案：ChannelJobBridge

### 核心组件：`channels/bridge.py`

```
Message from Feishu/Weixin
    ↓
ChannelJobBridge.on_message(message)
    ↓
解析消息 → 提取 topic/difficulty/command
    ↓
Gateway POST /jobs（通过 HTTP 客户端）
    ↓
返回 job_id
    ↓
Channel 发送回复（"任务已创建: job_id"）
```

### Bridge API 设计

```python
class ChannelJobBridge:
    def __init__(
        self,
        gateway_url: str = "http://localhost:8765",
        default_profile: str = "rl_controller",
        on_job_created: Optional[Callable[[str, CheckpointRecord], None]] = None,
    )

    async def on_channel_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        处理 Channel 消息，返回回复文本（用于 Channel 回复用户）。
        Returns None 表示消息无需回复（如未知命令）。
        """
        # 1. 解析消息内容
        # 2. 识别命令（run/status/list/...）
        # 3. 调用 Gateway API
        # 4. 返回回复文本
```

### 命令协议

| 消息内容 | 行为 | 回复 |
|---------|------|------|
| `run <topic>` | 创建 Job | "✅ 任务已创建: {job_id}\n执行中..." |
| `status` | 查询最近 Job | "状态: {state}, phase: {phase}" |
| `list` | 列出最近 5 个 Job | Job 列表 |
| `log <job_id>` | 查看 Job 日志 | 日志摘要 |
| `help` | 发送使用说明 | 帮助文本 |

### 集成方式

在 Gateway 的 `create_app()` 中：
1. 创建 `ChannelJobBridge(gateway_url="http://localhost:8765")`
2. 传给 `setup_feishu_webhook(bridge.on_channel_message)`
3. 传给 `setup_weixin_webhook(bridge.on_channel_message)`

### 技术要点

1. **异步桥接**：Bridge 是 async 的，Channel 的 `on_message` 可能是 sync Callable
   - 方案：用 `asyncio.get_event_loop().run_in_executor()` 包装
2. **HTTP 客户端**：Bridge 通过 httpx 调用 Gateway REST API（不是直接导入，避免循环依赖）
3. **Gateway 未启动时**：Bridge 返回友好的错误信息
4. **消息过滤**：非命令消息（闲聊）不触发 Job 创建，返回 `None`

## 文件变更

| 文件 | 操作 |
|------|------|
| `channels/bridge.py` | 新建（~200 行） |
| `channels/feishu.py` | 更新 `setup_feishu_webhook` 接受 `on_message` 可为 async |
| `channels/weixin.py` | 更新 `setup_weixin_webhook` 接受 `on_message` 可为 async |
| `runtimes/gateway.py` | 在 `create_app()` 中初始化 Bridge |

## 验收条件

1. 飞书/微信发送 `run <topic>` → Gateway 创建 Job → Channel 回复 job_id
2. 发送 `status` → 返回最近 Job 状态
3. 全量测试继续通过