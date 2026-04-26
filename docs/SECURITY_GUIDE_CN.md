# 安全指南

本文档涵盖 Curriculum-Forge 的安全认证、权限控制和敏感信息保护机制。

---

## 概述

Curriculum-Forge 从 P6 版本开始引入完整的安全体系，包括：

| 功能 | 说明 | 状态 |
|------|------|------|
| API Key 认证 | 基于密钥的访问控制 | ✅ 已启用 |
| JWT 认证 | 基于 Token 的会话管理 | ✅ 已启用 |
| RBAC 权限控制 | 角色-based 访问控制 | ✅ 已启用 |
| 速率限制 | 请求频率限制 | ✅ 已启用 |
| 输入验证 | Pydantic Schema 校验 | ✅ 已启用 |
| 敏感信息保护 | 响应脱敏、日志脱敏、错误脱敏 | ✅ 已启用 |

---

## 启用安全认证

默认情况下，安全认证**关闭**（开发模式）。生产环境必须启用：

```bash
export CF_ENABLE_AUTH=1
python main.py --gateway
```

或在启动命令中指定：

```bash
CF_ENABLE_AUTH=1 python main.py --gateway
```

---

## API Key 认证

### 创建 API Key

```bash
POST /auth/keys
Content-Type: application/json
Authorization: Bearer <admin-jwt-token>

{
  "name": "production-key",
  "scope": "write",
  "rate_limit_per_hour": 1000
}
```

**响应（仅创建时返回完整 Key）：**

```json
{
  "id": "key_abc123",
  "name": "production-key",
  "api_key": "cf_live_xxxxxxxxxxxxxxxx",
  "scope": "write",
  "rate_limit_per_hour": 1000,
  "created_at": "2026-04-26T10:00:00Z"
}
```

> ⚠️ **重要**：`api_key` 字段仅创建时返回，请务必保存。后续查询将显示脱敏版本。

### 使用 API Key

**方式一：X-API-Key 请求头**

```bash
curl -H "X-API-Key: cf_live_xxxxxxxxxxxxxxxx" \
     http://localhost:8765/jobs
```

**方式二：Bearer Token**

```bash
curl -H "Authorization: Bearer cf_live_xxxxxxxxxxxxxxxx" \
     http://localhost:8765/jobs
```

### Key 权限范围

| Scope | 权限 |
|-------|------|
| `read` | 只读访问（GET 请求） |
| `write` | 读写访问（包含 POST/PUT/DELETE） |
| `admin` | 全部权限（包含用户管理、角色管理） |

> write 自动继承 read，admin 自动继承 write。

### 列出 API Keys

```bash
GET /auth/keys
Authorization: Bearer <jwt-token>
```

### 删除 API Key

```bash
DELETE /auth/keys/{key_id}
Authorization: Bearer <admin-jwt-token>
```

---

## JWT 认证

### 登录获取 Token

```bash
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your-password"
}
```

**响应：**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

- **Access Token**: 15 分钟有效期
- **Refresh Token**: 7 天有效期

### 使用 Access Token

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
     http://localhost:8765/jobs
```

### 刷新 Token

```bash
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### 登出

```bash
POST /auth/logout
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 查看当前用户

```bash
GET /auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## RBAC 权限控制

### 默认角色

系统预定义 3 个角色：

| 角色 | 权限范围 |
|------|----------|
| `admin` | 全部权限（*.*） |
| `operator` | jobs.*, templates.*, schedules.*, acp.* |
| `viewer` | jobs.read, templates.read, schedules.read, profiles.read |

### 权限格式

权限使用 `resource.action` 格式：

- `jobs.read` — 查看任务
- `jobs.write` — 创建/修改任务
- `jobs.delete` — 删除任务
- `auth.admin` — 管理认证
- `users.manage` — 管理用户
- `*.*` — 全部权限（通配符）

### 查看角色列表

```bash
GET /roles
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 查看角色详情

```bash
GET /roles/admin
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 创建自定义角色

```bash
POST /roles
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "name": "data-scientist",
  "display_name": "数据科学家",
  "description": "可以创建和查看任务，但不能管理用户",
  "permissions": ["jobs.*", "templates.read", "profiles.read"]
}
```

