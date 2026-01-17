"""
Tests for prompt templates configuration.

Tests templates/_base/prompts.yaml and templates/spin_selling/prompts.yaml.
"""

import pytest
from pathlib import Path
import yaml


@pytest.fixture(scope="module")
def base_prompts_config():
    """Load base prompts configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "_base" / "prompts.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def spin_prompts_config():
    """Load SPIN selling prompts configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "spin_selling" / "prompts.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestBasePromptsStructure:
    """Tests for base prompts structure."""

    def test_has_templates_section(self, base_prompts_config):
        """Config should have templates section."""
        assert "templates" in base_prompts_config

    def test_templates_not_empty(self, base_prompts_config):
        """Templates section should not be empty."""
        assert len(base_prompts_config["templates"]) > 0

    def test_minimum_templates_count(self, base_prompts_config):
        """Should have at least 20 base templates."""
        assert len(base_prompts_config["templates"]) >= 20


class TestGreetingTemplates:
    """Tests for greeting templates."""

    def test_greet_back_exists(self, base_prompts_config):
        """greet_back template should exist."""
        assert "greet_back" in base_prompts_config["templates"]

    def test_greet_back_has_description(self, base_prompts_config):
        """greet_back should have description."""
        template = base_prompts_config["templates"]["greet_back"]
        assert "description" in template

    def test_greet_back_has_parameters(self, base_prompts_config):
        """greet_back should have parameters."""
        template = base_prompts_config["templates"]["greet_back"]
        assert "parameters" in template
        assert "required" in template["parameters"]

    def test_greet_back_has_template(self, base_prompts_config):
        """greet_back should have template text."""
        template = base_prompts_config["templates"]["greet_back"]
        assert "template" in template
        assert len(template["template"]) > 0

    def test_ask_how_to_help_exists(self, base_prompts_config):
        """ask_how_to_help template should exist."""
        assert "ask_how_to_help" in base_prompts_config["templates"]

    def test_greeting_exists(self, base_prompts_config):
        """greeting template should exist."""
        assert "greeting" in base_prompts_config["templates"]


class TestPriceTemplates:
    """Tests for price-related templates."""

    def test_deflect_and_continue_exists(self, base_prompts_config):
        """deflect_and_continue template should exist."""
        assert "deflect_and_continue" in base_prompts_config["templates"]

    def test_deflect_and_continue_requires_system(self, base_prompts_config):
        """deflect_and_continue should require system parameter."""
        template = base_prompts_config["templates"]["deflect_and_continue"]
        assert "system" in template["parameters"]["required"]

    def test_deflect_and_continue_requires_history(self, base_prompts_config):
        """deflect_and_continue should require history parameter."""
        template = base_prompts_config["templates"]["deflect_and_continue"]
        assert "history" in template["parameters"]["required"]

    def test_answer_with_facts_exists(self, base_prompts_config):
        """answer_with_facts template should exist."""
        assert "answer_with_facts" in base_prompts_config["templates"]

    def test_answer_with_range_and_qualify_exists(self, base_prompts_config):
        """answer_with_range_and_qualify template should exist."""
        assert "answer_with_range_and_qualify" in base_prompts_config["templates"]


class TestContinueTemplates:
    """Tests for conversation continuation templates."""

    def test_continue_current_goal_exists(self, base_prompts_config):
        """continue_current_goal template should exist."""
        assert "continue_current_goal" in base_prompts_config["templates"]

    def test_continue_current_goal_requires_collected_data(self, base_prompts_config):
        """continue_current_goal should require collected_data."""
        template = base_prompts_config["templates"]["continue_current_goal"]
        assert "collected_data" in template["parameters"]["required"]

    def test_continue_current_goal_requires_missing_data(self, base_prompts_config):
        """continue_current_goal should require missing_data."""
        template = base_prompts_config["templates"]["continue_current_goal"]
        assert "missing_data" in template["parameters"]["required"]


