# 部署指南

本文档涵盖 Curriculum-Forge 在生产环境的部署方案。

---

## 环境要求

| 项目 | 最低 | 推荐 |
|------|------|------|
| Python | 3.10+ | 3.11+ |
| 内存 | 2 GB | 8 GB+ |
| 磁盘 | 1 GB | 10 GB+ |
| OS | macOS / Linux | Ubuntu 22.04+ |

> 注意：Phase 1–4 核心依赖为 Python 3.10+ / FastAPI / uvicorn，不强制 GPU。

---

## 依赖安装

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl

pip install -r requirements.txt
# 额外需要的运行时依赖
pip install sse-starlette httpx aiosqlite
```

或使用 `pyproject.toml` 安装（若已配置）：

```bash
pip install -e .
```

---

## 快速启动（开发）

```bash
# 启动 Gateway（默认端口 8765）
python main.py --gateway

# 指定端口
python main.py --gateway --port 8765

# 自动重载（开发时）
python main.py --gateway --reload
```

启动后访问：
- API：`http://localhost:8765/docs`（Swagger UI）
- Web UI：`http://localhost:8765/ui/`

---

## 生产部署

### 1. 使用 Systemd（推荐 Linux）

创建服务文件 `/etc/systemd/system/curriculum-forge.service`：

```ini
[Unit]
Description=Curriculum-Forge Gateway
After=network.target

[Service]
Type=simple
User=lanaiconan
WorkingDirectory=/Users/lanaiconan/.qclaw/workspace/dual-agent-tool-rl
ExecStart=/usr/bin/python3 main.py --gateway --port 8765 --host 0.0.0.0
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"
Environment="CF_TOPIC=Production"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable curriculum-forge
sudo systemctl start curriculum-forge
sudo systemctl status curriculum-forge
```

---

### 2. 使用 Supervisor（Linux 备选）

```ini
# /etc/supervisor/conf.d/curriculum-forge.conf
[program:curriculum-forge]
command=python3 /Users/lanaiconan/.qclaw/workspace/dual-agent-tool-rl/main.py --gateway --port 8765 --host 0.0.0.0
directory=/Users/lanaiconan/.qclaw/workspace/dual-agent-tool-rl
user=lanaiconan
autostart=true
autorestart=true
stdout_logfile=/var/log/curriculum-forge.log
stderr_logfile=/var/log/curriculum-forge.err.log
```

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start curriculum-forge
```

---

### 3. 使用 Docker

#### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir sse-starlette httpx aiosqlite

COPY . .

# 不以 root 运行
USER 1000

EXPOSE 8765

CMD ["python", "main.py", "--gateway", "--port", "8765", "--host", "0.0.0.0"]
```

#### 构建与运行

```bash
docker build -t curriculum-forge:latest .
docker run -d \
  --name curriculum-forge \
  -p 8765:8765 \
  -v ~/.curriculum-forge:/home/python/.curriculum-forge \
  curriculum-forge:latest
```

---

### 4. 使用 Docker Compose

```yaml
version: "3.8"

services:
  gateway:
    build: .
    container_name: curriculum-forge
    ports:
      - "8765:8765"
    volumes:
      - curriculum-forge-data:/home/python/.curriculum-forge
      - ./profiles:/app/profiles:ro
      - ./plugins:/app/plugins:ro
    environment:
      - CF_TOPIC=Production
      - CF_MAX_ITERATIONS=10
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  curriculum-forge-data:
```

```bash
docker compose up -d
docker compose logs -f gateway
```

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CF_TOPIC` | 训练主题 | `Curriculum-Forge` |
| `CF_MAX_ITERATIONS` | 最大迭代次数 | 5 |
| `CF_PASS_THRESHOLD` | 通过阈值 | 0.65 |
| `CF_DIFFICULTY` | 初始难度 | 0.5 |
| `CF_GOAL` | 目标描述 | — |
| `PYTHONUNBUFFERED` | 日志实时输出 | 1 |
| `PORT` | Gateway 端口（覆盖 CLI） | 8765 |

---

## Nginx 反向代理

```nginx
upstream curriculum_forge {
    server 127.0.0.1:8765;
}

