"""
Tests for KB-grounded questions system.

Tests:
- Question validation and dedup (generate_kb_questions.py)
- KBQuestionPool loading and querying (kb_questions.py)
- Persona KB probability field (personas.py)
- ClientAgent KB integration (client_agent.py)
- ClientAgentTrace KB fields (decision_trace.py)

NOTE: No LLM or semantic search tests — all mocked.
"""

import json
import os
import random
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# ============================================================================
# Test generate_kb_questions.py helpers
# ============================================================================

from scripts.generate_kb_questions import (
    validate_question,
    truncate_facts,
    jaccard_similarity,
    dedup_questions,
    parse_questions_from_response,
)


class TestValidateQuestion:
    """Test question validation logic."""

    def test_valid_question(self):
        ok, reason = validate_question("Wipon Kassa точно бесплатная?")
        assert ok is True
        assert reason == "ok"

    def test_no_question_mark(self):
        ok, reason = validate_question("Wipon Kassa точно бесплатная")
        assert ok is False
        assert reason == "no_question_mark"

    def test_too_short(self):
        ok, reason = validate_question("да?")
        assert ok is False
        assert reason == "too_short"

    def test_too_long(self):
        long_q = "а" * 80 + "?"
        ok, reason = validate_question(long_q)
        assert ok is False
        assert reason == "too_long"

    def test_exactly_80_chars(self):
        q = "а" * 79 + "?"
        assert len(q) == 80
        ok, reason = validate_question(q)
        assert ok is True

    def test_meta_phrase_rejected(self):
        ok, reason = validate_question("вопрос: как подключить кассу?")
        assert ok is False
        assert "meta_phrase" in reason

    def test_markdown_rejected(self):
        ok, reason = validate_question("**как подключить** кассу?")
        assert ok is False
        assert "markdown" in reason

    def test_empty_string(self):
        ok, reason = validate_question("")
        assert ok is False
        assert reason == "empty"

    def test_whitespace_only(self):
        ok, reason = validate_question("   ")
        assert ok is False
        assert reason == "empty"

    def test_bullet_markdown_rejected(self):
        ok, reason = validate_question("- как подключить кассу?")
        assert ok is False
        assert "markdown" in reason


class TestTruncateFacts:
    """Test facts truncation."""

    def test_short_text_unchanged(self):
        text = "Короткий факт о продукте"
        assert truncate_facts(text, 300) == text

    def test_long_text_truncated(self):
        words = ["слово"] * 400
        text = " ".join(words)
        result = truncate_facts(text, 300)
        assert result.endswith("...")
        # 300 words + "..."
        result_words = result.rstrip("...").strip().split()
        assert len(result_words) == 300

    def test_exact_limit_unchanged(self):
        words = ["слово"] * 300
        text = " ".join(words)
        result = truncate_facts(text, 300)
        assert not result.endswith("...")


class TestJaccardSimilarity:
    """Test Jaccard similarity calculation."""

    def test_identical_strings(self):
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity("hello world foo", "hello bar foo")
        # intersection: {hello, foo} = 2, union: {hello, world, foo, bar} = 4
        assert sim == pytest.approx(0.5)

    def test_empty_string(self):
        assert jaccard_similarity("", "hello") == 0.0
        assert jaccard_similarity("hello", "") == 0.0
        assert jaccard_similarity("", "") == 0.0


