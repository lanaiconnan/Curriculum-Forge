"""Forge Adapters — 跨 Agent 统一适配层

核心理念：同一套 HarnessCase，能跑在任意 Agent 上。
只要实现 AgentAdapter 协议，无需改动 HarnessRunner。

支持现状：
    ✅ OpenClaw     — QueryEngine 封装
    ✅ Claude Code  — 待验证（需实际环境）
    ⚠️ Letta       — MCP/SDK 接口，待探索
    ⚠️ Goose       — MCP/SDK 接口，待探索

使用方式：

    from forge.adapters import OpenClawAdapter, make_harness_runner

    # 直接构建
    adapter = OpenClawAdapter(query_engine)
    runner  = HarnessRunner(adapter)

    # 或使用工厂函数
    runner = make_harness_runner("openclaw", engine=engine)
    runner = make_harness_runner("mock")

"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from services.harness import HarnessRunner, HarnessCase, HarnessReport

# ─── Adapter 协议 ──────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """
    标准化的工具调用表示。
    
    所有 Adapter 必须将各自 Agent 的工具调用格式
    转换为这个统一格式。
    """
    name: str                      # 工具名
    input: Dict[str, Any]          # 参数字典
    raw: Any = None                # 原始格式（保留，for 调试）

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "input": self.input}


@dataclass
class AgentResult:
    """
    标准化的 Agent 执行结果。
    
    这是 HarnessRunner 与具体 Agent 实现之间的唯一接口。
    """
    final_response: str                     # 最终文本响应
    tool_calls: List[ToolCall]              # 工具调用列表
    turns: int                              # 交互轮数
    success: bool                           # 是否成功
    error: Optional[str] = None             # 错误信息
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """
    Agent 适配器抽象接口。
    
    所有 Agent 实现（OpenClaw、Claude Code、Letta、Goose 等）
    只需实现这 4 个方法即可接入 Harness 评测体系。
    
    实现指南：
    1. submit()     — 核心：接收 prompt，返回 AgentResult
    2. reset()      — 重置对话历史（每次 HarnessCase 独立运行）
    3. get_name()   — 返回 Agent 名称（用于报告标注）
    4. get_tools()  — 返回可用工具列表（用于注册）
    
    可选覆写：
    - submit_messages()  — 如果 Agent 支持直接传 messages 而非单条 prompt
    """

    @abstractmethod
    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        """
        提交 prompt，获取 Agent 执行结果。
        
        Args:
            prompt:        用户消息
            extra_system:  额外系统提示（可选）
        
        Returns:
            AgentResult: 标准化的执行结果
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """重置 Agent 状态（清空对话历史），每次 HarnessCase 独立运行前调用。"""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """返回 Agent 名称，如 "OpenClaw-QueryEngine"、"Claude Code"、"Letta" """
        ...

    def get_tools(self) -> List[str]:
        """
        返回可用工具名称列表。
        
        默认返回空列表。
        子类可覆写以返回实际工具列表。
        """
        return []

    def submit_messages(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
    ) -> AgentResult:
        """
        可选覆写：如果 Agent 支持直接传消息历史，用这个。
        
        默认实现：将 messages 合并为单条 prompt 调用 submit()。
        """
        # 简化：合并最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return self.submit(last_user, extra_system=system)


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────

