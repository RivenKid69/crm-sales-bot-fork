"""
Extracted Data Validation Module.

Provides validation for LLM-extracted data fields to prevent hallucinations
and incorrect field mappings. This addresses issues like:
- "два-три человека" being mapped to current_tools instead of company_size
- "теряем клиентов" being mapped to contact_info instead of pain_point
- Random text being stored as contact_info

Architecture:
    constants.yaml (extraction section)
         |
         v
    extraction_ssot.py (loads rules, exports config)
         |
         v
    extraction_validator.py (THIS MODULE - validates fields)
         |
         v
    classifier/llm/classifier.py (post-processing)

Design Principles:
1. Explicit validation rules from YAML config (SSoT)
2. Type-safe validation with dataclasses
3. Fail-safe: prefer empty over wrong data
4. Comprehensive logging for debugging
5. Reusable validators for conditions and extractors

Usage:
    from src.classifier.extractors.extraction_validator import (
        ExtractionValidator,
        validate_extracted_data,
        ValidationResult,
    )

    validator = ExtractionValidator()
    result = validator.validate_field("contact_info", "теряем клиентов")
    if not result.is_valid:
        print(f"Invalid: {result.error}")  # "Not a valid phone or email"
"""

import re
import logging
from typing import Dict, Any, Optional, List, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class FieldType(Enum):
    """Supported field types for extracted data."""
    INT = "int"
    STR = "str"
    BOOL = "bool"
    ENUM = "enum"


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Data is completely wrong (e.g., text in contact_info)
    WARNING = "warning"  # Data is suspicious but might be valid
    INFO = "info"        # Minor issue, data accepted


@dataclass
class FieldValidationResult:
    """Result of validating a single field."""
    field_name: str
    is_valid: bool
    original_value: Any
    normalized_value: Optional[Any] = None
    error: Optional[str] = None
    severity: ValidationSeverity = ValidationSeverity.ERROR
    suggested_field: Optional[str] = None  # Where this value should go instead

    def __bool__(self) -> bool:
        return self.is_valid


@dataclass
class ExtractionValidationResult:
    """Result of validating entire extracted_data dict."""
    is_valid: bool
    original_data: Dict[str, Any]
    validated_data: Dict[str, Any]
    field_results: Dict[str, FieldValidationResult] = field(default_factory=dict)
    removed_fields: List[str] = field(default_factory=list)
    corrected_fields: Dict[str, str] = field(default_factory=dict)  # field -> suggested_field
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.is_valid


