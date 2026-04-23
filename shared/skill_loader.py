"""动态 Skills 加载系统

来自 Claude Code 灵感：
- 从目录动态加载 Skill
- 支持 Markdown frontmatter 解析
- 热加载（文件变更自动重载）
- 多来源：bundled / user / project / plugin

Skill 格式（Markdown）：
    ---
    name: my_skill
    description: 技能描述
    when_to_use: 何时使用
    ---
    # 技能内容
    ...
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SkillSource(Enum):
    """Skill 来源（Claude Code 风格）"""
    BUNDLED = "bundled"       # 内置
    USER = "user"             # 用户目录
    PROJECT = "project"       # 项目目录
    PLUGIN = "plugin"         # 插件


@dataclass
class SkillFrontmatter:
    """Skill 元数据（frontmatter）"""
    name: str
    description: str = ""
    when_to_use: str = ""
    version: str = "1.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Skill:
    """
    Skill 定义
    
    来自 Claude Code 灵感：
    - 支持 Markdown 格式
    - frontmatter 元数据
    - 动态加载
    """
    id: str
    name: str
    description: str
    content: str
    source: SkillSource
    file_path: str = ""
    when_to_use: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    loaded_at: datetime = None
    
    def __post_init__(self):
        if self.loaded_at is None:
            self.loaded_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'source': self.source.value,
            'file_path': self.file_path,
            'when_to_use': self.when_to_use,
            'tags': self.tags,
            'enabled': self.enabled,
            'loaded_at': self.loaded_at.isoformat() if self.loaded_at else None,
        }


class SkillLoader:
    """
    动态 Skill 加载器
    
    来自 Claude Code loadSkillsDir.ts 灵感：
    - 扫描目录加载 Skill
    - 解析 Markdown frontmatter
    - 支持多来源
    - 缓存 + 热加载
    """
    
    def __init__(
        self,
        skills_dirs: List[str] = None,
        auto_reload: bool = False,
    ):
        """
        初始化 Skill 加载器
        
        Args:
            skills_dirs: Skill 目录列表
            auto_reload: 是否自动重载
        """
        self.skills_dirs = skills_dirs or []
        self.auto_reload = auto_reload
        
        # Skill 缓存
        self._skills: Dict[str, Skill] = {}
        self._loaded_at: Dict[str, datetime] = {}
        
        # 内置 Skills
        self._bundled_skills: Dict[str, Skill] = {}
        self._register_bundled_skills()
    
    def _register_bundled_skills(self):
        """注册内置 Skills（Claude Code 风格）"""
        bundled = [
            Skill(
                id="batch",
                name="batch",
                description="批量执行多个操作",
                content="批量执行工具，支持并行和串行模式",
                source=SkillSource.BUNDLED,
                when_to_use="需要批量处理多个任务时",
                tags=["batch", "parallel"],
            ),
            Skill(
                id="loop",
                name="loop",
                description="循环执行直到满足条件",
                content="循环执行工具，支持条件终止",
                source=SkillSource.BUNDLED,
                when_to_use="需要重复执行直到满足条件时",
                tags=["loop", "iteration"],
            ),
            Skill(
                id="remember",
                name="remember",
                description="记住重要信息",
                content="记忆工具，将信息存入 Memory",
                source=SkillSource.BUNDLED,
                when_to_use="需要记住重要信息时",
                tags=["memory", "remember"],
            ),
        ]
        
        for skill in bundled:
            self._bundled_skills[skill.id] = skill
    
    def load_from_dir(
        self,
        directory: str,
        source: SkillSource = SkillSource.PROJECT,
    ) -> List[Skill]:
        """
        从目录加载 Skills
        
        Args:
            directory: 目录路径
            source: 来源类型
        
        Returns:
            List[Skill]: 加载的 Skills
        """
        if not os.path.isdir(directory):
            return []
        
        loaded = []
        
        for filename in os.listdir(directory):
            if not filename.endswith('.md'):
                continue
            
            filepath = os.path.join(directory, filename)
            skill = self._load_skill_file(filepath, source)
            
            if skill:
                self._skills[skill.id] = skill
                self._loaded_at[skill.id] = datetime.now()
                loaded.append(skill)
        
        return loaded
    
    def _load_skill_file(
        self,
        filepath: str,
        source: SkillSource,
    ) -> Optional[Skill]:
        """
        加载单个 Skill 文件
        
        Args:
            filepath: 文件路径
            source: 来源类型
        
        Returns:
            Optional[Skill]: 加载的 Skill
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 frontmatter
            frontmatter, body = self._parse_frontmatter(content)
            
            # 生成 ID
            skill_id = frontmatter.get('name') or os.path.splitext(os.path.basename(filepath))[0]
            
            return Skill(
                id=skill_id,
                name=frontmatter.get('name', skill_id),
                description=frontmatter.get('description', ''),
                content=body,
                source=source,
                file_path=filepath,
                when_to_use=frontmatter.get('when_to_use', ''),
                tags=frontmatter.get('tags', []),
                enabled=frontmatter.get('enabled', True),
            )
        
        except Exception:
            return None
    
    def _parse_frontmatter(self, content: str) -> tuple:
        """
        解析 Markdown frontmatter
        
        Returns:
            Tuple[Dict, str]: (frontmatter dict, body)
        """
        frontmatter = {}
        body = content
        
        # 匹配 --- ... --- 格式
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if match:
            fm_text = match.group(1)
            body = match.group(2)
            
            # 简单 YAML 解析
            for line in fm_text.split('\n'):
                line = line.strip()
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip()
                    
                    # 处理列表
                    if value.startswith('[') and value.endswith(']'):
                        value = [v.strip().strip('"\'') for v in value[1:-1].split(',') if v.strip()]
                    # 处理布尔值
                    elif value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    
                    frontmatter[key] = value
        
        return frontmatter, body
    
    def load_from_string(
        self,
        content: str,
        skill_id: str,
        source: SkillSource = SkillSource.USER,
    ) -> Skill:
        """
        从字符串加载 Skill
        
        Args:
            content: Skill 内容
            skill_id: Skill ID
            source: 来源类型
        
        Returns:
            Skill: 加载的 Skill
        """
        frontmatter, body = self._parse_frontmatter(content)
        
        skill = Skill(
            id=frontmatter.get('name', skill_id),
            name=frontmatter.get('name', skill_id),
            description=frontmatter.get('description', ''),
            content=body,
            source=source,
            when_to_use=frontmatter.get('when_to_use', ''),
            tags=frontmatter.get('tags', []),
            enabled=frontmatter.get('enabled', True),
        )
        
        self._skills[skill.id] = skill
        return skill
    
    def get(self, skill_id: str) -> Optional[Skill]:
        """获取 Skill"""
        # 先查用户/项目 Skills
        if skill_id in self._skills:
            return self._skills[skill_id]
        # 再查内置 Skills
        return self._bundled_skills.get(skill_id)
    
    def list_all(self) -> List[Skill]:
        """列出所有 Skills"""
        all_skills = list(self._bundled_skills.values()) + list(self._skills.values())
        return [s for s in all_skills if s.enabled]
    
    def list_by_source(self, source: SkillSource) -> List[Skill]:
        """按来源列出 Skills"""
        if source == SkillSource.BUNDLED:
            return list(self._bundled_skills.values())
        return [s for s in self._skills.values() if s.source == source]
    
    def search(self, query: str) -> List[Skill]:
        """搜索 Skills"""
        query_lower = query.lower()
        results = []
        
        for skill in self.list_all():
            if (query_lower in skill.name.lower() or
                query_lower in skill.description.lower() or
                query_lower in skill.when_to_use.lower() or
                any(query_lower in tag.lower() for tag in skill.tags)):
                results.append(skill)
        
        return results
    
    def reload(self, skill_id: str) -> bool:
        """
        重载单个 Skill（热加载）
        
        Args:
            skill_id: Skill ID
        
        Returns:
            bool: 是否成功
        """
        skill = self._skills.get(skill_id)
        if not skill or not skill.file_path:
            return False
        
        new_skill = self._load_skill_file(skill.file_path, skill.source)
        if new_skill:
            self._skills[skill_id] = new_skill
            self._loaded_at[skill_id] = datetime.now()
            return True
        
        return False
    
    def reload_all(self) -> int:
        """重载所有 Skills"""
        count = 0
        for skill_id in list(self._skills.keys()):
            if self.reload(skill_id):
                count += 1
        return count
    
    def register(self, skill: Skill):
        """手动注册 Skill"""
        self._skills[skill.id] = skill
    
    def unregister(self, skill_id: str) -> bool:
        """注销 Skill"""
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        all_skills = self.list_all()
        by_source = {}
        for source in SkillSource:
            by_source[source.value] = len(self.list_by_source(source))
        
        return {
            'total': len(all_skills),
            'bundled': len(self._bundled_skills),
            'user_loaded': len(self._skills),
            'by_source': by_source,
        }
