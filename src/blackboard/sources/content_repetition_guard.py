# src/blackboard/sources/content_repetition_guard.py

"""
ContentRepetitionGuardSource — cross-state, window-based guard against content repetition.

Detects when the bot keeps delivering the same information (even paraphrased)
across multiple turns, regardless of state changes.

Primary signal: response embedding cosine similarity (universal).
Secondary signal: fact_key overlap (deterministic confirmation).

Window-based count (NOT consecutive streak) catches:
- Direct loops (A-A-A)
- Oscillation (A-B-A-B)
- Meta-loops (KB → redirect → KB → redirect)

Escalation ladder:
    count >= 2 → redirect_after_repetition (HIGH)
    count >= 3 → escalate_repeated_content (CRITICAL) + transition → soft_close
"""

import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

logger = logging.getLogger(__name__)


class ContentRepetitionGuardSource(KnowledgeSource):
    """
    Детектирует повторение одного и того же контента cross-state.

    Window-based: считает сколько из последних N ответов похожи на текущий.
    НЕ consecutive — ловит oscillation (A-B-A-B) и meta-loops (KB→redirect→KB).

    Primary: response embedding cosine similarity (универсальный).
    Secondary: fact_key overlap (детерминистическое подтверждение).

    Count вычисляется в ContextWindow.compute_content_repeat_count()
    и передаётся через ContextEnvelope.content_repeat_count.
    """

    SOFT_THRESHOLD = 2   # count >= 2 → redirect
    HARD_THRESHOLD = 3   # count >= 3 → escalate

    # Actions that are our own interventions (to prevent meta-loops)
    _INTERVENTION_ACTIONS = frozenset({
        "redirect_after_repetition",
        "escalate_repeated_content",
    })

    def should_contribute(self, blackboard) -> bool:
        ctx = blackboard.get_context()
        envelope = ctx.context_envelope

        # Guard 1: Already in terminal state — never interfere
        if ctx.state_config.get("max_turns_in_state", -1) == 0:
            return False

        # Guard 2: Terminal data complete — about to transition, don't interfere
        terminal_reqs = ctx.state_config.get("terminal_state_requirements", {})
        if terminal_reqs:
            collected = ctx.collected_data or {}
            for reqs in terminal_reqs.values():
                if reqs and all(collected.get(f) for f in reqs):
                    return False

        count = getattr(envelope, 'content_repeat_count', 0) if envelope else 0
        if count < self.SOFT_THRESHOLD:
            return False

        # Anti-meta-loop: если предыдущий ход уже был нашим intervention,
        # пропустить — дать боту один нормальный ход, чтобы count пересчитался
        # корректно от нового KB-ответа (а не от redirect-ответа).
        last_action = getattr(envelope, 'last_action', None) if envelope else None
        if last_action in self._INTERVENTION_ACTIONS:
            return False

        # Guard: только если пользователь продолжает ту же тему
        # (предотвращает false positive при легитимном возврате к теме)
        repeated = getattr(envelope, 'repeated_question', None) if envelope else None
        if repeated is not None:
            return True

        # Fallback guard: текущий интент совпадает с последним
        current = getattr(envelope, 'current_intent', None) if envelope else None
        last = getattr(envelope, 'last_intent', None) if envelope else None
        return current is not None and current == last

    def contribute(self, blackboard) -> None:
        ctx = blackboard.get_context()
        envelope = ctx.context_envelope
        count = getattr(envelope, 'content_repeat_count', 0) if envelope else 0

        if count >= self.HARD_THRESHOLD:
            logger.info(
                "Content repetition HARD: count=%d, escalating", count
            )
            # CRITICAL priority: побеждает PriceQuestionSource (HIGH)
            # combinable=True (I18): позволяет merge action+transition
            blackboard.propose_action(
                action="escalate_repeated_content",
                priority=Priority.CRITICAL,
                combinable=True,
                reason_code="content_repetition_escalate",
                source_name=self.name,
            )
            blackboard.propose_transition(
                next_state="soft_close",
                priority=Priority.CRITICAL,
                reason_code="content_repetition_escalate",
                source_name=self.name,
            )
        else:
            logger.info(
                "Content repetition SOFT: count=%d, redirecting", count
            )
            blackboard.propose_action(
                action="redirect_after_repetition",
                priority=Priority.HIGH,
                combinable=True,
                reason_code="content_repetition_redirect",
                source_name=self.name,
            )
