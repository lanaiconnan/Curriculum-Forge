"""Forge Adapter — Claude Code

通过 Claude Code CLI 进行 Harness 测试。

Claude Code 使用 MCP（Model Context Protocol）通信：
- 启动方式：claude-code --print [--no-input-prompts]
- 工具调用格式：JSON stream via stdin/stdout
- 工具名称：Read, Write, Edit, Bash, Grep, Glob, ... (PascalCase)

配置：
    config = {
        "cli_path": "claude-code",  # 或绝对路径
        "model": "claude-sonnet-4-20250514",
        "max_turns": 5,
        "mcp_port": 3100,  # MCP server port (可选)
        "timeout": 120,
    }

Usage:
    from forge.adapters import ClaudeCodeAdapter
    adapter = ClaudeCodeAdapter(config={"cli_path": "/usr/local/bin/claude-code"})
    result = adapter.submit("Read config.json")
"""

import os
import json
import re
import subprocess
import tempfile
import time
import logging
from typing import Any, Dict, List, Optional

from .base import (
    AgentAdapter,
    CLIAdapter,
    AdapterResult,
    ToolCall,
    ToolNameNormalizer,
)

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(CLIAdapter):
    """
    Claude Code CLI Adapter。

    Claude Code 工具名称（需要归一化）：
      Read       → read_file
      Write      → write_file
      Edit       → edit_file
      Bash       → shell
      Grep       → search
      Glob       → glob
      WebSearch  → web_search
      WebFetch   → web_fetch

    交互模式：
      claude-code --print --no-input-prompts
      # 然后从 stdin 输入提示，从 stdout 读取 JSON 响应
    """

    name = "claude-code"
    description = "Claude Code CLI (MCP protocol)"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
    ):
        super().__init__(config, normalizer)

        self.cli_path = self.config.get(
            "cli_path",
            os.environ.get("CLAUDE_CODE_PATH", "claude-code")
        )
        self.model = self.config.get("model", "claude-sonnet-4-20250514")
        self.max_turns = self.config.get("max_turns", 5)
        self.timeout = self.config.get("timeout", 120)
        self.verbose = self.config.get("verbose", False)

        # Claude Code 工具名归一化规则
        claude_code_rules = {
            "read_file":    ["Read", "ReadFile"],
            "write_file":   ["Write", "WriteFile"],
            "edit_file":    ["Edit", "EditFile"],
            "shell":        ["Bash", "bash"],
            "search":       ["Grep", "grep", "Search"],
            "glob":         ["Glob", "glob"],
            "web_search":   ["WebSearch", "WebSearchTool"],
            "web_fetch":    ["WebFetch", "WebFetchTool"],
            "notebook_edit":["NotebookEdit", "NotebookCell"],
        }
        if normalizer is None:
            self.normalizer = ToolNameNormalizer(custom_rules=claude_code_rules)

        self._connected = False

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AdapterResult:
        """
        通过 Claude Code CLI 执行命令。

        Claude Code 输出格式（非流式 --print）：
        - JSON: {"type": "tool_use", "name": "Read", "input": {...}}
        - JSON: {"type": "text", "text": "..."}
        - JSON: {"type": "result", "content": "..."}
        """
        # 构建完整的提示（加上 system 如果有）
        full_prompt = prompt
        if extra_system:
            full_prompt = f"{extra_system}\n\n{prompt}"

        # 使用 --print --verbose 获取结构化 JSON 输出
        cmd = [
            self.cli_path,
            "--print",
            "--no-input-prompts",
            f"--max-turns={self.max_turns}",
        ]
        if self.verbose:
            cmd.append("--verbose")

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = proc.communicate(
                input=full_prompt.encode(),
                timeout=self.timeout,
            )

            output = stdout.decode(errors="replace")

            if proc.returncode != 0 and not output.strip():
                # 有错误但仍有输出
                err_msg = stderr.decode(errors="replace")[:200]
                return AdapterResult(
                    final_response="",
                    tool_calls=[],
                    turns=0,
                    success=False,
                    error=f"Claude Code exit {proc.returncode}: {err_msg}",
                )

            # 解析 JSON 输出
            tool_calls, final_response = self._parse_output(output)
            self._connected = True

            return AdapterResult(
                final_response=final_response,
                tool_calls=tool_calls,
                turns=len(tool_calls),
                success=True,
                raw_response=output,
            )

        except subprocess.TimeoutExpired:
            proc.kill()
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Claude Code timed out after {self.timeout}s",
            )
        except FileNotFoundError:
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Claude Code not found at: {self.cli_path}",
            )
        except Exception as e:
            logger.error(f"Claude Code error: {e}")
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        """Claude Code 无会话状态，无需 reset"""
        pass

    def health_check(self) -> bool:
        """检查 Claude Code CLI 是否可用"""
        try:
            result = subprocess.run(
                [self.cli_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ── 辅助 ─────────────────────────────────────────────────────────

    def _parse_output(self, output: str) -> tuple:
        """
        解析 Claude Code 输出。

        Claude Code JSON 格式（每行一个 JSON 对象）：
          {"type": "tool_use", "name": "Read", "input": {"file_path": "..."}}
          {"type": "text", "text": "..."}
          {"type": "result", "content": "Done."}

        Returns:
            (List[ToolCall], final_response)
        """
        tool_calls: List[ToolCall] = []
        final_response = ""

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # 非 JSON 行 → 可能是纯文本
                final_response += line + "\n"
                continue

            t = obj.get("type", "")

            if t == "tool_use":
                raw_name = obj.get("name", "")
                tool_calls.append(ToolCall(
                    name=self.normalizer.normalize(raw_name),
                    input=obj.get("input", {}),
                    raw_name=raw_name,
                    call_id=obj.get("id", f"cc_{len(tool_calls)}"),
                ))

            elif t in ("text", "text delta"):
                final_response += obj.get("text", "")

            elif t == "result":
                final_response = obj.get("content", obj.get("text", ""))

        return tool_calls, final_response.strip()
