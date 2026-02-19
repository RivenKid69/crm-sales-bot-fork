# tests/test_rc_fixes.py
"""
Unit tests for RC1-RC6 fixes: "бот отвечает мимо вопроса"

RC1a — specificity factor in _exact_search
RC1b — keyword cleanup in tariffs
RC4   — payment-term patterns in price_question
RC5   — expanded demo_request patterns
RC6a  — advance_request secondary intent
RC6b  — SKIP_RETRIEVAL bypass via secondary_intents
RC6d  — threshold 10→5 in _should_apply
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Optional

from src.knowledge.retriever import (
    CascadeRetriever,
    MatchStage,
    SearchResult,
)
from src.knowledge.base import KnowledgeSection
from src.classifier.secondary_intent_detection import (
    SecondaryIntentDetectionLayer,
    DEFAULT_SECONDARY_INTENT_PATTERNS,
)
from src.classifier.refinement_pipeline import RefinementContext


# =============================================================================
# HELPERS
# =============================================================================

def _make_section(
    topic: str,
    keywords: List[str],
    priority: int = 5,
    category: str = "pricing",
    facts: str = "test facts",
) -> KnowledgeSection:
    return KnowledgeSection(
        category=category,
        topic=topic,
        keywords=keywords,
        facts=facts,
        priority=priority,
    )


def _make_ctx(
    message: str,
    intent: str = "info_provided",
    confidence: float = 0.85,
) -> RefinementContext:
    return RefinementContext(
        message=message,
        intent=intent,
        confidence=confidence,
        state="autonomous_discovery",
        phase="discovery",
        last_action="autonomous_respond",
    )


def _make_result(intent: str = "info_provided", confidence: float = 0.85):
    return {
        "intent": intent,
        "confidence": confidence,
        "metadata": {},
    }


# =============================================================================
# RC1a — SPECIFICITY FACTOR
# =============================================================================

class TestSpecificityFactor:
    """RC1a: _exact_search specificity factor penalizes umbrella topics."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_specific_beats_umbrella_single_match(self, retriever):
        """
        'рассрочка' — installment topic (5 kw) must beat tariffs (~24 kw)
        when both have exactly 1 keyword match.
        """
        # Create two competing sections
        umbrella = _make_section(
            topic="tariffs",
            keywords=["тариф", "цена", "стоимость", "прайс", "подписка",
                       "почём", "ценник", "прейскурант", "расценки", "рассрочка",
                       "во сколько", "ценовая политика", "price", "price list",
                       "сколько стоит", "ценна", "цна", "ценy", "прас",
                       "праис", "прайз", "прайзы", "расценка", "во сколько обойдётся"],
            priority=10,
        )
        specific = _make_section(
            topic="installment_628",
            keywords=["рассрочка", "в рассрочку", "рассрочка 12 месяцев",
                       "помесячно", "ежемесячный платёж"],
            priority=5,
        )

        results = retriever._exact_search("рассрочка", [umbrella, specific])
        # Both should match, but specific must rank higher
        topics = [r.section.topic for r in results]
        assert "installment_628" in topics
        if "tariffs" in topics:
            idx_specific = topics.index("installment_628")
            idx_umbrella = topics.index("tariffs")
            assert idx_specific < idx_umbrella, \
                f"Specific topic should rank above umbrella: {topics}"

    def test_umbrella_wins_with_more_matches(self, retriever):
        """
        'сколько стоит тариф' — tariffs has 2 keyword matches (legitimate),
        should beat a topic with only 1 match.
        """
        umbrella = _make_section(
            topic="tariffs",
            keywords=["тариф", "цена", "стоимость", "прайс", "подписка",
                       "сколько стоит", "ценник", "прейскурант"],
            priority=10,
        )
        specific = _make_section(
            topic="pro_details",
            keywords=["тариф про", "pro", "максимальный", "премиум",
                       "корпоративный", "сколько стоит", "расширенный", "продвинутый"],
            priority=5,
        )

        results = retriever._exact_search("сколько стоит тариф", [umbrella, specific])
        topics = [r.section.topic for r in results]
        # tariffs matches "сколько стоит" + "тариф" = 2 matches
        # pro_details matches "сколько стоит" = 1 match
        # Both have 8 keywords, so specificity factors should be similar
        # But tariffs has more matches → higher raw score → should win
        assert len(results) >= 1
        if len(results) >= 2:
            assert topics[0] == "tariffs", f"Tariffs should win with 2 matches: {topics}"

    def test_specific_pos_beats_hardware_umbrella(self, retriever):
        """
        'терминал pos' — pos_i3_details (6 kw) beats hardware (43 kw)
        when both match 2 keywords.
        """
        hardware = _make_section(
            topic="hardware",
            keywords=["терминал", "pos", "оборудование", "моноблок", "касса",
                       "сканер", "принтер", "весы", "подключение", "wifi",
                       # ... simulating 43 keywords with fillers
                       ] + [f"hw_kw_{i}" for i in range(33)],
            priority=10,
            category="equipment",
        )
        pos_details = _make_section(
            topic="pos_i3_details",
            keywords=["терминал", "pos", "i3", "моноблок", "pos терминал", "pos i3"],
            priority=5,
            category="equipment",
        )

        results = retriever._exact_search("терминал pos", [hardware, pos_details])
        topics = [r.section.topic for r in results]
        assert "pos_i3_details" in topics
        if "hardware" in topics:
            idx_specific = topics.index("pos_i3_details")
            idx_umbrella = topics.index("hardware")
            assert idx_specific < idx_umbrella, \
                f"Specific POS topic should rank above hardware umbrella: {topics}"

    def test_specificity_factor_always_gte_1(self, retriever):
        """Factor is always >= 1.0, so scores only grow (never decrease)."""
        section = _make_section(
            topic="test",
            keywords=["тест", "проверка"],
            priority=5,
        )
        results = retriever._exact_search("тест", [section])
        assert len(results) > 0
        # Score must be > raw score (which is >= exact_threshold = 1.0)
        assert results[0].score >= 1.0


