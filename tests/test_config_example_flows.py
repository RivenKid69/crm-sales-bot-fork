"""
Tests for example flow configurations.

Tests flows/examples/bant_flow.yaml and flows/examples/support_flow.yaml.
"""

import pytest
from pathlib import Path
import yaml

@pytest.fixture(scope="module")
def bant_flow_config():
    """Load BANT flow configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "examples" / "bant_flow.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

@pytest.fixture(scope="module")
def support_flow_config():
    """Load Support flow configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "examples" / "support_flow.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# =============================================================================
# BANT FLOW TESTS
# =============================================================================

class TestBantFlowStructure:
    """Tests for BANT flow structure."""

    def test_has_flow_section(self, bant_flow_config):
        """Config should have flow section."""
        assert "flow" in bant_flow_config

    def test_flow_has_name(self, bant_flow_config):
        """Flow should have name."""
        assert "name" in bant_flow_config["flow"]
        assert bant_flow_config["flow"]["name"] == "bant_qualification"

    def test_flow_has_version(self, bant_flow_config):
        """Flow should have version."""
        assert "version" in bant_flow_config["flow"]
        assert bant_flow_config["flow"]["version"] == "1.0"

    def test_flow_has_description(self, bant_flow_config):
        """Flow should have description."""
        assert "description" in bant_flow_config["flow"]

    def test_has_phases_section(self, bant_flow_config):
        """Config should have phases section."""
        assert "phases" in bant_flow_config

    def test_has_entry_points(self, bant_flow_config):
        """Config should have entry_points section."""
        assert "entry_points" in bant_flow_config

    def test_has_states_section(self, bant_flow_config):
        """Config should have states section."""
        assert "states" in bant_flow_config

    def test_has_variables_section(self, bant_flow_config):
        """Config should have variables section."""
        assert "variables" in bant_flow_config

    def test_has_templates_section(self, bant_flow_config):
        """Config should have templates section."""
        assert "templates" in bant_flow_config

class TestBantPhases:
    """Tests for BANT phases configuration."""

    def test_phases_have_order(self, bant_flow_config):
        """Phases should have order."""
        assert "order" in bant_flow_config["phases"]

    def test_phases_order_has_qualification(self, bant_flow_config):
        """Phases order should include qualification."""
        assert "qualification" in bant_flow_config["phases"]["order"]

    def test_phases_order_has_presentation(self, bant_flow_config):
        """Phases order should include presentation."""
        assert "presentation" in bant_flow_config["phases"]["order"]

    def test_phases_order_has_closing(self, bant_flow_config):
        """Phases order should include closing."""
        assert "closing" in bant_flow_config["phases"]["order"]

    def test_phases_have_mapping(self, bant_flow_config):
        """Phases should have mapping."""
        assert "mapping" in bant_flow_config["phases"]

    def test_phases_have_post_phases_state(self, bant_flow_config):
        """Phases should have post_phases_state."""
        assert "post_phases_state" in bant_flow_config["phases"]
        assert bant_flow_config["phases"]["post_phases_state"] == "success"

class TestBantEntryPoints:
    """Tests for BANT entry points."""

    def test_default_entry_point(self, bant_flow_config):
        """Should have default entry point."""
        assert "default" in bant_flow_config["entry_points"]
        assert bant_flow_config["entry_points"]["default"] == "greeting"

    def test_inbound_hot_entry_point(self, bant_flow_config):
        """Should have inbound_hot entry point."""
        assert "inbound_hot" in bant_flow_config["entry_points"]
        assert bant_flow_config["entry_points"]["inbound_hot"] == "fast_track_demo"

    def test_referral_entry_point(self, bant_flow_config):
        """Should have referral entry point."""
        assert "referral" in bant_flow_config["entry_points"]

class TestBantGreetingState:
    """Tests for BANT greeting state."""

    def test_greeting_state_exists(self, bant_flow_config):
        """greeting state should exist."""
        assert "greeting" in bant_flow_config["states"]

    def test_greeting_type_is_simple(self, bant_flow_config):
        """greeting should be simple type."""
        state = bant_flow_config["states"]["greeting"]
        assert state["type"] == "simple"

    def test_greeting_has_goal(self, bant_flow_config):
        """greeting should have goal."""
        state = bant_flow_config["states"]["greeting"]
        assert "goal" in state

