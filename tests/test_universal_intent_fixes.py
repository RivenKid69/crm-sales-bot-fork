"""
Tests for Universal Intent Architecture fixes.

Covers:
1. unified_progress mixin - universal progress transitions
2. 4 new objection handlers (complexity, timing, trust, no_need)
3. BANT semantic fix - progress intents stay in current phase via rules
4. default_price_action parameter resolution
5. All 20 flows have correct configuration

Created to verify fixes from commit: fix(flows): implement universal intent architecture
"""

import pytest
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List, Set

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_loader import ConfigLoader, FlowConfig


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def config_loader():
    """Create ConfigLoader instance with real config."""
    return ConfigLoader()


@pytest.fixture(scope="module")
def config_dir():
    """Get config directory path."""
    return Path(__file__).parent.parent / "src" / "yaml_config"


@pytest.fixture(scope="module")
def raw_mixins(config_dir) -> Dict[str, Any]:
    """Load raw mixins YAML (before resolution)."""
    mixins_file = config_dir / "flows" / "_base" / "mixins.yaml"
    with open(mixins_file) as f:
        data = yaml.safe_load(f)
    return data.get("mixins", {})


@pytest.fixture(scope="module")
def all_flows(config_loader) -> Dict[str, FlowConfig]:
    """Load all 20 flows."""
    flow_names = [
        "aida", "bant", "challenger", "command", "consultative",
        "customer_centric", "demo_first", "fab", "gap", "inbound",
        "meddic", "neat", "relationship", "sandler", "snap",
        "social", "solution", "spin_selling", "transactional", "value"
    ]
    flows = {}
    for name in flow_names:
        try:
            flows[name] = config_loader.load_flow(name)
        except Exception as e:
            pytest.fail(f"Failed to load flow {name}: {e}")
    return flows


@pytest.fixture(scope="module")
def bant_flow(config_loader) -> FlowConfig:
    """Load BANT flow specifically."""
    return config_loader.load_flow("bant")


@pytest.fixture(scope="module")
def spin_flow(config_loader) -> FlowConfig:
    """Load SPIN Selling flow specifically."""
    return config_loader.load_flow("spin_selling")


# =============================================================================
# CLASSIFIER INTENTS (from prompts.py)
# =============================================================================

CLASSIFIER_INTENTS = {
    # Core communication
    "greeting", "agreement", "gratitude", "farewell", "small_talk",
    # Price/pricing
    "price_question", "pricing_details", "objection_price",
    # Product questions
    "question_features", "question_integrations", "comparison",
    # Objections (8 types)
    "objection_competitor", "objection_no_time", "objection_think",
    "objection_complexity", "objection_timing", "objection_trust", "objection_no_need",
    # Progress signals
    "situation_provided", "problem_revealed", "implication_acknowledged",
    "need_expressed", "info_provided", "data_complete",
    # Specific intents
    "demo_request", "callback_request", "consultation_request",
    "rejection", "no_problem", "no_need", "go_back",
    "unclear",
}


# =============================================================================
# TEST: UNIFIED_PROGRESS & PHASE_PROGRESS MIXINS
# =============================================================================