server {
    listen 80;
    server_name your-domain.com;

    # 静态文件（UI）
    location /ui/ {
        proxy_pass http://curriculum_forge/ui/;
        proxy_set_header Host $host;
    }

    # SSE 端点需要 Upgrade 支持
    location / {
        proxy_pass http://curriculum_forge;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }

    # SSE/流式响应
    location /jobs/ {
        proxy_pass http://curriculum_forge/jobs/;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
    }

    location /coordinator/ {
        proxy_pass http://curriculum_forge/coordinator/;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
    }
}
```

> **重要**：`proxy_set_header Connection ""` 和 `proxy_buffering off` 对 SSE 流至关重要，缺少会导致流式推送无法正常工作。

---

## 健康检查

Gateway 自带 `/health` 端点：

```bash
curl http://localhost:8765/health
# 返回: {"status": "healthy", "version": "0.1.0", "timestamp": "..."}
```

可用于：
- K8s liveness/readiness probe
- Nginx health check
- 负载均衡器探活

---

## 目录权限

确保以下目录对运行用户可写：

| 路径 | 用途 |
|------|------|
| `~/.curriculum-forge/checkpoints/` | Job checkpoint 数据 |
| `~/.curriculum-forge/logs/` | 审计日志 |
| `workspace/run_*/` | Per-run 工作目录 |

---

## 安全建议

1. **限制 CORS**：生产环境将 `allow_origins=["*"]` 改为具体域名
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://your-ui-domain.com"],
       allow_credentials=True,
       allow_methods=["GET", "POST", "DELETE"],
       allow_headers=["Authorization", "Content-Type"],
   )
   ```

2. **认证**：当前 API 无内置认证，建议通过 Nginx/Istio 添加 JWT 验证层，或在 API 网关层处理

3. **网络隔离**：Gateway 仅暴露必要端口（8765），数据库端口不应暴露

4. **飞书/微信 Webhook 密钥**：使用 `verification_token` / `encrypt_key` 进行签名验证

---

## 日志管理

### 应用日志

日志输出到 stdout，由 systemd/supervisor 捕获：

```bash
# systemd
journalctl -u curriculum-forge -f

# Docker
docker logs -f curriculum-forge
```

### 审计日志

审计日志路径：`~/.curriculum-forge/logs/audit_YYYY-MM-DD.jsonl`

```bash
# 查看今日日志
cat ~/.curriculum-forge/logs/audit_$(date +%Y-%m-%d).jsonl | jq .

# 统计今日事件
curl http://localhost:8765/audit/stats
```

---

## 备份与恢复

### Checkpoint 数据

```bash
# 备份
cp -r ~/.curriculum-forge/checkpoints/ /backup/checkpoints_$(date +%Y%m%d)/

# 恢复
cp -r /backup/checkpoints_20260401/ ~/.curriculum-forge/
```

### 完整备份

```bash
tar czf curriculum-forge-backup_$(date +%Y%m%d).tar.gz \
  ~/.curriculum-forge/ \
  ~/.qclaw/workspace/dual-agent-tool-rl/profiles/ \
  ~/.qclaw/workspace/dual-agent-tool-rl/plugins/
```

---

## 升级

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl

# 拉取最新代码
git pull

# 安装新依赖
pip install -r requirements.txt

# 重启服务
sudo systemctl restart curriculum-forge
# 或
docker compose restart gateway
```

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 启动后 503 No coordinator | Coordinator 初始化失败，检查 Agent 配置 |
| SSE 流不推送 | 检查 Nginx `proxy_buffering off` |
| 飞书 Webhook 报签名错误 | 确认 `verification_token` 与飞书后台一致 |
| 微信无法接收消息 | 确认外网可达，80/443 端口开放 |
| Checkpoint 数据损坏 | 从备份恢复，或删除损坏文件后重启 |

---

**Gateway 启动示例：**
```bash
python main.py --gateway --port 8765 --host 0.0.0.0
```
