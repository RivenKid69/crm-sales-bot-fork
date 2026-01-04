"""
Главный класс бота — объединяет все компоненты
"""

from typing import Dict, List
from classifier import HybridClassifier
from state_machine import StateMachine
from generator import ResponseGenerator


class SalesBot:
    def __init__(self, llm):
        self.classifier = HybridClassifier()
        self.state_machine = StateMachine()
        self.generator = ResponseGenerator(llm)
        self.history: List[Dict] = []
        # Контекст предыдущего хода для классификации коротких ответов
        self.last_action: str = None
        self.last_intent: str = None  # Интент пользователя, на который бот отвечал

    def reset(self):
        """Сброс для нового диалога"""
        self.state_machine.reset()
        self.history = []
        self.last_action = None
        self.last_intent = None

    def _get_classification_context(self) -> Dict:
        """Получить контекст для классификатора (включая SPIN-фазу и контекст предыдущего хода)"""
        from config import SALES_STATES

        state_config = SALES_STATES.get(self.state_machine.state, {})
        required = state_config.get("required_data", [])
        collected = self.state_machine.collected_data

        missing = [f for f in required if not collected.get(f)]

        # SPIN-фаза для контекстной классификации
        spin_phase = state_config.get("spin_phase")

        return {
            "state": self.state_machine.state,
            "collected_data": collected.copy(),
            "missing_data": missing,
            "spin_phase": spin_phase,
            # Контекст предыдущего хода для интерпретации коротких ответов
            "last_action": self.last_action,
            "last_intent": self.last_intent,
        }

    def process(self, user_message: str) -> Dict:
        """Обработать сообщение"""

        # Получаем текущий контекст для классификатора
        current_context = self._get_classification_context()

        # 1. Классификация (с контекстом для понимания коротких ответов)
        classification = self.classifier.classify(user_message, current_context)
        intent = classification["intent"]
        extracted = classification["extracted_data"]

        # 2. State Machine
        sm_result = self.state_machine.process(intent, extracted)

        # 3. Генерация ответа
        context = {
            "user_message": user_message,
            "intent": intent,  # Для retriever'а базы знаний
            "state": sm_result["next_state"],
            "history": self.history,
            "goal": sm_result["goal"],
            "collected_data": sm_result["collected_data"],
            "missing_data": sm_result["missing_data"],
            # SPIN-специфичный контекст
            "spin_phase": sm_result.get("spin_phase"),
            "optional_data": sm_result.get("optional_data", []),
        }

        response = self.generator.generate(sm_result["action"], context)

        # 4. Сохраняем в историю
        self.history.append({
            "user": user_message,
            "bot": response
        })

        # 5. Сохраняем контекст для следующего хода (классификация коротких ответов)
        self.last_action = sm_result["action"]
        self.last_intent = intent

        return {
            "response": response,
            "intent": intent,
            "action": sm_result["action"],
            "state": sm_result["next_state"],
            "is_final": sm_result["is_final"],
            "spin_phase": sm_result.get("spin_phase"),
        }


def run_interactive(bot: SalesBot):
    """Интерактивный режим"""
    print("\n" + "="*50)
    print("CRM Sales Bot")
    print("Команды: /reset /status /quit")
    print("="*50 + "\n")

    while True:
        try:
            user_input = input("Клиент: ").strip()

            if not user_input:
                continue

            if user_input == "/quit":
                break

            if user_input == "/reset":
                bot.reset()
                print("[Диалог сброшен]\n")
                continue

            if user_input == "/status":
                sm = bot.state_machine
                print(f"\nСостояние: {sm.state}")
                print(f"Данные: {sm.collected_data}\n")
                continue

            result = bot.process(user_input)

            print(f"Бот: {result['response']}")
            spin_info = f" (SPIN: {result['spin_phase']})" if result.get('spin_phase') else ""
            print(f"  [{result['state']}] {result['action']}{spin_info}\n")

            if result["is_final"]:
                print("[Диалог завершён]")
                if input("Новый диалог? (y/n): ").lower() == 'y':
                    bot.reset()
                else:
                    break

        except KeyboardInterrupt:
            print("\n\nПока!")
            break


if __name__ == "__main__":
    from llm import OllamaLLM

    llm = OllamaLLM()
    bot = SalesBot(llm)

    run_interactive(bot)
