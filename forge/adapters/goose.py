"""Forge Adapter — Goose

通过 Goose CLI 进行 Harness 测试。

Goose 交互方式：
- 启动：goose --print "prompt"
- 工具调用：MCP stream 格式
- 工具名称：ReadFile, WriteFile, Bash, Search, ... (CamelCase)

配置：
    config = {
        "cli_path": "goose",  # 或绝对路径
        "session_name": "forge-harness",
        "mcp_config": "~/.config/goose/mcp.json",
        "timeout": 120,
    }

Usage:
    from forge.adapters import GooseAdapter
    adapter = GooseAdapter(config={"cli_path": "/usr/local/bin/goose"})
    result = adapter.submit("Create a new file called hello.txt")
"""

import os
import json
import subprocess
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


class GooseAdapter(CLIAdapter):
    """
    Goose CLI Adapter。

    Goose 工具名称（需要归一化）：
      ReadFile    → read_file
      WriteFile   → write_file
      Bash        → shell
      Search      → search
      Grep        → search
      LintFix     → code_fix
      ...

    Goose 使用类似 Claude Code 的 MCP 格式，
    但输出格式略有不同。
    """

    name = "goose"
    description = "Goose CLI (MCP protocol)"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
    ):
        super().__init__(config, normalizer)

        self.cli_path = self.config.get(
            "cli_path",
            os.environ.get("GOOSE_CLI_PATH", "goose")
        )
        self.session_name = self.config.get("session_name", "forge-harness")
        self.mcp_config = self.config.get(
            "mcp_config",
            os.environ.get("GOOSE_MCP_CONFIG", "")
        )
        self.timeout = self.config.get("timeout", 120)

        # Goose 工具名归一化规则
        goose_rules = {
            "read_file":  ["ReadFile", "Read", "FileRead"],
            "write_file": ["WriteFile", "Write", "FileWrite"],
            "edit_file":  ["EditFile", "Edit", "FileEdit"],
            "shell":      ["Bash", "bash", "Shell", "RunCommand"],
            "search":     ["Grep", "grep", "Search", "search"],
            "glob":       ["Glob", "glob", "FindFiles"],
            "code_fix":   ["LintFix", "lintfix", "AutoFix"],
        }
        if normalizer is None:
            self.normalizer = ToolNameNormalizer(custom_rules=goose_rules)

        self._connected = False

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AdapterResult:
        """
        通过 Goose CLI 执行命令。

        Goose 输出格式（--print 模式）：
        - JSON 行流: {"type": "tool_call", "tool": "ReadFile", ...}
        - 或纯文本:  "I need to read the file first..."

        注意：Goose 可能有多种输出格式，尝试多种解析策略。
        """
        full_prompt = prompt
        if extra_system:
            full_prompt = f"{extra_system}\n\n{prompt}"

        # Goose 的 --print 模式
        cmd = [
            self.cli_path,
            "--print",
            "--session", self.session_name,
        ]

        env = os.environ.copy()
        if self.mcp_config:
            env["GOOSE_MCP_CONFIG"] = self.mcp_config

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = proc.communicate(
                input=full_prompt.encode(),
                timeout=self.timeout,
            )

            output = stdout.decode(errors="replace")
            err_output = stderr.decode(errors="replace")

            self._connected = True

            # 解析输出
            tool_calls, final_response = self._parse_output(output)

            if not tool_calls and not final_response.strip():
                return AdapterResult(
                    final_response="",
                    tool_calls=[],
                    turns=0,
                    success=False,
                    error=f"Empty output. stderr: {err_output[:200]}",
                )

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
                error=f"Goose timed out after {self.timeout}s",
            )
        except FileNotFoundError:
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"Goose not found at: {self.cli_path}",
            )
        except Exception as e:
            logger.error(f"Goose error: {e}")
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        """Goose 有会话概念，可重置"""
        try:
            subprocess.run(
                [self.cli_path, "session", "reset", "--name", self.session_name],
                capture_output=True,
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"Goose session reset failed: {e}")

    def health_check(self) -> bool:
        """检查 Goose CLI 是否可用"""
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
        解析 Goose 输出。

        策略1：JSON 行格式（类似 Claude Code）
        策略2：Markdown 格式（Goose 常用）
        策略3：纯文本
        """
        tool_calls: List[ToolCall] = []
        final_response = ""

        # 策略1：JSON 行（与 Claude Code 相似）
        json_lines, text_lines = [], []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                json_lines.append(obj)
            except json.JSONDecodeError:
                text_lines.append(line)

        # 解析 JSON 行
        for obj in json_lines:
            t = obj.get("type", "")

            # Goose 可能使用不同的 type 字段
            if t in ("tool_use", "tool_call", "tool"):
                tool_name = obj.get("tool", obj.get("name", ""))
                tool_calls.append(ToolCall(
                    name=self.normalizer.normalize(tool_name),
                    input=obj.get("input", obj.get("args", {})),
                    raw_name=tool_name,
                    call_id=obj.get("id", f"goose_{len(tool_calls)}"),
                ))

            elif t in ("text", "content", "message"):
                final_response += str(obj.get("content", obj.get("text", "")))

            elif t == "result":
                final_response = str(obj.get("content", obj.get("text", "")))

        # 策略2：从 Markdown 提取工具调用
        if not tool_calls:
            import re
            # ```goose
            # ReadFile("...")
            # ```
            code_blocks = re.findall(
                r'```(?:goose|\w+)?\n(.*?)```',
                output,
                re.DOTALL
            )
            for block in code_blocks:
                # 匹配 ToolName("args") 格式
                tool_matches = re.findall(
                    r'(\w+)\(["\'](.*?)["\']',
                    block,
                )
                for name, arg in tool_matches:
                    norm = self.normalizer.normalize(name)
                    tool_calls.append(ToolCall(
                        name=norm,
                        input={"arg": arg},
                        raw_name=name,
                    ))

        # 策略3：如果还没有，从纯文本推断
        if not tool_calls and text_lines:
            final_response = "\n".join(text_lines)

        return tool_calls, final_response.strip()
