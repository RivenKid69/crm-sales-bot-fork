"""
Personalization Engine v2 — главный движок адаптивной персонализации.

Объединяет:
- AdaptiveStyleSelector: выбор стиля на основе поведенческих сигналов
- IndustryDetectorV2: semantic определение отрасли
- EffectiveActionTracker: session memory для отслеживания тактик
- Legacy PersonalizationEngine: business context по размеру компании

Usage:
    engine = PersonalizationEngineV2(retriever)
    result = engine.personalize(envelope, collected_data, action_tracker)
    prompt_vars = result.to_prompt_variables()
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING

from feature_flags import flags
from logger import logger

from src.personalization.result import (
    StyleParameters,
    IndustryContext,
    BusinessContext,
    PersonalizationResult,
)
from src.personalization.style_selector import AdaptiveStyleSelector, BehavioralSignals
from src.personalization.industry_detector import IndustryDetectorV2, IndustryDetectionResult
from src.personalization.action_tracker import EffectiveActionTracker

if TYPE_CHECKING:
    from context_envelope import ContextEnvelope
    from knowledge.retriever import CascadeRetriever


class PersonalizationEngineV2:
    """
    Адаптивный движок персонализации v2.

    Использует поведенческие сигналы из ContextEnvelope для:
    1. Адаптивного выбора стиля коммуникации (engagement, momentum, frustration)
    2. Semantic определения отрасли клиента
    3. Тактических рекомендаций на основе session memory

    Feature flags:
    - personalization_v2: Master switch для v2 engine
    - personalization_adaptive_style: AdaptiveStyleSelector
    - personalization_semantic_industry: Semantic industry detection
    - personalization_session_memory: EffectiveActionTracker

    Usage:
        engine = PersonalizationEngineV2(retriever)

        # В generator.py
        result = engine.personalize(
            envelope=context_envelope,
            collected_data=collected,
            action_tracker=self.action_tracker,
            messages=user_messages
        )

        # Добавляем переменные в промпт
        variables.update(result.to_prompt_variables())
    """

    # === Business Context по размеру (из legacy PersonalizationEngine) ===
    BUSINESS_CONTEXTS: Dict[str, Dict[str, str]] = {
        "micro": {  # 1-5 человек
            "size_label": "небольшая команда",
            "pain_focus": "простота и экономия времени",
            "value_prop": "всё в одном месте, без сложных настроек",
            "objection_counter": "окупается за счёт сэкономленного времени",
            "demo_pitch": "покажу как работает — займёт 15 минут",
        },
        "small": {  # 6-15 человек
            "size_label": "растущая команда",
            "pain_focus": "контроль и координация команды",
            "value_prop": "видите работу каждого сотрудника",
            "objection_counter": "стоимость на человека ниже чем у конкурентов",
            "demo_pitch": "покажу как следить за командой — это удобно",
        },
        "medium": {  # 16-50 человек
            "size_label": "средний бизнес",
            "pain_focus": "масштабирование и автоматизация",
            "value_prop": "автоматизация рутины, аналитика в реальном времени",
            "objection_counter": "enterprise функции по цене малого бизнеса",
            "demo_pitch": "покажу автоматизацию и отчёты — экономит часы",
        },
        "large": {  # 50+ человек
            "size_label": "крупная компания",
            "pain_focus": "интеграция и кастомизация",
            "value_prop": "API, кастомные отчёты, dedicated поддержка",
            "objection_counter": "гибкие условия, индивидуальные тарифы",
            "demo_pitch": "обсудим ваши требования — подготовлю предложение",
        },
    }

    SIZE_THRESHOLDS = {
        "micro": (1, 5),
        "small": (6, 15),
        "medium": (16, 50),
        "large": (51, float("inf")),
    }

    def __init__(self, retriever: "CascadeRetriever" = None):
        """
        Initialize PersonalizationEngineV2.

        Args:
            retriever: CascadeRetriever for semantic matching (optional)
        """
        self.retriever = retriever

        # Инициализируем компоненты
        self.style_selector = AdaptiveStyleSelector()
        self.industry_detector = None

        # Industry detector инициализируется лениво (требует retriever)
        if retriever and flags.personalization_semantic_industry:
            self.industry_detector = IndustryDetectorV2(retriever)

        # Cache для industry detection (накопление уверенности)
        self._industry_cache: Dict[str, Any] = {
            "industry": None,
            "confidence": 0.0,
        }

        logger.debug(
            "PersonalizationEngineV2 initialized",
            has_retriever=retriever is not None,
            semantic_industry=flags.personalization_semantic_industry,
            adaptive_style=flags.personalization_adaptive_style,
        )

    def personalize(
        self,
        envelope: "ContextEnvelope" = None,
        collected_data: Dict[str, Any] = None,
        action_tracker: EffectiveActionTracker = None,
        messages: List[str] = None,
    ) -> PersonalizationResult:
        """
        Выполнить персонализацию на основе контекста.

        Args:
            envelope: ContextEnvelope с поведенческими сигналами
            collected_data: Собранные данные о клиенте
            action_tracker: EffectiveActionTracker для session memory
            messages: Список сообщений клиента (для semantic industry detection)

        Returns:
            PersonalizationResult с переменными для промпта
        """
        collected_data = collected_data or {}

        result = PersonalizationResult(personalization_applied=True)

        # === 1. Adaptive Style ===
        if flags.personalization_adaptive_style and envelope:
            result.style = self._select_style(envelope)
        else:
            result.style = StyleParameters()

        # === 2. Industry Detection ===
        industry_result = self._detect_industry(collected_data, messages)
        result.industry_context = self._build_industry_context(industry_result)

        # === 3. Business Context (по размеру) ===
        result.business_context = self._build_business_context(collected_data)

        # === 4. Session Memory (effective actions) ===
        if flags.personalization_session_memory and action_tracker:
            result.effective_actions = action_tracker.get_effective_actions()
            result.ineffective_actions = action_tracker.get_ineffective_actions()
            result.effective_actions_hint = action_tracker.get_tactical_recommendation()

        # === 5. Pain Reference ===
        pain_point = collected_data.get("pain_point")
        if pain_point:
            result.pain_reference = f"Вы упоминали про {pain_point}"
            result.has_pain_point = True

        logger.debug(
            "Personalization completed",
            style_verbosity=result.style.verbosity,
            style_empathy=result.style.empathy_level,
            industry=result.industry_context.industry,
            industry_confidence=result.industry_context.confidence,
            size_category=result.business_context.size_category,
            has_effective_actions=bool(result.effective_actions),
        )

        return result

    def _select_style(self, envelope: "ContextEnvelope") -> StyleParameters:
        """Select adaptive style based on envelope."""
        try:
            signals = BehavioralSignals.from_envelope(envelope)
            return self.style_selector.select_style(signals)
        except Exception as e:
            logger.warning(f"Style selection failed: {e}")
            return StyleParameters()

    def _detect_industry(
        self,
        collected_data: Dict[str, Any],
        messages: List[str] = None,
    ) -> IndustryDetectionResult:
        """Detect industry with caching and confidence accumulation."""
        # Если semantic отключен или нет detector - используем keyword
        if not self.industry_detector:
            return self._keyword_industry_detection(collected_data)

        try:
            result = self.industry_detector.detect(
                collected_data=collected_data,
                messages=messages,
                previous_confidence=self._industry_cache.get("confidence", 0.0),
                previous_industry=self._industry_cache.get("industry"),
            )

            # Обновляем cache
            if result.confidence > self._industry_cache.get("confidence", 0.0):
                self._industry_cache["industry"] = result.industry
                self._industry_cache["confidence"] = result.confidence

            return result

        except Exception as e:
            logger.warning(f"Industry detection failed: {e}")
            return self._keyword_industry_detection(collected_data)

    def _keyword_industry_detection(
        self, collected_data: Dict[str, Any]
    ) -> IndustryDetectionResult:
        """Fallback keyword-based industry detection."""
        result = IndustryDetectionResult(method="keyword")

        business_type = str(collected_data.get("business_type") or "").lower()

        # Простой keyword matching из v1
        industry_keywords = {
            "retail": ["магазин", "розница", "торговля", "товар"],
            "services": ["услуг", "сервис", "салон", "студия", "клиник"],
            "horeca": ["ресторан", "кафе", "общепит", "бар", "доставка еды"],
            "b2b": ["опт", "b2b", "дилер", "дистрибут", "поставщик"],
            "real_estate": ["недвижимост", "риелтор", "застройщик"],
            "it": ["it", "разработ", "софт", "digital", "агентство"],
        }

        for industry, keywords in industry_keywords.items():
            for keyword in keywords:
                if keyword in business_type:
                    result.industry = industry
                    result.confidence = 0.7
                    result.keyword_score = 0.7
                    result.matched_keywords = [keyword]
                    return result

        return result

    def _build_industry_context(
        self, detection_result: IndustryDetectionResult
    ) -> IndustryContext:
        """Build IndustryContext from detection result."""
        context = IndustryContext(
            industry=detection_result.industry,
            confidence=detection_result.confidence,
            method=detection_result.method,
        )

        # Получаем дополнительный контент если industry определена
        if detection_result.industry:
            if self.industry_detector:
                industry_data = self.industry_detector.get_industry_context(
                    detection_result.industry
                )
            else:
                industry_data = self._get_legacy_industry_context(
                    detection_result.industry
                )

            context.keywords = industry_data.get("keywords", [])
            context.examples = industry_data.get("examples", [])
            context.pain_examples = industry_data.get("pain_examples", [])

        return context

    def _get_legacy_industry_context(self, industry: str) -> Dict[str, List[str]]:
        """Get industry context from legacy data."""
        # Из v1 PersonalizationEngine
        legacy_contexts = {
            "retail": {
                "keywords": ["магазин", "розница", "торговля", "товар"],
                "examples": ["учёт товаров", "остатки", "поставщики"],
                "pain_examples": ["пересортица", "недостачи", "списания"],
            },
            "services": {
                "keywords": ["услуг", "сервис", "салон", "студия", "клиник"],
                "examples": ["запись клиентов", "расписание", "услуги"],
                "pain_examples": ["пропущенные записи", "накладки", "забытые клиенты"],
            },
            "horeca": {
                "keywords": ["ресторан", "кафе", "общепит", "бар", "доставка еды"],
                "examples": ["столики", "заказы", "меню"],
                "pain_examples": ["потерянные заказы", "очереди", "учёт продуктов"],
            },
            "b2b": {
                "keywords": ["опт", "b2b", "дилер", "дистрибут", "поставщик"],
                "examples": ["контракты", "отгрузки", "дебиторка"],
                "pain_examples": ["долгие сделки", "потерянные контакты", "забытые follow-up"],
            },
            "real_estate": {
                "keywords": ["недвижимост", "риелтор", "застройщик", "агентство недвиж"],
                "examples": ["объекты", "показы", "сделки"],
                "pain_examples": ["потерянные лиды", "забытые показы", "конкуренция"],
            },
            "it": {
                "keywords": ["it", "разработ", "софт", "digital", "агентство"],
                "examples": ["проекты", "задачи", "клиенты"],
                "pain_examples": ["срывы сроков", "потеря контекста", "нет прозрачности"],
            },
        }

        return legacy_contexts.get(industry, {"keywords": [], "examples": [], "pain_examples": []})

    def _build_business_context(self, collected_data: Dict[str, Any]) -> BusinessContext:
        """Build BusinessContext from collected data."""
        context = BusinessContext()

        # Получаем размер компании
        company_size = collected_data.get("company_size")
        if company_size is not None:
            try:
                company_size = int(company_size)
                context.company_size = company_size
            except (ValueError, TypeError):
                company_size = 0

            # Определяем категорию
            context.size_category = self._get_size_category(company_size)

            # Получаем контекст для размера
            bc = self.BUSINESS_CONTEXTS.get(
                context.size_category, self.BUSINESS_CONTEXTS["small"]
            )

            context.size_label = bc["size_label"]
            context.pain_focus = bc["pain_focus"]
            context.value_prop = bc["value_prop"]
            context.objection_counter = bc["objection_counter"]
            context.demo_pitch = bc["demo_pitch"]

        return context

    def _get_size_category(self, company_size: int) -> str:
        """Determine size category from company size."""
        if company_size <= 0:
            return "small"

        for category, (min_size, max_size) in self.SIZE_THRESHOLDS.items():
            if min_size <= company_size <= max_size:
                return category

        return "large"

    def reset(self) -> None:
        """Reset engine state for new conversation."""
        self._industry_cache = {
            "industry": None,
            "confidence": 0.0,
        }

    # === Legacy compatibility methods ===

    @classmethod
    def get_objection_counter(
        cls, collected_data: Dict[str, Any], objection_type: str = "price"
    ) -> str:
        """
        Legacy method: Get objection counter for compatibility.

        Args:
            collected_data: Collected client data
            objection_type: Type of objection

        Returns:
            Counter argument string
        """
        company_size = collected_data.get("company_size", 0)
        try:
            company_size = int(company_size)
        except (ValueError, TypeError):
            company_size = 0

        size_category = "small"
        for cat, (min_size, max_size) in cls.SIZE_THRESHOLDS.items():
            if min_size <= company_size <= max_size:
                size_category = cat
                break

        bc = cls.BUSINESS_CONTEXTS.get(size_category, cls.BUSINESS_CONTEXTS["small"])

        if objection_type == "price":
            return bc["objection_counter"]
        elif objection_type == "no_time":
            return bc["demo_pitch"]
        else:
            return bc["value_prop"]
