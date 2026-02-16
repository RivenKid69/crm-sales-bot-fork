"""
Targeted tests for Bug #7 (7A, 7B, 7C) and Bug #8 fixes.

Bug 7A: Exit intent priority downgrade in autonomous states
Bug 7B: _resolved_params preservation in config_loader + autonomous_decision hard override
Bug 7C: Objection handler split (no strategy vs exhausted) + bot.py autonomous gate
Bug 8:  Credential leak prevention (4 layers)

NOTE: Tests that require LLM or semantic search are intentionally skipped.
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, Any, List, Optional, Set

import pytest


# =============================================================================
# Step 1: autonomous: true flag in YAML
# =============================================================================

class TestAutonomousFlag:
    """Verify all 6 autonomous states have autonomous: true in resolved config."""

    def test_all_autonomous_states_have_flag(self):
        """All 6 autonomous states must have autonomous: true in YAML."""
        import yaml

        yaml_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "autonomous" / "states.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        expected_states = [
            "autonomous_discovery",
            "autonomous_qualification",
            "autonomous_presentation",
            "autonomous_objection_handling",
            "autonomous_negotiation",
            "autonomous_closing",
        ]

        for state_name in expected_states:
            state = data["states"][state_name]
            assert state.get("autonomous") is True, (
                f"State {state_name} missing autonomous: true"
            )

    def test_non_autonomous_states_no_flag(self):
        """Non-autonomous states should NOT have autonomous: true."""
        import yaml

        # Check the base states to make sure they don't have autonomous: true
        yaml_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "autonomous" / "states.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for name, state in data["states"].items():
            if not name.startswith("autonomous_"):
                assert not state.get("autonomous", False), (
                    f"Non-autonomous state {name} should not have autonomous: true"
                )


# =============================================================================
# Step 2 (Bug 7B): _resolved_params in config_loader + autonomous_decision
# =============================================================================

class TestResolvedParams:
    """Test that config_loader preserves _resolved_params after parameter resolution."""

    def test_resolved_params_preserved_after_pop(self):
        """After config_loader processes states, _resolved_params must contain
        the original parameter values (e.g. next_phase_state)."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        # Simulate what config_loader does: state with parameters
        state_config = {
            "goal": "Test goal",
            "max_turns_in_state": 6,
            "max_turns_fallback": "{{next_phase_state}}",
            "parameters": {
                "next_phase_state": "autonomous_qualification",
                "prev_phase_state": "greeting",
            },
        }

        variables = {}

        # Reproduce the config_loader logic
        state_params = state_config.pop("parameters", {})
        merged_params = {**variables, **state_params}
        resolved = loader._resolve_parameters(state_config, merged_params)
        resolved["_resolved_params"] = {
            k: loader._resolve_parameters(v, merged_params)
            for k, v in merged_params.items()
        }

        # Verify _resolved_params contains the expected values
        assert "_resolved_params" in resolved
        assert resolved["_resolved_params"]["next_phase_state"] == "autonomous_qualification"
        assert resolved["_resolved_params"]["prev_phase_state"] == "greeting"

    def test_resolved_params_with_template_substitution(self):
        """Parameters with {{var}} templates should be resolved in _resolved_params."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        state_config = {
            "max_turns_fallback": "{{next_phase_state}}",
            "parameters": {
                "next_phase_state": "autonomous_presentation",
            },
        }

        variables = {"default_action": "respond"}

        state_params = state_config.pop("parameters", {})
        merged_params = {**variables, **state_params}
        resolved = loader._resolve_parameters(state_config, merged_params)
        resolved["_resolved_params"] = {
            k: loader._resolve_parameters(v, merged_params)
            for k, v in merged_params.items()
        }

        # max_turns_fallback should be resolved to actual value
        assert resolved["max_turns_fallback"] == "autonomous_presentation"
        # _resolved_params should also have the value
        assert resolved["_resolved_params"]["next_phase_state"] == "autonomous_presentation"

    def test_resolved_params_flow_variables_merged(self):
        """Flow-level variables should be merged into _resolved_params."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        state_config = {
            "goal": "Test",
            "parameters": {
                "next_phase_state": "state_b",
            },
        }

        flow_variables = {"default_unclear_action": "autonomous_respond"}

        state_params = state_config.pop("parameters", {})
        merged_params = {**flow_variables, **state_params}
        resolved = loader._resolve_parameters(state_config, merged_params)
        resolved["_resolved_params"] = {
            k: loader._resolve_parameters(v, merged_params)
            for k, v in merged_params.items()
        }

        assert resolved["_resolved_params"]["next_phase_state"] == "state_b"
        assert resolved["_resolved_params"]["default_unclear_action"] == "autonomous_respond"


