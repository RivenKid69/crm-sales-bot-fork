"""
DisambiguationUI - форматирование вопросов и парсинг ответов disambiguation.

Отвечает за:
- Формирование вопроса пользователю с вариантами
- Парсинг ответа пользователя (числа, слова, ключевые слова)
"""

import re
from typing import Dict, List, Optional, Tuple

from constants.intent_labels import INTENT_LABELS


class DisambiguationUI:
    """
    Форматирование вопросов и парсинг ответов disambiguation.

    Поддерживает:
    - Числовые ответы: "1", "2", "3", "4"
    - Словесные номера: "первый", "второй", "третий", "четвёртый"
    - Ключевые слова: "цена", "функции", "интеграции"
    - Свой вариант: пользователь может выбрать 4-й вариант для ввода своего ответа
    """

    # Специальный маркер для "свой вариант"
    CUSTOM_INPUT_MARKER = "_custom_input"

    # Паттерны для распознавания ответов
    ANSWER_PATTERNS: Dict[str, List[Tuple[str, int]]] = {
        "numeric": [
            (r"^1$|^перв|^один$", 0),
            (r"^2$|^втор|^два$", 1),
            (r"^3$|^трет|^три$", 2),
            (r"^4$|^четв|^четыре$", 3),  # 4-й вариант - "свой вариант"
        ],
    }

    # Ключевые слова для каждого интента
    INTENT_KEYWORDS: Dict[str, List[str]] = {
        "price_question": ["цен", "стоим", "прайс", "скольк"],
        "question_features": ["функци", "возможност", "умеет"],
        "question_integrations": ["интеграц", "подключ", "1с", "kaspi"],
        "objection_price": ["дорог", "дешев"],
        "agreement": ["да", "давайте", "хорошо", "продолж"],
        "demo_request": ["демо", "показ", "попробов"],
        "callback_request": ["перезвон", "позвон", "свяж"],
    }

    def format_question(
        self,
        question: str,
        options: List[Dict],
        context: Dict
    ) -> str:
        """
        Сформировать вопрос для пользователя.

        Args:
            question: Базовый вопрос (может быть пустым)
            options: Список опций [{intent, label, confidence}]
            context: Контекст состояния

        Returns:
            Форматированный вопрос
        """
        # Defense Layer 3: empty options → generic question instead of broken numbered list
        if not options:
            return "Уточните, пожалуйста, что именно вас интересует?"

        spin_phase = context.get("spin_phase")
        frustration = context.get("frustration_level", 0)

        # Для раздражённых пользователей - минимальный формат
        if frustration >= 3:
            return self._format_minimal(options)

        # Для двух вариантов - inline формат
        if len(options) == 2:
            return self._format_inline(options)

        # При SPIN-контексте - контекстуальный формат
        if spin_phase:
            return self._format_contextual(options, spin_phase)

        # По умолчанию - нумерованный список
        return self._format_numbered(options)

    def format_repeat_question(self, options: List[Dict]) -> str:
        """
        Сформировать повторный вопрос при непонятном ответе.

        Args:
            options: Список опций

        Returns:
            Форматированный вопрос
        """
        lines = [f"{i+1}. {self._get_option_label(o)}" for i, o in enumerate(options)]
        options_text = "\n".join(lines)
        return f"Не совсем понял. Уточните:\n{options_text}\nИли напишите ваш вопрос своими словами."

    def parse_answer(
        self,
        answer: str,
        options: List[Dict]
    ) -> Optional[str]:
        """
        Распознать ответ пользователя.

        Args:
            answer: Ответ пользователя
            options: Доступные опции

        Returns:
            Intent выбранной опции, CUSTOM_INPUT_MARKER для своего варианта,
            или None если не удалось распознать
        """
        if not answer or not answer.strip():
            return None

        if not options:
            return None

        answer_lower = answer.lower().strip()
        option_intents = [o["intent"] for o in options]
        custom_input_index = len(option_intents)  # "Свой вариант" всегда следующий после опций

        # Проверяем числовые ответы
        for pattern, index in self.ANSWER_PATTERNS["numeric"]:
            if re.match(pattern, answer_lower):
                # Проверяем, это "свой вариант"?
                if index == custom_input_index:
                    return self.CUSTOM_INPUT_MARKER
                # Проверяем, это одна из опций?
                if index < len(option_intents):
                    return option_intents[index]

        # Проверяем ключевые слова для "свой вариант"
        if re.match(r"^сво[йяеёи]", answer_lower) or "другое" in answer_lower:
            return self.CUSTOM_INPUT_MARKER

        # Проверяем ключевые слова
        for intent, keywords in self.INTENT_KEYWORDS.items():
            if intent in option_intents:
                for keyword in keywords:
                    if keyword in answer_lower:
                        return intent

        return None

    def _get_option_label(self, option: Dict) -> str:
        """
        Получить label для опции.

        Приоритет:
        1. option["label"] (если явно задан)
        2. INTENT_LABELS[option["intent"]]
        3. option["intent"] (fallback)

        Args:
            option: Опция {intent, label?, confidence}

        Returns:
            Человекочитаемый label (никогда не возвращает None)
        """
        if option.get("label"):
            return option["label"]
        return INTENT_LABELS.get(option["intent"], option["intent"])

    def _format_numbered(self, options: List[Dict]) -> str:
        """Форматирование с нумерованным списком."""
        lines = ["Уточните, пожалуйста:"]
        for i, opt in enumerate(options, 1):
            label = self._get_option_label(opt)
            lines.append(f"{i}. {label}")
        lines.append("Или напишите ваш вопрос своими словами.")
        return "\n".join(lines)

    def _format_inline(self, options: List[Dict]) -> str:
        """Форматирование в одну строку для двух вариантов."""
        label1 = self._get_option_label(options[0])
        label2 = self._get_option_label(options[1])
        return f"Вы хотите {label1.lower()} или {label2.lower()}?"

    def _format_minimal(self, options: List[Dict]) -> str:
        """Минимальный формат для раздражённых пользователей."""
        label1 = self._get_option_label(options[0])
        label2 = self._get_option_label(options[1]) if len(options) > 1 else "другое"
        return f"{label1} или {label2}?"

    def _format_contextual(self, options: List[Dict], spin_phase: str) -> str:
        """Контекстуальный формат с учётом SPIN-фазы."""
        # Пока просто используем нумерованный формат
        # В будущем можно добавить контекстуальные фразы
        return self._format_numbered(options)
