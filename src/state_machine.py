"""
State Machine — управление состояниями диалога

Поддерживает:
- SPIN Selling flow: greeting → spin_situation → spin_problem → spin_implication → spin_need_payoff → presentation → close
- Обработка возражений: handle_objection
- Финальные состояния: success, soft_close
- Circular Flow: возврат назад по фазам (с защитой от злоупотреблений)
"""

from typing import Tuple, Dict, Optional, List
from config import SALES_STATES, QUESTION_INTENTS, DISAMBIGUATION_CONFIG
from logger import logger


# SPIN-фазы и их порядок
SPIN_PHASES = ["situation", "problem", "implication", "need_payoff"]

# Состояния SPIN
SPIN_STATES = {
    "situation": "spin_situation",
    "problem": "spin_problem",
    "implication": "spin_implication",
    "need_payoff": "spin_need_payoff",
}

# SPIN-интенты которые указывают на прогресс в соответствующей фазе
SPIN_PROGRESS_INTENTS = {
    "situation_provided": "situation",
    "problem_revealed": "problem",
    "implication_acknowledged": "implication",
    "need_expressed": "need_payoff",
}

# Интенты для возврата назад
GO_BACK_INTENTS = ["go_back", "correct_info"]

# Интенты возражений
OBJECTION_INTENTS = [
    "objection_price",
    "objection_competitor",
    "objection_no_time",
    "objection_think",
]


class ObjectionFlowManager:
    """
    Управление возражениями с защитой от зацикливания.

    Ограничивает количество последовательных возражений,
    после которых переходим в soft_close.

    Attributes:
        objection_count: Количество возражений в текущей серии
        total_objections: Общее количество возражений за диалог
        objection_history: История возражений (тип, состояние)
        MAX_CONSECUTIVE_OBJECTIONS: Максимум последовательных возражений
        MAX_TOTAL_OBJECTIONS: Максимум возражений за диалог
    """

    MAX_CONSECUTIVE_OBJECTIONS = 3  # Максимум подряд
    MAX_TOTAL_OBJECTIONS = 5        # Максимум за весь диалог

    def __init__(self):
        """Инициализация менеджера"""
        self.reset()

    def reset(self) -> None:
        """Сброс для нового разговора"""
        self.objection_count: int = 0
        self.total_objections: int = 0
        self.objection_history: List[tuple] = []
        self.last_state_before_objection: Optional[str] = None

    def record_objection(self, objection_type: str, state: str) -> None:
        """
        Записать возражение.

        Args:
            objection_type: Тип возражения (objection_price, etc.)
            state: Состояние в котором было возражение
        """
        self.objection_count += 1
        self.total_objections += 1
        self.objection_history.append((objection_type, state))

        if self.last_state_before_objection is None:
            self.last_state_before_objection = state

        logger.info(
            "Objection recorded",
            type=objection_type,
            consecutive=self.objection_count,
            total=self.total_objections
        )

    def reset_consecutive(self) -> None:
        """Сбросить счётчик последовательных возражений (при положительном интенте)"""
        self.objection_count = 0
        self.last_state_before_objection = None

    def should_soft_close(self) -> bool:
        """
        Проверить нужно ли мягко закрывать диалог.

        Returns:
            True если превышен лимит возражений
        """
        if self.objection_count >= self.MAX_CONSECUTIVE_OBJECTIONS:
            logger.info(
                "Consecutive objection limit reached",
                count=self.objection_count,
                limit=self.MAX_CONSECUTIVE_OBJECTIONS
            )
            return True

        if self.total_objections >= self.MAX_TOTAL_OBJECTIONS:
            logger.info(
                "Total objection limit reached",
                total=self.total_objections,
                limit=self.MAX_TOTAL_OBJECTIONS
            )
            return True

        return False

    def get_return_state(self) -> Optional[str]:
        """
        Получить состояние для возврата после успешной отработки возражения.

        Returns:
            Состояние до начала возражений или None
        """
        return self.last_state_before_objection

    def get_stats(self) -> Dict:
        """Получить статистику для аналитики"""
        return {
            "consecutive_objections": self.objection_count,
            "total_objections": self.total_objections,
            "history": self.objection_history,
            "return_state": self.last_state_before_objection,
        }


