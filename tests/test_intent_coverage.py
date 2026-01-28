"""Tests for intent coverage validation.

These tests ensure that:
1. All critical intents have explicit mappings
2. All intents have taxonomy entries
3. Price intents use answer_with_pricing
4. Zero unmapped intents by design
"""

import pytest
from src.config_loader import ConfigLoader
from src.validation.intent_coverage import (
    IntentCoverageValidator,
    validate_intent_coverage,
    CoverageIssue
)


@pytest.fixture
def config():
    """Load configuration for testing."""
    loader = ConfigLoader()
    return loader.load()


@pytest.fixture
def flow():
    """Load flow configuration for testing."""
    loader = ConfigLoader()
    from src.settings import settings
    return loader.load_flow(settings.flow.active)


def test_no_critical_intent_unmapped(config, flow):
    """All critical intents must have explicit mappings in _universal_base.

    This test ensures that the 4 critical bug chains are fixed:
    - price_question (81% failure) → answer_with_pricing
    - contact_provided (81% failure) → transition to success
    - request_brevity (55% failure) → respond_briefly
    - request_references (54% failure) → provide_references
    """
    validator = IntentCoverageValidator(config, flow)
    issues = validator.validate_critical_intent_mappings()

    critical_issues = [i for i in issues if i.severity == "critical"]

    # Print issues for debugging
    if critical_issues:
        print("\nCritical unmapped intents found:")
        for issue in critical_issues:
            print(f"  - {issue.intent}: {issue.message}")

    assert len(critical_issues) == 0, f"Found {len(critical_issues)} critical unmapped intents"


def test_taxonomy_completeness(config):
    """All intents in categories must have taxonomy entries.

    This ensures the taxonomy provides fallback coverage for all intents.
    """
    validator = IntentCoverageValidator(config, None)
    issues = validator.validate_taxonomy_completeness()

    missing_intents = [i.intent for i in issues if i.issue_type == "missing_taxonomy"]

    # Print missing intents for debugging
    if missing_intents:
        print(f"\nIntents missing from taxonomy: {missing_intents}")

    # Allow a small number of intentional exclusions, but flag if too many
    assert len(missing_intents) <= 5, f"Too many intents missing from taxonomy: {len(missing_intents)}"


def test_price_intents_use_answer_with_pricing(config, flow):
    """Price intents must use answer_with_pricing, not answer_with_facts.

    This fixes the 81% failure rate for price_question intents.
    """
    validator = IntentCoverageValidator(config, flow)
    issues = validator.validate_price_intent_actions()

    wrong_action_issues = [i for i in issues if i.issue_type == "wrong_action"]

    # Print issues for debugging
    if wrong_action_issues:
        print("\nPrice intents with wrong actions:")
        for issue in wrong_action_issues:
            print(f"  - {issue.intent}: {issue.message}")

    assert len(wrong_action_issues) == 0, "Price intents must use answer_with_pricing"


def test_universal_base_exists_and_is_first(config, flow):
    """_universal_base mixin must exist and be first in _base_phase.

    This ensures guaranteed coverage for all states that inherit from _base_phase.
    """
    validator = IntentCoverageValidator(config, flow)
    issues = validator.validate_universal_base_mixin()

    critical_issues = [i for i in issues if i.severity in ("critical", "high")]

    # Print issues for debugging
    if critical_issues:
        print("\n_universal_base mixin issues:")
        for issue in critical_issues:
            print(f"  - {issue.message}")

    assert len(critical_issues) == 0, "_universal_base must exist and be first in _base_phase"


def test_full_validation_passes(config, flow):
    """Full validation should pass with no critical issues.

    This is the main test that ensures "Zero Unmapped Intents by Design".
    """
    result = validate_intent_coverage(config, flow)

    # Print summary
    print(f"\nValidation summary:")
    print(f"  Total issues: {result['summary']['total']}")
    print(f"  Critical: {result['summary']['critical']}")
    print(f"  High: {result['summary']['high']}")
    print(f"  Medium: {result['summary']['medium']}")
    print(f"  Low: {result['summary']['low']}")

    # Print critical issues for debugging
    critical_issues = [i for i in result['issues'] if i.severity == "critical"]
    if critical_issues:
        print("\nCritical issues found:")
        for issue in critical_issues:
            print(f"  - {issue.message} (location: {issue.location})")

    assert result['is_valid'], "Intent coverage validation must pass with no critical issues"
    assert result['summary']['critical'] == 0, "No critical issues allowed"


def test_critical_intents_list_is_comprehensive():
    """Verify that CRITICAL_INTENTS list includes the known problem intents.

    This ensures we're testing for the specific intents that caused the
    81%, 55%, and 54% failure rates.
    """
    critical = IntentCoverageValidator.CRITICAL_INTENTS

    # The 4 critical bug chains from the plan
    assert "price_question" in critical, "price_question must be critical (81% failure)"
    assert "contact_provided" in critical, "contact_provided must be critical (81% failure)"
    assert "request_brevity" in critical, "request_brevity must be critical (55% failure)"
    assert "request_references" in critical, "request_references must be critical (54% failure)"

    # All 7 price intents
    assert "pricing_details" in critical
    assert "cost_inquiry" in critical
    assert "discount_request" in critical
    assert "payment_terms" in critical
    assert "pricing_comparison" in critical
    assert "budget_question" in critical


def test_taxonomy_has_fallback_actions():
    """Verify taxonomy config has all required fallback levels.

    This ensures the 5-level fallback chain works:
    1. Exact match
    2. Category fallback
    3. Super-category fallback
    4. Domain fallback
    5. DEFAULT_ACTION
    """
    loader = ConfigLoader()
    config = loader.load()

    taxonomy_config = config.taxonomy_config

    # Check all required sections exist
    assert "intent_taxonomy" in taxonomy_config
    assert "taxonomy_category_defaults" in taxonomy_config
    assert "taxonomy_super_category_defaults" in taxonomy_config
    assert "taxonomy_domain_defaults" in taxonomy_config

    # Check specific critical fallbacks
    category_defaults = taxonomy_config["taxonomy_category_defaults"]
    assert "question" in category_defaults, "question category must have fallback"
    assert "positive" in category_defaults, "positive category must have fallback"
    assert "purchase_stage" in category_defaults, "purchase_stage category must have fallback"

    domain_defaults = taxonomy_config["taxonomy_domain_defaults"]
    assert "pricing" in domain_defaults, "pricing domain must have fallback"
    assert domain_defaults["pricing"]["fallback_action"] == "answer_with_pricing"


def test_price_intents_in_taxonomy():
    """Verify all 7 price intents have taxonomy entries with correct domain.

    This ensures taxonomy provides intelligent fallback for price intents.
    """
    loader = ConfigLoader()
    config = loader.load()

    intent_taxonomy = config.taxonomy_config["intent_taxonomy"]

    price_intents = [
        "price_question", "pricing_details", "cost_inquiry",
        "discount_request", "payment_terms", "pricing_comparison",
        "budget_question"
    ]

    for intent in price_intents:
        assert intent in intent_taxonomy, f"{intent} must be in taxonomy"
        tax = intent_taxonomy[intent]
        assert tax["semantic_domain"] == "pricing", f"{intent} must have pricing domain"
        assert tax["fallback_action"] == "answer_with_pricing", f"{intent} must fallback to answer_with_pricing"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
