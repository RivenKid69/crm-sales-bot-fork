"""
LLM анализатор тона (Tier 3).

Использует основную LLM модель для анализа сложных случаев:
- Сарказм
- Ирония
- Неявные эмоции
"""

import time
from typing import Dict, Optional, Tuple

from logger import logger

from .models import Tone


class LLMToneAnalyzer:
    """
    Tier 3: LLM-based анализатор тона.

    Используется как последний fallback для сложных случаев,
    которые не детектируются regex или semantic методами.

    Особенности:
    - Использует существующий OllamaLLM из проекта
    - Детектирует сарказм и иронию
    - Учитывает контекст
    """

    PROMPT_TEMPLATE = """Определи эмоциональный тон сообщения клиента.

Сообщение: "{message}"

Выбери ОДИН тон из списка:
- frustrated (раздражён, недоволен, устал)
- skeptical (сомневается, не верит, скептичен)
- rushed (торопится, нет времени, спешит)
- confused (не понимает, запутался)
- positive (доволен, позитивен, рад)
- interested (заинтересован, хочет узнать больше)
- neutral (нейтральный, информационный)

Важно:
- Сарказм и ирония = frustrated или skeptical
- "Спасибо" после негатива может быть сарказмом
- Многоточие в конце часто означает сомнение
- Кавычки вокруг слов могут указывать на иронию

Ответь ТОЛЬКО одним словом (тон):"""

    # Маппинг ответа LLM на Tone enum
    TONE_MAPPING: Dict[str, Tone] = {
        "frustrated": Tone.FRUSTRATED,
        "skeptical": Tone.SKEPTICAL,
        "rushed": Tone.RUSHED,
        "confused": Tone.CONFUSED,
        "positive": Tone.POSITIVE,
        "interested": Tone.INTERESTED,
        "neutral": Tone.NEUTRAL,
    }

    # Confidence для LLM ответов
    LLM_CONFIDENCE = 0.75

    def __init__(self, llm=None):
        """
        Инициализация LLM анализатора.

        Args:
            llm: Экземпляр OllamaLLM (опционально, для dependency injection)
        """
        self._llm = llm
        self._available: Optional[bool] = None

    @property
    def llm(self):
        """Lazy initialization LLM клиента."""
        if self._llm is None:
            try:
                from llm import OllamaLLM
                self._llm = OllamaLLM()
            except ImportError:
                logger.warning("OllamaLLM not available")
                return None
        return self._llm

    @property
    def is_available(self) -> bool:
        """Проверить доступен ли LLM."""
        if self._available is not None:
            return self._available

        if self.llm is None:
            self._available = False
            return False

        try:
            self._available = self.llm.health_check()
        except Exception:
            self._available = False

        return self._available

    def analyze(
        self,
        message: str
    ) -> Optional[Tuple[Tone, float]]:
        """
        Анализировать тон через LLM.

        Args:
            message: Текст сообщения

        Returns:
            Tuple[tone, confidence] или None если недоступен/ошибка
        """
        if self.llm is None:
            return None

        if not message or not message.strip():
            return None

        try:
            start_time = time.perf_counter()

            prompt = self.PROMPT_TEMPLATE.format(message=message)
            response = self.llm.generate(prompt, allow_fallback=False)

            if not response:
                return None

            # Парсим ответ
            tone_str = response.strip().lower()

            # Убираем возможные лишние символы
            for char in [".", ",", "!", "?", ":", ";", '"', "'"]:
                tone_str = tone_str.replace(char, "")
            tone_str = tone_str.strip()

            # Маппим на Tone enum
            tone = self.TONE_MAPPING.get(tone_str)

            if tone is None:
                # Пробуем найти частичное совпадение
                for key, value in self.TONE_MAPPING.items():
                    if key in tone_str or tone_str in key:
                        tone = value
                        break

            if tone is None:
                logger.warning(
                    "LLM returned unknown tone",
                    response=response[:50],
                    parsed=tone_str
                )
                return None

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "LLM tone analysis",
                tone=tone.value,
                confidence=self.LLM_CONFIDENCE,
                latency_ms=round(latency_ms, 2)
            )

            return (tone, self.LLM_CONFIDENCE)

        except Exception as e:
            logger.warning(f"LLM tone analysis failed: {e}")
            return None

    def analyze_with_context(
        self,
        message: str,
        history: list[str]
    ) -> Optional[Tuple[Tone, float]]:
        """
        Анализировать тон с учётом истории диалога.

        Args:
            message: Текущее сообщение
            history: Предыдущие сообщения

        Returns:
            Tuple[tone, confidence] или None
        """
        if not history:
            return self.analyze(message)

        # Формируем контекст
        context = "\n".join(f"- {msg}" for msg in history[-3:])

        prompt = f"""Определи эмоциональный тон последнего сообщения клиента с учётом контекста диалога.

Предыдущие сообщения:
{context}

Последнее сообщение: "{message}"

Выбери ОДИН тон: frustrated, skeptical, rushed, confused, positive, interested, neutral

Учитывай:
- Изменение тона по ходу диалога
- Сарказм и ирония = frustrated или skeptical
- Накопительное раздражение

Ответь ТОЛЬКО одним словом:"""

        if self.llm is None:
            return None

        try:
            response = self.llm.generate(prompt, allow_fallback=False)
            if not response:
                return None

            tone_str = response.strip().lower()
            for char in [".", ",", "!", "?", ":", ";", '"', "'"]:
                tone_str = tone_str.replace(char, "")
            tone_str = tone_str.strip()

            tone = self.TONE_MAPPING.get(tone_str)
            if tone:
                return (tone, self.LLM_CONFIDENCE)
            return None

        except Exception as e:
            logger.warning(f"LLM context tone analysis failed: {e}")
            return None

    def reset(self) -> None:
        """Сброс не требуется (stateless)."""
        pass