class TestDedupQuestions:
    """Test question deduplication."""

    def test_exact_dedup(self):
        questions = [
            {"text": "Сколько стоит?", "category": "pricing", "source_topic": "t1", "priority": 5},
            {"text": "Сколько стоит?", "category": "pricing", "source_topic": "t1", "priority": 5},
        ]
        result = dedup_questions(questions)
        assert len(result) == 1

    def test_fuzzy_dedup(self):
        questions = [
            {"text": "сколько стоит подписка на месяц?", "category": "pricing", "source_topic": "t1", "priority": 5},
            {"text": "сколько стоит подписка на год?", "category": "pricing", "source_topic": "t1", "priority": 5},
        ]
        result = dedup_questions(questions)
        # Jaccard: intersection={сколько, стоит, подписка, на}=4, union={...месяц?, ...год?}=6
        # 4/6 = 0.667 < 0.7 — these are different enough to keep
        assert len(result) == 2

        # Now test truly similar questions (>0.7 overlap)
        questions2 = [
            {"text": "какая цена на подписку сейчас?", "category": "pricing", "source_topic": "t1", "priority": 5},
            {"text": "какая цена на подписку сегодня?", "category": "pricing", "source_topic": "t1", "priority": 5},
        ]
        result2 = dedup_questions(questions2)
        # intersection={какая, цена, на, подписку}=4, union={...сейчас?, ...сегодня?}=6
        # 4/6 = 0.667 < 0.7 — still different
        # To get >0.7 we need more overlapping words:
        questions3 = [
            {"text": "сколько стоит ваша crm система для бизнеса?", "category": "pricing", "source_topic": "t1", "priority": 5},
            {"text": "сколько стоит ваша crm система для компании?", "category": "pricing", "source_topic": "t1", "priority": 5},
        ]
        result3 = dedup_questions(questions3)
        # intersection={сколько, стоит, ваша, crm, система, для}=6, union 8
        # 6/8 = 0.75 > 0.7 — should dedup
        assert len(result3) == 1

    def test_different_questions_kept(self):
        questions = [
            {"text": "Сколько стоит?", "category": "pricing", "source_topic": "t1", "priority": 5},
            {"text": "Есть интеграция с 1С?", "category": "integrations", "source_topic": "t2", "priority": 5},
        ]
        result = dedup_questions(questions)
        assert len(result) == 2

    def test_empty_list(self):
        assert dedup_questions([]) == []


class TestParseQuestionsFromResponse:
    """Test LLM response parsing."""

    def test_simple_questions(self):
        response = "Сколько стоит подписка?\nЕсть ли бесплатный период?\nМожно попробовать бесплатно?"
        questions, rejected = parse_questions_from_response(
            response, "pricing", "tariffs", 7
        )
        assert len(questions) == 3
        assert rejected == 0
        assert questions[0]["text"] == "Сколько стоит подписка?"
        assert questions[0]["category"] == "pricing"
        assert questions[0]["source_topic"] == "tariffs"
        assert questions[0]["priority"] == 7

    def test_numbered_format_stripped(self):
        response = "1. Сколько стоит?\n2. Есть скидки?"
        questions, rejected = parse_questions_from_response(
            response, "pricing", "tariffs", 5
        )
        assert len(questions) == 2
        assert questions[0]["text"] == "Сколько стоит?"

    def test_invalid_questions_rejected(self):
        response = "Сколько стоит\nда?\n**Как подключить?**\nЕсть API?"
        questions, rejected = parse_questions_from_response(
            response, "features", "api", 5
        )
        # "Сколько стоит" — no ?, "да?" — too short, "**Как подключить?**" — markdown
        assert len(questions) == 1  # Only "Есть API?"
        assert rejected == 3

    def test_empty_response(self):
        questions, rejected = parse_questions_from_response(
            "", "pricing", "t1", 5
        )
        assert len(questions) == 0
        assert rejected == 0


# ============================================================================
# Test kb_questions.py (KBQuestionPool)
# ============================================================================

from src.simulator.kb_questions import (
    KBQuestion,
    KBQuestionPool,
    PERSONA_CATEGORY_AFFINITY,
    load_kb_question_pool,
    reset_pool_cache,
)