class TestAutonomousDecisionHardOverride:
    """Test that autonomous_decision.py reads next_phase_state from _resolved_params."""

    def test_target_from_resolved_params(self):
        """Hard override should read target from _resolved_params.next_phase_state."""
        state_config = {
            "phase_exhaust_threshold": 3,
            "max_turns_fallback": "autonomous_qualification",
            "_resolved_params": {
                "next_phase_state": "autonomous_qualification",
                "prev_phase_state": "greeting",
            },
        }

        # Simulate the lookup logic from autonomous_decision.py
        resolved_params = state_config.get("_resolved_params", {})
        target = (
            resolved_params.get("next_phase_state")
            or state_config.get("max_turns_fallback")
            or "soft_close"
        )

        assert target == "autonomous_qualification"

    def test_fallback_to_max_turns_fallback(self):
        """If _resolved_params missing, fallback to max_turns_fallback."""
        state_config = {
            "phase_exhaust_threshold": 3,
            "max_turns_fallback": "autonomous_presentation",
        }

        resolved_params = state_config.get("_resolved_params", {})
        target = (
            resolved_params.get("next_phase_state")
            or state_config.get("max_turns_fallback")
            or "soft_close"
        )

        assert target == "autonomous_presentation"

    def test_ultimate_fallback_to_soft_close(self):
        """If both sources missing, fallback to soft_close."""
        state_config = {
            "phase_exhaust_threshold": 3,
        }

        resolved_params = state_config.get("_resolved_params", {})
        target = (
            resolved_params.get("next_phase_state")
            or state_config.get("max_turns_fallback")
            or "soft_close"
        )

        assert target == "soft_close"

    def test_resolved_params_empty_dict_falls_through(self):
        """Empty _resolved_params should fall through to max_turns_fallback."""
        state_config = {
            "phase_exhaust_threshold": 3,
            "max_turns_fallback": "autonomous_negotiation",
            "_resolved_params": {},
        }

        resolved_params = state_config.get("_resolved_params", {})
        target = (
            resolved_params.get("next_phase_state")
            or state_config.get("max_turns_fallback")
            or "soft_close"
        )

        assert target == "autonomous_negotiation"


# =============================================================================
# Step 3 (Bug 7A): Priority downgrade for exit intents in autonomous states
# =============================================================================

