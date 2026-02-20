"""
IntentPatternGuardSource - Configurable pattern detection for any intent category.

Today: catches comparison fatigue (repeated comparison intents).
Tomorrow: configure for any new category without code changes.

Architecture:
- Config-driven from constants.yaml (intent_pattern_guard.patterns)
- O(1) should_contribute check (intent in set)
- Persona-aware limits
- State-aware action selection (close vs other states)
- Feature-flagged (intent_pattern_guard: False by default)

Principle 3.2: Single Responsibility - detects intent patterns
Principle 3.3: Config-Driven - all patterns from YAML
Principle 3.4: Defense-in-Depth - additional layer for close state
"""

from typing import Dict, Any, Optional, Set
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.feature_flags import flags

logger = logging.getLogger(__name__)


class IntentPatternGuardSource(KnowledgeSource):
    """
    Configurable pattern detection for any intent category.

    Reads pattern definitions from constants.yaml:
        intent_pattern_guard:
          patterns:
            comparison_like:
              intents: [comparison, question_product_comparison, ...]
              persona_limits:
                default: { streak: 3, total: 5 }
                competitor_user: { streak: 4, total: 7 }
              close_action: close_answer_and_collect
              default_action: nudge_progress

    should_contribute(): O(1) - checks current_intent in configured intents set
    contribute(): proposes action based on state and streak severity
    """

    def __init__(self, name: str = "IntentPatternGuardSource", enabled: bool = True):
        super().__init__(name)
        self._enabled = enabled

        # Build lookup: intent -> pattern_name for O(1) check
        self._intent_to_pattern: Dict[str, str] = {}
        self._patterns: Dict[str, Dict[str, Any]] = {}
        self._all_pattern_intents: Set[str] = set()

        self._load_config()

    def _load_config(self) -> None:
        """Load pattern config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_intent_pattern_guard_config
            config = get_intent_pattern_guard_config()
        except (ImportError, Exception) as e:
            logger.warning(f"Could not load intent_pattern_guard config: {e}")
            return

        patterns = config.get("patterns", {})
        for pattern_name, pattern_cfg in patterns.items():
            intents = pattern_cfg.get("intents", [])
            self._patterns[pattern_name] = pattern_cfg
            for intent in intents:
                self._intent_to_pattern[intent] = pattern_name
                self._all_pattern_intents.add(intent)

        logger.debug(
            f"IntentPatternGuardSource loaded {len(self._patterns)} patterns, "
            f"{len(self._all_pattern_intents)} intents"
        )

    def should_contribute(self, blackboard) -> bool:
        """
        O(1) check: is current intent in any configured pattern AND
        streak/total exceeds persona threshold?
        """
        if not self._enabled:
            return False

        if not flags.is_enabled("intent_pattern_guard"):
            return False

        if not self._patterns:
            return False

        ctx = blackboard.get_context()
        current_intent = ctx.current_intent

        # Autonomous flow delegates pattern fatigue judgment to LLM manager.
        state_config = getattr(ctx, "state_config", {})
        if isinstance(state_config, dict) and state_config.get("autonomous", False):
            return False

        # O(1) lookup
        if current_intent not in self._all_pattern_intents:
            return False

        # Get pattern config
        pattern_name = self._intent_to_pattern[current_intent]
        pattern_cfg = self._patterns[pattern_name]

        # Get persona-specific limits
        persona = ctx.persona or "default"
        persona_limits = pattern_cfg.get("persona_limits", {})
        limits = persona_limits.get(persona, persona_limits.get("default", {}))
        streak_threshold = limits.get("streak", 3)
        total_threshold = limits.get("total", 5)

        # Check streak via IntentTracker
        tracker = ctx.intent_tracker
        # Use category_streak if the pattern_name is a composed category,
        # otherwise count streak manually from pattern intents
        category_streak = self._get_pattern_streak(tracker, pattern_name, pattern_cfg)
        category_total = self._get_pattern_total(tracker, pattern_name, pattern_cfg)

        return category_streak >= streak_threshold or category_total >= total_threshold

    def contribute(self, blackboard) -> None:
        """
        Propose action based on current state and streak severity.

        In close state → proposes pattern's close_action (e.g., close_answer_and_collect)
        In other states → proposes pattern's default_action (e.g., nudge_progress)
        If streak >= 2x threshold → proposes at HIGH priority
        """
        ctx = blackboard.get_context()
        current_intent = ctx.current_intent
        pattern_name = self._intent_to_pattern.get(current_intent)

        if not pattern_name or pattern_name not in self._patterns:
            return

        pattern_cfg = self._patterns[pattern_name]
        current_state = ctx.state

        # Get persona limits
        persona = ctx.persona or "default"
        persona_limits = pattern_cfg.get("persona_limits", {})
        limits = persona_limits.get(persona, persona_limits.get("default", {}))
        streak_threshold = limits.get("streak", 3)

        # Get streak count
        tracker = ctx.intent_tracker
        category_streak = self._get_pattern_streak(tracker, pattern_name, pattern_cfg)

        # Determine action based on state
        if current_state == "close":
            action = pattern_cfg.get("close_action", "close_answer_and_collect")
        else:
            action = pattern_cfg.get("default_action", "nudge_progress")

        # Determine priority: HIGH if streak >= 2x threshold
        priority = Priority.HIGH if category_streak >= streak_threshold * 2 else Priority.NORMAL

        blackboard.propose_action(
            action=action,
            priority=priority,
            combinable=True,
            reason_code=f"intent_pattern_{pattern_name}",
            source_name=self.name,
            metadata={
                "pattern": pattern_name,
                "streak": category_streak,
                "threshold": streak_threshold,
                "persona": persona,
                "state": current_state,
            },
        )

        self._log_contribution(
            action=action,
            transition=None,
            reason=f"Pattern '{pattern_name}' streak={category_streak} >= threshold={streak_threshold}",
        )

    def _get_pattern_streak(self, tracker, pattern_name: str, pattern_cfg: Dict) -> int:
        """Get consecutive count for pattern intents."""
        # Try category_streak first (if IntentTracker knows this category)
        try:
            streak = tracker.category_streak(pattern_name)
            if streak > 0:
                return streak
        except (AttributeError, KeyError):
            pass

        # Fallback: count manually from recent intents
        intents_set = set(pattern_cfg.get("intents", []))
        try:
            recent = tracker.get_recent_intents(10)
        except (AttributeError, Exception):
            return 0

        streak = 0
        for intent in reversed(recent):
            if intent in intents_set:
                streak += 1
            else:
                break
        return streak

    def _get_pattern_total(self, tracker, pattern_name: str, pattern_cfg: Dict) -> int:
        """Get total count for pattern intents."""
        try:
            total = tracker.category_total(pattern_name)
            if total > 0:
                return total
        except (AttributeError, KeyError):
            pass

        # Fallback: sum individual intent totals
        intents = pattern_cfg.get("intents", [])
        total = 0
        for intent in intents:
            try:
                total += tracker.total_count(intent)
            except (AttributeError, Exception):
                pass
        return total
