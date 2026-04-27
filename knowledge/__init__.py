"""
知识层 (Knowledge Layer)

提供 Agent 经验存储、检索、关联能力。

核心组件：
- SyzygyVault: 知识库存储（Markdown 格式）
- ExperienceGenerator: 经验页生成器
- ExperiencePage: 经验页数据结构

使用示例：
    from knowledge import SyzygyVault, ExperienceGenerator
    
    # 创建知识库
    vault = SyzygyVault("./vault")
    
    # 创建经验页
    vault.create_page(
        title="API 性能优化经验",
        content="添加 LRU 缓存后响应时间从 500ms 降至 50ms",
        tags=["性能优化", "缓存"],
        links=["缓存设计", "API 最佳实践"]
    )
    
    # 按标签搜索
    pages = vault.search_by_tag("性能优化")
    
    # 获取关联页面
    linked = vault.get_linked_pages("API 性能优化经验")
"""

from knowledge.syzygy import ExperiencePage, SyzygyVault
from knowledge.experience_generator import ExperienceGenerator, ExperienceTemplate

__all__ = [
    "SyzygyVault",
    "ExperiencePage",
    "ExperienceGenerator",
    "ExperienceTemplate",
]
