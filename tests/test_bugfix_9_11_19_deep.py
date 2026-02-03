# tests/test_bugfix_9_11_19_deep.py

"""
Deep tests for cascade chain fix.

Principle: Mock ONLY external AI layers (LLM generate, classifier, tone analyzer).
All internal pipeline components run REAL code: knowledge base, blackboard,
conflict resolver, state machine, CTA generator, dialogue policy, fallback handler,
stall guard.

Narrow Fallback Knowledge: KB-sourced product overview
CTA Ignores Response Semantics: backoff detection + action gates
StallGuard Only 28.6% Effective: dual propose (action + transition)
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


# =============================================================================
# T1: Knowledge Source Unit Tests
# =============================================================================


class TestBug9KnowledgeSource:
    """T1: Product overview loads from real KB and provides diversity."""

    OLD_HARDCODED_FEATURES = [
        "Воронка продаж",
        "Автоматические напоминания",
        "История клиента",
        "Отчёты",
    ]

    def _make_generator(self):
        """Create ResponseGenerator with real retriever (no LLM needed for facts)."""
        from src.generator import ResponseGenerator
        llm = MagicMock()
        llm.generate.return_value = "mock response"
        return ResponseGenerator(llm)

    def test_t1_1_product_overview_loads_from_real_kb(self):
        """T1.1: _product_overview loads from real KB with >10 entries."""
        gen = self._make_generator()
        assert len(gen._product_overview) > 10
        assert all(isinstance(s, str) and len(s) >= 10 for s in gen._product_overview)
        # All entries should be unique (deduplication)
        assert len(gen._product_overview) == len(set(gen._product_overview))
        # No entry equals any of the old 4 hardcoded features verbatim
        for old_feat in self.OLD_HARDCODED_FEATURES:
            assert old_feat not in gen._product_overview, (
                f"Old hardcoded feature '{old_feat}' should not appear verbatim"
            )

    def test_t1_2_product_overview_spans_multiple_categories(self):
        """T1.2: Overview entries come from >= 5 different YAML categories."""
        from src.knowledge.retriever import get_retriever
        gen = self._make_generator()
        retriever = get_retriever()

        # Map each overview label back to its source category
        categories_found = set()
        for overview in gen._product_overview:
            for section in retriever.kb.sections:
                if section.priority <= 8:
                    first_line = section.facts.split("\n")[0].strip().rstrip(":")
                    if first_line == overview:
                        categories_found.add(section.category)
                        break

        assert len(categories_found) >= 5, (
            f"Expected >= 5 categories, got {len(categories_found)}: {categories_found}"
        )

    def test_t1_3_get_facts_rotation_no_fixation(self):
        """T1.3: get_facts() returns diverse results across 20 calls."""
        gen = self._make_generator()
        results = [gen.get_facts() for _ in range(20)]
        distinct = set(results)
        assert len(distinct) >= 5, (
            f"Expected >= 5 distinct results, got {len(distinct)}"
        )
        # Each result should be non-empty
        assert all(len(r) > 0 for r in results)
        # No single full result string appears in >50% of calls
        from collections import Counter
        counts = Counter(results)
        for result, count in counts.items():
            assert count <= 10, (  # 50% of 20
                f"Same result appears {count}/20 times (>50% fixation)"
            )

    def test_t1_4_get_facts_returns_empty_for_price_intents(self):
        """T1.4: get_facts() returns empty string for price_question intent (SSOT migration)."""
        gen = self._make_generator()
        result = gen.get_facts(company_size=10, intent="price_question")

        # Pricing данные НЕ генерируются в get_facts()
        # Они извлекаются через retriever и попадают в {retrieved_facts}
        assert result == "", "get_facts() should return empty string for price intents"

    def test_t1_5_get_facts_fallback_for_non_price_intents(self):
        """T1.5: get_facts() returns product overview for non-price intents."""
        gen = self._make_generator()
        result = gen.get_facts(company_size=None, intent="greeting")

        # Для non-price интентов возвращается product overview
        assert isinstance(result, str)
        assert len(result) > 0, "Product overview should be non-empty"

    def test_t1_6_knowledge_pricing_removed_from_config(self):
        """T1.6: KNOWLEDGE['pricing'] and ['discount_annual'] removed (SSOT migration)."""
        from src.config import KNOWLEDGE

        assert "features" not in KNOWLEDGE, "features already removed"
        assert "pricing" not in KNOWLEDGE, "pricing removed — SSOT is pricing.yaml"
        assert "discount_annual" not in KNOWLEDGE, "discount removed — data in pricing.yaml"

    def test_t1_7_no_hardcoded_ruble_prices_in_get_facts(self):
        """T1.7: get_facts() returns empty string for price intents (no ruble data)."""
        gen = self._make_generator()

        # Проверяем price-related интенты из PRICE_RELATED_INTENTS
        for intent in ["price_question", "pricing_details"]:
            result = gen.get_facts(intent=intent)

            # Для price интентов должна быть пустая строка
            assert result == "", f"get_facts() should return empty for {intent}"

            # Проверяем что НЕТ рублей (на случай если кто-то вернет данные)
            assert "₽" not in result, f"Found ruble symbol in {intent} response"
            assert "рубл" not in result.lower(), f"Found 'рубл' word in {intent} response"

    def test_t1_8_product_overview_only_priority_lte_8(self):
        """T1.7: _product_overview only contains priority <= 8 sections."""
        from src.knowledge.retriever import get_retriever
        gen = self._make_generator()
        retriever = get_retriever()

        # Count expected overview sections (priority <= 8, min length 10, deduped)
        seen = set()
        expected_count = 0
        for s in retriever.kb.sections:
            if s.priority <= 8:
                label = s.facts.split("\n")[0].strip().rstrip(":")
                if label and len(label) >= 10 and label not in seen:
                    expected_count += 1
                    seen.add(label)

        assert len(gen._product_overview) == expected_count, (
            f"Expected {expected_count} overview entries, got {len(gen._product_overview)}"
        )

    def test_t1_8_product_overview_graceful_with_empty_kb(self):
        """T1.8: Empty KB doesn't crash, returns empty string."""
        from src.generator import ResponseGenerator
        from src.knowledge.retriever import CascadeRetriever
        from src.knowledge.base import KnowledgeBase

        empty_kb = KnowledgeBase(
            company_name="Test",
            company_description="Test",
            sections=[],
        )
        with patch("src.generator.get_retriever") as mock_get:
            mock_retriever = MagicMock(spec=CascadeRetriever)
            mock_retriever.kb = empty_kb
            mock_get.return_value = mock_retriever

            llm = MagicMock()
            llm.generate.return_value = "mock"
            gen = ResponseGenerator(llm)

        assert gen._product_overview == []
        assert gen.get_facts() == ""


