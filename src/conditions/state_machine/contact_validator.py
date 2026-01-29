"""
Contact Validation Module.

Provides explicit validation logic for contact information:
- Email validation
- Phone validation (Russian phone formats)
- Combined contact info validation

This module addresses the implicit logic issue in ready_for_close condition
by making validation rules explicit and testable.

Design Decisions:
1. Explicit validation rules with clear documentation
2. Support for multiple contact formats (string, dict, nested)
3. Russian phone number validation with proper format checking
4. Reusable validators for conditions and extractors
"""

import re
from typing import Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
from enum import Enum


class ContactType(Enum):
    """Types of contact information."""
    EMAIL = "email"
    PHONE = "phone"
    NAME = "name"
    UNKNOWN = "unknown"


@dataclass
class ValidationResult:
    """Result of contact validation."""
    is_valid: bool
    contact_type: ContactType
    normalized_value: Optional[str] = None
    raw_value: Optional[str] = None
    error: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid


class ContactValidator:
    """
    Validates and normalizes contact information.

    Provides explicit validation rules for:
    - Email: standard RFC-compliant patterns
    - Phone: Russian phone formats (+7, 8, 10-digit)
    - Name: basic name validation

    Usage:
        validator = ContactValidator()
        result = validator.validate_email("user@example.com")
        if result.is_valid:
            print(f"Normalized: {result.normalized_value}")
    """

    # Email pattern - more strict than DataExtractor's pattern
    # Requires valid TLD and reasonable structure
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        re.IGNORECASE
    )

    # Russian phone patterns with named groups for validation
    # Supports: +7, 8, or 10-digit local
    PHONE_PATTERNS = [
        # +7 format: +7 999 123-45-67, +7(999)1234567, +79991234567
        re.compile(r'^\+7[\s\-\.]?\(?(\d{3})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
        # 8 format: 8 999 123-45-67, 8(999)1234567
        re.compile(r'^8[\s\-\.]?\(?(\d{3})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
        # 10-digit local: 9991234567, 999-123-45-67
        re.compile(r'^(\d{3})[\s\-\.]?(\d{3})[\s\-\.]?(\d{2})[\s\-\.]?(\d{2})$'),
    ]

    # Valid Russian mobile prefixes (900-999 range)
    VALID_MOBILE_PREFIXES = set(range(900, 1000))
    # Valid Kazakhstan mobile prefixes
    VALID_KZ_MOBILE_PREFIXES = set(range(700, 710)) | {747, 771} | set(range(775, 779))

    # Russian city codes (Moscow, SPb, etc.)
    VALID_CITY_CODES = {495, 499, 812, 343, 383, 861}
    # Kazakhstan city codes
    VALID_KZ_CITY_CODES = {727, 717}

    # Combined defaults (used when no config provided)
    _DEFAULT_PREFIXES = VALID_MOBILE_PREFIXES | VALID_KZ_MOBILE_PREFIXES
    _DEFAULT_CITY_CODES = VALID_CITY_CODES | VALID_KZ_CITY_CODES

    # Minimum name length to be considered valid
    MIN_NAME_LENGTH = 2

    # Blacklist patterns that look like phone numbers but aren't
    # (prevents false positives from DataExtractor)
    PHONE_BLACKLIST_PATTERNS = [
        re.compile(r'^[01]{10}$'),  # All 0s and 1s
        re.compile(r'^(\d)\1{9}$'),  # Same digit repeated (1111111111)
        re.compile(r'^1234567890$'),  # Sequential
        re.compile(r'^0987654321$'),  # Reverse sequential
        re.compile(r'^0000000000$'),  # All zeros
    ]

    @classmethod
    def _build_valid_prefixes(cls, config: dict) -> set:
        """Build valid prefix set from config (SSoT)."""
        prefixes = set()
        ru_range = config.get("ru_mobile_range", [900, 999])
        prefixes |= set(range(ru_range[0], ru_range[1] + 1))
        for r in config.get("kz_mobile_ranges", []):
            prefixes |= set(range(r[0], r[1] + 1))
        prefixes |= set(config.get("kz_mobile_explicit", []))
        return prefixes

    @classmethod
    def _build_city_codes(cls, config: dict) -> set:
        """Build city codes set from config (SSoT)."""
        return set(config.get("city_codes", [495, 499, 812]))

    def __init__(self, phone_config: dict = None):
        if phone_config:
            self.valid_prefixes = self._build_valid_prefixes(phone_config)
            self.valid_city_codes = self._build_city_codes(phone_config)
        else:
            self.valid_prefixes = self._DEFAULT_PREFIXES
            self.valid_city_codes = self._DEFAULT_CITY_CODES

    def validate_email(self, value: str) -> ValidationResult:
        """
        Validate email address.

        Args:
            value: Email string to validate

        Returns:
            ValidationResult with normalized email (lowercase) if valid
        """
        if not value or not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.EMAIL,
                raw_value=value,
                error="Email value is empty or not a string"
            )

        value = value.strip()

        if not self.EMAIL_PATTERN.match(value):
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.EMAIL,
                raw_value=value,
                error="Email format is invalid"
            )

        # Additional checks
        local_part, domain = value.split('@')

        # Check for reasonable lengths
        if len(local_part) > 64 or len(domain) > 255:
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.EMAIL,
                raw_value=value,
                error="Email parts exceed maximum length"
            )

        # Normalize to lowercase
        normalized = value.lower()

        return ValidationResult(
            is_valid=True,
            contact_type=ContactType.EMAIL,
            normalized_value=normalized,
            raw_value=value
        )

    def validate_phone(self, value: str) -> ValidationResult:
        """
        Validate Russian phone number.

        Validates against:
        - Proper format (+7, 8, or 10-digit)
        - Valid mobile prefix (900-999) or city code
        - Not a blacklisted pattern (sequential, repeated digits)

        Args:
            value: Phone string to validate

        Returns:
            ValidationResult with normalized phone (+7XXXXXXXXXX) if valid
        """
        if not value or not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.PHONE,
                raw_value=value,
                error="Phone value is empty or not a string"
            )

        value = value.strip()

        # Check blacklist first
        digits_only = re.sub(r'\D', '', value)
        for pattern in self.PHONE_BLACKLIST_PATTERNS:
            if pattern.match(digits_only[-10:] if len(digits_only) >= 10 else digits_only):
                return ValidationResult(
                    is_valid=False,
                    contact_type=ContactType.PHONE,
                    raw_value=value,
                    error="Phone number matches blacklist pattern (sequential or repeated)"
                )

        # Try each pattern
        for pattern in self.PHONE_PATTERNS:
            match = pattern.match(value)
            if match:
                groups = match.groups()
                prefix = int(groups[0])

                # Validate prefix
                if prefix not in self.valid_prefixes and prefix not in self.valid_city_codes:
                    return ValidationResult(
                        is_valid=False,
                        contact_type=ContactType.PHONE,
                        raw_value=value,
                        error=f"Invalid phone prefix: {prefix}"
                    )

                # Normalize to +7XXXXXXXXXX format
                normalized = f"+7{''.join(groups)}"

                return ValidationResult(
                    is_valid=True,
                    contact_type=ContactType.PHONE,
                    normalized_value=normalized,
                    raw_value=value
                )

        return ValidationResult(
            is_valid=False,
            contact_type=ContactType.PHONE,
            raw_value=value,
            error="Phone number format is invalid"
        )

    def validate_name(self, value: str) -> ValidationResult:
        """
        Validate contact name.

        Basic validation:
        - Non-empty
        - At least MIN_NAME_LENGTH characters
        - Contains at least one letter

        Args:
            value: Name string to validate

        Returns:
            ValidationResult with normalized name (stripped) if valid
        """
        if not value or not isinstance(value, str):
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.NAME,
                raw_value=value,
                error="Name value is empty or not a string"
            )

        value = value.strip()

        if len(value) < self.MIN_NAME_LENGTH:
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.NAME,
                raw_value=value,
                error=f"Name too short (min {self.MIN_NAME_LENGTH} chars)"
            )

        # Must contain at least one letter
        if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', value):
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.NAME,
                raw_value=value,
                error="Name must contain at least one letter"
            )

        return ValidationResult(
            is_valid=True,
            contact_type=ContactType.NAME,
            normalized_value=value,
            raw_value=value
        )

    def detect_contact_type(self, value: str) -> ContactType:
        """
        Detect the type of contact information.

        Args:
            value: String to analyze

        Returns:
            ContactType enum value
        """
        if not value or not isinstance(value, str):
            return ContactType.UNKNOWN

        value = value.strip()

        # Check email first (has @ symbol)
        if '@' in value and self.validate_email(value).is_valid:
            return ContactType.EMAIL

        # Check phone (mostly digits)
        digits = re.sub(r'\D', '', value)
        if len(digits) >= 10 and self.validate_phone(value).is_valid:
            return ContactType.PHONE

        return ContactType.UNKNOWN

    def validate_any(self, value: str) -> ValidationResult:
        """
        Validate contact information of any type (auto-detect).

        Args:
            value: Contact string to validate (email or phone)

        Returns:
            ValidationResult with detected type and validation status
        """
        contact_type = self.detect_contact_type(value)

        if contact_type == ContactType.EMAIL:
            return self.validate_email(value)
        elif contact_type == ContactType.PHONE:
            return self.validate_phone(value)
        else:
            return ValidationResult(
                is_valid=False,
                contact_type=ContactType.UNKNOWN,
                raw_value=value,
                error="Unable to detect contact type (not a valid email or phone)"
            )

    def validate_contact_info(
        self,
        contact_info: Union[str, Dict[str, Any], None]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate contact_info from collected_data.

        Handles multiple formats:
        1. String (email or phone from DataExtractor)
        2. Dict with email/phone/name keys
        3. None

        Args:
            contact_info: Contact info in any supported format

        Returns:
            Tuple of (is_valid, normalized_dict, error_message)
            normalized_dict contains validated and normalized contact fields
        """
        if contact_info is None:
            return False, None, "contact_info is None"

        # Handle string format (from DataExtractor)
        if isinstance(contact_info, str):
            contact_info = contact_info.strip()
            if not contact_info:
                return False, None, "contact_info is empty string"

            result = self.validate_any(contact_info)
            if result.is_valid:
                normalized = {}
                if result.contact_type == ContactType.EMAIL:
                    normalized["email"] = result.normalized_value
                elif result.contact_type == ContactType.PHONE:
                    normalized["phone"] = result.normalized_value
                return True, normalized, None
            else:
                return False, None, result.error

        # Handle dict format
        if isinstance(contact_info, dict):
            normalized = {}
            has_valid_contact = False
            errors = []

            # Check email
            email = contact_info.get("email")
            if email:
                result = self.validate_email(email)
                if result.is_valid:
                    normalized["email"] = result.normalized_value
                    has_valid_contact = True
                else:
                    errors.append(f"email: {result.error}")

            # Check phone
            phone = contact_info.get("phone")
            if phone:
                result = self.validate_phone(phone)
                if result.is_valid:
                    normalized["phone"] = result.normalized_value
                    has_valid_contact = True
                else:
                    errors.append(f"phone: {result.error}")

            # Check name (optional, doesn't make contact valid by itself)
            name = contact_info.get("name")
            if name:
                result = self.validate_name(name)
                if result.is_valid:
                    normalized["name"] = result.normalized_value

            if has_valid_contact:
                return True, normalized, None
            else:
                error_msg = "; ".join(errors) if errors else "No valid email or phone in dict"
                return False, None, error_msg

        return False, None, f"Unsupported contact_info type: {type(contact_info)}"

    def extract_and_validate_from_collected_data(
        self,
        collected_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Extract and validate contact information from collected_data.

        Checks multiple sources in order of priority:
        1. contact_info field (from DataExtractor)
        2. Top-level email field
        3. Top-level phone field
        4. Top-level contact field (legacy)

        Args:
            collected_data: Full collected_data dict from state machine

        Returns:
            Tuple of (has_valid_contact, normalized_dict, error_message)
        """
        if not collected_data:
            return False, None, "collected_data is empty"

        # Priority 1: Check contact_info field
        contact_info = collected_data.get("contact_info")
        if contact_info:
            is_valid, normalized, error = self.validate_contact_info(contact_info)
            if is_valid:
                return True, normalized, None

        # Priority 2: Check top-level email
        email = collected_data.get("email")
        if email:
            result = self.validate_email(email)
            if result.is_valid:
                return True, {"email": result.normalized_value}, None

        # Priority 3: Check top-level phone
        phone = collected_data.get("phone")
        if phone:
            result = self.validate_phone(phone)
            if result.is_valid:
                return True, {"phone": result.normalized_value}, None

        # Priority 4: Check legacy contact field (treat as auto-detect)
        contact = collected_data.get("contact")
        if contact and isinstance(contact, str):
            result = self.validate_any(contact)
            if result.is_valid:
                normalized = {}
                if result.contact_type == ContactType.EMAIL:
                    normalized["email"] = result.normalized_value
                elif result.contact_type == ContactType.PHONE:
                    normalized["phone"] = result.normalized_value
                return True, normalized, None

        return False, None, "No valid contact information found"


# Global validator instance for use in conditions
_validator = ContactValidator()


def has_valid_contact(collected_data: Dict[str, Any]) -> bool:
    """
    Check if collected_data contains valid contact information.

    This is the main entry point for conditions to use.

    Args:
        collected_data: Data collected during conversation

    Returns:
        True if valid email or phone is present
    """
    is_valid, _, _ = _validator.extract_and_validate_from_collected_data(collected_data)
    return is_valid


def get_validated_contact(collected_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get validated and normalized contact information.

    Args:
        collected_data: Data collected during conversation

    Returns:
        Dict with normalized contact fields, or None if invalid
    """
    is_valid, normalized, _ = _validator.extract_and_validate_from_collected_data(collected_data)
    return normalized if is_valid else None


def validate_contact_string(value: str) -> ValidationResult:
    """
    Validate a contact string (email or phone).

    Args:
        value: String to validate

    Returns:
        ValidationResult with validation details
    """
    return _validator.validate_any(value)
