"""
Structural Frustration Detector.

Detects behavioral frustration from context_window patterns
(not tonal — structural signals from dialogue patterns).

Research:
- Hone (2006) — message length decrease as frustration indicator
- Forbes-Riley & Litman (2011) — unanswered repetition correlates with frustration

Signals:
1. unanswered_repeat: question category 2+ times + deflect response each time → +1 per extra (max +3)
2. length_decrease: 3 recent user_message lengths strictly decreasing, last < 20 chars → +1
3. deflection_loop: 3+ deflect_and_continue actions in window → +1
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any


DEFLECTION_ACTIONS = {"deflect_and_continue", "continue_current_goal"}


@dataclass
class StructuralFrustrationSignal:
    """Result of structural frustration analysis."""
    delta: int = 0
    signals: List[str] = field(default_factory=list)


class StructuralFrustrationDetector:
    """
    Behavioral frustration from context_window patterns.

    This detector supplements tonal frustration (from tone_analyzer)
    with structural signals that indicate frustration even when
    the client's tone is neutral/polite.

    Signals:
    1. unanswered_repeat: question asked 2+ times, each time deflected → +1 per extra (max +3)
    2. length_decrease: 3 recent user_message lengths strictly decreasing, last < 20 chars → +1
    3. deflection_loop: 3+ deflect_and_continue actions in window → +1
    """

    def analyze(self, context_window: Any) -> StructuralFrustrationSignal:
        """
        Analyze context_window for structural frustration signals.

        Args:
            context_window: ContextWindow instance

        Returns:
            StructuralFrustrationSignal with delta and signal names
        """
        result = StructuralFrustrationSignal()
        if context_window is None or len(context_window) < 2:
            return result

        # Signal 1: unanswered repeats
        unanswered = self._count_unanswered_repeats(context_window)
        if unanswered >= 2:
            delta = min(unanswered - 1, 3)
            result.delta += delta
            result.signals.append(f"unanswered_repeat:{unanswered}")

        # Signal 2: length decrease
        if self._detect_length_decrease(context_window):
            result.delta += 1
            result.signals.append("length_decrease")

        # Signal 3: deflection loop
        deflections = self._count_deflections(context_window)
        if deflections >= 3:
            result.delta += 1
            result.signals.append(f"deflection_loop:{deflections}")

        return result

    def _count_unanswered_repeats(self, cw: Any) -> int:
        """
        Count unanswered question repeats.

        A question is "unanswered" if the bot responded with a deflection action.
        """
        question_set = cw._get_question_intents()
        count = 0
        seen = set()
        for turn in cw.turns:
            intent = getattr(turn, 'intent', None)
            action = getattr(turn, 'action', None)
            if intent and intent in question_set:
                if intent in seen and action in DEFLECTION_ACTIONS:
                    count += 1
                seen.add(intent)
        return count

    def _detect_length_decrease(self, cw: Any) -> bool:
        """
        Detect strictly decreasing message lengths in last 3 turns.

        Returns True if lengths are strictly decreasing and last < 20 chars.
        """
        turns = cw.turns
        if len(turns) < 3:
            return False
        recent = turns[-3:]
        lengths = [len(getattr(t, 'user_message', '') or '') for t in recent]
        return lengths[0] > lengths[1] > lengths[2] and lengths[2] < 20

    def _count_deflections(self, cw: Any) -> int:
        """Count deflection actions in the window."""
        return sum(
            1 for t in cw.turns
            if getattr(t, 'action', None) in DEFLECTION_ACTIONS
        )