class TestQuestionAnswerTemplates:
    """Tests for Q&A templates."""

    def test_answer_question_exists(self, base_prompts_config):
        """answer_question template should exist."""
        assert "answer_question" in base_prompts_config["templates"]

    def test_answer_with_knowledge_exists(self, base_prompts_config):
        """answer_with_knowledge template should exist."""
        assert "answer_with_knowledge" in base_prompts_config["templates"]

    def test_answer_and_continue_exists(self, base_prompts_config):
        """answer_and_continue template should exist."""
        assert "answer_and_continue" in base_prompts_config["templates"]

    def test_answer_question_requires_retrieved_facts(self, base_prompts_config):
        """answer_question should require retrieved_facts."""
        template = base_prompts_config["templates"]["answer_question"]
        assert "retrieved_facts" in template["parameters"]["required"]


class TestFinalStateTemplates:
    """Tests for final state templates."""

    def test_presentation_exists(self, base_prompts_config):
        """presentation template should exist."""
        assert "presentation" in base_prompts_config["templates"]

    def test_soft_close_exists(self, base_prompts_config):
        """soft_close template should exist."""
        assert "soft_close" in base_prompts_config["templates"]

    def test_close_exists(self, base_prompts_config):
        """close template should exist."""
        assert "close" in base_prompts_config["templates"]

    def test_presentation_requires_pain_point(self, base_prompts_config):
        """presentation should require pain_point."""
        template = base_prompts_config["templates"]["presentation"]
        assert "pain_point" in template["parameters"]["required"]


class TestObjectionTemplates:
    """Tests for objection handling templates."""

    def test_handle_objection_exists(self, base_prompts_config):
        """handle_objection template should exist."""
        assert "handle_objection" in base_prompts_config["templates"]

    def test_handle_objection_no_time_exists(self, base_prompts_config):
        """handle_objection_no_time template should exist."""
        assert "handle_objection_no_time" in base_prompts_config["templates"]

    def test_handle_objection_think_exists(self, base_prompts_config):
        """handle_objection_think template should exist."""
        assert "handle_objection_think" in base_prompts_config["templates"]


class TestSocialTemplates:
    """Tests for social interaction templates."""

    def test_small_talk_and_continue_exists(self, base_prompts_config):
        """small_talk_and_continue template should exist."""
        assert "small_talk_and_continue" in base_prompts_config["templates"]

    def test_acknowledge_and_continue_exists(self, base_prompts_config):
        """acknowledge_and_continue template should exist."""
        assert "acknowledge_and_continue" in base_prompts_config["templates"]

    def test_handle_farewell_exists(self, base_prompts_config):
        """handle_farewell template should exist."""
        assert "handle_farewell" in base_prompts_config["templates"]


class TestUtilityTemplates:
    """Tests for utility templates."""

    def test_clarify_and_continue_exists(self, base_prompts_config):
        """clarify_and_continue template should exist."""
        assert "clarify_and_continue" in base_prompts_config["templates"]

    def test_clarify_one_question_exists(self, base_prompts_config):
        """clarify_one_question template should exist."""
        assert "clarify_one_question" in base_prompts_config["templates"]

    def test_summarize_and_clarify_exists(self, base_prompts_config):
        """summarize_and_clarify template should exist."""
        assert "summarize_and_clarify" in base_prompts_config["templates"]

    def test_confirm_and_collect_contact_exists(self, base_prompts_config):
        """confirm_and_collect_contact template should exist."""
        assert "confirm_and_collect_contact" in base_prompts_config["templates"]


class TestToneTemplates:
    """Tests for tone-specific templates."""

    def test_short_response_frustrated_exists(self, base_prompts_config):
        """short_response_frustrated template should exist."""
        assert "short_response_frustrated" in base_prompts_config["templates"]

    def test_empathetic_response_exists(self, base_prompts_config):
        """empathetic_response template should exist."""
        assert "empathetic_response" in base_prompts_config["templates"]

    def test_informal_response_exists(self, base_prompts_config):
        """informal_response template should exist."""
        assert "informal_response" in base_prompts_config["templates"]

    def test_soft_exit_frustrated_exists(self, base_prompts_config):
        """soft_exit_frustrated template should exist."""
        assert "soft_exit_frustrated" in base_prompts_config["templates"]


