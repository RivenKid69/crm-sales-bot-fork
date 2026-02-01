"""
Conversation Guard для CRM Sales Bot.

Защита от зацикливания, тупиков и превышения лимитов.

Обнаруживает:
- Loops: одинаковые состояния/сообщения подряд
- Dead-ends: застревание в фазе
- Timeout: превышение времени
- Exhaustion: слишком много попыток

Использование:
    from conversation_guard import ConversationGuard

    guard = ConversationGuard()
    can_continue, intervention = guard.check("spin_situation", "сообщение", {})

    if not can_continue:
        # Мягко завершить диалог
        pass
    elif intervention:
        # Применить fallback указанного уровня
        pass
"""

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.logger import logger

# Import from Single Source of Truth for frustration thresholds
from src.frustration_thresholds import FRUSTRATION_HIGH


@dataclass
class GuardConfig:
    """Конфигурация лимитов ConversationGuard"""
    # Основные лимиты
    max_turns: int = 25                    # Средний sales диалог: 8-15 turns
    max_phase_attempts: int = 3            # LivePerson recommendation
    max_same_state: int = 4                # Loop detection
    max_same_message: int = 3              # BUG #4 FIX: raised from 2 — two identical is too aggressive
    timeout_seconds: int = 1800            # 30 минут

    # Пороги прогресса
    progress_check_interval: int = 5       # Каждые 5 turns проверяем прогресс
    min_unique_states_for_progress: int = 2  # Минимум уникальных состояний за интервал

    # FIX 3: Tier 2 self-loop escalation threshold
    max_consecutive_tier_2: int = 3        # Escalate to tier_3 after N consecutive tier_2 in same state

    # Frustration thresholds - MUST use centralized value from frustration_thresholds
    # NOTE: Using FRUSTRATION_HIGH ensures consistency with fallback conditions
    # and personalization conditions. DO NOT hardcode a different value here!
    high_frustration_threshold: int = FRUSTRATION_HIGH

    @classmethod
    def default(cls) -> "GuardConfig":
        """Дефолтная конфигурация"""
        return cls()

    @classmethod
    def strict(cls) -> "GuardConfig":
        """Строгая конфигурация (для коротких диалогов)"""
        return cls(
            max_turns=15,
            max_phase_attempts=2,
            max_same_state=3,
            timeout_seconds=900,  # 15 минут
        )

    @classmethod
    def relaxed(cls) -> "GuardConfig":
        """Расслабленная конфигурация (для сложных диалогов)"""
        return cls(
            max_turns=40,
            max_phase_attempts=5,
            max_same_state=6,
            timeout_seconds=3600,  # 1 час
        )


@dataclass
class GuardState:
    """Состояние ConversationGuard"""
    turn_count: int = 0
    state_history: List[str] = field(default_factory=list)
    message_history: List[str] = field(default_factory=list)
    phase_attempts: Dict[str, int] = field(default_factory=lambda: Counter())
    start_time: Optional[float] = None
    last_progress_turn: int = 0
    collected_data_count: int = 0
    frustration_level: int = 0
    # BUG-001 FIX: Track intents to detect informative responses
    intent_history: List[str] = field(default_factory=list)
    last_intent: str = ""
    # Pre-intervention flag (WARNING level 5-6 with certain conditions)
    pre_intervention_triggered: bool = False
    # TIER_2 self-loop escalation (moved from FallbackHandler)
    consecutive_tier_2_count: int = 0
    consecutive_tier_2_state: Optional[str] = None