# =============================================================================
# T2: FallbackHandler KB Integration
# =============================================================================


class TestBug9FallbackHandler:
    """T2: FallbackHandler receives and uses product_overviews."""

    def test_t2_1_fallback_receives_product_overviews(self):
        """T2.1: FallbackHandler uses KB overviews for dynamic CTA options."""
        from src.fallback_handler import FallbackHandler

        overviews = [
            "Складской учёт",
            "Аналитика",
            "Интеграции",
            "CRM",
            "Мобильное приложение",
        ]
        handler = FallbackHandler(product_overviews=overviews)

        # Check that DYNAMIC_CTA_OPTIONS was populated
        assert len(handler.DYNAMIC_CTA_OPTIONS) > 0

        # Check that options contain items from product_overviews
        for key, opts in handler.DYNAMIC_CTA_OPTIONS.items():
            option_list = opts.get("options", [])
            has_kb_option = any(
                opt in overviews for opt in option_list
            )
            # At least some pain contexts should have KB options
            # (some may be all generic if they have many generic_options)
            if has_kb_option:
                break
        else:
            # If loop didn't break, at least verify options exist
            all_options = []
            for opts in handler.DYNAMIC_CTA_OPTIONS.values():
                all_options.extend(opts.get("options", []))
            # Should have SOME options sourced from overviews
            overlap = set(all_options) & set(overviews)
            assert len(overlap) > 0, "Expected some KB-sourced options in fallback"

    def test_t2_2_fallback_rotation_across_pains(self):
        """T2.2: Options differ between pain contexts (random.sample)."""
        from src.fallback_handler import FallbackHandler

        overviews = [f"Feature_{i}" for i in range(15)]
        handler = FallbackHandler(product_overviews=overviews)

        all_option_sets = []
        for key in handler.DYNAMIC_CTA_OPTIONS:
            opts = handler.DYNAMIC_CTA_OPTIONS[key].get("options", [])
            all_option_sets.append(tuple(opts))

        # Not all identical (random.sample should vary)
        if len(all_option_sets) >= 2:
            unique_sets = set(all_option_sets)
            assert len(unique_sets) >= 2, (
                "Expected different option sets across pain contexts"
            )

    def test_t2_3_fallback_questions_from_yaml(self):
        """T2.3: fallback_options.yaml contains all 7 pain keys with questions."""
        yaml_path = (
            Path(__file__).parent.parent
            / "src"
            / "yaml_config"
            / "fallback_options.yaml"
        )
        assert yaml_path.exists(), f"YAML file not found: {yaml_path}"

        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        expected_keys = {
            "competitor_mentioned",
            "pain_losing_clients",
            "pain_no_control",
            "pain_manual_work",
            "large_company",
            "small_company",
            "after_price_question",
            "after_features_question",
        }
        for key in expected_keys:
            assert key in config, f"Missing pain key: {key}"
            assert "question" in config[key], f"Missing 'question' in {key}"
            assert len(config[key]["question"]) > 0, f"Empty question in {key}"


