"""
State Machine — управление состояниями диалога

Поддерживает:
- Базовый flow: greeting → qualification → presentation → close
- SPIN Selling flow: greeting → spin_situation → spin_problem → spin_implication → spin_need_payoff → presentation → close
"""

from typing import Tuple, Dict, Optional
from config import SALES_STATES, QUESTION_INTENTS


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


class StateMachine:
    def __init__(self):
        self.state = "greeting"
        self.collected_data = {}
        self.spin_phase = None  # Текущая SPIN-фаза (если в SPIN flow)

    def reset(self):
        self.state = "greeting"
        self.collected_data = {}
        self.spin_phase = None

    def update_data(self, data: Dict):
        """Сохраняем извлечённые данные"""
        for key, value in data.items():
            if value:
                self.collected_data[key] = value

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
        if spin_phase:
            return self.state, self.state

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

        # Устанавливаем probed-флаги при ВХОДЕ в соответствующие SPIN-фазы
        # Это означает что бот сейчас задаст I или N вопрос
        if next_state == "spin_implication" and prev_state != "spin_implication":
            self.collected_data["implication_probed"] = True
        if next_state == "spin_need_payoff" and prev_state != "spin_need_payoff":
            self.collected_data["need_payoff_probed"] = True

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