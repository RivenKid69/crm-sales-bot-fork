"""
Comprehensive tests for ExtractionValidator.

Tests cover:
1. Individual field validation
2. Common LLM hallucination patterns (the bugs we're fixing)
3. Field misplacement detection and suggestions
4. Full extracted_data validation
5. Edge cases and boundary conditions

Key bug scenarios being fixed:
- "два-три человека" → current_tools (should be company_size)
- "теряем клиентов" → contact_info (should be pain_point)
- "типа это бы помогло контролировать" → contact_info (should be desired_outcome)
"""

import pytest
from src.classifier.extractors.extraction_validator import (
    ExtractionValidator,
    FieldValidationResult,
    ExtractionValidationResult,
    ValidationSeverity,
    validate_extracted_data,
    validate_field,
    is_valid_contact_info,
    is_valid_tool,
)


@pytest.fixture
def validator():
    """Create a fresh validator instance."""
    return ExtractionValidator()


class TestContactInfoValidation:
    """Tests for contact_info field validation - the most problematic field."""

    def test_valid_phone_plus7(self, validator):
        """Valid phone with +7 prefix."""
        result = validator.validate_field("contact_info", "+7 999 123-45-67")
        assert result.is_valid
        assert result.normalized_value == "+79991234567"

    def test_valid_phone_8(self, validator):
        """Valid phone with 8 prefix."""
        result = validator.validate_field("contact_info", "8 999 123 45 67")
        assert result.is_valid
        assert result.normalized_value == "+79991234567"

    def test_valid_email(self, validator):
        """Valid email address."""
        result = validator.validate_field("contact_info", "user@example.com")
        assert result.is_valid
        assert result.normalized_value == "user@example.com"

    def test_valid_email_uppercase(self, validator):
        """Email should be normalized to lowercase."""
        result = validator.validate_field("contact_info", "User@Example.COM")
        assert result.is_valid
        assert result.normalized_value == "user@example.com"

    # =========================================================================
    # BUG FIX TESTS: Pain points incorrectly stored as contact_info
    # =========================================================================

    def test_reject_pain_point_as_contact_teryaem(self, validator):
        """BUG FIX: 'теряем клиентов' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "теряем клиентов")
        assert not result.is_valid
        assert result.suggested_field == "pain_point"
        assert "pain point" in result.error.lower() or "боль" in result.error.lower()

    def test_reject_pain_point_as_contact_net_kontrolya(self, validator):
        """BUG FIX: 'нет контроля' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "нет контроля над менеджерами")
        assert not result.is_valid
        assert result.suggested_field == "pain_point"

    def test_reject_pain_point_as_contact_zabyvayut(self, validator):
        """BUG FIX: 'забывают перезвонить' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "менеджеры забывают перезвонить")
        assert not result.is_valid
        assert result.suggested_field == "pain_point"

    def test_reject_pain_point_as_contact_haos(self, validator):
        """BUG FIX: 'хаос в данных' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "у нас хаос в клиентской базе")
        assert not result.is_valid

    # =========================================================================
    # BUG FIX TESTS: Desired outcome incorrectly stored as contact_info
    # =========================================================================

    def test_reject_desired_outcome_as_contact(self, validator):
        """BUG FIX: Desired outcome text should NOT be stored as contact_info."""
        result = validator.validate_field(
            "contact_info",
            "типа это бы помогло бы контролировать процесс, уменьшить ошибки и увеличить конверсию"
        )
        assert not result.is_valid
        assert result.suggested_field == "desired_outcome"

    def test_reject_desired_outcome_hochu_kontrolirovat(self, validator):
        """BUG FIX: 'хочу контролировать' should NOT be contact_info."""
        result = validator.validate_field("contact_info", "хочу контролировать менеджеров")
        assert not result.is_valid
        assert result.suggested_field == "desired_outcome"

    def test_reject_desired_outcome_pomoglo_by(self, validator):
        """BUG FIX: 'помогло бы' text should NOT be contact_info."""
        result = validator.validate_field("contact_info", "это помогло бы нам расти")
        assert not result.is_valid
        assert result.suggested_field == "desired_outcome"

    # =========================================================================
    # BUG FIX TESTS: People count incorrectly stored as contact_info
    # =========================================================================

    def test_reject_people_count_as_contact(self, validator):
        """BUG FIX: 'два-три человека' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "два-три человека")
        assert not result.is_valid
        assert result.suggested_field == "company_size"

    def test_reject_people_count_5_chelovek(self, validator):
        """BUG FIX: '5 человек' should NOT be stored as contact_info."""
        result = validator.validate_field("contact_info", "5 человек работает")
        assert not result.is_valid
        assert result.suggested_field == "company_size"

    # =========================================================================
    # Edge cases
    # =========================================================================

    def test_reject_empty_string(self, validator):
        """Empty string is not a valid contact."""
        result = validator.validate_field("contact_info", "")
        assert not result.is_valid

    def test_reject_random_text(self, validator):
        """Random text without phone/email is not a contact."""
        result = validator.validate_field("contact_info", "просто какой-то текст")
        assert not result.is_valid

    def test_reject_agreement(self, validator):
        """Agreement text is not a contact."""
        result = validator.validate_field("contact_info", "да, интересно")
        assert not result.is_valid


class TestCurrentToolsValidation:
    """Tests for current_tools field validation."""

    def test_valid_excel(self, validator):
        """Excel is a valid tool."""
        result = validator.validate_field("current_tools", "Excel")
        assert result.is_valid
        assert result.normalized_value == "Excel"

    def test_valid_excel_lowercase(self, validator):
        """Excel in lowercase should be normalized."""
        result = validator.validate_field("current_tools", "в excel ведём")
        assert result.is_valid
        assert result.normalized_value == "Excel"

    def test_valid_1c(self, validator):
        """1C is a valid tool."""
        result = validator.validate_field("current_tools", "1С")
        assert result.is_valid

    def test_valid_amocrm(self, validator):
        """AmoCRM is a valid tool."""
        result = validator.validate_field("current_tools", "амо")
        assert result.is_valid
        assert result.normalized_value == "AmoCRM"

    def test_valid_manually(self, validator):
        """'вручную' is a valid tool."""
        result = validator.validate_field("current_tools", "вручную")
        assert result.is_valid

    def test_valid_in_heads(self, validator):
        """'в головах' is a valid tool."""
        result = validator.validate_field("current_tools", "всё в головах держим")
        assert result.is_valid
        assert result.normalized_value == "в головах"

    # =========================================================================
    # BUG FIX TESTS: People count incorrectly stored as current_tools
    # =========================================================================

    def test_reject_people_count_dva_tri_cheloveka(self, validator):
        """BUG FIX: 'два-три человека' should NOT be stored as current_tools."""
        result = validator.validate_field("current_tools", "два-три человека")
        assert not result.is_valid
        assert result.suggested_field == "company_size"
        assert "people" in result.error.lower() or "люд" in result.error.lower()

    def test_reject_people_count_5_sotrudnikov(self, validator):
        """BUG FIX: '5 сотрудников' should NOT be stored as current_tools."""
        result = validator.validate_field("current_tools", "5 сотрудников")
        assert not result.is_valid
        assert result.suggested_field == "company_size"

    def test_reject_people_count_nas_10(self, validator):
        """BUG FIX: 'нас 10' should NOT be stored as current_tools."""
        result = validator.validate_field("current_tools", "нас 10 человек")
        assert not result.is_valid
        assert result.suggested_field == "company_size"

    def test_reject_people_count_komanda(self, validator):
        """BUG FIX: 'команда из 15 менеджеров' should NOT be current_tools."""
        result = validator.validate_field("current_tools", "команда из 15 менеджеров")
        assert not result.is_valid
        assert result.suggested_field == "company_size"

    # =========================================================================
    # BUG FIX TESTS: Pain points incorrectly stored as current_tools
    # =========================================================================

    def test_reject_pain_point_as_tool(self, validator):
        """BUG FIX: Pain points should NOT be stored as current_tools."""
        result = validator.validate_field(
            "current_tools",
            "теряем клиентов из-за забывчивости менеджеров"
        )
        assert not result.is_valid
        assert result.suggested_field == "pain_point"


class TestCompanySizeValidation:
    """Tests for company_size field validation."""

    def test_valid_integer(self, validator):
        """Integer is valid for company_size."""
        result = validator.validate_field("company_size", 5)
        assert result.is_valid
        assert result.normalized_value == 5

    def test_valid_string_number(self, validator):
        """String number should be converted to int."""
        result = validator.validate_field("company_size", "10")
        assert result.is_valid
        assert result.normalized_value == 10

    def test_valid_with_text(self, validator):
        """Should extract number from '5 человек'."""
        result = validator.validate_field("company_size", "5 человек")
        assert result.is_valid
        assert result.normalized_value == 5

    def test_reject_zero(self, validator):
        """Zero is not valid for company_size."""
        result = validator.validate_field("company_size", 0)
        assert not result.is_valid

    def test_reject_negative(self, validator):
        """Negative numbers are not valid."""
        result = validator.validate_field("company_size", -5)
        assert not result.is_valid

    def test_reject_too_large(self, validator):
        """Numbers over 10000 should be rejected."""
        result = validator.validate_field("company_size", 50000)
        assert not result.is_valid

    def test_reject_text_only(self, validator):
        """Text without numbers should be rejected."""
        result = validator.validate_field("company_size", "много")
        assert not result.is_valid


class TestPainPointValidation:
    """Tests for pain_point field validation."""

    def test_valid_pain_point(self, validator):
        """Valid pain point text."""
        result = validator.validate_field("pain_point", "теряем клиентов")
        assert result.is_valid

    def test_valid_pain_point_detailed(self, validator):
        """Detailed pain point is valid."""
        result = validator.validate_field(
            "pain_point",
            "менеджеры забывают перезванивать и мы теряем сделки"
        )
        assert result.is_valid

    def test_reject_contact_as_pain(self, validator):
        """Contact info should not be stored as pain_point."""
        result = validator.validate_field("pain_point", "+7 999 123 45 67")
        assert not result.is_valid
        assert result.suggested_field == "contact_info"

    def test_reject_tool_as_pain(self, validator):
        """Tool name alone should not be a pain_point."""
        result = validator.validate_field("pain_point", "Excel")
        assert not result.is_valid
        assert result.suggested_field == "current_tools"

    def test_reject_too_short(self, validator):
        """Pain point too short should be rejected."""
        result = validator.validate_field("pain_point", "да")
        assert not result.is_valid


class TestPainCategoryValidation:
    """Tests for pain_category field validation."""

    def test_valid_losing_clients(self, validator):
        """'losing_clients' is a valid category."""
        result = validator.validate_field("pain_category", "losing_clients")
        assert result.is_valid

    def test_valid_no_control(self, validator):
        """'no_control' is a valid category."""
        result = validator.validate_field("pain_category", "no_control")
        assert result.is_valid

    def test_valid_manual_work(self, validator):
        """'manual_work' is a valid category."""
        result = validator.validate_field("pain_category", "manual_work")
        assert result.is_valid

    def test_reject_invalid_category(self, validator):
        """Invalid category should be rejected."""
        result = validator.validate_field("pain_category", "unknown_category")
        assert not result.is_valid


class TestDesiredOutcomeValidation:
    """Tests for desired_outcome field validation."""

    def test_valid_outcome(self, validator):
        """Valid desired outcome."""
        result = validator.validate_field("desired_outcome", "хочу контролировать менеджеров")
        assert result.is_valid

    def test_valid_outcome_automation(self, validator):
        """Automation outcome is valid."""
        result = validator.validate_field("desired_outcome", "автоматизировать рутину")
        assert result.is_valid

    def test_reject_contact_as_outcome(self, validator):
        """Contact should not be stored as desired_outcome."""
        result = validator.validate_field("desired_outcome", "+7 999 123-45-67")
        assert not result.is_valid
        assert result.suggested_field == "contact_info"

    def test_reject_too_short(self, validator):
        """Too short outcome should be rejected."""
        result = validator.validate_field("desired_outcome", "да")
        assert not result.is_valid


class TestValueAcknowledgedValidation:
    """Tests for value_acknowledged field validation."""

    def test_valid_true(self, validator):
        """Boolean True is valid."""
        result = validator.validate_field("value_acknowledged", True)
        assert result.is_valid
        assert result.normalized_value is True

    def test_valid_false(self, validator):
        """Boolean False is valid."""
        result = validator.validate_field("value_acknowledged", False)
        assert result.is_valid
        assert result.normalized_value is False

    def test_string_da(self, validator):
        """String 'да' should be converted to True."""
        result = validator.validate_field("value_acknowledged", "да")
        assert result.is_valid
        assert result.normalized_value is True

    def test_string_net(self, validator):
        """String 'нет' should be converted to False."""
        result = validator.validate_field("value_acknowledged", "нет")
        assert result.is_valid
        assert result.normalized_value is False

    def test_reject_invalid_string(self, validator):
        """Invalid string should be rejected."""
        result = validator.validate_field("value_acknowledged", "может быть")
        assert not result.is_valid


class TestFullExtractedDataValidation:
    """Tests for validating complete extracted_data dictionaries."""

    def test_valid_complete_data(self, validator):
        """Complete valid extracted_data should pass."""
        extracted = {
            "company_size": 10,
            "current_tools": "Excel",
            "pain_point": "теряем клиентов",
            "pain_category": "losing_clients",
        }
        result = validator.validate_extracted_data(extracted)
        assert result.is_valid
        assert len(result.removed_fields) == 0
        assert result.validated_data == extracted

    def test_empty_data(self, validator):
        """Empty extracted_data should be valid."""
        result = validator.validate_extracted_data({})
        assert result.is_valid
        assert result.validated_data == {}

    def test_removes_invalid_contact(self, validator):
        """BUG FIX: Invalid contact_info should be removed."""
        extracted = {
            "company_size": 5,
            "contact_info": "теряем клиентов",  # Invalid!
        }
        result = validator.validate_extracted_data(extracted)
        assert "contact_info" in result.removed_fields
        assert "contact_info" not in result.validated_data
        assert result.validated_data["company_size"] == 5
        assert result.corrected_fields.get("contact_info") == "pain_point"

    def test_removes_invalid_current_tools(self, validator):
        """BUG FIX: People count in current_tools should be removed."""
        extracted = {
            "current_tools": "два-три человека",  # Invalid!
            "pain_point": "нет контроля",
        }
        result = validator.validate_extracted_data(extracted)
        assert "current_tools" in result.removed_fields
        assert "current_tools" not in result.validated_data
        assert result.validated_data["pain_point"] == "нет контроля"
        assert result.corrected_fields.get("current_tools") == "company_size"

    def test_normalizes_valid_data(self, validator):
        """Valid data should be normalized."""
        extracted = {
            "contact_info": "+7 999 123-45-67",
            "current_tools": "в эксел всё ведём",
        }
        result = validator.validate_extracted_data(extracted)
        assert result.is_valid
        assert result.validated_data["contact_info"] == "+79991234567"
        assert result.validated_data["current_tools"] == "Excel"


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_validate_extracted_data_function(self):
        """Test the module-level validate_extracted_data function."""
        result = validate_extracted_data({"company_size": 5})
        assert result.is_valid

    def test_validate_field_function(self):
        """Test the module-level validate_field function."""
        result = validate_field("company_size", 5)
        assert result.is_valid

    def test_is_valid_contact_info_valid(self):
        """Test is_valid_contact_info with valid phone."""
        assert is_valid_contact_info("+7 999 123 45 67")

    def test_is_valid_contact_info_invalid(self):
        """Test is_valid_contact_info with pain point."""
        assert not is_valid_contact_info("теряем клиентов")

    def test_is_valid_tool_valid(self):
        """Test is_valid_tool with valid tool."""
        assert is_valid_tool("Excel")

    def test_is_valid_tool_invalid(self):
        """Test is_valid_tool with people count."""
        assert not is_valid_tool("два-три человека")


class TestRealWorldBugScenarios:
    """
    Tests for the exact bug scenarios from the user report.

    These are the critical bugs we're fixing:
    1. Line 2530-2531: "типа это бы помогло бы контролировать процесс" → contact_info
    2. Line 2706-2709: "два-три человека" → current_tools
    3. Line 2878: "теряем клиентов" → contact_info
    """

    def test_bug_2530_2531_desired_outcome_as_contact(self, validator):
        """
        BUG: Line 2530-2531 - текст вопроса клиента записан как контакт

        "contact_info": "типа это бы помогло бы контролировать процесс,
                        уменьшить ошибки и увеличить конверсию"
        """
        extracted = {
            "contact_info": "типа это бы помогло бы контролировать процесс, уменьшить ошибки и увеличить конверсию"
        }
        result = validator.validate_extracted_data(extracted)

        assert "contact_info" in result.removed_fields
        assert result.corrected_fields.get("contact_info") == "desired_outcome"
        assert "contact_info" not in result.validated_data

    def test_bug_2706_2709_people_count_as_tools(self, validator):
        """
        BUG: Line 2706-2709 - количество людей записано как инструменты

        "current_tools": "два-три человека"
        """
        extracted = {
            "current_tools": "два-три человека"
        }
        result = validator.validate_extracted_data(extracted)

        assert "current_tools" in result.removed_fields
        assert result.corrected_fields.get("current_tools") == "company_size"
        assert "current_tools" not in result.validated_data

    def test_bug_2878_pain_as_contact(self, validator):
        """
        BUG: Line 2878 - фраза о потере клиентов записана как контакт

        "contact_info": "теряем клиентов"
        """
        extracted = {
            "contact_info": "теряем клиентов"
        }
        result = validator.validate_extracted_data(extracted)

        assert "contact_info" in result.removed_fields
        assert result.corrected_fields.get("contact_info") == "pain_point"
        assert "contact_info" not in result.validated_data

    def test_combined_bug_scenario(self, validator):
        """Test multiple bugs in one extracted_data dict."""
        extracted = {
            "contact_info": "теряем клиентов",  # BUG: should be pain_point
            "current_tools": "два-три человека",  # BUG: should be company_size
            "company_size": 5,  # Valid
        }
        result = validator.validate_extracted_data(extracted)

        # Both invalid fields should be removed
        assert "contact_info" in result.removed_fields
        assert "current_tools" in result.removed_fields

        # Only valid data should remain
        assert result.validated_data == {"company_size": 5}

        # Corrections should be suggested
        assert result.corrected_fields["contact_info"] == "pain_point"
        assert result.corrected_fields["current_tools"] == "company_size"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_none_value(self, validator):
        """None values should be handled gracefully."""
        extracted = {"company_size": None}
        result = validator.validate_extracted_data(extracted)
        # None values are skipped in validation
        assert result.is_valid

    def test_unicode_in_contact(self, validator):
        """Unicode text should not be valid contact."""
        result = validator.validate_field("contact_info", "Привет мир!")
        assert not result.is_valid

    def test_mixed_language_pain(self, validator):
        """Mixed language pain point should be valid."""
        result = validator.validate_field("pain_point", "теряем clients постоянно")
        assert result.is_valid

    def test_very_long_text_as_contact(self, validator):
        """Very long text should not be valid contact."""
        long_text = "это очень длинный текст который точно не является контактом " * 10
        result = validator.validate_field("contact_info", long_text)
        assert not result.is_valid

    def test_phone_with_extension(self, validator):
        """Phone with extension should be handled."""
        result = validator.validate_field("contact_info", "+7 999 123 45 67 доб. 123")
        # This should fail as it's not a standard format
        # But the core phone should be extractable in future versions
        assert not result.is_valid  # Current behavior

    def test_unknown_field_passthrough(self, validator):
        """Unknown fields should pass through with warning."""
        result = validator.validate_field("unknown_field", "some value")
        assert result.is_valid
        assert result.normalized_value == "some value"