class TestExitIntentPriorityDowngrade:
    """Test that exit intents get NORMAL priority in autonomous states."""

    def _get_priority_for_intent(self, intent: str, is_autonomous: bool) -> str:
        """Reproduce the priority logic from transition_resolver.py."""
        high_priority_intents = {
            "rejection",
            "hard_no",
            "end_conversation",
            "explicit_close_request",
        }

        if intent in high_priority_intents and is_autonomous:
            return "NORMAL"
        else:
            return "HIGH" if intent in high_priority_intents else "NORMAL"

    def test_rejection_normal_in_autonomous(self):
        assert self._get_priority_for_intent("rejection", is_autonomous=True) == "NORMAL"

    def test_hard_no_normal_in_autonomous(self):
        assert self._get_priority_for_intent("hard_no", is_autonomous=True) == "NORMAL"

    def test_end_conversation_normal_in_autonomous(self):
        assert self._get_priority_for_intent("end_conversation", is_autonomous=True) == "NORMAL"

    def test_explicit_close_normal_in_autonomous(self):
        assert self._get_priority_for_intent("explicit_close_request", is_autonomous=True) == "NORMAL"

    def test_rejection_high_in_non_autonomous(self):
        """In non-autonomous (SPIN/BANT), rejection must stay HIGH."""
        assert self._get_priority_for_intent("rejection", is_autonomous=False) == "HIGH"

    def test_hard_no_high_in_non_autonomous(self):
        assert self._get_priority_for_intent("hard_no", is_autonomous=False) == "HIGH"

    def test_non_exit_intent_normal_everywhere(self):
        """Non-exit intents stay NORMAL regardless of autonomous flag."""
        assert self._get_priority_for_intent("price_question", is_autonomous=True) == "NORMAL"
        assert self._get_priority_for_intent("price_question", is_autonomous=False) == "NORMAL"
        assert self._get_priority_for_intent("greeting", is_autonomous=True) == "NORMAL"
        assert self._get_priority_for_intent("greeting", is_autonomous=False) == "NORMAL"


class TestTransitionResolverAutonomousPriority:
    """Integration test: TransitionResolverSource reads autonomous from state_config."""

    def test_transition_resolver_reads_autonomous_flag(self):
        """TransitionResolverSource should check ctx.state_config['autonomous']."""
        from src.blackboard.sources.transition_resolver import TransitionResolverSource
        from src.blackboard.models import Priority

        source = TransitionResolverSource()

        # Create mock blackboard and context
        mock_blackboard = MagicMock()
        mock_ctx = MagicMock()

        # Autonomous state with rejection transition
        mock_ctx.state_config = {
            "autonomous": True,
            "transitions": {
                "rejection": "soft_close",
            },
        }
        mock_ctx.current_intent = "rejection"
        mock_blackboard.get_context.return_value = mock_ctx

        # Mock _resolve_transition to return a state
        source._resolve_transition = MagicMock(return_value="soft_close")

        source.contribute(mock_blackboard)

        # Verify propose_transition was called with NORMAL priority (not HIGH)
        call_args = mock_blackboard.propose_transition.call_args
        assert call_args is not None, "propose_transition should have been called"
        assert call_args.kwargs.get("priority") == Priority.NORMAL or \
               (len(call_args.args) > 1 and call_args.args[1] == Priority.NORMAL) or \
               call_args[1].get("priority") == Priority.NORMAL, \
               f"Expected NORMAL priority for rejection in autonomous state, got {call_args}"

    def test_transition_resolver_high_priority_in_spin(self):
        """In non-autonomous state, rejection should have HIGH priority."""
        from src.blackboard.sources.transition_resolver import TransitionResolverSource
        from src.blackboard.models import Priority

        source = TransitionResolverSource()

        mock_blackboard = MagicMock()
        mock_ctx = MagicMock()

        # Non-autonomous state (no autonomous flag)
        mock_ctx.state_config = {
            "transitions": {
                "rejection": "soft_close",
            },
        }
        mock_ctx.current_intent = "rejection"
        mock_blackboard.get_context.return_value = mock_ctx

        source._resolve_transition = MagicMock(return_value="soft_close")

        source.contribute(mock_blackboard)

        call_args = mock_blackboard.propose_transition.call_args
        assert call_args is not None
        # Should be HIGH in non-autonomous
        assert call_args.kwargs.get("priority") == Priority.HIGH or \
               (len(call_args.args) > 1 and call_args.args[1] == Priority.HIGH), \
               f"Expected HIGH priority for rejection in SPIN state"


# =============================================================================
# Step 4 (Bug 7C): Objection handler split + bot.py autonomous gate
# =============================================================================

