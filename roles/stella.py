"""
Stella - Memory-Enhanced Coordinator

Stella extends the base Coordinator with:
- Experience retrieval from Syzygy Vault
- Experience storage after task completion
- Reflection loop for continuous learning

Design Philosophy:
- Minimal changes to existing Coordinator
- Memory as an enhancement layer, not replacement
- LLM-optional: works with or without LLM for reflection

Based on AI Agent Town Architecture Phase 1.2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from knowledge.syzygy import SyzygyVault, ExperiencePage
    from knowledge.experience_generator import ExperienceGenerator
    from services.coordinator import Coordinator, Task, Workflow

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    """Memory context for task execution"""
    task_id: str
    relevant_experiences: List[ExperiencePage] = field(default_factory=list)
    similar_tasks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    
    def to_context_string(self) -> str:
        """Convert to context string for LLM prompt"""
        if not self.relevant_experiences:
            return "无历史经验参考"
        
        parts = ["相关历史经验："]
        for i, exp in enumerate(self.relevant_experiences[:3], 1):
            parts.append(f"\n{i}. {exp.title}")
            # Extract key content (first 200 chars)
            content_preview = exp.content[:200].replace('\n', ' ')
            parts.append(f"   {content_preview}...")
            if exp.tags:
                parts.append(f"   标签：{', '.join(exp.tags)}")
        
        if self.recommendations:
            parts.append("\n建议：")
            for rec in self.recommendations:
                parts.append(f"- {rec}")
        
        return "\n".join(parts)


class Stella:
    """Memory-Enhanced Coordinator
    
    Extends base Coordinator with experience retrieval and storage.
    Designed to work with existing Coordinator without breaking changes.
    """
    
    def __init__(
        self, 
        coordinator: Coordinator,
        vault: SyzygyVault,
        experience_generator: Optional[ExperienceGenerator] = None,
        enable_reflection: bool = True,
        max_relevant_experiences: int = 3,
    ):
        self.coordinator = coordinator
        self.vault = vault
        self.experience_generator = experience_generator
        self.enable_reflection = enable_reflection
        self.max_relevant_experiences = max_relevant_experiences
        
        # Memory cache for current session
        self._memory_cache: Dict[str, MemoryContext] = {}
        
        # Hook into coordinator events
        self._setup_hooks()
    
    def _setup_hooks(self):
        """Setup hooks for coordinator events"""
        # Subscribe to coordinator event bus
        subscriber_id = self.coordinator.event_bus.subscribe("stella")
        
        # Store original callbacks if they exist
        original_on_task_complete = self.coordinator._on_task_complete
        original_on_workflow_complete = self.coordinator._on_workflow_complete
        
        # Wrap task complete callback
        def on_task_complete(task):
            # Store experience
            self._store_experience(task)
            # Call original callback
            if original_on_task_complete:
                original_on_task_complete(task)
        
        # Wrap workflow complete callback
        def on_workflow_complete(workflow):
            # Analyze workflow results
            self._analyze_workflow(workflow)
            # Call original callback
            if original_on_workflow_complete:
                original_on_workflow_complete(workflow)
        
        # Set wrapped callbacks
        self.coordinator._on_task_complete = on_task_complete
        self.coordinator._on_workflow_complete = on_workflow_complete
        
        logger.info(f"Stella hooks initialized (subscriber: {subscriber_id})")
    
    def retrieve_experiences(self, task: Task) -> MemoryContext:
        """Retrieve relevant experiences for a task
        
        Searches the vault for:
        1. Tasks with similar type
        2. Tasks with similar tags
        3. Tasks with similar keywords in description
        """
        context = MemoryContext(task_id=task.id)
        
        # 1. Search by task type
        if task.type:
            type_experiences = self.vault.search_by_tag(task.type)
            context.relevant_experiences.extend(type_experiences[:2])
        
        # 2. Search by keywords in description
        description = getattr(task, 'description', None)
        if description:
            # Extract key terms (simple approach)
            keywords = self._extract_keywords(description)
            for keyword in keywords[:3]:
                keyword_results = self.vault.search_by_keyword(keyword)
                for exp in keyword_results:
                    if exp not in context.relevant_experiences:
                        context.relevant_experiences.append(exp)
        
        # 3. Limit results
        context.relevant_experiences = context.relevant_experiences[:self.max_relevant_experiences]
        
        # 4. Find similar task IDs
        for exp in context.relevant_experiences:
            task_id = exp.metadata.get('task_id')
            if task_id and task_id != task.id:
                context.similar_tasks.append(task_id)
        
        # 5. Calculate confidence score
        if context.relevant_experiences:
            # Simple heuristic: more experiences = higher confidence
            context.confidence_score = min(1.0, len(context.relevant_experiences) * 0.3)
        
        # 6. Generate recommendations (simple rule-based)
        context.recommendations = self._generate_recommendations(task, context)
        
        # Cache the context
        self._memory_cache[task.id] = context
        
        return context
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text (simple implementation)
        
        Uses simple heuristics for Chinese keyword extraction.
        For production, consider using jieba or other NLP libraries.
        """
        # Remove common words
        stop_words = {'的', '是', '在', '和', '了', '有', '不', '这', '为', '以', '需要', '可以', '进行'}
        
        # Simple tokenization for Chinese (2-char sliding window)
        # This is a simple approach; production should use jieba
        import re
        keywords = []
        
        # Extract English words (2+ chars)
        en_words = re.findall(r'[a-zA-Z]{2,}', text.lower())
        keywords.extend(en_words)
        
        # For Chinese, use 2-char sliding window for common 2-char words
        # This catches words like '缓存', '优化', '性能', etc.
        chinese_text = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_text:
            # Generate 2-char and 3-char candidates
            for i in range(len(segment) - 1):
                candidate = segment[i:i+2]
                if candidate not in stop_words:
                    keywords.append(candidate)
            for i in range(len(segment) - 2):
                candidate = segment[i:i+3]
                if candidate not in stop_words:
                    keywords.append(candidate)
        
        # Return unique keywords
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        
        return unique
    
    def _generate_recommendations(self, task: Task, context: MemoryContext) -> List[str]:
        """Generate recommendations based on past experiences"""
        recommendations = []
        
        for exp in context.relevant_experiences:
            # Check if experience was successful
            status = exp.metadata.get('status', '')
            
            if status == 'completed':
                # Extract lessons from content
                if '经验教训' in exp.content:
                    # Find the lessons section
                    lessons_start = exp.content.find('经验教训')
                    lessons_text = exp.content[lessons_start:lessons_start+200]
                    recommendations.append(f"参考成功案例：{exp.title}")
            else:
                # Failure case - warn about potential issues
                recommendations.append(f"注意避免：{exp.title} 中的错误")
        
        return recommendations[:3]  # Limit to 3 recommendations
    
    def _store_experience(self, task: Task):
        """Store experience after task completion"""
        if not self.experience_generator:
            logger.debug("ExperienceGenerator not configured, skipping storage")
            return
        
        # Get task result
        result = getattr(task, 'result', None)
        if not result:
            logger.debug(f"Task {task.id} has no result, skipping experience storage")
            return
        
        try:
            # Generate reflection if enabled
            reflection = None
            if self.enable_reflection:
                reflection = self._generate_reflection(task, result)
            
            # Create mock result object if needed
            if not hasattr(result, 'status'):
                from types import SimpleNamespace
                result = SimpleNamespace(
                    status=SimpleNamespace(value='completed'),
                    output=result,
                    error=None
                )
            
            # Generate experience page
            filepath = self.experience_generator.generate_from_task(
                task=task,
                result=result,
                reflection=reflection
            )
            
            logger.info(f"Experience stored: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to store experience for task {task.id}: {e}")
    
    def _generate_reflection(self, task: Task, result: Any) -> Optional[str]:
        """Generate reflection text (can be enhanced with LLM)"""
        # Simple rule-based reflection
        status = getattr(result, 'status', None)
        if status:
            status_value = getattr(status, 'value', str(status))
        else:
            status_value = 'unknown'
        
        if status_value == 'completed':
            return """
反思：
- 任务成功完成，关键步骤执行正确
- 可以作为类似任务的参考模板
- 建议记录关键参数配置以供复用
""".strip()
        else:
            error = getattr(result, 'error', '未知错误')
            return f"""
反思：
- 任务执行失败：{error}
- 需要检查输入参数和环境配置
- 建议查阅相关文档或寻求帮助
""".strip()
    
    def _analyze_workflow(self, workflow: Workflow):
        """Analyze workflow results and generate insights"""
        completed = 0
        failed = 0
        
        for task in workflow.tasks.values():
            if task.status.value == 'completed':
                completed += 1
            elif task.status.value == 'failed':
                failed += 1
        
        total = len(workflow.tasks)
        success_rate = completed / total if total > 0 else 0
        
        logger.info(
            f"Workflow {workflow.id} analysis: "
            f"{completed}/{total} completed ({success_rate:.1%}), "
            f"{failed} failed"
        )
        
        # Store workflow-level experience if significant
        if failed > 0 and self.experience_generator:
            # Could generate workflow-level experience
            pass
    
    def build_context(self, task: Task) -> Dict[str, Any]:
        """Build context for task execution
        
        This is the main entry point for memory-enhanced execution.
        Returns a context dict that can be passed to agents.
        """
        memory_context = self.retrieve_experiences(task)
        
        return {
            "task_id": task.id,
            "task_type": task.type,
            "memory_context": memory_context.to_context_string(),
            "relevant_experiences": [
                {"title": exp.title, "tags": exp.tags}
                for exp in memory_context.relevant_experiences
            ],
            "recommendations": memory_context.recommendations,
            "confidence_score": memory_context.confidence_score,
        }
    
    # Delegate to coordinator
    def __getattr__(self, name):
        """Delegate unknown attributes to coordinator"""
        return getattr(self.coordinator, name)
    
    # Convenience methods
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        all_pages = self.vault.list_all_pages()
        return {
            "total_experiences": len(all_pages),
            "cached_contexts": len(self._memory_cache),
            "vault_path": str(self.vault.vault_path),
        }
    
    def clear_cache(self):
        """Clear memory cache"""
        self._memory_cache.clear()
        logger.info("Memory cache cleared")