class TestSpinPromptsStructure:
    """Tests for SPIN prompts structure."""

    def test_has_templates_section(self, spin_prompts_config):
        """Config should have templates section."""
        assert "templates" in spin_prompts_config

    def test_templates_not_empty(self, spin_prompts_config):
        """Templates section should not be empty."""
        assert len(spin_prompts_config["templates"]) > 0

    def test_minimum_spin_templates_count(self, spin_prompts_config):
        """Should have at least 10 SPIN templates."""
        assert len(spin_prompts_config["templates"]) >= 10


class TestSpinSituationTemplates:
    """Tests for SPIN Situation templates."""

    def test_spin_situation_exists(self, spin_prompts_config):
        """spin_situation template should exist."""
        assert "spin_situation" in spin_prompts_config["templates"]

    def test_spin_situation_has_phase(self, spin_prompts_config):
        """spin_situation should have phase marker."""
        template = spin_prompts_config["templates"]["spin_situation"]
        assert "phase" in template
        assert template["phase"] == "situation"

    def test_spin_situation_has_description(self, spin_prompts_config):
        """spin_situation should have description."""
        template = spin_prompts_config["templates"]["spin_situation"]
        assert "description" in template

    def test_probe_situation_exists(self, spin_prompts_config):
        """probe_situation template should exist."""
        assert "probe_situation" in spin_prompts_config["templates"]

    def test_transition_to_spin_problem_exists(self, spin_prompts_config):
        """transition_to_spin_problem template should exist."""
        assert "transition_to_spin_problem" in spin_prompts_config["templates"]


class TestSpinProblemTemplates:
    """Tests for SPIN Problem templates."""

    def test_spin_problem_exists(self, spin_prompts_config):
        """spin_problem template should exist."""
        assert "spin_problem" in spin_prompts_config["templates"]

    def test_spin_problem_has_phase(self, spin_prompts_config):
        """spin_problem should have phase marker."""
        template = spin_prompts_config["templates"]["spin_problem"]
        assert "phase" in template
        assert template["phase"] == "problem"

    def test_probe_problem_exists(self, spin_prompts_config):
        """probe_problem template should exist."""
        assert "probe_problem" in spin_prompts_config["templates"]

    def test_transition_to_spin_implication_exists(self, spin_prompts_config):
        """transition_to_spin_implication template should exist."""
        assert "transition_to_spin_implication" in spin_prompts_config["templates"]


class TestSpinImplicationTemplates:
    """Tests for SPIN Implication templates."""

    def test_spin_implication_exists(self, spin_prompts_config):
        """spin_implication template should exist."""
        assert "spin_implication" in spin_prompts_config["templates"]

    def test_spin_implication_has_phase(self, spin_prompts_config):
        """spin_implication should have phase marker."""
        template = spin_prompts_config["templates"]["spin_implication"]
        assert "phase" in template
        assert template["phase"] == "implication"

    def test_probe_implication_exists(self, spin_prompts_config):
        """probe_implication template should exist."""
        assert "probe_implication" in spin_prompts_config["templates"]

    def test_transition_to_spin_need_payoff_exists(self, spin_prompts_config):
        """transition_to_spin_need_payoff template should exist."""
        assert "transition_to_spin_need_payoff" in spin_prompts_config["templates"]