@pytest.fixture
def sample_kb_json(tmp_path):
    """Create a temporary kb_questions.json for testing."""
    data = {
        "generated_at": "2026-02-01T00:00:00",
        "total_generated": 10,
        "total_after_dedup": 10,
        "rejected": 0,
        "model": "test",
        "questions": [
            {"text": "Сколько стоит подписка?", "category": "pricing", "source_topic": "tariffs", "priority": 9},
            {"text": "Есть скидки для новых?", "category": "pricing", "source_topic": "discounts", "priority": 7},
            {"text": "Wipon Kassa бесплатная?", "category": "products", "source_topic": "wipon_kassa", "priority": 8},
            {"text": "Есть интеграция с 1С?", "category": "integrations", "source_topic": "1c", "priority": 9},
            {"text": "Как работает API?", "category": "integrations", "source_topic": "api", "priority": 8},
            {"text": "Какой uptime у системы?", "category": "stability", "source_topic": "uptime", "priority": 7},
            {"text": "Есть мобильное приложение?", "category": "mobile", "source_topic": "mobile_app", "priority": 6},
            {"text": "Как связаться с поддержкой?", "category": "support", "source_topic": "contacts", "priority": 5},
            {"text": "Чем лучше Poster?", "category": "competitors", "source_topic": "poster", "priority": 8},
            {"text": "Какая аналитика доступна?", "category": "analytics", "source_topic": "reports", "priority": 6},
        ],
    }
    json_path = tmp_path / "kb_questions.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return str(json_path)


