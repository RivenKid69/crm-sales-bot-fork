"""
Анализатор тона сообщений клиента.

Определяет эмоциональный тон (frustration, skepticism, etc.) и стиль (formal/informal).
Отслеживает накопительный уровень frustration в течение диалога.

Использование:
    from tone_analyzer import ToneAnalyzer, Tone, Style

    analyzer = ToneAnalyzer()
    result = analyzer.analyze("Сколько можно уже!")
    print(result.tone)  # Tone.FRUSTRATED
    print(result.frustration_level)  # 3
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from logger import logger


class Tone(Enum):
    """Типы эмоционального тона"""
    NEUTRAL = "neutral"         # Нейтральный
    POSITIVE = "positive"       # Позитивный
    FRUSTRATED = "frustrated"   # Раздражён
    SKEPTICAL = "skeptical"     # Сомневается
    RUSHED = "rushed"           # Торопится
    CONFUSED = "confused"       # Не понимает
    INTERESTED = "interested"   # Заинтересован


class Style(Enum):
    """Стиль общения"""
    FORMAL = "formal"       # Формальный
    INFORMAL = "informal"   # Неформальный


@dataclass
class ToneAnalysis:
    """Результат анализа тона"""
    tone: Tone                          # Основной тон сообщения
    style: Style                        # Стиль общения
    confidence: float                   # Уверенность в определении (0-1)
    frustration_level: int              # Накопительный уровень frustration (0-10)
    signals: List[str] = field(default_factory=list)  # Обнаруженные сигналы


class ToneAnalyzer:
    """
    Анализатор тона с накопительным frustration tracking.

    Критично: отслеживаем ИЗМЕНЕНИЕ тона в течение диалога,
    не только текущее сообщение.

    Особенности:
    - Определение тона по ключевым словам и эмодзи
    - Определение стиля (formal/informal)
    - Накопительный frustration_level с decay
    - Рекомендации по формированию ответа
    """

    # Маркеры тона (паттерны regex)
    TONE_MARKERS: Dict[Tone, List[str]] = {
        Tone.POSITIVE: [
            r"отлично", r"супер", r"класс", r"здорово", r"круто",
            r"интересно", r"нравится", r"хорошо", r"замечательно",
            r"прекрасно", r"великолепно", r"чудесно", r"потрясающе",
            r"👍", r"😊", r"🔥", r"💪", r"😄", r"🙂", r"❤", r"👏",
        ],
        Tone.FRUSTRATED: [
            r"сколько\s+можно", r"опять", r"снова", r"достал",
            r"надоел", r"хватит", r"отстань", r"уже\s+говорил",
            r"не\s+понимаете", r"бесит", r"раздража", r"задолбал",
            r"замучил", r"утомил", r"устал", r"невозможно",
            r"🙄", r"😤", r"😡", r"😠", r"🤬", r"💢",
        ],
        Tone.SKEPTICAL: [
            r"сомнева", r"вряд\s*ли", r"не\s+верю", r"не\s+уверен",
            r"правда\s*\?", r"серьёзно\s*\?", r"это\s+точно",
            r"а\s+доказательств", r"чем\s+докаж", r"не\s+факт",
            r"сказки", r"враньё", r"обман", r"развод",
            r"🤔", r"🤨", r"😒",
        ],
        Tone.RUSHED: [
            r"быстр", r"короче", r"давай\s+к\s+делу", r"некогда",
            r"времени\s+нет", r"срочно", r"скорее", r"не\s+тяни",
            r"побыстр", r"без\s+воды", r"ближе\s+к\s+делу",
            r"к\s+сути", r"по\s+быстрому", r"оперативн",
            r"⏰", r"⚡",
        ],
        Tone.CONFUSED: [
            r"не\s+понял", r"не\s+понятно", r"что\s+это", r"как\s+это",
            r"не\s+понимаю", r"объясни", r"что\s+имеете", r"имеете\s+в\s+виду", r"\?\?\?",
            r"запутал", r"сложно", r"непонят", r"странно",
            r"в\s+смысле", r"то\s+есть", r"а\s+именно",
            r"🤷", r"❓", r"⁉️",
        ],
        Tone.INTERESTED: [
            r"расскажите\s+подробнее", r"интересно", r"а\s+как",
            r"покажите", r"хочу\s+узнать", r"любопытно",
            r"расскажи", r"поведайте", r"поделитесь",
            r"хотелось\s+бы", r"было\s+бы\s+интересно",
            r"👀", r"🧐", r"🤩",
        ],
    }

    # Маркеры неформального стиля
    INFORMAL_MARKERS: List[str] = [
        r"\bпривет\b", r"\bприв\b", r"\bок\b", r"\bокей\b", r"\bну\b", r"\bтипа\b",
        r"\bкороче\b", r"\bчё\b", r"\bваще\b", r"\bнорм\b", r"\bблин\b",
        r"\bчо\b", r"\bага\b", r"\bугу\b", r"\bкласс\b", r"\bкруто\b",
        r"\bчел\b", r"\bпацан\b", r"\bбро\b", r"\bдруг\b", r"\bбратан\b",
        r"\bлады\b", r"\bладушки\b", r"\bокейно\b", r"\bнормас\b",
        r"\bпон\b", r"\bпонял\b", r"\bясн\b", r"\bприкол\b",
    ]

    # Веса для frustration (накапливается)
    FRUSTRATION_WEIGHTS: Dict[Tone, int] = {
        Tone.FRUSTRATED: 3,     # Сильно увеличивает
        Tone.SKEPTICAL: 1,      # Немного увеличивает
        Tone.RUSHED: 1,         # Немного увеличивает
        Tone.CONFUSED: 1,       # Если долго не понимает — тоже frustration
    }

    # Веса для снижения frustration
    FRUSTRATION_DECAY: Dict[Tone, int] = {
        Tone.NEUTRAL: 1,        # Немного снижает
        Tone.POSITIVE: 2,       # Хорошо снижает
        Tone.INTERESTED: 2,     # Хорошо снижает
    }

    # Максимальный уровень frustration
    MAX_FRUSTRATION: int = 10

    # Пороги frustration для разных действий
    FRUSTRATION_THRESHOLDS = {
        "warning": 4,           # Начать сокращать ответы
        "high": 7,              # Предложить помощь/выход
        "critical": 9,          # Мягкое завершение
    }

    def __init__(self):
        self.frustration_history: List[Dict] = []
        self.cumulative_frustration: int = 0
        self._compiled_patterns: Dict[Tone, List[re.Pattern]] = {}
        self._compiled_informal: List[re.Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Компилируем regex паттерны для производительности"""
        for tone, markers in self.TONE_MARKERS.items():
            self._compiled_patterns[tone] = [
                re.compile(m, re.IGNORECASE | re.UNICODE) for m in markers
            ]

        self._compiled_informal = [
            re.compile(m, re.IGNORECASE | re.UNICODE) for m in self.INFORMAL_MARKERS
        ]

    def reset(self) -> None:
        """Сброс состояния анализатора (для нового диалога)"""
        self.frustration_history = []
        self.cumulative_frustration = 0

    def analyze(self, message: str, history: Optional[List[str]] = None) -> ToneAnalysis:
        """
        Анализирует тон сообщения + учитывает историю.

        Args:
            message: Текст сообщения для анализа
            history: Опциональная история предыдущих сообщений (не используется напрямую,
                    но frustration накапливается автоматически между вызовами)

        Returns:
            ToneAnalysis с результатами анализа
        """
        message_lower = message.lower()
        signals: List[str] = []

        # Определяем тон
        detected_tones: List[Tone] = []
        tone_scores: Dict[Tone, int] = {}

        for tone, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message_lower):
                    if tone not in detected_tones:
                        detected_tones.append(tone)
                        tone_scores[tone] = tone_scores.get(tone, 0) + 1
                    signals.append(f"{tone.value}:{pattern.pattern}")
                    break  # Один паттерн на тон достаточно

        # Выбираем доминирующий тон (приоритет важности)
        primary_tone = self._select_primary_tone(detected_tones, tone_scores)

        # Определяем стиль
        style = self._detect_style(message_lower)

        # Обновляем cumulative frustration
        self._update_frustration(primary_tone)

        # Confidence на основе количества сигналов
        confidence = min(0.5 + len(signals) * 0.15, 0.95)
        if not signals:
            confidence = 0.3  # Низкая уверенность для нейтрального без сигналов

        result = ToneAnalysis(
            tone=primary_tone,
            style=style,
            confidence=confidence,
            frustration_level=self.cumulative_frustration,
            signals=signals
        )

        # Логируем если frustration высокий
        if self.cumulative_frustration >= self.FRUSTRATION_THRESHOLDS["warning"]:
            logger.warning(
                "Elevated frustration detected",
                frustration_level=self.cumulative_frustration,
                tone=primary_tone.value,
                signals_count=len(signals)
            )

        return result

    def _select_primary_tone(
        self,
        detected_tones: List[Tone],
        tone_scores: Dict[Tone, int]
    ) -> Tone:
        """
        Выбираем доминирующий тон с учётом приоритетов.

        Приоритет (от высшего к низшему):
        1. FRUSTRATED - самый важный, нужно реагировать
        2. RUSHED - клиент торопится
        3. SKEPTICAL - сомневается
        4. CONFUSED - не понимает
        5. POSITIVE - позитивный
        6. INTERESTED - заинтересован
        7. NEUTRAL - по умолчанию
        """
        priority_order = [
            Tone.FRUSTRATED,
            Tone.RUSHED,
            Tone.SKEPTICAL,
            Tone.CONFUSED,
            Tone.POSITIVE,
            Tone.INTERESTED,
        ]

        for tone in priority_order:
            if tone in detected_tones:
                return tone

        return Tone.NEUTRAL

    def _detect_style(self, message_lower: str) -> Style:
        """Определяем стиль общения (formal/informal)"""
        informal_count = sum(
            1 for pattern in self._compiled_informal
            if pattern.search(message_lower)
        )

        # Если есть 2+ неформальных маркера — неформальный стиль
        if informal_count >= 2:
            return Style.INFORMAL

        # Или если есть характерные признаки
        if informal_count >= 1 and len(message_lower) < 50:
            return Style.INFORMAL

        return Style.FORMAL

    def _update_frustration(self, tone: Tone) -> None:
        """
        Накопительный frustration tracking.

        - Негативные тона увеличивают frustration
        - Позитивные/нейтральные тона снижают (decay)
        - Уровень ограничен [0, MAX_FRUSTRATION]
        """
        # Увеличение frustration
        if tone in self.FRUSTRATION_WEIGHTS:
            weight = self.FRUSTRATION_WEIGHTS[tone]
            self.cumulative_frustration = min(
                self.MAX_FRUSTRATION,
                self.cumulative_frustration + weight
            )
        # Снижение frustration (decay)
        elif tone in self.FRUSTRATION_DECAY:
            decay = self.FRUSTRATION_DECAY[tone]
            self.cumulative_frustration = max(
                0,
                self.cumulative_frustration - decay
            )

        # Сохраняем историю
        self.frustration_history.append({
            "tone": tone.value,
            "cumulative": self.cumulative_frustration
        })

        # Логируем критический уровень
        if self.cumulative_frustration >= self.FRUSTRATION_THRESHOLDS["critical"]:
            logger.error(
                "Critical frustration level reached",
                frustration_level=self.cumulative_frustration
            )

    def get_response_guidance(self, analysis: ToneAnalysis) -> Dict:
        """
        Возвращает рекомендации для генерации ответа.

        Args:
            analysis: Результат анализа тона

        Returns:
            Словарь с рекомендациями:
            - max_words: максимальное количество слов
            - tone_instruction: инструкция для промпта
            - should_apologize: нужно ли извиниться
            - should_offer_exit: нужно ли предложить выход
            - formality: уровень формальности ("formal" или "casual")
        """
        guidance = {
            "max_words": 50,
            "tone_instruction": "",
            "should_apologize": False,
            "should_offer_exit": False,
            "formality": "formal" if analysis.style == Style.FORMAL else "casual"
        }

        # Критический frustration — минимальные ответы, предложить выход
        if analysis.frustration_level >= self.FRUSTRATION_THRESHOLDS["critical"]:
            guidance["max_words"] = 20
            guidance["tone_instruction"] = (
                "Будь МАКСИМАЛЬНО кратким. Одно предложение. "
                "Извинись и предложи завершить разговор."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # Высокий frustration — короткие ответы, возможен выход
        elif analysis.frustration_level >= self.FRUSTRATION_THRESHOLDS["high"]:
            guidance["max_words"] = 30
            guidance["tone_instruction"] = (
                "Будь максимально кратким и по делу. "
                "Не задавай лишних вопросов. Извинись за неудобства."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # Повышенный frustration — сокращаем ответы
        elif analysis.frustration_level >= self.FRUSTRATION_THRESHOLDS["warning"]:
            guidance["max_words"] = 40
            guidance["tone_instruction"] = (
                "Будь кратким и деловым. "
                "Признай возможные неудобства."
            )
            guidance["should_apologize"] = True

        # Специфика по тону (если frustration низкий)
        elif analysis.tone == Tone.RUSHED:
            guidance["max_words"] = 30
            guidance["tone_instruction"] = (
                "Коротко и по делу, без вступлений и воды."
            )

        elif analysis.tone == Tone.SKEPTICAL:
            guidance["tone_instruction"] = (
                "Приведи конкретные факты и цифры. "
                "Не используй общие фразы."
            )

        elif analysis.tone == Tone.CONFUSED:
            guidance["tone_instruction"] = (
                "Объясни просто и понятно. "
                "Используй короткие предложения и примеры."
            )

        elif analysis.tone == Tone.POSITIVE:
            guidance["max_words"] = 60
            guidance["tone_instruction"] = (
                "Можно быть чуть более разговорным. "
                "Поддержи позитивный настрой."
            )

        elif analysis.tone == Tone.INTERESTED:
            guidance["max_words"] = 60
            guidance["tone_instruction"] = (
                "Клиент заинтересован — дай полезную информацию. "
                "Можно быть подробнее."
            )

        return guidance

    def get_frustration_level(self) -> int:
        """Получить текущий уровень frustration"""
        return self.cumulative_frustration

    def is_frustrated(self) -> bool:
        """Проверка на повышенный frustration"""
        return self.cumulative_frustration >= self.FRUSTRATION_THRESHOLDS["warning"]

    def is_critically_frustrated(self) -> bool:
        """Проверка на критический frustration"""
        return self.cumulative_frustration >= self.FRUSTRATION_THRESHOLDS["critical"]

    def get_frustration_history(self) -> List[Dict]:
        """Получить историю изменения frustration"""
        return self.frustration_history.copy()


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ДЕМО TONE ANALYZER")
    print("=" * 60)

    analyzer = ToneAnalyzer()

    test_messages = [
        "Привет, расскажите о вашей системе",           # NEUTRAL/INTERESTED
        "Интересно, а сколько это стоит?",              # INTERESTED
        "Сколько можно уже! Я уже спрашивал!",          # FRUSTRATED
        "Не уверен что это нам подойдёт...",            # SKEPTICAL
        "Короче, давайте к делу, времени нет",          # RUSHED
        "Не понял, что имеете в виду???",               # CONFUSED
        "Супер! Это то что нужно! 👍",                  # POSITIVE
        "Ну окей, норм вроде",                          # INFORMAL
    ]

    for msg in test_messages:
        print(f"\n--- Сообщение: '{msg}' ---")
        result = analyzer.analyze(msg)
        print(f"  Тон: {result.tone.value}")
        print(f"  Стиль: {result.style.value}")
        print(f"  Уверенность: {result.confidence:.2f}")
        print(f"  Frustration: {result.frustration_level}")
        if result.signals:
            print(f"  Сигналы: {result.signals[:3]}")

        guidance = analyzer.get_response_guidance(result)
        print(f"  Рекомендация: max {guidance['max_words']} слов")
        if guidance["tone_instruction"]:
            print(f"  Инструкция: {guidance['tone_instruction'][:50]}...")

    print("\n" + "=" * 60)
    print(f"Финальный frustration level: {analyzer.get_frustration_level()}")
    print("=" * 60)