### 为用户分配角色

创建用户时指定角色：

```bash
POST /users
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "username": "zhangsan",
  "password": "secure-password",
  "email": "zhangsan@example.com",
  "full_name": "张三",
  "roles": ["operator", "data-scientist"]
}
```

或更新现有用户：

```bash
PUT /users/{user_id}
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "roles": ["viewer"]
}
```

---

## 用户管理

### 创建用户（仅 admin）

```bash
POST /users
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "username": "newuser",
  "password": "secure-password",
  "email": "user@example.com",
  "full_name": "新用户",
  "roles": ["viewer"]
}
```

### 列出用户

```bash
GET /users
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 获取用户详情

```bash
GET /users/{user_id}
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 修改密码

```bash
POST /users/{user_id}/password
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Content-Type: application/json

{
  "current_password": "old-password",
  "new_password": "new-secure-password"
}
```

### 删除用户

```bash
DELETE /users/{user_id}
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## 敏感信息保护

### 自动脱敏机制

系统对以下敏感信息自动脱敏：

| 数据类型 | 脱敏方式 | 示例 |
|----------|----------|------|
| API Key | 显示前 8 位 + *** | `cf_live_12******` |
| 密码哈希 | 完全不返回 | — |
| 邮箱 | 部分掩码 | `zha***@example.com` |
| 失败登录次数 | 不暴露 | — |
| 账户锁定时间 | 不暴露 | — |

### 安全响应头

所有响应自动包含以下安全头：

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'
```

### 错误信息脱敏

生产环境下，错误响应不会暴露：
- 内部文件路径
- 堆栈跟踪
- 数据库详情
- 配置信息

**开发模式**（`CF_ENABLE_AUTH=0`）会显示完整错误信息便于调试。

---

## 速率限制

API Key 支持按小时限制请求次数：

```bash
POST /auth/keys
Content-Type: application/json

{
  "name": "limited-key",
  "scope": "read",
  "rate_limit_per_hour": 100
}
```

超出限制返回：

```json
{
  "detail": "Rate limit exceeded: 100 requests per hour"
}
```

---

## 输入验证

所有端点使用 Pydantic 进行严格的输入验证：

- 类型检查（字符串、整数、布尔值等）
- 必填字段验证
- 范围限制（如 `limit` 参数 1-500）
- 格式验证（如邮箱格式）

验证失败返回 422：

```json
{
  "detail": [
    {
      "loc": ["body", "username"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 安全最佳实践

### 1. 生产环境必做

- [ ] 设置 `CF_ENABLE_AUTH=1`
- [ ] 修改默认 admin 密码
- [ ] 为不同服务创建独立的 API Key
- [ ] 启用 HTTPS（通过 Nginx/Traefik）
- [ ] 配置防火墙限制访问 IP

### 2. API Key 管理

- 定期轮换 API Key（建议 90 天）
- 不同环境使用不同的 Key（开发/测试/生产）
- 离职员工立即撤销其 Key
- 避免在代码中硬编码 Key，使用环境变量

### 3. 用户密码策略

- 最小长度 8 位
- 包含大小写字母、数字、特殊字符
- 定期更换密码
- 5 次失败登录后自动锁定 15 分钟

### 4. 日志审计

所有认证和授权操作记录审计日志：

```bash
GET /audit?action=login
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

查看审计统计：

```bash
GET /audit/stats
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

## 故障排查

### 401 Unauthorized

- 未提供认证信息
- Token 已过期
- API Key 已被撤销

### 403 Forbidden

- 认证成功但权限不足
- 用户角色不包含所需权限

### 429 Too Many Requests

- 超出 API Key 的速率限制
- 等待一小时后重试或申请更高限额

### 账户锁定

连续 5 次密码错误后账户锁定 15 分钟：

```json
{
  "detail": "Account locked due to too many failed login attempts. Try again after 15 minutes."
}
```

---

## 相关文档

- [部署指南](./DEPLOYMENT_CN.md) — 生产环境部署
- [Gateway API](./GATEWAY_API_CN.md) — 完整 API 参考
- [配置指南](./CONFIG_GUIDE_CN.md) — 环境变量和配置覆盖