class CircularFlowManager:
    """
    Управление возвратами назад с защитой от злоупотреблений.

    Позволяет клиенту вернуться к предыдущей фазе SPIN,
    но ограничивает количество возвратов для предотвращения зацикливания.

    Attributes:
        goback_count: Количество совершённых возвратов
        goback_history: История возвратов (from_state, to_state)
        MAX_GOBACKS: Максимально допустимое количество возвратов
    """

    MAX_GOBACKS = 2  # Максимум возвратов за диалог

    # Разрешённые переходы назад
    ALLOWED_GOBACKS: Dict[str, str] = {
        "spin_problem": "spin_situation",
        "spin_implication": "spin_problem",
        "spin_need_payoff": "spin_implication",
        "presentation": "spin_need_payoff",
        "close": "presentation",
        "handle_objection": "presentation",
        # Из soft_close можно вернуться в greeting для новой попытки
        "soft_close": "greeting",
    }

    def __init__(self):
        """Инициализация менеджера"""
        self.reset()

    def reset(self) -> None:
        """Сброс для нового разговора"""
        self.goback_count: int = 0
        self.goback_history: List[tuple] = []

    def can_go_back(self, current_state: str) -> bool:
        """
        Проверить можно ли вернуться назад.

        Args:
            current_state: Текущее состояние

        Returns:
            True если возврат возможен
        """
        if self.goback_count >= self.MAX_GOBACKS:
            logger.info(
                "Go back limit reached",
                current=current_state,
                count=self.goback_count
            )
            return False

        return current_state in self.ALLOWED_GOBACKS

    def go_back(self, current_state: str) -> Optional[str]:
        """
        Выполнить возврат назад.

        Args:
            current_state: Текущее состояние

        Returns:
            Предыдущее состояние или None если возврат невозможен
        """
        if not self.can_go_back(current_state):
            return None

        prev_state = self.ALLOWED_GOBACKS.get(current_state)
        if prev_state:
            self.goback_count += 1
            self.goback_history.append((current_state, prev_state))
            logger.info(
                "Go back executed",
                from_state=current_state,
                to_state=prev_state,
                remaining=self.MAX_GOBACKS - self.goback_count
            )

        return prev_state

    def get_remaining_gobacks(self) -> int:
        """Получить оставшееся количество возвратов"""
        return max(0, self.MAX_GOBACKS - self.goback_count)

    def get_history(self) -> List[tuple]:
        """Получить историю возвратов"""
        return self.goback_history.copy()

    def get_stats(self) -> Dict:
        """Получить статистику для аналитики"""
        return {
            "goback_count": self.goback_count,
            "remaining": self.get_remaining_gobacks(),
            "history": self.goback_history,
        }


