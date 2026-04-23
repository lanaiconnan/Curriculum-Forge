"""
Channel → Job Bridge

桥接 Channel 消息与 Gateway Job 创建：
- 解析用户命令（run/status/list/log/help）
- 调用 Gateway REST API 创建 Job
- 返回回复文本供 Channel 发送给用户

Usage:
    bridge = ChannelJobBridge(gateway_url="http://localhost:8765")

    # 用于飞书/微信的 on_message 回调
    def on_message(msg):
        return bridge.on_message(msg)

    # 或异步版本
    async def on_message_async(msg):
        return await bridge.on_message_async(msg)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

import httpx

logger = logging.getLogger("channel_bridge")


# ─────────────────────────────────────────────────────────────────────────────
# Bridge Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BridgeConfig:
    """Bridge 配置"""

    gateway_url: str = "http://localhost:8765"
    default_profile: str = "rl_controller"
    max_list_jobs: int = 5

    # 超时设置（秒）
    create_job_timeout: float = 10.0
    get_status_timeout: float = 5.0
    list_jobs_timeout: float = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Command Parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedCommand:
    """解析后的命令"""

    action: str  # run/status/list/log/help/unknown
    topic: Optional[str] = None
    profile: Optional[str] = None
    job_id: Optional[str] = None
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


def parse_command(text: str) -> ParsedCommand:
    """
    解析用户输入的命令

    支持的命令格式：
    - "run <topic>" 或 "run <topic> with <profile>"
    - "workflow <name>" 或 "workflow <name> with <task_types>"
    - "status" 或 "status <job_id>"
    - "list" 或 "list <n>"
    - "log <job_id>"
    - "help"

    Args:
        text: 用户输入文本

    Returns:
        ParsedCommand 实例
    """
    text = text.strip().lower()

    # ── help ────────────────────────────────────────────────────────────────
    if text in ("help", "帮助", "?", "？"):
        return ParsedCommand(action="help")

    # ── list ────────────────────────────────────────────────────────────────
    list_match = re.match(r"^list\s*(\d+)?$", text)
    if list_match:
        limit = int(list_match.group(1)) if list_match.group(1) else 5
        return ParsedCommand(action="list", extra={"limit": limit})

    # ── status ──────────────────────────────────────────────────────────────
    status_match = re.match(r"^status\s*([a-zA-Z0-9\-]+)?$", text)
    if status_match:
        job_id = status_match.group(1)
        return ParsedCommand(action="status", job_id=job_id)

    # ── log ────────────────────────────────────────────────────────────────
    log_match = re.match(r"^log\s+([a-zA-Z0-9\-]+)$", text)
    if log_match:
        job_id = log_match.group(1)
        return ParsedCommand(action="log", job_id=job_id)

    # ── workflow ────────────────────────────────────────────────────────────
    # workflow <name>
    # workflow <name> with <task_types>
    wf_match = re.match(r"^workflow\s+(.+?)(?:\s+with\s+(.+))?$", text)
    if wf_match:
        name = wf_match.group(1).strip()
        task_types_str = wf_match.group(2)
        task_types = [t.strip() for t in task_types_str.split(",")] if task_types_str else None
        return ParsedCommand(action="workflow", topic=name, extra={"task_types": task_types})

    # ── run ─────────────────────────────────────────────────────────────────
    # run <topic>
    # run <topic> with <profile>
    run_match = re.match(r"^run\s+(.+?)(?:\s+with\s+(\w+))?$", text)
    if run_match:
        topic = run_match.group(1).strip()
        profile = run_match.group(2)
        return ParsedCommand(action="run", topic=topic, profile=profile)

    # ── unknown ─────────────────────────────────────────────────────────────
    return ParsedCommand(action="unknown", extra={"raw_text": text})


# ─────────────────────────────────────────────────────────────────────────────
# Channel Job Bridge
# ─────────────────────────────────────────────────────────────────────────────

class ChannelJobBridge:
    """
    Channel → Job 桥接器

    功能：
    - 解析用户命令
    - 调用 Gateway REST API
    - 返回回复文本

    支持：
    - 同步调用（用于微信被动回复）
    - 异步调用（用于飞书等异步场景）
    """

    def __init__(
        self,
        config: Optional[BridgeConfig] = None,
        on_job_created: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.config = config or BridgeConfig()
        self.on_job_created = on_job_created
        self._http_sync = httpx.Client(timeout=30.0)
        self._http_async = httpx.AsyncClient(timeout=30.0)

    def close(self):
        """关闭 HTTP 客户端"""
        self._http_sync.close()

    async def aclose(self):
        """关闭异步 HTTP 客户端"""
        await self._http_async.aclose()

    # ── Message Handling ──────────────────────────────────────────────────────

    def on_message(self, message: Union[Dict[str, Any], Any]) -> Optional[str]:
        """
        同步处理 Channel 消息（用于微信被动回复）

        Args:
            message: 飞书消息 dict 或微信 WeixinMessage 对象

        Returns:
            回复文本（None 表示不回复）
        """
        # 提取消息文本
        text = self._extract_text(message)
        if not text:
            return None

        # 解析命令
        cmd = parse_command(text)

        # 执行命令（同步）
        return self._execute_command_sync(cmd, message)

    async def on_message_async(self, message: Union[Dict[str, Any], Any]) -> Optional[str]:
        """
        异步处理 Channel 消息

        Args:
            message: 飞书消息 dict 或微信 WeixinMessage 对象

        Returns:
            回复文本（None 表示不回复）
        """
        text = self._extract_text(message)
        if not text:
            return None

        cmd = parse_command(text)
        return await self._execute_command_async(cmd, message)

    def _extract_text(self, message: Union[Dict[str, Any], Any]) -> Optional[str]:
        """从消息对象中提取文本内容"""
        # 飞书消息 dict
        if isinstance(message, dict):
            content = message.get("content", {})
            if isinstance(content, dict):
                # 文本消息
                if "text" in content:
                    return content["text"]
                # 其他类型（可以扩展）
                return None
            return None

        # 微信 WeixinMessage 对象
        if hasattr(message, "content"):
            return message.content

        # 字符串
        if isinstance(message, str):
            return message

        return None

    # ── Command Execution (Sync) ──────────────────────────────────────────────

    def _execute_command_sync(
        self,
        cmd: ParsedCommand,
        message: Union[Dict[str, Any], Any],
    ) -> Optional[str]:
        """同步执行命令"""

        if cmd.action == "help":
            return self._help_text()

        if cmd.action == "list":
            return self._list_jobs_sync(cmd.extra.get("limit", 5))

        if cmd.action == "status":
            return self._get_status_sync(cmd.job_id)

        if cmd.action == "log":
            return self._get_log_sync(cmd.job_id)

        if cmd.action == "run":
            return self._create_job_sync(cmd, message)

        if cmd.action == "workflow":
            return self._create_workflow_sync(cmd, message)

        # unknown
        return None

    def _list_jobs_sync(self, limit: int) -> str:
        """同步列出 Jobs"""
        try:
            resp = self._http_sync.get(
                f"{self.config.gateway_url}/jobs",
                params={"limit": limit},
                timeout=self.config.list_jobs_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            jobs = data.get("jobs", [])
            if not jobs:
                return "📭 暂无任务记录"

            lines = ["📋 最近任务："]
            for i, job in enumerate(jobs, 1):
                state = job.get("state", "unknown")
                phase = job.get("phase", "unknown")
                desc = job.get("description", "")[:30]
                job_id = job.get("id", "")[:8]
                lines.append(f"{i}. [{state}] {job_id}... - {desc}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"列出 Jobs 失败: {e}")
            return f"❌ 查询失败: {str(e)[:50]}"

    def _get_status_sync(self, job_id: Optional[str]) -> str:
        """同步查询 Job 状态"""
        if not job_id:
            # 返回最近一个 Job 的状态
            try:
                resp = self._http_sync.get(
                    f"{self.config.gateway_url}/jobs",
                    params={"limit": 1},
                    timeout=self.config.get_status_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                jobs = data.get("jobs", [])
                if not jobs:
                    return "📭 暂无任务"
                job_id = jobs[0].get("id")
            except Exception as e:
                return f"❌ 查询失败: {str(e)[:50]}"

        try:
            resp = self._http_sync.get(
                f"{self.config.gateway_url}/jobs/{job_id}",
                timeout=self.config.get_status_timeout,
            )
            resp.raise_for_status()
            job = resp.json()

            state = job.get("state", "unknown")
            phase = job.get("phase", "unknown")
            desc = job.get("description", "")

            # 状态映射
            state_emoji = {
                "pending": "⏳",
                "running": "🔄",
                "waiting": "⏸️",
                "completed": "✅",
                "failed": "❌",
                "cancelled": "🚫",
            }.get(state.lower(), "❓")

            lines = [
                f"{state_emoji} 任务状态：{state}",
                f"阶段：{phase}",
                f"描述：{desc[:50] if desc else '无'}",
                f"ID：{job_id}",
            ]

            # 添加指标（如果有）
            metrics = job.get("metrics", {})
            if metrics:
                lines.append("📊 指标：")
                for k, v in metrics.items():
                    lines.append(f"  - {k}: {v}")

            return "\n".join(lines)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"❌ 任务不存在: {job_id[:8]}..."
            return f"❌ 查询失败: HTTP {e.response.status_code}"
        except Exception as e:
            return f"❌ 查询失败: {str(e)[:50]}"

    def _get_log_sync(self, job_id: str) -> str:
        """同步查询 Job 日志"""
        # Gateway 暂时没有专门的日志端点，用 status 代替
        return self._get_status_sync(job_id)

    def _create_job_sync(
        self,
        cmd: ParsedCommand,
        message: Union[Dict[str, Any], Any],
    ) -> str:
        """同步创建 Job"""
        profile = cmd.profile or self.config.default_profile

        # 提取用户 ID（用于标识任务来源）
        user_id = self._extract_user_id(message)

        try:
            resp = self._http_sync.post(
                f"{self.config.gateway_url}/jobs",
                json={
                    "profile": profile,
                    "config": {
                        "topic": cmd.topic,
                        "source": "channel",
                        "user_id": user_id,
                    },
                },
                timeout=self.config.create_job_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            job = data.get("job", {})
            job_id = job.get("id", "unknown")

            # 回调
            if self.on_job_created:
                try:
                    self.on_job_created(job_id, job)
                except Exception as e:
                    logger.exception(f"on_job_created 回调失败: {e}")

            return f"✅ 任务已创建\nID: {job_id}\n执行中..."

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"❌ Profile 不存在: {profile}"
            return f"❌ 创建失败: HTTP {e.response.status_code}"
        except httpx.ConnectError:
            return "❌ Gateway 未启动，请检查服务状态"
        except Exception as e:
            logger.error(f"创建 Job 失败: {e}")
            return f"❌ 创建失败: {str(e)[:50]}"

    # ── Command Execution (Async) ─────────────────────────────────────────────

    async def _execute_command_async(
        self,
        cmd: ParsedCommand,
        message: Union[Dict[str, Any], Any],
    ) -> Optional[str]:
        """异步执行命令"""
        if cmd.action == "workflow":
            return self._create_workflow_sync(cmd, message)
        # Delegate to sync for other commands
        return self._execute_command_sync(cmd, message)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_user_id(self, message: Union[Dict[str, Any], Any]) -> str:
        """提取用户 ID"""
        # 飞书
        if isinstance(message, dict):
            return message.get("sender_id", "unknown")

        # 微信
        if hasattr(message, "to_user"):
            return message.to_user

        return "unknown"

    def _create_workflow_sync(
        self,
        cmd: ParsedCommand,
        message: Union[Dict[str, Any], Any],
    ) -> str:
        """同步创建 Workflow（多 Agent DAG 协作）"""
        name = cmd.topic or "unnamed_workflow"
        task_types = cmd.extra.get("task_types") or ["environment", "experiment", "review"]
        user_id = self._extract_user_id(message)

        try:
            # Build DAG task definitions
            tasks = []
            for i, ttype in enumerate(task_types):
                task_id = f"task_{ttype}_{i}"
                deps = [f"task_{task_types[i-1]}_{i-1}"] if i > 0 else []
                tasks.append({
                    "id": task_id,
                    "type": ttype,
                    "payload": {
                        "source": "channel",
                        "user_id": user_id,
                        "topic": name,
                    },
                    "dependencies": deps,
                    "stage": ttype,
                })

            resp = self._http_sync.post(
                f"{self.config.gateway_url}/workflows",
                json={
                    "name": name,
                    "description": f"Workflow from channel: {name}",
                    "tasks": tasks,
                },
                timeout=self.config.create_job_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            wf = data.get("workflow", {})
            wf_id = wf.get("id", "unknown")
            task_count = wf.get("tasks", 0)

            return f"✅ Workflow 已创建\nID: {wf_id}\n任务数: {task_count}\n类型: {', '.join(task_types)}\n执行中..."

        except httpx.HTTPStatusError as e:
            return f"❌ 创建 Workflow 失败: HTTP {e.response.status_code}"
        except httpx.ConnectError:
            return "❌ Gateway 未启动，请检查服务状态"
        except Exception as e:
            logger.error(f"创建 Workflow 失败: {e}")
            return f"❌ 创建 Workflow 失败: {str(e)[:50]}"

    def _help_text(self) -> str:
        """返回帮助文本"""
        return """📚 可用命令：

• run <topic> - 创建新任务（自动路由到 Workflow）
  示例: run 机器学习基础

• run <topic> with <profile> - 指定 profile 创建任务
  示例: run Python入门 with pure_harness

• workflow <name> - 创建多 Agent Workflow
  示例: workflow 双Agent训练

• workflow <name> with <task_types> - 指定任务类型
  示例: workflow 实验流程 with environment,experiment,review

• status [job_id] - 查询任务状态
  示例: status
  示例: status abc123

• list [n] - 列出最近 n 个任务
  示例: list
  示例: list 10

• log <job_id> - 查看任务日志
  示例: log abc123

• help - 显示此帮助
"""


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_bridge(
    gateway_url: str = "http://localhost:8765",
    default_profile: str = "rl_controller",
    on_job_created: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> ChannelJobBridge:
    """
    创建 ChannelJobBridge 实例

    Args:
        gateway_url: Gateway URL
        default_profile: 默认 profile 名称
        on_job_created: Job 创建后的回调

    Returns:
        ChannelJobBridge 实例
    """
    config = BridgeConfig(
        gateway_url=gateway_url,
        default_profile=default_profile,
    )
    return ChannelJobBridge(config=config, on_job_created=on_job_created)
