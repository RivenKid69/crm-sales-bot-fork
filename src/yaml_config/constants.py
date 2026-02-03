"""
Centralized Constants Module.

This module provides a single source of truth for all constants
by loading them from YAML configuration files.

Usage:
    from src.config.constants import (
        SPIN_PHASES, SPIN_STATES, OBJECTION_INTENTS,
        POSITIVE_INTENTS, QUESTION_INTENTS, GO_BACK_INTENTS,
        MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS, MAX_GOBACKS,
        # DialoguePolicy constants
        OVERLAY_ALLOWED_STATES, PROTECTED_STATES, AGGRESSIVE_ACTIONS,
        # Lead scoring
        LEAD_SCORING_WEIGHTS, LEAD_TEMPERATURE_THRESHOLDS, SKIP_PHASES,
        # Guard
        GUARD_CONFIG,
        # Frustration
        FRUSTRATION_WEIGHTS, FRUSTRATION_THRESHOLDS,
    )

Part of Phase 1: State Machine Parameterization
"""

from typing import Dict, List, Set, Any, Tuple
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


def _load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load {file_path}: {e}")
        return {}


# Load YAML files
_config_dir = Path(__file__).parent
_constants = _load_yaml(_config_dir / "constants.yaml")


# =============================================================================
# PHASE CONFIGURATION (loaded from YAML, no hardcoded fallback)
# =============================================================================

_spin_config = _constants.get("spin", {})

# Phase order and mappings from YAML config
SPIN_PHASES: List[str] = _spin_config.get("phases", [])
SPIN_STATES: Dict[str, str] = _spin_config.get("states", {})
SPIN_PROGRESS_INTENTS: Dict[str, str] = _spin_config.get("progress_intents", {})
# Phase classification config: maps phase -> {data_fields, intent, confidence}
SPIN_PHASE_CLASSIFICATION: Dict[str, Dict[str, Any]] = _spin_config.get("phase_classification", {})
# Short answer classification: maps phase -> {positive_intent, negative_intent, ...}
SPIN_SHORT_ANSWER_CLASSIFICATION: Dict[str, Dict[str, Any]] = _spin_config.get("short_answer_classification", {})


# =============================================================================
# LIMITS
# =============================================================================

_limits = _constants.get("limits", {})

MAX_CONSECUTIVE_OBJECTIONS: int = _limits.get("max_consecutive_objections", 3)
MAX_TOTAL_OBJECTIONS: int = _limits.get("max_total_objections", 5)
MAX_GOBACKS: int = _limits.get("max_gobacks", 2)


# =============================================================================
# DISAMBIGUATION (Unified Disambiguation Decision Engine)
# =============================================================================

_disambiguation = _constants.get("disambiguation", {})
_disambiguation_thresholds = _disambiguation.get("thresholds", {})
_disambiguation_options = _disambiguation.get("options", {})

DISAMBIGUATION_CONFIG: Dict[str, Any] = {
    # Confidence thresholds
    "high_confidence": _disambiguation_thresholds.get("high_confidence", 0.85),
    "medium_confidence": _disambiguation_thresholds.get("medium_confidence", 0.65),
    "low_confidence": _disambiguation_thresholds.get("low_confidence", 0.45),
    "min_confidence": _disambiguation_thresholds.get("min_confidence", 0.30),

    # Gap threshold
    "gap_threshold": _disambiguation.get("gap_threshold", 0.20),
    "max_score_gap": _disambiguation.get("gap_threshold", 0.20),  # Alias for legacy

    # Options config
    "max_options": _disambiguation_options.get("max_options", 3),
    "min_option_confidence": _disambiguation_options.get("min_option_confidence", 0.25),

    # Bypass and excluded intents
    "bypass_disambiguation_intents": _disambiguation.get("bypass_intents", [
        "rejection", "contact_provided", "demo_request"
    ]),
    "excluded_intents": _disambiguation.get("excluded_intents", [
        "unclear", "small_talk"
    ]),

    # Cooldown
    "cooldown_turns": _disambiguation.get("cooldown_turns", 3),
}


def get_disambiguation_config() -> Dict[str, Any]:
    """
    Get disambiguation configuration from YAML.

    Returns:
        Dict with all disambiguation settings
    """
    return DISAMBIGUATION_CONFIG.copy()


# =============================================================================
# INTENT CATEGORIES
# =============================================================================

_intents = _constants.get("intents", {})
_categories = _intents.get("categories", {})

GO_BACK_INTENTS: List[str] = _intents.get("go_back", [])

# =============================================================================
# БАЗОВЫЕ КАТЕГОРИИ (для обратной совместимости - экспортируются напрямую)
# =============================================================================
# NOTE: NEGATIVE_INTENTS теперь composed category и определяется позже
# после создания INTENT_CATEGORIES (см. секцию ниже)
OBJECTION_INTENTS: List[str] = _categories.get("objection", [])
POSITIVE_INTENTS: Set[str] = set(_categories.get("positive", []))
QUESTION_INTENTS: List[str] = _categories.get("question", [])
SPIN_PROGRESS_INTENT_LIST: List[str] = _categories.get("spin_progress", [])
INFORMATIVE_INTENTS: List[str] = _categories.get("informative", [])

