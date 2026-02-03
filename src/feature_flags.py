"""
Feature Flags для CRM Sales Bot.

Контроль постепенного включения фич.
Позволяет откатить любое изменение без деплоя.

Использование:
    from feature_flags import flags

    if flags.tone_analysis:
        # Новая логика анализа тона
        pass

    if flags.is_enabled("custom_flag"):
        # Проверка произвольного флага
        pass
"""

from typing import Any, Dict, List, Set
from src.settings import settings


class FeatureFlags:
    """
    Система feature flags для постепенного включения фич.

    Особенности:
    - Загрузка из settings.yaml
    - Override через environment variables
    - Типизированные property для основных флагов
    - Метод is_enabled() для произвольных флагов
    - Поддержка групп флагов
    """

    # Дефолтные значения флагов (используются если не указаны в settings)
    DEFAULTS: Dict[str, bool] = {
        # Фаза 2: Естественность диалога
        "tone_analysis": True,            # Анализ тона клиента (критично для frustration)
        "response_variations": True,      # Вариативность ответов (безопасно)

        # Фаза 3: Оптимизация SPIN Flow
        "lead_scoring": False,            # Скоринг лидов для адаптивного SPIN
        "circular_flow": False,           # Возврат назад по фазам (опасно)

        # Фаза 1: Защита и надёжность
        "multi_tier_fallback": True,      # 4-уровневый fallback (критично)
        "conversation_guard": True,       # Защита от зацикливания

        # Фаза 0: Инфраструктура
        "structured_logging": True,       # JSON логи
        "metrics_tracking": True,         # Трекинг метрик

        # Дополнительные флаги
        "personalization": False,         # Персонализация на основе данных
        "objection_handler": False,       # Продвинутая обработка возражений
        "cta_generator": False,           # Генерация Call-to-Action

        # Фаза 4: Intent Disambiguation
        "intent_disambiguation": False,   # Уточнение намерения при близких scores (legacy HybridClassifier)
        "unified_disambiguation": True,   # Унифицированный disambiguation для LLM и Hybrid классификаторов

        # Фаза 4.5: Cascade Classifier (семантический fallback)
        "cascade_classifier": True,       # Каскадный классификатор с эмбеддингами

        # Фаза 4.6: Semantic Objection Detection
        "semantic_objection_detection": True,  # Semantic fallback для возражений

        # Фаза 5: Dynamic CTA Fallback
        "dynamic_cta_fallback": False,    # Динамические подсказки в fallback tier_2

        # === Context Policy (PLAN_CONTEXT_POLICY.md) ===
        # Phase 0: Инфраструктура контекста
        "context_full_envelope": True,    # Полный ContextEnvelope для всех подсистем
        "context_shadow_mode": False,     # Shadow mode: логируем решения без применения

        # Phase 2: Естественность диалога
        "context_response_directives": True,  # ResponseDirectives для генератора

        # Phase 3: Policy overlays
        "context_policy_overlays": True,   # DialoguePolicy action overrides
        "context_engagement_v2": False,    # Улучшенный расчёт engagement

        # Phase 5: CTA с памятью
        "context_cta_memory": False,       # CTA с учётом episodic memory

        # === Cascade Tone Analyzer (Phase 5) ===
        "cascade_tone_analyzer": True,     # Master switch для каскадного анализатора
        "tone_semantic_tier2": True,       # FRIDA semantic (Tier 2)
        "tone_llm_tier3": True,            # LLM fallback (Tier 3)

        # === LLM Classifier (Phase LLM) ===
        "llm_classifier": True,            # Использовать LLM классификатор вместо Hybrid

        # === Personalization v2 (Adaptive Personalization) ===
        # NOTE: personalization_v2 intentionally disabled — requires calibration
        # of AdaptiveStyleSelector and IndustryDetectorV2 before production use.
        # Legacy PersonalizationEngine (v1) is used as fallback via _apply_legacy_personalization().
        "personalization_v2": False,              # V2 engine с behavioral adaptation
        "personalization_adaptive_style": False,  # AdaptiveStyleSelector
        "personalization_semantic_industry": False,  # IndustryDetectorV2 semantic matching
        "personalization_session_memory": False,  # EffectiveActionTracker

        # === НОВОЕ: Response Quality (Bag Fixes) ===
        "response_deduplication": True,           # Проверка на дублирующиеся ответы
        "price_question_override": True,          # Intent-aware override для вопросов о цене

        # === Guard/Fallback Intervention Fixes ===
        "guard_informative_intent_check": True,   # Проверка информативных интентов перед TIER_3
        "guard_skip_resets_fallback": True,       # Сброс fallback_response после skip action

        # === Robust Classification: ConfidenceRouter ===
        "confidence_router": True,                # Gap-based решения и graceful degradation
        "confidence_router_logging": True,        # Логирование слепых зон для self-learning

        # === State Loop Fix: Classification Refinement ===
        "classification_refinement": True,        # Контекстное уточнение коротких ответов

        # === Objection Stuck Fix: Objection Refinement ===
        "objection_refinement": True,             # Контекстная валидация objection классификаций

        # === Composite Message Refinement: Data Priority ===
        "composite_refinement": True,             # Приоритет извлечения данных над мета-интентами

        # === Option Selection Refinement: Disambiguation Assist Fix ===
        "option_selection_refinement": True,      # Обработка выбора вариантов ("1", "2", "первое")

        # === Universal Refinement Pipeline ===
        "refinement_pipeline": True,              # Использовать универсальный RefinementPipeline вместо отдельных слоёв

        # === Confidence Calibration: Scientific LLM Confidence Calibration ===
        "confidence_calibration": True,           # Калибровка confidence для решения проблемы overconfident LLM

        # === Response Diversity: Anti-Monotony Engine ===
        "response_diversity": True,               # Post-processing замена монотонных вступлений
        "response_diversity_logging": True,       # Логирование замен для мониторинга

        # === Question Deduplication: Prevent Re-asking Already Answered Questions ===
        "question_deduplication": True,           # Фильтрация вопросов по collected_data
        "question_deduplication_logging": True,   # Логирование фильтраций для мониторинга

        # === Apology System: Guaranteed Apology Insertion ===
        # SSoT: src/apology_ssot.py
        "apology_system": True,                   # Гарантированное добавление извинений при frustration

        # === Lost Question Fix: Secondary Intent Detection ===
        # SSoT: src/classifier/secondary_intent_detection.py
        "secondary_intent_detection": True,       # Детекция secondary intents в composite сообщениях

        # === Structural Frustration Detection ===
        "structural_frustration_detection": True,  # Behavioral frustration from dialogue patterns

        # === Greeting State Safety (Phase 1: Dialog Failure Fix) ===
        "greeting_state_safety": True,             # Category-based greeting transition overrides
        "greeting_context_refinement": True,       # Greeting context refinement layer

        # === First Contact Refinement (Objection in First Contact) ===
        "first_contact_refinement": True,          # First contact objection refinement layer

        # === Universal Stall Guard (Defense-in-Depth: Max Turns in State) ===
        "universal_stall_guard": True,             # Universal max-turns-in-state forced ejection
        "stall_guard_dual_proposal": True,         # StallGuard proposes action + transition

        # === Data-Aware Refinement (Stall Prevention) ===
        "data_aware_refinement": True,             # Promote unclear→info_provided when data extracted

        # === Phase Exhausted Source (Guard-Blackboard Race Fix) ===
        "phase_exhausted_source": True,            # PhaseExhaustedSource: options menu when phase stuck

        # === Phase Completion Gating ===
        "phase_completion_gating": True,           # has_completed_minimum_phases condition

        # === ConversationGuard in Pipeline ===
        "conversation_guard_in_pipeline": False,   # Gradual rollout: guard inside Blackboard pipeline

        # === Simulation Diagnostic Mode ===
        "simulation_diagnostic_mode": False,       # Higher sim limits for bug detection

        # === Classification fixes ===
        "intent_pattern_guard": False,             # Configurable intent pattern detection (Change 7)
        "comparison_refinement": False,            # Comparison refinement layer (Change 8)

        # === Autonomous Flow ===
        "autonomous_flow": False,                  # LLM-driven sales flow (no YAML rules)
    }

    # Группы флагов для удобного управления
    GROUPS: Dict[str, List[str]] = {
        "phase_0": ["structured_logging", "metrics_tracking"],
        "phase_1": ["multi_tier_fallback", "conversation_guard", "conversation_guard_in_pipeline"],
        "phase_2": ["tone_analysis", "response_variations", "personalization", "response_diversity", "question_deduplication", "apology_system"],
        "phase_3": ["lead_scoring", "circular_flow", "objection_handler", "cta_generator", "dynamic_cta_fallback"],
        "phase_4": ["intent_disambiguation", "unified_disambiguation", "cascade_classifier", "semantic_objection_detection"],
        "safe": ["response_variations", "response_diversity", "question_deduplication", "apology_system", "multi_tier_fallback", "structured_logging", "metrics_tracking", "conversation_guard", "cascade_classifier", "semantic_objection_detection"],
        "risky": ["circular_flow", "lead_scoring"],
        # Context Policy groups (PLAN_CONTEXT_POLICY.md)
        "context_phase_0": ["context_full_envelope", "context_shadow_mode"],
        "context_phase_2": ["context_response_directives"],
        "context_phase_3": ["context_policy_overlays", "context_engagement_v2"],
        "context_phase_5": ["context_cta_memory"],
        "context_all": [
            "context_full_envelope", "context_shadow_mode",
            "context_response_directives", "context_policy_overlays",
            "context_engagement_v2", "context_cta_memory"
        ],
        "context_safe": ["context_full_envelope", "context_response_directives"],
        # Cascade Tone Analyzer groups
        "phase_5_tone": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
        "tone_safe": ["cascade_tone_analyzer"],  # Только улучшенный Tier 1
        "tone_full": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
        # Personalization v2 groups
        "personalization_v2_safe": [
            "personalization", "personalization_v2", "personalization_adaptive_style"
        ],
        "personalization_v2_full": [
            "personalization", "personalization_v2", "personalization_adaptive_style",
            "personalization_semantic_industry", "personalization_session_memory"
        ],
        # Guard/Fallback groups
        "guard_fixes": [
            "guard_informative_intent_check", "guard_skip_resets_fallback"
        ],
        # Robust Classification groups
        "robust_classification": [
            "confidence_router", "confidence_router_logging"
        ],
        # State Loop Fix groups
        "state_loop_fix": [
            "classification_refinement"
        ],
        # Objection Stuck Fix groups
        "objection_stuck_fix": [
            "objection_refinement"
        ],
        # Composite Message Refinement groups
        "composite_message_fix": [
            "composite_refinement"
        ],
        # Universal Refinement Pipeline groups
        "refinement_pipeline_all": [
            "refinement_pipeline",
            "classification_refinement",
            "composite_refinement",
            "objection_refinement",
            "confidence_calibration",
            "first_contact_refinement",
            "data_aware_refinement"
        ],
        # Confidence Calibration groups
        "confidence_calibration_all": [
            "confidence_calibration"
        ],
        # Response Diversity groups
        "response_diversity_all": [
            "response_diversity", "response_diversity_logging"
        ],
        # Lost Question Fix groups
        "lost_question_fix": [
            "secondary_intent_detection"
        ],
        # Universal Stall Guard groups
        "stall_guard": [
            "universal_stall_guard"
        ],
        # Refinement pipeline: include first_contact_refinement
        "refinement_pipeline_first_contact": [
            "first_contact_refinement"
        ],
        # Autonomous flow
        "autonomous": [
            "autonomous_flow"
        ],
    }

    def __init__(self):
        self._flags: Dict[str, bool] = {}
        self._overrides: Dict[str, bool] = {}
        self._load_flags()

    def _load_flags(self) -> None:
        """Загрузить флаги из settings и environment"""
        # Начинаем с defaults
        self._flags = self.DEFAULTS.copy()

        # Переопределяем из settings.yaml
        settings_flags = settings.get_nested("feature_flags", {})
        if isinstance(settings_flags, dict):
            for key, value in settings_flags.items():
                if isinstance(value, bool):
                    self._flags[key] = value

        # Переопределяем из environment (высший приоритет)
        import os
        for key in self._flags:
            env_key = f"FF_{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                self._flags[key] = env_value.lower() in ("true", "1", "yes", "on")

    def reload(self) -> None:
        """Перезагрузить флаги из settings"""
        self._overrides.clear()
        self._load_flags()

    def is_enabled(self, flag: str) -> bool:
        """
        Проверить включён ли флаг.

        Args:
            flag: Имя флага

        Returns:
            True если флаг включён, False иначе
        """
        # Сначала проверяем runtime overrides
        if flag in self._overrides:
            return self._overrides[flag]

        # Затем проверяем загруженные флаги
        return self._flags.get(flag, False)

    def set_override(self, flag: str, value: bool) -> None:
        """
        Установить runtime override для флага.
        Используется для тестов и динамического управления.

        Args:
            flag: Имя флага
            value: Значение
        """
        self._overrides[flag] = value

    def clear_override(self, flag: str) -> None:
        """Убрать runtime override для флага"""
        self._overrides.pop(flag, None)

    def clear_all_overrides(self) -> None:
        """Убрать все runtime overrides"""
        self._overrides.clear()

    def get_all_flags(self) -> Dict[str, bool]:
        """Получить все флаги с текущими значениями"""
        result = self._flags.copy()
        result.update(self._overrides)
        return result

    def get_enabled_flags(self) -> Set[str]:
        """Получить набор включённых флагов"""
        all_flags = self.get_all_flags()
        return {k for k, v in all_flags.items() if v}

    def get_disabled_flags(self) -> Set[str]:
        """Получить набор выключенных флагов"""
        all_flags = self.get_all_flags()
        return {k for k, v in all_flags.items() if not v}

    def is_group_enabled(self, group: str, require_all: bool = False) -> bool:
        """
        Проверить включена ли группа флагов.

        Args:
            group: Имя группы
            require_all: True = все флаги должны быть включены,
                        False = хотя бы один

        Returns:
            True если группа включена
        """
        flags_in_group = self.GROUPS.get(group, [])
        if not flags_in_group:
            return False

        if require_all:
            return all(self.is_enabled(f) for f in flags_in_group)
        else:
            return any(self.is_enabled(f) for f in flags_in_group)

    def enable_group(self, group: str) -> None:
        """Включить все флаги в группе (через overrides)"""
        for flag in self.GROUPS.get(group, []):
            self.set_override(flag, True)

    def disable_group(self, group: str) -> None:
        """Выключить все флаги в группе (через overrides)"""
        for flag in self.GROUPS.get(group, []):
            self.set_override(flag, False)

    # =========================================================================
    # Типизированные property для основных флагов
    # =========================================================================

    @property
    def tone_analysis(self) -> bool:
        """Включён ли анализ тона клиента"""
        return self.is_enabled("tone_analysis")

    @property
    def lead_scoring(self) -> bool:
        """Включён ли скоринг лидов для адаптивного SPIN"""
        return self.is_enabled("lead_scoring")

    @property
    def response_variations(self) -> bool:
        """Включена ли вариативность ответов"""
        return self.is_enabled("response_variations")

    @property
    def multi_tier_fallback(self) -> bool:
        """Включён ли 4-уровневый fallback"""
        return self.is_enabled("multi_tier_fallback")

    @property
    def circular_flow(self) -> bool:
        """Включён ли возврат назад по фазам"""
        return self.is_enabled("circular_flow")

    @property
    def conversation_guard(self) -> bool:
        """Включена ли защита от зацикливания"""
        return self.is_enabled("conversation_guard")

    @property
    def structured_logging(self) -> bool:
        """Включены ли структурированные логи"""
        return self.is_enabled("structured_logging")

    @property
    def metrics_tracking(self) -> bool:
        """Включён ли трекинг метрик"""
        return self.is_enabled("metrics_tracking")

    @property
    def personalization(self) -> bool:
        """Включена ли персонализация"""
        return self.is_enabled("personalization")

    @property
    def objection_handler(self) -> bool:
        """Включена ли продвинутая обработка возражений"""
        return self.is_enabled("objection_handler")

    @property
    def cta_generator(self) -> bool:
        """Включена ли генерация Call-to-Action"""
        return self.is_enabled("cta_generator")

    @property
    def intent_disambiguation(self) -> bool:
        """Включено ли уточнение намерения при близких scores (legacy)"""
        return self.is_enabled("intent_disambiguation")

    @property
    def unified_disambiguation(self) -> bool:
        """Включён ли унифицированный disambiguation для LLM и Hybrid классификаторов"""
        return self.is_enabled("unified_disambiguation")

    @property
    def dynamic_cta_fallback(self) -> bool:
        """Включены ли динамические подсказки в fallback tier_2"""
        return self.is_enabled("dynamic_cta_fallback")

    @property
    def cascade_classifier(self) -> bool:
        """Включён ли каскадный классификатор с семантическим fallback"""
        return self.is_enabled("cascade_classifier")

    @property
    def semantic_objection_detection(self) -> bool:
        """Включён ли семантический fallback для детекции возражений"""
        return self.is_enabled("semantic_objection_detection")

    @property
    def response_diversity(self) -> bool:
        """Включён ли post-processing для разнообразия ответов"""
        return self.is_enabled("response_diversity")

    @property
    def response_diversity_logging(self) -> bool:
        """Включено ли логирование замен в response_diversity"""
        return self.is_enabled("response_diversity_logging")

    # =========================================================================
    # Context Policy flags (PLAN_CONTEXT_POLICY.md)
    # =========================================================================

    @property
    def context_full_envelope(self) -> bool:
        """Включён ли полный ContextEnvelope"""
        return self.is_enabled("context_full_envelope")

    @property
    def context_shadow_mode(self) -> bool:
        """Включён ли shadow mode для policy"""
        return self.is_enabled("context_shadow_mode")

    @property
    def context_response_directives(self) -> bool:
        """Включены ли ResponseDirectives"""
        return self.is_enabled("context_response_directives")

    @property
    def context_policy_overlays(self) -> bool:
        """Включены ли policy overlays"""
        return self.is_enabled("context_policy_overlays")

    @property
    def context_engagement_v2(self) -> bool:
        """Включён ли улучшенный расчёт engagement"""
        return self.is_enabled("context_engagement_v2")

    @property
    def context_cta_memory(self) -> bool:
        """Включён ли CTA с учётом episodic memory"""
        return self.is_enabled("context_cta_memory")

    # =========================================================================
    # Cascade Tone Analyzer flags
    # =========================================================================

    @property
    def cascade_tone_analyzer(self) -> bool:
        """Включён ли каскадный анализатор тона"""
        return self.is_enabled("cascade_tone_analyzer")

    @property
    def tone_semantic_tier2(self) -> bool:
        """Включён ли Tier 2 (FRIDA semantic) для анализа тона"""
        return self.is_enabled("tone_semantic_tier2")

    @property
    def tone_llm_tier3(self) -> bool:
        """Включён ли Tier 3 (LLM) для анализа тона"""
        return self.is_enabled("tone_llm_tier3")

    # =========================================================================
    # LLM Classifier flags
    # =========================================================================

    @property
    def llm_classifier(self) -> bool:
        """Включён ли LLM классификатор вместо Hybrid"""
        return self.is_enabled("llm_classifier")

    # =========================================================================
    # Personalization v2 flags
    # =========================================================================

    @property
    def personalization_v2(self) -> bool:
        """Включён ли PersonalizationEngine v2 с behavioral adaptation"""
        return self.is_enabled("personalization_v2")

    @property
    def personalization_adaptive_style(self) -> bool:
        """Включён ли AdaptiveStyleSelector"""
        return self.is_enabled("personalization_adaptive_style")

    @property
    def personalization_semantic_industry(self) -> bool:
        """Включён ли semantic matching для определения отрасли"""
        return self.is_enabled("personalization_semantic_industry")

    @property
    def personalization_session_memory(self) -> bool:
        """Включён ли EffectiveActionTracker для session memory"""
        return self.is_enabled("personalization_session_memory")

    # =========================================================================
    # Guard/Fallback flags
    # =========================================================================

    @property
    def guard_informative_intent_check(self) -> bool:
        """Включена ли проверка информативных интентов перед TIER_3"""
        return self.is_enabled("guard_informative_intent_check")

    @property
    def guard_skip_resets_fallback(self) -> bool:
        """Включён ли сброс fallback_response после skip action"""
        return self.is_enabled("guard_skip_resets_fallback")

    # =========================================================================
    # Robust Classification flags
    # =========================================================================

    @property
    def confidence_router(self) -> bool:
        """Включён ли ConfidenceRouter для graceful degradation"""
        return self.is_enabled("confidence_router")

    @property
    def confidence_router_logging(self) -> bool:
        """Включено ли логирование слепых зон для self-learning"""
        return self.is_enabled("confidence_router_logging")

    # =========================================================================
    # State Loop Fix flags
    # =========================================================================

    @property
    def classification_refinement(self) -> bool:
        """Включено ли контекстное уточнение классификации коротких ответов"""
        return self.is_enabled("classification_refinement")

    # =========================================================================
    # Objection Stuck Fix flags
    # =========================================================================

    @property
    def objection_refinement(self) -> bool:
        """Включена ли контекстная валидация objection классификаций"""
        return self.is_enabled("objection_refinement")

    # =========================================================================
    # Composite Message Refinement flags
    # =========================================================================

    @property
    def composite_refinement(self) -> bool:
        """Включён ли рефайнмент составных сообщений с приоритетом данных"""
        return self.is_enabled("composite_refinement")

    @property
    def refinement_pipeline(self) -> bool:
        """Включён ли универсальный RefinementPipeline вместо отдельных слоёв"""
        return self.is_enabled("refinement_pipeline")

    # =========================================================================
    # Confidence Calibration flags
    # =========================================================================

    @property
    def confidence_calibration(self) -> bool:
        """Включена ли калибровка confidence для решения проблемы overconfident LLM"""
        return self.is_enabled("confidence_calibration")

    # =========================================================================
    # Lost Question Fix flags
    # =========================================================================

    @property
    def secondary_intent_detection(self) -> bool:
        """Включена ли детекция secondary intents в composite сообщениях"""
        return self.is_enabled("secondary_intent_detection")

    # =========================================================================
    # First Contact Refinement flags
    # =========================================================================

    @property
    def first_contact_refinement(self) -> bool:
        """Включён ли рефайнмент возражений при первом контакте"""
        return self.is_enabled("first_contact_refinement")

    # =========================================================================
    # Universal Stall Guard flags
    # =========================================================================

    @property
    def universal_stall_guard(self) -> bool:
        """Включён ли универсальный max-turns-in-state guard"""
        return self.is_enabled("universal_stall_guard")

    @property
    def stall_guard_dual_proposal(self) -> bool:
        """StallGuard proposes action + transition simultaneously"""
        return self.is_enabled("stall_guard_dual_proposal")

    # =========================================================================
    # ConversationGuard in Pipeline flags
    # =========================================================================

    @property
    def conversation_guard_in_pipeline(self) -> bool:
        """Включён ли ConversationGuard внутри Blackboard pipeline"""
        return self.is_enabled("conversation_guard_in_pipeline")

    # =========================================================================
    # Simulation Diagnostic Mode flags
    # =========================================================================

    @property
    def simulation_diagnostic_mode(self) -> bool:
        """Включён ли диагностический режим с повышенными лимитами"""
        return self.is_enabled("simulation_diagnostic_mode")

    # =========================================================================
    # Classification fixes flags
    # =========================================================================

    @property
    def intent_pattern_guard(self) -> bool:
        """Включён ли configurable intent pattern guard"""
        return self.is_enabled("intent_pattern_guard")

    @property
    def comparison_refinement(self) -> bool:
        """Включён ли comparison refinement layer"""
        return self.is_enabled("comparison_refinement")

    # =========================================================================
    # Autonomous Flow flags
    # =========================================================================

    @property
    def autonomous_flow(self) -> bool:
        """Включён ли автономный LLM-driven sales flow"""
        return self.is_enabled("autonomous_flow")