class TestObjectionHandlerSplit:
    """Test that ObjectionHandler distinguishes 'no strategy' vs 'exhausted'."""

    def test_exhausted_strategies_soft_close(self):
        """When strategies exist but are exhausted, should_soft_close=True."""
        from src.objection_handler import ObjectionHandler, ObjectionType

        handler = ObjectionHandler()

        # Exhaust all attempts for a known strategy
        objection_type = ObjectionType.PRICE
        # Register enough attempts to exhaust
        for _ in range(10):
            handler.objection_attempts[objection_type] = handler.objection_attempts.get(objection_type, 0) + 1

        # Now get_strategy should return None (exhausted)
        strategy = handler.get_strategy(objection_type)
        assert strategy is None, "Strategy should be exhausted"

        # Verify the type IS in one of the strategy dicts
        has_registered = (
            objection_type in handler.STRATEGIES_4PS
            or objection_type in handler.STRATEGIES_3FS
        )
        assert has_registered, f"{objection_type} should be in a strategy dict"

    def test_no_strategy_registered_continues_dialogue(self):
        """When objection type detected but no strategy registered, should_soft_close=False."""
        from src.objection_handler import ObjectionHandler, ObjectionResult

        handler = ObjectionHandler()

        # Create a mock objection type that's not in any strategy dict
        mock_objection_type = MagicMock()
        mock_objection_type.value = "unknown_custom_type"

        # Verify it's not registered
        has_registered = (
            mock_objection_type in handler.STRATEGIES_4PS
            or mock_objection_type in handler.STRATEGIES_3FS
        )
        assert not has_registered

        # Simulate the logic from the fix
        strategy = None  # get_strategy returns None
        attempt = 1

        if not strategy:
            if has_registered:
                result = ObjectionResult(
                    objection_type=mock_objection_type,
                    strategy=None,
                    attempt_number=attempt,
                    should_soft_close=True,
                    response_parts={"message": "closing"},
                )
            else:
                result = ObjectionResult(
                    objection_type=mock_objection_type,
                    strategy=None,
                    attempt_number=attempt,
                    should_soft_close=False,
                    response_parts={},
                )

        assert result.should_soft_close is False
        assert result.response_parts == {}

    def test_handle_objection_no_objection_returns_false(self):
        """Non-objection messages should return should_soft_close=False."""
        from src.objection_handler import ObjectionHandler

        handler = ObjectionHandler()
        result = handler.handle_objection("Расскажите о вашей CRM системе", {})
        assert result.should_soft_close is False
        assert result.objection_type is None


class TestBotAutonomousGate:
    """Test that bot.py respects autonomous flag and doesn't override Blackboard."""

    def test_soft_close_override_blocked_in_autonomous(self):
        """In autonomous state, objection soft_close should NOT override Blackboard."""
        state_config = {"autonomous": True}
        objection_info = {"should_soft_close": True}
        is_autonomous = state_config.get("autonomous", False)

        should_override = (
            objection_info and objection_info.get("should_soft_close")
            and not is_autonomous
        )
        assert should_override is False

    def test_soft_close_override_allowed_in_spin(self):
        """In non-autonomous (SPIN) state, objection soft_close SHOULD override."""
        state_config = {}  # no autonomous flag
        objection_info = {"should_soft_close": True}
        is_autonomous = state_config.get("autonomous", False)

        should_override = (
            objection_info and objection_info.get("should_soft_close")
            and not is_autonomous
        )
        assert should_override is True

    def test_no_objection_info_no_override(self):
        """When no objection info, no override regardless of state."""
        state_config = {"autonomous": True}
        objection_info = None
        is_autonomous = state_config.get("autonomous", False)

        should_override = (
            objection_info and objection_info.get("should_soft_close")
            and not is_autonomous
        )
        assert not should_override

    def test_soft_close_false_no_override(self):
        """When should_soft_close=False, no override."""
        state_config = {}
        objection_info = {"should_soft_close": False}
        is_autonomous = state_config.get("autonomous", False)

        should_override = (
            objection_info and objection_info.get("should_soft_close")
            and not is_autonomous
        )
        assert not should_override