# =============================================================================
# НОВЫЕ КАТЕГОРИИ (150+ интентов) - загружаются из YAML
# =============================================================================
PRICE_RELATED_INTENTS: List[str] = _categories.get("price_related", [])
# REMOVED: objection_return_questions base category
# All question intents are now covered by composed all_questions category
QUESTION_REQUIRES_FACTS_INTENTS: List[str] = _categories.get("question_requires_facts", [])

# Вопросы об оборудовании (12 интентов)
EQUIPMENT_QUESTIONS: List[str] = _categories.get("equipment_questions", [])

# Вопросы о тарифах (8 интентов)
TARIFF_QUESTIONS: List[str] = _categories.get("tariff_questions", [])

# Вопросы о ТИС (10 интентов)
TIS_QUESTIONS: List[str] = _categories.get("tis_questions", [])

# Вопросы о налогах (8 интентов)
TAX_QUESTIONS: List[str] = _categories.get("tax_questions", [])

# Бухгалтерия и документы (8 интентов)
ACCOUNTING_QUESTIONS: List[str] = _categories.get("accounting_questions", [])

# Интеграции специфичные (8 интентов)
INTEGRATION_SPECIFIC: List[str] = _categories.get("integration_specific", [])

# Учёт и операции (10 интентов)
OPERATIONS_QUESTIONS: List[str] = _categories.get("operations_questions", [])

# Доставка и сервис (6 интентов)
DELIVERY_SERVICE: List[str] = _categories.get("delivery_service", [])

# Бизнес-сценарии (18 интентов)
BUSINESS_SCENARIOS: List[str] = _categories.get("business_scenarios", [])

# Технические проблемы (6 интентов)
TECHNICAL_PROBLEMS: List[str] = _categories.get("technical_problems", [])

# Разговорные/эмоциональные (10 интентов)
CONVERSATIONAL_INTENTS: List[str] = _categories.get("conversational", [])

# Фискализация (8 интентов)
FISCAL_QUESTIONS: List[str] = _categories.get("fiscal_questions", [])

# Аналитика (8 интентов)
ANALYTICS_QUESTIONS: List[str] = _categories.get("analytics_questions", [])

# Продукты WIPON (6 интентов)
WIPON_PRODUCTS: List[str] = _categories.get("wipon_products", [])

# Сотрудники/кадры (6 интентов)
EMPLOYEE_QUESTIONS: List[str] = _categories.get("employee_questions", [])

# Промо/лояльность (6 интентов)
PROMO_LOYALTY: List[str] = _categories.get("promo_loyalty", [])

# Стабильность/надёжность (6 интентов)
STABILITY_QUESTIONS: List[str] = _categories.get("stability_questions", [])

# Регионы/присутствие (6 интентов)
REGION_QUESTIONS: List[str] = _categories.get("region_questions", [])

# Дополнительные интеграции (6 интентов)
ADDITIONAL_INTEGRATIONS: List[str] = _categories.get("additional_integrations", [])

# Этапы покупки (8 интентов)
PURCHASE_STAGES: List[str] = _categories.get("purchase_stages", [])

# Вопросы о компании (4 интента)
COMPANY_INFO: List[str] = _categories.get("company_info", [])

# Управление диалогом (8 интентов)
DIALOGUE_CONTROL: List[str] = _categories.get("dialogue_control", [])

# =============================================================================
# INTENT_CATEGORIES - ПОЛНЫЙ СЛОВАРЬ ВСЕХ КАТЕГОРИЙ
# =============================================================================
# КРИТИЧНО: Это единственный источник истины для IntentTracker
# Загружает ВСЕ категории из constants.yaml автоматически
#
# Поддерживает два типа категорий:
# 1. Базовые категории - определены напрямую как списки интентов
# 2. Композитные категории - создаются путём объединения базовых категорий
#    (определены в секции composed_categories)