# Singleton экземпляр
flags = FeatureFlags()


# =============================================================================
# Декоратор для условного выполнения
# =============================================================================

def feature_flag(flag_name: str, default_return: Any = None):
    """
    Декоратор для условного выполнения функции на основе feature flag.

    Args:
        flag_name: Имя флага
        default_return: Что возвращать если флаг выключен

    Example:
        @feature_flag("tone_analysis")
        def analyze_tone(message: str):
            # Выполняется только если tone_analysis включён
            return {"tone": "neutral"}
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if flags.is_enabled(flag_name):
                return func(*args, **kwargs)
            return default_return
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# =============================================================================
# CLI для проверки флагов
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("FEATURE FLAGS STATUS")
    print("=" * 60)

    print("\n--- All Flags ---")
    for flag, value in sorted(flags.get_all_flags().items()):
        status = "ON" if value else "OFF"
        print(f"  {flag}: {status}")

    print("\n--- Enabled Flags ---")
    enabled = flags.get_enabled_flags()
    if enabled:
        for flag in sorted(enabled):
            print(f"  + {flag}")
    else:
        print("  (none)")

    print("\n--- Disabled Flags ---")
    disabled = flags.get_disabled_flags()
    if disabled:
        for flag in sorted(disabled):
            print(f"  - {flag}")
    else:
        print("  (none)")

    print("\n--- Groups ---")
    for group, group_flags in FeatureFlags.GROUPS.items():
        all_enabled = flags.is_group_enabled(group, require_all=True)
        any_enabled = flags.is_group_enabled(group, require_all=False)
        status = "ALL ON" if all_enabled else ("PARTIAL" if any_enabled else "OFF")
        print(f"  {group}: {status}")

    print("\n" + "=" * 60)