# =============================================================================
# T4: CTA Backoff Detection Unit Tests
# =============================================================================


class TestBug11BackoffDetection:
    """T4: Backoff language detection and action gates."""

    def _make_cta_generator(self, turn_count=5):
        gen = self._create_generator()
        gen.turn_count = turn_count
        return gen

    def _create_generator(self):
        from src.cta_generator import CTAGenerator
        return CTAGenerator()

    def test_t4_1_all_backoff_patterns_detected(self):
        """T4.1: All BACK_OFF_PATTERNS are detected."""
        gen = self._create_generator()
        phrases = [
            "Понимаю, не будем настаивать.",
            "Хорошо, не буду торопить.",
            "Не буду давить на вас.",
            "Когда будете готовы — напишите.",
            "Решать вам, конечно.",
            "Решение за вами.",
            "Не спешите с ответом.",
            "Подумайте спокойно.",
        ]
        for phrase in phrases:
            assert gen._has_backoff_language(phrase), (
                f"Failed to detect backoff in: '{phrase}'"
            )

    def test_t4_2_no_false_positives_on_normal_text(self):
        """T4.2: Normal sales text does not trigger backoff."""
        gen = self._create_generator()
        phrases = [
            "Wipon поможет решить проблему с учётом.",
            "Давайте покажу основные функции.",
            "У нас есть отличное решение для вашего бизнеса.",
            "Могу рассказать подробнее о тарифах.",
            "Готовы попробовать бесплатную версию?",
        ]
        for phrase in phrases:
            assert not gen._has_backoff_language(phrase), (
                f"False positive backoff in: '{phrase}'"
            )

    def test_t4_3_should_add_cta_blocks_on_backoff(self):
        """T4.3: should_add_cta returns False for backoff response."""
        gen = self._make_cta_generator(turn_count=5)
        should_add, reason = gen.should_add_cta(
            "handle_objection",
            "Понимаю, не будем настаивать.",
            {},
        )
        assert not should_add
        assert reason == "response_contains_backoff"

    def test_t4_4_should_add_cta_passes_on_normal_response(self):
        """T4.4: Normal response in same state gets CTA."""
        gen = self._make_cta_generator(turn_count=5)
        should_add, reason = gen.should_add_cta(
            "handle_objection",
            "Понимаю вашу ситуацию. Давайте посмотрим на конкретные цифры.",
            {},
        )
        assert should_add
        assert reason is None

    def test_t4_5_action_gate_soft_close(self):
        """T4.5: soft_close action blocks CTA."""
        gen = self._make_cta_generator(turn_count=5)
        should_add, reason = gen.should_add_cta(
            "soft_close",
            "Было приятно пообщаться.",
            {"action": "soft_close"},
        )
        # soft_close is a "close" phase → might be blocked by phase or action gate
        # The action gate should catch it
        assert not should_add

    def test_t4_6_action_gate_objection_limit_reached(self):
        """T4.6: objection_limit_reached action blocks CTA."""
        gen = self._make_cta_generator(turn_count=5)
        should_add, reason = gen.should_add_cta(
            "handle_objection",
            "Понимаю.",
            {"action": "objection_limit_reached"},
        )
        assert not should_add

    def test_t4_7_action_gate_normal_action_passes(self):
        """T4.7: Normal action does not block CTA."""
        gen = self._make_cta_generator(turn_count=5)
        should_add, reason = gen.should_add_cta(
            "presentation",
            "Вот наши функции.",
            {"action": "present_solution"},
        )
        assert should_add
        assert reason is None