def _resolve_composed_categories(
    base_categories: Dict[str, List[str]],
    compositions: Dict[str, Dict[str, Any]]
) -> Dict[str, List[str]]:
    """
    Resolve composed categories by merging base categories.

    Supports three composition mechanisms:
    1. auto_include.intent_prefix — auto-includes any base category containing
       at least one intent matching the prefix (scans base_categories only)
    2. includes — explicit list of categories to merge (can reference
       already-resolved composed categories)
    3. direct_intents — explicit list of individual intents

    Args:
        base_categories: Dictionary of base category name -> list of intents
        compositions: Dictionary of composed category specs from YAML

    Returns:
        Dictionary with all categories (base + composed)
    """
    result = dict(base_categories)

    for composed_name, spec in compositions.items():
        if not isinstance(spec, dict):
            logger.warning(f"Invalid composed category spec for '{composed_name}': expected dict")
            continue

        includes = spec.get("includes", [])
        direct_intents = spec.get("direct_intents", [])
        auto_include = spec.get("auto_include", {})

        if not includes and not direct_intents and not auto_include:
            logger.warning(f"Composed category '{composed_name}' has no includes, direct_intents, or auto_include")
            continue

        merged_intents: List[str] = list(direct_intents)

        # Auto-include base categories matching intent prefix pattern
        if auto_include:
            prefix = auto_include.get("intent_prefix", "")
            exclude_categories = set(auto_include.get("exclude_categories", []))
            if prefix:
                auto_included = []
                for cat_name, cat_intents in base_categories.items():
                    if cat_name == composed_name:
                        continue  # skip self-reference
                    if cat_name in exclude_categories:
                        continue  # explicitly excluded
                    if any(intent.startswith(prefix) for intent in cat_intents):
                        merged_intents.extend(cat_intents)
                        auto_included.append(cat_name)
                if auto_included:
                    logger.debug(
                        f"Auto-included {len(auto_included)} categories into "
                        f"'{composed_name}' by prefix '{prefix}': {auto_included}"
                    )

        # Explicit includes (runs on result — can reference already-resolved composed categories)
        for included_category in includes:
            if included_category not in result:
                logger.warning(
                    f"Composed category '{composed_name}' references unknown category "
                    f"'{included_category}'. Available: {list(result.keys())}"
                )
                continue
            merged_intents.extend(result[included_category])

        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_intents: List[str] = []
        for intent in merged_intents:
            if intent not in seen:
                seen.add(intent)
                unique_intents.append(intent)

        result[composed_name] = unique_intents

        description = spec.get("description", "")
        logger.debug(
            f"Created composed category '{composed_name}' with {len(unique_intents)} intents "
            f"from {includes}. {description}"
        )

    return result


# Step 1: Load base categories from YAML
_base_categories: Dict[str, List[str]] = {
    category_name: list(category_intents) if isinstance(category_intents, list) else []
    for category_name, category_intents in _categories.items()
}

# Step 2: Load composed category definitions
_composed_definitions: Dict[str, Dict[str, Any]] = _intents.get("composed_categories", {})

# Step 3: Resolve composed categories (merge base categories)
INTENT_CATEGORIES: Dict[str, List[str]] = _resolve_composed_categories(
    _base_categories,
    _composed_definitions
)

# Step 4: Validation - ensure critical categories exist
_REQUIRED_CATEGORIES = ["objection", "positive", "question", "negative", "exit", "objection_return_triggers", "greeting_redirect_intents"]
for _required in _REQUIRED_CATEGORIES:
    if _required not in INTENT_CATEGORIES or not INTENT_CATEGORIES[_required]:
        logger.warning(f"Required category '{_required}' is missing or empty in INTENT_CATEGORIES")

# Step 5: Log category stats for debugging
if logger.isEnabledFor(logging.DEBUG):
    _base_count = len(_base_categories)
    _composed_count = len(_composed_definitions)
    _total_count = len(INTENT_CATEGORIES)
    logger.debug(
        f"INTENT_CATEGORIES loaded: {_base_count} base + {_composed_count} composed = "
        f"{_total_count} total categories"
    )

# Step 6: Validate no ghost question intents in categories
def _validate_no_ghost_intents(categories: Dict[str, List[str]]) -> None:
    """Warn about question_* intents not in classifier taxonomy (INTENT_ROOTS)."""
    try:
        from src.config import INTENT_ROOTS
        known = set(INTENT_ROOTS.keys())
        for cat_name, intents in categories.items():
            for intent in intents:
                if intent.startswith("question_") and intent not in known:
                    logger.warning(
                        f"Ghost intent '{intent}' in category '{cat_name}': "
                        f"not in INTENT_ROOTS (classifier cannot generate it)"
                    )
    except ImportError:
        pass  # Graceful degradation if config not available

_validate_no_ghost_intents(INTENT_CATEGORIES)

# Legacy exports (for backwards compatibility)
# These now reference the unified INTENT_CATEGORIES
EXIT_INTENTS: List[str] = INTENT_CATEGORIES.get("exit", [])
NEGATIVE_INTENTS: List[str] = INTENT_CATEGORIES.get("negative", [])

# SSOT: Composed category for objection return triggers
# Loaded from constants.yaml → composed_categories → objection_return_triggers
# Contains: positive + price_related + all_questions
OBJECTION_RETURN_TRIGGERS: List[str] = INTENT_CATEGORIES.get("objection_return_triggers", [])

# SSOT: Composed category for greeting state safety overrides
# Loaded from constants.yaml → composed_categories → greeting_redirect_intents
# Contains: technical_problems + greeting_additional_redirects
GREETING_REDIRECT_INTENTS: List[str] = INTENT_CATEGORIES.get("greeting_redirect_intents", [])

