"""Git 工具"""

from .base import Tool, ToolResult
import subprocess
import os


class GitTool(Tool):
    """Git 版本控制工具"""
    
    name = "git"
    description = """Git version control for experiment isolation.
Commands:
- checkout -b <branch>: Create new branch for experiment
- commit -m <msg>: Save experiment result
- reset --hard HEAD: Revert changes
"""
    
    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
    
    def execute(self, params: dict) -> ToolResult:
        cmd = params.get("command")
        try:
            if cmd == "checkout-b":
                branch = params.get("branch", "")
                r = subprocess.run(["git", "checkout", "-b", branch], cwd=self.cwd, capture_output=True, text=True)
                if r.returncode == 0:
                    return ToolResult(True, f"Created branch: {branch}", metadata={"branch": branch})
                return ToolResult(False, "", r.stderr)
            
            elif cmd == "commit":
                msg = params.get("message", "auto commit")
                subprocess.run(["git", "add", "-A"], cwd=self.cwd, capture_output=True)
                r = subprocess.run(["git", "commit", "-m", msg], cwd=self.cwd, capture_output=True, text=True)
                if r.returncode == 0:
                    h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.cwd, capture_output=True, text=True)
                    return ToolResult(True, f"Committed: {h.stdout.strip()}", metadata={"hash": h.stdout.strip()})
                return ToolResult(False, "", r.stderr)
            
            elif cmd == "reset-hard":
                r = subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=self.cwd, capture_output=True, text=True)
                return ToolResult(r.returncode == 0, "Reset to HEAD" if r.returncode == 0 else "", r.stderr)
            
            elif cmd == "status":
                r = subprocess.run(["git", "status", "--short"], cwd=self.cwd, capture_output=True, text=True)
                return ToolResult(True, r.stdout or "Clean")
            
            else:
                return ToolResult(False, "", f"Unknown command: {cmd}")
        except Exception as e:
            return ToolResult(False, "", str(e))