class TestBantLeadRouter:
    """Tests for BANT lead router (CHOICE state)."""

    def test_lead_router_exists(self, bant_flow_config):
        """lead_router state should exist."""
        assert "lead_router" in bant_flow_config["states"]

    def test_lead_router_is_choice_type(self, bant_flow_config):
        """lead_router should be choice type."""
        state = bant_flow_config["states"]["lead_router"]
        assert state["type"] == "choice"

    def test_lead_router_has_choices(self, bant_flow_config):
        """lead_router should have choices."""
        state = bant_flow_config["states"]["lead_router"]
        assert "choices" in state
        assert len(state["choices"]) >= 4

    def test_lead_router_has_default(self, bant_flow_config):
        """lead_router should have default."""
        state = bant_flow_config["states"]["lead_router"]
        assert "default" in state

    def test_lead_router_choices_have_conditions(self, bant_flow_config):
        """Each choice should have condition and next."""
        state = bant_flow_config["states"]["lead_router"]
        for choice in state["choices"]:
            assert "condition" in choice
            assert "next" in choice

class TestBantStandardBant:
    """Tests for BANT standard_bant (FORK state)."""

    def test_standard_bant_exists(self, bant_flow_config):
        """standard_bant state should exist."""
        assert "standard_bant" in bant_flow_config["states"]

    def test_standard_bant_is_fork_type(self, bant_flow_config):
        """standard_bant should be fork type."""
        state = bant_flow_config["states"]["standard_bant"]
        assert state["type"] == "fork"

    def test_standard_bant_has_branches(self, bant_flow_config):
        """standard_bant should have branches."""
        state = bant_flow_config["states"]["standard_bant"]
        assert "branches" in state
        assert len(state["branches"]) == 4

    def test_standard_bant_has_budget_branch(self, bant_flow_config):
        """standard_bant should have budget branch."""
        state = bant_flow_config["states"]["standard_bant"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "budget_qualification" in branch_ids

    def test_standard_bant_has_authority_branch(self, bant_flow_config):
        """standard_bant should have authority branch."""
        state = bant_flow_config["states"]["standard_bant"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "authority_check" in branch_ids

    def test_standard_bant_has_need_branch(self, bant_flow_config):
        """standard_bant should have need branch."""
        state = bant_flow_config["states"]["standard_bant"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "need_discovery" in branch_ids

    def test_standard_bant_has_timeline_branch(self, bant_flow_config):
        """standard_bant should have timeline branch."""
        state = bant_flow_config["states"]["standard_bant"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "timeline_assessment" in branch_ids

    def test_standard_bant_has_join_at(self, bant_flow_config):
        """standard_bant should have join_at."""
        state = bant_flow_config["states"]["standard_bant"]
        assert "join_at" in state
        assert state["join_at"] == "bant_aggregation"

    def test_standard_bant_has_join_condition(self, bant_flow_config):
        """standard_bant should have join_condition."""
        state = bant_flow_config["states"]["standard_bant"]
        assert "join_condition" in state

class TestBantAggregation:
    """Tests for BANT aggregation (JOIN state)."""

    def test_bant_aggregation_exists(self, bant_flow_config):
        """bant_aggregation state should exist."""
        assert "bant_aggregation" in bant_flow_config["states"]

    def test_bant_aggregation_is_join_type(self, bant_flow_config):
        """bant_aggregation should be join type."""
        state = bant_flow_config["states"]["bant_aggregation"]
        assert state["type"] == "join"

    def test_bant_aggregation_expects_branches(self, bant_flow_config):
        """bant_aggregation should expect branches."""
        state = bant_flow_config["states"]["bant_aggregation"]
        assert "expects_branches" in state
        assert len(state["expects_branches"]) == 4

    def test_bant_aggregation_has_on_join(self, bant_flow_config):
        """bant_aggregation should have on_join."""
        state = bant_flow_config["states"]["bant_aggregation"]
        assert "on_join" in state
        assert state["on_join"]["action"] == "calculate_lead_score"

class TestBantVariables:
    """Tests for BANT variables."""

    def test_max_qualification_turns(self, bant_flow_config):
        """Should have max_qualification_turns variable."""
        assert "max_qualification_turns" in bant_flow_config["variables"]
        assert bant_flow_config["variables"]["max_qualification_turns"] == 15

    def test_min_bant_score_for_qualified(self, bant_flow_config):
        """Should have min_bant_score_for_qualified variable."""
        assert "min_bant_score_for_qualified" in bant_flow_config["variables"]

    def test_enterprise_threshold(self, bant_flow_config):
        """Should have enterprise_threshold variable."""
        assert "enterprise_threshold" in bant_flow_config["variables"]

    def test_smb_threshold(self, bant_flow_config):
        """Should have smb_threshold variable."""
        assert "smb_threshold" in bant_flow_config["variables"]

class TestBantFinalStates:
    """Tests for BANT final states."""

    def test_success_state_exists(self, bant_flow_config):
        """success state should exist."""
        assert "success" in bant_flow_config["states"]

    def test_success_is_final(self, bant_flow_config):
        """success should be final."""
        state = bant_flow_config["states"]["success"]
        assert state.get("is_final") is True

    def test_polite_exit_exists(self, bant_flow_config):
        """polite_exit state should exist."""
        assert "polite_exit" in bant_flow_config["states"]

    def test_polite_exit_is_final(self, bant_flow_config):
        """polite_exit should be final."""
        state = bant_flow_config["states"]["polite_exit"]
        assert state.get("is_final") is True

# =============================================================================
# SUPPORT FLOW TESTS
# =============================================================================

class TestSupportFlowStructure:
    """Tests for Support flow structure."""

    def test_has_flow_section(self, support_flow_config):
        """Config should have flow section."""
        assert "flow" in support_flow_config

    def test_flow_has_name(self, support_flow_config):
        """Flow should have name."""
        assert support_flow_config["flow"]["name"] == "customer_support"

    def test_flow_has_version(self, support_flow_config):
        """Flow should have version."""
        assert support_flow_config["flow"]["version"] == "1.0"

    def test_has_entry_points(self, support_flow_config):
        """Config should have entry_points section."""
        assert "entry_points" in support_flow_config

    def test_has_states_section(self, support_flow_config):
        """Config should have states section."""
        assert "states" in support_flow_config

    def test_has_variables_section(self, support_flow_config):
        """Config should have variables section."""
        assert "variables" in support_flow_config

    def test_has_templates_section(self, support_flow_config):
        """Config should have templates section."""
        assert "templates" in support_flow_config

class TestSupportEntryPoints:
    """Tests for Support entry points."""

    def test_default_entry_point(self, support_flow_config):
        """Should have default entry point."""
        assert support_flow_config["entry_points"]["default"] == "greeting"

    def test_returning_customer_entry_point(self, support_flow_config):
        """Should have returning_customer entry point."""
        assert "returning_customer" in support_flow_config["entry_points"]

    def test_escalation_entry_point(self, support_flow_config):
        """Should have escalation entry point."""
        assert "escalation" in support_flow_config["entry_points"]
        assert support_flow_config["entry_points"]["escalation"] == "human_handoff"

class TestSupportIssueClassifier:
    """Tests for Support issue classifier (CHOICE state)."""

    def test_issue_classifier_exists(self, support_flow_config):
        """issue_classifier state should exist."""
        assert "issue_classifier" in support_flow_config["states"]

    def test_issue_classifier_is_choice_type(self, support_flow_config):
        """issue_classifier should be choice type."""
        state = support_flow_config["states"]["issue_classifier"]
        assert state["type"] == "choice"

    def test_issue_classifier_has_choices(self, support_flow_config):
        """issue_classifier should have choices."""
        state = support_flow_config["states"]["issue_classifier"]
        assert "choices" in state
        assert len(state["choices"]) >= 5

    def test_issue_classifier_has_technical_choice(self, support_flow_config):
        """issue_classifier should route technical issues."""
        state = support_flow_config["states"]["issue_classifier"]
        conditions = [c["condition"] for c in state["choices"]]
        assert "is_technical_issue" in conditions

    def test_issue_classifier_has_billing_choice(self, support_flow_config):
        """issue_classifier should route billing issues."""
        state = support_flow_config["states"]["issue_classifier"]
        conditions = [c["condition"] for c in state["choices"]]
        assert "is_billing_issue" in conditions

class TestSupportTechnicalFlow:
    """Tests for Support technical flow (FORK state)."""

    def test_technical_flow_exists(self, support_flow_config):
        """technical_flow state should exist."""
        assert "technical_flow" in support_flow_config["states"]

    def test_technical_flow_is_fork_type(self, support_flow_config):
        """technical_flow should be fork type."""
        state = support_flow_config["states"]["technical_flow"]
        assert state["type"] == "fork"

    def test_technical_flow_has_branches(self, support_flow_config):
        """technical_flow should have branches."""
        state = support_flow_config["states"]["technical_flow"]
        assert "branches" in state
        assert len(state["branches"]) >= 2

    def test_technical_flow_has_system_check_branch(self, support_flow_config):
        """technical_flow should have system_check branch."""
        state = support_flow_config["states"]["technical_flow"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "system_check" in branch_ids

    def test_technical_flow_has_user_diagnostics_branch(self, support_flow_config):
        """technical_flow should have user_diagnostics branch."""
        state = support_flow_config["states"]["technical_flow"]
        branch_ids = [b["id"] for b in state["branches"]]
        assert "user_diagnostics" in branch_ids

class TestSupportTechnicalResolution:
    """Tests for Support technical resolution (JOIN state)."""

    def test_technical_resolution_exists(self, support_flow_config):
        """technical_resolution state should exist."""
        assert "technical_resolution" in support_flow_config["states"]

    def test_technical_resolution_is_join_type(self, support_flow_config):
        """technical_resolution should be join type."""
        state = support_flow_config["states"]["technical_resolution"]
        assert state["type"] == "join"

    def test_technical_resolution_has_on_join(self, support_flow_config):
        """technical_resolution should have on_join."""
        state = support_flow_config["states"]["technical_resolution"]
        assert "on_join" in state

class TestSupportBillingFlow:
    """Tests for Support billing flow."""

    def test_billing_flow_exists(self, support_flow_config):
        """billing_flow state should exist."""
        assert "billing_flow" in support_flow_config["states"]

    def test_billing_flow_has_history(self, support_flow_config):
        """billing_flow should have history."""
        state = support_flow_config["states"]["billing_flow"]
        assert "history" in state
        assert state["history"] == "shallow"

    def test_process_refund_exists(self, support_flow_config):
        """process_refund state should exist."""
        assert "process_refund" in support_flow_config["states"]

    def test_troubleshoot_payment_exists(self, support_flow_config):
        """troubleshoot_payment state should exist."""
        assert "troubleshoot_payment" in support_flow_config["states"]

class TestSupportAccountFlow:
    """Tests for Support account flow."""

    def test_account_flow_exists(self, support_flow_config):
        """account_flow state should exist."""
        assert "account_flow" in support_flow_config["states"]

    def test_help_password_reset_exists(self, support_flow_config):
        """help_password_reset state should exist."""
        assert "help_password_reset" in support_flow_config["states"]

    def test_verify_identity_exists(self, support_flow_config):
        """verify_identity state should exist."""
        assert "verify_identity" in support_flow_config["states"]

    def test_unlock_account_exists(self, support_flow_config):
        """unlock_account state should exist."""
        assert "unlock_account" in support_flow_config["states"]

class TestSupportFeatureRequest:
    """Tests for Support feature request handling."""

    def test_feature_request_handler_exists(self, support_flow_config):
        """feature_request_handler state should exist."""
        assert "feature_request_handler" in support_flow_config["states"]

    def test_thank_for_feedback_exists(self, support_flow_config):
        """thank_for_feedback state should exist."""
        assert "thank_for_feedback" in support_flow_config["states"]

    def test_share_roadmap_exists(self, support_flow_config):
        """share_roadmap state should exist."""
        assert "share_roadmap" in support_flow_config["states"]

class TestSupportVariables:
    """Tests for Support variables."""

    def test_max_self_service_attempts(self, support_flow_config):
        """Should have max_self_service_attempts variable."""
        assert "max_self_service_attempts" in support_flow_config["variables"]

    def test_auto_escalate_after_turns(self, support_flow_config):
        """Should have auto_escalate_after_turns variable."""
        assert "auto_escalate_after_turns" in support_flow_config["variables"]

    def test_satisfaction_survey_enabled(self, support_flow_config):
        """Should have satisfaction_survey_enabled variable."""
        assert "satisfaction_survey_enabled" in support_flow_config["variables"]

class TestSupportFinalStates:
    """Tests for Support final states."""

    def test_success_state_exists(self, support_flow_config):
        """success state should exist."""
        assert "success" in support_flow_config["states"]

    def test_success_is_final(self, support_flow_config):
        """success should be final."""
        state = support_flow_config["states"]["success"]
        assert state.get("is_final") is True

    def test_human_handoff_exists(self, support_flow_config):
        """human_handoff state should exist."""
        assert "human_handoff" in support_flow_config["states"]

    def test_human_handoff_is_final(self, support_flow_config):
        """human_handoff should be final."""
        state = support_flow_config["states"]["human_handoff"]
        assert state.get("is_final") is True

    def test_human_handoff_has_on_enter(self, support_flow_config):
        """human_handoff should have on_enter action."""
        state = support_flow_config["states"]["human_handoff"]
        assert "on_enter" in state

    def test_final_goodbye_exists(self, support_flow_config):
        """final_goodbye state should exist."""
        assert "final_goodbye" in support_flow_config["states"]

class TestSupportTemplates:
    """Tests for Support templates."""

    def test_welcome_to_support_template(self, support_flow_config):
        """Should have welcome_to_support template."""
        assert "welcome_to_support" in support_flow_config["templates"]

    def test_analyze_diagnostics_template(self, support_flow_config):
        """Should have analyze_diagnostics template."""
        assert "analyze_diagnostics" in support_flow_config["templates"]

    def test_notify_human_agent_template(self, support_flow_config):
        """Should have notify_human_agent template."""
        assert "notify_human_agent" in support_flow_config["templates"]

# =============================================================================
# CROSS-FLOW TESTS
# =============================================================================

class TestDagFlowFeatures:
    """Tests for DAG flow features across example flows."""

    def test_both_flows_have_choice_states(self, bant_flow_config, support_flow_config):
        """Both flows should have CHOICE states."""
        bant_types = [s.get("type") for s in bant_flow_config["states"].values()]
        support_types = [s.get("type") for s in support_flow_config["states"].values()]
        assert "choice" in bant_types
        assert "choice" in support_types

    def test_both_flows_have_fork_states(self, bant_flow_config, support_flow_config):
        """Both flows should have FORK states."""
        bant_types = [s.get("type") for s in bant_flow_config["states"].values()]
        support_types = [s.get("type") for s in support_flow_config["states"].values()]
        assert "fork" in bant_types
        assert "fork" in support_types

    def test_both_flows_have_join_states(self, bant_flow_config, support_flow_config):
        """Both flows should have JOIN states."""
        bant_types = [s.get("type") for s in bant_flow_config["states"].values()]
        support_types = [s.get("type") for s in support_flow_config["states"].values()]
        assert "join" in bant_types
        assert "join" in support_types

    def test_flows_have_final_states(self, bant_flow_config, support_flow_config):
        """Both flows should have final states."""
        bant_finals = [name for name, s in bant_flow_config["states"].items() if s.get("is_final")]
        support_finals = [name for name, s in support_flow_config["states"].items() if s.get("is_final")]
        assert len(bant_finals) >= 2
        assert len(support_finals) >= 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
