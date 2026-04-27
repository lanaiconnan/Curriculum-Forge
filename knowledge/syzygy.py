"""
Syzygy Vault Python 绑定

集成 Syzygy 知识库，提供：
- 经验页创建（Markdown 格式）
- 标签检索
- 双向链接 [[wikilink]]
- 知识图谱可视化

参考：https://github.com/nashsu/syzygy
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class ExperiencePage:
    """经验页"""
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)  # [[wikilink]]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            f"# {self.title}",
            "",
            self.content,
            "",
            "## 标签",
            " ".join(f"#{tag}" for tag in self.tags),
            "",
            "## 相关链接",
            "\n".join(f"- [[{link}]]" for link in self.links) if self.links else "无",
            "",
            "---",
            f"创建时间：{self.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"更新时间：{self.updated_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        return "\n".join(lines)
    
    @classmethod
    def from_markdown(cls, filepath: Path) -> ExperiencePage:
        """从 Markdown 文件解析"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析标题（第一个 # 开头的行）
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else filepath.stem
        
        # 解析标签（## 标签 后面的行）
        tags_match = re.search(r'## 标签\n(.+?)(?=\n##|\n---|\Z)', content, re.DOTALL)
        tags = []
        if tags_match:
            tag_text = tags_match.group(1).strip()
            tags = re.findall(r'#(\w+)', tag_text)
        
        # 解析链接（## 相关链接 后面的 [[wikilink]]）
        links_match = re.search(r'## 相关链接\n(.+?)(?=\n##|\n---|\Z)', content, re.DOTALL)
        links = []
        if links_match:
            link_text = links_match.group(1)
            links = re.findall(r'\[\[([^\]]+)\]\]', link_text)
        
        # 解析正文（标题后到 ## 标签 之前）
        body_match = re.search(r'^# .+\n\n(.+?)(?=\n## 标签)', content, re.DOTALL)
        body = body_match.group(1).strip() if body_match else ""
        
        return cls(
            title=title,
            content=body,
            tags=tags,
            links=links,
        )


class SyzygyVault:
    """Syzygy Vault 知识库"""
    
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
    
    def _to_filename(self, title: str) -> str:
        """标题转文件名"""
        # 移除特殊字符
        safe_title = re.sub(r'[^\w\s-]', '', title)
        # 空格转下划线
        safe_title = re.sub(r'\s+', '_', safe_title)
        return f"{safe_title}.md"
    
    def create_page(self, title: str, content: str, 
                    tags: Optional[List[str]] = None, 
                    links: Optional[List[str]] = None,
                    metadata: Optional[Dict[str, str]] = None) -> Path:
        """创建经验页"""
        page = ExperiencePage(
            title=title,
            content=content,
            tags=tags or [],
            links=links or [],
            metadata=metadata or {},
        )
        
        filepath = self.vault_path / self._to_filename(title)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(page.to_markdown())
        
        return filepath
    
    def get_page(self, title: str) -> Optional[ExperiencePage]:
        """获取经验页"""
        filepath = self.vault_path / self._to_filename(title)
        if not filepath.exists():
            return None
        return ExperiencePage.from_markdown(filepath)
    
    def search_by_tag(self, tag: str) -> List[ExperiencePage]:
        """按标签搜索"""
        results = []
        for filepath in self.vault_path.glob("*.md"):
            page = ExperiencePage.from_markdown(filepath)
            if tag in page.tags:
                results.append(page)
        return results
    
    def search_by_keyword(self, keyword: str) -> List[ExperiencePage]:
        """按关键词搜索"""
        results = []
        keyword_lower = keyword.lower()
        for filepath in self.vault_path.glob("*.md"):
            page = ExperiencePage.from_markdown(filepath)
            # 搜索标题和内容
            if (keyword_lower in page.title.lower() or 
                keyword_lower in page.content.lower()):
                results.append(page)
        return results
    
    def get_linked_pages(self, title: str) -> List[ExperiencePage]:
        """获取链接的页面"""
        page = self.get_page(title)
        if not page:
            return []
        
        linked = []
        for link in page.links:
            linked_page = self.get_page(link)
            if linked_page:
                linked.append(linked_page)
        return linked
    
    def get_backlinks(self, title: str) -> List[ExperiencePage]:
        """获取反向链接（哪些页面链接到此页）"""
        backlinks = []
        for filepath in self.vault_path.glob("*.md"):
            page = ExperiencePage.from_markdown(filepath)
            if title in page.links:
                backlinks.append(page)
        return backlinks
    
    def list_all_pages(self) -> List[str]:
        """列出所有页面标题"""
        titles = []
        for filepath in self.vault_path.glob("*.md"):
            page = ExperiencePage.from_markdown(filepath)
            titles.append(page.title)
        return titles
    
    def generate_ascii_graph(self) -> str:
        """生成 ASCII 知识图谱"""
        pages = self.list_all_pages()
        if not pages:
            return "(空知识库)"
        
        lines = ["知识图谱：", ""]
        for title in pages:
            page = self.get_page(title)
            if page and page.links:
                links_str = " → ".join(page.links[:3])  # 最多显示3个
                if len(page.links) > 3:
                    links_str += f" (+{len(page.links)-3})"
                lines.append(f"  {title}")
                lines.append(f"    └─ {links_str}")
            else:
                lines.append(f"  {title}")
        
        return "\n".join(lines)