class ExtractionValidator:
    """
    Validates and normalizes LLM-extracted data fields.

    Prevents common LLM hallucinations:
    - Text in contact_info (should only be phone/email)
    - People count in current_tools (should be in company_size)
    - Pain points in contact_info (should be in pain_point)

    Uses rules from constants.yaml (extraction section) via extraction_ssot.
    """

    # =========================================================================
    # PHONE PATTERNS (from ContactValidator)
    # =========================================================================
    PHONE_PATTERNS = [
        # +7 format: +7 999 123-45-67, +7(999)1234567, +79991234567
        re.compile(r'^\+7[\s\-\.]?\(?(\d{3})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
        # 8 format: 8 999 123-45-67, 8(999)1234567
        re.compile(r'^8[\s\-\.]?\(?(\d{3})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
        # 10-digit local: 9991234567
        re.compile(r'^(\d{3})[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
    ]

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        re.IGNORECASE
    )

    # Valid Russian mobile prefixes (900-999 range)
    VALID_MOBILE_PREFIXES = set(range(900, 1000))

    # Valid city codes
    VALID_CITY_CODES = {495, 499, 812, 343, 383, 861}

    # =========================================================================
    # TOOL PATTERNS (from DataExtractor)
    # =========================================================================
    TOOL_PATTERNS = {
        r'(?:в\s+)?excel': "Excel",
        r'(?:в\s+)?эксел': "Excel",
        r'(?:в\s+)?табли[цч]': "таблицы",
        r'(?:в\s+)?гугл\s*(?:табли|докс|sheets|docs)': "Google Таблицы",
        r'(?:в\s+)?1[сc]': "1С",
        r'(?:в\s+)?битрикс': "Битрикс24",
        r'(?:в\s+)?амо': "AmoCRM",
        r'(?:в\s+)?мегаплан': "Мегаплан",
        r'(?:в\s+)?notion': "Notion",
        r'(?:в\s+)?trello': "Trello",
        r'(?:на\s+)?бумаг': "на бумаге",
        r'(?:в\s+)?блокнот': "в блокноте",
        r'(?:в\s+)?голов': "в головах",
        r'вручную|руками': "вручную",
        r'никак|нигде|ничего': "никак не ведём",
    }

    ALLOWED_TOOLS: Set[str] = {
        "Excel", "Google Таблицы", "таблицы", "1С", "Битрикс24", "AmoCRM",
        "Мегаплан", "Notion", "Trello", "на бумаге", "в блокноте",
        "в головах", "вручную", "никак не ведём", "другая CRM",
    }

    # =========================================================================
    # PAIN PATTERNS (for detecting misplaced pain_points)
    # =========================================================================
    PAIN_KEYWORDS = [
        'теря', 'упуска', 'забыва', 'ошиб', 'хаос', 'контрол',
        'проблем', 'сложн', 'долго', 'рутин', 'вручную', 'клиент',
        'менеджер', 'не вид', 'не понима', 'не знаю',
    ]

    # =========================================================================
    # PEOPLE COUNT PATTERNS (for detecting misplaced company_size)
    # =========================================================================
    PEOPLE_PATTERNS = [
        re.compile(r'(\d+)\s*(?:человек|чел\.?|сотрудник|менеджер|продавец|работник)', re.IGNORECASE),
        re.compile(r'(?:два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s*(?:человек|чел)', re.IGNORECASE),
        re.compile(r'нас\s*(\d+)', re.IGNORECASE),
        re.compile(r'команда?\s*(?:из|в|на)?\s*(\d+)', re.IGNORECASE),
    ]

    # =========================================================================
    # BUSINESS TYPE PATTERNS
    # =========================================================================
    BUSINESS_TYPE_PATTERNS = {
        r'магазин|розни[цч]|ритейл|retail': "розничная торговля",
        r'опт(?:ов)?|b2b': "оптовые продажи",
        r'ресторан|кафе|общепит|еда': "общепит",
        r'услуг|сервис|service': "сфера услуг",
        r'салон|красот|spa|спа': "салон красоты",
        r'клиник|медицин|врач': "медицина",
        r'недвижим|агентств|риэлтор': "недвижимость",
        r'склад|логистик|доставк': "логистика",
        r'производств|завод|фабрик': "производство",
        r'it|айти|программ|разработ': "IT",
        r'строител|ремонт': "строительство",
        r'образован|обучен|курс': "образование",
    }

    ALLOWED_BUSINESS_TYPES: Set[str] = {
        "розничная торговля", "оптовые продажи", "общепит", "сфера услуг",
        "салон красоты", "медицина", "недвижимость", "логистика",
        "производство", "IT", "строительство", "образование", "другое",
    }

    # =========================================================================
    # PAIN CATEGORIES
    # =========================================================================
    ALLOWED_PAIN_CATEGORIES: Set[str] = {
        "losing_clients", "no_control", "manual_work", "manager_issues", "chaos",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize validator.

        Args:
            config: Optional config override. If not provided,
                   loads from extraction_ssot.
        """
        self._config = config
        if self._config is None:
            self._load_config()

    def _load_config(self) -> None:
        """Load configuration from extraction_ssot."""
        try:
            from src.extraction_ssot import get_extraction_config
            self._config = get_extraction_config()
        except ImportError:
            logger.warning(
                "Could not import extraction_ssot, using default config"
            )
            self._config = {}

    # =========================================================================
    # MAIN VALIDATION METHODS
    # =========================================================================

    def validate_extracted_data(
        self,
        extracted_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ExtractionValidationResult:
        """
        Validate entire extracted_data dictionary.

        Removes invalid fields and corrects misplacements.

        Args:
            extracted_data: Dictionary from LLM extraction
            context: Optional context (spin_phase, etc.)

        Returns:
            ExtractionValidationResult with validated data
        """
        if not extracted_data:
            return ExtractionValidationResult(
                is_valid=True,
                original_data={},
                validated_data={},
            )

        context = context or {}
        validated_data: Dict[str, Any] = {}
        field_results: Dict[str, FieldValidationResult] = {}
        removed_fields: List[str] = []
        corrected_fields: Dict[str, str] = {}
        errors: List[str] = []
        warnings: List[str] = []

        for field_name, value in extracted_data.items():
            if value is None:
                continue

            result = self.validate_field(field_name, value, context)
            field_results[field_name] = result

            if result.is_valid:
                # Use normalized value if available
                validated_data[field_name] = (
                    result.normalized_value
                    if result.normalized_value is not None
                    else value
                )
            else:
                removed_fields.append(field_name)
                errors.append(f"{field_name}: {result.error}")

                # Track suggested corrections
                if result.suggested_field:
                    corrected_fields[field_name] = result.suggested_field
                    warnings.append(
                        f"'{field_name}' value '{value}' should be in '{result.suggested_field}'"
                    )

        # Log validation results for debugging
        if removed_fields:
            logger.info(
                "Extraction validation removed fields",
                extra={
                    "removed": removed_fields,
                    "corrections": corrected_fields,
                    "original_keys": list(extracted_data.keys()),
                }
            )

        return ExtractionValidationResult(
            is_valid=len(errors) == 0,
            original_data=extracted_data,
            validated_data=validated_data,
            field_results=field_results,
            removed_fields=removed_fields,
            corrected_fields=corrected_fields,
            errors=errors,
            warnings=warnings,
        )

    def validate_field(
        self,
        field_name: str,
        value: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> FieldValidationResult:
        """
        Validate a single field value.

        Args:
            field_name: Name of the field
            value: Value to validate
            context: Optional context

        Returns:
            FieldValidationResult
        """
        context = context or {}

        # Route to specific validator
        validator_method = getattr(self, f"_validate_{field_name}", None)

        if validator_method:
            return validator_method(value, context)
        else:
            # Unknown field - accept as-is with warning
            logger.debug(f"No validator for field '{field_name}', accepting as-is")
            return FieldValidationResult(
                field_name=field_name,
                is_valid=True,
                original_value=value,
                normalized_value=value,
            )

    # =========================================================================
    # FIELD-SPECIFIC VALIDATORS
    # =========================================================================

    def _validate_company_size(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """
        Validate company_size field.

        Must be an integer between 1 and 10000.
        """
        field_name = "company_size"

        # Convert to int if possible
        if isinstance(value, str):
            # Try to extract number from string like "5 человек"
            match = re.search(r'(\d+)', value)
            if match:
                try:
                    value = int(match.group(1))
                except ValueError:
                    pass

        # Validate type
        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error=f"Must be an integer, got {type(value).__name__}",
                )

        # Validate range
        if value < 1:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Company size must be at least 1",
            )

        if value > 10000:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Company size cannot exceed 10000",
                severity=ValidationSeverity.WARNING,
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value,
        )

    def _validate_current_tools(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """
        Validate current_tools field.

        Must be a valid CRM/tool, NOT people count!
        """
        field_name = "current_tools"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        value_lower = value.lower().strip()

        # Check if this is actually a people count (common LLM error)
        for pattern in self.PEOPLE_PATTERNS:
            if pattern.search(value_lower):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This is a people count, not a tool",
                    suggested_field="company_size",
                )

        # Check if this is a pain point (common LLM error)
        for keyword in self.PAIN_KEYWORDS:
            if keyword in value_lower and len(value_lower) > 15:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This looks like a pain point, not a tool",
                    suggested_field="pain_point",
                )

        # Try to normalize to known tool
        normalized = None
        for pattern, tool_name in self.TOOL_PATTERNS.items():
            if re.search(pattern, value_lower, re.IGNORECASE):
                normalized = tool_name
                break

        # If not matched by pattern, check if it's in allowed list
        if normalized is None:
            # Check exact match (case-insensitive)
            for allowed in self.ALLOWED_TOOLS:
                if value_lower == allowed.lower():
                    normalized = allowed
                    break

        if normalized is None:
            # Accept with warning if it looks like a tool name
            if len(value) <= 30 and not any(c.isdigit() for c in value):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=True,
                    original_value=value,
                    normalized_value=value,
                    severity=ValidationSeverity.WARNING,
                )
            else:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error=f"Unknown tool. Allowed: {', '.join(sorted(self.ALLOWED_TOOLS)[:5])}...",
                )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=normalized,
        )

    def _validate_business_type(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate business_type field."""
        field_name = "business_type"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        value_lower = value.lower().strip()

        # Try to normalize to known business type
        normalized = None
        for pattern, btype in self.BUSINESS_TYPE_PATTERNS.items():
            if re.search(pattern, value_lower, re.IGNORECASE):
                normalized = btype
                break

        # Check exact match
        if normalized is None:
            for allowed in self.ALLOWED_BUSINESS_TYPES:
                if value_lower == allowed.lower():
                    normalized = allowed
                    break

        if normalized is None:
            # Accept as "другое" if reasonable length
            if len(value) <= 50:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=True,
                    original_value=value,
                    normalized_value="другое",
                    severity=ValidationSeverity.WARNING,
                )
            else:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="Invalid business type",
                )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=normalized,
        )

    def _validate_contact_info(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """
        Validate contact_info field.

        CRITICAL: Must be ONLY a valid phone number or email!
        This is where most LLM hallucinations occur.
        """
        field_name = "contact_info"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        value = value.strip()

        # Empty string is invalid
        if not value:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Empty contact info",
            )

        value_lower = value.lower()

        # IMPORTANT: Check desired outcome FIRST (before pain point)
        # Because "контрол" appears in both, but "хочу контролировать" is clearly
        # a desired outcome, not a pain point
        outcome_patterns = [
            r'помог', r'контролир', r'автоматиз', r'хотел', r'хочу',
            r'было бы', r'упрост', r'улучш', r'типа',
        ]
        for pattern in outcome_patterns:
            if re.search(pattern, value_lower):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This looks like desired outcome, not a contact",
                    suggested_field="desired_outcome",
                )

        # Check if this is a pain point (common LLM error)
        for keyword in self.PAIN_KEYWORDS:
            if keyword in value_lower:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This is a pain point, not a contact",
                    suggested_field="pain_point",
                )

        # Check if this is a people count (common LLM error)
        for pattern in self.PEOPLE_PATTERNS:
            if pattern.search(value_lower):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This is a people count, not a contact",
                    suggested_field="company_size",
                )

        # Try to validate as email
        if '@' in value:
            if self.EMAIL_PATTERN.match(value):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=True,
                    original_value=value,
                    normalized_value=value.lower(),
                )
            else:
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="Invalid email format",
                )

        # Try to validate as phone
        for pattern in self.PHONE_PATTERNS:
            match = pattern.match(value)
            if match:
                groups = match.groups()
                prefix = int(groups[0])

                # Validate prefix
                if prefix in self.VALID_MOBILE_PREFIXES or prefix in self.VALID_CITY_CODES:
                    normalized = f"+7{''.join(groups)}"
                    return FieldValidationResult(
                        field_name=field_name,
                        is_valid=True,
                        original_value=value,
                        normalized_value=normalized,
                    )

        # Check if it has enough digits to be a phone
        digits = re.sub(r'\D', '', value)
        if len(digits) >= 10:
            # Might be a phone, try to extract
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Contains digits but not a valid phone format",
                severity=ValidationSeverity.WARNING,
            )

        # Not a valid contact
        return FieldValidationResult(
            field_name=field_name,
            is_valid=False,
            original_value=value,
            error="Not a valid phone number or email. contact_info must be ONLY +7XXX... or xxx@xxx.xx",
        )

    def _validate_contact_type(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate contact_type field."""
        field_name = "contact_type"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        allowed = {"phone", "email"}
        if value.lower() not in allowed:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be one of: {allowed}",
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value.lower(),
        )

    def _validate_pain_point(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate pain_point field."""
        field_name = "pain_point"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        value = value.strip()

        # Check minimum length
        if len(value) < 3:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Pain point too short (min 3 chars)",
            )

        # Check if this is actually a contact (misplacement)
        if '@' in value or re.search(r'\+7|\d{10}', value):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="This looks like a contact, not a pain point",
                suggested_field="contact_info",
            )

        # Check if this is actually a tool
        for pattern in self.TOOL_PATTERNS.keys():
            if re.fullmatch(pattern, value.lower()):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=False,
                    original_value=value,
                    error="This looks like a tool, not a pain point",
                    suggested_field="current_tools",
                )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value,
        )

    def _validate_pain_category(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate pain_category field."""
        field_name = "pain_category"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        if value not in self.ALLOWED_PAIN_CATEGORIES:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be one of: {self.ALLOWED_PAIN_CATEGORIES}",
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value,
        )

    def _validate_pain_impact(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate pain_impact field."""
        field_name = "pain_impact"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        if len(value.strip()) < 3:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Pain impact too short",
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value.strip(),
        )

    def _validate_financial_impact(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate financial_impact field."""
        field_name = "financial_impact"

        # Accept string or number
        if isinstance(value, (int, float)):
            value = str(int(value))

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string or number, got {type(value).__name__}",
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value.strip(),
        )

    def _validate_desired_outcome(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate desired_outcome field."""
        field_name = "desired_outcome"

        if not isinstance(value, str):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error=f"Must be a string, got {type(value).__name__}",
            )

        value = value.strip()

        if len(value) < 5:
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="Desired outcome too short (min 5 chars)",
            )

        # Check if this is actually a contact
        if '@' in value or re.search(r'\+7|\d{10}', value):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=False,
                original_value=value,
                error="This looks like a contact, not desired outcome",
                suggested_field="contact_info",
            )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=True,
            original_value=value,
            normalized_value=value,
        )

    def _validate_value_acknowledged(
        self,
        value: Any,
        context: Dict[str, Any]
    ) -> FieldValidationResult:
        """Validate value_acknowledged field."""
        field_name = "value_acknowledged"

        if isinstance(value, bool):
            return FieldValidationResult(
                field_name=field_name,
                is_valid=True,
                original_value=value,
                normalized_value=value,
            )

        # Try to convert string to bool
        if isinstance(value, str):
            if value.lower() in ('true', 'да', 'yes', '1'):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=True,
                    original_value=value,
                    normalized_value=True,
                )
            elif value.lower() in ('false', 'нет', 'no', '0'):
                return FieldValidationResult(
                    field_name=field_name,
                    is_valid=True,
                    original_value=value,
                    normalized_value=False,
                )

        return FieldValidationResult(
            field_name=field_name,
            is_valid=False,
            original_value=value,
            error="Must be a boolean (true/false)",
        )