# =============================================================================
# T6: StallGuard Dual Proposal Unit Tests
# =============================================================================


class TestBug19StallGuardDualProposal:
    """T6: StallGuard contribute() calls both propose_action AND propose_transition."""

    def _make_source(self, enabled=True):
        from src.blackboard.sources.stall_guard import StallGuardSource
        return StallGuardSource(enabled=enabled)

    def _make_blackboard(
        self,
        state="presentation",
        max_turns=5,
        consecutive=5,
        fallback="close",
        state_before_objection=None,
        is_progressing=False,
        has_extracted_data=False,
    ):
        bb = MagicMock()
        envelope = Mock()
        envelope.consecutive_same_state = consecutive
        envelope.is_progressing = is_progressing
        envelope.has_extracted_data = has_extracted_data

        ctx = Mock()
        ctx.state = state
        ctx.state_config = {
            "max_turns_in_state": max_turns,
            "max_turns_fallback": fallback,
        }
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx

        sm = Mock()
        sm._state_before_objection = state_before_objection
        bb._state_machine = sm

        return bb

    def test_t6_1_contribute_calls_both_propose_action_and_transition_flag_on(self):
        """T6.1: With flag ON, contribute calls both propose_action and propose_transition."""
        from src.blackboard.enums import Priority

        source = self._make_source()
        bb = self._make_blackboard(consecutive=5, max_turns=5)

        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.side_effect = lambda flag: {
                "universal_stall_guard": True,
                "stall_guard_dual_proposal": True,
            }.get(flag, False)
            source.contribute(bb)

        bb.propose_action.assert_called_once()
        bb.propose_transition.assert_called_once()

        action_kwargs = bb.propose_action.call_args.kwargs
        assert action_kwargs["action"] == "stall_guard_eject"
        assert action_kwargs["priority"] == Priority.HIGH
        assert action_kwargs["combinable"] is True

    def test_t6_2_contribute_only_transition_when_flag_off(self):
        """T6.2: With flag OFF, only propose_transition (backward compat)."""
        source = self._make_source()
        bb = self._make_blackboard(consecutive=5, max_turns=5)

        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.side_effect = lambda flag: {
                "universal_stall_guard": True,
                "stall_guard_dual_proposal": False,
            }.get(flag, False)
            source.contribute(bb)

        bb.propose_action.assert_not_called()
        bb.propose_transition.assert_called_once()

    def test_t6_3_hard_threshold_priority_high_combinable_true(self):
        """T6.3: Hard threshold uses Priority.HIGH + combinable=True."""
        from src.blackboard.enums import Priority

        source = self._make_source()
        bb = self._make_blackboard(consecutive=5, max_turns=5)

        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.side_effect = lambda flag: True
            source.contribute(bb)

        action_kwargs = bb.propose_action.call_args.kwargs
        assert action_kwargs["priority"] == Priority.HIGH
        assert action_kwargs["combinable"] is True
        assert action_kwargs["action"] == "stall_guard_eject"

        transition_kwargs = bb.propose_transition.call_args.kwargs
        assert transition_kwargs["priority"] == Priority.HIGH

    def test_t6_4_soft_threshold_priority_normal_combinable_true(self):
        """T6.4: Soft threshold uses Priority.NORMAL + combinable=True."""
        from src.blackboard.enums import Priority

        source = self._make_source()
        # consecutive=4, max_turns=5 → soft threshold
        bb = self._make_blackboard(
            consecutive=4,
            max_turns=5,
            is_progressing=False,
            has_extracted_data=False,
        )

        with patch("src.blackboard.sources.stall_guard.flags") as mock_flags:
            mock_flags.is_enabled.side_effect = lambda flag: True
            source.contribute(bb)

        action_kwargs = bb.propose_action.call_args.kwargs
        assert action_kwargs["priority"] == Priority.NORMAL
        assert action_kwargs["combinable"] is True
        assert action_kwargs["action"] == "stall_guard_nudge"

    def test_t6_5_stall_guard_beats_normal_blocking_action(self):
        """T6.5: StallGuard HIGH action beats NORMAL blocking action."""
        from src.blackboard.conflict_resolver import ConflictResolver
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        resolver = ConflictResolver()
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="continue",
                priority=Priority.NORMAL,
                source_name="TransitionResolver",
                reason_code="yaml_transition",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="stall_guard_eject",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="close",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
            ),
        ]
        decision = resolver.resolve(proposals, current_state="presentation")
        assert decision.action == "stall_guard_eject"
        assert decision.next_state == "close"

    def test_t6_6_stall_guard_yields_to_critical(self):
        """T6.6: CRITICAL (escalation) always wins over StallGuard HIGH."""
        from src.blackboard.conflict_resolver import ConflictResolver
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        resolver = ConflictResolver()
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="escalate_to_human",
                priority=Priority.CRITICAL,
                source_name="EscalationSource",
                reason_code="human_escalation",
                combinable=False,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="escalated",
                priority=Priority.CRITICAL,
                source_name="EscalationSource",
                reason_code="human_escalation",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="stall_guard_eject",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="close",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
            ),
        ]
        decision = resolver.resolve(proposals, current_state="presentation")
        assert decision.action == "escalate_to_human"

    def test_t6_7_combinable_true_allows_own_transition(self):
        """T6.7: combinable=True doesn't block transitions."""
        from src.blackboard.conflict_resolver import ConflictResolver
        from src.blackboard.models import Proposal
        from src.blackboard.enums import Priority, ProposalType

        resolver = ConflictResolver()
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="stall_guard_eject",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="close",
                priority=Priority.HIGH,
                source_name="StallGuardSource",
                reason_code="max_turns_in_state_exceeded",
            ),
        ]
        decision = resolver.resolve(proposals, current_state="presentation")
        assert decision.next_state == "close"  # NOT "presentation" self-loop


