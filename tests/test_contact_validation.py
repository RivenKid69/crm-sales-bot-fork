"""
Tests for Contact Validation Module.

This module provides comprehensive tests for:
- ContactValidator class
- Email validation
- Phone validation (Russian formats)
- Contact info extraction and validation
- Integration with conditions (ready_for_close, has_validated_contact, etc.)

Tests ensure explicit validation logic works correctly and prevents
false positives from DataExtractor regex patterns.
"""

import pytest
from typing import Dict, Any

from src.conditions.state_machine.contact_validator import (
    ContactValidator,
    ContactType,
    ValidationResult,
    has_valid_contact,
    get_validated_contact,
    validate_contact_string,
)
from src.conditions.state_machine.context import EvaluatorContext
from src.conditions.state_machine.conditions import (
    has_contact_info,
    has_validated_contact,
    has_valid_email,
    has_valid_phone,
    ready_for_close,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def validator():
    """Create a ContactValidator instance."""
    return ContactValidator()

@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return EvaluatorContext.create_test_context()

def make_context(collected_data: Dict[str, Any]) -> EvaluatorContext:
    """Helper to create context with collected_data."""
    return EvaluatorContext.create_test_context(collected_data=collected_data)

# =============================================================================
# EMAIL VALIDATION TESTS
# =============================================================================

class TestEmailValidation:
    """Tests for email validation."""

    @pytest.mark.parametrize("email", [
        "user@example.com",
        "user.name@example.com",
        "user+tag@example.org",
        "user_name@sub.domain.co.uk",
        "user123@example.ru",
        "USER@EXAMPLE.COM",
        "test@test.io",
    ])
    def test_valid_emails(self, validator, email):
        """Test that valid email formats are accepted."""
        result = validator.validate_email(email)
        assert result.is_valid, f"Email {email} should be valid"
        assert result.contact_type == ContactType.EMAIL
        assert result.normalized_value == email.lower()

    @pytest.mark.parametrize("email", [
        "",
        "   ",
        "not-an-email",
        "missing@tld",
        "@nodomain.com",
        "nodomain@",
        "spaces in@email.com",
        "test@.com",
        "test@com.",
    ])
    def test_invalid_emails(self, validator, email):
        """Test that invalid email formats are rejected."""
        result = validator.validate_email(email)
        assert not result.is_valid, f"Email '{email}' should be invalid"
        assert result.error is not None

    def test_email_normalization(self, validator):
        """Test that emails are normalized to lowercase."""
        result = validator.validate_email("User.Name@Example.COM")
        assert result.is_valid
        assert result.normalized_value == "user.name@example.com"

    def test_email_with_whitespace(self, validator):
        """Test that whitespace around email is handled."""
        result = validator.validate_email("  user@example.com  ")
        assert result.is_valid
        assert result.normalized_value == "user@example.com"

    def test_none_email(self, validator):
        """Test that None email is rejected."""
        result = validator.validate_email(None)
        assert not result.is_valid

# =============================================================================
# PHONE VALIDATION TESTS
# =============================================================================

class TestPhoneValidation:
    """Tests for Russian phone validation."""

    @pytest.mark.parametrize("phone,normalized", [
        # +7 format
        ("+79991234567", "+79991234567"),
        ("+7 999 123-45-67", "+79991234567"),
        ("+7(999)123-45-67", "+79991234567"),
        ("+7-999-123-45-67", "+79991234567"),
        ("+7 999 123 45 67", "+79991234567"),
        # 8 format
        ("89991234567", "+79991234567"),
        ("8 999 123-45-67", "+79991234567"),
        ("8(999)123-45-67", "+79991234567"),
        ("8-999-123-45-67", "+79991234567"),
        # 10-digit local
        ("9991234567", "+79991234567"),
        ("999-123-45-67", "+79991234567"),
        ("999 123 45 67", "+79991234567"),
    ])
    def test_valid_mobile_phones(self, validator, phone, normalized):
        """Test that valid Russian mobile phone formats are accepted."""
        result = validator.validate_phone(phone)
        assert result.is_valid, f"Phone {phone} should be valid: {result.error}"
        assert result.contact_type == ContactType.PHONE
        assert result.normalized_value == normalized

    @pytest.mark.parametrize("phone", [
        # City codes (Moscow, SPb)
        ("+74951234567"),
        ("+78121234567"),
    ])
    def test_valid_city_phones(self, validator, phone):
        """Test that valid city phone codes are accepted."""
        result = validator.validate_phone(phone)
        assert result.is_valid, f"Phone {phone} should be valid: {result.error}"

    @pytest.mark.parametrize("phone", [
        # Invalid patterns that DataExtractor might match
        "1234567890",  # Sequential
        "0987654321",  # Reverse sequential
        "1111111111",  # All same digit
        "0000000000",  # All zeros
        "0101010101",  # Pattern
        # Invalid prefix
        "+71001234567",  # 100 is not a valid prefix
        "+72001234567",  # 200 is not a valid prefix
        "+75001234567",  # 500 is not a valid prefix
        # Too short/long
        "12345",
        "+7999123456789",
        # Not a phone
        "not-a-phone",
        "",
        "   ",
    ])
    def test_invalid_phones(self, validator, phone):
        """Test that invalid phone patterns are rejected."""
        result = validator.validate_phone(phone)
        assert not result.is_valid, f"Phone '{phone}' should be invalid"
        assert result.error is not None

    def test_phone_with_whitespace(self, validator):
        """Test that whitespace around phone is handled."""
        result = validator.validate_phone("  +79991234567  ")
        assert result.is_valid
        assert result.normalized_value == "+79991234567"

    def test_none_phone(self, validator):
        """Test that None phone is rejected."""
        result = validator.validate_phone(None)
        assert not result.is_valid

# =============================================================================
# CONTACT TYPE DETECTION TESTS
# =============================================================================

class TestContactTypeDetection:
    """Tests for contact type auto-detection."""

    @pytest.mark.parametrize("value,expected_type", [
        ("user@example.com", ContactType.EMAIL),
        ("+79991234567", ContactType.PHONE),
        ("89991234567", ContactType.PHONE),
        ("9991234567", ContactType.PHONE),
        ("not-contact", ContactType.UNKNOWN),
        ("", ContactType.UNKNOWN),
    ])
    def test_detect_contact_type(self, validator, value, expected_type):
        """Test contact type detection."""
        result = validator.detect_contact_type(value)
        assert result == expected_type

    def test_validate_any_email(self, validator):
        """Test validate_any correctly handles email."""
        result = validator.validate_any("user@example.com")
        assert result.is_valid
        assert result.contact_type == ContactType.EMAIL

    def test_validate_any_phone(self, validator):
        """Test validate_any correctly handles phone."""
        result = validator.validate_any("+79991234567")
        assert result.is_valid
        assert result.contact_type == ContactType.PHONE

    def test_validate_any_invalid(self, validator):
        """Test validate_any rejects invalid input."""
        result = validator.validate_any("not-a-contact")
        assert not result.is_valid
        assert result.contact_type == ContactType.UNKNOWN

# =============================================================================
# CONTACT INFO VALIDATION TESTS
# =============================================================================

class TestContactInfoValidation:
    """Tests for contact_info field validation (multiple formats)."""

    def test_string_email_format(self, validator):
        """Test contact_info as string email."""
        is_valid, normalized, error = validator.validate_contact_info("user@example.com")
        assert is_valid
        assert normalized == {"email": "user@example.com"}

    def test_string_phone_format(self, validator):
        """Test contact_info as string phone."""
        is_valid, normalized, error = validator.validate_contact_info("+79991234567")
        assert is_valid
        assert normalized == {"phone": "+79991234567"}

    def test_dict_with_email(self, validator):
        """Test contact_info as dict with email."""
        is_valid, normalized, error = validator.validate_contact_info({
            "email": "user@example.com"
        })
        assert is_valid
        assert normalized["email"] == "user@example.com"

    def test_dict_with_phone(self, validator):
        """Test contact_info as dict with phone."""
        is_valid, normalized, error = validator.validate_contact_info({
            "phone": "+79991234567"
        })
        assert is_valid
        assert normalized["phone"] == "+79991234567"

    def test_dict_with_both(self, validator):
        """Test contact_info as dict with both email and phone."""
        is_valid, normalized, error = validator.validate_contact_info({
            "email": "user@example.com",
            "phone": "+79991234567"
        })
        assert is_valid
        assert normalized["email"] == "user@example.com"
        assert normalized["phone"] == "+79991234567"

    def test_dict_with_name_only(self, validator):
        """Test contact_info as dict with name only (invalid - needs email or phone)."""
        is_valid, normalized, error = validator.validate_contact_info({
            "name": "John Doe"
        })
        assert not is_valid
        assert error is not None

    def test_dict_with_invalid_email(self, validator):
        """Test contact_info as dict with invalid email."""
        is_valid, normalized, error = validator.validate_contact_info({
            "email": "not-an-email"
        })
        assert not is_valid

    def test_dict_with_invalid_phone(self, validator):
        """Test contact_info as dict with invalid phone (sequential)."""
        is_valid, normalized, error = validator.validate_contact_info({
            "phone": "1234567890"
        })
        assert not is_valid

    def test_none_contact_info(self, validator):
        """Test None contact_info."""
        is_valid, normalized, error = validator.validate_contact_info(None)
        assert not is_valid

    def test_empty_string_contact_info(self, validator):
        """Test empty string contact_info."""
        is_valid, normalized, error = validator.validate_contact_info("")
        assert not is_valid

    def test_empty_dict_contact_info(self, validator):
        """Test empty dict contact_info."""
        is_valid, normalized, error = validator.validate_contact_info({})
        assert not is_valid

# =============================================================================
# COLLECTED_DATA EXTRACTION TESTS
# =============================================================================

class TestCollectedDataExtraction:
    """Tests for extracting contact from collected_data."""

    def test_contact_info_string_priority(self, validator):
        """Test contact_info field has priority."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({
            "contact_info": "user@example.com",
            "email": "other@example.com",  # This should be ignored
        })
        assert is_valid
        assert normalized["email"] == "user@example.com"

    def test_top_level_email_fallback(self, validator):
        """Test top-level email is used when contact_info is missing."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({
            "email": "user@example.com"
        })
        assert is_valid
        assert normalized["email"] == "user@example.com"

    def test_top_level_phone_fallback(self, validator):
        """Test top-level phone is used when email is missing."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({
            "phone": "+79991234567"
        })
        assert is_valid
        assert normalized["phone"] == "+79991234567"

    def test_legacy_contact_field(self, validator):
        """Test legacy 'contact' field is used as last resort."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({
            "contact": "user@example.com"
        })
        assert is_valid
        assert normalized["email"] == "user@example.com"

    def test_empty_collected_data(self, validator):
        """Test empty collected_data."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({})
        assert not is_valid

    def test_collected_data_with_invalid_contact(self, validator):
        """Test collected_data with invalid contact (sequential phone)."""
        is_valid, normalized, error = validator.extract_and_validate_from_collected_data({
            "contact_info": "1234567890"
        })
        assert not is_valid

# =============================================================================
# MODULE-LEVEL FUNCTION TESTS
# =============================================================================

class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_has_valid_contact_with_email(self):
        """Test has_valid_contact with valid email."""
        assert has_valid_contact({"contact_info": "user@example.com"})

    def test_has_valid_contact_with_phone(self):
        """Test has_valid_contact with valid phone."""
        assert has_valid_contact({"phone": "+79991234567"})

    def test_has_valid_contact_without_contact(self):
        """Test has_valid_contact without contact."""
        assert not has_valid_contact({})

    def test_has_valid_contact_with_invalid(self):
        """Test has_valid_contact with invalid contact."""
        assert not has_valid_contact({"contact_info": "1234567890"})

    def test_get_validated_contact_with_email(self):
        """Test get_validated_contact returns normalized email."""
        result = get_validated_contact({"email": "USER@EXAMPLE.COM"})
        assert result is not None
        assert result["email"] == "user@example.com"

    def test_get_validated_contact_without_contact(self):
        """Test get_validated_contact returns None without contact."""
        result = get_validated_contact({})
        assert result is None

    def test_validate_contact_string_email(self):
        """Test validate_contact_string with email."""
        result = validate_contact_string("user@example.com")
        assert result.is_valid
        assert result.contact_type == ContactType.EMAIL

    def test_validate_contact_string_phone(self):
        """Test validate_contact_string with phone."""
        result = validate_contact_string("+79991234567")
        assert result.is_valid
        assert result.contact_type == ContactType.PHONE

# =============================================================================
# CONDITION FUNCTION TESTS
# =============================================================================

class TestConditionFunctions:
    """Tests for condition functions using ContactValidator."""

    def test_has_contact_info_lenient(self):
        """Test has_contact_info (lenient) accepts any non-empty value."""
        # This is the backward-compatible lenient check
        ctx = make_context({"contact_info": "anything"})
        assert has_contact_info(ctx)

    def test_has_contact_info_empty(self):
        """Test has_contact_info returns False for empty."""
        ctx = make_context({})
        assert not has_contact_info(ctx)

    def test_has_validated_contact_valid_email(self):
        """Test has_validated_contact with valid email."""
        ctx = make_context({"email": "user@example.com"})
        assert has_validated_contact(ctx)

    def test_has_validated_contact_valid_phone(self):
        """Test has_validated_contact with valid phone."""
        ctx = make_context({"phone": "+79991234567"})
        assert has_validated_contact(ctx)

    def test_has_validated_contact_invalid(self):
        """Test has_validated_contact rejects invalid contact."""
        # Sequential number - should be rejected by validator
        ctx = make_context({"contact_info": "1234567890"})
        assert not has_validated_contact(ctx)

    def test_has_valid_email_positive(self):
        """Test has_valid_email with valid email."""
        ctx = make_context({"email": "user@example.com"})
        assert has_valid_email(ctx)

    def test_has_valid_email_negative(self):
        """Test has_valid_email with invalid email."""
        ctx = make_context({"email": "not-an-email"})
        assert not has_valid_email(ctx)

    def test_has_valid_email_in_contact_info(self):
        """Test has_valid_email finds email in contact_info."""
        ctx = make_context({"contact_info": "user@example.com"})
        assert has_valid_email(ctx)

    def test_has_valid_phone_positive(self):
        """Test has_valid_phone with valid phone."""
        ctx = make_context({"phone": "+79991234567"})
        assert has_valid_phone(ctx)

    def test_has_valid_phone_negative(self):
        """Test has_valid_phone with invalid phone."""
        ctx = make_context({"phone": "1234567890"})
        assert not has_valid_phone(ctx)

    def test_has_valid_phone_in_contact_info(self):
        """Test has_valid_phone finds phone in contact_info."""
        ctx = make_context({"contact_info": "+79991234567"})
        assert has_valid_phone(ctx)

# =============================================================================
# READY_FOR_CLOSE CONDITION TESTS
# =============================================================================

class TestReadyForClose:
    """Tests for ready_for_close condition (main use case)."""

    def test_ready_with_valid_email(self):
        """Test ready_for_close with valid email."""
        ctx = make_context({"email": "user@example.com"})
        assert ready_for_close(ctx)

    def test_ready_with_valid_phone(self):
        """Test ready_for_close with valid phone."""
        ctx = make_context({"phone": "+79991234567"})
        assert ready_for_close(ctx)

    def test_ready_with_valid_contact_info_email(self):
        """Test ready_for_close with valid email in contact_info."""
        ctx = make_context({"contact_info": "user@example.com"})
        assert ready_for_close(ctx)

    def test_ready_with_valid_contact_info_phone(self):
        """Test ready_for_close with valid phone in contact_info."""
        ctx = make_context({"contact_info": "+79991234567"})
        assert ready_for_close(ctx)

    def test_not_ready_without_contact(self):
        """Test ready_for_close is False without contact."""
        ctx = make_context({})
        assert not ready_for_close(ctx)

    def test_not_ready_with_invalid_sequential_phone(self):
        """Test ready_for_close rejects sequential phone numbers."""
        # This is the key fix - previously would pass with lenient check
        ctx = make_context({"contact_info": "1234567890"})
        assert not ready_for_close(ctx)

    def test_not_ready_with_invalid_repeated_phone(self):
        """Test ready_for_close rejects repeated digit phone numbers."""
        ctx = make_context({"contact_info": "1111111111"})
        assert not ready_for_close(ctx)

    def test_not_ready_with_invalid_email(self):
        """Test ready_for_close rejects invalid email."""
        ctx = make_context({"email": "not-an-email"})
        assert not ready_for_close(ctx)

    def test_not_ready_with_name_only(self):
        """Test ready_for_close rejects name without email/phone."""
        ctx = make_context({"contact_info": {"name": "John Doe"}})
        assert not ready_for_close(ctx)

    def test_ready_with_dict_contact_info(self):
        """Test ready_for_close with dict contact_info."""
        ctx = make_context({
            "contact_info": {
                "email": "user@example.com",
                "phone": "+79991234567",
                "name": "John Doe"
            }
        })
        assert ready_for_close(ctx)

# =============================================================================
# EDGE CASES AND REGRESSION TESTS
# =============================================================================

class TestEdgeCases:
    """Edge cases and regression tests."""

    def test_email_with_cyrillic_domain(self, validator):
        """Test email with cyrillic domain (punycode would be needed)."""
        # This should fail as we don't support IDN currently
        result = validator.validate_email("user@домен.рф")
        # Note: Basic regex doesn't support cyrillic, which is expected
        assert not result.is_valid

    def test_phone_with_extra_characters(self, validator):
        """Test phone with extra characters."""
        result = validator.validate_phone("+7 (999) 123-45-67 доб. 123")
        # Extension should not be part of core validation
        assert not result.is_valid

    def test_phone_formats_consistency(self, validator):
        """Test that different phone formats normalize to same value."""
        formats = [
            "+79991234567",
            "+7 999 123-45-67",
            "89991234567",
            "8 999 123 45 67",
            "9991234567",
        ]
        normalized_values = []
        for phone in formats:
            result = validator.validate_phone(phone)
            if result.is_valid:
                normalized_values.append(result.normalized_value)

        # All valid formats should normalize to the same value
        assert len(set(normalized_values)) == 1
        assert normalized_values[0] == "+79991234567"

    def test_validation_result_bool(self):
        """Test ValidationResult can be used as boolean."""
        valid = ValidationResult(is_valid=True, contact_type=ContactType.EMAIL)
        invalid = ValidationResult(is_valid=False, contact_type=ContactType.EMAIL)

        assert valid
        assert not invalid

    def test_collected_data_priority_order(self, validator):
        """Test priority order: contact_info > email > phone > contact."""
        # contact_info should win
        is_valid, normalized, _ = validator.extract_and_validate_from_collected_data({
            "contact_info": "info@example.com",
            "email": "email@example.com",
            "phone": "+79991234567",
            "contact": "contact@example.com",
        })
        assert is_valid
        assert normalized["email"] == "info@example.com"

    def test_real_world_false_positive(self, validator):
        """Test protection against real-world false positive patterns."""
        # These are patterns that DataExtractor regex might match
        # but are not valid phone numbers
        false_positives = [
            "1234567890",  # Sequential
            "2147483647",  # MAX_INT
            "1000000000",  # Round number
            "9999999999",  # All nines
        ]
        for value in false_positives:
            result = validator.validate_phone(value)
            assert not result.is_valid, f"{value} should be rejected"

# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests with DataExtractor."""

    def test_data_extractor_validates_email(self):
        """Test that DataExtractor validates email on extraction."""
        from src.classifier.extractors.data_extractor import DataExtractor

        extractor = DataExtractor()
        result = extractor.extract("Мой email: user@example.com")

        # Should extract and normalize
        assert "contact_info" in result
        assert result["contact_info"] == "user@example.com"
        assert result.get("contact_type") == "email"

    def test_data_extractor_validates_phone(self):
        """Test that DataExtractor validates phone on extraction."""
        from src.classifier.extractors.data_extractor import DataExtractor

        extractor = DataExtractor()
        result = extractor.extract("Мой телефон: +7 999 123-45-67")

        # Should extract and normalize
        assert "contact_info" in result
        assert result["contact_info"] == "+79991234567"
        assert result.get("contact_type") == "phone"

    def test_data_extractor_rejects_invalid_phone(self):
        """Test that DataExtractor rejects invalid phone patterns."""
        from src.classifier.extractors.data_extractor import DataExtractor

        extractor = DataExtractor()
        # Message with sequential number that looks like phone
        result = extractor.extract("Код товара: 1234567890")

        # Should NOT extract as contact_info (invalid phone)
        assert "contact_info" not in result or result.get("contact_info") != "1234567890"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