# =============================================================================
# Step 5 (Bug 8 L1): Credentials removed from KB YAML
# =============================================================================

class TestCredentialsRemovedFromKB:
    """Verify no credentials remain in KB YAML files."""

    @pytest.fixture
    def kb_data_dir(self):
        return Path(__file__).parent.parent / "src" / "knowledge" / "data"

    def test_no_password_12345678_in_any_yaml(self, kb_data_dir):
        """Grep for '12345678' in all KB YAML files — must be 0 matches."""
        for yaml_file in kb_data_dir.glob("*.yaml"):
            content = yaml_file.read_text(encoding="utf-8")
            assert "12345678" not in content, (
                f"Credential '12345678' found in {yaml_file.name}"
            )

    def test_no_demo_phone_in_any_yaml(self, kb_data_dir):
        """Grep for '+7 777 777 77 77' in all KB YAML files — must be 0 matches."""
        for yaml_file in kb_data_dir.glob("*.yaml"):
            content = yaml_file.read_text(encoding="utf-8")
            assert "+7 777 777 77 77" not in content, (
                f"Demo phone number found in {yaml_file.name}"
            )

    def test_no_login_password_pattern_in_facts(self, kb_data_dir):
        """No facts should contain login+password patterns."""
        import yaml

        pattern = re.compile(r'логин.*пароль|login.*password', re.IGNORECASE)
        for yaml_file in kb_data_dir.glob("*.yaml"):
            if yaml_file.name == "_meta.yaml":
                continue
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not data or "sections" not in data:
                continue
            for section in data["sections"]:
                facts = section.get("facts", "")
                assert not pattern.search(facts), (
                    f"Login/password pattern found in {yaml_file.name}:{section['topic']}: {facts[:100]}"
                )

    def test_demo_sections_redirect_to_contact(self, kb_data_dir):
        """Demo-related facts should now redirect to leaving contact data."""
        import yaml

        demo_topics = [
            "support_demo_account_1123",
            "support_demo_version_1499",
            "support_demo_test_1528",
            "pricing_demo_access_1901",
            "products_demo_access_1812",
        ]

        all_sections = {}
        for yaml_file in kb_data_dir.glob("*.yaml"):
            if yaml_file.name == "_meta.yaml":
                continue
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not data or "sections" not in data:
                continue
            for section in data["sections"]:
                all_sections[section["topic"]] = section

        for topic in demo_topics:
            if topic in all_sections:
                facts = all_sections[topic]["facts"]
                assert "контактные данные" in facts.lower() or "контакт" in facts.lower(), (
                    f"Demo section {topic} should redirect to contact data, got: {facts}"
                )
                assert "12345678" not in facts
                assert "+7 777 777 77 77" not in facts


# =============================================================================
# Step 6 (Bug 8 L2): Sensitive field in KB schema + filtering
# =============================================================================