# Intent action overrides (intent -> action mapping)
INTENT_ACTION_OVERRIDES: Dict[str, str] = _intents.get("intent_action_overrides", {})


# =============================================================================
# DIALOGUE POLICY SETTINGS
# =============================================================================

_policy = _constants.get("policy", {})

OVERLAY_ALLOWED_STATES: Set[str] = set(_policy.get("overlay_allowed_states", []))
PROTECTED_STATES: Set[str] = set(_policy.get("protected_states", []))
AGGRESSIVE_ACTIONS: Set[str] = set(_policy.get("aggressive_actions", []))
REPAIR_ACTIONS: Dict[str, str] = _policy.get("repair_actions", {})
REPAIR_PROTECTED_ACTIONS: Set[str] = set(_policy.get("repair_protected_actions", []))
PRICING_CORRECT_ACTIONS: Set[str] = set(_policy.get("pricing_correct_actions", []))
REPEATABLE_INTENT_GROUPS: Dict[str, Set[str]] = {
    k: set(v) for k, v in _policy.get("repeatable_intent_groups", {}).items()
}
OBJECTION_ESCALATION_ACTIONS: Dict[str, str] = _policy.get("objection_actions", {})


# =============================================================================
# LEAD SCORING SETTINGS
# =============================================================================

_lead_scoring = _constants.get("lead_scoring", {})

LEAD_SCORING_POSITIVE_WEIGHTS: Dict[str, int] = _lead_scoring.get("positive_weights", {})
LEAD_SCORING_NEGATIVE_WEIGHTS: Dict[str, int] = _lead_scoring.get("negative_weights", {})

_thresholds = _lead_scoring.get("thresholds", {})
LEAD_TEMPERATURE_THRESHOLDS: Dict[str, Tuple[int, int]] = {
    temp: tuple(_thresholds.get(temp, [0, 100]))
    for temp in ["cold", "warm", "hot", "very_hot"]
    if temp in _thresholds
} or {}

SKIP_PHASES_BY_TEMPERATURE: Dict[str, List[str]] = _lead_scoring.get("skip_phases", {})


# =============================================================================
# CONVERSATION GUARD SETTINGS
# =============================================================================

_guard = _constants.get("guard", {})

GUARD_CONFIG: Dict[str, Any] = {
    "max_turns": _guard.get("max_turns", 25),
    "max_phase_attempts": _guard.get("max_phase_attempts", 3),
    "max_same_state": _guard.get("max_same_state", 4),
    "max_same_message": _guard.get("max_same_message", 2),
    "timeout_seconds": _guard.get("timeout_seconds", 1800),
    "progress_check_interval": _guard.get("progress_check_interval", 5),
    "min_unique_states_for_progress": _guard.get("min_unique_states_for_progress", 2),
    "high_frustration_threshold": _guard.get("high_frustration_threshold", 7),
}

GUARD_PROFILES: Dict[str, Dict[str, Any]] = _guard.get("profiles", {})


# =============================================================================
# FRUSTRATION TRACKER SETTINGS
# =============================================================================

_frustration = _constants.get("frustration", {})

MAX_FRUSTRATION: int = _frustration.get("max_level", 10)
FRUSTRATION_WEIGHTS: Dict[str, int] = _frustration.get("weights", {})
FRUSTRATION_DECAY: Dict[str, int] = _frustration.get("decay", {})
FRUSTRATION_THRESHOLDS: Dict[str, int] = _frustration.get("thresholds", {})

# Intensity-based frustration configuration (NEW)
# Used by FrustrationIntensityCalculator for signal-aware frustration calculation
_frustration_intensity = _frustration.get("intensity", {})

# Tone-aware apology configuration
_apology_config = _frustration.get("apology", {})
APOLOGY_TONE_OVERRIDES: Dict[str, int] = _apology_config.get("tone_overrides", {})

FRUSTRATION_INTENSITY_CONFIG: Dict[str, Any] = {
    "base_weights": _frustration_intensity.get("base_weights", {
        "frustrated": 3,
        "rushed": 2,
        "skeptical": 1,
        "confused": 1,
    }),
    "intensity_multipliers": _frustration_intensity.get("intensity_multipliers", {
        1: 1.0,
        2: 1.5,
        3: 2.0,
    }),
    "consecutive_turn_multiplier": _frustration_intensity.get("consecutive_turn_multiplier", 1.2),
    "consecutive_turn_threshold": _frustration_intensity.get("consecutive_turn_threshold", 2),
    "decay_weights": _frustration_intensity.get("decay_weights", {
        "neutral": 1,
        "positive": 2,
        "interested": 2,
    }),
    "rushed_pre_intervention_threshold": _frustration_intensity.get(
        "rushed_pre_intervention_threshold", 2
    ),
    "urgency_thresholds": _frustration_intensity.get("urgency_thresholds", {
        "low": 2,
        "medium": 4,
        "high": 7,
        "critical": 9,
    }),
}