def make_harness_runner(
    adapter_type: str,
    engine=None,
    **kwargs,
) -> 'HarnessRunner':
    """
    工厂函数：根据 adapter_type 创建 HarnessRunner。
    
    Args:
        adapter_type: "openclaw" | "mock" | "claude-code" | "letta" | "goose"
        engine:       传入 QueryEngine（openclaw 必需）
        **kwargs:     传给具体 Adapter 的额外参数
    
    Returns:
        HarnessRunner 实例，ready to run(suite)
    
    Raises:
        ValueError: 未知 adapter_type
        ImportError: 依赖未安装
    """
    from services.harness import HarnessRunner

    if adapter_type == "openclaw":
        if engine is None:
            raise ValueError("OpenClaw adapter 需要传入 engine=QueryEngine 实例")
        adapter = OpenClawAdapter(engine)
        return HarnessRunner(adapter)

    elif adapter_type == "mock":
        adapter = MockAgentAdapter(**kwargs)
        return HarnessRunner(adapter)

    elif adapter_type in ("claude-code", "claudecode", "claude_code"):
        adapter = ClaudeCodeAdapter(**kwargs)
        return HarnessRunner(adapter)

    elif adapter_type in ("letta", "memgpt"):
        adapter = LettaAdapter(**kwargs)
        return HarnessRunner(adapter)

    elif adapter_type in ("goose", "goose-ai"):
        adapter = GooseAdapter(**kwargs)
        return HarnessRunner(adapter)

    else:
        raise ValueError(
            f"未知 adapter_type: {adapter_type!r}。"
            f"支持的类型: openclaw, mock, claude-code, letta, goose"
        )


# ─── 内置实现 ────────────────────────────────────────────────────────────────

class OpenClawAdapter(AgentAdapter):
    """
    OpenClaw QueryEngine 适配器。
    
    将 QueryEngine 包装为 AgentAdapter，使 HarnessRunner 能直接测试它。
    
    使用方式：
        from forge.adapters import OpenClawAdapter
        from services.harness import HarnessRunner
        
        adapter = OpenClawAdapter(query_engine)
        runner  = HarnessRunner(adapter)
        report  = runner.run(suite.cases())
    """

    def __init__(self, engine):
        """
        Args:
            engine: QueryEngine 实例（来自 services/query_engine.py）
        """
        self._engine = engine

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        result = self._engine.submit(prompt, extra_system=extra_system)
        return self._to_agent_result(result)

    def reset(self) -> None:
        self._engine.reset()

    def get_name(self) -> str:
        return f"OpenClaw-{self._engine.backend.model_name}"

    def get_tools(self) -> List[str]:
        tools = getattr(self._engine, "tools", None)
        if tools is None:
            return []
        return list(getattr(tools, "_tools", {}).keys())

    def _to_agent_result(self, query_result) -> AgentResult:
        tool_calls = []
        for tc in query_result.tool_calls:
            if isinstance(tc, dict):
                tool_calls.append(ToolCall(
                    name=tc.get("name", ""),
                    input=tc.get("input", {}),
                    raw=tc,
                ))
            else:
                # ToolCall / ToolUseBlock 对象
                tool_calls.append(ToolCall(
                    name=tc.name if hasattr(tc, "name") else str(tc),
                    input=tc.input if hasattr(tc, "input") else {},
                    raw=tc,
                ))

        return AgentResult(
            final_response=query_result.final_response or "",
            tool_calls=tool_calls,
            turns=query_result.turns,
            success=query_result.success,
            error=query_result.error,
            metadata={
                "usage": {
                    "input_tokens": query_result.usage.input_tokens,
                    "output_tokens": query_result.usage.output_tokens,
                }
                if hasattr(query_result, "usage")
                else {},
            },
        )