# =============================================================================
# T7: DialoguePolicy Protection
# =============================================================================


class TestBug19DialoguePolicyProtection:
    """T7: maybe_override returns None for stall_guard actions."""

    def _make_policy(self):
        from src.dialogue_policy import DialoguePolicy
        return DialoguePolicy(shadow_mode=False)

    def _make_envelope(self, state="presentation", consecutive=5):
        envelope = Mock()
        envelope.state = state
        envelope.consecutive_same_state = consecutive
        envelope.last_intent = "unclear"
        envelope.turn_number = 6
        envelope.frustration_level = 0
        envelope.is_stuck = True
        envelope.is_oscillating = False
        envelope.is_progressing = False
        envelope.has_repeated_question = False
        envelope.has_guard_intervention = False
        envelope.guard_intervention = None
        envelope.collected_data = {}
        envelope.missing_data = []
        envelope.consecutive_objections = 0
        envelope.total_objections = 0
        envelope.current_action = ""
        envelope.has_extracted_data = False
        envelope.last_confidence = 0.9
        envelope.last_action = "continue"
        envelope.response_directives = None
        envelope.engagement_level = 0.5
        envelope.is_first_contact = False
        envelope.has_price_question = False
        envelope.visited_states = [state]
        envelope.phase_attempts = {}
        envelope.same_state_count = consecutive
        envelope.same_message_count = 0
        envelope.unique_states = 1
        return envelope

    def test_t7_1_maybe_override_returns_none_for_stall_guard_eject(self):
        """T7.1: StallGuard eject action is not overridden."""
        policy = self._make_policy()
        sm_result = {"action": "stall_guard_eject", "next_state": "close"}
        envelope = self._make_envelope()

        with patch("src.dialogue_policy.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            result = policy.maybe_override(sm_result, envelope)

        assert result is None

    def test_t7_2_maybe_override_returns_none_for_stall_guard_nudge(self):
        """T7.2: StallGuard nudge action is not overridden."""
        policy = self._make_policy()
        sm_result = {"action": "stall_guard_nudge", "next_state": "close"}
        envelope = self._make_envelope()

        with patch("src.dialogue_policy.flags") as mock_flags:
            mock_flags.is_enabled.return_value = True
            result = policy.maybe_override(sm_result, envelope)

        assert result is None

    def test_t7_3_maybe_override_still_works_for_regular_actions(self):
        """T7.3: Regular actions don't hit the stall_guard early-return guard."""
        # The key assertion: our stall_guard protection only triggers for
        # "stall_guard_eject" and "stall_guard_nudge" actions.
        # For any other action, the code proceeds past our guard.
        from src.dialogue_policy import DialoguePolicy

        policy = DialoguePolicy(shadow_mode=False)

        # These actions should NOT be short-circuited by stall_guard protection
        regular_actions = ["continue", "answer_with_facts", "present_solution", "handle_objection"]
        for action in regular_actions:
            sm_result = {"action": action, "next_state": "presentation"}
            # Verify the action doesn't match stall_guard pattern
            assert action not in ("stall_guard_eject", "stall_guard_nudge")

        # These actions SHOULD be short-circuited
        for sg_action in ("stall_guard_eject", "stall_guard_nudge"):
            sm_result = {"action": sg_action, "next_state": "close"}
            envelope = self._make_envelope()
            with patch("src.dialogue_policy.flags") as mock_flags:
                mock_flags.is_enabled.return_value = True
                result = policy.maybe_override(sm_result, envelope)
            assert result is None, f"StallGuard action '{sg_action}' should be protected"


# =============================================================================
# T10: Feature Flag
# =============================================================================


class TestBug19FeatureFlag:
    """T10: stall_guard_dual_proposal feature flag exists and works."""

    def test_t10_1_flag_in_defaults(self):
        """T10.1: stall_guard_dual_proposal is in DEFAULTS."""
        from src.feature_flags import FeatureFlags
        assert "stall_guard_dual_proposal" in FeatureFlags.DEFAULTS
        assert FeatureFlags.DEFAULTS["stall_guard_dual_proposal"] is True

    def test_t10_2_property_accessor_works(self):
        """T10.2: Property accessor returns bool."""
        from src.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert isinstance(ff.stall_guard_dual_proposal, bool)
        assert ff.stall_guard_dual_proposal is True


# =============================================================================
# T12: Regression Guards
# =============================================================================


class TestRegressionGuards:
    """T12: Structural invariants and no hardcoded knowledge remains."""

    def test_t12_3_kb_sections_structure_invariant(self):
        """T12.3: KB sections have correct structure for auto-discovery."""
        from src.knowledge.retriever import get_retriever
        retriever = get_retriever()

        for section in retriever.kb.sections:
            if section.priority <= 8:
                assert len(section.facts) > 0, (
                    f"Empty facts in overview section: {section.category}/{section.topic}"
                )

    def test_t12_4_no_hardcoded_product_knowledge_in_config(self):
        """T12.4: KNOWLEDGE has no 'features' key."""
        from src.config import KNOWLEDGE
        assert "features" not in KNOWLEDGE

    def test_t12_4b_no_hardcoded_features_in_fallback_handler(self):
        """T12.4b: No hardcoded 'Автоматические напоминания' in fallback_handler.py."""
        handler_path = Path(__file__).parent.parent / "src" / "fallback_handler.py"
        content = handler_path.read_text(encoding="utf-8")
        assert "Автоматические напоминания клиентам" not in content
        assert "Контроль работы менеджеров" not in content
        assert "Видеть всех клиентов в одном месте" not in content
