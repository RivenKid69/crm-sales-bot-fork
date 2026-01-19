"""
Effective Action Tracker — отслеживание эффективности действий в сессии.

На основе исследований:
- Contextual Bandits: выбор оптимальной стратегии на основе feedback
- Reinforcement Learning for Dialogue: обучение на результатах действий

Отслеживает какие actions приводят к прогрессу (PROGRESS, LATERAL)
и какие к регрессу (REGRESS, STUCK), чтобы дать рекомендации генератору.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from logger import logger


@dataclass
class ActionOutcome:
    """Результат одного action."""

    action: str
    turn_type: str  # PROGRESS, REGRESS, LATERAL, STUCK, NEUTRAL
    intent: str
    success: bool
    turn_number: int


class EffectiveActionTracker:
    """
    Отслеживает эффективность actions в текущей сессии.

    Записывает результаты каждого action и предоставляет:
    - Список эффективных actions (success rate > 50%)
    - Список неэффективных actions (success rate < 30%)
    - Рекомендации для генератора

    Usage:
        tracker = EffectiveActionTracker()

        # После каждого хода
        tracker.record_outcome(
            action="spin_problem",
            turn_type="PROGRESS",
            intent="pain_shared"
        )

        # Получить рекомендации
        effective = tracker.get_effective_actions()
        hint = tracker.get_tactical_recommendation()
    """

    # Минимальное количество попыток для оценки
    MIN_ATTEMPTS_FOR_EVAL = 2

    # Пороги success rate
    EFFECTIVE_THRESHOLD = 0.5  # > 50% success
    INEFFECTIVE_THRESHOLD = 0.3  # < 30% success

    # Turn types считающиеся успехом
    SUCCESS_TURN_TYPES = {"PROGRESS", "LATERAL"}
    FAILURE_TURN_TYPES = {"REGRESS", "STUCK"}

    # Интенты считающиеся успехом (независимо от turn_type)
    SUCCESS_INTENTS = {
        "agreement",
        "positive",
        "interest_shown",
        "demo_request",
        "contact_provided",
        "question",  # Вопросы = вовлечённость
    }

    def __init__(self):
        """Initialize tracker."""
        self._outcomes: List[ActionOutcome] = []
        self._action_results: Dict[str, List[bool]] = defaultdict(list)
        self._turn_counter = 0

    def reset(self) -> None:
        """Reset tracker for new conversation."""
        self._outcomes.clear()
        self._action_results.clear()
        self._turn_counter = 0

    def record_outcome(
        self,
        action: str,
        turn_type: str,
        intent: str,
    ) -> None:
        """
        Записать результат action.

        Args:
            action: Выполненный action (e.g., "spin_problem", "handle_objection")
            turn_type: Тип хода (PROGRESS, REGRESS, LATERAL, STUCK, NEUTRAL)
            intent: Интент клиента на следующем ходу
        """
        self._turn_counter += 1

        # Определяем успешность
        success = self._is_success(turn_type, intent)

        outcome = ActionOutcome(
            action=action,
            turn_type=turn_type,
            intent=intent,
            success=success,
            turn_number=self._turn_counter,
        )

        self._outcomes.append(outcome)
        self._action_results[action].append(success)

        logger.debug(
            "Action outcome recorded",
            action=action,
            turn_type=turn_type,
            intent=intent,
            success=success,
            turn_number=self._turn_counter,
        )

    def _is_success(self, turn_type: str, intent: str) -> bool:
        """Determine if outcome is successful."""
        # Success by turn type
        if turn_type.upper() in self.SUCCESS_TURN_TYPES:
            return True

        # Success by intent
        if intent.lower() in self.SUCCESS_INTENTS:
            return True

        # Failure by turn type
        if turn_type.upper() in self.FAILURE_TURN_TYPES:
            return False

        # NEUTRAL - считаем нейтральным (не влияет сильно)
        return False

    def get_effective_actions(self) -> List[str]:
        """
        Получить список эффективных actions.

        Returns:
            List of action names with success rate > EFFECTIVE_THRESHOLD
        """
        effective = []

        for action, results in self._action_results.items():
            if len(results) >= self.MIN_ATTEMPTS_FOR_EVAL:
                success_rate = sum(results) / len(results)
                if success_rate > self.EFFECTIVE_THRESHOLD:
                    effective.append(action)

        return effective

    def get_ineffective_actions(self) -> List[str]:
        """
        Получить список неэффективных actions.

        Returns:
            List of action names with success rate < INEFFECTIVE_THRESHOLD
        """
        ineffective = []

        for action, results in self._action_results.items():
            if len(results) >= self.MIN_ATTEMPTS_FOR_EVAL:
                success_rate = sum(results) / len(results)
                if success_rate < self.INEFFECTIVE_THRESHOLD:
                    ineffective.append(action)

        return ineffective

    def get_action_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Получить статистику по всем actions.

        Returns:
            Dict[action, {"attempts": int, "success_rate": float}]
        """
        stats = {}

        for action, results in self._action_results.items():
            attempts = len(results)
            success_rate = sum(results) / attempts if attempts > 0 else 0.0

            stats[action] = {
                "attempts": attempts,
                "successes": sum(results),
                "success_rate": success_rate,
            }

        return stats

    def get_best_action(self) -> Optional[Tuple[str, float]]:
        """
        Получить лучший action по success rate.

        Returns:
            Tuple of (action, success_rate) or None
        """
        best_action = None
        best_rate = 0.0

        for action, results in self._action_results.items():
            if len(results) >= self.MIN_ATTEMPTS_FOR_EVAL:
                success_rate = sum(results) / len(results)
                if success_rate > best_rate:
                    best_rate = success_rate
                    best_action = action

        if best_action:
            return (best_action, best_rate)
        return None

    def get_worst_action(self) -> Optional[Tuple[str, float]]:
        """
        Получить худший action по success rate.

        Returns:
            Tuple of (action, success_rate) or None
        """
        worst_action = None
        worst_rate = 1.0

        for action, results in self._action_results.items():
            if len(results) >= self.MIN_ATTEMPTS_FOR_EVAL:
                success_rate = sum(results) / len(results)
                if success_rate < worst_rate:
                    worst_rate = success_rate
                    worst_action = action

        if worst_action:
            return (worst_action, worst_rate)
        return None

    def get_tactical_recommendation(self) -> str:
        """
        Сгенерировать тактическую рекомендацию для генератора.

        Returns:
            Строка с рекомендацией для добавления в промпт
        """
        parts = []

        # Эффективные actions
        effective = self.get_effective_actions()
        if effective:
            # Берём топ-3
            top_effective = effective[:3]
            actions_str = ", ".join(self._humanize_action(a) for a in top_effective)
            parts.append(f"Эффективно с этим клиентом: {actions_str}")

        # Неэффективные actions
        ineffective = self.get_ineffective_actions()
        if ineffective:
            # Берём топ-2
            top_ineffective = ineffective[:2]
            actions_str = ", ".join(self._humanize_action(a) for a in top_ineffective)
            parts.append(f"Избегай: {actions_str}")

        # Если мало данных - не даём рекомендаций
        if not parts and self._turn_counter < 3:
            return ""

        return ". ".join(parts) if parts else ""

    def _humanize_action(self, action: str) -> str:
        """Convert action name to human-readable form."""
        action_names = {
            "spin_situation": "вопросы о ситуации",
            "spin_problem": "вопросы о проблемах",
            "spin_implication": "вопросы о последствиях",
            "spin_need_payoff": "вопросы о пользе решения",
            "handle_objection": "работа с возражениями",
            "handle_objection_price": "обработка возражений по цене",
            "presentation": "презентация",
            "deflect_and_continue": "перенаправление разговора",
            "continue_current_goal": "продолжение текущей темы",
            "ask_for_contact": "запрос контакта",
            "offer_demo": "предложение демо",
        }

        return action_names.get(action, action.replace("_", " "))

    def get_recent_pattern(self, last_n: int = 3) -> str:
        """
        Получить паттерн последних N результатов.

        Returns:
            String like "success-success-fail" or "improving"/"declining"
        """
        if len(self._outcomes) < last_n:
            return "insufficient_data"

        recent = self._outcomes[-last_n:]
        successes = sum(1 for o in recent if o.success)

        # Определяем тренд
        if successes == last_n:
            return "all_success"
        elif successes == 0:
            return "all_failure"
        elif successes >= last_n * 0.6:
            return "mostly_success"
        else:
            return "mixed"

    @property
    def total_turns(self) -> int:
        """Get total number of turns tracked."""
        return self._turn_counter

    @property
    def overall_success_rate(self) -> float:
        """Get overall success rate across all actions."""
        total_attempts = sum(len(r) for r in self._action_results.values())
        total_successes = sum(sum(r) for r in self._action_results.values())

        if total_attempts == 0:
            return 0.0

        return total_successes / total_attempts
