"""
State Machine — управление состояниями диалога
"""

from typing import Tuple, Dict
from config import SALES_STATES


class StateMachine:
    def __init__(self):
        self.state = "greeting"
        self.collected_data = {}
    
    def reset(self):
        self.state = "greeting"
        self.collected_data = {}
    
    def update_data(self, data: Dict):
        """Сохраняем извлечённые данные"""
        for key, value in data.items():
            if value:
                self.collected_data[key] = value
    
    def apply_rules(self, intent: str) -> Tuple[str, str]:
        """
        Определяем действие и следующее состояние
        
        Returns: (action, next_state)
        """
        config = SALES_STATES.get(self.state, {})
        
        # Финальное состояние
        if config.get("is_final"):
            return "final", self.state
        
        # Приоритет 1: Специальные правила
        rules = config.get("rules", {})
        if intent in rules:
            return rules[intent], self.state
        
        # Приоритет 2: Переходы по интенту
        transitions = config.get("transitions", {})
        if intent in transitions:
            next_state = transitions[intent]
            return f"transition_to_{next_state}", next_state
        
        # Приоритет 3: Все данные собраны?
        required = config.get("required_data", [])
        if required:
            missing = [f for f in required if not self.collected_data.get(f)]
            if not missing and "data_complete" in transitions:
                next_state = transitions["data_complete"]
                return f"transition_to_{next_state}", next_state
        
        # Приоритет 4: Автопереход (для greeting)
        if "any" in transitions:
            next_state = transitions["any"]
            return f"transition_to_{next_state}", next_state
        
        # Дефолт
        return "continue_current_goal", self.state
    
    def process(self, intent: str, extracted_data: Dict = None) -> Dict:
        """Обработать интент, вернуть результат"""
        prev_state = self.state
        
        if extracted_data:
            self.update_data(extracted_data)
        
        action, next_state = self.apply_rules(intent)
        self.state = next_state
        
        config = SALES_STATES.get(self.state, {})
        required = config.get("required_data", [])
        missing = [f for f in required if not self.collected_data.get(f)]
        
        return {
            "action": action,
            "prev_state": prev_state,
            "next_state": next_state,
            "goal": config.get("goal", ""),
            "collected_data": self.collected_data.copy(),
            "missing_data": missing,
            "is_final": config.get("is_final", False)
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