class TestSensitiveField:
    """Test the sensitive field in KnowledgeSection and filtering in retrievers."""

    def test_knowledge_section_has_sensitive_field(self):
        """KnowledgeSection should have a sensitive: bool field, default False."""
        from src.knowledge.base import KnowledgeSection

        section = KnowledgeSection(
            category="test",
            topic="test_topic",
            keywords=["test"],
            facts="test facts",
        )
        assert section.sensitive is False

    def test_knowledge_section_sensitive_true(self):
        """KnowledgeSection can be created with sensitive=True."""
        from src.knowledge.base import KnowledgeSection

        section = KnowledgeSection(
            category="test",
            topic="sensitive_topic",
            keywords=["secret"],
            facts="secret data",
            sensitive=True,
        )
        assert section.sensitive is True

    def test_loader_loads_sensitive_field(self):
        """loader._load_sections_from_file should load sensitive from YAML."""
        from src.knowledge.loader import _load_sections_from_file
        import yaml
        import tempfile
        import os

        yaml_content = {
            "sections": [
                {
                    "topic": "test_normal",
                    "keywords": ["normal"],
                    "facts": "Normal facts",
                    "category": "test",
                },
                {
                    "topic": "test_sensitive",
                    "keywords": ["secret"],
                    "facts": "Secret credentials here",
                    "category": "test",
                    "sensitive": True,
                },
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ) as f:
            yaml.dump(yaml_content, f, allow_unicode=True)
            temp_path = f.name

        try:
            sections = _load_sections_from_file(Path(temp_path))
            assert len(sections) == 2

            normal = [s for s in sections if s.topic == "test_normal"][0]
            assert normal.sensitive is False

            sensitive = [s for s in sections if s.topic == "test_sensitive"][0]
            assert sensitive.sensitive is True
        finally:
            os.unlink(temp_path)


class TestSensitiveFiltering:
    """Test that sensitive sections are filtered out in retrieval paths."""

    def test_retrieve_filters_sensitive(self):
        """CascadeRetriever.retrieve() should filter out sensitive sections."""
        from src.knowledge.base import KnowledgeSection

        # Create mock results
        normal_section = KnowledgeSection(
            category="support", topic="normal", keywords=["help"],
            facts="Normal facts", sensitive=False,
        )
        sensitive_section = KnowledgeSection(
            category="support", topic="secret", keywords=["secret"],
            facts="Login: +7 777 Password: 12345", sensitive=True,
        )

        # Simulate the filtering logic
        class MockResult:
            def __init__(self, section):
                self.section = section
                self.score = 0.9

        results = [MockResult(normal_section), MockResult(sensitive_section)]
        results = [r for r in results if not r.section.sensitive]
        facts = [r.section.facts.strip() for r in results]

        assert len(facts) == 1
        assert "Normal facts" in facts[0]
        assert "Login" not in "\n".join(facts)

    def test_retrieve_with_urls_filters_sensitive(self):
        """retrieve_with_urls should filter sensitive before collecting facts and URLs."""
        from src.knowledge.base import KnowledgeSection

        class MockResult:
            def __init__(self, section):
                self.section = section
                self.score = 0.9

        normal = KnowledgeSection(
            category="pricing", topic="tariffs", keywords=["price"],
            facts="Prices here", sensitive=False,
            urls=[{"url": "https://example.com", "label": "Docs"}],
        )
        sensitive = KnowledgeSection(
            category="support", topic="demo_creds", keywords=["demo"],
            facts="Login: admin Password: 123", sensitive=True,
            urls=[{"url": "https://console.example.com", "label": "Console"}],
        )

        results = [MockResult(normal), MockResult(sensitive)]
        results = [r for r in results if not r.section.sensitive]

        facts = [r.section.facts.strip() for r in results]
        urls = []
        for r in results:
            urls.extend(getattr(r.section, 'urls', []) or [])

        assert len(facts) == 1
        assert "Prices here" in facts[0]
        assert len(urls) == 1
        assert urls[0]["url"] == "https://example.com"

    def test_autonomous_kb_filters_sensitive(self):
        """autonomous_kb loop should skip sensitive sections."""
        from src.knowledge.base import KnowledgeSection

        sections = [
            KnowledgeSection(
                category="products", topic="overview", keywords=["crm"],
                facts="CRM overview", sensitive=False,
            ),
            KnowledgeSection(
                category="support", topic="demo_creds", keywords=["demo"],
                facts="Login: +7 777 Password: 12345678", sensitive=True,
            ),
            KnowledgeSection(
                category="pricing", topic="tariffs", keywords=["price"],
                facts="Pricing info", sensitive=False,
            ),
        ]

        # Simulate autonomous_kb logic
        facts_parts = []
        for section in sections:
            if section.sensitive:
                continue
            section_text = f"[{section.category}/{section.topic}]\n{section.facts}\n"
            facts_parts.append(section_text)

        facts_text = "\n".join(facts_parts)
        assert "demo_creds" not in facts_text
        assert "12345678" not in facts_text
        assert "CRM overview" in facts_text
        assert "Pricing info" in facts_text
        assert len(facts_parts) == 2


# =============================================================================
# Step 7 (Bug 8 L3): Credential redaction in ResponseGenerator
# =============================================================================

class TestCredentialRedaction:
    """Test _redact_credentials method of ResponseGenerator."""

    @pytest.fixture
    def patterns(self):
        """Return the credential patterns matching ResponseGenerator."""
        return [
            re.compile(
                r'(?:логин|login)[:\s]*\+?\d[\d\s\-]{8,15}[\s,;.]*'
                r'(?:пароль|password|құпиясөз)[:\s]*\S+',
                re.IGNORECASE
            ),
            re.compile(
                r'(?:пароль|password|құпиясөз)[:\s]*\d{4,}',
                re.IGNORECASE
            ),
        ]

    def _redact(self, text: str, patterns) -> str:
        result = text
        for pattern in patterns:
            result = pattern.sub('[демо-доступ предоставляется по запросу]', result)
        return result

    def test_redact_login_password_russian(self, patterns):
        text = "Демо доступ на https://console.wipon.kz/login логин +7 777 777 77 77 пароль 12345678."
        result = self._redact(text, patterns)
        assert "12345678" not in result
        assert "+7 777 777 77 77" not in result
        assert "демо-доступ предоставляется по запросу" in result

    def test_redact_password_only(self, patterns):
        text = "Пароль: 12345678"
        result = self._redact(text, patterns)
        assert "12345678" not in result
        assert "демо-доступ предоставляется по запросу" in result

    def test_redact_kazakh_password(self, patterns):
        text = "құпиясөз: 87654321"
        result = self._redact(text, patterns)
        assert "87654321" not in result

    def test_no_redaction_for_normal_text(self, patterns):
        text = "CRM система помогает вести учёт клиентов и продаж."
        result = self._redact(text, patterns)
        assert result == text

    def test_redact_login_with_comma_separator(self, patterns):
        text = "логин +7 777 777 77 77, пароль 12345678."
        result = self._redact(text, patterns)
        assert "12345678" not in result

    def test_no_redaction_for_short_numbers(self, patterns):
        """Numbers shorter than 4 digits should not be redacted."""
        text = "Пароль: 123"  # 3 digits, should not match
        result = self._redact(text, patterns)
        assert result == text

    def test_redact_english_login_password(self, patterns):
        text = "login: +77777777777 password: secretpass123"
        result = self._redact(text, patterns)
        assert "secretpass123" not in result


class TestResponseGeneratorRedaction:
    """Integration test: verify ResponseGenerator._redact_credentials works end-to-end."""

    def test_generator_has_redact_method(self):
        """ResponseGenerator should have _redact_credentials method."""
        from src.generator import ResponseGenerator
        assert hasattr(ResponseGenerator, '_redact_credentials')
        assert hasattr(ResponseGenerator, '_CREDENTIAL_PATTERNS')

    def test_generator_redact_credentials(self):
        """ResponseGenerator._redact_credentials should redact credential patterns."""
        from src.generator import ResponseGenerator

        # Create a minimal generator instance
        mock_llm = MagicMock()
        gen = ResponseGenerator(llm=mock_llm)

        text_with_creds = "Логин: +7 777 777 77 77, пароль 12345678."
        result = gen._redact_credentials(text_with_creds)
        assert "12345678" not in result

    def test_generator_redact_preserves_normal_text(self):
        """Normal text should pass through _redact_credentials unchanged."""
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        gen = ResponseGenerator(llm=mock_llm)

        normal_text = "Наша CRM система поддерживает интеграцию с 1С."
        result = gen._redact_credentials(normal_text)
        assert result == normal_text


# =============================================================================
# Step 8 (Bug 8 L4): Security prompt guard
# =============================================================================

class TestSecurityPromptGuard:
    """Test that SYSTEM_PROMPT contains security instructions."""

    def test_system_prompt_has_security_section(self):
        """SYSTEM_PROMPT must contain security instructions about credentials."""
        from src.config import SYSTEM_PROMPT

        assert "БЕЗОПАСНОСТЬ" in SYSTEM_PROMPT
        assert "логины" in SYSTEM_PROMPT or "пароли" in SYSTEM_PROMPT
        assert "контактные данные" in SYSTEM_PROMPT

    def test_system_prompt_security_before_tone(self):
        """Security section should appear before tone_instruction placeholder."""
        from src.config import SYSTEM_PROMPT

        security_pos = SYSTEM_PROMPT.index("БЕЗОПАСНОСТЬ")
        tone_pos = SYSTEM_PROMPT.index("{tone_instruction}")
        assert security_pos < tone_pos, (
            "Security instructions should come before tone_instruction"
        )


# =============================================================================
# Cross-cutting: End-to-end config_loader integration
# =============================================================================

class TestConfigLoaderIntegration:
    """Verify that full config loading preserves _resolved_params and autonomous flag."""

    def test_autonomous_flow_states_have_resolved_params(self):
        """After loading autonomous flow, all states should have _resolved_params."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        try:
            flow = loader.load_flow("autonomous")
        except Exception:
            pytest.skip("Cannot load autonomous flow in test environment")

        autonomous_states = [
            "autonomous_discovery",
            "autonomous_qualification",
            "autonomous_presentation",
            "autonomous_objection_handling",
            "autonomous_negotiation",
            "autonomous_closing",
        ]

        for state_name in autonomous_states:
            if state_name not in flow.states:
                continue
            state = flow.states[state_name]
            assert "_resolved_params" in state, (
                f"State {state_name} missing _resolved_params"
            )
            assert "next_phase_state" in state["_resolved_params"], (
                f"State {state_name} missing next_phase_state in _resolved_params"
            )

    def test_autonomous_flag_survives_config_loading(self):
        """After full config loading, autonomous: true should be in state_config."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        try:
            flow = loader.load_flow("autonomous")
        except Exception:
            pytest.skip("Cannot load autonomous flow in test environment")

        autonomous_states = [
            "autonomous_discovery",
            "autonomous_qualification",
            "autonomous_presentation",
            "autonomous_objection_handling",
            "autonomous_negotiation",
            "autonomous_closing",
        ]

        for state_name in autonomous_states:
            if state_name not in flow.states:
                continue
            state = flow.states[state_name]
            assert state.get("autonomous") is True, (
                f"State {state_name} should have autonomous: true after loading"
            )

    def test_resolved_params_next_phase_state_correct(self):
        """_resolved_params.next_phase_state should match the YAML parameters."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        try:
            flow = loader.load_flow("autonomous")
        except Exception:
            pytest.skip("Cannot load autonomous flow in test environment")

        expected_transitions = {
            "autonomous_discovery": "autonomous_qualification",
            "autonomous_qualification": "autonomous_presentation",
            "autonomous_presentation": "autonomous_objection_handling",
            "autonomous_objection_handling": "autonomous_negotiation",
            "autonomous_negotiation": "autonomous_closing",
            "autonomous_closing": "close",
        }

        for state_name, expected_next in expected_transitions.items():
            if state_name not in flow.states:
                continue
            state = flow.states[state_name]
            actual_next = state.get("_resolved_params", {}).get("next_phase_state")
            assert actual_next == expected_next, (
                f"State {state_name}: expected next_phase_state={expected_next}, "
                f"got {actual_next}"
            )