class TestSpinNeedPayoffTemplates:
    """Tests for SPIN Need-Payoff templates."""

    def test_spin_need_payoff_exists(self, spin_prompts_config):
        """spin_need_payoff template should exist."""
        assert "spin_need_payoff" in spin_prompts_config["templates"]

    def test_spin_need_payoff_has_phase(self, spin_prompts_config):
        """spin_need_payoff should have phase marker."""
        template = spin_prompts_config["templates"]["spin_need_payoff"]
        assert "phase" in template
        assert template["phase"] == "need_payoff"

    def test_probe_need_payoff_exists(self, spin_prompts_config):
        """probe_need_payoff template should exist."""
        assert "probe_need_payoff" in spin_prompts_config["templates"]

    def test_transition_to_presentation_exists(self, spin_prompts_config):
        """transition_to_presentation template should exist."""
        assert "transition_to_presentation" in spin_prompts_config["templates"]


class TestTemplateParameterValidity:
    """Tests for template parameter validity."""

    def test_all_base_templates_have_parameters(self, base_prompts_config):
        """All base templates should have parameters."""
        for name, template in base_prompts_config["templates"].items():
            assert "parameters" in template, f"{name} missing parameters"

    def test_all_base_templates_have_required_params(self, base_prompts_config):
        """All base templates should have required parameters."""
        for name, template in base_prompts_config["templates"].items():
            assert "required" in template["parameters"], f"{name} missing required params"

    def test_all_spin_templates_have_parameters(self, spin_prompts_config):
        """All SPIN templates should have parameters."""
        for name, template in spin_prompts_config["templates"].items():
            assert "parameters" in template, f"{name} missing parameters"

    def test_all_templates_have_template_text(self, base_prompts_config):
        """All templates should have template text."""
        for name, template in base_prompts_config["templates"].items():
            assert "template" in template, f"{name} missing template"
            assert len(template["template"]) > 0, f"{name} has empty template"

    def test_spin_templates_have_template_text(self, spin_prompts_config):
        """All SPIN templates should have template text."""
        for name, template in spin_prompts_config["templates"].items():
            assert "template" in template, f"{name} missing template"
            assert len(template["template"]) > 0, f"{name} has empty template"


class TestTemplateVariables:
    """Tests for template variable usage."""

    def test_templates_use_placeholders(self, base_prompts_config):
        """Templates should use {placeholder} syntax."""
        for name, template in base_prompts_config["templates"].items():
            text = template["template"]
            # Check for at least one placeholder
            assert "{" in text and "}" in text, f"{name} missing placeholders"

    def test_spin_templates_use_placeholders(self, spin_prompts_config):
        """SPIN templates should use {placeholder} syntax."""
        for name, template in spin_prompts_config["templates"].items():
            text = template["template"]
            assert "{" in text and "}" in text, f"{name} missing placeholders"

    def test_common_placeholders_in_base(self, base_prompts_config):
        """Common placeholders should be used in base templates."""
        all_templates_text = " ".join(
            t["template"] for t in base_prompts_config["templates"].values()
        )
        assert "{system}" in all_templates_text
        assert "{user_message}" in all_templates_text
        assert "{history}" in all_templates_text


class TestSpinPhaseCompleteness:
    """Tests for SPIN phase completeness."""

    def test_all_spin_phases_have_main_template(self, spin_prompts_config):
        """Each SPIN phase should have a main template."""
        phases = ["situation", "problem", "implication", "need_payoff"]
        for phase in phases:
            template_name = f"spin_{phase}"
            assert template_name in spin_prompts_config["templates"], f"Missing {template_name}"

    def test_all_spin_phases_have_probe_template(self, spin_prompts_config):
        """Each SPIN phase should have a probe template."""
        phases = ["situation", "problem", "implication", "need_payoff"]
        for phase in phases:
            template_name = f"probe_{phase}"
            assert template_name in spin_prompts_config["templates"], f"Missing {template_name}"

    def test_phase_transitions_exist(self, spin_prompts_config):
        """Transition templates should exist between phases."""
        transitions = [
            "transition_to_spin_problem",
            "transition_to_spin_implication",
            "transition_to_spin_need_payoff",
            "transition_to_presentation",
        ]
        for transition in transitions:
            assert transition in spin_prompts_config["templates"], f"Missing {transition}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
