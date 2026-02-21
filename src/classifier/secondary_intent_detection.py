# src/classifier/secondary_intent_detection.py

"""
Secondary Intent Detection Layer.

Architectural Solution for the "Lost Question" Bug.

Problem:
    When a user sends a composite message like "100 человек. Сколько стоит?",
    the LLM classifier picks ONE primary intent (often info_provided for the data).
    The question intent (price_question) is LOST.

Solution:
    This layer detects secondary intents (especially questions) in ANY message,
    regardless of what primary intent was classified. These secondary intents
    are stored in the result metadata and can be acted upon by Knowledge Sources.

Architecture:
    - Runs EARLY in the pipeline (HIGH priority, after confidence calibration)
    - Does NOT change primary intent (preserves classifier decision)
    - ADDS secondary_intents list to result metadata
    - Uses keyword/pattern matching for reliability (no LLM dependency)
    - Configuration-driven: patterns loaded from constants.yaml

Design Principles:
    - Non-destructive: Never overwrites primary intent
    - Additive: Only adds metadata
    - Fast: O(n) pattern matching, no external calls
    - Fail-safe: Returns original on any error
    - Universal: Works with ANY flow (SPIN, BANT, custom)

Usage by Downstream Components:
    - FactQuestionSource checks secondary_intents for question_* intents
    - DialoguePolicy can use secondary_intents for overlay decisions
    - Response generator can acknowledge both data and question

Example:
    Input:
        message: "100 человек. Сколько стоит?"
        intent: "info_provided"
        confidence: 0.85

    Output:
        intent: "info_provided"  # UNCHANGED
        confidence: 0.85         # UNCHANGED
        secondary_intents: ["price_question"]  # ADDED
        secondary_intent_confidence: {"price_question": 0.9}  # ADDED
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, FrozenSet, Pattern
import re
import logging

from src.classifier.refinement_pipeline import (
    BaseRefinementLayer,
    LayerPriority,
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    register_refinement_layer,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecondaryIntentPattern:
    """
    Pattern definition for detecting secondary intents.

    Attributes:
        intent: Target intent name (e.g., "price_question")
        patterns: List of regex patterns to match
        keywords: Set of keywords for fast O(1) lookup
        min_confidence: Minimum confidence for this detection
        priority: Higher priority patterns are checked first
    """
    intent: str
    patterns: List[str] = field(default_factory=list)
    keywords: FrozenSet[str] = field(default_factory=frozenset)
    min_confidence: float = 0.8
    priority: int = 10


# =============================================================================
# DEFAULT PATTERNS (can be overridden from constants.yaml)
# =============================================================================

DEFAULT_SECONDARY_INTENT_PATTERNS: Dict[str, SecondaryIntentPattern] = {
    # Price-related questions (highest priority)
    # keywords=frozenset() — patterns run unconditionally on every message.
    # Removed homonyms "стоит" (worth/should vs costs) and "давайте" (let's vs pricing).
    # Without frozenset(), removing those keywords would break "сколько стоит?" detection
    # since the pattern r"сколько\s+стоит" requires a keyword gate to execute.
    # Performance cost: ~13 regex checks per message — negligible for chatbot traffic.
    "price_question": SecondaryIntentPattern(
        intent="price_question",
        patterns=[
            r"сколько\s+стоит",
            r"какая\s+цена",
            r"по\s+цен[еам]",
            r"почём",
            r"прайс",
            r"стоимость",
            r"тариф[ыа]?\b",
            r"расценк[иа]",
            r"бюджет\s+какой",
            r"во\s+сколько\s+обойд[её]тся",
            r"сколько\s+будет\s+стоить",
            r"цен[ау]\s+скаж",
            r"давай(?:те)?\s+(?:уже\s+)?(?:по\s+)?(?:цене|ценам|стоимости)",
            # Payment-term patterns (RC4): installment/monthly payment vocabulary
            r"рассрочк[аеуойи]",             # рассрочка/рассрочке/рассрочку/рассрочкой/рассрочки
            r"в\s+рассрочку",                 # в рассрочку
            r"помесячн",                       # помесячно, помесячная
            r"ежемесячн",                      # ежемесячный платёж
            r"частями",                        # оплатить частями, платить частями
            r"(?:без\s+)?переплат",           # без переплат
        ],
        keywords=frozenset(),  # empty → all patterns always run; no keyword-gating homonyms
        min_confidence=0.9,
        priority=100,
    ),

    # Feature questions
    # Removed homonyms: "может" (maybe/can), "какие" (generic which/what),
    # "работает" (e.g., "магазин работает" false positive).
    "question_features": SecondaryIntentPattern(
        intent="question_features",
        patterns=[
            r"какие\s+функци[ияй]",
            r"что\s+(?:может|умеет|делает)",
            r"(?:какие\s+)?возможност[иь]",
            r"функционал",
            r"как\s+работает",
            r"расскажите\s+(?:про|о|об)",
            r"что\s+система\s+умеет",
        ],
        keywords=frozenset({
            "функции", "функционал", "возможности", "возможность",
            "умеет",
            # Removed: "может" (homonym: may/maybe), "какие" (too generic),
            # "работает" (generic operational status phrase)
        }),
        min_confidence=0.85,
        priority=80,
    ),

    # Integration questions
    "question_integrations": SecondaryIntentPattern(
        intent="question_integrations",
        patterns=[
            # Existing patterns
            r"интеграци[яию]",
            r"подключ(?:ить|ение|ается)",
            r"синхрониз(?:ация|ировать)",
            r"совместим(?:ость|о)",
            r"api\b",
            r"касп[иы]",
            r"1с\b",

            # NEW: API/Technical integration
            r"webhook",
            r"rest|soap|graphql",
            r"запрос[ыа]?\s+(?:к\s+)?api",
            r"эндпоинт[ыа]?|endpoint",
            r"метод[ыа]?\s+api",
            r"авторизаци[яи]\s+api",
            r"ключ[ия]?\s+api",
            r"токен[а]?",
            r"импорт|экспорт",
            r"обмен\s+данн",
        ],
        keywords=frozenset({
            # Existing keywords
            "интеграция", "интеграции", "интегрируется",
            "подключить", "подключение", "синхронизация",
            "каспи", "kaspi", "1с", "api",

            # API keywords
            "webhook",
            "rest", "soap", "graphql",
            "эндпоинт", "endpoint",
            "токен", "token",
            # Removed: "импорт", "экспорт" — retail homonyms ("импорт товаров" = trade, not data)
            # Removed: "обмен" — homonym ("обмен товаров" = return, "обмен валюты" = currency)
            # Pattern r"импорт|экспорт" still runs when other integration keywords trigger it.
            "exchange",
        }),
        min_confidence=0.8,
        priority=65,
    ),

    # Technical questions
    "question_technical": SecondaryIntentPattern(
        intent="question_technical",
        patterns=[
            # Existing patterns
            r"техническ(?:ий|ие|ая)",
            r"как\s+настро(?:ить|йка)",
            r"документаци[яию]",
            r"инструкци[яию]",
            r"требовани[яе]",

            # NEW: Security/Technical patterns
            r"\bssl\b|\btls\b|https",
            r"шифровани[яе]|encryption",
            r"сертификат[ыа]?|certificate",
            r"протокол[ыа]?",
            r"спецификаци[яи]",
            r"тех\s*характеристик",
            r"api\b|webhook",
            r"интеграци[яи]\s+через",
            r"sdk\b|библиотек",

            # NEW: Implementation questions
            r"как\s+(?:это\s+)?работа[её]т",
            r"какие?\s+(?:параметры|настройки)",
            r"где\s+(?:настра|конфигур)",
        ],
        keywords=frozenset({
            # Existing keywords
            "технический", "настройка", "документация",
            "инструкция", "требования", "спецификация",

            # Security/Technical
            "ssl", "tls", "https",
            "шифрование", "encryption",
            "сертификат", "certificate",
            # Removed: "протокол" — homonym ("протокол встречи" = meeting minutes)
            # Removed: "protocols" — kept only specific Russian forms

            # API/Integration
            "api", "webhook", "sdk",
            "интеграция", "integration",
            "библиотека", "library",

            # Configuration
            # Removed: "параметры" — homonym ("параметры бизнеса", "эти параметры важны")
            "конфигурация",
            # Removed: "характеристики" — homonym ("характеристики клиентов")
            "specs",
        }),
        min_confidence=0.75,  # Снизили с 0.8 для большего coverage
        priority=60,
    ),

    # Security questions (NEW)
    "question_security": SecondaryIntentPattern(
        intent="question_security",
        patterns=[
            r"безопасност[ьи]",
            r"защит[аыу](?:\s+данных)?",
            r"\bssl\b|\btls\b",
            r"шифровани[яе]",
            r"сертификат[ыа]?",
            r"аудит[а]?\s+безопасности",
            r"gdpr|персональн[ыхм]*\s+данн",
            r"конфиденциальност[ьи]",
            r"двухфакторн|2fa|mfa",
            r"аутентификаци[яи]",
            r"авторизаци[яи]",
            r"контроль\s+доступа",
            r"роли\s+(?:и\s+)?права",
            r"резервн(?:ое|ая)\s+копи",
            r"бэкап|backup",
            r"восстановлени[яе]",
            r"отказоустойчив",
        ],
        keywords=frozenset({
            "безопасность", "security",
            "защита", "защиты",
            "ssl", "tls", "https",
            "шифрование", "encryption",
            "сертификат", "certificate",
            "аудит", "audit",
            "gdpr", "персональные",
            "конфиденциальность",
            "двухфакторная", "2fa", "mfa",
            "аутентификация", "authentication",
            # Removed: "авторизация" — POS homonym ("авторизация платежа" = payment auth)
            # Pattern r"авторизаци[яи]" still runs when other security keywords gate it.
            "authorization",
            # Removed: "доступа" — homonym ("нет доступа к интернету" = connectivity issue)
            "контроль",  # Gates r"контроль\s+доступа" pattern; safe — patterns are contextual
            "роли",      # Gates r"роли\s+(?:и\s+)?права" pattern
            "access",
            "права", "permissions",
            "бэкап", "backup",
            "восстановление", "recovery",
        }),
        min_confidence=0.8,
        priority=70,  # Выше question_technical (более специфичный)
    ),

    # Equipment questions
    "question_equipment": SecondaryIntentPattern(
        intent="question_equipment_general",
        patterns=[
            r"оборудовани[ея]",
            r"терминал",
            r"касс(?:а|у|ы|овы[йм])",
            r"сканер",
            r"принтер",
            r"весы\b",
        ],
        keywords=frozenset({
            "оборудование", "терминал", "касса",
            "сканер", "принтер", "весы", "моноблок",
        }),
        min_confidence=0.85,
        priority=65,
    ),

    # Demo/callback requests (high priority - closing signals)
    "demo_request": SecondaryIntentPattern(
        intent="demo_request",
        patterns=[
            r"(?:покажите|показать)\s+(?:как|демо)",
            r"демонстраци[яию]",
            r"попробовать",
            r"тест(?:овый|ировать)",
            r"пробн(?:ый|ая|ую)",
            # RC5: expanded demo/visual request patterns
            r"(?:можно|хочу|хотел[аи]?\s+бы)\s+(?:посмотреть|глянуть|увидеть)",
            r"посмотреть\s+(?:на\s+)?(?:примере|как|демо|в\s+деле|систему|интерфейс)",
            r"(?:увидеть|глянуть)\s+(?:как|демо|пример|в\s+работе|в\s+деле)",
            r"как\s+выглядит",
            r"(?:покажите?|показать)\s+(?:интерфейс|систему|в\s+деле|пример)",
            r"\bвидео\b",
            r"скрин(?:шот)?",
        ],
        keywords=frozenset({
            "демо", "демонстрация", "показать", "покажите",
            "попробовать", "тестовый", "пробный",
            "посмотреть", "глянуть", "увидеть", "видео", "скриншот", "интерфейс",
        }),
        min_confidence=0.9,
        priority=95,
    ),

    "callback_request": SecondaryIntentPattern(
        intent="callback_request",
        patterns=[
            r"перезвон(?:ите|ить)",
            r"позвон(?:ите|ить)",
            r"свяж(?:итесь|усь)",
            r"(?:остав(?:ьте|ить)|да(?:йте|ть)|укаж(?:ите|и))\s+(?:контакт|номер|телефон)",
            r"номер\s+телефон",
        ],
        keywords=frozenset({
            "перезвоните", "позвоните", "свяжитесь",
            "телефон",
        }),
        min_confidence=0.9,
        priority=95,
    ),

    # Urgency signals (meta-intents)
    # Removed homonym keywords: "давайте"/"давай" (let's do X ≠ get to the point),
    # "быстрее" (faster delivery? faster than competitors? ≠ speak faster),
    # "сразу" (right away / I immediately understood ≠ cut to the chase).
    # Remaining keywords "короче", "конкретно", "конкретнее" are unambiguous brevity signals.
    # Patterns that relied on removed keywords (e.g. r"давай(?:те)?\s+(?:уже\s+)?по\s+делу")
    # will still fire when "короче" or "конкретно" gates the check — or the LLM catches
    # bare "давайте по делу" as primary intent directly.
    "request_brevity": SecondaryIntentPattern(
        intent="request_brevity",
        patterns=[
            r"короче",
            r"быстрее",
            r"давай(?:те)?\s+(?:уже\s+)?по\s+делу",
            r"не\s+тян[иу]",
            r"конкретн(?:о|ее)",
            r"сразу\s+(?:к\s+делу|говори)",
        ],
        keywords=frozenset({
            "короче", "конкретно", "конкретнее",
            # Removed: "быстрее" (homonym), "сразу" (homonym),
            #          "давайте" (homonym), "давай" (homonym)
        }),
        min_confidence=0.85,
        priority=50,
    ),

    # Advance/continue requests — triggers SKIP_RETRIEVAL bypass (RC6a)
    # keywords=frozenset() is REQUIRED: gate logic (line 521) only checks patterns
    # when keywords match OR keywords is empty. Words like "продолжай", "всё что есть"
    # have no natural keyword — frozenset() ensures patterns always run.
    "advance_request": SecondaryIntentPattern(
        intent="advance_request",
        patterns=[
            r"что\s+ещ[ёе]",                                        # "что ещё?", "что ещё можете?"
            r"а\s+ещ[ёе]\b",                                        # "а ещё?"
            r"какие\s+ещ[ёе]",                                      # "какие ещё?"
            r"ещ[ёе]\s+что[- ](?:то|нибудь)",                       # "ещё что-то", "ещё что-нибудь"
            r"расскажи(?:те)?\s+ещ[ёе]",                            # "расскажите ещё"
            r"\bдальше\b",                                           # "дальше", "что дальше", "идём дальше"
            r"продолж(?:ай|айте|и)",                                 # "продолжай", "продолжайте", "продолжи"
            r"ещ[ёе]\s+расскажи",                                   # "ещё расскажи"
            r"что\s+ещ[ёе]\s+(?:можете|умеет|есть|предлагаете|покажете)",  # "что ещё можете?"
            r"а\s+помимо\s+(?:этого|того)",                         # "а помимо этого?"
            r"(?:это\s+)?всё\s+(?:что\s+есть|что\s+можете)\??",    # "это всё что есть?"
            r"что[- ]то\s+ещ[ёе]",                                  # "что-то ещё?"
        ],
        keywords=frozenset(),  # empty → patterns always run (no keyword gating)
        min_confidence=0.85,
        priority=75,
    ),
}


@register_refinement_layer("secondary_intent_detection")
class SecondaryIntentDetectionLayer(BaseRefinementLayer):
    """
    Detects secondary intents in composite messages.

    This layer ADDS secondary_intents metadata without changing the primary intent.
    It enables downstream components (FactQuestionSource, DialoguePolicy) to
    respond to questions even when they weren't the primary classification.

    Key Design Decisions:
        1. NON-DESTRUCTIVE: Never changes primary intent
        2. PATTERN-BASED: Uses regex + keywords, no LLM dependency
        3. CONFIGURABLE: Patterns can be extended via constants.yaml
        4. FAIL-SAFE: Returns original result on any error

    Example:
        >>> layer = SecondaryIntentDetectionLayer()
        >>> ctx = RefinementContext(
        ...     message="100 человек. Сколько стоит?",
        ...     intent="info_provided",
        ...     confidence=0.85,
        ... )
        >>> result = layer.refine("100 человек. Сколько стоит?", {...}, ctx)
        >>> result.secondary_signals
        ['price_question']
    """

    LAYER_NAME = "secondary_intent_detection"
    LAYER_PRIORITY = LayerPriority.HIGH  # Run early, after confidence calibration
    FEATURE_FLAG = "secondary_intent_detection"  # Feature flag for gradual rollout

    def __init__(self):
        """Initialize with default patterns (can be overridden from config)."""
        super().__init__()

        # Load patterns from config or use defaults
        self._patterns = self._load_patterns()

        # Compile regex patterns for efficiency
        self._compiled_patterns: Dict[str, List[Pattern]] = {}
        self._compile_patterns()

        # Stats for monitoring
        self._detections_by_intent: Dict[str, int] = {}
        self._multi_intent_count = 0

        logger.debug(
            f"{self.name} initialized with {len(self._patterns)} intent patterns"
        )

    def _get_config(self) -> Dict[str, Any]:
        """Load configuration from constants.yaml."""
        try:
            from src.yaml_config.constants import get_secondary_intent_config
            return get_secondary_intent_config()
        except (ImportError, AttributeError):
            # Config function not yet added, use defaults
            return {}

    def _load_patterns(self) -> Dict[str, SecondaryIntentPattern]:
        """
        Load patterns from config, merging with defaults.

        Config can:
        - Add new patterns
        - Override existing patterns
        - Disable patterns (enabled: false)
        """
        patterns = dict(DEFAULT_SECONDARY_INTENT_PATTERNS)

        config_patterns = self._config.get("patterns", {})
        for intent, config in config_patterns.items():
            if not config.get("enabled", True):
                # Pattern disabled in config
                patterns.pop(intent, None)
                continue

            # Create or update pattern
            patterns[intent] = SecondaryIntentPattern(
                intent=intent,
                patterns=config.get("patterns", []),
                keywords=frozenset(config.get("keywords", [])),
                min_confidence=config.get("min_confidence", 0.8),
                priority=config.get("priority", 10),
            )

        return patterns

    def _compile_patterns(self) -> None:
        """Compile all regex patterns for efficiency."""
        for intent, pattern_def in self._patterns.items():
            compiled = []
            for p in pattern_def.patterns:
                try:
                    compiled.append(re.compile(p, re.IGNORECASE))
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {intent}: {p} - {e}")
            self._compiled_patterns[intent] = compiled

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """
        Always try to detect secondary intents.

        We don't filter by primary intent because:
        - ANY primary intent can have a secondary question
        - "info_provided" + "price_question" is common
        - "agreement" + "demo_request" is valuable
        """
        # Only skip for very short messages (unlikely to have multiple intents)
        # Threshold 5 (not 10): "что ещё?" (8 chars), "дальше" (6 chars) are valid
        if len(ctx.message) < 5:
            return False

        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Detect secondary intents and add to metadata.

        Algorithm:
        1. Normalize message (lowercase)
        2. Check keywords (O(n) where n = words in message)
        3. Check regex patterns for keyword-matched intents
        4. Rank by confidence and priority
        5. Add to secondary_intents (excluding primary intent)
        """
        text = message.lower()
        # Remove punctuation for keyword matching (keeps original text for regex)
        # This ensures "стоит?" matches keyword "стоит"
        text_clean = re.sub(r'[^\w\s]', ' ', text)
        words = set(text_clean.split())

        # Find matching intents
        detected: List[tuple] = []  # (intent, confidence, priority)

        for intent, pattern_def in self._patterns.items():
            # Skip if this is the primary intent (no need to detect)
            if intent == ctx.intent:
                continue

            # Fast keyword check first
            keyword_match = bool(words & pattern_def.keywords)

            # If keywords match, check patterns for confirmation
            pattern_match = False
            if keyword_match or pattern_def.keywords == frozenset():
                # Check compiled patterns
                for compiled in self._compiled_patterns.get(intent, []):
                    if compiled.search(text):
                        pattern_match = True
                        break

            # Determine confidence based on match type
            if pattern_match:
                confidence = pattern_def.min_confidence
                detected.append((intent, confidence, pattern_def.priority))
            elif keyword_match:
                # Keyword-only match: lower confidence
                confidence = pattern_def.min_confidence * 0.8
                if confidence >= 0.6:  # Threshold for keyword-only
                    detected.append((intent, confidence, pattern_def.priority))

        # Filter out already-separated style intents (from StyleModifierDetectionLayer)
        skip_intents = set(ctx.metadata.get("skip_secondary_detection", []))
        if skip_intents:
            detected = [d for d in detected if d[0] not in skip_intents]

        # If no secondary intents detected, pass through
        if not detected:
            return self._pass_through(result, ctx)

        # Sort by priority (descending), then confidence (descending)
        detected.sort(key=lambda x: (x[2], x[1]), reverse=True)

        # Extract intents and confidences
        secondary_intents = [d[0] for d in detected]
        secondary_confidences = {d[0]: d[1] for d in detected}

        # Update stats
        for intent in secondary_intents:
            self._detections_by_intent[intent] = (
                self._detections_by_intent.get(intent, 0) + 1
            )
        if len(secondary_intents) > 1:
            self._multi_intent_count += 1

        # Log detection
        logger.info(
            f"Secondary intents detected: {secondary_intents}",
            extra={
                "primary_intent": ctx.intent,
                "secondary_intents": secondary_intents,
                "log_message": message[:50],
            }
        )

        # Create result with secondary intents (primary unchanged)
        return RefinementResult(
            decision=RefinementDecision.REFINED,  # Metadata was added
            intent=ctx.intent,  # PRIMARY UNCHANGED
            confidence=ctx.confidence,  # PRIMARY UNCHANGED
            original_intent=ctx.intent,
            refinement_reason="secondary_intents_detected",
            layer_name=self.name,
            extracted_data=result.get("extracted_data", {}),
            secondary_signals=secondary_intents,  # THE KEY OUTPUT
            metadata={
                "secondary_intent_confidences": secondary_confidences,
                "detection_method": "pattern_matching",
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        base_stats = super().get_stats()
        base_stats.update({
            "detections_by_intent": dict(self._detections_by_intent),
            "multi_intent_count": self._multi_intent_count,
            "patterns_count": len(self._patterns),
        })
        return base_stats


# =============================================================================
# HELPER FUNCTION FOR CONFIG
# =============================================================================

def get_default_secondary_intent_config() -> Dict[str, Any]:
    """
    Get default configuration for secondary intent detection.

    This can be added to constants.yaml and loaded by the layer.

    Returns:
        Default configuration dict
    """
    return {
        "enabled": True,
        "min_message_length": 10,
        "patterns": {
            intent: {
                "patterns": list(pattern.patterns),
                "keywords": list(pattern.keywords),
                "min_confidence": pattern.min_confidence,
                "priority": pattern.priority,
                "enabled": True,
            }
            for intent, pattern in DEFAULT_SECONDARY_INTENT_PATTERNS.items()
        },
    }
