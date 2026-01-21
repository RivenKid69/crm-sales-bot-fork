"""
Multi-Tier Fallback Handler для CRM Sales Bot.

4-уровневая система fallback для восстановления диалога.

Уровни:
- Tier 1: Переформулировать вопрос
- Tier 2: Предложить варианты (кнопки)
- Tier 3: Предложить skip
- Tier 4: Graceful exit

По исследованию Nexus Flow: 74% диалогов восстанавливаются с правильным fallback.

Использование:
    from fallback_handler import FallbackHandler

    handler = FallbackHandler()
    response = handler.get_fallback("fallback_tier_1", "spin_situation", context)

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
- Integrated with conditions system for declarative decision making
- Added tracing support for observability
- Enhanced logging with events and metrics
"""

from dataclasses import dataclass, field
from random import choice
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from src.config_loader import FlowConfig, LoadedConfig

from logger import logger
from src.conditions.fallback import (
    FallbackContext,
    fallback_registry,
    FALLBACK_TIERS,
)
from src.conditions.trace import EvaluationTrace, Resolution
from src.yaml_config.constants import (
    FALLBACK_REPHRASE_TEMPLATES,
    FALLBACK_OPTIONS_TEMPLATES,
    FALLBACK_DEFAULT_REPHRASE,
    FALLBACK_DEFAULT_OPTIONS,
)


@dataclass
class FallbackResponse:
    """Структура ответа fallback"""
    message: str
    options: Optional[List[str]] = None  # Для tier_2
    action: str = "continue"             # continue, skip, close
    next_state: Optional[str] = None     # Куда перейти при skip
    trace: Optional[EvaluationTrace] = None  # Трассировка для отладки


@dataclass
class FallbackStats:
    """Статистика использования fallback"""
    total_count: int = 0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    state_counts: Dict[str, int] = field(default_factory=dict)
    last_tier: Optional[str] = None
    last_state: Optional[str] = None
    # Dynamic CTA tracking
    dynamic_cta_counts: Dict[str, int] = field(default_factory=dict)


