"""Moon 工具"""

from .base import Tool, ToolResult
import subprocess
import re
import os


class MoonTool(Tool):
    """MoonBit 工具链"""
    
    name = "moon"
    description = """MoonBit toolchain for build, test, and benchmark.
Commands:
- build: Compile to WASM
- test: Run tests
- bench: Run benchmarks
- check: Type checking
"""
    
    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
    
    def execute(self, params: dict) -> ToolResult:
        cmd = params.get("command")
        try:
            full_cmd = ["moon", cmd]
            if cmd == "test" and params.get("filter"):
                full_cmd.extend(["--filter", params["filter"]])
            
            r = subprocess.run(full_cmd, cwd=self.cwd, capture_output=True, text=True, timeout=300)
            output = r.stdout + r.stderr
            
            if cmd == "bench":
                return self._parse_bench(output, r.returncode == 0)
            elif cmd == "test":
                passed = len(re.findall(r"PASS|passed|OK", output, re.I))
                failed = len(re.findall(r"FAIL|failed|ERROR", output, re.I))
                return ToolResult(r.returncode == 0, f"Passed: {passed}, Failed: {failed}", 
                                metadata={"passed": passed, "failed": failed})
            else:
                return ToolResult(r.returncode == 0, output[:500])
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Timeout after 300s")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def _parse_bench(self, output: str, success: bool) -> ToolResult:
        if not success:
            return ToolResult(False, output, "Benchmark failed")
        metrics = {}
        for pattern, key in [("WASM.*?(\d+(?:\.\d+)?)\s*KB", "wasm_kb"),
                              ("Startup.*?(\d+(?:\.\d+)?)\s*ms", "startup_ms"),
                              ("score.*?(\d+(?:\.\d+)?)", "score")]:
            m = re.search(pattern, output, re.I)
            if m:
                metrics[key] = float(m.group(1))
        return ToolResult(True, f"Benchmark: {metrics}", metadata=metrics)
