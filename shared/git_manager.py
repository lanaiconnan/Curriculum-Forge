"""Git 版本控制管理器

借鉴 autoresearch 的 Git 设计理念：
- 每个实验一个分支
- 好的结果 commit
- 坏的结果 reset
- 完整的历史记录
"""

import subprocess
import os
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime


@dataclass
class GitCommit:
    """Git 提交记录"""
    hash: str
    message: str
    author: str
    date: str
    files_changed: List[str]


@dataclass
class GitBranch:
    """Git 分支信息"""
    name: str
    is_current: bool
    last_commit: str


class GitManager:
    """Git 版本控制管理器"""
    
    def __init__(self, repo_path: str, enabled: bool = True):
        """
        初始化 Git 管理器
        
        Args:
            repo_path: 仓库路径
            enabled: 是否启用 Git 版本控制
        """
        self.repo_path = repo_path
        self.enabled = enabled and self._is_git_repo()
        self._current_branch = None
    
    def _is_git_repo(self) -> bool:
        """检查是否是 Git 仓库"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def _run_git(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """运行 Git 命令"""
        try:
            return subprocess.run(
                ['git'] + list(args),
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                **kwargs
            )
        except subprocess.TimeoutExpired:
            print(f"   ⚠️ Git command timeout: git {' '.join(args)}")
            raise
        except FileNotFoundError:
            print(f"   ⚠️ Git not found in PATH")
            self.enabled = False
            raise
    
    def init(self) -> bool:
        """初始化 Git 仓库"""
        if not self.enabled:
            return False
        
        try:
            result = self._run_git('status')
            print(f"   ✓ Git repository found")
            return True
        except:
            print(f"   ⚠️ Not a Git repository, initializing...")
            try:
                self._run_git('init')
                self._run_git('config', 'user.name', 'Curriculum-Forge')
                self._run_git('config', 'user.email', 'agent@curriculum-forge.local')
                print(f"   ✓ Git repository initialized")
                self.enabled = True
                return True
            except:
                print(f"   ⚠️ Failed to initialize Git repository")
                self.enabled = False
                return False
    
    def get_current_branch(self) -> Optional[str]:
        """获取当前分支"""
        if not self.enabled:
            return None
        
        try:
            result = self._run_git('branch', '--show-current')
            self._current_branch = result.stdout.strip()
            return self._current_branch
        except:
            return None
    
    def create_experiment_branch(self, run_tag: Optional[str] = None) -> Optional[str]:
        """
        创建实验分支
        
        Args:
            run_tag: 实验标签（如 "mar29"）
        
        Returns:
            str: 新分支名，或 None
        """
        if not self.enabled:
            return None
        
        if run_tag is None:
            run_tag = datetime.now().strftime("%b%d")
        
        branch_name = f"autoresearch/{run_tag}"
        
        try:
            # 检查分支是否已存在
            result = self._run_git('branch', '--list', branch_name)
            if result.stdout.strip():
                # 切换到已存在的分支
                self._run_git('checkout', branch_name)
            else:
                # 创建新分支
                self._run_git('checkout', '-b', branch_name)
            
            self._current_branch = branch_name
            print(f"   ✓ Branch: {branch_name}")
            return branch_name
        except Exception as e:
            print(f"   ⚠️ Failed to create branch: {e}")
            return None
    
    def commit_improvement(
        self,
        message: str,
        files: Optional[List[str]] = None,
        keep_rate: Optional[float] = None,
        avg_reward: Optional[float] = None,
    ) -> Optional[str]:
        """
        提交好的实验结果
        
        Args:
            message: 提交信息
            files: 要提交的文件列表
            keep_rate: 保留率
            avg_reward: 平均奖励
        
        Returns:
            str: 提交哈希，或 None
        """
        if not self.enabled:
            return None
        
        # 构建提交信息
        commit_msg = f"✅ {message}"
        if keep_rate is not None:
            commit_msg += f" | keep_rate: {keep_rate:.1%}"
        if avg_reward is not None:
            commit_msg += f" | avg_reward: {avg_reward:.2f}"
        
        try:
            # 添加文件
            if files:
                for f in files:
                    self._run_git('add', f)
            else:
                self._run_git('add', '-A')
            
            # 提交
            result = self._run_git('commit', '-m', commit_msg)
            
            if result.returncode == 0:
                # 获取提交哈希
                hash_result = self._run_git('rev-parse', '--short', 'HEAD')
                commit_hash = hash_result.stdout.strip()
                print(f"   ✓ Committed: {commit_hash[:8]} - {message[:50]}")
                return commit_hash
            else:
                print(f"   ⚠️ Commit failed: {result.stderr}")
                return None
        except Exception as e:
            print(f"   ⚠️ Failed to commit: {e}")
            return None
    
    def discard_result(self) -> bool:
        """
        丢弃坏的实验结果（git reset --hard HEAD~1）
        
        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False
        
        try:
            self._run_git('reset', '--hard', 'HEAD~1')
            print(f"   ✓ Discarded last result")
            return True
        except Exception as e:
            print(f"   ⚠️ Failed to discard: {e}")
            return False
    
    def get_experiment_history(self, limit: int = 10) -> List[GitCommit]:
        """
        获取实验历史
        
        Args:
            limit: 返回的提交数量
        
        Returns:
            List[GitCommit]: 提交记录列表
        """
        if not self.enabled:
            return []
        
        try:
            # 获取提交历史
            result = self._run_git(
                'log',
                '--oneline',
                '--format=%H|%s|%an|%ad',
                f'-{limit}',
                '--date=iso'
            )
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) >= 4:
                    commits.append(GitCommit(
                        hash=parts[0][:8],
                        message=parts[1],
                        author=parts[2],
                        date=parts[3],
                        files_changed=[]
                    ))
            
            return commits
        except:
            return []
    
    def checkout_branch(self, branch_name: str) -> bool:
        """
        切换分支
        
        Args:
            branch_name: 分支名
        
        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False
        
        try:
            self._run_git('checkout', branch_name)
            self._current_branch = branch_name
            print(f"   ✓ Switched to branch: {branch_name}")
            return True
        except Exception as e:
            print(f"   ⚠️ Failed to switch branch: {e}")
            return False
    
    def get_status(self) -> Dict[str, any]:
        """
        获取 Git 状态
        
        Returns:
            Dict: 状态信息
        """
        if not self.enabled:
            return {'enabled': False}
        
        try:
            # 获取当前分支
            branch = self.get_current_branch()
            
            # 获取状态
            status_result = self._run_git('status', '--porcelain')
            has_changes = bool(status_result.stdout.strip())
            
            # 获取未提交的更改数
            diff_result = self._run_git('diff', '--stat')
            changes = diff_result.stdout.strip()
            
            return {
                'enabled': True,
                'branch': branch,
                'has_changes': has_changes,
                'changes': changes,
                'is_clean': not has_changes,
            }
        except:
            return {'enabled': False}
    
    def print_status(self):
        """打印 Git 状态"""
        if not self.enabled:
            print(f"   ⚠️ Git version control disabled")
            return
        
        status = self.get_status()
        
        print(f"   📍 Branch: {status.get('branch', 'unknown')}")
        
        if status.get('is_clean'):
            print(f"   ✓ Working tree clean")
        else:
            print(f"   ⚠️ Working tree has changes")
        
        # 显示最近的提交
        history = self.get_experiment_history(limit=3)
        if history:
            print(f"   📜 Recent commits:")
            for commit in history[:3]:
                print(f"      • {commit.hash[:8]}: {commit.message[:60]}")


# 全局 Git 管理器实例
_git_manager = None


def get_git_manager(repo_path: str = '.', enabled: bool = True) -> GitManager:
    """获取全局 Git 管理器"""
    global _git_manager
    if _git_manager is None:
        _git_manager = GitManager(repo_path, enabled)
        _git_manager.init()
    return _git_manager


def reset_git_manager():
    """重置全局 Git 管理器"""
    global _git_manager
    _git_manager = None