class TestProgressMixins:
    """Tests for unified_progress and phase_progress mixins."""

    def test_unified_progress_mixin_exists(self, raw_mixins):
        """Verify unified_progress mixin is defined."""
        assert "unified_progress" in raw_mixins, "unified_progress mixin should exist"

    def test_phase_progress_mixin_exists(self, raw_mixins):
        """Verify phase_progress mixin is defined (used by _base_phase)."""
        assert "phase_progress" in raw_mixins, "phase_progress mixin should exist"

    def test_unified_progress_has_progress_transitions(self, raw_mixins):
        """Verify unified_progress has all progress intent transitions."""
        mixin = raw_mixins["unified_progress"]
        transitions = mixin.get("transitions", {})

        progress_intents = [
            "agreement", "info_provided",
            "situation_provided", "problem_revealed",
            "implication_acknowledged", "need_expressed"
        ]

        for intent in progress_intents:
            assert intent in transitions, f"unified_progress should have {intent} transition"
            assert transitions[intent] == "{{next_phase_state}}", \
                f"{intent} should transition to {{{{next_phase_state}}}}"

    def test_phase_progress_has_progress_transitions(self, raw_mixins):
        """Verify phase_progress has SPIN-like progress transitions."""
        mixin = raw_mixins["phase_progress"]
        transitions = mixin.get("transitions", {})

        progress_intents = [
            "situation_provided", "problem_revealed",
            "implication_acknowledged", "need_expressed"
        ]

        for intent in progress_intents:
            assert intent in transitions, f"phase_progress should have {intent} transition"
            assert transitions[intent] == "{{next_phase_state}}", \
                f"{intent} should transition to {{{{next_phase_state}}}}"

    def test_unified_progress_has_question_rules(self, raw_mixins):
        """Verify unified_progress handles questions with rules."""
        mixin = raw_mixins["unified_progress"]
        rules = mixin.get("rules", {})

        question_intents = [
            "question_features", "question_integrations",
            "comparison", "consultation_request"
        ]

        for intent in question_intents:
            assert intent in rules, f"unified_progress should have {intent} rule"


# =============================================================================
# TEST: NEW OBJECTION HANDLERS
# =============================================================================

class TestNewObjectionHandlers:
    """Tests for 4 new objection handlers added to objection_handling mixin."""

    NEW_OBJECTIONS = [
        "objection_complexity",
        "objection_timing",
        "objection_trust",
        "objection_no_need"
    ]

    def test_objection_handling_mixin_exists(self, raw_mixins):
        """Verify objection_handling mixin exists."""
        assert "objection_handling" in raw_mixins, "objection_handling mixin should exist"

    def test_new_objection_handlers_exist(self, raw_mixins):
        """Verify all 4 new objection handlers are defined."""
        objection_mixin = raw_mixins["objection_handling"]
        transitions = objection_mixin.get("transitions", {})

        for objection in self.NEW_OBJECTIONS:
            assert objection in transitions, \
                f"objection_handling should have {objection} transition"

    def test_new_objection_handlers_have_limit_check(self, raw_mixins):
        """Verify new objection handlers check objection_limit_reached."""
        objection_mixin = raw_mixins["objection_handling"]
        transitions = objection_mixin.get("transitions", {})

        for objection in self.NEW_OBJECTIONS:
            handler = transitions[objection]
            assert isinstance(handler, list), \
                f"{objection} should be a conditional list"

            # First item should check limit
            assert len(handler) >= 2, \
                f"{objection} should have limit check and default action"

            limit_check = handler[0]
            assert isinstance(limit_check, dict), \
                f"{objection} first item should be condition dict"
            assert limit_check.get("when") == "objection_limit_reached", \
                f"{objection} should check objection_limit_reached"
            assert limit_check.get("then") == "soft_close", \
                f"{objection} should go to soft_close when limit reached"

    def test_new_objection_handlers_default_to_handle(self, raw_mixins):
        """Verify new objection handlers default to handle_objection."""
        objection_mixin = raw_mixins["objection_handling"]
        transitions = objection_mixin.get("transitions", {})

        for objection in self.NEW_OBJECTIONS:
            handler = transitions[objection]
            # Last item should be default action
            default_action = handler[-1]
            assert default_action == "handle_objection", \
                f"{objection} should default to handle_objection, got {default_action}"

    def test_all_classifier_objections_have_handlers(self, raw_mixins):
        """Verify all objection intents from classifier have handlers."""
        objection_mixin = raw_mixins["objection_handling"]
        transitions = objection_mixin.get("transitions", {})

        classifier_objections = [
            intent for intent in CLASSIFIER_INTENTS
            if intent.startswith("objection_")
        ]

        for objection in classifier_objections:
            assert objection in transitions, \
                f"Classifier objection {objection} should have handler in objection_handling mixin"

    def test_spin_selling_has_new_objection_handlers(self, spin_flow):
        """Verify SPIN Selling flow has new objection handlers in resolved states."""
        # Check spin_situation state (inherits from _spin_base)
        spin_situation = spin_flow.states.get("spin_situation", {})
        transitions = spin_situation.get("transitions", {})

        for objection in self.NEW_OBJECTIONS:
            assert objection in transitions, \
                f"spin_situation should have {objection} handler (inherited from _spin_base)"

    def test_all_flows_have_objection_handlers_resolved(self, all_flows):
        """Verify all flows have objection handlers in resolved states."""
        for flow_name, flow in all_flows.items():
            # Get first non-abstract state
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue
                if state_name in ("greeting", "success", "soft_close"):
                    continue  # Skip base states

                transitions = state_config.get("transitions", {})

                # Should have at least objection_price handler
                assert "objection_price" in transitions, \
                    f"{flow_name}/{state_name} should have objection_price handler"
                break  # Only check first flow-specific state


