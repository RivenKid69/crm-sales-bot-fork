"""
Lead Scoring для CRM Sales Bot.

Скоринг лидов для адаптивного SPIN flow.
Позволяет ускорить диалог для "горячих" лидов.

ВАЖНО: Пороги требуют калибровки на реальных данных!
Начальные значения консервативные.

Использование:
    from lead_scoring import LeadScorer, LeadTemperature

    scorer = LeadScorer()
    scorer.add_signal("demo_request")
    score = scorer.get_score()

    if score.temperature == LeadTemperature.HOT:
        # Skip некоторые SPIN-фазы
        pass
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from src.config_loader import LoadedConfig

from logger import logger


class LeadTemperature(Enum):
    """
    Температура лида определяет путь через SPIN.

    COLD: Полный SPIN (S → P → I → N → presentation)
    WARM: Сокращённый SPIN (S → P → presentation, skip I, N)
    HOT: Прямой путь (S → presentation)
    VERY_HOT: Максимально прямой (presentation → close)
    """
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    VERY_HOT = "very_hot"


class LeadSignal(Enum):
    """
    Сигналы для скоринга лидов.

    Разделены на категории по силе влияния.
    """
    # Высокий интент (25-30 баллов)
    DEMO_REQUEST = "demo_request"
    PRICE_WITH_SIZE = "price_with_size"
    CALLBACK_REQUEST = "callback_request"
    CONSULTATION_REQUEST = "consultation_request"
    CONTACT_PROVIDED = "contact_provided"

    # Средний интент (10-20 баллов)
    EXPLICIT_PROBLEM = "explicit_problem"
    COMPETITOR_COMPARISON = "competitor_comparison"
    BUDGET_MENTIONED = "budget_mentioned"
    TIMELINE_MENTIONED = "timeline_mentioned"
    MULTIPLE_QUESTIONS = "multiple_questions"

    # Низкий интент (3-8 баллов)
    FEATURES_QUESTION = "features_question"
    INTEGRATIONS_QUESTION = "integrations_question"
    GENERAL_INTEREST = "general_interest"
    PRICE_QUESTION = "price_question"

    # Негативные сигналы (снижают score)
    OBJECTION_PRICE = "objection_price"
    OBJECTION_COMPETITOR = "objection_competitor"
    OBJECTION_NO_TIME = "objection_no_time"
    OBJECTION_THINK = "objection_think"
    OBJECTION_NO_NEED = "objection_no_need"
    UNCLEAR_REPEATED = "unclear_repeated"
    REJECTION_SOFT = "rejection_soft"
    FRUSTRATION = "frustration"


@dataclass
class LeadScore:
    """
    Результат скоринга лида.

    Attributes:
        score: Числовой score (0-100)
        temperature: Категория температуры
        signals: Последние сигналы (для отладки)
        recommended_path: Рекомендуемый путь через SPIN
        skip_phases: Какие фазы можно пропустить
    """
    score: int
    temperature: LeadTemperature
    signals: List[str]
    recommended_path: str
    skip_phases: Set[str] = field(default_factory=set)


class LeadScorer:
    """
    Скоринг лидов для адаптивного SPIN flow.

    Принципы работы:
    1. Сигналы имеют разный вес
    2. Старые сигналы "затухают" (decay)
    3. Негативные сигналы снижают score
    4. Temperature определяет путь через SPIN

    Attributes:
        current_score: Текущий score (0-100)
        signals_history: История сигналов
        decay_factor: Коэффициент затухания старых сигналов
    """

    # Веса сигналов (положительные)
    POSITIVE_WEIGHTS: Dict[str, int] = {
        # Высокий интент
        LeadSignal.DEMO_REQUEST.value: 30,
        LeadSignal.PRICE_WITH_SIZE.value: 25,
        LeadSignal.CALLBACK_REQUEST.value: 25,
        LeadSignal.CONSULTATION_REQUEST.value: 20,
        LeadSignal.CONTACT_PROVIDED.value: 35,

        # Средний интент
        LeadSignal.EXPLICIT_PROBLEM.value: 15,
        LeadSignal.COMPETITOR_COMPARISON.value: 12,
        LeadSignal.BUDGET_MENTIONED.value: 10,
        LeadSignal.TIMELINE_MENTIONED.value: 10,
        LeadSignal.MULTIPLE_QUESTIONS.value: 8,

        # Низкий интент
        LeadSignal.FEATURES_QUESTION.value: 5,
        LeadSignal.INTEGRATIONS_QUESTION.value: 5,
        LeadSignal.GENERAL_INTEREST.value: 3,
        LeadSignal.PRICE_QUESTION.value: 5,
    }

    # Веса сигналов (негативные)
    NEGATIVE_WEIGHTS: Dict[str, int] = {
        LeadSignal.OBJECTION_PRICE.value: -15,
        LeadSignal.OBJECTION_COMPETITOR.value: -10,
        LeadSignal.OBJECTION_NO_TIME.value: -20,
        LeadSignal.OBJECTION_THINK.value: -10,
        LeadSignal.OBJECTION_NO_NEED.value: -25,
        LeadSignal.UNCLEAR_REPEATED.value: -5,
        LeadSignal.REJECTION_SOFT.value: -25,
        LeadSignal.FRUSTRATION.value: -15,
    }

    # Пороги температуры (КОНСЕРВАТИВНЫЕ - требуют калибровки)
    THRESHOLDS: Dict[LeadTemperature, tuple] = {
        LeadTemperature.COLD: (0, 29),
        LeadTemperature.WARM: (30, 49),
        LeadTemperature.HOT: (50, 69),
        LeadTemperature.VERY_HOT: (70, 100),
    }

    # Рекомендуемые пути по температуре
    PATHS: Dict[LeadTemperature, str] = {
        LeadTemperature.COLD: "full_spin",           # S → P → I → N → presentation
        LeadTemperature.WARM: "short_spin",          # S → P → presentation (skip I, N)
        LeadTemperature.HOT: "direct_present",       # S → presentation
        LeadTemperature.VERY_HOT: "direct_close",    # presentation → close
    }

    # Фазы для пропуска по температуре (DEPRECATED: use config parameter)
    # Kept as fallback for backward compatibility
    DEFAULT_SKIP_PHASES: Dict[LeadTemperature, Set[str]] = {
        LeadTemperature.COLD: set(),
        LeadTemperature.WARM: {"spin_implication", "spin_need_payoff"},
        LeadTemperature.HOT: {"spin_problem", "spin_implication", "spin_need_payoff"},
        LeadTemperature.VERY_HOT: {"spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"},
    }
    # Backward compatibility alias
    SKIP_PHASES = DEFAULT_SKIP_PHASES

    # Максимальная длина истории сигналов
    MAX_HISTORY_LENGTH = 20

    # Default phase order for get_next_phase (DEPRECATED: use config parameter)
    # Kept as fallback for backward compatibility
    DEFAULT_PHASE_ORDER: List[str] = [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
        "presentation",
        "close"
    ]

    def __init__(
        self,
        decay_factor: float = 0.95,
        config: Optional["LoadedConfig"] = None
    ):
        """
        Инициализация скорера.

        Args:
            decay_factor: Коэффициент затухания (0.0-1.0).
                          Чем ближе к 1, тем дольше "помнятся" старые сигналы.
            config: LoadedConfig for skip_phases and phase_order. If provided,
                    reads from config.lead_scoring. Otherwise uses DEFAULT_*.
        """
        self.decay_factor = decay_factor
        self._skip_phases = self._load_skip_phases(config)
        self._phase_order = self._load_phase_order(config)
        self.reset()

    def _load_skip_phases(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[LeadTemperature, Set[str]]:
        """
        Load skip_phases from config or use defaults.

        Args:
            config: LoadedConfig with lead_scoring.skip_phases

        Returns:
            Dict mapping temperature -> set of phases to skip
        """
        if config is None:
            return self.DEFAULT_SKIP_PHASES

        # Try to get from config.lead_scoring.skip_phases
        skip_phases_config = config.lead_scoring.get("skip_phases", {})
        if not skip_phases_config:
            return self.DEFAULT_SKIP_PHASES

        # Convert config format (str keys) to LeadTemperature keys
        result: Dict[LeadTemperature, Set[str]] = {}
        temp_map = {
            "cold": LeadTemperature.COLD,
            "warm": LeadTemperature.WARM,
            "hot": LeadTemperature.HOT,
            "very_hot": LeadTemperature.VERY_HOT,
        }
        for temp_str, phases in skip_phases_config.items():
            temp_key = temp_map.get(temp_str.lower())
            if temp_key:
                result[temp_key] = set(phases) if phases else set()

        # Fill in any missing temperatures with defaults
        for temp in LeadTemperature:
            if temp not in result:
                result[temp] = self.DEFAULT_SKIP_PHASES.get(temp, set())

        return result

    def _load_phase_order(self, config: Optional["LoadedConfig"]) -> List[str]:
        """
        Load phase order from config or use defaults.

        Args:
            config: LoadedConfig with context.state_order or lead_scoring.phase_order

        Returns:
            List of phase names in order

        Priority:
            1. context.state_order (dict with numeric ordering)
            2. lead_scoring.phase_order (explicit list)
            3. DEFAULT_PHASE_ORDER (fallback)
        """
        if config is None:
            return self.DEFAULT_PHASE_ORDER

        # Try context.state_order first (extract ordered keys)
        state_order = config.context.get("state_order", {})
        if state_order:
            # Filter to only include valid phases and sort by order
            valid_phases = {
                "spin_situation", "spin_problem", "spin_implication",
                "spin_need_payoff", "presentation", "close"
            }
            ordered = [
                (phase, order) for phase, order in state_order.items()
                if phase in valid_phases
            ]
            ordered.sort(key=lambda x: x[1])
            if ordered:
                return [phase for phase, _ in ordered]

        # Try lead_scoring.phase_order as alternative (explicit list)
        phase_order = config.lead_scoring.get("phase_order")
        if phase_order and isinstance(phase_order, list):
            return phase_order

        return self.DEFAULT_PHASE_ORDER

    def reset(self) -> None:
        """Сброс скорера для нового разговора"""
        self.current_score: int = 0
        self.signals_history: List[str] = []
        self._raw_score: float = 0.0  # Для точных расчётов с decay
        self._turn_count: int = 0  # Счётчик ходов для turn-based decay
        self._decay_applied_this_turn: bool = False  # Флаг для предотвращения двойного decay

    def apply_turn_decay(self) -> None:
        """
        Применить decay к score на основе хода.

        Вызывается при каждом ходе диалога, независимо от наличия сигналов.
        Это обеспечивает "затухание" старых сигналов со временем.
        """
        if self._decay_applied_this_turn:
            return  # Уже применили decay в этом ходу

        self._turn_count += 1
        old_score = self._raw_score

        # Применяем decay
        self._raw_score *= self.decay_factor
        self._raw_score = max(0.0, min(100.0, self._raw_score))
        self.current_score = int(self._raw_score)

        self._decay_applied_this_turn = True

        if old_score != self._raw_score:
            logger.debug(
                "Lead score decay applied",
                turn=self._turn_count,
                old_score=round(old_score, 2),
                new_score=self.current_score
            )

    def end_turn(self) -> None:
        """
        Завершить ход и сбросить флаг decay.

        Вызывается в конце обработки каждого хода.
        """
        self._decay_applied_this_turn = False

    def add_signal(self, signal: str) -> LeadScore:
        """
        Добавить сигнал и пересчитать score.

        NOTE: Decay теперь применяется через apply_turn_decay() в начале хода,
        а не при добавлении сигнала. Это обеспечивает корректный decay
        даже когда нет новых сигналов.

        Args:
            signal: Имя сигнала (из LeadSignal или строка)

        Returns:
            LeadScore: Обновлённый результат скоринга
        """
        # Убеждаемся что decay применён в этом ходу
        if not self._decay_applied_this_turn:
            self.apply_turn_decay()

        # Получаем вес сигнала
        weight = self.POSITIVE_WEIGHTS.get(signal, 0)
        if weight == 0:
            weight = self.NEGATIVE_WEIGHTS.get(signal, 0)

        if weight != 0:
            # Обновляем raw score
            self._raw_score += weight

            # Ограничиваем диапазон 0-100
            self._raw_score = max(0.0, min(100.0, self._raw_score))
            self.current_score = int(self._raw_score)

            # Добавляем в историю
            self.signals_history.append(signal)

            # Ограничиваем длину истории
            if len(self.signals_history) > self.MAX_HISTORY_LENGTH:
                self.signals_history = self.signals_history[-self.MAX_HISTORY_LENGTH:]

            logger.info(
                "Lead score updated",
                signal=signal,
                weight=weight,
                new_score=self.current_score
            )

        return self.get_score()

    def add_signals(self, signals: List[str]) -> LeadScore:
        """
        Добавить несколько сигналов за раз.

        Args:
            signals: Список сигналов

        Returns:
            LeadScore: Обновлённый результат скоринга
        """
        for signal in signals:
            self.add_signal(signal)
        return self.get_score()

    def get_score(self) -> LeadScore:
        """
        Получить текущий результат скоринга.

        Returns:
            LeadScore: Текущий результат
        """
        temperature = self._get_temperature()

        return LeadScore(
            score=self.current_score,
            temperature=temperature,
            signals=self.signals_history[-5:],  # Последние 5 сигналов
            recommended_path=self.PATHS[temperature],
            skip_phases=self._skip_phases[temperature].copy()
        )

    def _get_temperature(self) -> LeadTemperature:
        """Определить температуру по текущему score"""
        for temp, (low, high) in self.THRESHOLDS.items():
            if low <= self.current_score <= high:
                return temp
        return LeadTemperature.COLD

    def should_skip_phase(self, phase: str) -> bool:
        """
        Проверить можно ли пропустить фазу.

        Args:
            phase: Название фазы (spin_situation, spin_problem, etc.)

        Returns:
            True если фазу можно пропустить
        """
        score = self.get_score()
        return phase in score.skip_phases

    def get_next_phase(self, current_phase: str) -> Optional[str]:
        """
        Получить следующую фазу с учётом пропусков.

        Args:
            current_phase: Текущая фаза

        Returns:
            Следующая фаза или None
        """
        try:
            current_idx = self._phase_order.index(current_phase)
        except ValueError:
            return None

        score = self.get_score()

        # Ищем следующую фазу, которую не нужно пропускать
        for next_phase in self._phase_order[current_idx + 1:]:
            if next_phase not in score.skip_phases:
                return next_phase

        return None

    def is_ready_for_close(self) -> bool:
        """Проверить готов ли лид к закрытию"""
        return self.current_score >= self.THRESHOLDS[LeadTemperature.VERY_HOT][0]

    def get_summary(self) -> Dict:
        """
        Получить сводку для аналитики.

        Returns:
            Dict с данными для аналитики
        """
        score = self.get_score()
        return {
            "score": score.score,
            "temperature": score.temperature.value,
            "signals_count": len(self.signals_history),
            "recent_signals": score.signals,
            "recommended_path": score.recommended_path,
            "skip_phases": list(score.skip_phases),
        }


# =============================================================================
# Интеграция с интентами
# =============================================================================

# Маппинг интентов на сигналы скоринга
INTENT_TO_SIGNAL: Dict[str, str] = {
    # Высокий интент
    "demo_request": LeadSignal.DEMO_REQUEST.value,
    "callback_request": LeadSignal.CALLBACK_REQUEST.value,
    "consultation_request": LeadSignal.CONSULTATION_REQUEST.value,
    "contact_provided": LeadSignal.CONTACT_PROVIDED.value,

    # Средний интент
    "problem_revealed": LeadSignal.EXPLICIT_PROBLEM.value,
    # NOTE: objection_competitor - это возражение, маппится на негативный сигнал
    # COMPETITOR_COMPARISON (+12) используется для comparison интента (сравнение без возражения)
    "comparison": LeadSignal.COMPETITOR_COMPARISON.value,

    # Низкий интент
    "question_features": LeadSignal.FEATURES_QUESTION.value,
    "question_integrations": LeadSignal.INTEGRATIONS_QUESTION.value,
    "price_question": LeadSignal.PRICE_QUESTION.value,
    "agreement": LeadSignal.GENERAL_INTEREST.value,

    # Негативные сигналы (снижают score)
    "objection_competitor": LeadSignal.OBJECTION_COMPETITOR.value,
    "objection_price": LeadSignal.OBJECTION_PRICE.value,
    "objection_no_time": LeadSignal.OBJECTION_NO_TIME.value,
    "objection_think": LeadSignal.OBJECTION_THINK.value,
    "rejection": LeadSignal.REJECTION_SOFT.value,
    "no_need": LeadSignal.OBJECTION_NO_NEED.value,
    "no_problem": LeadSignal.OBJECTION_NO_NEED.value,  # Аналогично no_need
}


def get_signal_from_intent(intent: str) -> Optional[str]:
    """
    Получить сигнал скоринга по интенту.

    Args:
        intent: Название интента

    Returns:
        Сигнал или None если маппинг не найден
    """
    return INTENT_TO_SIGNAL.get(intent)


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LEAD SCORING DEMO")
    print("=" * 60)

    scorer = LeadScorer()

    # Симуляция диалога
    signals_sequence = [
        ("price_question", "Клиент спросил о цене"),
        ("features_question", "Клиент спросил о функциях"),
        ("explicit_problem", "Клиент озвучил проблему"),
        ("demo_request", "Клиент запросил демо"),
    ]

    for signal, description in signals_sequence:
        print(f"\n--- {description} ---")
        score = scorer.add_signal(signal)
        print(f"Signal: {signal}")
        print(f"Score: {score.score}")
        print(f"Temperature: {score.temperature.value}")
        print(f"Path: {score.recommended_path}")
        print(f"Skip phases: {score.skip_phases}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(scorer.get_summary())