# =============================================================================
# CIRCULAR FLOW SETTINGS
# =============================================================================

_circular_flow = _constants.get("circular_flow", {})

ALLOWED_GOBACKS: Dict[str, str] = _circular_flow.get("allowed_gobacks", {})


# =============================================================================
# CONTEXT WINDOW SETTINGS
# =============================================================================

_context = _constants.get("context", {})

STATE_ORDER: Dict[str, int] = _context.get("state_order", {})
PHASE_ORDER: Dict[str, int] = _context.get("phase_order", {})


# =============================================================================
# FALLBACK SETTINGS
# =============================================================================

_fallback = _constants.get("fallback", {})

FALLBACK_REPHRASE_TEMPLATES: Dict[str, List[str]] = _fallback.get("rephrase_templates", {})
FALLBACK_OPTIONS_TEMPLATES: Dict[str, Dict[str, Any]] = _fallback.get("options_templates", {})
# FIX: default_rephrase теперь может быть списком для вариативности
_default_rephrase_raw = _fallback.get("default_rephrase", "Давайте попробую спросить иначе...")
FALLBACK_DEFAULT_REPHRASE: List[str] = (
    _default_rephrase_raw if isinstance(_default_rephrase_raw, list)
    else [_default_rephrase_raw]
)
FALLBACK_DEFAULT_OPTIONS: Dict[str, Any] = _fallback.get("default_options", {})


# =============================================================================
# LLM SETTINGS
# =============================================================================

_llm = _constants.get("llm", {})

LLM_FALLBACK_RESPONSES: Dict[str, str] = _llm.get("fallback_responses", {})
LLM_DEFAULT_FALLBACK: str = _llm.get("default_fallback", "Произошла техническая ошибка.")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_short_answer_config() -> Dict[str, Dict[str, Any]]:
    """
    Get short_answer_classification config from constants.yaml.

    Used by ClassificationRefinementLayer to refine LLM classification
    for short messages based on SPIN phase context.

    Returns:
        Dict with phase -> {positive_intent, positive_confidence, negative_intent, ...}

    Example:
        >>> config = get_short_answer_config()
        >>> config["situation"]
        {'positive_intent': 'situation_provided', 'positive_confidence': 0.7}
    """
    return SPIN_SHORT_ANSWER_CLASSIFICATION


def get_informative_intents() -> List[str]:
    """
    Get list of informative intents (client provides data, not stuck).

    Used by ConversationGuard to check if client is providing information
    before triggering TIER_3 fallback.

    Returns:
        List of intent names that indicate client is providing information.
    """
    return INFORMATIVE_INTENTS


def get_objection_return_config() -> Dict[str, Any]:
    """
    Get objection_return config from constants.yaml.

    Used by ObjectionReturnSource to determine when and how to return
    to the previous phase after successfully handling an objection.

    Returns:
        Dict with objection return configuration including:
        - enabled: bool (default True)
        - use_positive_intents: bool (default True)
        - return_intents: List[str] (custom intents if use_positive_intents is False)

    Example:
        >>> config = get_objection_return_config()
        >>> config["enabled"]
        True
        >>> config["use_positive_intents"]
        True
    """
    return _constants.get("objection_return", {
        "enabled": True,
        "use_positive_intents": True,
        "return_intents": [],
    })


def get_objection_refinement_config() -> Dict[str, Any]:
    """
    Get objection_refinement config from constants.yaml.

    Used by ObjectionRefinementLayer to validate and refine objection
    classifications using contextual signals.

    Returns:
        Dict with objection refinement configuration including:
        - enabled: bool
        - min_confidence_to_accept: float
        - question_markers: List[str]
        - callback_patterns: List[str]
        - interest_patterns: List[str]
        - refinement_mapping: Dict[str, Dict]
        - topic_alignment_actions: Dict[str, List[str]]
        - cooldown: Dict[str, int]

    Example:
        >>> config = get_objection_refinement_config()
        >>> config["min_confidence_to_accept"]
        0.85
        >>> config["refinement_mapping"]["objection_price"]
        {'question_context': 'price_question', 'info_context': 'info_provided'}
    """
    return _constants.get("objection_refinement", {})


def get_first_contact_refinement_config() -> Dict[str, Any]:
    """
    Get first_contact_refinement config from constants.yaml.

    Used by FirstContactRefinementLayer to refine early-turn classifications
    where objection-like messages are actually cautious interest.

    Problem: "слушайте мне тут посоветовали... но я не уверен" (turn=1)
             LLM returns objection_trust → bot goes to handle_objection
             Expected: consultation_request → bot greets and starts dialog

    Semantic difference by turn_number:
      turn=1: "не уверен" = modesty, cautious interest (want to learn more)
      turn>3: "не уверен" = doubt after presentation (real objection)

    Returns:
        Dict with first contact refinement configuration including:
        - enabled: bool
        - max_turn_number: int (when layer stops applying)
        - active_states: List[str] (states where layer is active)
        - suspicious_intents: List[str] (intents to potentially refine)
        - referral_patterns: List[str] (e.g., "посоветовали")
        - cautious_interest_patterns: List[str] (e.g., "не уверен")
        - first_contact_patterns: List[str] (e.g., "слушайте")
        - target_intent: str (default: "consultation_request")
        - refined_confidence: float (default: 0.75)

    Example:
        >>> config = get_first_contact_refinement_config()
        >>> config["max_turn_number"]
        2
        >>> "посоветовали" in config["referral_patterns"]
        True
    """
    return _constants.get("first_contact_refinement", {})


