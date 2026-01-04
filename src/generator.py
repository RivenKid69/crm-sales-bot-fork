"""
Генератор ответов — собирает промпт и вызывает LLM
"""

from typing import Dict, List
from config import SYSTEM_PROMPT, PROMPT_TEMPLATES, KNOWLEDGE
from knowledge.retriever import get_retriever
from settings import settings


class ResponseGenerator:
    def __init__(self, llm):
        self.llm = llm
        # Параметры из settings
        self.max_retries = settings.generator.max_retries
        self.history_length = settings.generator.history_length
        self.retriever_top_k = settings.generator.retriever_top_k
        self.allowed_english = set(settings.generator.allowed_english_words)
    
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
        # Используем параметр из settings
        for turn in history[-self.history_length:]:
            lines.append(f"Клиент: {turn.get('user', '')}")
            if turn.get("bot"):
                lines.append(f"Вы: {turn['bot']}")
        
        return "\n".join(lines)
    
    def _has_chinese(self, text: str) -> bool:
        """Проверяем есть ли китайские/японские/корейские символы"""
        import re
        return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]', text))

    def _has_english(self, text: str) -> bool:
        """Проверяем есть ли английские слова (минимум 2 буквы подряд)"""
        import re
        # Ищем английские слова (минимум 2 латинские буквы подряд)
        # Исключаем: CRM, API, OK, ID и подобные аббревиатуры из settings

        # Находим все английские слова
        english_words = re.findall(r'\b[a-zA-Z]{2,}\b', text)

        # Проверяем есть ли недопустимые английские слова
        for word in english_words:
            if word.lower() not in self.allowed_english:
                return True
        return False

    def _has_foreign_language(self, text: str) -> bool:
        """Проверяем есть ли иностранный текст (китайский или английский)"""
        return self._has_chinese(text) or self._has_english(text)

    def generate(self, action: str, context: Dict, max_retries: int = None) -> str:
        """Генерируем ответ с retry при китайских символах"""

        # Используем параметр из settings если не указано явно
        if max_retries is None:
            max_retries = self.max_retries

        # НОВОЕ: Получаем релевантные факты из базы знаний
        retriever = get_retriever()
        intent = context.get("intent", "")
        state = context.get("state", "")
        user_message = context.get("user_message", "")

        retrieved_facts = retriever.retrieve(
            message=user_message,
            intent=intent,
            state=state,
            top_k=self.retriever_top_k
        )

        # Выбираем шаблон
        if action.startswith("transition_to_"):
            template_key = action.replace("transition_to_", "")
        else:
            template_key = action

        template = PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES["continue_current_goal"])

        # Собираем переменные
        collected = context.get("collected_data", {})
        facts = self.get_facts(collected.get("company_size"))

        # SPIN-специфичные данные
        current_tools = collected.get("current_tools", "не указано")
        business_type = collected.get("business_type", "не указано")
        pain_impact = collected.get("pain_impact", "не определено")
        financial_impact = collected.get("financial_impact", "")
        desired_outcome = collected.get("desired_outcome", "не сформулирован")
        spin_phase = context.get("spin_phase", "")

        variables = {
            "system": SYSTEM_PROMPT,
            "user_message": user_message,
            "history": self.format_history(context.get("history", [])),
            "goal": context.get("goal", ""),
            "collected_data": str(collected),
            "missing_data": ", ".join(context.get("missing_data", [])) or "всё собрано",
            "company_size": collected.get("company_size", "?"),
            "pain_point": collected.get("pain_point", "?"),
            "facts": facts,
            # База знаний
            "retrieved_facts": retrieved_facts or "Информация по этому вопросу будет уточнена.",
            "company_info": retriever.get_company_info(),
            # SPIN-специфичные данные
            "current_tools": current_tools,
            "business_type": business_type,
            "pain_impact": pain_impact,
            "financial_impact": financial_impact,
            "desired_outcome": desired_outcome,
            "spin_phase": spin_phase,
        }

        # Подставляем в шаблон
        try:
            prompt = template.format(**variables)
        except KeyError as e:
            print(f"Missing variable: {e}")
            prompt = template

        # Генерируем с retry при китайских символах
        best_response = ""
        for attempt in range(max_retries):
            response = self.llm.generate(prompt)

            # Если нет иностранного текста — сразу возвращаем
            if not self._has_foreign_language(response):
                return self._clean(response)

            # Иначе чистим и сохраняем лучший результат
            cleaned = self._clean(response)
            if len(cleaned) > len(best_response):
                best_response = cleaned

            # Добавляем усиление в промпт для следующей попытки
            if attempt == 0:
                prompt = prompt.replace(
                    "Ответ на русском",
                    "ВАЖНО: Отвечай ТОЛЬКО на русском языке, без китайских символов и английских слов!\nОтвет на русском"
                )

        # Возвращаем лучший результат из попыток
        return best_response if best_response else "Чем могу помочь?"
    
    def _clean(self, text: str) -> str:
        """Убираем лишнее и фильтруем нерусский текст"""
        import re

        text = text.strip()

        # Убираем префиксы
        for prefix in ["Ответ:", "Вы:", "Менеджер:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Удаляем китайские/японские/корейские символы и пунктуацию (Qwen иногда переключается)
        # Иероглифы + китайская пунктуация (。，！？：；「」『』【】)
        text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u3000-\u303f\uff00-\uffef]+', '', text)

        # Удаляем английские слова (кроме разрешённых из settings)
        def replace_english(match):
            word = match.group(0)
            if word.lower() in self.allowed_english:
                return word
            return ''

        text = re.sub(r'\b[a-zA-Z]{2,}\b', replace_english, text)

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