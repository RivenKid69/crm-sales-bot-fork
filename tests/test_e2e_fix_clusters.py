"""
Tests for 4 Clusters of E2E Simulation Error Fixes.

Covers:
- Cluster 1: _clean() proportion-based English detection
- Cluster 2: CTA phase-based coverage for all flows
- Cluster 3: Price question intent-aware get_product_overview()
- Cluster 4: Repair mode enriched directives
- Additional A1: Retriever question_features mapping
- Additional A3: Tariff names preserved by proportion-based _clean()
"""

import sys
import re
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

# =============================================================================
# CLUSTER 1: _clean() proportion-based English detection
# =============================================================================

class TestCleanProportionBased:
    """Test that _clean() uses proportion-based English detection."""

    def _make_generator(self):
        """Create a ResponseGenerator with mock LLM."""
        from src.generator import ResponseGenerator
        llm = MagicMock()
        llm.generate.return_value = "test"
        gen = ResponseGenerator(llm)
        return gen

    def test_russian_text_with_technical_terms_preserved(self):
        """Technical terms like REST, OAuth, JWT should NOT be stripped from Russian text."""
        gen = self._make_generator()
        # Russian text with <30% latin chars
        text = "Наша система поддерживает REST API и OAuth 2.0 аутентификацию"
        result = gen._clean(text)
        assert "REST" in result, f"REST was stripped from: {result}"
        assert "API" in result, f"API was stripped from: {result}"
        assert "OAuth" in result, f"OAuth was stripped from: {result}"

    def test_russian_text_with_ssl_jwt_preserved(self):
        """SSL, JWT, SLA terms should be preserved in Russian text."""
        gen = self._make_generator()
        text = "Мы используем SSL шифрование и JWT токены для безопасности"
        result = gen._clean(text)
        assert "SSL" in result, f"SSL was stripped from: {result}"
        assert "JWT" in result, f"JWT was stripped from: {result}"

    def test_full_english_text_stripped(self):
        """Full English text (>50% latin) should be stripped."""
        gen = self._make_generator()
        text = "This is a completely English response that should be cleaned"
        result = gen._clean(text)
        # Most English words should be removed
        english_words = re.findall(r'\b[a-zA-Z]{3,}\b', result)
        assert len(english_words) < 3, f"English text not stripped: {result}"

    def test_short_text_not_processed(self):
        """Text with <= 10 alpha chars should not be processed."""
        gen = self._make_generator()
        text = "OK CRM API"
        result = gen._clean(text)
        # Short text should pass through (allowed words preserved)
        assert "OK" in result or "CRM" in result or "API" in result

    def test_chinese_still_removed(self):
        """Chinese characters should still be removed regardless."""
        gen = self._make_generator()
        text = "Привет 你好 мир"
        result = gen._clean(text)
        assert "你好" not in result

    def test_mixed_text_under_threshold_preserved(self):
        """Russian text with some English (<50%) should preserve English terms."""
        gen = self._make_generator()
        text = "Интеграция с PostgreSQL базой данных через HTTPS протокол"
        result = gen._clean(text)
        assert "PostgreSQL" in result, f"PostgreSQL stripped: {result}"
        assert "HTTPS" in result or "https" in result.lower(), f"HTTPS stripped: {result}"

    def test_has_english_proportion_based(self):
        """_has_english() should use proportion-based detection."""
        gen = self._make_generator()
        # Mostly Russian with a few English terms - should be False
        assert not gen._has_english("API 2.0 с REST аутентификацией")
        # Mostly English - should be True
        assert gen._has_english("This is a completely English text response from the model")
        # Short text - should be False
        assert not gen._has_english("API REST")

    def test_tariff_names_preserved(self):
        """Tariff names (basic, team, business, pro) should be preserved.
        This is Additional A3."""
        gen = self._make_generator()
        text = "Тариф Basic подходит для команд до 5 человек, Team для средних"
        result = gen._clean(text)
        assert "Basic" in result, f"Basic stripped: {result}"
        assert "Team" in result, f"Team stripped: {result}"

# =============================================================================
# CLUSTER 2: CTA phase-based coverage for all flows
# =============================================================================