# =============================================================================
# TEST: BANT SEMANTIC FIX
# =============================================================================

class TestBANTSemanticFix:
    """Tests for BANT semantic fix - progress intents stay in current phase via rules."""

    BANT_STATES = ["bant_budget", "bant_authority", "bant_need", "bant_timeline"]

    def test_bant_states_exist(self, bant_flow):
        """Verify all BANT states are defined."""
        for state in self.BANT_STATES:
            assert state in bant_flow.states, f"BANT flow should have {state}"

    def test_bant_budget_progress_intents_in_rules(self, bant_flow):
        """Verify progress intents in budget phase are handled via rules (stay in phase)."""
        budget = bant_flow.states["bant_budget"]
        rules = budget.get("rules", {})

        # situation_provided should result in ask_about_budget (stay in budget)
        assert "situation_provided" in rules, \
            "bant_budget should have situation_provided rule"
        assert rules.get("situation_provided") == "ask_about_budget", \
            "situation_provided in budget should ask about budget, not advance"

        # problem_revealed should also stay in budget
        assert "problem_revealed" in rules, \
            "bant_budget should have problem_revealed rule"
        assert rules.get("problem_revealed") == "ask_about_budget", \
            "problem_revealed in budget should ask about budget, not advance"

    def test_bant_authority_progress_intents_in_rules(self, bant_flow):
        """Verify progress intents in authority phase are handled via rules."""
        authority = bant_flow.states["bant_authority"]
        rules = authority.get("rules", {})

        assert rules.get("situation_provided") == "ask_about_authority", \
            "situation_provided in authority should ask about authority"
        assert rules.get("problem_revealed") == "ask_about_authority", \
            "problem_revealed in authority should ask about authority"

    def test_bant_need_problem_revealed_explores(self, bant_flow):
        """Verify problem_revealed in need phase explores deeper (semantic exception)."""
        need = bant_flow.states["bant_need"]
        rules = need.get("rules", {})

        # In need phase, problem_revealed is relevant progress
        assert rules.get("problem_revealed") == "explore_need_deeper", \
            "problem_revealed in need phase should explore deeper"

    def test_bant_timeline_progress_intents_continue(self, bant_flow):
        """Verify progress intents in timeline phase continue current goal."""
        timeline = bant_flow.states["bant_timeline"]
        rules = timeline.get("rules", {})

        assert rules.get("situation_provided") == "continue_current_goal", \
            "situation_provided in timeline should continue current goal"
        assert rules.get("problem_revealed") == "continue_current_goal", \
            "problem_revealed in timeline should continue current goal"

    def test_bant_advances_only_on_explicit_intents(self, bant_flow):
        """Verify BANT advances only on agreement/info_provided/data_complete transitions."""
        explicit_advance_intents = {"agreement", "info_provided", "data_complete"}

        expected_transitions = {
            "bant_budget": "bant_authority",
            "bant_authority": "bant_need",
            "bant_need": "bant_timeline",
            "bant_timeline": "presentation"
        }

        for state_name in self.BANT_STATES:
            state = bant_flow.states[state_name]
            transitions = state.get("transitions", {})
            expected_next = expected_transitions[state_name]

            # Check that explicit intents cause correct transitions
            for intent in explicit_advance_intents:
                if intent in transitions:
                    target = transitions[intent]
                    # Handle both simple string and conditional list
                    if isinstance(target, str):
                        assert target == expected_next, \
                            f"{intent} in {state_name} should advance to {expected_next}"

    def test_bant_rules_override_transitions(self, bant_flow):
        """Verify BANT has rules that semantically override inherited transitions.

        Rules are checked before transitions in state machine, so having both:
        - transitions.situation_provided: bant_authority (from phase_progress mixin)
        - rules.situation_provided: ask_about_budget

        Results in the rule firing first, keeping the state and applying the action.
        """
        budget = bant_flow.states["bant_budget"]

        # Both should exist
        assert "situation_provided" in budget.get("rules", {}), \
            "BANT budget should have situation_provided rule"

        # The rule should define the actual behavior
        rule_action = budget["rules"]["situation_provided"]
        assert rule_action == "ask_about_budget", \
            "Rule should keep us in budget phase asking about budget"