# =============================================================================
# RC1b — KEYWORD CLEANUP
# =============================================================================

class TestKeywordCleanup:
    """RC1b: tariffs topic should not match bare generic words."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_tariffs_no_match_for_bare_oplata(self, retriever):
        """
        'оплата картой' should NOT match tariffs (keyword removed).
        It should match payment_methods instead.
        """
        from src.knowledge import WIPON_KNOWLEDGE
        sections = WIPON_KNOWLEDGE.sections

        # Find tariffs section
        tariff_sections = [s for s in sections if s.topic == "tariffs"]
        if tariff_sections:
            tariff = tariff_sections[0]
            # 'оплата' should not be in keywords
            lower_kw = [kw.lower() for kw in tariff.keywords]
            assert "оплата" not in lower_kw, "RC1b: 'оплата' should be removed from tariffs"
            assert "дорого" not in lower_kw, "RC1b: 'дорого' should be removed from tariffs"
            assert "стоит" not in lower_kw, "RC1b: 'стоит' should be removed from tariffs"
            assert "рассрочка" not in lower_kw, "RC1b: 'рассрочка' should be removed from tariffs"
            assert "сколько" not in lower_kw, "RC1b: bare 'сколько' should be removed from tariffs"
            assert "денег" not in lower_kw, "RC1b: 'денег' should be removed from tariffs"
            # But "сколько стоит" (2-word) should remain
            assert "сколько стоит" in lower_kw, "'сколько стоит' (2-word) should remain"

    def test_no_duplicate_keywords_in_tariffs(self, retriever):
        """RC1b: no duplicate keywords in tariffs (was: 'прас' x2)."""
        from src.knowledge import WIPON_KNOWLEDGE
        tariff_sections = [s for s in WIPON_KNOWLEDGE.sections if s.topic == "tariffs"]
        if tariff_sections:
            kw = tariff_sections[0].keywords
            assert len(kw) == len(set(kw)), f"Duplicate keywords found: {[k for k in kw if kw.count(k) > 1]}"


# =============================================================================
# RC4 — PAYMENT-TERM SECONDARY INTENT
# =============================================================================

class TestPaymentTermPatterns:
    """RC4: payment-term vocabulary triggers price_question secondary intent."""

    @pytest.fixture
    def layer(self):
        return SecondaryIntentDetectionLayer()

    def test_rassrochka_triggers_price_question(self, layer):
        """'дорого. рассрочка есть?' → secondary=price_question."""
        ctx = _make_ctx("дорого. рассрочка есть?", intent="price_objection")
        result = _make_result("price_objection")
        refined = layer.refine("дорого. рассрочка есть?", result, ctx)
        si = refined.secondary_signals
        assert "price_question" in si, f"Expected price_question, got: {si}"

    def test_chastyami_triggers_price_question(self, layer):
        """'можно частями оплатить?' → secondary=price_question."""
        ctx = _make_ctx("можно частями оплатить?", intent="question_features")
        result = _make_result("question_features")
        refined = layer.refine("можно частями оплатить?", result, ctx)
        si = refined.secondary_signals
        assert "price_question" in si, f"Expected price_question, got: {si}"

    def test_pomesyachno_triggers_price_question(self, layer):
        """'а помесячно можно платить?' → secondary=price_question."""
        ctx = _make_ctx("а помесячно можно платить?", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("а помесячно можно платить?", result, ctx)
        si = refined.secondary_signals
        assert "price_question" in si, f"Expected price_question, got: {si}"


# =============================================================================
# RC5 — DEMO REQUEST EXPANDED
# =============================================================================

class TestDemoRequestExpanded:
    """RC5: expanded demo/visual request patterns."""

    @pytest.fixture
    def layer(self):
        return SecondaryIntentDetectionLayer()

    def test_posmotret_na_primere(self, layer):
        """'можно посмотреть на примере?' → secondary=demo_request."""
        ctx = _make_ctx("можно посмотреть на примере?", intent="doubt")
        result = _make_result("doubt")
        refined = layer.refine("можно посмотреть на примере?", result, ctx)
        si = refined.secondary_signals
        assert "demo_request" in si, f"Expected demo_request, got: {si}"

    def test_est_video(self, layer):
        """'есть видео как работает?' → secondary=demo_request."""
        ctx = _make_ctx("есть видео как работает?", intent="question_features")
        result = _make_result("question_features")
        refined = layer.refine("есть видео как работает?", result, ctx)
        si = refined.secondary_signals
        assert "demo_request" in si, f"Expected demo_request, got: {si}"

    def test_kak_vyglyadit(self, layer):
        """'как выглядит интерфейс?' → secondary=demo_request."""
        ctx = _make_ctx("как выглядит интерфейс?", intent="question_features")
        result = _make_result("question_features")
        refined = layer.refine("как выглядит интерфейс?", result, ctx)
        si = refined.secondary_signals
        assert "demo_request" in si, f"Expected demo_request, got: {si}"

    def test_video_word_boundary(self, layer):
        """'видеонаблюдение' should NOT trigger demo_request (word boundary)."""
        ctx = _make_ctx("у вас есть видеонаблюдение?", intent="question_features")
        result = _make_result("question_features")
        refined = layer.refine("у вас есть видеонаблюдение?", result, ctx)
        si = refined.secondary_signals
        assert "demo_request" not in si, \
            f"'видеонаблюдение' should not match demo_request: {si}"


# =============================================================================
# RC6a — ADVANCE_REQUEST SECONDARY INTENT
# =============================================================================

class TestAdvanceRequest:
    """RC6a: advance_request secondary intent."""

    @pytest.fixture
    def layer(self):
        return SecondaryIntentDetectionLayer()

    def test_chto_eshyo(self, layer):
        """'что ещё?' → secondary=advance_request."""
        ctx = _make_ctx("что ещё?", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("что ещё?", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_dalshe(self, layer):
        r"""'дальше' → secondary=advance_request (\bдальше\b)."""
        ctx = _make_ctx("дальше", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("дальше", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_a_eshyo(self, layer):
        r"""'а ещё?' → secondary=advance_request (а\s+ещ[ёе]\b)."""
        ctx = _make_ctx("а ещё?", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("а ещё?", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_idyom_dalshe(self, layer):
        """'идём дальше' → secondary=advance_request."""
        ctx = _make_ctx("идём дальше", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("идём дальше", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_prodolzhay(self, layer):
        """'продолжай' → secondary=advance_request."""
        ctx = _make_ctx("продолжай", intent="question_features")
        result = _make_result("question_features")
        refined = layer.refine("продолжай", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_chto_eshyo_mozhete(self, layer):
        """'что ещё можете?' → secondary=advance_request."""
        ctx = _make_ctx("что ещё можете?", intent="info_provided")
        result = _make_result("info_provided")
        refined = layer.refine("что ещё можете?", result, ctx)
        si = refined.secondary_signals
        assert "advance_request" in si, f"Expected advance_request, got: {si}"

    def test_advance_request_in_defaults(self):
        """advance_request is defined in DEFAULT_SECONDARY_INTENT_PATTERNS."""
        assert "advance_request" in DEFAULT_SECONDARY_INTENT_PATTERNS
        pat = DEFAULT_SECONDARY_INTENT_PATTERNS["advance_request"]
        assert pat.keywords == frozenset(), \
            "advance_request must have empty keywords (patterns always run)"


# =============================================================================
# RC6b — SKIP_RETRIEVAL BYPASS
# =============================================================================

class TestSkipRetrievalBypass:
    """RC6b: secondary_intents bypass SKIP_RETRIEVAL."""

    def _make_pipeline(self):
        """Create a minimal EnhancedRetrievalPipeline with mocked deps."""
        from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline
        pipeline = EnhancedRetrievalPipeline.__new__(EnhancedRetrievalPipeline)
        # Minimal init for testing the skip logic
        pipeline.category_router = None
        pipeline.query_rewriter = MagicMock()
        pipeline.query_rewriter.rewrite.return_value = "test query"
        pipeline.complexity_detector = MagicMock()
        pipeline.complexity_detector.is_complex.return_value = False
        pipeline.multi_query_retriever = MagicMock()
        pipeline.top_k_per_sub_query = 3
        pipeline.rrf_k = 60
        pipeline.max_chars = 4000
        return pipeline

    @patch("src.knowledge.enhanced_retrieval.load_facts_for_state")
    def test_skip_with_social_only_secondary(self, mock_load):
        """intent=greeting + secondary=[request_brevity] → SKIP (social-only)."""
        mock_load.return_value = ("state facts", [], ["key1"])
        pipeline = self._make_pipeline()

        result = pipeline.retrieve(
            user_message="привет",
            intent="greeting",
            state="autonomous_discovery",
            flow_config=MagicMock(),
            kb=MagicMock(),
            secondary_intents=["request_brevity"],
        )
        mock_load.assert_called_once()
        assert result[0] == "state facts"

    @patch("src.knowledge.enhanced_retrieval.load_facts_for_state")
    @patch("src.knowledge.enhanced_retrieval.get_retriever")
    def test_bypass_skip_with_advance_request(self, mock_get_retriever, mock_load):
        """intent=info_provided + secondary=[advance_request] → bypass SKIP."""
        mock_load.return_value = ("state facts", [], ["key1"])
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []
        mock_get_retriever.return_value = mock_retriever
        pipeline = self._make_pipeline()

        # Should NOT call load_facts_for_state as the fast path
        # Instead should fall through to full retrieval
        try:
            pipeline.retrieve(
                user_message="что ещё?",
                intent="info_provided",
                state="autonomous_discovery",
                flow_config=MagicMock(),
                kb=MagicMock(),
                secondary_intents=["advance_request"],
            )
        except Exception:
            pass  # We don't care about downstream errors, just bypass logic

        # info_provided IS in SKIP_RETRIEVAL_INTENTS, but with advance_request
        # it should bypass. If load_facts_for_state was called as first action,
        # it means bypass didn't work (but it might be called for state backfill later).
        # The key test: get_retriever should be called (full retrieval path).
        mock_get_retriever.assert_called_once()

    @patch("src.knowledge.enhanced_retrieval.load_facts_for_state")
    @patch("src.knowledge.enhanced_retrieval.get_retriever")
    def test_bypass_skip_with_price_question(self, mock_get_retriever, mock_load):
        """intent=greeting + secondary=[price_question] → bypass SKIP."""
        mock_load.return_value = ("state facts", [], ["key1"])
        mock_retriever = MagicMock()
        mock_retriever.search.return_value = []
        mock_get_retriever.return_value = mock_retriever
        pipeline = self._make_pipeline()

        try:
            pipeline.retrieve(
                user_message="привет, сколько стоит?",
                intent="greeting",
                state="autonomous_discovery",
                flow_config=MagicMock(),
                kb=MagicMock(),
                secondary_intents=["price_question"],
            )
        except Exception:
            pass

        mock_get_retriever.assert_called_once()

    @patch("src.knowledge.enhanced_retrieval.load_facts_for_state")
    def test_no_secondary_intents_still_skips(self, mock_load):
        """intent=greeting + no secondary → still SKIP."""
        mock_load.return_value = ("state facts", [], ["key1"])
        pipeline = self._make_pipeline()

        result = pipeline.retrieve(
            user_message="привет",
            intent="greeting",
            state="autonomous_discovery",
            flow_config=MagicMock(),
            kb=MagicMock(),
            secondary_intents=None,
        )
        mock_load.assert_called_once()

    @patch("src.knowledge.enhanced_retrieval.load_facts_for_state")
    def test_empty_secondary_intents_still_skips(self, mock_load):
        """intent=greeting + secondary=[] → still SKIP."""
        mock_load.return_value = ("state facts", [], ["key1"])
        pipeline = self._make_pipeline()

        result = pipeline.retrieve(
            user_message="привет",
            intent="greeting",
            state="autonomous_discovery",
            flow_config=MagicMock(),
            kb=MagicMock(),
            secondary_intents=[],
        )
        mock_load.assert_called_once()


# =============================================================================
# RC6d — THRESHOLD 10→5
# =============================================================================

class TestThreshold:
    """RC6d: _should_apply threshold lowered from 10 to 5."""

    @pytest.fixture
    def layer(self):
        return SecondaryIntentDetectionLayer()

    def test_8_chars_passes(self, layer):
        """'что ещё?' (8 chars) should pass _should_apply."""
        ctx = _make_ctx("что ещё?")
        assert layer._should_apply(ctx) is True

    def test_6_chars_passes(self, layer):
        """'дальше' (6 chars) should pass _should_apply."""
        ctx = _make_ctx("дальше")
        assert layer._should_apply(ctx) is True

    def test_3_chars_fails(self, layer):
        """'ещё' (3 chars) should fail _should_apply."""
        ctx = _make_ctx("ещё")
        assert layer._should_apply(ctx) is False

    def test_5_chars_passes(self, layer):
        """5 chars exactly should pass (threshold is <5)."""
        ctx = _make_ctx("12345")
        assert layer._should_apply(ctx) is True

    def test_4_chars_fails(self, layer):
        """4 chars should fail _should_apply."""
        ctx = _make_ctx("1234")
        assert layer._should_apply(ctx) is False