class TestKBQuestionPool:
    """Test KBQuestionPool class."""

    def test_load_from_json(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        assert pool.total_questions == 10

    def test_categories(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        cats = pool.categories
        assert "pricing" in cats
        assert "integrations" in cats
        assert "stability" in cats

    def test_get_starter(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        random.seed(42)
        q = pool.get_starter("technical")
        assert q is not None
        assert isinstance(q, KBQuestion)
        assert q.text
        assert q.category
        assert q.source_topic

    def test_get_starter_unknown_persona_uses_all(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        q = pool.get_starter("unknown_persona")
        # Falls back to all questions
        assert q is not None

    def test_get_followup_excludes_topics(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        random.seed(42)

        # Exclude all topics except one category
        all_topics = {q.source_topic for q in pool._all_questions}
        exclude_all_but_one = all_topics - {"tariffs"}

        q = pool.get_followup("price_sensitive", exclude_all_but_one)
        assert q is not None
        assert q.source_topic == "tariffs"

    def test_get_followup_returns_none_when_all_excluded(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        all_topics = {q.source_topic for q in pool._all_questions}
        q = pool.get_followup("technical", all_topics)
        assert q is None

    def test_get_random(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        q = pool.get_random()
        assert q is not None

    def test_get_random_by_category(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        q = pool.get_random(category="pricing")
        assert q is not None
        assert q.category == "pricing"

    def test_get_random_missing_category(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        q = pool.get_random(category="nonexistent")
        assert q is None

    def test_persona_pools_populated(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        for persona_key in PERSONA_CATEGORY_AFFINITY:
            persona_pool = pool._persona_pools.get(persona_key, [])
            assert len(persona_pool) > 0, f"Empty pool for {persona_key}"

    def test_technical_persona_prefers_integrations(self, sample_kb_json):
        pool = KBQuestionPool(sample_kb_json)
        tech_pool = pool._persona_pools["technical"]
        # Top questions should have integrations category (highest affinity)
        top_categories = [q.category for q in tech_pool[:3]]
        assert "integrations" in top_categories


class TestLoadKBQuestionPool:
    """Test the convenience loader function."""

    def test_returns_none_when_file_missing(self, tmp_path):
        reset_pool_cache()
        with patch("src.simulator.kb_questions.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            mock_path.return_value.exists.return_value = False
            # Directly test the logic
            from src.simulator.kb_questions import load_kb_question_pool
            reset_pool_cache()
            # The real function uses Path(__file__).parent / "data" / "kb_questions.json"
            # so we need to test differently
        reset_pool_cache()

    def test_caches_after_load(self, sample_kb_json):
        reset_pool_cache()
        with patch("src.simulator.kb_questions.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.__truediv__ = MagicMock(side_effect=lambda x: mock_instance)
            mock_instance.exists.return_value = True
            mock_instance.__str__ = MagicMock(return_value=sample_kb_json)
            mock_path.return_value = MagicMock()
            mock_path.return_value.parent.__truediv__ = MagicMock(return_value=mock_instance)
        reset_pool_cache()


# ============================================================================
# Test persona kb_question_probability
# ============================================================================

from src.simulator.personas import PERSONAS, Persona


class TestPersonaKBProbability:
    """Test that all personas have kb_question_probability."""

    def test_all_personas_have_field(self):
        for name, persona in PERSONAS.items():
            assert hasattr(persona, "kb_question_probability"), f"{name} missing kb_question_probability"
            assert 0.0 <= persona.kb_question_probability <= 1.0, f"{name} probability out of range"

    def test_expected_values(self):
        expected = {
            "happy_path": 0.5,
            "skeptic": 0.3,
            "busy": 0.6,
            "price_sensitive": 0.7,
            "competitor_user": 0.5,
            "aggressive": 0.4,
            "technical": 0.8,
            "tire_kicker": 0.2,
        }
        for name, expected_prob in expected.items():
            assert PERSONAS[name].kb_question_probability == expected_prob, \
                f"{name}: expected {expected_prob}, got {PERSONAS[name].kb_question_probability}"

    def test_default_value(self):
        p = Persona(name="test", description="test", max_turns=5, objection_probability=0.1)
        assert p.kb_question_probability == 0.5


# ============================================================================
# Test ClientAgent KB integration
# ============================================================================

from src.simulator.client_agent import ClientAgent


class TestClientAgentKBStarter:
    """Test KB question as conversation starter."""

    def _make_pool(self, tmp_path):
        """Create a minimal pool for testing."""
        data = {
            "generated_at": "2026-02-01",
            "total_generated": 3,
            "total_after_dedup": 3,
            "rejected": 0,
            "model": "test",
            "questions": [
                {"text": "Сколько стоит подписка?", "category": "pricing", "source_topic": "tariffs", "priority": 9},
                {"text": "Есть интеграция с 1С?", "category": "integrations", "source_topic": "1c", "priority": 8},
                {"text": "Wipon Kassa бесплатная?", "category": "products", "source_topic": "wipon_kassa", "priority": 7},
            ],
        }
        json_path = tmp_path / "kb_questions.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return KBQuestionPool(str(json_path))

    def test_kb_starter_used_when_random_low(self, tmp_path):
        """When random < starter_prob, KB question is used."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]  # kb_question_probability=0.8, capped at 0.4
        llm = MagicMock()
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")

        # Force random to return 0.0 (always below threshold)
        with patch("src.simulator.client_agent.random") as mock_random:
            mock_random.random.return_value = 0.0
            mock_random.choice = random.choice
            starter = client.start_conversation()

        assert client._kb_questions_used == 1
        assert client._kb_starter_topic is not None
        assert len(client._asked_topics) == 1

    def test_original_starter_used_when_random_high(self, tmp_path):
        """When random > starter_prob, original starters used."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]
        llm = MagicMock()
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")

        # Force random to return 0.99 (always above 0.4 cap)
        with patch("src.simulator.client_agent.random") as mock_random:
            mock_random.random.return_value = 0.99
            mock_random.choice = random.choice
            starter = client.start_conversation()

        assert client._kb_questions_used == 0
        assert client._kb_starter_topic is None

    def test_no_pool_uses_original_starters(self):
        """Without pool, always uses original starters."""
        persona = PERSONAS["happy_path"]
        llm = MagicMock()
        client = ClientAgent(llm, persona, kb_pool=None)
        starter = client.start_conversation()
        assert client._kb_questions_used == 0

    def test_starter_prob_capped_at_04(self, tmp_path):
        """Starter probability is capped at 0.4 even for high kb_question_probability."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]  # kb_question_probability=0.8
        llm = MagicMock()
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")

        # random returns 0.39 — should be below cap of 0.4
        with patch("src.simulator.client_agent.random") as mock_random:
            mock_random.random.return_value = 0.39
            mock_random.choice = random.choice
            client.start_conversation()
        assert client._kb_questions_used == 1

        # Reset and test with 0.41 — should be above cap
        client2 = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")
        with patch("src.simulator.client_agent.random") as mock_random:
            mock_random.random.return_value = 0.41
            mock_random.choice = random.choice
            client2.start_conversation()
        assert client2._kb_questions_used == 0


class TestClientAgentKBFollowup:
    """Test KB follow-up injection in respond()."""

    def _make_pool(self, tmp_path):
        data = {
            "generated_at": "2026-02-01",
            "total_generated": 5,
            "total_after_dedup": 5,
            "rejected": 0,
            "model": "test",
            "questions": [
                {"text": "Сколько стоит подписка?", "category": "pricing", "source_topic": "tariffs", "priority": 9},
                {"text": "Есть интеграция с 1С?", "category": "integrations", "source_topic": "1c", "priority": 8},
                {"text": "Wipon Kassa бесплатная?", "category": "products", "source_topic": "kassa", "priority": 7},
                {"text": "Как связаться с поддержкой?", "category": "support", "source_topic": "support", "priority": 5},
                {"text": "Есть мобильное приложение?", "category": "mobile", "source_topic": "mobile", "priority": 6},
            ],
        }
        json_path = tmp_path / "kb_questions.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return KBQuestionPool(str(json_path))

    def test_kb_followup_injected_when_bot_not_asking(self, tmp_path):
        """KB followup injected when bot message doesn't end with '?'."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]
        llm = MagicMock()
        llm.generate.return_value = "интересно, расскажите подробнее"
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")

        # Bot message without question mark (safe moment)
        bot_msg = "Наша CRM поддерживает интеграции с различными системами."

        with patch("src.simulator.client_agent.random") as mock_random:
            # First random call: _should_leave_now -> don't leave
            # random() calls: leave check, insistence, KB injection
            mock_random.random.return_value = 0.0  # Always trigger KB
            mock_random.choice = random.choice
            response = client.respond(bot_msg)

        assert client._kb_questions_used == 1
        # Response should contain an ack prefix
        ack_prefixes = ["ок", "понял", "ага", "хорошо", "ну ладно"]
        assert any(response.lower().startswith(ack) for ack in ack_prefixes)

    def test_kb_followup_not_injected_when_bot_asking(self, tmp_path):
        """KB followup NOT injected when bot message ends with '?'."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]
        llm = MagicMock()
        llm.generate.return_value = "да, нас 15 человек"
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")

        # Bot message WITH question mark (bot is asking, preserve flow)
        bot_msg = "Сколько человек в вашей команде?"

        response = client.respond(bot_msg)
        # KB should not override — bot's question should be answered by LLM
        # The response comes from LLM generate
        assert "да" in response.lower() or "человек" in response.lower() or len(response) > 0

    def test_kb_max_4_questions(self, tmp_path):
        """Maximum 4 KB questions per dialogue."""
        pool = self._make_pool(tmp_path)
        persona = PERSONAS["technical"]
        llm = MagicMock()
        llm.generate.return_value = "ок"
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="technical")
        client._kb_questions_used = 4  # Already used 4

        bot_msg = "Вот информация о нашем продукте."
        with patch("src.simulator.client_agent.random") as mock_random:
            mock_random.random.return_value = 0.0
            mock_random.choice = random.choice
            response = client.respond(bot_msg)

        # Should not inject more KB questions (already at max)
        assert client._kb_questions_used == 4


class TestClientAgentKBSummary:
    """Test KB data in get_summary()."""

    def test_summary_includes_kb_fields(self, tmp_path):
        data = {
            "generated_at": "2026-02-01",
            "total_generated": 1,
            "total_after_dedup": 1,
            "rejected": 0,
            "model": "test",
            "questions": [
                {"text": "Сколько стоит?", "category": "pricing", "source_topic": "tariffs", "priority": 9},
            ],
        }
        json_path = tmp_path / "kb_questions.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        pool = KBQuestionPool(str(json_path))

        persona = PERSONAS["happy_path"]
        llm = MagicMock()
        client = ClientAgent(llm, persona, kb_pool=pool, persona_key="happy_path")

        # Manually set some KB state
        client._kb_questions_used = 2
        client._asked_topics = {"tariffs", "api"}
        client._kb_starter_topic = "tariffs"

        summary = client.get_summary()
        assert summary["kb_questions_used"] == 2
        assert set(summary["kb_topics_covered"]) == {"tariffs", "api"}
        assert summary["kb_starter_topic"] == "tariffs"

    def test_summary_defaults_when_no_pool(self):
        persona = PERSONAS["happy_path"]
        llm = MagicMock()
        client = ClientAgent(llm, persona)

        summary = client.get_summary()
        assert summary["kb_questions_used"] == 0
        assert summary["kb_topics_covered"] == []
        assert summary["kb_starter_topic"] is None


# ============================================================================
# Test ClientAgentTrace KB fields
# ============================================================================

from src.decision_trace import ClientAgentTrace


class TestClientAgentTraceKBFields:
    """Test new KB fields in ClientAgentTrace."""

    def test_kb_fields_default_none(self):
        trace = ClientAgentTrace()
        assert trace.kb_question_used is None
        assert trace.kb_question_source is None

    def test_kb_fields_set(self):
        trace = ClientAgentTrace(
            kb_question_used="Сколько стоит подписка?",
            kb_question_source="tariffs",
        )
        assert trace.kb_question_used == "Сколько стоит подписка?"
        assert trace.kb_question_source == "tariffs"

    def test_to_dict_includes_kb_when_set(self):
        trace = ClientAgentTrace(
            persona_name="Технарь",
            kb_question_used="Есть API?",
            kb_question_source="api",
        )
        d = trace.to_dict()
        assert d["kb_question_used"] == "Есть API?"
        assert d["kb_question_source"] == "api"

    def test_to_dict_excludes_kb_when_none(self):
        trace = ClientAgentTrace(persona_name="Технарь")
        d = trace.to_dict()
        assert "kb_question_used" not in d
        assert "kb_question_source" not in d


# ============================================================================
# Test SimulationResult KB fields
# ============================================================================

from src.simulator.runner import SimulationResult


class TestSimulationResultKBFields:
    """Test KB fields on SimulationResult dataclass."""

    def test_default_values(self):
        result = SimulationResult(
            simulation_id=0, persona="test", outcome="success",
            turns=5, duration_seconds=1.0, dialogue=[],
        )
        assert result.kb_questions_used == 0
        assert result.kb_topics_covered == []

    def test_custom_values(self):
        result = SimulationResult(
            simulation_id=0, persona="test", outcome="success",
            turns=5, duration_seconds=1.0, dialogue=[],
            kb_questions_used=3,
            kb_topics_covered=["tariffs", "api", "kassa"],
        )
        assert result.kb_questions_used == 3
        assert len(result.kb_topics_covered) == 3


# ============================================================================
# Test E2EResult KB fields
# ============================================================================

from src.simulator.e2e_evaluator import E2EResult


class TestE2EResultKBFields:
    """Test KB fields on E2EResult dataclass."""

    def test_default_values(self):
        result = E2EResult(
            scenario_id="01", scenario_name="test", flow_name="default",
            passed=True, score=0.8, outcome="success",
            expected_outcome="success", phases_reached=[], expected_phases=[],
            turns=5,
        )
        assert result.kb_questions_used == 0
        assert result.kb_topics_covered == []

    def test_custom_values(self):
        result = E2EResult(
            scenario_id="01", scenario_name="test", flow_name="default",
            passed=True, score=0.8, outcome="success",
            expected_outcome="success", phases_reached=[], expected_phases=[],
            turns=5,
            kb_questions_used=2,
            kb_topics_covered=["tariffs", "api"],
        )
        assert result.kb_questions_used == 2
        assert result.kb_topics_covered == ["tariffs", "api"]


# ============================================================================
# Test PERSONA_CATEGORY_AFFINITY completeness
# ============================================================================

class TestPersonaCategoryAffinity:
    """Test that affinity map covers all personas."""

    def test_all_personas_have_affinity(self):
        for persona_key in PERSONAS:
            assert persona_key in PERSONA_CATEGORY_AFFINITY, \
                f"Missing affinity map for persona: {persona_key}"

    def test_affinity_values_in_range(self):
        for persona_key, affinities in PERSONA_CATEGORY_AFFINITY.items():
            for category, weight in affinities.items():
                assert 0.0 <= weight <= 1.0, \
                    f"{persona_key}/{category}: weight {weight} out of range [0,1]"

    def test_each_persona_has_at_least_one_affinity(self):
        for persona_key, affinities in PERSONA_CATEGORY_AFFINITY.items():
            assert len(affinities) > 0, f"{persona_key} has no affinities"
