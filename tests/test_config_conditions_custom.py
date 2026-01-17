"""
Tests for conditions/custom.yaml configuration.

Tests all custom conditions, their expressions, and aliases.
"""

import pytest
from pathlib import Path
import yaml


@pytest.fixture(scope="module")
def custom_conditions_config():
    """Load custom conditions configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "conditions" / "custom.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestCustomConditionsStructure:
    """Tests for custom conditions structure."""

    def test_has_conditions_section(self, custom_conditions_config):
        """Config should have conditions section."""
        assert "conditions" in custom_conditions_config

    def test_has_aliases_section(self, custom_conditions_config):
        """Config should have aliases section."""
        assert "aliases" in custom_conditions_config

    def test_conditions_not_empty(self, custom_conditions_config):
        """Conditions section should not be empty."""
        assert len(custom_conditions_config["conditions"]) > 0

    def test_aliases_not_empty(self, custom_conditions_config):
        """Aliases section should not be empty."""
        assert len(custom_conditions_config["aliases"]) > 0


class TestReadyForDemoCondition:
    """Tests for ready_for_demo condition."""

    def test_ready_for_demo_exists(self, custom_conditions_config):
        """ready_for_demo condition should exist."""
        assert "ready_for_demo" in custom_conditions_config["conditions"]

    def test_ready_for_demo_has_description(self, custom_conditions_config):
        """ready_for_demo should have description."""
        cond = custom_conditions_config["conditions"]["ready_for_demo"]
        assert "description" in cond
        assert "демо" in cond["description"].lower()

    def test_ready_for_demo_has_expression(self, custom_conditions_config):
        """ready_for_demo should have expression."""
        cond = custom_conditions_config["conditions"]["ready_for_demo"]
        assert "expression" in cond

    def test_ready_for_demo_uses_and(self, custom_conditions_config):
        """ready_for_demo should use AND logic."""
        cond = custom_conditions_config["conditions"]["ready_for_demo"]
        assert "and" in cond["expression"]

    def test_ready_for_demo_requires_contact_info(self, custom_conditions_config):
        """ready_for_demo should require has_contact_info."""
        cond = custom_conditions_config["conditions"]["ready_for_demo"]
        assert "has_contact_info" in cond["expression"]["and"]

    def test_ready_for_demo_checks_not_frustrated(self, custom_conditions_config):
        """ready_for_demo should check not frustrated."""
        cond = custom_conditions_config["conditions"]["ready_for_demo"]
        and_conditions = cond["expression"]["and"]
        has_not_frustrated = any(
            isinstance(c, dict) and c.get("not") == "client_frustrated"
            for c in and_conditions
        )
        assert has_not_frustrated


class TestCanAccelerateFlowCondition:
    """Tests for can_accelerate_flow condition."""

    def test_can_accelerate_flow_exists(self, custom_conditions_config):
        """can_accelerate_flow condition should exist."""
        assert "can_accelerate_flow" in custom_conditions_config["conditions"]

    def test_can_accelerate_flow_has_description(self, custom_conditions_config):
        """can_accelerate_flow should have description."""
        cond = custom_conditions_config["conditions"]["can_accelerate_flow"]
        assert "description" in cond
        assert "SPIN" in cond["description"] or "ускорить" in cond["description"]

    def test_can_accelerate_flow_requires_momentum(self, custom_conditions_config):
        """can_accelerate_flow should check momentum."""
        cond = custom_conditions_config["conditions"]["can_accelerate_flow"]
        assert "momentum_positive" in cond["expression"]["and"]

    def test_can_accelerate_flow_requires_engagement(self, custom_conditions_config):
        """can_accelerate_flow should check engagement."""
        cond = custom_conditions_config["conditions"]["can_accelerate_flow"]
        assert "engagement_high" in cond["expression"]["and"]


class TestStuckAndFrustratedCondition:
    """Tests for stuck_and_frustrated condition."""

    def test_stuck_and_frustrated_exists(self, custom_conditions_config):
        """stuck_and_frustrated condition should exist."""
        assert "stuck_and_frustrated" in custom_conditions_config["conditions"]

    def test_stuck_and_frustrated_requires_stuck(self, custom_conditions_config):
        """stuck_and_frustrated should require client_stuck."""
        cond = custom_conditions_config["conditions"]["stuck_and_frustrated"]
        assert "client_stuck" in cond["expression"]["and"]

    def test_stuck_and_frustrated_uses_or(self, custom_conditions_config):
        """stuck_and_frustrated should have OR sub-condition."""
        cond = custom_conditions_config["conditions"]["stuck_and_frustrated"]
        has_or = any(
            isinstance(c, dict) and "or" in c
            for c in cond["expression"]["and"]
        )
        assert has_or


class TestSoftCtaCondition:
    """Tests for soft_cta_appropriate condition."""

    def test_soft_cta_appropriate_exists(self, custom_conditions_config):
        """soft_cta_appropriate condition should exist."""
        assert "soft_cta_appropriate" in custom_conditions_config["conditions"]

    def test_soft_cta_requires_breakthrough(self, custom_conditions_config):
        """soft_cta_appropriate should require breakthrough."""
        cond = custom_conditions_config["conditions"]["soft_cta_appropriate"]
        assert "has_breakthrough" in cond["expression"]["and"]

    def test_soft_cta_not_in_protected_state(self, custom_conditions_config):
        """soft_cta_appropriate should check not in protected state."""
        cond = custom_conditions_config["conditions"]["soft_cta_appropriate"]
        and_conditions = cond["expression"]["and"]
        has_not_protected = any(
            isinstance(c, dict) and c.get("not") == "in_protected_state"
            for c in and_conditions
        )
        assert has_not_protected


class TestRoiOpportunityCondition:
    """Tests for roi_opportunity condition."""

    def test_roi_opportunity_exists(self, custom_conditions_config):
        """roi_opportunity condition should exist."""
        assert "roi_opportunity" in custom_conditions_config["conditions"]

    def test_roi_opportunity_requires_pain_point(self, custom_conditions_config):
        """roi_opportunity should require pain point."""
        cond = custom_conditions_config["conditions"]["roi_opportunity"]
        assert "has_pain_point" in cond["expression"]["and"]

    def test_roi_opportunity_checks_data(self, custom_conditions_config):
        """roi_opportunity should check for company size or financial impact."""
        cond = custom_conditions_config["conditions"]["roi_opportunity"]
        has_or = any(
            isinstance(c, dict) and "or" in c
            for c in cond["expression"]["and"]
        )
        assert has_or


class TestRepairConditions:
    """Tests for repair conditions."""

    def test_needs_repair_exists(self, custom_conditions_config):
        """needs_repair condition should exist."""
        assert "needs_repair" in custom_conditions_config["conditions"]

    def test_needs_repair_uses_or(self, custom_conditions_config):
        """needs_repair should use OR logic."""
        cond = custom_conditions_config["conditions"]["needs_repair"]
        assert "or" in cond["expression"]

    def test_needs_repair_checks_stuck(self, custom_conditions_config):
        """needs_repair should check client_stuck."""
        cond = custom_conditions_config["conditions"]["needs_repair"]
        assert "client_stuck" in cond["expression"]["or"]

    def test_needs_severe_repair_exists(self, custom_conditions_config):
        """needs_severe_repair condition should exist."""
        assert "needs_severe_repair" in custom_conditions_config["conditions"]

    def test_needs_severe_repair_references_needs_repair(self, custom_conditions_config):
        """needs_severe_repair should reference needs_repair."""
        cond = custom_conditions_config["conditions"]["needs_severe_repair"]
        assert "needs_repair" in cond["expression"]["and"]


class TestObjectionConditions:
    """Tests for objection conditions."""

    def test_repeated_same_objection_exists(self, custom_conditions_config):
        """repeated_same_objection condition should exist."""
        assert "repeated_same_objection" in custom_conditions_config["conditions"]

    def test_repeated_same_objection_checks_objection(self, custom_conditions_config):
        """repeated_same_objection should check has_objection."""
        cond = custom_conditions_config["conditions"]["repeated_same_objection"]
        assert "has_objection" in cond["expression"]["and"]

    def test_repeated_same_objection_checks_repeated(self, custom_conditions_config):
        """repeated_same_objection should check objection_repeated."""
        cond = custom_conditions_config["conditions"]["repeated_same_objection"]
        assert "objection_repeated" in cond["expression"]["and"]

    def test_objection_needs_escalation_exists(self, custom_conditions_config):
        """objection_needs_escalation condition should exist."""
        assert "objection_needs_escalation" in custom_conditions_config["conditions"]

    def test_objection_needs_escalation_references_custom(self, custom_conditions_config):
        """objection_needs_escalation should reference custom condition."""
        cond = custom_conditions_config["conditions"]["objection_needs_escalation"]
        has_custom_ref = any(
            isinstance(c, str) and c.startswith("custom:")
            for c in cond["expression"]["and"]
        )
        assert has_custom_ref


class TestEngagementConditions:
    """Tests for engagement conditions."""

    def test_high_engagement_exists(self, custom_conditions_config):
        """high_engagement condition should exist."""
        assert "high_engagement" in custom_conditions_config["conditions"]

    def test_high_engagement_checks_engagement_high(self, custom_conditions_config):
        """high_engagement should check engagement_high."""
        cond = custom_conditions_config["conditions"]["high_engagement"]
        assert "engagement_high" in cond["expression"]["and"]

    def test_low_engagement_exists(self, custom_conditions_config):
        """low_engagement condition should exist."""
        assert "low_engagement" in custom_conditions_config["conditions"]

    def test_low_engagement_uses_or(self, custom_conditions_config):
        """low_engagement should use OR logic."""
        cond = custom_conditions_config["conditions"]["low_engagement"]
        assert "or" in cond["expression"]


class TestLeadTemperatureConditions:
    """Tests for lead temperature conditions."""

    def test_lead_is_hot_exists(self, custom_conditions_config):
        """lead_is_hot condition should exist."""
        assert "lead_is_hot" in custom_conditions_config["conditions"]

    def test_lead_is_hot_uses_or(self, custom_conditions_config):
        """lead_is_hot should use OR logic."""
        cond = custom_conditions_config["conditions"]["lead_is_hot"]
        assert "or" in cond["expression"]

    def test_lead_is_hot_checks_temperatures(self, custom_conditions_config):
        """lead_is_hot should check hot and very_hot."""
        cond = custom_conditions_config["conditions"]["lead_is_hot"]
        assert "lead_temperature_hot" in cond["expression"]["or"]
        assert "lead_temperature_very_hot" in cond["expression"]["or"]

    def test_lead_is_cold_exists(self, custom_conditions_config):
        """lead_is_cold condition should exist."""
        assert "lead_is_cold" in custom_conditions_config["conditions"]

    def test_lead_is_cold_uses_and(self, custom_conditions_config):
        """lead_is_cold should use AND logic."""
        cond = custom_conditions_config["conditions"]["lead_is_cold"]
        assert "and" in cond["expression"]


class TestConditionAliases:
    """Tests for condition aliases."""

    def test_frustrated_alias_exists(self, custom_conditions_config):
        """frustrated alias should exist."""
        assert "frustrated" in custom_conditions_config["aliases"]

    def test_frustrated_alias_value(self, custom_conditions_config):
        """frustrated alias should map to client_frustrated."""
        assert custom_conditions_config["aliases"]["frustrated"] == "client_frustrated"

    def test_stuck_alias_exists(self, custom_conditions_config):
        """stuck alias should exist."""
        assert "stuck" in custom_conditions_config["aliases"]

    def test_stuck_alias_value(self, custom_conditions_config):
        """stuck alias should map to client_stuck."""
        assert custom_conditions_config["aliases"]["stuck"] == "client_stuck"

    def test_hot_lead_alias_exists(self, custom_conditions_config):
        """hot_lead alias should exist."""
        assert "hot_lead" in custom_conditions_config["aliases"]

    def test_hot_lead_alias_references_custom(self, custom_conditions_config):
        """hot_lead alias should reference custom condition."""
        assert custom_conditions_config["aliases"]["hot_lead"] == "custom:lead_is_hot"

    def test_cold_lead_alias_exists(self, custom_conditions_config):
        """cold_lead alias should exist."""
        assert "cold_lead" in custom_conditions_config["aliases"]

    def test_cold_lead_alias_references_custom(self, custom_conditions_config):
        """cold_lead alias should reference custom condition."""
        assert custom_conditions_config["aliases"]["cold_lead"] == "custom:lead_is_cold"

    def test_ready_alias_exists(self, custom_conditions_config):
        """ready alias should exist."""
        assert "ready" in custom_conditions_config["aliases"]

    def test_ready_alias_references_custom(self, custom_conditions_config):
        """ready alias should reference custom:ready_for_demo."""
        assert custom_conditions_config["aliases"]["ready"] == "custom:ready_for_demo"


class TestConditionExpressionValidity:
    """Tests for condition expression validity."""

    def test_all_conditions_have_description(self, custom_conditions_config):
        """All conditions should have descriptions."""
        for name, cond in custom_conditions_config["conditions"].items():
            assert "description" in cond, f"{name} missing description"

    def test_all_conditions_have_expression(self, custom_conditions_config):
        """All conditions should have expressions."""
        for name, cond in custom_conditions_config["conditions"].items():
            assert "expression" in cond, f"{name} missing expression"

    def test_expressions_have_valid_operators(self, custom_conditions_config):
        """Expressions should use valid operators (and/or/not)."""
        valid_operators = {"and", "or", "not"}
        for name, cond in custom_conditions_config["conditions"].items():
            expr = cond["expression"]
            if isinstance(expr, dict):
                for key in expr.keys():
                    assert key in valid_operators, f"{name} has invalid operator: {key}"

    def test_condition_names_are_snake_case(self, custom_conditions_config):
        """Condition names should be snake_case."""
        import re
        for name in custom_conditions_config["conditions"].keys():
            assert re.match(r'^[a-z][a-z0-9_]*$', name), f"Invalid condition name: {name}"

    def test_alias_names_are_snake_case(self, custom_conditions_config):
        """Alias names should be snake_case."""
        import re
        for name in custom_conditions_config["aliases"].keys():
            assert re.match(r'^[a-z][a-z0-9_]*$', name), f"Invalid alias name: {name}"


class TestConditionCompleteness:
    """Tests for condition completeness."""

    def test_minimum_conditions_count(self, custom_conditions_config):
        """Should have at least 10 conditions."""
        assert len(custom_conditions_config["conditions"]) >= 10

    def test_minimum_aliases_count(self, custom_conditions_config):
        """Should have at least 5 aliases."""
        assert len(custom_conditions_config["aliases"]) >= 5

    def test_all_expected_conditions_exist(self, custom_conditions_config):
        """All expected conditions should exist."""
        expected = [
            "ready_for_demo",
            "can_accelerate_flow",
            "stuck_and_frustrated",
            "soft_cta_appropriate",
            "roi_opportunity",
            "needs_repair",
            "needs_severe_repair",
            "repeated_same_objection",
            "objection_needs_escalation",
            "high_engagement",
            "low_engagement",
            "lead_is_hot",
            "lead_is_cold",
        ]
        for cond_name in expected:
            assert cond_name in custom_conditions_config["conditions"], f"Missing: {cond_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