class StateMachine:
    def __init__(self):
        self.state = "greeting"
        self.collected_data = {}
        self.spin_phase = None  # Текущая SPIN-фаза (если в SPIN flow)
        self.circular_flow = CircularFlowManager()  # Менеджер возвратов
        self.objection_flow = ObjectionFlowManager()  # Менеджер возражений

        # Disambiguation state
        self.in_disambiguation: bool = False
        self.disambiguation_context: Optional[Dict] = None
        self.pre_disambiguation_state: Optional[str] = None
        self.turns_since_last_disambiguation: int = 999  # Большое число = давно не было

        # Для контекстной классификации
        self.last_action: Optional[str] = None
        self.last_intent: Optional[str] = None

    def reset(self):
        self.state = "greeting"
        self.collected_data = {}
        self.spin_phase = None
        self.circular_flow.reset()
        self.objection_flow.reset()

        # Reset disambiguation state
        self.in_disambiguation = False
        self.disambiguation_context = None
        self.pre_disambiguation_state = None
        self.turns_since_last_disambiguation = 999

        self.last_action = None
        self.last_intent = None

    def update_data(self, data: Dict):
        """Сохраняем извлечённые данные"""
        for key, value in data.items():
            if value:
                self.collected_data[key] = value

    # =========================================================================
    # Disambiguation Methods
    # =========================================================================

    def increment_turn(self) -> None:
        """
        Вызывать в начале каждого process() для отслеживания cooldown.
        """
        if self.turns_since_last_disambiguation < 999:
            self.turns_since_last_disambiguation += 1

    def enter_disambiguation(
        self,
        options: List[Dict],
        extracted_data: Optional[Dict] = None
    ) -> None:
        """
        Войти в режим disambiguation.

        Args:
            options: Список вариантов для пользователя
            extracted_data: Извлечённые данные для сохранения
        """
        self.pre_disambiguation_state = self.state
        self.in_disambiguation = True
        self.disambiguation_context = {
            "options": options,
            "original_state": self.state,
            "extracted_data": extracted_data or {},
            "attempt": 1,
        }

    def resolve_disambiguation(self, resolved_intent: str) -> Tuple[str, str]:
        """
        Разрешить disambiguation с выбранным интентом.

        Args:
            resolved_intent: Выбранный пользователем интент

        Returns:
            Tuple[current_state, resolved_intent]
        """
        current_state = self.state
        self._exit_disambiguation_internal()
        return current_state, resolved_intent

    def exit_disambiguation(self) -> None:
        """Выйти из режима disambiguation без разрешения."""
        self._exit_disambiguation_internal()

    def _exit_disambiguation_internal(self) -> None:
        """Внутренний метод для выхода из disambiguation."""
        self.in_disambiguation = False
        self.disambiguation_context = None
        self.pre_disambiguation_state = None
        self.turns_since_last_disambiguation = 0

    def get_context(self) -> Dict:
        """
        Получить контекст для классификатора.

        Returns:
            Dict с текущим контекстом состояния
        """
        context = {
            "state": self.state,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "spin_phase": self.spin_phase,
            "missing_data": self._get_missing_data(),
            "turns_since_last_disambiguation": self.turns_since_last_disambiguation,
        }

        if self.in_disambiguation:
            context["in_disambiguation"] = True

        return context

    def _get_missing_data(self) -> List[str]:
        """Получить список недостающих обязательных данных."""
        config = SALES_STATES.get(self.state, {})
        required = config.get("required_data", [])
        return [f for f in required if not self.collected_data.get(f)]

    # =========================================================================
    # SPIN Methods
    # =========================================================================

    def _get_current_spin_phase(self) -> Optional[str]:
        """Определяем текущую SPIN-фазу по состоянию"""
        config = SALES_STATES.get(self.state, {})
        return config.get("spin_phase")

    def _get_next_spin_state(self, current_phase: str) -> Optional[str]:
        """Определяем следующее SPIN-состояние"""
        if current_phase not in SPIN_PHASES:
            return None

        current_idx = SPIN_PHASES.index(current_phase)
        if current_idx < len(SPIN_PHASES) - 1:
            next_phase = SPIN_PHASES[current_idx + 1]
            return SPIN_STATES.get(next_phase)
        return "presentation"  # После need_payoff идёт presentation

    def _check_spin_data_complete(self, config: Dict) -> bool:
        """Проверяем собраны ли данные для текущей SPIN-фазы"""
        required = config.get("required_data", [])
        if not required:
            return True  # Если нет обязательных данных — считаем завершённой

        for field in required:
            if not self.collected_data.get(field):
                return False
        return True

    def _should_skip_spin_phase(self, phase: str) -> bool:
        """Определяем можно ли пропустить SPIN-фазу (для ускорения)"""
        # Implication и Need-Payoff можно пропустить если клиент уже готов
        if phase in ["implication", "need_payoff"]:
            # Если клиент уже выразил сильный интерес
            if self.collected_data.get("high_interest"):
                return True
            # Если уже есть желаемый результат
            if phase == "need_payoff" and self.collected_data.get("desired_outcome"):
                return True
        return False

    def _is_spin_phase_progression(self, intent_phase: str, current_phase: str) -> bool:
        """
        Проверяет, является ли intent_phase прогрессом относительно current_phase.

        Args:
            intent_phase: Фаза из интента (situation, problem, etc.)
            current_phase: Текущая SPIN-фаза

        Returns:
            True если intent_phase соответствует текущей или следующей фазе
        """
        if intent_phase not in SPIN_PHASES or current_phase not in SPIN_PHASES:
            return False

        intent_idx = SPIN_PHASES.index(intent_phase)
        current_idx = SPIN_PHASES.index(current_phase)

        return intent_idx >= current_idx

    def apply_rules(self, intent: str) -> Tuple[str, str]:
        """
        Определяем действие и следующее состояние.

        Порядок приоритетов:
        0. Финальное состояние
        1. Rejection — критический интент
        2. State-specific rules (включая deflect_and_continue для SPIN)
        3. Общий обработчик вопросов (QUESTION_INTENTS)
        4. SPIN-специфичная логика
        5. Переходы по интенту
        6. Автопереход по data_complete
        7. Автопереход по "any"
        8. Default — оставаться в текущем состоянии

        Returns:
            Tuple[str, str]: (action, next_state)
        """
        config = SALES_STATES.get(self.state, {})
        transitions = config.get("transitions", {})
        rules = config.get("rules", {})
        spin_phase = self._get_current_spin_phase()

        # =====================================================================
        # ПРИОРИТЕТ 0: Финальное состояние
        # =====================================================================
        if config.get("is_final"):
            return "final", self.state

        # =====================================================================
        # ПРИОРИТЕТ 1: Rejection — всегда обрабатываем немедленно
        # =====================================================================
        if intent == "rejection":
            if "rejection" in transitions:
                next_state = transitions["rejection"]
                return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 1.5: Go Back — возврат назад по фазам
        # =====================================================================
        if intent in GO_BACK_INTENTS:
            prev_state = self.circular_flow.go_back(self.state)
            if prev_state:
                return "go_back", prev_state
            # Если возврат невозможен — продолжаем обычную обработку

        # =====================================================================
        # ПРИОРИТЕТ 1.7: Возражения с защитой от зацикливания
        # =====================================================================
        if intent in OBJECTION_INTENTS:
            # Записываем возражение
            self.objection_flow.record_objection(intent, self.state)

            # Проверяем лимит возражений
            if self.objection_flow.should_soft_close():
                return "objection_limit_reached", "soft_close"

            # Иначе обрабатываем через transitions (handle_objection или soft_close)
            if intent in transitions:
                next_state = transitions[intent]
                return f"transition_to_{next_state}", next_state

        # Сбрасываем счётчик последовательных возражений при положительных интентах
        # Полный список включает:
        # - Явное согласие и запросы: agreement, demo_request, callback_request, contact_provided
        # - SPIN-прогресс: situation_provided, problem_revealed, implication_acknowledged, need_expressed
        # - Информационные: info_provided, consultation_request
        # - Вопросы (показывают интерес): question_features, question_integrations, price_question, comparison
        POSITIVE_INTENTS = {
            # Явное согласие и запросы
            "agreement", "demo_request", "callback_request", "contact_provided",
            "consultation_request",
            # SPIN-прогресс (клиент даёт информацию = прогресс)
            "situation_provided", "problem_revealed", "implication_acknowledged",
            "need_expressed", "info_provided",
            # Вопросы показывают интерес (хотя слабее чем agreement)
            "question_features", "question_integrations", "comparison",
            # Благодарность и приветствие тоже не должны считаться возражениями
            "greeting", "gratitude",
        }
        if intent in POSITIVE_INTENTS:
            self.objection_flow.reset_consecutive()

        # =====================================================================
        # ПРИОРИТЕТ 2: State-specific rules
        # Позволяет состояниям переопределять поведение для конкретных интентов,
        # например deflect_and_continue для вопросов о цене в SPIN-фазах
        # =====================================================================
        if intent in rules:
            return rules[intent], self.state

        # =====================================================================
        # ПРИОРИТЕТ 3: Общий обработчик вопросов
        # Если клиент задаёт вопрос — сначала отвечаем, потом продолжаем
        # =====================================================================
        if intent in QUESTION_INTENTS:
            next_state = transitions.get(intent, self.state)
            return "answer_question", next_state

        # =====================================================================
        # ПРИОРИТЕТ 4: SPIN-специфичная логика
        # =====================================================================
        if spin_phase:
            if intent in SPIN_PROGRESS_INTENTS:
                intent_phase = SPIN_PROGRESS_INTENTS[intent]
                if self._is_spin_phase_progression(intent_phase, spin_phase):
                    if intent in transitions:
                        next_state = transitions[intent]
                        return f"transition_to_{next_state}", next_state

            # Автопереход по data_complete только если:
            # 1. Данные собраны
            # 2. Интент НЕ определён явно в transitions (no_need, no_problem и т.д.)
            # Это позволяет явным интентам иметь приоритет над автопереходом
            if intent not in transitions and self._check_spin_data_complete(config):
                if "data_complete" in transitions:
                    next_state = transitions["data_complete"]
                    next_config = SALES_STATES.get(next_state, {})
                    next_phase = next_config.get("spin_phase")
                    if next_phase and self._should_skip_spin_phase(next_phase):
                        skip_transitions = next_config.get("transitions", {})
                        if "data_complete" in skip_transitions:
                            next_state = skip_transitions["data_complete"]
                    return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 5: Переходы по интенту
        # =====================================================================
        if intent in transitions:
            next_state = transitions[intent]
            return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 6: Проверка data_complete для non-SPIN состояний
        # =====================================================================
        required = config.get("required_data", [])
        if required:
            missing = [f for f in required if not self.collected_data.get(f)]
            if not missing and "data_complete" in transitions:
                next_state = transitions["data_complete"]
                return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 7: Автопереход (для greeting)
        # =====================================================================
        if "any" in transitions:
            next_state = transitions["any"]
            return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 8: Default — остаёмся в текущем состоянии
        # =====================================================================
        # Всегда возвращаем валидный action, а не имя состояния
        # generator.py использует spin_phase из контекста для выбора нужного шаблона
        return "continue_current_goal", self.state

    def process(self, intent: str, extracted_data: Dict = None) -> Dict:
        """Обработать интент, вернуть результат"""
        prev_state = self.state

        if extracted_data:
            self.update_data(extracted_data)

        action, next_state = self.apply_rules(intent)
        self.state = next_state

        # Обновляем spin_phase
        self.spin_phase = self._get_current_spin_phase()

        # Устанавливаем phase-флаги при ВХОДЕ в соответствующие SPIN-фазы
        # Эти флаги означают: "мы вошли в эту фазу и бот задаст вопрос"
        # Используются для:
        # 1. Предотвращения пропуска фазы при первом неясном ответе
        # 2. Определения data_complete (required_data в config.py)
        # 3. Отслеживания прогресса через SPIN для аналитики
        # NOTE: Название "_probed" историческое, семантически означает "phase_entered"
        if next_state == "spin_implication" and prev_state != "spin_implication":
            self.collected_data["implication_probed"] = True  # = implication_phase_entered
        if next_state == "spin_need_payoff" and prev_state != "spin_need_payoff":
            self.collected_data["need_payoff_probed"] = True  # = need_payoff_phase_entered

        config = SALES_STATES.get(self.state, {})
        required = config.get("required_data", [])
        missing = [f for f in required if not self.collected_data.get(f)]

        # Собираем optional данные для SPIN
        optional = config.get("optional_data", [])
        optional_missing = [f for f in optional if not self.collected_data.get(f)]

        return {
            "action": action,
            "prev_state": prev_state,
            "next_state": next_state,
            "goal": config.get("goal", ""),
            "collected_data": self.collected_data.copy(),
            "missing_data": missing,
            "optional_data": optional_missing,
            "is_final": config.get("is_final", False),
            "spin_phase": self.spin_phase,
            "circular_flow": self.circular_flow.get_stats(),
            "objection_flow": self.objection_flow.get_stats(),
        }


if __name__ == "__main__":
    sm = StateMachine()
    
    # Тест
    print("=== Тест State Machine ===\n")
    
    tests = [
        ("greeting", {}),
        ("price_question", {}),
        ("info_provided", {"company_size": 15}),
        ("info_provided", {"pain_point": "теряем клиентов"}),
        ("agreement", {}),
    ]
    
    for intent, data in tests:
        result = sm.process(intent, data)
        print(f"Intent: {intent}")
        print(f"  {result['prev_state']} → {result['next_state']}")
        print(f"  Action: {result['action']}")
        print(f"  Data: {result['collected_data']}\n")