class ConversationGuard:
    """
    Защита от зацикливания, тупиков и превышения лимитов.

    Обнаруживает:
    - Loops: одинаковые состояния/сообщения подряд
    - Dead-ends: застревание в фазе без прогресса
    - Timeout: превышение времени диалога
    - Exhaustion: слишком много попыток в одной фазе
    - Frustration: накопленное раздражение клиента

    Returns:
        Tuple[can_continue, intervention_action]
        - can_continue: True если можно продолжать
        - intervention_action: None или tier (fallback_tier_1, ..., soft_close)
    """

    # Уровни интервенций
    TIER_1 = "fallback_tier_1"  # Переформулировать вопрос
    TIER_2 = "fallback_tier_2"  # Предложить варианты (кнопки)
    TIER_3 = "fallback_tier_3"  # Предложить skip
    TIER_4 = "soft_close"       # Мягко завершить

    def __init__(self, config: Optional[GuardConfig] = None):
        self.config = config or GuardConfig.default()
        self._state = GuardState()

    def reset(self) -> None:
        """Сбросить состояние для нового диалога"""
        self._state = GuardState()
        logger.debug("ConversationGuard reset")

    @property
    def turn_count(self) -> int:
        """Текущий номер хода"""
        return self._state.turn_count

    @property
    def state_history(self) -> List[str]:
        """История состояний"""
        return self._state.state_history.copy()

    @property
    def phase_attempts(self) -> Dict[str, int]:
        """Счётчик попыток по фазам"""
        return dict(self._state.phase_attempts)

    def set_frustration_level(self, level: int) -> None:
        """
        Установить уровень раздражения клиента.
        Используется ToneAnalyzer'ом извне.
        """
        self._state.frustration_level = max(0, min(10, level))

    def check(
        self,
        state: str,
        message: str,
        collected_data: Dict,
        frustration_level: Optional[int] = None,
        last_intent: str = "",  # BUG-001 FIX: Accept intent for informative check
        pre_intervention_triggered: bool = False  # Pre-intervention at WARNING level (5-6)
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить состояние диалога и определить нужна ли интервенция.

        Args:
            state: Текущее состояние FSM
            message: Сообщение клиента
            collected_data: Собранные данные о клиенте
            frustration_level: Уровень раздражения (0-10), если None - используется внутренний
            last_intent: Предыдущий intent клиента (для проверки информативности)
            pre_intervention_triggered: Whether pre-intervention was triggered at WARNING level
                                        (5-6 frustration with RUSHED/FRUSTRATED tone)

        Returns:
            Tuple[can_continue, intervention_action]
            - can_continue: True если можно продолжать диалог
            - intervention_action: None или уровень fallback
        """
        # Инициализация времени старта
        if self._state.start_time is None:
            self._state.start_time = time.time()

        # Обновляем состояние
        self._state.turn_count += 1
        self._state.state_history.append(state)
        self._state.message_history.append(self._normalize_message(message))
        self._state.phase_attempts[state] += 1

        # Обновляем frustration если передан
        if frustration_level is not None:
            self._state.frustration_level = frustration_level

        # BUG-001 FIX: Record intent history for informative response detection
        if last_intent:
            self._state.intent_history.append(last_intent)
            self._state.last_intent = last_intent

        # Проверки в порядке критичности

        # 1. Проверка timeout
        elapsed = time.time() - self._state.start_time
        if elapsed > self.config.timeout_seconds:
            logger.warning(
                "Conversation timeout",
                turns=self._state.turn_count,
                elapsed_seconds=int(elapsed)
            )
            return False, self.TIER_4

        # 2. Проверка max turns
        if self._state.turn_count > self.config.max_turns:
            logger.warning(
                "Max turns exceeded",
                turns=self._state.turn_count,
                limit=self.config.max_turns
            )
            return False, self.TIER_4

        # 3. Проверка высокого раздражения ИЛИ pre_intervention_triggered
        # Pre-intervention срабатывает при WARNING уровне (5-6) с определёнными условиями
        # (RUSHED tone, multiple frustration signals), поэтому нужно проверять оба флага
        if (self._state.frustration_level >= self.config.high_frustration_threshold
                or pre_intervention_triggered):
            # If client is engaged (asking questions, objecting, providing data),
            # offer structured options (TIER_2) instead of skipping phase (TIER_3).
            # The client may be frustrated BECAUSE their question wasn't answered —
            # skipping the phase makes it worse. TIER_2 gives them structured choices,
            # and policy layer can still override to answer directly.
            if self._is_engagement_intent():
                logger.info(
                    "High frustration but client is engaged — TIER_2 instead of TIER_3",
                    frustration_level=self._state.frustration_level,
                    last_intent=self._state.last_intent,
                )
                return True, self.TIER_2

            logger.warning(
                "High frustration or pre-intervention triggered",
                frustration_level=self._state.frustration_level,
                pre_intervention=pre_intervention_triggered,
                turns=self._state.turn_count
            )
            # Не прерываем, но рекомендуем мягкий подход
            return True, self.TIER_3

        # 4. Проверка повторяющихся сообщений (exact loop)
        if self._check_message_loop():
            logger.warning(
                "Message loop detected",
                user_message=message[:50],
                turns=self._state.turn_count
            )
            return True, self.TIER_2  # Предложить варианты

        # 5. Проверка застревания в состоянии (с учётом информативности)
        same_state_count = self._count_recent_same_state(state)
        if same_state_count >= self.config.max_same_state:
            # BUG-001 FIX: Проверяем был ли последний intent информативным
            if self._is_engagement_intent():
                logger.debug(
                    "State loop threshold reached but client is providing info - not triggering",
                    state=state,
                    count=same_state_count,
                    last_intent=self._state.last_intent
                )
                # Не возвращаем TIER_3, даём диалогу продолжиться
            else:
                logger.warning(
                    "State loop detected",
                    state=state,
                    count=same_state_count
                )
                return True, self.TIER_3  # Предложить skip

        # 6. Phase exhaustion — REMOVED: Now handled by PhaseExhaustedSource
        # inside the Blackboard pipeline (Principle 3.2: Blackboard Pipeline Authority).
        # See src/blackboard/sources/phase_exhausted.py

        # Обновляем счётчик собранных данных
        self._state.collected_data_count = len(collected_data)

        # 7. Проверка общего прогресса
        turns_since_progress = self._state.turn_count - self._state.last_progress_turn
        if turns_since_progress >= self.config.progress_check_interval:
            if not self._has_progress():
                logger.warning(
                    "No progress detected",
                    turns_since_progress=turns_since_progress
                )
                return True, self.TIER_1

        return True, None

    def _apply_tier_2_escalation(
        self, state: str, tier: str
    ) -> str:
        """
        Track consecutive TIER_2 in same state and escalate to TIER_3 if threshold reached.

        Moved from FallbackHandler to keep detection logic co-located with detection state.
        """
        if tier == self.TIER_2:
            if self._state.consecutive_tier_2_state == state:
                self._state.consecutive_tier_2_count += 1
            else:
                self._state.consecutive_tier_2_count = 1
                self._state.consecutive_tier_2_state = state

            if self._state.consecutive_tier_2_count >= self.config.max_consecutive_tier_2:
                self._state.consecutive_tier_2_count = 0
                logger.info(
                    "TIER_2 self-loop escalation to TIER_3",
                    state=state,
                    threshold=self.config.max_consecutive_tier_2,
                )
                return self.TIER_3
        else:
            self._state.consecutive_tier_2_count = 0
            self._state.consecutive_tier_2_state = None

        return tier

    def record_progress(self) -> None:
        """
        Отметить что был прогресс в диалоге.
        Вызывается когда собраны новые данные или сменилось состояние.
        """
        self._state.last_progress_turn = self._state.turn_count
        logger.debug(
            "Progress recorded",
            turn=self._state.turn_count
        )

    def _normalize_message(self, message: str) -> str:
        """Нормализация сообщения для сравнения"""
        return message.lower().strip()

    def _check_message_loop(self) -> bool:
        """Проверка на повторяющиеся сообщения клиента"""
        history = self._state.message_history
        if len(history) < self.config.max_same_message:
            return False

        # Проверяем последние N сообщений на идентичность
        recent = history[-self.config.max_same_message:]
        return len(set(recent)) == 1

    def _count_recent_same_state(self, state: str) -> int:
        """Считаем последние подряд идущие одинаковые состояния"""
        count = 0
        for s in reversed(self._state.state_history):
            if s == state:
                count += 1
            else:
                break
        return count

    def _has_progress(self) -> bool:
        """Проверка есть ли прогресс по состояниям"""
        if len(self._state.state_history) < 2:
            return True

        # Берём последние N состояний
        interval = self.config.progress_check_interval
        recent_states = self._state.state_history[-interval:]
        unique_recent = len(set(recent_states))

        return unique_recent >= self.config.min_unique_states_for_progress

    # Blacklist: intents indicating client is NOT progressing
    STUCK_INTENTS = frozenset({"unclear"})

    def _is_engagement_intent(self) -> bool:
        """
        Inverted stuck-detection: any classifiable intent except 'unclear'
        indicates the client is actively engaged (asking questions, providing
        data, raising objections, etc.) — NOT stuck in a loop.

        This is fundamentally more robust than a whitelist of informative
        intents: new intents added to the system are automatically treated
        as engagement without manual updates.
        """
        if not self._state.last_intent:
            return False
        return self._state.last_intent not in self.STUCK_INTENTS

    def get_stats(self) -> Dict:
        """Получить статистику диалога"""
        elapsed = 0.0
        if self._state.start_time:
            elapsed = time.time() - self._state.start_time

        return {
            "turn_count": self._state.turn_count,
            "elapsed_seconds": round(elapsed, 1),
            "phase_attempts": dict(self._state.phase_attempts),
            "unique_states": len(set(self._state.state_history)),
            "last_state": self._state.state_history[-1] if self._state.state_history else None,
            "frustration_level": self._state.frustration_level,
            "collected_data_count": self._state.collected_data_count,
        }


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("CONVERSATION GUARD DEMO")
    print("=" * 60)

    guard = ConversationGuard()

    # Симулируем диалог
    test_cases = [
        ("greeting", "Привет", {}),
        ("spin_situation", "10 человек", {"company_size": 10}),
        ("spin_problem", "Теряем клиентов", {"company_size": 10, "problem": "churn"}),
        ("spin_problem", "Теряем клиентов", {"company_size": 10, "problem": "churn"}),  # Repeat
        ("spin_problem", "Теряем клиентов", {"company_size": 10, "problem": "churn"}),  # Repeat again
    ]

    print("\n--- Simulating conversation ---")
    for state, message, data in test_cases:
        can_continue, intervention = guard.check(state, message, data)
        status = "OK" if can_continue else "STOP"
        intervention_str = intervention or "none"
        print(f"Turn {guard.turn_count}: state={state}, {status}, intervention={intervention_str}")

    print("\n--- Guard Stats ---")
    print(json.dumps(guard.get_stats(), indent=2, ensure_ascii=False))

    # Тест timeout
    print("\n--- Testing timeout detection ---")
    guard2 = ConversationGuard(GuardConfig(timeout_seconds=0))  # Immediate timeout
    time.sleep(0.1)
    can_continue, intervention = guard2.check("test", "test", {})
    print(f"Timeout test: can_continue={can_continue}, intervention={intervention}")

    print("\n" + "=" * 60)
