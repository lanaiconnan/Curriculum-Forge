# Channel 集成指南

本文档介绍如何将 Curriculum Forge 与飞书（Feishu/Lark）和微信公众号集成，实现通过聊天界面创建和管理训练任务。

---

## 目录

1. [架构概览](#架构概览)
2. [飞书集成](#飞书集成)
3. [微信集成](#微信集成)
4. [命令参考](#命令参考)
5. [故障排查](#故障排查)

---

## 架构概览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   飞书 Bot   │     │  微信公众号  │     │   其他渠道   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
              ┌─────────────────────┐
              │   Channel Adapters   │
              │  (feishu/weixin)    │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   ChannelJobBridge   │
              │  (命令解析/任务创建)  │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │     Gateway API      │
              │   (端口 8765)        │
              └─────────────────────┘
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| FeishuAdapter | `channels/feishu.py` | 飞书消息接收/发送、签名验证 |
| WeixinAdapter | `channels/weixin.py` | 微信消息接收/发送、被动回复 |
| ChannelJobBridge | `channels/bridge.py` | 命令解析、Gateway API 调用 |

---

## 飞书集成

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 记录 **App ID** 和 **App Secret**
4. 在「事件订阅」中获取 **Verification Token** 和 **Encrypt Key**

### 2. 配置权限

在「权限管理」中添加以下权限：

- `im:chat:readonly` - 读取群组信息
- `im:message:send_as_bot` - 以机器人身份发送消息
- `im:message.group_msg` - 接收群消息
- `im:message.p2p_msg` - 接收单聊消息

### 3. 配置事件订阅

订阅以下事件：

- `im.message.receive_v1` - 接收消息
- `im.chat.member.bot.added_v1` - 机器人被添加进群

**请求地址配置：**
```
https://your-domain.com/webhooks/feishu
```

### 4. 环境变量配置

```bash
# .env 文件
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
FEISHU_ENCRYPT_KEY=xxxxxxxxxxxxxxxx
```

### 5. 代码集成

```python
from fastapi import FastAPI
from channels import setup_feishu_webhook

app = FastAPI()

# 方式1：使用环境变量自动配置
setup_feishu_webhook(app)

# 方式2：手动配置
from channels.feishu import FeishuConfig, FeishuAdapter

config = FeishuConfig.from_env()
adapter = FeishuAdapter(config)
setup_feishu_webhook(app, adapter)
```

### 6. 消息类型支持

| 消息类型 | 接收 | 发送 | 说明 |
|---------|------|------|------|
| text | ✅ | ✅ | 纯文本消息 |
| post | ✅ | ✅ | 富文本消息 |
| image | ✅ | ✅ | 图片消息 |
| interactive | ❌ | ✅ | 卡片消息 |

### 7. 发送卡片消息示例

```python
await adapter.send_card(
    receive_id="ou_xxxxxxxx",
    card={
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "任务完成"},
            "template": "green"
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**任务ID**: job_abc123"}
            }
        ]
    }
)
```

---

## 微信集成

### 1. 配置公众号

1. 登录 [微信公众平台](https://mp.weixin.qq.com/)
2. 进入「开发-基本配置」
3. 记录 **AppID** 和 **AppSecret**
4. 设置 **服务器配置**：
   - URL: `https://your-domain.com/webhooks/weixin`
   - Token: 自定义令牌（用于签名验证）
   - EncodingAESKey: 随机生成（消息加密）

### 2. 环境变量配置

```bash
# .env 文件
WEIXIN_APP_ID=wx_xxxxxxxxxxxxxxxx
WEIXIN_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WEIXIN_TOKEN=your_custom_token
WEIXIN_ENCODING_AES_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 代码集成

```python
from fastapi import FastAPI
from channels import setup_weixin_webhook

app = FastAPI()

# 方式1：使用环境变量自动配置
setup_weixin_webhook(app)

# 方式2：手动配置
from channels.weixin import WeixinConfig, WeixinAdapter

config = WeixinConfig.from_env()
adapter = WeixinAdapter(config)
setup_weixin_webhook(app, adapter)
```

### 4. 消息类型支持

| 消息类型 | 接收 | 发送 | 说明 |
|---------|------|------|------|
| text | ✅ | ✅ | 文本消息（被动回复） |
| image | ✅ | ❌ | 图片消息 |
| voice | ✅ | ❌ | 语音消息 |
| video | ✅ | ❌ | 视频消息 |
| location | ✅ | ❌ | 地理位置 |
| link | ✅ | ❌ | 链接消息 |
| template | ❌ | ✅ | 模板消息（主动推送） |

### 5. 被动回复机制

微信要求在 **5秒内** 返回响应，因此采用同步处理模式：

```xml
<xml>
  <ToUserName><![CDATA[user_openid]]></ToUserName>
  <FromUserName><![CDATA[official_account]]></FromUserName>
  <CreateTime>123456789</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[收到，正在处理...]]></Content>
</xml>
```

### 6. 模板消息（主动推送）

对于异步任务完成通知，使用模板消息：

```python
await adapter.send_template_message(
    openid="user_openid",
    template_id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    url="https://your-domain.com/job/abc123",
    data={
        "first": {"value": "任务执行完成", "color": "#173177"},
        "keyword1": {"value": "job_abc123", "color": "#173177"},
        "keyword2": {"value": "成功", "color": "#00FF00"},
        "remark": {"value": "点击查看详情", "color": "#173177"}
    }
)
```

---

## 命令参考

### 命令格式

```
@agent <命令> [参数] [#profile]
```

### 可用命令

| 命令 | 格式 | 说明 | 示例 |
|------|------|------|------|
| create | `create <主题>` | 创建新任务 | `@agent create 强化学习训练` |
| status | `status <任务ID>` | 查询任务状态 | `@agent status job_abc123` |
| list | `list [数量]` | 列出最近任务 | `@agent list 5` |
| logs | `logs <任务ID>` | 查看任务日志 | `@agent logs job_abc123` |
| workflow | `workflow <名称>` | 创建多Agent工作流 | `@agent workflow 实验分析` |
| help | `help` | 显示帮助信息 | `@agent help` |

### Profile 选择

使用 `#` 前缀指定执行配置：

```
@agent create 数学问题 #rl_controller
@agent create 代码审查 #pure_harness
@agent create 渐进式教学 #progressive_disclosure
```

内置 Profile：
- `rl_controller` - 强化学习控制器
- `pure_harness` - 纯测试模式
- `progressive_disclosure` - 渐进式披露

### Workflow 命令详解

创建多 Agent DAG 协作任务：

```
@agent workflow 实验分析
```

默认执行流程：
1. **environment** - 环境准备
2. **experiment** - 实验执行
3. **review** - 结果评审

自定义任务类型：
```
@agent workflow 自定义流程 --types environment,review
```

---

## 故障排查

### 飞书常见问题

#### 签名验证失败

**现象：** 收到 "Invalid signature" 错误

**排查：**
```bash
# 检查环境变量是否正确
echo $FEISHU_VERIFICATION_TOKEN
echo $FEISHU_ENCRYPT_KEY

# 确认与飞书后台配置一致
```

#### 无法接收消息

**排查清单：**
1. 检查应用是否发布（版本管理与发布 → 创建版本 → 申请发布）
2. 确认机器人已添加到群组
3. 检查事件订阅 URL 是否可访问
4. 查看飞书后台「事件订阅」的「请求记录」

#### Token 过期

**现象：** 发送消息返回 `99991663` 错误码

**解决：**
```python
# 强制刷新 Token
await adapter.get_tenant_access_token(force_refresh=True)
```

### 微信常见问题

#### URL 验证失败

**现象：** 配置服务器 URL 时提示「请求 URL 超时」或「token 验证失败」

**排查：**
1. 确认服务器可通过公网访问
2. 检查 Token 是否与微信公众平台配置一致
3. 查看服务器日志中的签名计算过程

#### 被动回复无响应

**现象：** 用户发送消息后无回复

**排查：**
```python
# 确认处理时间不超过5秒
# 如需异步处理，先回复"收到"，后续通过模板消息通知结果
```

#### 模板消息发送失败

**现象：** 返回 `40001` access_token 错误

**解决：**
```python
# 清除 Token 缓存
adapter._access_token = None
adapter._token_expires_at = 0
```

### 通用排查

#### Gateway 连接失败

```bash
# 测试 Gateway 是否运行
curl http://localhost:8765/health

# 检查环境变量
export GATEWAY_URL=http://localhost:8765
```

#### 查看日志

```bash
# 查看详细日志
tail -f logs/curriculum_forge.log | grep -E "(feishu|weixin|channel)"

# 调试模式
export LOG_LEVEL=DEBUG
python main.py --gateway
```

---

## 高级配置

### 自定义消息处理器

```python
from channels.bridge import ChannelJobBridge, BridgeConfig

async def custom_handler(message, channel_type):
    """自定义消息处理逻辑"""
    print(f"收到 {channel_type} 消息: {message}")
    # 自定义处理...
    return "处理结果"

config = BridgeConfig(
    gateway_url="http://localhost:8765",
    default_profile="rl_controller"
)

bridge = ChannelJobBridge(config)
bridge.on_message = custom_handler
```

### 多渠道同时启用

```python
from fastapi import FastAPI
from channels import setup_feishu_webhook, setup_weixin_webhook

app = FastAPI()

# 同时启用飞书和微信
setup_feishu_webhook(app)
setup_weixin_webhook(app)
```

### 安全配置

**IP 白名单：**
- 飞书：在「事件订阅」中配置 IP 白名单
- 微信：在「开发-基本配置」中配置服务器 IP

**HTTPS 强制：**
生产环境必须使用 HTTPS，建议使用 Nginx 反向代理：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhooks/ {
        proxy_pass http://localhost:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 参考链接

- [飞书开放平台文档](https://open.feishu.cn/document/)
- [微信公众平台开发文档](https://developers.weixin.qq.com/doc/offiaccount/)
- [Curriculum Forge Gateway API](./GATEWAY_API_CN.md)

---

*文档版本: 1.0*
*最后更新: 2026-04-24*
