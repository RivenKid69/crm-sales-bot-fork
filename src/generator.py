"""
Генератор ответов — собирает промпт и вызывает LLM
"""

from typing import Dict, List
from config import SYSTEM_PROMPT, PROMPT_TEMPLATES, KNOWLEDGE


class ResponseGenerator:
    def __init__(self, llm):
        self.llm = llm
    
    def get_facts(self, company_size: int = None) -> str:
        """Получить факты о продукте"""
        if company_size:
            # Подбираем тариф
            if company_size <= 5:
                tariff = KNOWLEDGE["pricing"]["basic"]
            elif company_size <= 25:
                tariff = KNOWLEDGE["pricing"]["team"]
            else:
                tariff = KNOWLEDGE["pricing"]["business"]
            
            total = tariff["price"] * company_size
            discount = KNOWLEDGE["discount_annual"]
            annual = total * (1 - discount / 100)
            
            return f"""Тариф: {tariff['name']}
Цена: {tariff['price']}₽/мес за человека
На {company_size} чел: {total}₽/мес
При оплате за год: {annual:.0f}₽/мес (скидка {discount}%)"""
        
        return ", ".join(KNOWLEDGE["features"])
    
    def format_history(self, history: List[Dict]) -> str:
        """Форматируем историю"""
        if not history:
            return "(начало разговора)"
        
        lines = []
        for turn in history[-4:]:
            lines.append(f"Клиент: {turn.get('user', '')}")
            if turn.get("bot"):
                lines.append(f"Вы: {turn['bot']}")
        
        return "\n".join(lines)
    
    def generate(self, action: str, context: Dict) -> str:
        """Генерируем ответ"""
        
        # Выбираем шаблон
        if action.startswith("transition_to_"):
            template_key = action.replace("transition_to_", "")
        else:
            template_key = action
        
        template = PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES["continue_current_goal"])
        
        # Собираем переменные
        collected = context.get("collected_data", {})
        facts = self.get_facts(collected.get("company_size"))
        
        variables = {
            "system": SYSTEM_PROMPT,
            "user_message": context.get("user_message", ""),
            "history": self.format_history(context.get("history", [])),
            "goal": context.get("goal", ""),
            "collected_data": str(collected),
            "missing_data": ", ".join(context.get("missing_data", [])) or "всё собрано",
            "company_size": collected.get("company_size", "?"),
            "pain_point": collected.get("pain_point", "?"),
            "facts": facts,
        }
        
        # Подставляем в шаблон
        try:
            prompt = template.format(**variables)
        except KeyError as e:
            print(f"Missing variable: {e}")
            prompt = template
        
        # Генерируем через LLM
        response = self.llm.generate(prompt)
        
        return self._clean(response)
    
    def _clean(self, text: str) -> str:
        """Убираем лишнее и фильтруем нерусский текст"""
        import re

        text = text.strip()

        # Убираем префиксы
        for prefix in ["Ответ:", "Вы:", "Менеджер:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Удаляем китайские/японские/корейские символы (Qwen иногда переключается)
        text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]+', '', text)

        # Удаляем строки начинающиеся с извинений на китайском
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # Пропускаем пустые строки и строки с "..."
            if not line or line == '...':
                continue
            # Пропускаем строки которые начинаются с китайского извинения
            if '对不起' in line or '抱歉' in line:
                continue
            cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()

        return text


if __name__ == "__main__":
    from llm import OllamaLLM
    
    llm = OllamaLLM()
    gen = ResponseGenerator(llm)
    
    print("=== Тест генератора ===\n")
    
    # Тест 1: Приветствие
    ctx1 = {"user_message": "Привет"}
    print(f"Клиент: Привет")
    print(f"Бот: {gen.generate('greeting', ctx1)}\n")
    
    # Тест 2: Deflect price
    ctx2 = {
        "user_message": "Сколько стоит?",
        "history": [{"user": "Привет", "bot": "Здравствуйте!"}],
        "goal": "Узнать размер и боль",
        "missing_data": ["company_size", "pain_point"]
    }
    print(f"Клиент: Сколько стоит?")
    print(f"Бот: {gen.generate('deflect_and_continue', ctx2)}\n")