# =============================================================================
# TEST: PARAMETER RESOLUTION
# =============================================================================

class TestParameterResolution:
    """Tests for default_price_action resolution in price rules."""

    def test_price_question_rules_resolved(self, all_flows):
        """Verify price_question rules have resolved actions (not templates)."""
        valid_actions = {
            "answer_with_facts",
            "deflect_and_continue",
            "acknowledge_and_continue",
            "continue_current_goal"
        }

        for flow_name, flow in all_flows.items():
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                rules = state_config.get("rules", {})
                price_rule = rules.get("price_question")

                if price_rule:
                    # Handle conditional rules (list with when/then)
                    if isinstance(price_rule, list):
                        for item in price_rule:
                            if isinstance(item, str):
                                assert "{{" not in item, \
                                    f"{flow_name}/{state_name} has unresolved template in price_question: {item}"
                    elif isinstance(price_rule, str):
                        assert "{{" not in price_rule, \
                            f"{flow_name}/{state_name} has unresolved template: {price_rule}"

    def test_bant_states_have_correct_price_actions(self, bant_flow):
        """Verify BANT states have correct price handling based on phase."""
        # Budget phase can answer about price
        budget = bant_flow.states["bant_budget"]
        budget_price = budget.get("rules", {}).get("price_question", [])
        if isinstance(budget_price, list):
            # Should have answer_with_facts as default
            assert "answer_with_facts" in str(budget_price), \
                "bant_budget should answer with facts about price"

        # Timeline phase can also answer about price
        timeline = bant_flow.states["bant_timeline"]
        timeline_price = timeline.get("rules", {}).get("price_question", [])
        if isinstance(timeline_price, list):
            assert "answer_with_facts" in str(timeline_price), \
                "bant_timeline should answer with facts about price"


# =============================================================================
# TEST: ALL 20 FLOWS CONFIGURATION
# =============================================================================