class FallbackHandler:
    """
    4-уровневая система fallback для восстановления диалога.

    Tier 1: Переформулировать вопрос (разные варианты)
    Tier 2: Предложить варианты (кнопки)
    Tier 3: Предложить skip
    Tier 4: Graceful exit
    """

    # Tier 1: Переформулировать вопрос (загружается из YAML конфига)
    # Fallback на пустой dict если конфиг не загружен
    REPHRASE_TEMPLATES: Dict[str, List[str]] = FALLBACK_REPHRASE_TEMPLATES or {}

    # Tier 2: Предложить варианты (кнопки) — загружается из YAML конфига
    OPTIONS_TEMPLATES: Dict[str, Dict[str, Any]] = FALLBACK_OPTIONS_TEMPLATES or {}

    # Динамические подсказки по контексту (priority descending)
    DYNAMIC_CTA_OPTIONS: Dict[str, Dict[str, Any]] = {
        "competitor_mentioned": {
            "question": "Что важнее всего при выборе системы?",
            "options": [
                "Сравнить функции с {competitor}",
                "Узнать о переходе с {competitor}",
                "Посмотреть демо",
                "Узнать цены"
            ],
            "priority": 10
        },
        "pain_losing_clients": {
            "question": "Что поможет решить эту проблему?",
            "options": [
                "Автоматические напоминания клиентам",
                "Контроль работы менеджеров",
                "Аналитика по клиентам",
                "Посмотреть как это работает"
            ],
            "priority": 8
        },
        "pain_no_control": {
            "question": "Какой контроль для вас важнее?",
            "options": [
                "Видеть всех клиентов в одном месте",
                "Контроль задач и сроков",
                "Отчёты и аналитика",
                "Посмотреть как это работает"
            ],
            "priority": 8
        },
        "pain_manual_work": {
            "question": "Что хотелось бы автоматизировать?",
            "options": [
                "Напоминания и follow-up",
                "Отчёты и документы",
                "Распределение заявок",
                "Посмотреть возможности"
            ],
            "priority": 8
        },
        "large_company": {
            "question": "Что важнее для вашей команды?",
            "options": [
                "Интеграции с другими системами",
                "Права доступа и роли",
                "Масштабируемость",
                "Запланировать демо"
            ],
            "priority": 5
        },
        "small_company": {
            "question": "С чего хотите начать?",
            "options": [
                "Узнать базовые функции",
                "Быстрый старт за 15 минут",
                "Узнать стоимость",
                "Попробовать бесплатно"
            ],
            "priority": 5
        },
        "after_price_question": {
            "question": "Что ещё хотите узнать?",
            "options": [
                "Условия оплаты",
                "Есть ли пробный период",
                "Что входит в тариф",
                "Запланировать демо"
            ],
            "priority": 7
        },
        "after_features_question": {
            "question": "Какие функции интересуют больше всего?",
            "options": [
                "Автоматизация рутины",
                "Аналитика и отчёты",
                "Интеграции",
                "Показать всё на демо"
            ],
            "priority": 6
        },
    }

    # Подпись для текстовых вариантов
    OPTIONS_FOOTER = "\nНапишите номер или ответьте своими словами."

    # Tier 3: Предложить skip
    SKIP_TEMPLATES: List[str] = [
        "Если сложно ответить — можем пропустить этот вопрос и перейти дальше.",
        "Не страшно, давайте пока пропустим это и вернёмся позже если нужно.",
        "Окей, двигаемся дальше — этот вопрос не критичен.",
        "Давайте пропустим и перейдём к следующему шагу.",
    ]

    # Карта переходов при skip (DEPRECATED: use skip_map parameter or FlowConfig)
    # Kept as fallback for backward compatibility
    DEFAULT_SKIP_MAP: Dict[str, str] = {
        "greeting": "spin_situation",
        "spin_situation": "spin_problem",
        "spin_problem": "spin_implication",
        "spin_implication": "spin_need_payoff",
        "spin_need_payoff": "presentation",
        "presentation": "close",
        "handle_objection": "soft_close",
    }
    # Backward compatibility alias
    SKIP_MAP = DEFAULT_SKIP_MAP

    # Tier 4: Graceful exit
    EXIT_TEMPLATES: List[str] = [
        "Похоже, сейчас не лучшее время для подробного разговора. Могу прислать информацию на почту — удобно?",
        "Давайте так: я оставлю контакты, и вы свяжетесь когда будет удобно. Хорошо?",
        "Понимаю, что времени мало. Могу просто прислать краткую информацию — посмотрите когда будет время.",
        "Не буду отнимать время. Оставьте контакт — пришлю информацию, а вы решите.",
    ]

    # Дефолтные fallback сообщения (загружаются из YAML конфига)
    # FIX: DEFAULT_REPHRASE теперь список для вариативности
    DEFAULT_REPHRASE: List[str] = FALLBACK_DEFAULT_REPHRASE or ["Давайте попробую спросить иначе..."]
    DEFAULT_OPTIONS = FALLBACK_DEFAULT_OPTIONS or {
        "question": "Что вас интересует?",
        "options": ["Подробнее о системе", "Цены", "Демо", "Связаться позже"]
    }

    def __init__(
        self,
        enable_tracing: bool = True,
        skip_map: Optional[Dict[str, str]] = None,
        flow: Optional["FlowConfig"] = None,
        config: Optional["LoadedConfig"] = None
    ):
        """
        Initialize FallbackHandler.

        Args:
            enable_tracing: Whether to enable condition evaluation tracing
            skip_map: Custom skip map (state -> next_state). If not provided,
                      will try to get from flow.skip_map, or use DEFAULT_SKIP_MAP.
            flow: FlowConfig to get skip_map from (auto-builds from transitions)
            config: LoadedConfig for templates (rephrase, options, defaults)
        """
        self._stats = FallbackStats()
        self._used_templates: Dict[str, List[str]] = {}  # Для избежания повторов
        self._enable_tracing = enable_tracing

        # Determine skip_map priority: explicit > flow > default
        if skip_map is not None:
            self._skip_map = skip_map
        elif flow is not None:
            self._skip_map = flow.skip_map
        else:
            self._skip_map = self.DEFAULT_SKIP_MAP

        # Load templates from config (fallback to class constants)
        self._rephrase_templates = self._load_rephrase_templates(config)
        self._options_templates = self._load_options_templates(config)
        self._default_rephrase = self._load_default_rephrase(config)
        self._default_options = self._load_default_options(config)

    def _load_rephrase_templates(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, List[str]]:
        """Load rephrase templates from config or use class default."""
        if config is None:
            return self.REPHRASE_TEMPLATES
        templates = config.fallback.get("rephrase_templates", {})
        return templates if templates else self.REPHRASE_TEMPLATES

    def _load_options_templates(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, Dict[str, Any]]:
        """Load options templates from config or use class default."""
        if config is None:
            return self.OPTIONS_TEMPLATES
        templates = config.fallback.get("options_templates", {})
        return templates if templates else self.OPTIONS_TEMPLATES

    def _load_default_rephrase(self, config: Optional["LoadedConfig"]) -> List[str]:
        """Load default rephrase from config or use class default.

        FIX: Now returns List[str] for variability.
        """
        if config is None:
            return self.DEFAULT_REPHRASE
        raw = config.fallback.get("default_rephrase", self.DEFAULT_REPHRASE)
        # Handle both string and list formats
        if isinstance(raw, list):
            return raw
        return [raw]

    def _load_default_options(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, Any]:
        """Load default options from config or use class default."""
        if config is None:
            return self.DEFAULT_OPTIONS
        return config.fallback.get("default_options", self.DEFAULT_OPTIONS)

    def reset(self) -> None:
        """Сбросить состояние для нового диалога"""
        self._stats = FallbackStats()
        self._used_templates.clear()

    @property
    def stats(self) -> FallbackStats:
        """Статистика использования"""
        return self._stats

    def _create_fallback_context(
        self,
        tier: str,
        state: str,
        context: Optional[Dict] = None
    ) -> FallbackContext:
        """
        Create FallbackContext for condition evaluation.

        Args:
            tier: Current fallback tier
            state: Current dialogue state
            context: Additional context data

        Returns:
            Initialized FallbackContext
        """
        context = context or {}
        return FallbackContext.from_handler_stats(
            stats=self.get_stats_dict(),
            state=state,
            context=context,
            current_tier=tier
        )

    def _create_trace(self, tier: str, state: str) -> Optional[EvaluationTrace]:
        """Create evaluation trace if tracing is enabled."""
        if not self._enable_tracing:
            return None
        return EvaluationTrace(
            rule_name=f"fallback_{tier}",
            intent="fallback",
            state=state,
            domain="fallback"
        )

    def get_fallback(
        self,
        tier: str,
        state: str,
        context: Optional[Dict] = None
    ) -> FallbackResponse:
        """
        Получить fallback response для указанного уровня и состояния.

        Args:
            tier: Уровень fallback (fallback_tier_1, ..., soft_close)
            state: Текущее состояние FSM
            context: Дополнительный контекст (pain_point, company_size, etc.)

        Returns:
            FallbackResponse с сообщением и возможными опциями
        """
        start_time = time.perf_counter()
        context = context or {}

        # Normalize tier for backward compatibility
        # "fallback_tier_4" was renamed to "soft_close"
        if tier == "fallback_tier_4":
            tier = "soft_close"

        # Обновляем статистику
        self._stats.total_count += 1
        self._stats.tier_counts[tier] = self._stats.tier_counts.get(tier, 0) + 1
        self._stats.state_counts[state] = self._stats.state_counts.get(state, 0) + 1
        self._stats.last_tier = tier
        self._stats.last_state = state

        # Create context and trace for condition evaluation
        fb_context = self._create_fallback_context(tier, state, context)
        trace = self._create_trace(tier, state)

        # Log event
        logger.event(
            "fallback_triggered",
            tier=tier,
            state=state,
            total_fallbacks=self._stats.total_count,
            frustration_level=fb_context.frustration_level,
            engagement_level=fb_context.engagement_level
        )

        # Check for immediate escalation using conditions
        if self._should_immediate_escalate(fb_context, trace):
            response = self._tier_4_exit(context, trace)
            self._log_metrics(start_time, tier, "immediate_escalation", trace)
            return response

        # Process based on tier
        if tier == "fallback_tier_1":
            response = self._tier_1_rephrase(state, context, fb_context, trace)
        elif tier == "fallback_tier_2":
            response = self._tier_2_options(state, context, fb_context, trace)
        elif tier == "fallback_tier_3":
            response = self._tier_3_skip(state, context, fb_context, trace)
        else:  # tier_4 or soft_close
            response = self._tier_4_exit(context, trace)

        self._log_metrics(start_time, tier, "normal", trace)
        return response

    def _should_immediate_escalate(
        self,
        ctx: FallbackContext,
        trace: Optional[EvaluationTrace]
    ) -> bool:
        """Check if immediate escalation to soft_close is needed."""
        result = fallback_registry.evaluate("needs_immediate_escalation", ctx, trace)
        if result:
            logger.event(
                "fallback_immediate_escalation",
                tier=ctx.current_tier,
                state=ctx.state,
                frustration_level=ctx.frustration_level,
                total_fallbacks=ctx.total_fallbacks
            )
        return result

    def _log_metrics(
        self,
        start_time: float,
        tier: str,
        resolution: str,
        trace: Optional[EvaluationTrace]
    ) -> None:
        """Log metrics for fallback processing."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        conditions_checked = trace.conditions_checked if trace else 0

        logger.metric(
            "fallback_processing_time",
            round(elapsed_ms, 3),
            tier=tier,
            resolution=resolution,
            conditions_checked=conditions_checked,
            total_fallbacks=self._stats.total_count
        )

    def _tier_1_rephrase(
        self,
        state: str,
        context: Dict,
        fb_context: Optional[FallbackContext] = None,
        trace: Optional[EvaluationTrace] = None
    ) -> FallbackResponse:
        """Tier 1: Переформулировать вопрос"""
        # FIX: _default_rephrase теперь список, не нужно оборачивать в []
        templates = self._rephrase_templates.get(state, self._default_rephrase)

        # Evaluate if rephrase is appropriate using conditions
        if fb_context and trace:
            can_rephrase = fallback_registry.evaluate("can_try_rephrase", fb_context, trace)
            if not can_rephrase:
                # Escalate to tier 2 if rephrase not appropriate
                logger.event(
                    "fallback_tier_escalated",
                    from_tier="fallback_tier_1",
                    to_tier="fallback_tier_2",
                    reason="rephrase_not_appropriate"
                )
                return self._tier_2_options(state, context, fb_context, trace)

        # Выбираем не использованный недавно шаблон
        message = self._get_unused_template(f"rephrase_{state}", templates)

        if trace:
            trace.set_result("rephrase", Resolution.SIMPLE, None)

        return FallbackResponse(
            message=message,
            options=None,
            action="continue",
            next_state=None,
            trace=trace
        )

    def _tier_2_options(
        self,
        state: str,
        context: Dict,
        fb_context: Optional[FallbackContext] = None,
        trace: Optional[EvaluationTrace] = None
    ) -> FallbackResponse:
        """
        Tier 2: Предложить варианты (текстовые подсказки).

        Динамические подсказки на основе контекста:
        1. competitor_mentioned → сравнение и переход
        2. pain_point → решение конкретной проблемы
        3. last_intent → релевантные follow-up
        4. company_size → масштаб решения
        5. Fallback к статичным если контекст пуст
        """
        from feature_flags import flags

        if not flags.is_enabled("dynamic_cta_fallback"):
            return self._get_static_tier_2_options(state, context, trace)

        # Use conditions to check if dynamic CTA is appropriate
        if fb_context:
            should_use_dynamic = fallback_registry.evaluate(
                "should_use_dynamic_cta", fb_context, trace
            )
            if not should_use_dynamic:
                return self._get_static_tier_2_options(state, context, trace)

        collected = context.get("collected_data", {})
        last_intent = context.get("last_intent")

        # Use conditions to select best dynamic options
        best = self._select_dynamic_options_with_conditions(
            collected, last_intent, state, fb_context, trace
        )

        if best:
            option_type = best.get("_type", "unknown")
            self._stats.dynamic_cta_counts[option_type] = \
                self._stats.dynamic_cta_counts.get(option_type, 0) + 1

            logger.event(
                "fallback_dynamic_cta_selected",
                option_type=option_type,
                state=state,
                has_competitor=fb_context.competitor_mentioned if fb_context else False,
                pain_category=fb_context.pain_category if fb_context else None
            )

            # Форматируем сообщение с нумерованными вариантами
            message = self._format_options_message(
                question=best["question"],
                options=best["options"][:4],
                collected_data=collected
            )

            if trace:
                trace.set_result(
                    f"dynamic_cta_{option_type}",
                    Resolution.CONDITION_MATCHED,
                    option_type
                )

            return FallbackResponse(
                message=message,
                options=best["options"][:4],  # Сохраняем для аналитики
                action="continue",
                next_state=None,
                trace=trace
            )

        return self._get_static_tier_2_options(state, context, trace)

    def _get_static_tier_2_options(
        self,
        state: str,
        context: Dict,
        trace: Optional[EvaluationTrace] = None
    ) -> FallbackResponse:
        """Статичные варианты (оригинальное поведение)."""
        template = self._options_templates.get(state)

        if template:
            collected = context.get("collected_data", {})
            message = self._format_options_message(
                question=template["question"],
                options=template["options"],
                collected_data=collected
            )

            if trace:
                trace.set_result("static_options", Resolution.DEFAULT, None)

            return FallbackResponse(
                message=message,
                options=template["options"].copy(),
                action="continue",
                next_state=None,
                trace=trace
            )

        return self._tier_1_rephrase(state, context, trace=trace)

    def _select_dynamic_options_with_conditions(
        self,
        collected: Dict,
        last_intent: Optional[str],
        state: str,
        fb_context: Optional[FallbackContext],
        trace: Optional[EvaluationTrace]
    ) -> Optional[Dict]:
        """
        Select best dynamic options using conditions.

        Uses condition registry to evaluate which dynamic CTA is most appropriate.
        Returns the best option based on priority.
        """
        if not fb_context:
            # Fallback to old method if no context
            return self._select_dynamic_options(collected, last_intent, state)

        candidates = []

        # Priority 10: Competitor - use condition
        if fallback_registry.evaluate("has_competitor_context", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("competitor_mentioned")
            if opt:
                candidates.append({**opt, "_type": "competitor_mentioned"})

        # Priority 8: Pain point - use conditions
        if fallback_registry.evaluate("has_pain_losing_clients", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("pain_losing_clients")
            if opt:
                candidates.append({**opt, "_type": "pain_losing_clients"})
        elif fallback_registry.evaluate("has_pain_no_control", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("pain_no_control")
            if opt:
                candidates.append({**opt, "_type": "pain_no_control"})
        elif fallback_registry.evaluate("has_pain_manual_work", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("pain_manual_work")
            if opt:
                candidates.append({**opt, "_type": "pain_manual_work"})

        # Priority 7: Last intent - use conditions
        if fallback_registry.evaluate("last_intent_price_related", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("after_price_question")
            if opt:
                candidates.append({**opt, "_type": "after_price_question"})
        elif fallback_registry.evaluate("last_intent_feature_related", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("after_features_question")
            if opt:
                candidates.append({**opt, "_type": "after_features_question"})

        # Priority 5: Company size - use conditions
        if fallback_registry.evaluate("is_large_company", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("large_company")
            if opt:
                candidates.append({**opt, "_type": "large_company"})
        elif fallback_registry.evaluate("is_small_company", fb_context, trace):
            opt = self.DYNAMIC_CTA_OPTIONS.get("small_company")
            if opt:
                candidates.append({**opt, "_type": "small_company"})

        # Sort by priority and return best
        if candidates:
            candidates.sort(key=lambda x: x.get("priority", 0), reverse=True)
            return candidates[0]

        return None

    def _format_options_message(
        self,
        question: str,
        options: List[str],
        collected_data: Dict
    ) -> str:
        """
        Форматирует сообщение с нумерованными вариантами.

        Пример вывода:
            Что важнее всего при выборе системы?

            1. Сравнить функции с Битрикс
            2. Узнать о переходе
            3. Посмотреть демо
            4. Узнать цены

            Напишите номер или ответьте своими словами.
        """
        # Подставляем имя конкурента если есть placeholder
        competitor_name = collected_data.get("competitor_name", "текущей системой")
        formatted_options = []

        for i, opt in enumerate(options, 1):
            formatted_opt = opt.format(competitor=competitor_name)
            formatted_options.append(f"{i}. {formatted_opt}")

        options_text = "\n".join(formatted_options)

        return f"{question}\n\n{options_text}{self.OPTIONS_FOOTER}"

    def _select_dynamic_options(
        self,
        collected: Dict,
        last_intent: Optional[str],
        state: str
    ) -> Optional[Dict]:
        """
        Выбрать лучшие динамические подсказки по приоритету.

        Приоритеты:
            10 - competitor_mentioned (самый высокий)
             8 - pain_point
             7 - last_intent (price, features)
             5 - company_size
        """
        candidates = []

        # Priority 10: Competitor
        if collected.get("competitor_mentioned"):
            opt = self.DYNAMIC_CTA_OPTIONS.get("competitor_mentioned")
            if opt:
                candidates.append({**opt, "_type": "competitor_mentioned"})

        # Priority 8: Pain point (используем pain_category из data_extractor)
        pain_category = collected.get("pain_category")
        if pain_category:
            option_key = f"pain_{pain_category}"
            opt = self.DYNAMIC_CTA_OPTIONS.get(option_key)
            if opt:
                candidates.append({**opt, "_type": option_key})

        # Priority 7: Last intent
        if last_intent:
            if last_intent in ["price_question", "pricing_details", "objection_price"]:
                opt = self.DYNAMIC_CTA_OPTIONS.get("after_price_question")
                if opt:
                    candidates.append({**opt, "_type": "after_price_question"})
            elif last_intent in ["question_features", "question_integrations", "question_how_works"]:
                opt = self.DYNAMIC_CTA_OPTIONS.get("after_features_question")
                if opt:
                    candidates.append({**opt, "_type": "after_features_question"})

        # Priority 5: Company size
        size = collected.get("company_size", 0)
        if isinstance(size, str):
            try:
                size = int(size)
            except ValueError:
                size = 0

        if size > 20:
            opt = self.DYNAMIC_CTA_OPTIONS.get("large_company")
            if opt:
                candidates.append({**opt, "_type": "large_company"})
        elif 0 < size <= 5:
            opt = self.DYNAMIC_CTA_OPTIONS.get("small_company")
            if opt:
                candidates.append({**opt, "_type": "small_company"})

        # Сортируем по приоритету и возвращаем лучший
        if candidates:
            candidates.sort(key=lambda x: x.get("priority", 0), reverse=True)
            return candidates[0]

        return None

    def _tier_3_skip(
        self,
        state: str,
        context: Dict,
        fb_context: Optional[FallbackContext] = None,
        trace: Optional[EvaluationTrace] = None
    ) -> FallbackResponse:
        """Tier 3: Предложить skip"""
        # Check using conditions if skip is appropriate
        if fb_context and trace:
            should_skip = fallback_registry.evaluate("should_skip_to_next_state", fb_context, trace)
            if not should_skip:
                # Still offer skip but log that conditions weren't optimal
                logger.event(
                    "fallback_skip_suboptimal",
                    state=state,
                    fallbacks_in_state=fb_context.fallbacks_in_state,
                    frustration_level=fb_context.frustration_level
                )

        next_state = self._skip_map.get(state, "presentation")
        message = self._get_unused_template("skip", self.SKIP_TEMPLATES)

        if trace:
            trace.set_result(f"skip_to_{next_state}", Resolution.SIMPLE, None)

        logger.event(
            "fallback_skip_offered",
            from_state=state,
            to_state=next_state
        )

        return FallbackResponse(
            message=message,
            options=None,
            action="skip",
            next_state=next_state,
            trace=trace
        )

    def _tier_4_exit(
        self,
        context: Dict,
        trace: Optional[EvaluationTrace] = None
    ) -> FallbackResponse:
        """Tier 4: Graceful exit"""
        message = self._get_unused_template("exit", self.EXIT_TEMPLATES)

        if trace:
            trace.set_result("graceful_exit", Resolution.FALLBACK, None)

        logger.event(
            "fallback_graceful_exit",
            total_fallbacks=self._stats.total_count,
            last_state=self._stats.last_state
        )

        return FallbackResponse(
            message=message,
            options=None,
            action="close",
            next_state="soft_close",
            trace=trace
        )

    def _get_unused_template(self, key: str, templates: List[str]) -> str:
        """
        Получить шаблон, не использованный недавно.
        Помогает избежать повторений.
        """
        if not templates:
            return self.DEFAULT_REPHRASE

        if key not in self._used_templates:
            self._used_templates[key] = []

        used = self._used_templates[key]
        available = [t for t in templates if t not in used]

        if not available:
            # Все использованы — сбросить историю
            self._used_templates[key] = []
            available = templates

        selected = choice(available)
        self._used_templates[key].append(selected)

        # Ограничиваем историю
        max_history = max(1, len(templates) // 2)
        if len(self._used_templates[key]) > max_history:
            self._used_templates[key] = self._used_templates[key][-max_history:]

        return selected

    def get_stats_dict(self) -> Dict:
        """Получить статистику в виде словаря"""
        return {
            "total_count": self._stats.total_count,
            "tier_counts": self._stats.tier_counts.copy(),
            "state_counts": self._stats.state_counts.copy(),
            "last_tier": self._stats.last_tier,
            "last_state": self._stats.last_state,
            "dynamic_cta_counts": self._stats.dynamic_cta_counts.copy(),
        }

    def escalate_tier(self, current_tier: str) -> str:
        """
        Получить следующий уровень fallback (эскалация).

        Args:
            current_tier: Текущий уровень

        Returns:
            Следующий уровень или soft_close
        """
        try:
            current_index = FALLBACK_TIERS.index(current_tier)
            next_index = min(current_index + 1, len(FALLBACK_TIERS) - 1)
            next_tier = FALLBACK_TIERS[next_index]

            logger.event(
                "fallback_tier_escalated",
                from_tier=current_tier,
                to_tier=next_tier
            )

            return next_tier
        except ValueError:
            return "soft_close"

    def smart_escalate(
        self,
        state: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Smart tier escalation using conditions.

        Determines whether to escalate based on context signals
        like frustration, fallback count, and engagement.

        Args:
            state: Current dialogue state
            context: Conversation context

        Returns:
            Appropriate tier for the situation
        """
        current_tier = self._stats.last_tier or "fallback_tier_1"
        fb_context = self._create_fallback_context(current_tier, state, context)
        trace = self._create_trace(current_tier, state)

        # Check if immediate escalation needed
        if fallback_registry.evaluate("needs_immediate_escalation", fb_context, trace):
            logger.event(
                "fallback_smart_escalation",
                reason="immediate_escalation",
                to_tier="soft_close"
            )
            return "soft_close"

        # Check if should escalate
        if fallback_registry.evaluate("should_escalate_tier", fb_context, trace):
            next_tier = self.escalate_tier(current_tier)
            logger.event(
                "fallback_smart_escalation",
                reason="condition_triggered",
                from_tier=current_tier,
                to_tier=next_tier
            )
            return next_tier

        # Check if can recover
        if not fallback_registry.evaluate("can_recover", fb_context, trace):
            logger.event(
                "fallback_smart_escalation",
                reason="cannot_recover",
                to_tier="soft_close"
            )
            return "soft_close"

        # Stay at current tier
        return current_tier

    def get_recommended_tier(
        self,
        state: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Get recommended tier based on current context.

        This is useful for starting a fallback sequence
        at an appropriate level.

        Args:
            state: Current dialogue state
            context: Conversation context

        Returns:
            Recommended starting tier
        """
        context = context or {}
        # Create a temporary context for the first tier
        fb_context = self._create_fallback_context("fallback_tier_1", state, context)

        # If frustration is high, start at tier 2
        if fb_context.frustration_level >= 2:
            return "fallback_tier_2"

        # If many total fallbacks, start at tier 2
        if fb_context.total_fallbacks >= 3:
            return "fallback_tier_2"

        # If critical, go straight to exit
        if fb_context.frustration_level >= 4:
            return "soft_close"

        return "fallback_tier_1"


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("FALLBACK HANDLER DEMO")
    print("=" * 60)

    handler = FallbackHandler()

    # Демо всех уровней
    tiers = ["fallback_tier_1", "fallback_tier_2", "fallback_tier_3", "soft_close"]
    states = ["spin_situation", "spin_problem", "presentation"]

    for tier in tiers:
        print(f"\n--- {tier.upper()} ---")
        for state in states:
            response = handler.get_fallback(tier, state, {})
            print(f"\nState: {state}")
            print(f"  Message: {response.message}")
            if response.options:
                print(f"  Options: {response.options}")
            print(f"  Action: {response.action}")
            if response.next_state:
                print(f"  Next state: {response.next_state}")

    print("\n" + "=" * 60)
    print("STATS")
    print("=" * 60)
    print(json.dumps(handler.get_stats_dict(), indent=2, ensure_ascii=False))

    print("\n--- Tier Escalation ---")
    tier = "fallback_tier_1"
    for _ in range(4):
        print(f"{tier} -> ", end="")
        tier = handler.escalate_tier(tier)
    print(tier)

    print("\n" + "=" * 60)