def get_composite_refinement_config() -> Dict[str, Any]:
    """
    Get composite_refinement config from constants.yaml.

    Used by CompositeMessageRefinementLayer to refine composite message
    classifications (messages containing both data and meta-signals).

    This configuration is FLOW-AGNOSTIC and works with any dialogue structure
    (SPIN, BANT, custom flows, etc.).

    Returns:
        Dict with composite refinement configuration including:
        - enabled: bool
        - min_confidence_for_refinement: float
        - default_data_intent: str
        - action_expects_data: Dict[str, str] - action → expected data type
        - action_data_intent: Dict[str, str] - action → target intent
        - data_expecting_states: List[str]
        - data_expecting_phases: List[str]
        - data_fields: Dict[str, Dict] - field configurations
        - meta_signals: Dict[str, Dict] - meta-signal configurations
        - ambiguous_patterns: Dict[str, Dict] - ambiguity configurations

    Example:
        >>> config = get_composite_refinement_config()
        >>> config["action_expects_data"]["ask_about_company"]
        'company_size'
        >>> config["action_data_intent"]["ask_about_company"]
        'situation_provided'
        >>> config["ambiguous_patterns"]["bolshe_ne_nuzhno"]["patterns"]
        ['больше\\s+не\\s+(?:нужно|надо)', ...]
    """
    return _constants.get("composite_refinement", {})


def get_refinement_pipeline_config() -> Dict[str, Any]:
    """
    Get refinement_pipeline config from constants.yaml.

    Used by RefinementPipeline to configure layer order and settings.
    This is the Single Source of Truth for the refinement pipeline.

    Returns:
        Dict with pipeline configuration including:
        - enabled: bool - master switch for the pipeline
        - layers: List[Dict] - ordered list of layer configurations
          Each layer config:
            - name: str - layer name (must be registered in RefinementLayerRegistry)
            - enabled: bool - whether layer is enabled
            - priority: int (optional) - override layer's default priority

    Example:
        >>> config = get_refinement_pipeline_config()
        >>> config["enabled"]
        True
        >>> config["layers"][0]["name"]
        'short_answer'
    """
    return _constants.get("refinement_pipeline", {
        "enabled": True,
        "layers": []
    })


def get_option_selection_config() -> Dict[str, Any]:
    """
    Get option_selection_refinement config from constants.yaml.

    Used by OptionSelectionRefinementLayer to configure option selection detection.
    Solves the "option selection" bug where LLM misclassifies "1", "2", "первое"
    as request_brevity when they're actually answers to bot's option questions.

    Problem Scenario:
        Bot: "Что для вас приоритетнее — скорость или функционал?"
        User: "1"
        LLM: request_brevity (0.9) ← WRONG
        Expected: info_provided with option_selection signal

    Research Basis:
        - Grice's Cooperative Principle (1975): short answers carry implicature
        - Conversational repair research: numeric responses = selections

    Returns:
        Dict with option selection configuration including:
        - enabled: bool - master switch
        - target_intent: str - intent to refine to (default: info_provided)
        - refined_confidence: float - confidence for refined result
        - secondary_signal: str - signal to add to result
        - option_question_patterns: List[str] - patterns for bot questions
        - selection_answer_patterns: List[str] - patterns for user answers
        - suspicious_intents: List[str] - intents that may be wrong

    Example:
        >>> config = get_option_selection_config()
        >>> config["enabled"]
        True
        >>> config["target_intent"]
        'info_provided'
    """
    return _constants.get("option_selection_refinement", {
        "enabled": True,
        "target_intent": "info_provided",
        "refined_confidence": 0.75,
        "secondary_signal": "option_selection",
        "option_question_patterns": [
            r"(.+?)\s+или\s+(.+?)\?",
        ],
        "selection_answer_patterns": [
            r"^1$", r"^2$", r"^3$",
            r"^перв", r"^втор", r"^трет",
        ],
        "suspicious_intents": [
            "request_brevity", "greeting", "unclear", "small_talk",
        ],
    })


