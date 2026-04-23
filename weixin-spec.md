# 微信 Channel Adapter 规格文档

## 目标

为 dual-agent-tool-rl 项目实现微信/企业微信 Channel Adapter，支持通过微信接收任务指令和接收执行结果通知。

## 背景

- dual-agent-tool-rl 已有飞书 Channel Adapter（Webhook 模式）
- 需要补充微信渠道，覆盖习惯使用微信的用户
- 飞书凭证：`cli_a9300dfa90391bce` / `nMPAzDdauDdfyJFV50EUObzEEAnnoYZK`
- 微信凭证待用户提供

## 集成模式选择

### 微信公众号（订阅号/服务号）

**优点**：用户覆盖面广，个人/企业均可使用
**挑战**：
- 消息内容需要通过微信服务器中转，消息格式为 XML
- 模板消息有严格的行业限制和审核流程
- 单个公众号每日模板消息配额有限（100-1000条/天）

**接入方式**：
1. 微信公众平台 → 设置与开发 → 基本配置
2. 配置服务器地址（URL）+ Token + EncodingAESKey
3. 启用服务器配置（需公网可达）

### 企业微信（WeCom）

**优点**：
- API 完善，支持应用消息、群发、网页授权
- 消息发送配额更宽松
- 适合企业内部工具集成

**挑战**：需要企业主体或测试企业（最多 200 成员免费试用）

**接入方式**：
1. 企业微信管理后台 → 应用管理 → 创建应用
2. 获取 `corpId` + `corpSecret` + `agentId`
3. 调用应用消息接口发送通知

### 选型决策

**Phase 1：微信公众号 Webhook 模式**

理由：
- 与飞书适配器架构一致（Webhook 接收 + API 发送）
- 用户覆盖面最广
- 飞书适配器代码可复用模式

后续可扩展：企业微信（只需新增 WeComAdapter 类，复用 base.py 抽象）

## 功能范围

### 核心功能（Phase 1）

1. **消息接收**
   - Webhook 端点：`POST /webhooks/weixin`
   - 支持消息类型：文本消息（text）
   - 消息加解密：明文模式 /兼容模式（安全增强可选）

2. **消息发送**
   - 客服消息接口（被动回复，48小时内有效）
   - 模板消息接口（主动通知，需预先申请模板）

3. **配置管理**
   - `WeixinConfig` dataclass：appId, appSecret, token, encodingAESKey

### 安全机制

1. **Token 验证**（GET 请求）
   - 参数：`signature`, `timestamp`, `nonce`, `echostr`
   - 验证：`sha1(token, timestamp, nonce)` 与 `signature` 比对
   - 成功：`echostr` 原样返回

2. **消息签名验证**（POST 请求，可选）
   - 使用 `EncodingAESKey` 解密消息体
   - 防止伪造请求

## 技术架构

```
channels/
  __init__.py          # WeixinConfig, WeixinAdapter, WeixinMessage
  feishu.py            # 已有
  weixin.py            # 新增（~300 行）
  base.py               # 可选：通用 Channel ABC（复用接口）

runtimes/
  gateway.py           # 已有 setup_feishu_webhook，新增 setup_weixin_webhook
```

### WeixinConfig

```python
@dataclass
class WeixinConfig:
    app_id: str         # 微信公众号 AppID
    app_secret: str     # 微信公众号 AppSecret
    token: str          # 配置的 Token（用于签名验证）
    encoding_aes_key: str = ""  # 可选：消息加解密密钥
```

### WeixinAdapter

```python
class WeixinAdapter:
    def __init__(self, config: WeixinConfig, http_client: httpx.AsyncClient = None)
    
    # 认证
    async def get_access_token(self, force_refresh=False) -> str
    
    # 消息接收处理
    def verify_url(timestamp, nonce, signature) -> bool
    def parse_message(xml_body: str) -> WeixinMessage
    async def handle_event(request: Request) -> Response
    
    # 消息发送（被动回复）
    async def send_text(to_user: str, content: str) -> dict
    
    # 模板消息（主动通知）
    async def send_template_message(to_user: str, template_id: str, data: dict, url: str = "") -> dict
    
    # 工具方法
    def message_to_xml(msg_type: str, to_user: str, content: str) -> str
```

### WeixinMessage 数据类

```python
@dataclass
class WeixinMessage:
    to_user: str        # 发送者 OpenID
    from_user: str      # 开发者微信号
    msg_type: str       # text/image/voice/video/location/link
    content: str        # 消息内容（文本消息）
    msg_id: int        # 消息 ID
    create_time: int   # 创建时间戳
    raw_xml: str        # 原始 XML（供调试）
```

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/webhooks/weixin` | GET | URL 验证（微信服务器连通性校验）|
| `/webhooks/weixin` | POST | 接收微信事件（消息推送）|

## 微信公众平台配置

1. 登录微信公众平台 → 设置与开发 → 基本配置
2. 服务器配置：
   - URL: `https://你的域名/webhooks/weixin`
   - Token: 与 `WeixinConfig.token` 一致
   - EncodingAESKey: 可选，与 `WeixinConfig.encoding_aes_key` 一致
   - 消息加解密方式：明文 / 兼容 / 安全（推荐兼容）
3. 启用服务器配置
4. 获取 AppID + AppSecret（开发者凭据）

## Gateway 集成

```python
from runtimes.gateway import create_app, setup_weixin_webhook

app = create_app()
adapter = setup_weixin_webhook(
    app,
    app_id="your_app_id",
    app_secret="your_app_secret",
    token="your_token",
    encoding_aes_key="your_aes_key",  # 可选
)
```

## 测试策略

- 单元测试：`tests/unit/test_weixin_adapter.py`
  - Config 验证
  - URL 签名验证
  - 消息解析（XML → WeixinMessage）
  - 消息回复（XML 构造）
  - access_token 获取/缓存
  - 错误处理（网络错误、API 错误）

## 依赖

- `httpx`（已在飞书适配器中添加）

## 边界与约束

1. **公网可达**：微信 Webhook URL 必须公网可达（80/443端口）
2. **消息时效**：被动回复仅在用户发送消息后 48 小时内有效
3. **模板消息**：需要预先在公众平台申请模板 ID
4. **接口限制**：微信 API 有频率限制（模板消息 1000次/天）
5. **Python 3.7 兼容**：同项目其他代码，保持 `async def` + `dataclass` 兼容

## 参考资料

- 微信公众号接入文档：https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Access_Overview.html
- 被动回复消息：https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Passive_user_reply_message.html
- 模板消息：https://developers.weixin.qq.com/doc/offiaccount/Message_Operations/Template_Message_Operation.html