class TestCTAPhaseMapping:
    """Test CTA phase-based coverage for all 20 flows."""

    def _make_cta_generator(self):
        from src.cta_generator import CTAGenerator
        gen = CTAGenerator()
        # Set turn count above minimum
        gen.turn_count = 5
        return gen

    def test_early_phase_no_cta(self):
        """States in early phase should not get CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "greeting", "Здравствуйте!", {}
        )
        assert not should_add
        assert reason == "early_phase_no_cta"

    def test_spin_situation_early_phase(self):
        """spin_situation maps to early phase."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "spin_situation", "Расскажите о компании.", {}
        )
        assert not should_add
        assert reason == "early_phase_no_cta"

    def test_presentation_late_phase_gets_cta(self):
        """presentation should be in late phase and get CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "presentation", "Wipon решает эту проблему автоматически.", {}
        )
        assert should_add, f"CTA should be added for presentation, got reason: {reason}"

    def test_close_phase_gets_cta(self):
        """close state should get CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "close", "Отлично, давайте обсудим следующие шаги.", {}
        )
        assert should_add, f"CTA should be added for close, got reason: {reason}"

    def test_bant_need_mid_phase(self):
        """BANT need state should be in mid phase."""
        from src.cta_generator import STATE_TO_CTA_PHASE
        assert STATE_TO_CTA_PHASE.get("bant_need") == "mid"

    def test_meddic_champion_late_phase(self):
        """MEDDIC champion state should be in late phase."""
        from src.cta_generator import STATE_TO_CTA_PHASE
        assert STATE_TO_CTA_PHASE.get("meddic_champion") == "late"

    def test_dynamic_phase_resolution(self):
        """Dynamic phase resolution should work for any flow with phase_order."""
        gen = self._make_cta_generator()
        flow_context = {
            "phase_order": ["phase1", "phase2", "phase3", "phase4"],
            "phase_states": {
                "phase1": "custom_state_1",
                "phase2": "custom_state_2",
                "phase3": "custom_state_3",
                "phase4": "custom_state_4",
            }
        }
        # First state -> early
        assert gen._get_cta_phase("custom_state_1", flow_context) == "early"
        # Middle states -> mid
        assert gen._get_cta_phase("custom_state_2", flow_context) == "mid"
        assert gen._get_cta_phase("custom_state_3", flow_context) == "mid"
        # Last state -> late
        assert gen._get_cta_phase("custom_state_4", flow_context) == "late"

    def test_dynamic_phase_21st_flow(self):
        """Hypothetical 21st flow should get correct CTA phases dynamically."""
        gen = self._make_cta_generator()
        flow_context = {
            "phase_order": ["discover", "evaluate", "decide"],
            "phase_states": {
                "discover": "test_flow_discover",
                "evaluate": "test_flow_evaluate",
                "decide": "test_flow_decide",
            }
        }
        assert gen._get_cta_phase("test_flow_discover", flow_context) == "early"
        assert gen._get_cta_phase("test_flow_evaluate", flow_context) == "mid"
        assert gen._get_cta_phase("test_flow_decide", flow_context) == "late"

    def test_terminal_states_always_correct(self):
        """Terminal states should always return correct phase regardless of flow_context."""
        gen = self._make_cta_generator()
        assert gen._get_cta_phase("greeting") == "early"
        assert gen._get_cta_phase("presentation") == "late"
        assert gen._get_cta_phase("close") == "close"
        assert gen._get_cta_phase("soft_close") == "close"
        assert gen._get_cta_phase("success") == "close"

    def test_unknown_state_defaults_to_early(self):
        """Unknown states should default to early (safe - no CTA)."""
        gen = self._make_cta_generator()
        assert gen._get_cta_phase("completely_unknown_state") == "early"

    def test_mid_phase_question_blocks_cta(self):
        """In mid phase, question-ending responses should block CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "spin_implication", "Как это влияет на бизнес?", {}
        )
        assert not should_add
        assert reason == "response_ends_with_question"

    def test_late_phase_question_allows_cta(self):
        """In late/close phases, question-ending responses should still allow CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "presentation", "Хотите узнать подробнее?", {}
        )
        assert should_add, f"Late phase should allow CTA even with question, got: {reason}"

    def test_get_cta_phase_fallback(self):
        """get_cta() should fall back to phase-based CTA when state has no specific CTA."""
        gen = self._make_cta_generator()
        # bant_need is in mid phase but has no state-specific CTA
        cta = gen.get_cta("bant_need")
        assert cta is not None, "Phase fallback should provide CTA for mid-phase state"

    def test_get_cta_with_flow_context(self):
        """get_cta() should accept flow_context parameter."""
        gen = self._make_cta_generator()
        flow_context = {
            "phase_order": ["a", "b"],
            "phase_states": {"a": "custom_a", "b": "custom_b"}
        }
        # custom_b is last -> late phase -> should get CTA
        cta = gen.get_cta("custom_b", flow_context=flow_context)
        assert cta is not None, "Should get CTA for late-phase dynamic state"

    def test_all_20_flow_states_mapped(self):
        """All known flow states should have a mapping in STATE_TO_CTA_PHASE."""
        from src.cta_generator import STATE_TO_CTA_PHASE
        # Check a sample from each flow
        expected_states = [
            "spin_situation", "spin_implication",  # SPIN
            "bant_budget", "bant_need",  # BANT
            "challenger_teach", "challenger_close",  # CHALLENGER
            "meddic_metrics", "meddic_champion",  # MEDDIC
            "sandler_bonding", "sandler_decision",  # SANDLER
            "fab_features", "fab_benefits",  # FAB
            "gap_current", "gap_solution",  # GAP
            "aida_attention", "aida_action",  # AIDA
            "value_discover", "value_roi",  # VALUE
            "solution_pain", "solution_value",  # SOLUTION
        ]
        for state in expected_states:
            assert state in STATE_TO_CTA_PHASE, f"State {state} not in STATE_TO_CTA_PHASE"

    def test_frustration_blocks_cta(self):
        """High frustration should still block CTA."""
        gen = self._make_cta_generator()
        should_add, reason = gen.should_add_cta(
            "presentation", "Wipon решает проблему.",
            {"frustration_level": 6}
        )
        assert not should_add
        assert "high_frustration" in reason