def get_confidence_calibration_config() -> Dict[str, Any]:
    """
    Get confidence_calibration config from constants.yaml.

    Used by ConfidenceCalibrationLayer to configure calibration strategies.
    This is the Single Source of Truth for confidence calibration.

    Solves the fundamental LLM overconfidence problem:
    - LLM generates confidence as text, not computed algorithmically
    - Few-shot examples teach high confidence (0.85-0.98)
    - Result: confidence 0.85-0.95 even with incorrect classification

    Scientific Foundations:
    - Entropy-based calibration (Shannon, 1948)
    - Post-hoc calibration (Guo et al., 2017)
    - Verbal confidence calibration (Tian et al., 2023)

    Returns:
        Dict with calibration configuration including:
        - enabled: bool - master switch
        - min_confidence_floor: float - minimum confidence after calibration
        - max_confidence_ceiling: float - maximum confidence (can't be 100% sure)
        - entropy_*: entropy strategy settings
        - gap_*: gap strategy settings
        - heuristic_*: heuristic strategy settings

    Example:
        >>> config = get_confidence_calibration_config()
        >>> config["enabled"]
        True
        >>> config["entropy_threshold"]
        0.5
        >>> config["gap_threshold"]
        0.2
    """
    return _constants.get("confidence_calibration", {
        "enabled": True,
        "min_confidence_floor": 0.1,
        "max_confidence_ceiling": 0.95,
        "entropy_enabled": True,
        "entropy_threshold": 0.5,
        "entropy_penalty_factor": 0.15,
        "gap_enabled": True,
        "gap_threshold": 0.2,
        "gap_penalty_factor": 0.2,
        "heuristic_enabled": True,
    })


def get_greeting_safety_config() -> Dict[str, Any]:
    """Get greeting_state_safety config. SSOT for greeting state transition safety."""
    return _constants.get("greeting_state_safety", {})


def get_greeting_context_refinement_config() -> Dict[str, Any]:
    """Get greeting_context_refinement config. Uses category-based SSOT for suspicious intents."""
    return _constants.get("greeting_context_refinement", {})


def get_stall_detection_config() -> Dict[str, Any]:
    """Get stall_detection config for flow state stall detection."""
    return _constants.get("stall_detection", {})


def get_frustration_intensity_config() -> Dict[str, Any]:
    """
    Get frustration_intensity config from constants.yaml.

    Used by FrustrationIntensityCalculator for signal-aware frustration calculation.
    This is the Single Source of Truth for intensity-based frustration handling.

    Solves the frustration intervention bug:
    - Original: Only ONE signal per tone counted per message
    - Original: "быстрее, не тяни, некогда" (3 RUSHED signals) = +1 frustration
    - Fixed: Multiple signals = higher weight (intensity-based calculation)
    - Fixed: 3 RUSHED signals = base(2) * multiplier(2.0) = +4 frustration

    Returns:
        Dict with intensity configuration including:
        - base_weights: Dict[str, int] - base weight per tone
        - intensity_multipliers: Dict[int, float] - signal count -> multiplier
        - consecutive_turn_multiplier: float - bonus for consecutive negative turns
        - consecutive_turn_threshold: int - turns before bonus applies
        - decay_weights: Dict[str, int] - decay per positive tone
        - rushed_pre_intervention_threshold: int - signals to trigger pre-intervention

    Example:
        >>> config = get_frustration_intensity_config()
        >>> config["base_weights"]["rushed"]
        2
        >>> config["intensity_multipliers"][3]
        2.0
        >>> config["rushed_pre_intervention_threshold"]
        2
    """
    return FRUSTRATION_INTENSITY_CONFIG


def get_secondary_intent_config() -> Dict[str, Any]:
    """
    Get secondary_intent_detection config from constants.yaml.

    Used by SecondaryIntentDetectionLayer for detecting lost questions
    in composite messages.

    This is part of the architectural solution for the "Lost Question" bug:
    - When user sends "100 человек. Сколько стоит?"
    - LLM picks info_provided as primary (data detected)
    - price_question is LOST
    - This layer detects price_question as secondary intent
    - FactQuestionSource can then respond to the question

    Returns:
        Dict with secondary intent detection configuration including:
        - enabled: bool - master switch
        - min_message_length: int - minimum length for detection
        - patterns: Dict[str, Dict] - intent -> pattern config

    Example:
        >>> config = get_secondary_intent_config()
        >>> config["patterns"]["price_question"]["priority"]
        100
    """
    return _constants.get("secondary_intent_detection", {
        "enabled": True,
        "min_message_length": 10,
        "patterns": {},
    })


def get_intent_pattern_guard_config() -> Dict[str, Any]:
    """
    Get intent_pattern_guard config from constants.yaml.

    Used by IntentPatternGuardSource for configurable pattern detection.

    Returns:
        Dict with pattern guard configuration including:
        - patterns: Dict of pattern_name -> pattern config
    """
    return _intents.get("intent_pattern_guard", {"patterns": {}})