class MockAgentAdapter(AgentAdapter):
    """
    Mock Adapter — 用于无 API 环境的测试。
    
    行为：
    - 高概率调用工具（tool_call_probability 可配置）
    - 随机参数，符合 schema
    - 可注入学预设的工具调用序列（用于精确测试）
    
    使用方式：
        # 随机行为
        adapter = MockAgentAdapter()
        
        # 预设序列（用于精确测试）
        adapter = MockAgentAdapter(
            scripted=[
                {"name": "read_file", "input": {"target": "config.json"}},
                {"name": "write_file", "input": {"target": "out.txt"}},
            ]
        )
    """

    def __init__(
        self,
        model: str = "mock-agent",
        tool_call_probability: float = 0.7,
        max_tool_calls: int = 5,
        scripted: Optional[List[Dict[str, Any]]] = None,
    ):
        self._model = model
        self._tool_prob = tool_call_probability
        self._max_calls = max_tool_calls
        self._scripted = scripted or []
        self._script_idx = 0
        self._turns = 0

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        import random

        # 预设序列优先
        if self._script_idx < len(self._scripted):
            call = self._scripted[self._script_idx]
            self._script_idx += 1
            self._turns += 1
            return AgentResult(
                final_response=f"Executed {call['name']}",
                tool_calls=[ToolCall(name=call["name"], input=call.get("input", {}), raw=call)],
                turns=self._turns,
                success=True,
            )

        # 随机决定是否调用工具
        if random.random() < self._tool_prob and self._turns < self._max_calls:
            # 随机生成工具调用
            tools = ["read_file", "write_file", "search", "git", "moon"]
            name = random.choice(tools)
            tool_calls = [ToolCall(
                name=name,
                input={"target": f"mock_{name}_value"},
                raw={"name": name},
            )]
            self._turns += 1
        else:
            tool_calls = []

        return AgentResult(
            final_response=f"Mock response to: {prompt[:50]}...",
            tool_calls=tool_calls,
            turns=self._turns,
            success=True,
        )

    def reset(self) -> None:
        self._turns = 0
        self._script_idx = 0

    def get_name(self) -> str:
        return self._model

    def get_tools(self) -> List[str]:
        if self._scripted:
            return list({c["name"] for c in self._scripted})
        return ["read_file", "write_file", "search", "git", "moon"]


# ─── Claude Code 适配器（占位，待实际环境验证）───────────────────────────────

class ClaudeCodeAdapter(AgentAdapter):
    """
    Claude Code (claude-code CLI) 适配器。
    
    接口方式：
    - 方式A（推荐）：subprocess 启动 claude-code --print，输入 prompt
    - 方式B：使用 claude-code 的 --output-format json 模式
    
    当前实现：subprocess 模式（基于公开 CLI 接口）。
    需验证：claude-code --print 是否在所有版本均支持。
    
    状态：⚠️ 待验证（需要实际安装 claude-code 环境）
    """

    def __init__(
        self,
        executable: str = "claude-code",
        cwd: Optional[str] = None,
        timeout: int = 60,
        **kwargs,
    ):
        import shutil
        self._executable = shutil.which(executable) or executable
        self._cwd = cwd or "."
        self._timeout = timeout

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        import subprocess
        import json

        # 构造命令：claude-code --print <prompt>
        cmd = [self._executable, "--print"]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
            )
            output = proc.stdout.strip()
            # 尝试解析 JSON（如果 Claude Code 输出 JSON）
            try:
                data = json.loads(output)
                # 提取 tool_calls（格式待验证）
                tool_calls = []
                if isinstance(data, dict) and "tool_calls" in data:
                    for tc in data["tool_calls"]:
                        tool_calls.append(ToolCall(
                            name=tc.get("name", ""),
                            input=tc.get("input", {}),
                            raw=tc,
                        ))
                return AgentResult(
                    final_response=data.get("text", output),
                    tool_calls=tool_calls,
                    turns=1,
                    success=True,
                )
            except (json.JSONDecodeError, AttributeError):
                # 纯文本输出
                return AgentResult(
                    final_response=output,
                    tool_calls=[],
                    turns=1,
                    success=True,
                )
        except subprocess.TimeoutExpired:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=1,
                success=False,
                error=f"Timeout after {self._timeout}s",
            )
        except FileNotFoundError:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"claude-code not found: {self._executable}",
            )
        except Exception as e:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        # Claude Code 无需显式 reset（每次调用是独立进程）
        pass

    def get_name(self) -> str:
        return "Claude Code"

    def get_tools(self) -> List[str]:
        # Claude Code 工具集（待确认）
        return ["Bash", "Read", "Write", "Edit", "Notebook", "WebSearch", "WebFetch"]


# ─── Letta/MemGPT 适配器（占位，待探索）──────────────────────────────────────