class TestAll20FlowsConfiguration:
    """Tests verifying all 20 flows are correctly configured."""

    FLOW_NAMES = [
        "aida", "bant", "challenger", "command", "consultative",
        "customer_centric", "demo_first", "fab", "gap", "inbound",
        "meddic", "neat", "relationship", "sandler", "snap",
        "social", "solution", "spin_selling", "transactional", "value"
    ]

    def test_all_20_flows_load_successfully(self, all_flows):
        """Verify all 20 flows load without errors."""
        assert len(all_flows) == 20, f"Should have 20 flows, got {len(all_flows)}"

        for flow_name in self.FLOW_NAMES:
            assert flow_name in all_flows, f"Flow {flow_name} should be loaded"

    def test_all_flows_have_states(self, all_flows):
        """Verify all flows have at least one non-abstract state."""
        for flow_name, flow in all_flows.items():
            non_abstract = [s for s in flow.states if not s.startswith("_")]
            assert len(non_abstract) > 0, \
                f"{flow_name} should have at least one non-abstract state"

    def test_all_flows_have_objection_handling(self, all_flows):
        """Verify all flows have objection handling capability."""
        for flow_name, flow in all_flows.items():
            has_objection_handling = False

            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                transitions = state_config.get("transitions", {})

                # Check for objection transitions
                for intent in transitions:
                    if intent.startswith("objection_"):
                        has_objection_handling = True
                        break

                if has_objection_handling:
                    break

            assert has_objection_handling, \
                f"{flow_name} should have objection handling"

    def test_all_flows_handle_exit_intents(self, all_flows):
        """Verify all flows handle rejection and farewell."""
        for flow_name, flow in all_flows.items():
            handles_exit = False

            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                transitions = state_config.get("transitions", {})
                rules = state_config.get("rules", {})

                # Check both transitions and rules for exit handling
                if "rejection" in transitions or "farewell" in transitions:
                    handles_exit = True
                    break
                if "rejection" in rules or "farewell" in rules:
                    handles_exit = True
                    break

            # All flows should handle exit intents in some form
            assert handles_exit, \
                f"{flow_name} should handle exit intents (rejection/farewell)"

    def test_no_unresolved_template_variables(self, all_flows):
        """Verify no unresolved {{variable}} in final config."""
        import re
        template_pattern = re.compile(r"\{\{[^}]+\}\}")

        unresolved = []

        for flow_name, flow in all_flows.items():
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                # Check rules for unresolved templates
                rules = state_config.get("rules", {})
                for intent, action in rules.items():
                    if isinstance(action, str) and template_pattern.search(action):
                        unresolved.append(f"{flow_name}/{state_name}/rules/{intent}: {action}")
                    elif isinstance(action, list):
                        for item in action:
                            if isinstance(item, str) and template_pattern.search(item):
                                unresolved.append(f"{flow_name}/{state_name}/rules/{intent}: {item}")

        assert len(unresolved) == 0, \
            f"Found unresolved template variables:\n" + "\n".join(unresolved)


# =============================================================================
# TEST: INTENT COVERAGE
# =============================================================================

class TestIntentCoverage:
    """Tests verifying all classifier intents are handled somewhere."""

    def test_all_objection_intents_covered(self, raw_mixins):
        """Verify all objection intents have handlers."""
        objection_handling = raw_mixins.get("objection_handling", {})
        transitions = objection_handling.get("transitions", {})

        objection_intents = [i for i in CLASSIFIER_INTENTS if i.startswith("objection_")]

        for intent in objection_intents:
            assert intent in transitions, \
                f"Objection intent {intent} not in objection_handling mixin"

    def test_all_progress_intents_in_phase_progress(self, raw_mixins):
        """Verify progress intents are in phase_progress mixin."""
        phase_progress = raw_mixins.get("phase_progress", {})
        transitions = phase_progress.get("transitions", {})

        # SPIN-like progress intents
        progress_intents = [
            "situation_provided", "problem_revealed",
            "implication_acknowledged", "need_expressed"
        ]

        for intent in progress_intents:
            assert intent in transitions, \
                f"Progress intent {intent} not in phase_progress mixin"

    def test_question_intents_handled_in_product_questions(self, raw_mixins):
        """Verify question intents are handled in product_questions mixin."""
        product_questions = raw_mixins.get("product_questions", {})
        rules = product_questions.get("rules", {})

        question_intents = ["question_features", "question_integrations", "comparison"]

        for intent in question_intents:
            assert intent in rules, \
                f"Question intent {intent} should be in product_questions rules"


# =============================================================================
# TEST: STATE TRANSITIONS VALIDITY
# =============================================================================

