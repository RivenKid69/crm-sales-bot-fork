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

    Args:
        base_categories: Dictionary of base category name -> list of intents
        compositions: Dictionary of composed category specs from YAML

    Returns:
        Dictionary with all categories (base + composed)

    Raises:
        ValueError: If a referenced category doesn't exist
    """
    result = dict(base_categories)

    for composed_name, spec in compositions.items():
        if not isinstance(spec, dict):
            logger.warning(f"Invalid composed category spec for '{composed_name}': expected dict")
            continue

        includes = spec.get("includes", [])
        if not includes:
            logger.warning(f"Composed category '{composed_name}' has no includes")
            continue

        # Merge all included categories
        merged_intents: List[str] = []
        for included_category in includes:
            if included_category not in result:
                # Это может быть ссылка на ещё не созданную composed категорию
                # или ошибка - категория не существует
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
_REQUIRED_CATEGORIES = ["objection", "positive", "question", "negative", "exit"]
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

# Legacy exports (for backwards compatibility)
# These now reference the unified INTENT_CATEGORIES
EXIT_INTENTS: List[str] = INTENT_CATEGORIES.get("exit", [])
NEGATIVE_INTENTS: List[str] = INTENT_CATEGORIES.get("negative", [])

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
    "get_objection_refinement_config",
    "get_composite_refinement_config",
    "get_disambiguation_config",
]
