"""
Conditions for detecting mirroring behavior (user repeating bot's words).

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Any
from src.conditions.policy.registry import policy_condition
from src.conditions.policy.context import PolicyContext
import difflib

def _calculate_similarity(text1: str, text2: str) -> float:
    """Calculate normalized similarity ratio between two texts."""
    if not text1 or not text2:
        return 0.0
    return difflib.SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()

@policy_condition("is_mirroring_bot", category="repair")
def is_mirroring_bot(ctx: PolicyContext) -> bool:
    """
    Check if the user's last message is a mirror of the bot's previous message.
    
    This detects loops where:
    Bot: "Сколько сотрудников?"
    User: "Сколько сотрудников?" (mirroring)
    Bot: "Сколько сотрудников?" (loop)
    
    Returns True if similarity > 0.85
    """
    if not ctx.last_user_message or not ctx.last_bot_message:
        return False
        
    similarity = _calculate_similarity(ctx.last_user_message, ctx.last_bot_message)
    return similarity > 0.85