# =============================================================================
# CLUSTER 3: Price question intent-aware get_product_overview()
# =============================================================================

class TestPriceQuestionPipeline:
    """Test price question pipeline fixes."""

    def _make_generator(self):
        from src.generator import ResponseGenerator
        llm = MagicMock()
        llm.generate.return_value = "test"
        gen = ResponseGenerator(llm)
        return gen

    def test_get_product_overview_with_company_size(self):
        """get_product_overview with company_size should return specific tariff."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=3)
        assert "₽" in result
        assert "Тариф" in result

    def test_get_product_overview_price_intent_no_size(self):
        """get_product_overview with price intent but no company_size should return price range."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=None, intent="price_question")
        assert "₽" in result, f"Price not in result: {result}"
        assert "Тарифы" in result or "чел" in result, f"No tariff info: {result}"

    def test_get_product_overview_pricing_details_intent(self):
        """get_product_overview with pricing_details intent should return prices."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=None, intent="pricing_details")
        assert "₽" in result, f"Price not in result: {result}"

    def test_get_product_overview_no_intent_returns_features(self):
        """get_product_overview without intent should return features list."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=None, intent="")
        # Should be a comma-separated features list, not pricing
        assert "Тарифы" not in result

    def test_get_product_overview_company_size_takes_priority(self):
        """company_size should take priority over intent."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=10, intent="price_question")
        # Should return specific tariff, not range
        assert "Тариф" in result
        assert "10 чел" in result

    def test_price_intent_returns_all_three_tiers(self):
        """Price intent should return all three pricing tiers."""
        gen = self._make_generator()
        result = gen.get_product_overview(company_size=None, intent="price_question")
        # Should mention all tiers
        assert "5" in result  # up to 5 people
        assert "25" in result or "6" in result  # team tier
        assert "26" in result  # business tier

# =============================================================================
# CLUSTER 4: Repair mode enriched directives
# =============================================================================

class TestRepairModeDirectives:
    """Test repair mode enriched directives."""

    def _make_envelope(self, **kwargs):
        """Create a mock ContextEnvelope."""
        envelope = MagicMock()
        envelope.reason_codes = kwargs.get("reason_codes", [])
        envelope.frustration_level = kwargs.get("frustration_level", 0)
        envelope.engagement_level = kwargs.get("engagement_level", "medium")
        envelope.is_stuck = kwargs.get("is_stuck", False)
        envelope.has_oscillation = kwargs.get("has_oscillation", False)
        envelope.repeated_question = kwargs.get("repeated_question", None)
        envelope.has_reason = lambda code: code.value in [r.value if hasattr(r, 'value') else r for r in envelope.reason_codes]
        envelope.first_objection_type = kwargs.get("first_objection_type", None)
        envelope.has_breakthrough = kwargs.get("has_breakthrough", False)
        envelope.client_has_data = kwargs.get("client_has_data", False)
        envelope.client_company_size = kwargs.get("client_company_size", None)
        envelope.client_pain_points = kwargs.get("client_pain_points", [])
        envelope.collected_data = kwargs.get("collected_data", {})
        envelope.objection_types_seen = kwargs.get("objection_types_seen", [])
        envelope.repeated_objection_types = kwargs.get("repeated_objection_types", [])
        envelope.bot_responses = kwargs.get("bot_responses", [])
        envelope.history = kwargs.get("history", [])
        envelope.total_turns = kwargs.get("total_turns", 0)
        envelope.pre_intervention_triggered = kwargs.get("pre_intervention_triggered", False)
        return envelope

    def test_repair_trigger_and_context_fields_exist(self):
        """ResponseDirectives should have repair_trigger and repair_context fields."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives()
        assert hasattr(d, "repair_trigger")
        assert hasattr(d, "repair_context")
        assert d.repair_trigger == ""
        assert d.repair_context == ""

    def test_repair_mode_stuck_trigger(self):
        """Stuck repair mode should set repair_trigger='stuck' and offer choices."""
        from src.response_directives import ResponseDirectivesBuilder, ResponseDirectives
        from src.context_envelope import ReasonCode

        envelope = self._make_envelope(
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE],
            is_stuck=True,
        )

        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        assert directives.repair_mode is True
        assert directives.repair_trigger == "stuck"
        assert directives.offer_choices is True
        assert directives.ask_clarifying is True

    def test_repair_mode_oscillation_trigger(self):
        """Oscillation repair mode should set repair_trigger='oscillation'."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ReasonCode

        envelope = self._make_envelope(
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE],
            is_stuck=False,
            has_oscillation=True,
        )

        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        assert directives.repair_mode is True
        assert directives.repair_trigger == "oscillation"

    def test_repair_mode_repeated_question_trigger(self):
        """Repeated question should set repair_trigger and context."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ReasonCode

        envelope = self._make_envelope(
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE],
            is_stuck=False,
            has_oscillation=False,
            repeated_question="price_question",
        )

        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        assert directives.repair_mode is True
        assert directives.repair_trigger == "repeated_question"
        assert "цене" in directives.repair_context.lower() or "590" in directives.repair_context

    def test_repair_mode_generic_repeated_question(self):
        """Non-price repeated question should set generic context."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ReasonCode

        envelope = self._make_envelope(
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE],
            is_stuck=False,
            has_oscillation=False,
            repeated_question="question_features",
        )

        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        assert directives.repair_trigger == "repeated_question"
        assert "question_features" in directives.repair_context

    def test_repair_instruction_stuck_contains_steps(self):
        """Stuck repair instruction should mention concrete next steps."""
        from src.response_directives import ResponseDirectives

        d = ResponseDirectives()
        d.repair_mode = True
        d.repair_trigger = "stuck"
        instruction = d.get_instruction()

        assert "демо" in instruction.lower() or "варианта" in instruction.lower() or "шаг" in instruction.lower()

    def test_repair_instruction_oscillation_contains_summary(self):
        """Oscillation repair instruction should mention summarizing."""
        from src.response_directives import ResponseDirectives

        d = ResponseDirectives()
        d.repair_mode = True
        d.repair_trigger = "oscillation"
        instruction = d.get_instruction()

        assert "суммируй" in instruction.lower() or "обсудили" in instruction.lower()

    def test_repair_instruction_repeated_contains_context(self):
        """Repeated question repair instruction should include context."""
        from src.response_directives import ResponseDirectives

        d = ResponseDirectives()
        d.repair_mode = True
        d.repair_trigger = "repeated_question"
        d.repair_context = "Клиент ПОВТОРНО спрашивает о цене! ОБЯЗАТЕЛЬНО назови цену: от 590 до 990₽/чел./мес."
        instruction = d.get_instruction()

        assert "590" in instruction

    def test_repair_to_dict_includes_new_fields(self):
        """to_dict() should include repair_trigger and repair_context."""
        from src.response_directives import ResponseDirectives

        d = ResponseDirectives()
        d.repair_mode = True
        d.repair_trigger = "stuck"
        d.repair_context = "test context"
        result = d.to_dict()

        assert "repair_trigger" in result["dialogue_moves"]
        assert result["dialogue_moves"]["repair_trigger"] == "stuck"
        assert "repair_context" in result["dialogue_moves"]
        assert result["dialogue_moves"]["repair_context"] == "test context"

# =============================================================================
# ADDITIONAL A1: Retriever question_features mapping
# =============================================================================

class TestRetrieverMapping:
    """Test retriever question_features mapping."""

    def test_question_features_includes_support_integrations(self):
        """question_features should include support and integrations categories."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY
        cats = INTENT_TO_CATEGORY.get("question_features", [])
        assert "support" in cats, f"support not in question_features: {cats}"
        assert "integrations" in cats, f"integrations not in question_features: {cats}"

    def test_question_features_preserves_existing(self):
        """Existing categories should still be present."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY
        cats = INTENT_TO_CATEGORY.get("question_features", [])
        assert "features" in cats
        assert "products" in cats
        assert "tis" in cats
        assert "analytics" in cats
        assert "inventory" in cats

# =============================================================================
# SETTINGS: Expanded allowed_english_words
# =============================================================================

class TestExpandedAllowlist:
    """Test expanded allowed English words list."""

    def test_settings_has_technical_terms(self):
        """Settings should include technical terms in allowlist."""
        from src.settings import settings
        allowed = settings.generator.allowed_english_words
        technical_terms = ["rest", "oauth", "ssl", "jwt", "sla", "http", "https", "url", "sql"]
        for term in technical_terms:
            assert term in allowed, f"'{term}' not in allowed_english_words"

    def test_settings_has_tariff_terms(self):
        """Settings should include tariff/product terms in allowlist."""
        from src.settings import settings
        allowed = settings.generator.allowed_english_words
        tariff_terms = ["mini", "lite", "standard", "pro", "basic", "team", "business", "demo"]
        for term in tariff_terms:
            assert term in allowed, f"'{term}' not in allowed_english_words"

    def test_settings_has_brand_names(self):
        """Settings should include brand names in allowlist."""
        from src.settings import settings
        allowed = settings.generator.allowed_english_words
        brands = ["kaspi", "halyk", "iiko", "poster"]
        for brand in brands:
            assert brand in allowed, f"'{brand}' not in allowed_english_words"

# =============================================================================
# INTEGRATION: CTA phase in constants.yaml
# =============================================================================

class TestCTAPhaseConfig:
    """Test CTA phase configuration in constants.yaml."""

    def test_cta_by_phase_loaded(self):
        """CTA by_phase should be defined in cta_generator module."""
        from src.cta_generator import CTA_BY_PHASE
        assert "early" in CTA_BY_PHASE
        assert "mid" in CTA_BY_PHASE
        assert "late" in CTA_BY_PHASE
        assert "close" in CTA_BY_PHASE

    def test_early_phase_has_no_ctas(self):
        """Early phase should have empty CTA list."""
        from src.cta_generator import CTA_BY_PHASE
        assert CTA_BY_PHASE["early"] == []

    def test_mid_phase_has_soft_ctas(self):
        """Mid phase should have soft CTAs."""
        from src.cta_generator import CTA_BY_PHASE
        assert len(CTA_BY_PHASE["mid"]) > 0

    def test_late_phase_has_direct_ctas(self):
        """Late phase should have direct CTAs."""
        from src.cta_generator import CTA_BY_PHASE
        assert len(CTA_BY_PHASE["late"]) > 0

    def test_close_phase_has_contact_ctas(self):
        """Close phase should have contact CTAs."""
        from src.cta_generator import CTA_BY_PHASE
        assert len(CTA_BY_PHASE["close"]) > 0

# =============================================================================
# INTEGRATION: bot.py cta_added field
# =============================================================================

class TestBotCTATracking:
    """Test that bot.py returns cta_added and cta_text in process() result."""

    def test_cta_result_type(self):
        """CTAResult dataclass should have expected fields."""
        from src.cta_generator import CTAResult
        result = CTAResult(
            original_response="test",
            cta="Try demo?",
            final_response="test Try demo?",
            cta_added=True,
        )
        assert result.cta_added is True
        assert result.cta == "Try demo?"

# =============================================================================
# UNIVERSALITY: Future flow compatibility
# =============================================================================

class TestUniversality:
    """Test universality guarantees for future flows."""

    def test_proportion_detection_any_english_term(self):
        """Any English term should survive in Russian text (Cluster 1 universality)."""
        from src.generator import ResponseGenerator
        llm = MagicMock()
        llm.generate.return_value = "test"
        gen = ResponseGenerator(llm)

        # Simulate various technical terms in Russian text
        test_cases = [
            "Мы поддерживаем WebSocket соединения для real-time обновлений",
            "Функция Kubernetes оркестрации доступна в тарифе Enterprise",
            "Поддержка Docker контейнеров для развёртывания",
        ]
        for text in test_cases:
            result = gen._clean(text)
            # Russian text proportion should be >50%, so English should be preserved
            russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', text))
            latin_chars = len(re.findall(r'[a-zA-Z]', text))
            total = russian_chars + latin_chars
            if total > 10 and latin_chars / total <= 0.5:
                # English should be preserved
                # At least some English words should remain
                original_english = re.findall(r'\b[a-zA-Z]{3,}\b', text)
                result_english = re.findall(r'\b[a-zA-Z]{3,}\b', result)
                assert len(result_english) >= len(original_english) * 0.5, (
                    f"Too many English words stripped from: {text}\n"
                    f"Result: {result}"
                )

    def test_dynamic_cta_any_flow(self):
        """Any new flow automatically gets CTA phases (Cluster 2 universality)."""
        from src.cta_generator import CTAGenerator
        gen = CTAGenerator()
        gen.turn_count = 5

        # Simulate a 21st flow
        flow_context = {
            "phase_order": ["explore", "analyze", "recommend", "convert"],
            "phase_states": {
                "explore": "new_flow_explore",
                "analyze": "new_flow_analyze",
                "recommend": "new_flow_recommend",
                "convert": "new_flow_convert",
            }
        }

        # Verify phases are correctly computed
        assert gen._get_cta_phase("new_flow_explore", flow_context) == "early"
        assert gen._get_cta_phase("new_flow_analyze", flow_context) == "mid"
        assert gen._get_cta_phase("new_flow_recommend", flow_context) == "mid"
        assert gen._get_cta_phase("new_flow_convert", flow_context) == "late"

        # Verify CTA is added for late phase
        should_add, reason = gen.should_add_cta(
            "new_flow_convert",
            "Рекомендую попробовать наш продукт.",
            {"flow_context": flow_context}
        )
        assert should_add, f"Late phase of new flow should get CTA, got: {reason}"

    def test_intent_aware_facts_extensible(self):
        """get_product_overview() intent parameter is extensible (Cluster 3 universality)."""
        from src.generator import ResponseGenerator
        llm = MagicMock()
        gen = ResponseGenerator(llm)
        # Non-price intent should still return features
        result = gen.get_product_overview(company_size=None, intent="question_features")
        assert "Тарифы" not in result  # Should NOT return pricing for non-price intent

    def test_repair_trigger_extensible(self):
        """repair_trigger field supports open-ended extension (Cluster 4 universality)."""
        from src.response_directives import ResponseDirectives
        d = ResponseDirectives()
        d.repair_mode = True
        # Any new trigger type can be set
        d.repair_trigger = "custom_new_trigger"
        d.repair_context = "Custom context for new trigger type"
        instruction = d.get_instruction()
        # Should fall through to default "Перефразируй"
        assert "Перефразируй" in instruction or "восстановления" in instruction.lower()
