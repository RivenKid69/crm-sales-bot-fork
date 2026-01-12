"""
LLM-агент для имитации клиента.

Использует LLM для генерации реалистичных ответов клиента
на основе персоны и истории диалога.
"""

import random
from typing import List, Dict, Any

from .personas import Persona
from .noise import add_noise, add_heavy_noise, add_light_noise


class ClientAgent:
    """LLM-агент для имитации клиента"""

    SYSTEM_PROMPT = """Ты играешь роль потенциального клиента CRM системы Wipon в Казахстане.

ПЕРСОНА: {persona_name}
{persona_description}

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Отвечай КОРОТКО - максимум 1-2 предложения (не больше 30 слов)
2. Пиши как реальный человек в мессенджере:
   - Можно без заглавных букв
   - Можно с опечатками
   - Используй разговорную речь
3. НЕ будь слишком вежливым - это подозрительно
4. НЕ используй формальные фразы типа "Благодарю за информацию"
5. Веди себя СТРОГО согласно персоне

МОЖЕШЬ:
- Отвлекаться от темы
- Задавать неожиданные вопросы
- Выражать сомнения
- Торопиться или грубить (если персона такая)
- Уйти из разговора если надоело

ИСТОРИЯ ДИАЛОГА:
{history}

ПОСЛЕДНЕЕ СООБЩЕНИЕ ПРОДАВЦА:
{bot_message}

Ответь как клиент (1-2 коротких предложения, максимум 30 слов):"""

    def __init__(self, llm: Any, persona: Persona):
        """
        Инициализация агента клиента.

        Args:
            llm: LLM для генерации ответов
            persona: Персона клиента
        """
        self.llm = llm
        self.persona = persona
        self.history: List[Dict[str, str]] = []
        self.turn = 0
        self._decided_to_leave = False
        self._objection_count = 0
        self._last_response = ""
        self._repeat_count = 0

    def start_conversation(self) -> str:
        """
        Генерирует первое сообщение клиента.

        Returns:
            Стартовое сообщение
        """
        starter = random.choice(self.persona.conversation_starters)
        # Добавляем шум к стартеру
        starter = self._apply_persona_noise(starter)
        return starter

    def respond(self, bot_message: str) -> str:
        """
        Генерирует ответ клиента на сообщение бота.

        Args:
            bot_message: Сообщение бота

        Returns:
            Ответ клиента
        """
        # Проверяем, решил ли клиент уйти
        if self._should_leave_now():
            return self._generate_leave_message()

        # Строим промпт
        prompt = self.SYSTEM_PROMPT.format(
            persona_name=self.persona.name,
            persona_description=self.persona.description,
            history=self._format_history(),
            bot_message=bot_message
        )

        # Генерируем ответ через LLM
        try:
            response = self.llm.generate(prompt)
            response = self._clean_response(response)
        except Exception:
            # Fallback если LLM не работает
            response = self._generate_fallback_response()

        # Проверяем на повтор и форсируем разнообразие
        response = self._ensure_variety(response)

        # Применяем шум согласно персоне
        response = self._apply_persona_noise(response)

        # Проверяем, нужно ли добавить возражение
        if self._should_add_objection():
            response = self._inject_objection(response)

        # Сохраняем в историю
        self.history.append({
            "bot": bot_message,
            "client": response
        })
        self.turn += 1

        return response

    def should_continue(self) -> bool:
        """
        Решает, продолжать ли диалог.

        Returns:
            True если клиент хочет продолжать
        """
        # Явно решил уйти
        if self._decided_to_leave:
            return False

        # Достигли максимума ходов
        if self.turn >= self.persona.max_turns:
            return False

        # Случайный уход для некоторых персон
        if self.persona.name in ["busy", "aggressive", "tire_kicker"]:
            if self.turn > 3 and random.random() < 0.15:
                self._decided_to_leave = True
                return False

        return True

    def _format_history(self) -> str:
        """Форматирует историю диалога для промпта"""
        if not self.history:
            return "(начало диалога)"

        lines = []
        for turn in self.history[-5:]:  # Последние 5 ходов
            lines.append(f"Продавец: {turn['bot']}")
            lines.append(f"Вы: {turn['client']}")

        return "\n".join(lines)

    def _clean_response(self, response: str) -> str:
        """Очищает ответ LLM от лишнего"""
        # Убираем кавычки если есть
        response = response.strip('"\'')

        # Убираем префиксы типа "Клиент:" или "Ответ:"
        prefixes = ["Клиент:", "Ответ:", "Client:", "Response:", "Вы:"]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()

        # Ограничиваем длину
        words = response.split()
        if len(words) > 35:
            response = ' '.join(words[:35])

        # Убираем слишком формальные фразы
        formal_phrases = [
            "Благодарю за информацию",
            "Спасибо за подробный ответ",
            "Очень интересно",
            "Это замечательно",
        ]
        for phrase in formal_phrases:
            response = response.replace(phrase, "")

        return response.strip()

    def _apply_persona_noise(self, text: str) -> str:
        """Применяет шум согласно персоне"""
        if self.persona.name in ["aggressive", "busy"]:
            return add_heavy_noise(text)
        elif self.persona.name in ["technical"]:
            return add_light_noise(text)
        else:
            return add_noise(text)

    def _should_add_objection(self) -> bool:
        """Решает, добавить ли возражение"""
        if self._objection_count >= 3:
            return False
        return random.random() < self.persona.objection_probability * 0.3

    def _inject_objection(self, response: str) -> str:
        """Добавляет возражение к ответу"""
        if not self.persona.preferred_objections:
            return response

        objection_type = random.choice(self.persona.preferred_objections)
        objections = {
            "price": ["но это дорого", "а подешевле?", "дороговато"],
            "time": ["некогда", "давайте быстрее", "нет времени"],
            "skepticism": ["не уверен", "сомневаюсь", "а это точно работает?"],
            "competitor": ["а чем лучше Poster?", "у iiko это есть"],
            "not_now": ["потом", "не сейчас", "подумаю"],
            "trust": ["не верю", "докажите"],
        }

        if objection_type in objections:
            objection = random.choice(objections[objection_type])
            response = f"{response} {objection}"
            self._objection_count += 1

        return response

    def _should_leave_now(self) -> bool:
        """Проверяет, пора ли уходить"""
        if self._decided_to_leave:
            return True

        # tire_kicker уходит рано
        if self.persona.name == "tire_kicker" and self.turn > 4:
            if random.random() < 0.4:
                self._decided_to_leave = True
                return True

        return False

    def _generate_leave_message(self) -> str:
        """Генерирует сообщение об уходе"""
        leave_messages = {
            "busy": ["всё, некогда", "потом", "ладно пока"],
            "aggressive": ["всё хватит", "надоело", "пока"],
            "tire_kicker": ["спс, подумаю", "ок понял, потом", "ладн посмотрим"],
            "default": ["ладно, потом", "пока подумаю", "спасибо, до свидания"]
        }

        messages = leave_messages.get(self.persona.name, leave_messages["default"])
        return random.choice(messages)

    def _generate_fallback_response(self) -> str:
        """Генерирует fallback ответ если LLM не работает"""
        fallbacks = [
            "ага",
            "понял",
            "ок",
            "хм, интересно",
            "а подробнее?",
            "и что дальше?",
        ]
        return random.choice(fallbacks)

    def _ensure_variety(self, response: str) -> str:
        """
        Проверяет на повторы и форсирует разнообразие ответов.

        Если клиент повторяется 2+ раза - меняем стратегию.
        """
        # Нормализуем для сравнения
        normalized = response.lower().strip()[:50]
        last_normalized = self._last_response.lower().strip()[:50]

        # Проверяем на повтор
        if normalized == last_normalized or self._is_similar(normalized, last_normalized):
            self._repeat_count += 1

            # При повторах - меняем стратегию
            if self._repeat_count >= 2:
                # Варианты выхода из цикла
                alternatives = [
                    "ладно, давай дальше",
                    "ок понял, что еще?",
                    "хорошо, продолжай",
                    "угу, а что дальше?",
                    "ну ок",
                    "да да, слышу",
                ]
                response = random.choice(alternatives)
                self._repeat_count = 0
        else:
            self._repeat_count = 0

        self._last_response = response
        return response

    def _is_similar(self, a: str, b: str) -> bool:
        """Проверяет схожесть двух строк (простая эвристика)"""
        if not a or not b:
            return False
        # Если совпадает >70% слов - считаем похожими
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return False
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return (intersection / union) > 0.7 if union > 0 else False

    def get_summary(self) -> Dict[str, Any]:
        """Возвращает summary по клиенту"""
        return {
            "persona": self.persona.name,
            "turns": self.turn,
            "objections": self._objection_count,
            "left_early": self._decided_to_leave,
        }
