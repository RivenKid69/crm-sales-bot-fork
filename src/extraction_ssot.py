"""
Centralized Data Extraction Rules Module.

This module provides the Single Source of Truth for all data extraction rules
across the system. All components that need extraction rules MUST import from
this module to ensure consistency.

Architecture:
    constants.yaml (extraction section)
         |
         v
    yaml_config/constants.py (loads YAML)
         |
         v
    extraction_ssot.py (THIS MODULE - validates & exports)
         |
         v
    +-----------------+-------------------+----------------------+
    |                 |                   |                      |
    v                 v                   v                      v
extraction_     classifier/llm/      classifier/llm/      data_extractor.py
validator.py    prompts.py           classifier.py

Usage:
    from src.extraction_ssot import (
        # Field configurations
        EXTRACTION_FIELDS,
        get_field_config,
        # Prompt instructions
        get_extraction_prompt_instructions,
        # Phase mappings
        get_phase_fields,
        # Validation rules
        VALIDATION_RULES,
        # Helper functions
        is_field_valid_for_phase,
        get_allowed_values,
    )

Part of Data Extraction Quality Fix (addressing LLM hallucinations).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class FieldConfig:
    """
    Immutable configuration for a single extraction field.

    Provides type safety and clear documentation of field semantics.
    """
    name: str
    description: str
    field_type: str  # int, str, bool, enum
    spin_phase: Optional[str]  # Which SPIN phase this field belongs to
    validation: Dict[str, Any] = field(default_factory=dict)
    examples_valid: List[Dict[str, Any]] = field(default_factory=list)
    examples_invalid: List[Dict[str, Any]] = field(default_factory=list)

    def get_allowed_values(self) -> Optional[List[str]]:
        """Get allowed values for enum fields."""
        return self.validation.get("allowed_values")

    def get_patterns(self) -> Optional[List[str]]:
        """Get extraction patterns."""
        return self.validation.get("extract_patterns")

    def get_min_value(self) -> Optional[int]:
        """Get minimum value for numeric fields."""
        return self.validation.get("min")

    def get_max_value(self) -> Optional[int]:
        """Get maximum value for numeric fields."""
        return self.validation.get("max")


@dataclass(frozen=True)
class ExtractionConfig:
    """
    Complete extraction configuration.

    Contains all field configs, phase mappings, and validation rules.
    """
    fields: Dict[str, FieldConfig]
    phase_fields: Dict[str, List[str]]
    validation_rules: Dict[str, bool]
    prompt_instructions: Dict[str, str]

    def get_field(self, name: str) -> Optional[FieldConfig]:
        """Get configuration for a specific field."""
        return self.fields.get(name)

    def get_fields_for_phase(self, phase: str) -> List[str]:
        """Get list of fields for a SPIN phase."""
        return self.phase_fields.get(phase, [])


# =============================================================================
# LOAD FROM YAML
# =============================================================================

def _load_extraction_config() -> ExtractionConfig:
    """
    Load and validate extraction configuration from YAML.

    Returns:
        ExtractionConfig with all extraction rules

    Raises:
        ValueError: If configuration is invalid
    """
    try:
        from src.yaml_config.constants import _constants
        extraction_yaml = _constants.get("extraction", {})
    except ImportError:
        logger.warning("Could not import constants, using empty config")
        extraction_yaml = {}

    # Load field configurations
    fields_yaml = extraction_yaml.get("fields", {})
    fields: Dict[str, FieldConfig] = {}

    for field_name, field_data in fields_yaml.items():
        if not isinstance(field_data, dict):
            continue

        # Parse examples
        examples_yaml = field_data.get("examples", {})
        examples_valid = examples_yaml.get("valid", [])
        examples_invalid = examples_yaml.get("invalid", [])

        fields[field_name] = FieldConfig(
            name=field_name,
            description=field_data.get("description", ""),
            field_type=field_data.get("type", "str"),
            spin_phase=field_data.get("spin_phase"),
            validation=field_data.get("validation", {}),
            examples_valid=examples_valid if isinstance(examples_valid, list) else [],
            examples_invalid=examples_invalid if isinstance(examples_invalid, list) else [],
        )

    # Load phase fields mapping
    phase_fields = extraction_yaml.get("phase_fields", {})

    # Load validation rules
    validation_rules = extraction_yaml.get("validation_rules", {})

    # Load prompt instructions
    prompt_instructions = extraction_yaml.get("prompt_instructions", {})

    return ExtractionConfig(
        fields=fields,
        phase_fields=phase_fields,
        validation_rules=validation_rules,
        prompt_instructions=prompt_instructions,
    )


# Load at module import time
_config = _load_extraction_config()


# =============================================================================
# EXPORTED CONFIGURATION VALUES
# =============================================================================

# All field configurations
EXTRACTION_FIELDS: Dict[str, FieldConfig] = _config.fields

# Phase to fields mapping
PHASE_FIELDS: Dict[str, List[str]] = _config.phase_fields

# Validation rules
VALIDATION_RULES: Dict[str, bool] = _config.validation_rules

# Prompt instructions
PROMPT_INSTRUCTIONS: Dict[str, str] = _config.prompt_instructions

# Convenience: set of all field names
ALL_FIELD_NAMES: Set[str] = set(EXTRACTION_FIELDS.keys())

# Convenience: fields by type
INT_FIELDS: Set[str] = {
    name for name, cfg in EXTRACTION_FIELDS.items()
    if cfg.field_type == "int"
}
STR_FIELDS: Set[str] = {
    name for name, cfg in EXTRACTION_FIELDS.items()
    if cfg.field_type == "str"
}
BOOL_FIELDS: Set[str] = {
    name for name, cfg in EXTRACTION_FIELDS.items()
    if cfg.field_type == "bool"
}
ENUM_FIELDS: Set[str] = {
    name for name, cfg in EXTRACTION_FIELDS.items()
    if cfg.field_type == "enum"
}

# Convenience: contact fields (special handling)
CONTACT_FIELDS: Set[str] = {"contact_info", "contact_type"}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_field_config(field_name: str) -> Optional[FieldConfig]:
    """
    Get configuration for a specific field.

    Args:
        field_name: Name of the field

    Returns:
        FieldConfig or None if not found
    """
    return EXTRACTION_FIELDS.get(field_name)


def get_phase_fields(phase: str) -> List[str]:
    """
    Get list of fields expected in a SPIN phase.

    Args:
        phase: SPIN phase name (situation, problem, implication, need_payoff)

    Returns:
        List of field names, empty if phase not found
    """
    return PHASE_FIELDS.get(phase, [])


def is_field_valid_for_phase(field_name: str, phase: str) -> bool:
    """
    Check if a field is expected in the given SPIN phase.

    Args:
        field_name: Field name to check
        phase: Current SPIN phase

    Returns:
        True if field is expected in this phase or is phase-independent
    """
    config = get_field_config(field_name)
    if config is None:
        return False

    # Phase-independent fields (contact_info, etc.)
    if config.spin_phase is None:
        return True

    # Check if field's phase matches
    return config.spin_phase == phase


def get_allowed_values(field_name: str) -> Optional[List[str]]:
    """
    Get allowed values for an enum field.

    Args:
        field_name: Field name

    Returns:
        List of allowed values, or None if not an enum
    """
    config = get_field_config(field_name)
    if config is None:
        return None
    return config.get_allowed_values()


def get_extraction_config() -> Dict[str, Any]:
    """
    Get full extraction configuration as a dictionary.

    Used by ExtractionValidator for configuration.

    Returns:
        Dictionary with all extraction settings
    """
    return {
        "fields": {
            name: {
                "description": cfg.description,
                "type": cfg.field_type,
                "spin_phase": cfg.spin_phase,
                "validation": cfg.validation,
            }
            for name, cfg in EXTRACTION_FIELDS.items()
        },
        "phase_fields": PHASE_FIELDS,
        "validation_rules": VALIDATION_RULES,
    }


# =============================================================================
# PROMPT GENERATION
# =============================================================================

def get_extraction_prompt_instructions() -> str:
    """
    Get extraction instructions for LLM prompt.

    These instructions are appended to the system prompt to guide
    the LLM in correctly filling extracted_data fields.

    Returns:
        Formatted string with extraction rules
    """
    parts = []

    # Header
    header = PROMPT_INSTRUCTIONS.get("header", "")
    if header:
        parts.append(header.strip())

    # Field rules
    field_rules = PROMPT_INSTRUCTIONS.get("field_rules", "")
    if field_rules:
        parts.append(field_rules.strip())

    # Examples
    examples = PROMPT_INSTRUCTIONS.get("examples", "")
    if examples:
        parts.append(examples.strip())

    # If no instructions in YAML, generate default
    if not parts:
        parts.append(_generate_default_instructions())

    return "\n\n".join(parts)


def _generate_default_instructions() -> str:
    """
    Generate default extraction instructions from field configs.

    Used as fallback if prompt_instructions not in YAML.
    """
    lines = [
        "## Правила извлечения данных (extracted_data)",
        "",
        "КРИТИЧНО: Заполняй extracted_data ТОЛЬКО если данные соответствуют полю!",
        "Пустой extracted_data лучше неправильного.",
        "",
    ]

    for name, cfg in EXTRACTION_FIELDS.items():
        lines.append(f"- **{name}** ({cfg.field_type}): {cfg.description}")

        # Add examples
        if cfg.examples_valid:
            valid_ex = cfg.examples_valid[0]
            lines.append(f"  - ✅ \"{valid_ex.get('source', '')}\" → {name}: {valid_ex.get('value')}")

        if cfg.examples_invalid:
            invalid_ex = cfg.examples_invalid[0]
            lines.append(f"  - ❌ {invalid_ex.get('value')} — {invalid_ex.get('reason', 'invalid')}")

        lines.append("")

    return "\n".join(lines)


def get_field_description(field_name: str) -> str:
    """
    Get description for a field (for LLM context).

    Args:
        field_name: Field name

    Returns:
        Description string
    """
    config = get_field_config(field_name)
    if config is None:
        return f"Unknown field: {field_name}"
    return config.description


def get_invalid_examples(field_name: str) -> List[Dict[str, Any]]:
    """
    Get invalid examples for a field (for LLM negative examples).

    Args:
        field_name: Field name

    Returns:
        List of invalid example dicts with 'value' and 'reason'
    """
    config = get_field_config(field_name)
    if config is None:
        return []
    return config.examples_invalid


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_extraction_config() -> bool:
    """
    Validate that extraction configuration is consistent.

    This should be called at application startup to catch config errors.

    Returns:
        True if configuration is valid

    Raises:
        ValueError: If configuration is inconsistent
    """
    errors = []

    # Check all phase_fields reference valid fields
    for phase, fields in PHASE_FIELDS.items():
        for field_name in fields:
            if field_name not in EXTRACTION_FIELDS:
                errors.append(
                    f"phase_fields.{phase} references unknown field '{field_name}'"
                )

    # Check field configurations
    for name, cfg in EXTRACTION_FIELDS.items():
        # Enum fields must have allowed_values
        if cfg.field_type == "enum":
            if not cfg.get_allowed_values():
                errors.append(
                    f"Field '{name}' is enum but has no allowed_values"
                )

        # Int fields should have min/max
        if cfg.field_type == "int":
            if cfg.get_min_value() is None or cfg.get_max_value() is None:
                logger.warning(
                    f"Field '{name}' is int but missing min/max validation"
                )

    if errors:
        error_msg = "Extraction config validation failed:\n" + "\n".join(errors)
        raise ValueError(error_msg)

    logger.info(
        f"Extraction config validated: {len(EXTRACTION_FIELDS)} fields, "
        f"{len(PHASE_FIELDS)} phases"
    )
    return True


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Config classes
    "FieldConfig",
    "ExtractionConfig",
    # Config values
    "EXTRACTION_FIELDS",
    "PHASE_FIELDS",
    "VALIDATION_RULES",
    "PROMPT_INSTRUCTIONS",
    # Convenience sets
    "ALL_FIELD_NAMES",
    "INT_FIELDS",
    "STR_FIELDS",
    "BOOL_FIELDS",
    "ENUM_FIELDS",
    "CONTACT_FIELDS",
    # Functions
    "get_field_config",
    "get_phase_fields",
    "is_field_valid_for_phase",
    "get_allowed_values",
    "get_extraction_config",
    "get_extraction_prompt_instructions",
    "get_field_description",
    "get_invalid_examples",
    "validate_extraction_config",
]