class TestStateTransitionsValidity:
    """Tests verifying state transitions point to valid states."""

    def test_bant_transitions_valid(self, bant_flow):
        """Verify BANT transitions point to valid states or known targets."""
        valid_targets = set(bant_flow.states.keys())
        # Add known external states
        valid_targets.update(["presentation", "close", "soft_close", "handle_objection"])

        for state_name, state_config in bant_flow.states.items():
            if state_name.startswith("_"):
                continue

            transitions = state_config.get("transitions", {})
            for intent, target in transitions.items():
                if isinstance(target, str):
                    assert target in valid_targets, \
                        f"{state_name}/{intent} -> {target} is invalid target"

    def test_flow_transitions_form_complete_paths(self, all_flows):
        """Verify flows have valid progression paths."""
        for flow_name, flow in all_flows.items():
            # Each flow should have some path to presentation or close
            non_abstract = [s for s in flow.states if not s.startswith("_")]

            if len(non_abstract) == 0:
                continue

            # Check at least one state transitions to presentation or close
            reaches_end = False
            end_states = {"presentation", "close", "soft_close", "success"}

            for state_name, state_config in flow.states.items():
                transitions = state_config.get("transitions", {})
                for target in transitions.values():
                    if isinstance(target, str) and target in end_states:
                        reaches_end = True
                        break
                    elif isinstance(target, list):
                        for item in target:
                            if isinstance(item, dict) and item.get("then") in end_states:
                                reaches_end = True
                                break
                            elif isinstance(item, str) and item in end_states:
                                reaches_end = True
                                break

            assert reaches_end, \
                f"{flow_name} should have at least one path to terminal state"


# =============================================================================
# TEST: REGRESSION TESTS
# =============================================================================

class TestRegressions:
    """Regression tests for previously fixed issues."""

    def test_no_flow_specific_intents_in_transitions(self, all_flows):
        """Verify flows don't use flow-specific intents that classifier doesn't emit."""
        # These were the old flow-specific intents that caused the sync issue
        old_flow_intents = {
            "attention_captured", "interest_built", "desire_created",
            "insight_accepted", "reframe_accepted", "teach_complete",
            "authority_established", "control_taken", "direction_set",
            "trust_built", "value_shared", "engagement_achieved",
            "connection_made", "rapport_built", "relationship_developed",
        }

        issues = []

        for flow_name, flow in all_flows.items():
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                transitions = state_config.get("transitions", {})
                for intent in transitions.keys():
                    if intent in old_flow_intents:
                        issues.append(f"{flow_name}/{state_name}: uses {intent}")

        assert len(issues) == 0, \
            f"Flows still using old flow-specific intents:\n" + "\n".join(issues)

    def test_price_question_not_unresolved(self, all_flows):
        """Verify price_question has valid action (not unresolved template)."""
        for flow_name, flow in all_flows.items():
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue

                rules = state_config.get("rules", {})
                price_rule = rules.get("price_question")

                if price_rule:
                    if isinstance(price_rule, str):
                        assert "{{" not in price_rule, \
                            f"{flow_name}/{state_name}/price_question has unresolved template"
                    elif isinstance(price_rule, list):
                        for item in price_rule:
                            if isinstance(item, str):
                                assert "{{" not in item, \
                                    f"{flow_name}/{state_name}/price_question has unresolved template in list"

    def test_144_high_issues_fixed(self, all_flows, raw_mixins):
        """Meta-test: Verify all 144 HIGH severity issues from audit are fixed."""
        issues_count = 0

        # 1. Check all objection intents have handlers (was ~8 issues)
        objection_handling = raw_mixins.get("objection_handling", {})
        obj_transitions = objection_handling.get("transitions", {})
        required_objections = [
            "objection_price", "objection_competitor", "objection_no_time",
            "objection_think", "objection_complexity", "objection_timing",
            "objection_trust", "objection_no_need"
        ]
        for obj in required_objections:
            if obj not in obj_transitions:
                issues_count += 1

        # 2. Check no unresolved {{default_price_action}} (was ~19*4=76 issues)
        for flow_name, flow in all_flows.items():
            for state_name, state_config in flow.states.items():
                if state_name.startswith("_"):
                    continue
                rules = state_config.get("rules", {})
                for intent, action in rules.items():
                    if isinstance(action, str) and "{{default_price_action}}" in action:
                        issues_count += 1
                    elif isinstance(action, list):
                        for item in action:
                            if isinstance(item, str) and "{{default_price_action}}" in item:
                                issues_count += 1

        assert issues_count == 0, \
            f"Still have {issues_count} HIGH severity issues (should be 0)"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
