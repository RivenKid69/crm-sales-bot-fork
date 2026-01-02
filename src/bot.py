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
    
    def reset(self):
        """Сброс для нового диалога"""
        self.state_machine.reset()
        self.history = []
    
    def process(self, user_message: str) -> Dict:
        """Обработать сообщение"""
        
        # 1. Классификация
        classification = self.classifier.classify(user_message)
        intent = classification["intent"]
        extracted = classification["extracted_data"]
        
        # 2. State Machine
        sm_result = self.state_machine.process(intent, extracted)
        
        # 3. Генерация ответа
        context = {
            "user_message": user_message,
            "history": self.history,
            "goal": sm_result["goal"],
            "collected_data": sm_result["collected_data"],
            "missing_data": sm_result["missing_data"],
        }
        
        response = self.generator.generate(sm_result["action"], context)
        
        # 4. Сохраняем в историю
        self.history.append({
            "user": user_message,
            "bot": response
        })
        
        return {
            "response": response,
            "intent": intent,
            "action": sm_result["action"],
            "state": sm_result["next_state"],
            "is_final": sm_result["is_final"]
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
            print(f"  [{result['state']}] {result['action']}\n")
            
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