def get_fact_question_source_config() -> Dict[str, Any]:
    """
    Get fact_question_source config from constants.yaml.

    Used by FactQuestionSource for handling all fact-based questions.
    Works with SecondaryIntentDetectionLayer to detect lost questions.

    Returns:
        Dict with fact question source configuration including:
        - enabled: bool - master switch
        - fact_intents: List[str] - intents requiring factual answers
        - default_actions: Dict[str, str] - intent-specific actions
        - fallback_action: str - default action if no specific one

    Example:
        >>> config = get_fact_question_source_config()
        >>> "question_features" in config["fact_intents"]
        True
    """
    return _constants.get("fact_question_source", {
        "enabled": True,
        "fact_intents": [],
        "default_actions": {},
        "fallback_action": "answer_with_facts",
    })


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # SPIN
    "SPIN_PHASES",
    "SPIN_STATES",
    "SPIN_PROGRESS_INTENTS",
    "SPIN_PHASE_CLASSIFICATION",
    "SPIN_SHORT_ANSWER_CLASSIFICATION",
    # Limits
    "MAX_CONSECUTIVE_OBJECTIONS",
    "MAX_TOTAL_OBJECTIONS",
    "MAX_GOBACKS",
    # Intent categories - базовые
    "GO_BACK_INTENTS",
    "OBJECTION_INTENTS",
    "POSITIVE_INTENTS",
    "QUESTION_INTENTS",
    "SPIN_PROGRESS_INTENT_LIST",
    "NEGATIVE_INTENTS",
    "EXIT_INTENTS",
    "INFORMATIVE_INTENTS",
    "PRICE_RELATED_INTENTS",
    # REMOVED: "OBJECTION_RETURN_QUESTIONS" (replaced by all_questions)
    "OBJECTION_RETURN_TRIGGERS",
    "GREETING_REDIRECT_INTENTS",
    "QUESTION_REQUIRES_FACTS_INTENTS",
    # Intent categories - новые (150+ интентов)
    "EQUIPMENT_QUESTIONS",
    "TARIFF_QUESTIONS",
    "TIS_QUESTIONS",
    "TAX_QUESTIONS",
    "ACCOUNTING_QUESTIONS",
    "INTEGRATION_SPECIFIC",
    "OPERATIONS_QUESTIONS",
    "DELIVERY_SERVICE",
    "BUSINESS_SCENARIOS",
    "TECHNICAL_PROBLEMS",
    "CONVERSATIONAL_INTENTS",
    "FISCAL_QUESTIONS",
    "ANALYTICS_QUESTIONS",
    "WIPON_PRODUCTS",
    "EMPLOYEE_QUESTIONS",
    "PROMO_LOYALTY",
    "STABILITY_QUESTIONS",
    "REGION_QUESTIONS",
    "ADDITIONAL_INTEGRATIONS",
    "PURCHASE_STAGES",
    "COMPANY_INFO",
    "DIALOGUE_CONTROL",
    # Главный словарь всех категорий
    "INTENT_CATEGORIES",
    "INTENT_ACTION_OVERRIDES",
    # Policy
    "OVERLAY_ALLOWED_STATES",
    "PROTECTED_STATES",
    "AGGRESSIVE_ACTIONS",
    "REPAIR_ACTIONS",
    "REPAIR_PROTECTED_ACTIONS",
    "PRICING_CORRECT_ACTIONS",
    "REPEATABLE_INTENT_GROUPS",
    "OBJECTION_ESCALATION_ACTIONS",
    # Lead scoring
    "LEAD_SCORING_POSITIVE_WEIGHTS",
    "LEAD_SCORING_NEGATIVE_WEIGHTS",
    "LEAD_TEMPERATURE_THRESHOLDS",
    "SKIP_PHASES_BY_TEMPERATURE",
    # Guard
    "GUARD_CONFIG",
    "GUARD_PROFILES",
    # Frustration
    "MAX_FRUSTRATION",
    "FRUSTRATION_WEIGHTS",
    "FRUSTRATION_DECAY",
    "FRUSTRATION_THRESHOLDS",
    "FRUSTRATION_INTENSITY_CONFIG",
    "APOLOGY_TONE_OVERRIDES",
    # Circular flow
    "ALLOWED_GOBACKS",
    # Context window
    "STATE_ORDER",
    "PHASE_ORDER",
    # Fallback
    "FALLBACK_REPHRASE_TEMPLATES",
    "FALLBACK_OPTIONS_TEMPLATES",
    "FALLBACK_DEFAULT_REPHRASE",
    "FALLBACK_DEFAULT_OPTIONS",
    # LLM
    "LLM_FALLBACK_RESPONSES",
    "LLM_DEFAULT_FALLBACK",
    # Helper functions
    "get_short_answer_config",
    "get_informative_intents",
    "get_greeting_safety_config",
    "get_greeting_context_refinement_config",
    "get_stall_detection_config",
    "get_objection_return_config",
    "get_objection_refinement_config",
    "get_composite_refinement_config",
    "get_disambiguation_config",
    "get_refinement_pipeline_config",
    "get_confidence_calibration_config",
    "get_frustration_intensity_config",
    # FIX: New functions for Lost Question Fix
    "get_secondary_intent_config",
    "get_fact_question_source_config",
]