class LettaAdapter(AgentAdapter):
    """
    Letta (原 MemGPT) 适配器。
    
    接口方式：
    - Letta REST API (默认 http://localhost:8283)
    - 或 Python SDK: from letta import LLM, Tool
    
    当前实现：REST API 模式。
    需验证：Letta 的 /api/agents/{id}/messages 接口参数格式。
    
    状态：⚠️ 待探索（需要实际运行 Letta 服务）
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8283",
        agent_id: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id
        self._api_key = api_key or ""
        self._session = None  # 后续可用于保持对话

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        import requests

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "role": "user",
            "content": prompt,
        }
        if extra_system:
            payload["systemPrompt"] = extra_system

        try:
            # 创建新消息
            resp = requests.post(
                f"{self._base_url}/api/agents/{self._agent_id}/messages",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            tool_calls = []
            if isinstance(data, dict):
                for tc in data.get("tool_calls", []):
                    tool_calls.append(ToolCall(
                        name=tc.get("name", ""),
                        input=tc.get("input", {}),
                        raw=tc,
                    ))

            return AgentResult(
                final_response=data.get("text", ""),
                tool_calls=tool_calls,
                turns=data.get("turns", 1),
                success=True,
            )

        except requests.ConnectionError:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Letta 服务未启动: {self._base_url}",
            )
        except Exception as e:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        """重置 Letta 对话（杀死旧 agent，创建新的）"""
        # 如有需要：POST /api/agents/{id}/reset
        self._session = None

    def get_name(self) -> str:
        return f"Letta-{self._agent_id or 'local'}"

    def get_tools(self) -> List[str]:
        # Letta 暴露的核心工具
        return ["send_message", "pause", "core_memory", "archival_memory"]


# ─── Goose 适配器（占位，待探索）────────────────────────────────────────────

class GooseAdapter(AgentAdapter):
    """
    Goose AI (goose-ai) 适配器。
    
    接口方式：
    - goose CLI: goose --message "<prompt>"
    - 或 MCP 协议（如果 goose 实现了标准 MCP server）
    
    当前实现：subprocess CLI 模式。
    需验证：goose CLI 的接口格式。
    
    状态：⚠️ 待探索
    """

    def __init__(
        self,
        executable: str = "goose",
        cwd: Optional[str] = None,
        timeout: int = 60,
        **kwargs,
    ):
        import shutil
        self._executable = shutil.which(executable) or executable
        self._cwd = cwd or "."
        self._timeout = timeout

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AgentResult:
        import subprocess
        import json

        cmd = [self._executable, "--message", prompt]
        if extra_system:
            cmd += ["--system", extra_system]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
            )
            output = proc.stdout.strip()

            # 尝试 JSON 输出
            try:
                data = json.loads(output)
                tool_calls = []
                for tc in data.get("tool_calls", []):
                    tool_calls.append(ToolCall(
                        name=tc.get("name", ""),
                        input=tc.get("input", {}),
                        raw=tc,
                    ))
                return AgentResult(
                    final_response=data.get("text", output),
                    tool_calls=tool_calls,
                    turns=1,
                    success=True,
                )
            except json.JSONDecodeError:
                return AgentResult(
                    final_response=output,
                    tool_calls=[],
                    turns=1,
                    success=True,
                )

        except subprocess.TimeoutExpired:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Goose timeout after {self._timeout}s",
            )
        except FileNotFoundError:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Goose not found: {self._executable}",
            )
        except Exception as e:
            return AgentResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        # Goose CLI 每次独立调用
        pass

    def get_name(self) -> str:
        return "Goose"

    def get_tools(self) -> List[str]:
        # Goose 工具集（待确认）
        return ["bash", "read", "write", "edit", "grep"]


__all__ = [
    "AgentAdapter",
    "ToolCall",
    "AgentResult",
    "OpenClawAdapter",
    "MockAgentAdapter",
    "ClaudeCodeAdapter",
    "LettaAdapter",
    "GooseAdapter",
    "make_harness_runner",
]
