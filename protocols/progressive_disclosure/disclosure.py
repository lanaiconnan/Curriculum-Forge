"""Context Disclosure - Graduated information release

Manages how much context (hints, examples, documentation) to provide.
Lower context difficulty = more hints/examples (more support).
Higher context difficulty = less help (more challenging).

Disclosure Policy:
- Round 1: Minimal context (test learner's ability)
- Round 2: Add targeted hints (if struggling)
- Round 3: Full context (scaffolded learning)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import math


class ContextType(Enum):
    """Types of context that can be disclosed"""
    HINTS = "hints"
    EXAMPLES = "examples"
    DOCUMENTATION = "documentation"
    CONSTRAINTS = "constraints"
    SCAFFOLD = "scaffold"


@dataclass
class ContextLayer:
    """A single layer of context
    
    Layers are revealed progressively as context_difficulty decreases.
    """
    type: ContextType
    content: str
    importance: float  # 0-1, higher = revealed first when struggling
    condition: Optional[str] = None  # Optional condition for reveal
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "content": self.content,
            "importance": self.importance,
            "condition": self.condition,
        }


@dataclass
class DisclosurePolicy:
    """Policy for context disclosure
    
    Defines when and how to reveal context layers.
    """
    # Disclosure triggers
    score_threshold_for_hint: float = 0.5      # Below this = reveal hints
    score_threshold_for_example: float = 0.3   # Below this = reveal examples
    score_threshold_for_scaffold: float = 0.2  # Below this = full scaffold
    
    # Layer limits per round
    max_hints_per_round: int = 2
    max_examples_per_round: int = 1
    max_scaffold_per_round: int = 3
    
    # Progressive disclosure
    reveal_rate: float = 0.3  # How much context to reveal per difficulty decrease
    
    def should_reveal(self, context_type: ContextType, score: float, round_num: int) -> bool:
        """Determine if context should be revealed"""
        thresholds = {
            ContextType.HINTS: self.score_threshold_for_hint,
            ContextType.EXAMPLES: self.score_threshold_for_example,
            ContextType.SCAFFOLD: self.score_threshold_for_scaffold,
            ContextType.DOCUMENTATION: 0.4,
            ContextType.CONSTRAINTS: 0.6,
        }
        
        threshold = thresholds.get(context_type, 0.5)
        return score < threshold or round_num > 1


class ContextDiscloser:
    """
    Manages progressive context disclosure
    
    Coordinates with DifficultyController to determine how much
    context to provide based on current difficulty and performance.
    
    Key insight: Context difficulty is INVERSELY related to support.
    - Low context_difficulty (0.2) = lots of hints/examples
    - High context_difficulty (0.8) = minimal context
    """
    
    def __init__(self, policy: DisclosurePolicy = None):
        self.policy = policy or DisclosurePolicy()
        self.layers: List[ContextLayer] = []
        self.revealed_layers: List[str] = []
        self.disclosure_history: List[Dict[str, Any]] = []
    
    def register_layer(self, layer: ContextLayer):
        """Register a context layer"""
        self.layers.append(layer)
    
    def register_layers(self, layers: List[ContextLayer]):
        """Register multiple layers"""
        for layer in layers:
            self.register_layer(layer)
    
    def compute_disclosure(
        self,
        context_difficulty: float,
        current_score: float = 0.5,
        round_num: int = 1,
        weak_areas: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute which context to reveal
        
        Args:
            context_difficulty: Current context difficulty (0-1)
            current_score: Most recent task score (0-1)
            round_num: Current review round
            weak_areas: Learner's weak areas for targeted hints
        
        Returns:
            Dict with revealed context by type
        """
        weak_areas = weak_areas or []
        
        # Sort layers by importance (most important first for struggling learners)
        sorted_layers = sorted(self.layers, key=lambda l: l.importance, reverse=True)
        
        # Compute how much to reveal (inverse of difficulty)
        reveal_ratio = 1.0 - context_difficulty
        
        # Determine number of layers to reveal
        num_to_reveal = max(1, int(len(sorted_layers) * reveal_ratio))
        
        # Adjust based on round
        round_bonus = (round_num - 1) * 0.2
        num_to_reveal = min(len(sorted_layers), num_to_reveal + int(len(sorted_layers) * round_bonus))
        
        # Select layers to reveal
        revealed = {
            "hints": [],
            "examples": [],
            "documentation": [],
            "constraints": [],
            "scaffold": [],
        }
        
        counts = {t.value: 0 for t in ContextType}
        
        for layer in sorted_layers[:num_to_reveal]:
            # Check policy limits
            type_key = layer.type.value
            max_key = f"max_{type_key}_per_round"
            max_count = getattr(self.policy, max_key, 3)
            
            if counts[type_key] >= max_count:
                continue
            
            # Check if relevant to weak areas
            if weak_areas and layer.condition:
                if not any(wa.lower() in layer.condition.lower() for wa in weak_areas):
                    continue
            
            # Check disclosure policy
            if not self.policy.should_reveal(layer.type, current_score, round_num):
                continue
            
            revealed[type_key].append(layer.content)
            counts[type_key] += 1
            self.revealed_layers.append(layer.content[:50])  # Track revealed
        
        # Record disclosure
        disclosure_record = {
            "context_difficulty": context_difficulty,
            "current_score": current_score,
            "round_num": round_num,
            "reveal_ratio": reveal_ratio,
            "layers_revealed": sum(len(v) for v in revealed.values()),
            "by_type": {k: len(v) for k, v in revealed.items()},
        }
        self.disclosure_history.append(disclosure_record)
        
        return revealed
    
    def get_revealed_summary(self) -> str:
        """Get summary of revealed context"""
        if not self.revealed_layers:
            return "No context revealed yet"
        
        return f"Revealed {len(self.revealed_layers)} context items"
    
    def reset(self):
        """Reset disclosed context"""
        self.revealed_layers.clear()
        self.disclosure_history.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get disclosure statistics"""
        if not self.disclosure_history:
            return {"total_disclosures": 0}
        
        # Aggregate by type
        type_totals = {t.value: 0 for t in ContextType}
        for record in self.disclosure_history:
            for type_key, count in record.get("by_type", {}).items():
                type_totals[type_key] = type_totals.get(type_key, 0) + count
        
        return {
            "total_disclosures": len(self.disclosure_history),
            "total_layers_revealed": len(self.revealed_layers),
            "by_type": type_totals,
            "registered_layers": len(self.layers),
        }
