# Curriculum-Forge 灾备与恢复方案

**版本**: 1.0.0  
**更新日期**: 2026-04-28

---

## 目录

1. [概述](#概述)
2. [备份策略](#备份策略)
3. [数据备份](#数据备份)
4. [恢复流程](#恢复流程)
5. [灾难场景与应对](#灾难场景与应对)
6. [高可用架构](#高可用架构)
7. [备份监控与告警](#备份监控与告警)
8. [演练计划](#演练计划)

---

## 概述

本文档定义 Curriculum-Forge (AI Agent Town) 系统的灾备与恢复方案，确保在各类故障场景下能够快速恢复服务，最小化数据丢失。

### 关键指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| RTO (恢复时间目标) | < 30 分钟 | 从灾难发生到服务恢复的时间 |
| RPO (恢复点目标) | < 1 小时 | 可接受的最大数据丢失量 |
| 备份频率 | 每小时增量 + 每日全量 | 数据备份周期 |
| 演练频率 | 每季度一次 | 灾备演练周期 |

---

## 备份策略

### 三级备份架构

```
┌─────────────────────────────────────────────────────────────┐
│                    备份架构拓扑                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────────────────┐   │
│   │ 本地备份 │───▶│ 异地备份 │───▶│ 云端备份 (S3/OSS)   │   │
│   │ (热)    │    │ (温)    │    │ (冷)                │   │
│   └─────────┘    └─────────┘    └─────────────────────┘   │
│                                                             │
│   保留 7 天       保留 30 天      保留 90 天                │
│   快速恢复        异地容灾        合规归档                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 备份类型

| 类型 | 频率 | 内容 | 存储位置 |
|------|------|------|----------|
| 全量备份 | 每日 02:00 | 所有数据 | 本地 + 异地 + 云端 |
| 增量备份 | 每小时 | 变更数据 | 本地 + 异地 |
| 实时复制 | 持续 | 关键数据 | 本地从节点 |

---

## 数据备份

### 需要备份的数据

#### 1. 数据目录 (`data/`)

```
data/
├── auth/              # 用户认证数据
│   ├── users.json     # 用户信息 (含密码哈希)
│   └── api_keys.json  # API 密钥
├── checkpoints/       # 运行时检查点
├── vault/             # 知识库页面 (Markdown)
├── tenants/           # 租户数据
│   └── {tenant_id}/   # 租户隔离目录
└── audit/             # 审计日志
    └── audit.log      # JSONL 格式
```

#### 2. 配置文件

```
config/
├── gateway.yaml       # 网关配置
├── coordinator.yaml   # 协调器配置
└── profiles/          # 任务配置文件

.env                   # 环境变量 (含密钥)
```

#### 3. 日志文件

```
logs/
├── gateway.log
├── coordinator.log
└── error.log
```

### 备份脚本

#### 全量备份脚本 (`scripts/backup_full.sh`)

```bash
#!/bin/bash
# Curriculum-Forge 全量备份脚本

set -e

# 配置
BACKUP_DIR="/backup/curriculum-forge"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="full_${DATE}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# 创建备份目录
mkdir -p "${BACKUP_PATH}"

echo "[$(date)] 开始全量备份: ${BACKUP_NAME}"

# 1. 备份数据目录
echo "备份数据目录..."
tar -czf "${BACKUP_PATH}/data.tar.gz" -C /app data/

# 2. 备份配置文件
echo "备份配置文件..."
tar -czf "${BACKUP_PATH}/config.tar.gz" -C /app config/
cp /app/.env "${BACKUP_PATH}/env.backup" 2>/dev/null || true

# 3. 备份日志 (可选)
echo "备份日志..."
tar -czf "${BACKUP_PATH}/logs.tar.gz" -C /app logs/ 2>/dev/null || true

# 4. 生成备份清单
cat > "${BACKUP_PATH}/manifest.json" << EOF
{
  "backup_name": "${BACKUP_NAME}",
  "backup_type": "full",
  "timestamp": "$(date -Iseconds)",
  "version": "$(git -C /app rev-parse HEAD 2>/dev/null || echo 'unknown')",
  "files": [
    "data.tar.gz",
    "config.tar.gz",
    "logs.tar.gz",
    "env.backup"
  ],
  "size_bytes": $(du -sb "${BACKUP_PATH}" | cut -f1)
}
EOF

# 5. 计算校验和
sha256sum "${BACKUP_PATH}"/*.tar.gz > "${BACKUP_PATH}/checksums.sha256"

echo "[$(date)] 全量备份完成: ${BACKUP_PATH}"

# 6. 同步到异地 (如果配置)
if [ -n "${REMOTE_BACKUP_HOST}" ]; then
    echo "同步到异地备份服务器..."
    rsync -avz --delete "${BACKUP_DIR}/" "${REMOTE_BACKUP_HOST}:${REMOTE_BACKUP_PATH}/"
fi

# 7. 同步到云端 (如果配置)
if [ -n "${S3_BUCKET}" ]; then
    echo "同步到云端存储..."
    aws s3 sync "${BACKUP_DIR}/" "s3://${S3_BUCKET}/backups/" --storage-class STANDARD_IA
fi

# 8. 清理旧备份 (本地保留 7 天)
find "${BACKUP_DIR}" -type d -name "full_*" -mtime +7 -exec rm -rf {} \; 2>/dev/null || true

echo "[$(date)] 备份清理完成"
```

#### 增量备份脚本 (`scripts/backup_incremental.sh`)

```bash
#!/bin/bash
# Curriculum-Forge 增量备份脚本

set -e

BACKUP_DIR="/backup/curriculum-forge"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="incr_${DATE}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
LAST_BACKUP=$(ls -td "${BACKUP_DIR}/full_"* 2>/dev/null | head -1)

if [ -z "${LAST_BACKUP}" ]; then
    echo "错误: 未找到全量备份，请先执行全量备份"
    exit 1
fi

mkdir -p "${BACKUP_PATH}"

echo "[$(date)] 开始增量备份: ${BACKUP_NAME} (基于 ${LAST_BACKUP})"

# 使用 rsync 增量同步
rsync -av --link-dest="${LAST_BACKUP}" /app/data/ "${BACKUP_PATH}/data/"
rsync -av --link-dest="${LAST_BACKUP}" /app/config/ "${BACKUP_PATH}/config/"

# 生成清单
cat > "${BACKUP_PATH}/manifest.json" << EOF
{
  "backup_name": "${BACKUP_NAME}",
  "backup_type": "incremental",
  "base_backup": "$(basename ${LAST_BACKUP})",
  "timestamp": "$(date -Iseconds)"
}
EOF

# 清理旧增量备份 (保留 24 小时)
find "${BACKUP_DIR}" -type d -name "incr_*" -mtime +1 -exec rm -rf {} \; 2>/dev/null || true

echo "[$(date)] 增量备份完成"
```

### 定时任务配置

```bash
# /etc/cron.d/curriculum-forge-backup

# 每日 02:00 全量备份
0 2 * * * forge /app/scripts/backup_full.sh >> /var/log/forge-backup.log 2>&1

# 每小时增量备份
0 * * * * forge /app/scripts/backup_incremental.sh >> /var/log/forge-backup.log 2>&1
```

---

## 恢复流程

### 恢复优先级

1. **认证数据** (auth/) — 用户无法登录则完全不可用
2. **知识库数据** (vault/) — 核心业务数据
3. **检查点数据** (checkpoints/) — 运行中的任务
4. **租户数据** (tenants/) — 多租户隔离
5. **配置文件** (config/, .env) — 服务配置
6. **审计日志** (audit/) — 合规要求
7. **普通日志** (logs/) — 调试用途

### 完整恢复流程

#### 步骤 1: 评估灾难范围

```bash
# 检查服务状态
systemctl status curriculum-forge

# 检查数据完整性
ls -la /app/data/
cat /app/data/auth/users.json | python3 -m json.tool

# 检查磁盘状态
df -h
dmesg | grep -i error
```

#### 步骤 2: 选择恢复点

```bash
# 列出可用备份
ls -la /backup/curriculum-forge/

# 查看备份清单
cat /backup/curriculum-forge/full_20260428_020000/manifest.json

# 验证备份完整性
cd /backup/curriculum-forge/full_20260428_020000/
sha256sum -c checksums.sha256
```

#### 步骤 3: 停止服务

```bash
# 优雅停止
systemctl stop curriculum-forge

# 或使用 Docker
docker-compose down

# 确认进程已停止
ps aux | grep -E "(gateway|coordinator)" | grep -v grep
```

#### 步骤 4: 恢复数据

```bash
# 创建当前数据快照 (以防万一)
mv /app/data /app/data.corrupted.$(date +%s)
mv /app/config /app/config.corrupted.$(date +%s)

# 恢复数据目录
tar -xzf /backup/curriculum-forge/full_20260428_020000/data.tar.gz -C /app/
tar -xzf /backup/curriculum-forge/full_20260428_020000/config.tar.gz -C /app/

# 恢复环境变量
cp /backup/curriculum-forge/full_20260428_020000/env.backup /app/.env
chmod 600 /app/.env

# 应用增量备份 (如果有)
if [ -d "/backup/curriculum-forge/incr_20260428_030000" ]; then
    rsync -av /backup/curriculum-forge/incr_20260428_030000/data/ /app/data/
fi
```

#### 步骤 5: 验证数据完整性

```bash
# 检查用户数据
python3 -c "
import json
with open('/app/data/auth/users.json') as f:
    users = json.load(f)
    print(f'用户数量: {len(users)}')
    for u in users[:3]:
        print(f'  - {u[\"username\"]}')
"

# 检查知识库
ls -la /app/data/vault/
wc -l /app/data/vault/*.md

# 检查审计日志
tail -5 /app/data/audit/audit.log | python3 -m json.tool
```

#### 步骤 6: 重启服务

```bash
# 启动服务
systemctl start curriculum-forge

# 或使用 Docker
docker-compose up -d

# 检查启动日志
journalctl -u curriculum-forge -f
```

#### 步骤 7: 功能验证

```bash
# 健康检查
curl http://localhost:8765/health

# 用户登录测试
curl -X POST http://localhost:8765/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# 知识库查询测试
curl -H "X-API-Key: your-key" http://localhost:8765/memory/stats
```

### 单表/单文件恢复

当只需要恢复特定数据时：

```bash
# 只恢复用户数据
tar -xzf /backup/curriculum-forge/full_20260428_020000/data.tar.gz \
  -C /app/ data/auth/users.json

# 只恢复知识库
tar -xzf /backup/curriculum-forge/full_20260428_020000/data.tar.gz \
  -C /app/ data/vault/

# 只恢复租户数据
tar -xzf /backup/curriculum-forge/full_20260428_020000/data.tar.gz \
  -C /app/ data/tenants/tenant_001/
```

---

## 灾难场景与应对

### 场景 1: 磁盘故障

**症状**: 磁盘 I/O 错误、文件系统只读

**应对**:
1. 立即将服务切换到备用节点 (如果有)
2. 更换故障磁盘
3. 从异地/云端备份恢复数据
4. 验证数据完整性后恢复服务

**预估 RTO**: 2-4 小时

### 场景 2: 数据误删

**症状**: 用户/租户数据被意外删除

**应对**:
1. 立即停止写入操作 (避免覆盖)
2. 定位最近的备份点
3. 只恢复被删除的数据
4. 验证恢复结果

**预估 RTO**: 30 分钟 - 1 小时

### 场景 3: 勒索软件攻击

**症状**: 文件被加密、勒索信息

**应对**:
1. 立即断开网络
2. 隔离受影响系统
3. 从已知干净的备份恢复
4. 重置所有凭证
5. 进行安全审计

**预估 RTO**: 4-8 小时

### 场景 4: 数据中心故障

**症状**: 整个数据中心不可用

**应对**:
1. 激活异地灾备中心
2. 从云端备份恢复数据
3. 更新 DNS 指向灾备中心
4. 通知用户服务迁移

**预估 RTO**: 4-8 小时

### 场景 5: 数据库损坏

**症状**: JSON 文件解析失败、数据不一致

**应对**:
1. 尝试从损坏文件中提取可恢复数据
2. 从备份恢复完整数据
3. 合并步骤 1 中提取的数据
4. 运行数据一致性检查

**预估 RTO**: 1-2 小时

---

## 高可用架构

### 主从复制架构

```
┌─────────────────────────────────────────────────────────────┐
│                    高可用架构拓扑                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ┌─────────────┐                         │
│                    │   负载均衡   │                         │
│                    │  (Nginx/ALB) │                        │
│                    └──────┬──────┘                         │
│                           │                                │
│           ┌───────────────┼───────────────┐               │
│           │               │               │               │
│     ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐        │
│     │  主节点   │   │  从节点 1  │   │  从节点 2  │        │
│     │ (RW)      │   │ (RO)      │   │ (RO)      │        │
│     └─────┬─────┘   └─────┬─────┘   └─────┬─────┘        │
│           │               │               │               │
│           └───────────────┼───────────────┘               │
│                           │                                │
│                    ┌──────▼──────┐                        │
│                    │  共享存储   │                        │
│                    │ (NFS/S3)    │                        │
│                    └─────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 故障自动切换

使用 Keeper 模块的 LeaderElection 实现：

```yaml
# config/ha.yaml
high_availability:
  enabled: true
  node_id: "node-1"
  peers:
    - "node-2:8766"
    - "node-3:8766"
  
  election:
    lease_ttl: 30s
    heartbeat_interval: 10s
  
  failover:
    auto_promote: true
    promotion_delay: 60s
```

---

## 备份监控与告警

### Prometheus 指标

```yaml
# monitoring/backup.rules.yml
groups:
  - name: backup_alerts
    rules:
      - alert: BackupMissing
        expr: |
          time() - forge_backup_last_success_timestamp > 86400
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "备份已超过 24 小时未执行"
          description: "上次成功备份时间超过 24 小时"

      - alert: BackupSizeAnomaly
        expr: |
          abs(forge_backup_size_bytes - forge_backup_size_bytes offset 1d) 
          / forge_backup_size_bytes offset 1d > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "备份大小异常变化"
          description: "备份大小较昨日变化超过 50%"
```

### 备份状态端点

```python
# 添加到 gateway.py
@app.get("/backup/status")
async def backup_status():
    """备份状态查询"""
    backup_dir = Path(os.getenv("BACKUP_DIR", "/backup/curriculum-forge"))
    
    backups = []
    for d in backup_dir.glob("full_*"):
        manifest_path = d / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            backups.append({
                "name": d.name,
                "timestamp": manifest.get("timestamp"),
                "size_mb": int(d.stat().st_size / 1024 / 1024),
                "type": manifest.get("backup_type", "full")
            })
    
    last_backup = backups[0] if backups else None
    last_success = datetime.fromisoformat(last_backup["timestamp"]) if last_backup else None
    
    return {
        "total_backups": len(backups),
        "last_success": last_success.isoformat() if last_success else None,
        "backups": sorted(backups, key=lambda x: x["timestamp"], reverse=True)[:10]
    }
```

---

## 演练计划

### 演练时间表

| 演练类型 | 频率 | 参与人员 | 目标 |
|----------|------|----------|------|
| 桌面演练 | 每月 | 运维团队 | 熟悉流程 |
| 单表恢复演练 | 每月 | 运维 + 开发 | 验证数据恢复 |
| 完整恢复演练 | 每季度 | 全团队 | 验证 RTO/RPO |
| 异地切换演练 | 每半年 | 全团队 + 管理层 | 验证灾备中心 |

### 演练检查清单

#### 演练前

- [ ] 通知所有相关人员
- [ ] 准备演练环境 (隔离生产数据)
- [ ] 检查备份完整性
- [ ] 准备回滚方案

#### 演练中

- [ ] 记录每个步骤的耗时
- [ ] 记录遇到的问题
- [ ] 验证数据完整性
- [ ] 验证服务功能

#### 演练后

- [ ] 编写演练报告
- [ ] 更新文档
- [ ] 改进流程
- [ ] 安排后续培训

### 演练报告模板

```markdown
# 灾备演练报告

**演练日期**: YYYY-MM-DD
**演练类型**: [桌面演练/单表恢复/完整恢复/异地切换]
**参与人员**: [名单]

## 演练目标
- 目标 RTO: XX 分钟
- 目标 RPO: XX 分钟

## 演练结果
- 实际 RTO: XX 分钟
- 实际 RPO: XX 分钟
- 演练结论: [成功/部分成功/失败]

## 问题记录
| 序号 | 问题描述 | 影响等级 | 解决方案 |
|------|----------|----------|----------|
| 1 | ... | 高/中/低 | ... |

## 改进建议
1. ...
2. ...

## 下次演练计划
- 时间: YYYY-MM-DD
- 类型: ...
```

---

## 附录

### A. 备份命令速查

```bash
# 手动全量备份
/app/scripts/backup_full.sh

# 手动增量备份
/app/scripts/backup_incremental.sh

# 列出所有备份
ls -la /backup/curriculum-forge/

# 验证备份
sha256sum -c /backup/curriculum-forge/full_*/checksums.sha256

# 查看备份内容
tar -tzf /backup/curriculum-forge/full_*/data.tar.gz | head

# 恢复单个文件
tar -xzf backup.tar.gz path/to/file -C /
```

### B. 紧急联系人

| 角色 | 姓名 | 电话 | 邮箱 |
|------|------|------|------|
| 运维主管 | - | - | - |
| DBA | - | - | - |
| 安全主管 | - | - | - |
| 技术总监 | - | - | - |

### C. 相关文档

- [部署指南](./DEPLOYMENT_CN.md)
- [配置指南](./CONFIG_GUIDE_CN.md)
- [安全指南](./SECURITY_GUIDE_CN.md)
- [监控配置](../monitoring/README.md)

---

**文档维护**: 本文档应每季度审核更新一次，确保与实际架构一致。
