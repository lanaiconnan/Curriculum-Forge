"""
经验生成器

从任务执行结果自动生成经验页，包括：
- 失败分析
- 成功要素提取
- 经验教训总结
- 相关任务关联
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from knowledge.syzygy import SyzygyVault
    from providers.base import Task, TaskResult


@dataclass
class ExperienceTemplate:
    """经验模板"""
    task_type: str
    success_pattern: str
    failure_pattern: str
    key_lessons: List[str]


class ExperienceGenerator:
    """经验生成器"""
    
    def __init__(self, vault: SyzygyVault):
        self.vault = vault
    
    def generate_from_task(
        self, 
        task,  # Task from services.coordinator
        result,  # Mock or result object
        reflection: Optional[str] = None
    ) -> str:
        """从任务生成经验页"""
        # 确定标题
        title = f"任务：{getattr(task, 'name', None) or task.id}"
        
        # 构建正文
        content_parts = []
        
        # 背景
        content_parts.append("## 背景")
        content_parts.append(f"任务类型：{task.type}")
        if hasattr(task, 'description') and task.description:
            content_parts.append(f"描述：{task.description}")
        content_parts.append("")
        
        # 方案
        content_parts.append("## 方案")
        # Task uses payload, not params
        payload = getattr(task, 'payload', {}) or getattr(task, 'params', {})
        if payload:
            for key, value in payload.items():
                content_parts.append(f"- {key}: {value}")
        content_parts.append("")
        
        # 结果
        content_parts.append("## 结果")
        status = "成功" if result.status.value == "completed" else "失败"
        content_parts.append(f"状态：{status}")
        if result.output:
            output_data = result.output.data if hasattr(result.output, 'data') else result.output
            if output_data:
                content_parts.append(f"输出：{output_data}")
        if result.error:
            content_parts.append(f"错误：{result.error}")
        content_parts.append("")
        
        # 经验教训
        content_parts.append("## 经验教训")
        if reflection:
            content_parts.append(reflection)
        elif result.status.value != "completed":
            content_parts.append("- 任务失败，需要分析原因")
            content_parts.append("- 建议检查参数配置和环境")
        else:
            content_parts.append("- 任务执行成功")
            if hasattr(result, 'metrics') and result.metrics:
                content_parts.append(f"- 关键指标：{result.metrics}")
        content_parts.append("")
        
        content = "\n".join(content_parts)
        
        # 提取标签
        tags = self._extract_tags(task)
        
        # 提取链接
        links = self._extract_links(task)
        
        # 创建页面
        filepath = self.vault.create_page(
            title=title,
            content=content,
            tags=tags,
            links=links,
            metadata={
                "task_id": task.id,
                "task_type": task.type,
                "status": result.status.value,
            }
        )
        
        return str(filepath)
    
    def _extract_tags(self, task) -> List[str]:
        """提取标签"""
        tags = []
        
        # 任务类型作为标签
        if task.type:
            tags.append(task.type)
        
        # 从参数提取关键词
        payload = getattr(task, 'payload', {}) or getattr(task, 'params', {})
        if payload:
            param_str = str(payload).lower()
            # 性能相关
            if any(kw in param_str for kw in ["性能", "performance", "速度", "优化"]):
                tags.append("性能优化")
            # 缓存相关
            if any(kw in param_str for kw in ["缓存", "cache"]):
                tags.append("缓存")
            # 数据库相关
            if any(kw in param_str for kw in ["数据库", "database", "sql", "db"]):
                tags.append("数据库")
        
        return tags
    
    def _extract_links(self, task) -> List[str]:
        """提取相关链接"""
        links = []
        
        # 从任务描述提取可能的链接
        description = getattr(task, 'description', None)
        if description:
            # 查找已有经验页中的关键词
            all_pages = self.vault.list_all_pages()
            for page_title in all_pages:
                # 简单匹配：标题出现在描述中
                if page_title.replace("任务：", "") in description:
                    links.append(page_title)
        
        return links
    
    def generate_reflection(
        self, 
        task, 
        result
    ) -> str:
        """生成反思文本（供 LLM 增强）"""
        template = f"""
任务：{getattr(task, 'name', None) or task.id}
类型：{task.type}
状态：{result.status.value}

{self._generate_failure_analysis(result) if result.status.value != "completed" else self._generate_success_analysis(result)}
"""
        return template.strip()
    
    def _generate_failure_analysis(self, result) -> str:
        """失败分析"""
        parts = ["失败分析："]
        if result.error:
            parts.append(f"错误信息：{result.error}")
        parts.append("可能原因：")
        parts.append("- 参数配置不正确")
        parts.append("- 资源不足")
        parts.append("- 环境问题")
        parts.append("")
        parts.append("建议改进：")
        parts.append("- 检查输入参数")
        parts.append("- 增加资源配额")
        parts.append("- 查看日志详情")
        return "\n".join(parts)
    
    def _generate_success_analysis(self, result) -> str:
        """成功分析"""
        parts = ["成功要素："]
        if hasattr(result, 'metrics') and result.metrics:
            parts.append(f"关键指标：{result.metrics}")
        parts.append("- 任务按预期完成")
        parts.append("- 参数配置合理")
        parts.append("")
        parts.append("可复用经验：")
        parts.append("- 当前配置可作为模板")
        return "\n".join(parts)