# =============================================================================
# GLOBAL INSTANCE AND HELPER FUNCTIONS
# =============================================================================

_validator = ExtractionValidator()


def validate_extracted_data(
    extracted_data: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> ExtractionValidationResult:
    """
    Validate extracted_data dictionary.

    Main entry point for post-processing LLM extraction results.

    Args:
        extracted_data: Dictionary from LLM extraction
        context: Optional context (spin_phase, etc.)

    Returns:
        ExtractionValidationResult with validated data
    """
    return _validator.validate_extracted_data(extracted_data, context)


def validate_field(
    field_name: str,
    value: Any,
    context: Optional[Dict[str, Any]] = None
) -> FieldValidationResult:
    """
    Validate a single field.

    Args:
        field_name: Name of the field
        value: Value to validate
        context: Optional context

    Returns:
        FieldValidationResult
    """
    return _validator.validate_field(field_name, value, context)


def is_valid_contact_info(value: str) -> bool:
    """
    Quick check if value is a valid contact (phone/email).

    Args:
        value: String to check

    Returns:
        True if valid phone or email
    """
    result = _validator.validate_field("contact_info", value)
    return result.is_valid


def is_valid_tool(value: str) -> bool:
    """
    Quick check if value is a valid CRM tool.

    Args:
        value: String to check

    Returns:
        True if valid tool
    """
    result = _validator.validate_field("current_tools", value)
    return result.is_valid


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Classes
    "ExtractionValidator",
    "FieldValidationResult",
    "ExtractionValidationResult",
    "FieldType",
    "ValidationSeverity",
    # Functions
    "validate_extracted_data",
    "validate_field",
    "is_valid_contact_info",
    "is_valid_tool",
]
