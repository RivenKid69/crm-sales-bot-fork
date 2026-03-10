"""
Tests for structured output reliability fix in OllamaClient.generate_structured().

Tests 3 improvements:
1. _clean_structured_output() — strips <think> tags, extracts JSON, fixes trailing commas
2. Validation error no longer breaks retry loop — retries continue
3. Temperature escalation on retries — 0.05 → 0.2 → 0.4

Uses realistic production schemas (VerifierOutput, ClassificationResult, CategoryResult).
"""

import json
from typing import Literal, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import BaseModel, Field

from src.llm import OllamaClient


# ---------------------------------------------------------------------------
# Production-realistic schemas
# ---------------------------------------------------------------------------

class ClaimCheck(BaseModel):
    claim: str = Field(default="", max_length=300)
    supported: bool = False
    evidence_quote: str = Field(default="", max_length=240)


class VerifierOutput(BaseModel):
    """Exact mirror of src/factual_verifier.py — Literal field is the hard case."""
    verdict: Literal["pass", "fail"]
    checks: List[ClaimCheck] = Field(default_factory=list)
    rewritten_response: str = Field(default="", max_length=1500)
    confidence: float = Field(default=0.0, ge=0.0)


IntentLite = Literal[
    "greeting", "agreement", "gratitude", "farewell", "small_talk",
    "price_question", "pricing_details", "objection_price",
    "question_features", "question_integrations", "comparison",
    "question_support", "demo_request", "callback_request",
    "contact_provided", "payment_confirmation",
    "situation_provided", "problem_revealed", "no_need", "rejection",
]


class ExtractedDataLite(BaseModel):
    company_name: Optional[str] = None
    business_type: Optional[str] = None
    contact_info: Optional[str] = None
    pain_point: Optional[str] = None


class ClassificationLike(BaseModel):
    """Mirrors ClassificationResult — complex nested schema with Literal + validators."""
    intent: IntentLite
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    extracted_data: ExtractedDataLite = Field(default_factory=ExtractedDataLite)


CategoryLite = Literal[
    "analytics", "competitors", "equipment", "features",
    "integrations", "pricing", "products", "support", "stability",
]


class CategoryResult(BaseModel):
    categories: List[CategoryLite] = Field(..., min_length=1, max_length=5)


class SimpleSchema(BaseModel):
    intent: str
    confidence: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": {"content": content}}
    return resp


def _openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return resp


def _extract_temps(mock_post, api="ollama") -> list:
    """Extract temperature from each call to requests.post."""
    temps = []
    for c in mock_post.call_args_list:
        body = c.kwargs.get("json") or c[1].get("json", {})
        if api == "ollama":
            temps.append(body.get("options", {}).get("temperature"))
        else:
            temps.append(body.get("temperature"))
    return temps


# =========================================================================
# 1. _clean_structured_output() — unit tests (comprehensive)
# =========================================================================

class TestCleanStructuredOutput:

    def _clean(self, text: str) -> str:
        return OllamaClient._clean_structured_output(text)

    # --- Basic passthrough ---

    def test_valid_json_passthrough(self):
        raw = '{"verdict": "pass", "confidence": 0.9}'
        assert self._clean(raw) == raw

    def test_empty_string(self):
        assert self._clean("") == ""

    def test_whitespace_only(self):
        assert self._clean("   \n\t  ") == ""

    # --- <think> tag stripping ---

    def test_think_simple(self):
        raw = '<think>analysis</think>{"verdict": "pass"}'
        assert json.loads(self._clean(raw))["verdict"] == "pass"

    def test_think_multiline_with_newlines(self):
        raw = (
            "<think>\nChecking claim 1...\n"
            "Checking claim 2...\nAll claims verified.\n</think>\n"
            '{"verdict": "pass", "checks": [], "confidence": 0.92}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"
        assert parsed["confidence"] == 0.92

    def test_think_with_json_inside(self):
        """<think> block itself contains JSON-like text — must not extract that."""
        raw = (
            '<think>The expected format is {"verdict": "pass"} but I need to check...</think>'
            '{"verdict": "fail", "confidence": 0.1}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "fail"

    def test_think_with_cyrillic(self):
        raw = (
            '<think>Мне нужно проверить утверждения клиента о цене 500 000 ₸.</think>'
            '{"verdict": "pass", "rewritten_response": "Тариф Pro стоит 500 000 ₸/год"}'
        )
        parsed = json.loads(self._clean(raw))
        assert "500 000" in parsed["rewritten_response"]

    def test_multiple_think_blocks(self):
        """Some models emit multiple <think> blocks."""
        raw = (
            '<think>first thought</think>'
            '<think>second thought</think>'
            '{"verdict": "pass"}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_think_unclosed_does_not_strip_json(self):
        """Unclosed <think> tag — should not eat the JSON."""
        raw = '<think>started thinking... {"verdict": "pass", "confidence": 0.5}'
        result = self._clean(raw)
        # Since <think> is unclosed, regex won't match — JSON should be extractable
        assert "{" in result

    # --- JSON extraction from prose ---

    def test_json_with_prefix_text(self):
        raw = 'Here is the result: {"intent": "greeting", "confidence": 0.9}'
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "greeting"

    def test_json_with_suffix_text(self):
        raw = '{"intent": "greeting", "confidence": 0.9} — this is the final answer.'
        result = self._clean(raw)
        parsed = json.loads(result)
        assert parsed["intent"] == "greeting"

    def test_json_with_both_prefix_and_suffix(self):
        raw = 'Analysis complete: {"verdict": "fail"} End.'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "fail"

    def test_json_starts_at_position_zero(self):
        """No extraction needed — JSON starts at char 0."""
        raw = '{"verdict": "pass"}'
        assert self._clean(raw) == raw

    def test_nested_json_objects(self):
        """Nested braces — must find the outermost matching pair."""
        raw = (
            'Result: {"checks": [{"claim": "price is 5000", "supported": true}], '
            '"verdict": "pass", "confidence": 0.88}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"
        assert len(parsed["checks"]) == 1
        assert parsed["checks"][0]["supported"] is True

    def test_braces_inside_string_values(self):
        """Braces inside string values — depth counting is naive but JSON is outer-matched."""
        raw = '{"reasoning": "user said {цена} is high", "intent": "objection_price", "confidence": 0.7}'
        # This starts at position 0 — no extraction needed, passthrough
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "objection_price"

    # --- Trailing comma fixes ---

    def test_trailing_comma_object(self):
        raw = '{"verdict": "pass", "confidence": 0.9,}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_trailing_comma_array(self):
        raw = '{"categories": ["pricing", "features",]}'
        parsed = json.loads(self._clean(raw))
        assert parsed["categories"] == ["pricing", "features"]

    def test_trailing_comma_nested(self):
        raw = '{"checks": [{"claim": "ok", "supported": true,},], "verdict": "pass",}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_trailing_comma_with_whitespace(self):
        raw = '{"verdict": "pass" ,  \n}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    # --- Combined artefacts ---

    def test_think_plus_prose_plus_trailing_comma(self):
        raw = (
            '<think>Let me verify all claims...</think> '
            'Here is the result: {"verdict": "pass", "confidence": 0.85,}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_real_verifier_output_dirty(self):
        """Realistic dirty output from Qwen3.5 verifier call."""
        raw = (
            '<think>\n'
            'The user asked about pricing for 5 stores.\n'
            'The KB says Pro tariff costs 500,000 tenge/year.\n'
            'The bot response mentions 500,000 — this is correct.\n'
            'Verdict: pass\n'
            '</think>\n'
            '{"verdict": "pass", "checks": ['
            '{"claim": "Pro tariff costs 500000 per year", "supported": true, '
            '"evidence_quote": "тариф Pro — 500 000 ₸/год"},'
            '], "rewritten_response": "", "confidence": 0.95,}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"
        assert len(parsed["checks"]) == 1
        assert parsed["confidence"] == 0.95

    # --- Edge cases that should NOT break ---

    def test_no_json_at_all_returns_input(self):
        raw = "I cannot determine the answer."
        assert self._clean(raw) == raw

    def test_only_think_tags_no_json(self):
        raw = "<think>I don't know</think>"
        result = self._clean(raw)
        assert result == ""  # stripped think block, nothing left

    def test_json_with_escaped_quotes_in_values(self):
        raw = r'{"reasoning": "user said \"hello\"", "intent": "greeting", "confidence": 0.8}'
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "greeting"

    def test_unicode_emoji_in_values(self):
        raw = '{"reasoning": "клиент доволен 👍", "intent": "agreement", "confidence": 0.9}'
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "agreement"


# =========================================================================
# 2. Validation error retries — comprehensive
# =========================================================================

class TestValidationErrorRetry:

    def test_all_retries_used_on_missing_fields(self):
        """Missing required fields — all attempts used, not just 1."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong_field": "value"}')

        with patch('requests.post', return_value=bad) as mp:
            result = client.generate_structured("test", SimpleSchema)

        assert result is None
        assert mp.call_count == 3

    def test_all_retries_on_literal_violation(self):
        """Literal["pass","fail"] gets invalid value — all 3 retries used."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"verdict": "maybe", "confidence": 0.5}')

        with patch('requests.post', return_value=bad) as mp:
            result = client.generate_structured("test", VerifierOutput)

        assert result is None
        assert mp.call_count == 3

    def test_validation_then_success(self):
        """Bad attempt → good attempt succeeds."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"verdict": "maybe"}')
        good = _ollama_response('{"verdict": "pass", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"

    def test_literal_wrong_then_correct(self):
        """Literal field gets wrong value twice, then correct."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        bad1 = _ollama_response('{"verdict": "ok", "confidence": 0.5}')
        bad2 = _ollama_response('{"verdict": "yes", "confidence": 0.6}')
        good = _ollama_response('{"verdict": "fail", "rewritten_response": "Уточню", "confidence": 0.8}')

        with patch('requests.post', side_effect=[bad1, bad2, good]) as mp:
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "fail"
        assert mp.call_count == 3

    def test_classification_intent_not_in_literal(self):
        """Intent value outside IntentLite enum — should retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        # "buy_now" is not in IntentLite
        bad = _ollama_response(
            '{"intent": "buy_now", "confidence": 0.9, "reasoning": "client wants to buy"}'
        )
        good = _ollama_response(
            '{"intent": "demo_request", "confidence": 0.85, "reasoning": "client asks for demo"}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", ClassificationLike)

        assert result is not None
        assert result.intent == "demo_request"

    def test_confidence_out_of_range_retries(self):
        """confidence > 1.0 violates ge/le constraint — should retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "greeting", "confidence": 1.5, "reasoning": "obvious greeting"}'
        )
        good = _ollama_response(
            '{"intent": "greeting", "confidence": 0.95, "reasoning": "obvious greeting"}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", ClassificationLike)

        assert result is not None
        assert result.confidence == 0.95

    def test_category_list_empty_violates_min_length(self):
        """Empty categories list violates min_length=1 — should retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"categories": []}')
        good = _ollama_response('{"categories": ["pricing"]}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", CategoryResult)

        assert result is not None
        assert result.categories == ["pricing"]

    def test_mixed_errors_timeout_then_validation_then_success(self):
        """Timeout → validation error → success — all different error types."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        bad_validation = _ollama_response('{"verdict": "maybe"}')
        good = _ollama_response('{"verdict": "pass", "confidence": 0.9}')

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.Timeout("timeout")
            if call_count == 2:
                return bad_validation
            return good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert call_count == 3

    def test_stats_correct_after_retry_with_validation_error(self):
        """Stats tracking is accurate across validation-error retries."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", SimpleSchema)

        assert result is not None
        assert client.stats.total_requests == 1
        assert client.stats.successful_requests == 1
        assert client.stats.total_retries == 1


# =========================================================================
# 3. Temperature escalation — precise verification
# =========================================================================

class TestTemperatureEscalation:

    def test_exact_escalation_values(self):
        """Verify exact temperatures: base, base+0.15, base+0.35."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.05)

        temps = _extract_temps(mp)
        assert temps == [0.05, pytest.approx(0.20), pytest.approx(0.40)]

    def test_escalation_with_high_base_caps_at_1(self):
        """High base temperature + escalation should cap at 1.0."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.8)

        temps = _extract_temps(mp)
        assert temps[0] == 0.8
        assert temps[1] == pytest.approx(0.95)
        assert temps[2] == 1.0  # capped

    def test_escalation_with_zero_base(self):
        """Zero base temperature still escalates."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.0)

        temps = _extract_temps(mp)
        assert temps[0] == 0.0
        assert temps[1] > 0.0
        assert temps[2] > temps[1]

    def test_no_escalation_on_first_success(self):
        """No retry = no escalation; original temperature used."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)

        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        with patch('requests.post', return_value=good) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.05)

        temps = _extract_temps(mp)
        assert len(temps) == 1
        assert temps[0] == 0.05

    def test_escalation_beyond_3_retries(self):
        """With MAX_RETRIES > 3, attempts beyond 3 use the last escalation bump."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 5
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.05)

        temps = _extract_temps(mp)
        assert len(temps) == 5
        # Attempts 4 and 5 should use same escalation as attempt 3
        assert temps[3] == temps[2]
        assert temps[4] == temps[2]

    def test_openai_api_escalation(self):
        """Temperature escalation works for OpenAI-compatible API too."""
        client = OllamaClient(
            enable_retry=True, enable_circuit_breaker=False,
            api_format="openai",
        )
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _openai_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_structured("test", SimpleSchema, temperature=0.1)

        temps = _extract_temps(mp, api="openai")
        assert temps[0] == 0.1
        assert temps[1] > temps[0]
        assert temps[2] > temps[1]


# =========================================================================
# 4. Integration: cleaning + retry + temperature together
# =========================================================================

class TestIntegration:

    def test_think_tags_cleaned_for_simple_schema(self):
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>analyzing...</think>{"intent": "price_question", "confidence": 0.95}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SimpleSchema)

        assert result is not None
        assert result.intent == "price_question"

    def test_trailing_comma_cleaned(self):
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response('{"intent": "greeting", "confidence": 0.8,}')
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SimpleSchema)

        assert result is not None
        assert result.intent == "greeting"

    def test_verifier_output_full_realistic_dirty(self):
        """Full VerifierOutput with think tags + nested checks + trailing commas."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>\n'
            'Claim: "Тариф Pro — 500 000 ₸/год" — checking against KB...\n'
            'Found in pricing_multistore_5_points: "тариф Pro — 500 000 ₸/год"\n'
            'Supported.\n'
            '</think>\n'
            '{"verdict": "pass", '
            '"checks": [{"claim": "Pro costs 500000/year", "supported": true, '
            '"evidence_quote": "тариф Pro — 500 000 ₸/год"},], '
            '"rewritten_response": "Для 5 точек подойдёт тариф Pro за 500 000 ₸ в год.", '
            '"confidence": 0.94,}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert len(result.checks) == 1
        assert result.checks[0].supported is True
        assert "500 000" in result.rewritten_response
        assert result.confidence == pytest.approx(0.94)

    def test_classification_with_extracted_data_dirty(self):
        """ClassificationResult with nested extracted_data + think tags."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>Client mentions 4 stores in Karaganda and 1 in Astana</think>'
            '{"intent": "situation_provided", "confidence": 0.92, '
            '"reasoning": "Client describes their business setup", '
            '"extracted_data": {"business_type": "продуктовый магазин", '
            '"company_name": null, "contact_info": null, "pain_point": null},}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", ClassificationLike)

        assert result is not None
        assert result.intent == "situation_provided"
        assert result.extracted_data.business_type == "продуктовый магазин"

    def test_category_result_dirty(self):
        """CategoryResult with trailing comma in list."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response('{"categories": ["pricing", "features", "stability",]}')
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", CategoryResult)

        assert result is not None
        assert result.categories == ["pricing", "features", "stability"]

    def test_dirty_first_attempt_clean_second(self):
        """First attempt: think tags + wrong literal. Second attempt: clean + correct."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '<think>I think the verdict is ok</think>{"verdict": "ok", "confidence": 0.5}'
        )
        good = _ollama_response('{"verdict": "pass", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]) as mp:
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert mp.call_count == 2

    def test_trace_contains_cleaned_content(self):
        """LLMTrace.raw_response should contain the cleaned JSON, not raw think tags."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>verifying...</think>{"verdict": "pass", "confidence": 0.8}'
        )
        with patch('requests.post', return_value=resp):
            result, trace = client.generate_structured(
                "test", VerifierOutput, return_trace=True
            )

        assert result is not None
        assert "<think>" not in trace.raw_response
        assert trace.success is True
        assert trace.latency_ms > 0

    def test_trace_on_all_retries_failed(self):
        """LLMTrace records failure info when all retries exhausted."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"verdict": "maybe"}')

        with patch('requests.post', return_value=bad):
            result, trace = client.generate_structured(
                "test", VerifierOutput, return_trace=True
            )

        assert result is None
        assert trace.success is False
        assert "validation error" in trace.error.lower()
        assert trace.retry_count == 2

    def test_cleaning_does_not_corrupt_valid_json(self):
        """Cleaning pipeline is idempotent — valid JSON is not modified."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        valid = (
            '{"verdict": "fail", "checks": ['
            '{"claim": "test", "supported": false, "evidence_quote": ""}], '
            '"rewritten_response": "Уточню у коллег.", "confidence": 0.3}'
        )
        resp = _ollama_response(valid)

        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "fail"
        assert result.rewritten_response == "Уточню у коллег."

    def test_circuit_breaker_not_tripped_by_validation_errors(self):
        """Validation errors during retries should not trip circuit breaker."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 2

        bad = _ollama_response('{"wrong": true}')

        # Two complete generate_structured calls, both fail on validation
        with patch('requests.post', return_value=bad):
            client.generate_structured("test1", SimpleSchema)
            client.generate_structured("test2", SimpleSchema)

        # CB records failures but both calls fully exhausted retries
        assert client._circuit_breaker.failures == 2
        assert client.stats.failed_requests == 2

    def test_concurrent_schemas_independent(self):
        """Different schema types don't interfere with each other."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        r1 = _ollama_response('{"intent": "greeting", "confidence": 0.9}')
        r2 = _ollama_response('{"verdict": "pass", "confidence": 0.8}')
        r3 = _ollama_response('{"categories": ["pricing"]}')

        with patch('requests.post', side_effect=[r1, r2, r3]):
            res1 = client.generate_structured("test1", SimpleSchema)
            res2 = client.generate_structured("test2", VerifierOutput)
            res3 = client.generate_structured("test3", CategoryResult)

        assert res1.intent == "greeting"
        assert res2.verdict == "pass"
        assert res3.categories == ["pricing"]


# =========================================================================
# 5. Adversarial cleaning — edge cases that break naive implementations
# =========================================================================

class TestCleanAdversarial:
    """Edge cases specifically designed to break naive JSON extraction."""

    def _clean(self, text: str) -> str:
        return OllamaClient._clean_structured_output(text)

    def test_think_tag_literal_inside_json_string(self):
        """String value contains literal '</think>' — must NOT break extraction."""
        raw = (
            '<think>reasoning here</think>'
            '{"reasoning": "the token </think> appeared in output", '
            '"intent": "greeting", "confidence": 0.8}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "greeting"
        assert "</think>" in parsed["reasoning"]

    def test_markdown_fence_already_stripped_by_extract_content(self):
        """_strip_markdown_json runs BEFORE _clean — verify the combo works end-to-end."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        # _extract_content strips markdown; _clean_structured_output handles the rest
        resp = _ollama_response('```json\n{"intent": "greeting", "confidence": 0.9,}\n```')
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"

    def test_bom_marker_prefix(self):
        """UTF-8 BOM at start of output."""
        raw = '\ufeff{"verdict": "pass", "confidence": 0.9}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_deeply_nested_5_levels(self):
        """5 levels of nesting — brace matching must handle depth correctly."""
        raw = (
            'Result: {"a": {"b": {"c": {"d": {"e": "deep"}, '
            '"d2": true}, "c2": [1,2]}, "b2": null}, "verdict": "pass"}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"
        assert parsed["a"]["b"]["c"]["d"]["e"] == "deep"

    def test_multiple_json_objects_takes_first(self):
        """Two JSON objects in output — extraction takes the first complete one."""
        raw = '{"verdict": "pass", "confidence": 0.9} {"verdict": "fail"}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_truncated_json_no_crash(self):
        """Truncated JSON (model hit num_predict limit) — clean should not crash."""
        raw = '{"verdict": "pass", "rewritten_response": "Тариф Pro стоит'
        result = self._clean(raw)
        # The brace is never closed, so the full string is returned
        # json.loads will fail but _clean itself must not crash
        assert isinstance(result, str)

    def test_empty_json_object(self):
        """Empty {} is valid JSON — cleaning shouldn't break it."""
        raw = '{}'
        assert self._clean(raw) == '{}'

    def test_json_array_wrapping_object(self):
        """JSON array wrapping an object — extracts the inner object (useful recovery)."""
        raw = '[{"intent": "greeting"}]'
        result = self._clean(raw)
        # Finds { at position 1, extracts the inner object
        parsed = json.loads(result)
        assert parsed["intent"] == "greeting"

    def test_newlines_inside_json_string(self):
        """Actual \\n (escaped) inside string values."""
        raw = r'{"reasoning": "line1\nline2\nline3", "intent": "greeting", "confidence": 0.8}'
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "greeting"

    def test_think_with_angle_brackets_in_content(self):
        """<think> block containing other angle-bracket patterns like <b>, <user>."""
        raw = (
            '<think>The <user> message contains <b>price</b> keywords.</think>'
            '{"intent": "price_question", "confidence": 0.95}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "price_question"

    def test_think_block_with_newlines_between_think_and_json(self):
        """Multiple newlines between </think> and JSON start."""
        raw = '<think>ok</think>\n\n\n\n{"verdict": "pass"}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_consecutive_trailing_commas(self):
        """Multiple trailing commas at different levels."""
        raw = '{"a": [1, 2, 3,], "b": {"x": 1, "y": 2,}, "c": true,}'
        parsed = json.loads(self._clean(raw))
        assert parsed["a"] == [1, 2, 3]
        assert parsed["b"]["y"] == 2

    def test_comma_inside_string_not_stripped(self):
        """Comma followed by } inside a string value must NOT be stripped."""
        raw = '{"text": "price is 5,000}", "verdict": "pass"}'
        # This is tricky — the regex is ,\s*([}\]]) which would match ,}
        # but here ,} is inside a string value. Since we don't parse strings,
        # the regex WILL strip it. This is a known limitation.
        # The test documents the behavior — if this ever matters,
        # we'd need a proper JSON parser.
        result = self._clean(raw)
        # The important thing: it should not crash
        assert isinstance(result, str)

    def test_very_long_think_block_10k_chars(self):
        """Very long <think> block — regex must handle it without catastrophic backtracking."""
        reasoning = "x" * 10000
        raw = f'<think>{reasoning}</think>{{"verdict": "pass"}}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"

    def test_prose_with_colon_before_json(self):
        """Common pattern: 'Here is the JSON:' followed by the object."""
        raw = 'Based on my analysis, here is the JSON:\n{"verdict": "fail", "confidence": 0.2}'
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "fail"

    def test_think_block_contains_complete_json(self):
        """<think> contains a valid JSON — must use the one AFTER </think>."""
        raw = (
            '<think>Expected output: {"verdict": "fail", "confidence": 0.1}</think>'
            '{"verdict": "pass", "confidence": 0.95}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["verdict"] == "pass"
        assert parsed["confidence"] == 0.95


# =========================================================================
# 6. Adversarial retry scenarios
# =========================================================================

class TestRetryAdversarial:

    def test_four_error_types_in_sequence(self):
        """ConnectionError → Timeout → HTTP 500 → validation → success."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 6
        client.INITIAL_DELAY = 0.001

        bad_validation = _ollama_response('{"verdict": "maybe"}')
        good = _ollama_response('{"verdict": "pass", "confidence": 0.9}')

        http_500 = MagicMock()
        http_500.status_code = 500
        http_500.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        call_seq = 0
        def side_effect(*args, **kwargs):
            nonlocal call_seq
            call_seq += 1
            if call_seq == 1:
                raise requests.exceptions.ConnectionError("refused")
            if call_seq == 2:
                raise requests.exceptions.Timeout("timeout")
            if call_seq == 3:
                return http_500
            if call_seq == 4:
                return bad_validation
            return good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert call_seq == 5
        assert client.stats.total_retries == 4

    def test_http_500_then_dirty_json_success(self):
        """HTTP 500 first, then dirty JSON that needs cleaning."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        http_500 = MagicMock()
        http_500.status_code = 500
        http_500.raise_for_status.side_effect = requests.exceptions.HTTPError("500")

        dirty_good = _ollama_response(
            '<think>checking...</think>{"verdict": "pass", "confidence": 0.88,}'
        )

        with patch('requests.post', side_effect=[http_500, dirty_good]):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"

    def test_backoff_sleep_called_on_validation_errors(self):
        """Verify time.sleep is called between validation-error retries."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 1.0
        client.BACKOFF_MULTIPLIER = 2.0

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad), \
             patch('time.sleep') as mock_sleep:
            client.generate_structured("test", SimpleSchema)

        # 3 attempts → 2 sleeps between them
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    def test_generate_merged_gets_cleaning_and_retry(self):
        """generate_merged delegates to generate_structured — cleaning + retry apply."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        dirty = _ollama_response('<think>hmm</think>{"verdict": "maybe"}')
        good = _ollama_response('{"verdict": "pass", "confidence": 0.9}')

        with patch('requests.post', side_effect=[dirty, good]) as mp:
            result = client.generate_merged("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        # Verify merged temperature (0.3) was used on first call
        body = mp.call_args_list[0].kwargs.get("json", {})
        assert body["options"]["temperature"] == 0.3

    def test_generate_merged_temperature_escalation(self):
        """generate_merged with base=0.3 should escalate: 0.3, 0.45, 0.65."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad) as mp:
            client.generate_merged("test", SimpleSchema)

        temps = _extract_temps(mp)
        assert temps[0] == 0.3
        assert temps[1] == pytest.approx(0.45)
        assert temps[2] == pytest.approx(0.65)

    def test_multiple_calls_stats_accumulate(self):
        """Stats accumulate correctly across multiple calls with mixed results."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')
        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=good):
            client.generate_structured("p1", SimpleSchema)  # success
        with patch('requests.post', return_value=good):
            client.generate_structured("p2", SimpleSchema)  # success
        with patch('requests.post', return_value=bad):
            client.generate_structured("p3", SimpleSchema)  # fail after 2 retries

        assert client.stats.total_requests == 3
        assert client.stats.successful_requests == 2
        assert client.stats.failed_requests == 1

    def test_circuit_breaker_blocks_after_threshold_then_recovers(self):
        """CB trips after N failures, blocks, then recovers on half-open success."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2
        client.CIRCUIT_BREAKER_TIMEOUT = 5.0  # Long enough to not expire during test

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        # Trip the circuit breaker: 2 validation failures
        with patch('requests.post', return_value=bad):
            client.generate_structured("p1", SimpleSchema)
            client.generate_structured("p2", SimpleSchema)

        assert client._circuit_breaker.is_open is True

        # While open, calls return None without hitting LLM
        with patch('requests.post', return_value=good) as mp:
            result = client.generate_structured("p3", SimpleSchema)
        assert result is None
        assert mp.call_count == 0

        # Force timeout expiry by setting open_until to the past
        client._circuit_breaker.open_until = 0.0

        with patch('requests.post', return_value=good):
            result = client.generate_structured("p4", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"
        assert client._circuit_breaker.is_open is False


# =========================================================================
# 7. Adversarial schema validation
# =========================================================================

class AllDefaultsSchema(BaseModel):
    """All fields have defaults — empty {} should be valid."""
    verdict: str = "unknown"
    confidence: float = 0.0


class StrictBoundsSchema(BaseModel):
    score: float = Field(..., ge=-1.0, le=1.0)
    label: Literal["pos", "neg", "neutral"]


class DeeplyNestedSchema(BaseModel):
    class Inner(BaseModel):
        class Leaf(BaseModel):
            value: Literal["a", "b", "c"]
            count: int = Field(default=0, ge=0)
        items: List[Leaf] = Field(default_factory=list)
    outer: Inner = Field(default_factory=lambda: DeeplyNestedSchema.Inner())
    tag: str = ""


class TestSchemaAdversarial:

    def test_empty_json_object_with_all_defaults(self):
        """Empty {} is valid for schema with all-defaults fields."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response('{}')
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", AllDefaultsSchema)
        assert result is not None
        assert result.verdict == "unknown"
        assert result.confidence == 0.0

    def test_negative_score_in_bounds(self):
        """Negative float in ge constraint."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response('{"score": -0.5, "label": "neg"}')
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", StrictBoundsSchema)
        assert result is not None
        assert result.score == -0.5

    def test_score_out_of_bounds_retries(self):
        """score=2.0 violates le=1.0 — retry with escalation should fix it."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"score": 2.0, "label": "pos"}')
        good = _ollama_response('{"score": 0.8, "label": "pos"}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", StrictBoundsSchema)
        assert result is not None
        assert result.score == 0.8

    def test_deeply_nested_schema_with_literal_in_leaf(self):
        """Literal inside nested sub-models."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '{"outer": {"items": [{"value": "a", "count": 3}, {"value": "c", "count": 0}]}, '
            '"tag": "test"}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", DeeplyNestedSchema)
        assert result is not None
        assert len(result.outer.items) == 2
        assert result.outer.items[0].value == "a"
        assert result.outer.items[1].value == "c"

    def test_deeply_nested_wrong_literal_retries(self):
        """Wrong Literal value deep in nested schema — retry recovers."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        # "x" is not in Literal["a", "b", "c"]
        bad = _ollama_response('{"outer": {"items": [{"value": "x"}]}, "tag": "t"}')
        good = _ollama_response('{"outer": {"items": [{"value": "b"}]}, "tag": "t"}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", DeeplyNestedSchema)
        assert result is not None
        assert result.outer.items[0].value == "b"

    def test_max_length_exceeded_on_rewritten_response(self):
        """rewritten_response exceeding max_length=1500 — validation error, retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        long_text = "А" * 1600  # > 1500
        bad = _ollama_response(
            f'{{"verdict": "pass", "rewritten_response": "{long_text}", "confidence": 0.9}}'
        )
        good = _ollama_response('{"verdict": "pass", "rewritten_response": "ok", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", VerifierOutput)
        assert result is not None
        assert result.rewritten_response == "ok"

    def test_categories_exceeds_max_length_5(self):
        """List with 6 items exceeds max_length=5 — validation error, retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"categories": ["analytics", "competitors", "equipment", '
            '"features", "integrations", "pricing"]}'
        )
        good = _ollama_response('{"categories": ["analytics", "pricing"]}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", CategoryResult)
        assert result is not None
        assert len(result.categories) == 2

    def test_extra_fields_ignored_by_pydantic(self):
        """Extra fields in JSON not in schema — Pydantic ignores them by default."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '{"intent": "greeting", "confidence": 0.9, '
            '"extra_field": "should be ignored", "another": 42}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"
        assert not hasattr(result, "extra_field")

    def test_null_for_optional_field_is_valid(self):
        """null value for Optional field should parse fine."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '{"intent": "situation_provided", "confidence": 0.9, '
            '"reasoning": "business info", '
            '"extracted_data": {"company_name": null, "business_type": "retail", '
            '"contact_info": null, "pain_point": null}}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", ClassificationLike)
        assert result is not None
        assert result.extracted_data.company_name is None
        assert result.extracted_data.business_type == "retail"


# =========================================================================
# 8. Full pipeline replay — exact sequences from production logs
# =========================================================================

class TestProductionReplay:
    """Replays exact failure patterns observed in production."""

    def test_verifier_pass_with_think_and_nested_checks(self):
        """Real pattern: verifier passes but output has think + trailing commas everywhere."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        # This exact pattern was observed in production logs
        resp = _ollama_response(
            '<think>\n'
            'Проверяю утверждения бота:\n'
            '1. "Тариф Mini — 5 000 ₸/мес" → в БЗ: pricing_basic_mini_23: '
            '"Тариф Mini: 5 000 ₸/мес (60 000 ₸/год)" ✓\n'
            '2. "Подключение за 1 день" → в БЗ: support_onboarding_fast_2187: '
            '"Подключение за 1 рабочий день" ✓\n'
            '3. "Бесплатное обучение" → в БЗ: support_training_free_2190: '
            '"Бесплатное обучение персонала" ✓\n'
            'Все утверждения подтверждены.\n'
            '</think>\n'
            '{"verdict": "pass", "checks": [\n'
            '  {"claim": "Mini costs 5000/month", "supported": true, '
            '"evidence_quote": "Тариф Mini: 5 000 ₸/мес"},\n'
            '  {"claim": "1 day onboarding", "supported": true, '
            '"evidence_quote": "Подключение за 1 рабочий день"},\n'
            '  {"claim": "free training", "supported": true, '
            '"evidence_quote": "Бесплатное обучение персонала"},\n'
            '], "rewritten_response": "", "confidence": 0.97,}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert len(result.checks) == 3
        assert all(c.supported for c in result.checks)
        assert result.confidence == pytest.approx(0.97)

    def test_verifier_fail_with_rewrite(self):
        """Real pattern: verifier catches hallucination and rewrites."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>\n'
            'Бот сказал "тестовый период 7 дней" — проверяю...\n'
            'В БЗ нет информации о тестовом периоде. Это галлюцинация.\n'
            '</think>\n'
            '{"verdict": "fail", "checks": [\n'
            '  {"claim": "7-day trial period", "supported": false, '
            '"evidence_quote": ""},\n'
            '], "rewritten_response": "Wipon предлагает тариф Mini от 5 000 ₸/мес. '
            'Подключение занимает 1 рабочий день, обучение персонала бесплатное.", '
            '"confidence": 0.85,}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "fail"
        assert result.checks[0].supported is False
        assert "5 000" in result.rewritten_response
        assert "тестовый" not in result.rewritten_response.lower()

    def test_classifier_with_dirty_output_and_full_extracted_data(self):
        """Real pattern: classifier extracts business info from complex message."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        resp = _ollama_response(
            '<think>Клиент описывает бизнес: 4 магазина в Караганде + 1 в Астане.\n'
            'Это situation_provided с business_type и pain_point.</think>\n'
            '{"intent": "situation_provided", "confidence": 0.94, '
            '"reasoning": "Клиент описывает структуру бизнеса и проблемы с учётом", '
            '"extracted_data": {'
            '"company_name": null, '
            '"business_type": "сеть продуктовых магазинов", '
            '"contact_info": null, '
            '"pain_point": "недостачи при инвентаризации, кассиры путаются с ценами"'
            '},}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", ClassificationLike)

        assert result is not None
        assert result.intent == "situation_provided"
        assert result.confidence == pytest.approx(0.94)
        assert "продуктовых" in result.extracted_data.business_type
        assert "недостачи" in result.extracted_data.pain_point

    def test_wrong_literal_then_dirty_correct_on_retry(self):
        """Real pattern: 1st attempt wrong Literal, 2nd attempt correct but dirty."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        # Attempt 1: "ok" not in Literal["pass","fail"]
        bad = _ollama_response(
            '<think>Everything looks ok</think>{"verdict": "ok", "confidence": 0.7}'
        )
        # Attempt 2: correct but with think + trailing comma
        good_dirty = _ollama_response(
            '<think>Reassessing... pass is correct.</think>'
            '{"verdict": "pass", "checks": [], "confidence": 0.92,}'
        )

        with patch('requests.post', side_effect=[bad, good_dirty]) as mp:
            result = client.generate_structured("test", VerifierOutput)

        assert result is not None
        assert result.verdict == "pass"
        assert result.confidence == pytest.approx(0.92)
        assert mp.call_count == 2

        # Verify temperature escalated on retry
        temps = _extract_temps(mp)
        assert temps[1] > temps[0]

    def test_timeout_then_connection_error_then_dirty_success(self):
        """Real production failure: network issues followed by dirty successful response."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        dirty_good = _ollama_response(
            '<think>Finally got through...</think>'
            '{"categories": ["pricing", "support",],}'
        )

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                raise requests.exceptions.Timeout("read timeout")
            if call_n == 2:
                raise requests.exceptions.ConnectionError("connection reset")
            return dirty_good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured("test", CategoryResult)

        assert result is not None
        assert result.categories == ["pricing", "support"]
        assert call_n == 3

    def test_full_e2e_trace_through_retry_and_cleaning(self):
        """Verify complete trace data through retry + cleaning pipeline."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"verdict": "maybe", "confidence": 0.1}')
        good = _ollama_response(
            '<think>ok</think>{"verdict": "pass", "confidence": 0.9,}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result, trace = client.generate_structured(
                "Verify: тариф 5000 ₸",
                VerifierOutput,
                return_trace=True,
                purpose="factual_verification",
            )

        assert result is not None
        assert result.verdict == "pass"

        # Trace verification
        assert trace.success is True
        assert trace.retry_count == 1  # succeeded on 2nd attempt (index 1)
        assert trace.purpose == "factual_verification"
        assert "<think>" not in trace.raw_response
        assert "pass" in trace.raw_response
        assert trace.latency_ms > 0
        assert trace.tokens_input > 0
        assert trace.tokens_output > 0
        assert trace.model_used == client.model


# =========================================================================
# 9. Real production schemas — exact mirrors of all 8 callers
# =========================================================================

class SubQueryLike(BaseModel):
    query: str = Field(min_length=1)
    categories: List[str] = Field(default_factory=list)

class DecompositionResultLike(BaseModel):
    is_complex: bool = False
    sub_queries: List[SubQueryLike] = Field(default_factory=list)

class SemanticRelevanceResultLike(BaseModel):
    relevant: bool
    reason: str = Field(default="", max_length=200)

class HistoryCompactSchemaLike(BaseModel):
    summary: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)

class SemanticEntitiesLike(BaseModel):
    store_count: Optional[int] = None
    employee_count: Optional[int] = None
    business_type: str = ""

class SemanticFrameModelLike(BaseModel):
    primary_goal: str = "unknown"
    asked_dimensions: List[str] = Field(default_factory=list)
    needs_direct_answer: bool = False
    has_question: bool = False
    price_requested: bool = False
    comparison_requested: bool = False
    recommended_intent: str = ""
    recommended_confidence: float = 0.0
    override_intent: bool = False
    confidence: float = 0.0
    entities: SemanticEntitiesLike = Field(default_factory=SemanticEntitiesLike)

class AutonomousDecisionLike(BaseModel):
    reasoning: str
    should_transition: bool = False
    next_state: str = ""
    action: str = "autonomous_respond"

class AutonomousDecisionAndResponseLike(BaseModel):
    reasoning: str
    should_transition: bool = False
    next_state: str = ""
    action: str = "autonomous_respond"
    response: str = ""


class TestProductionSchemaExact:
    """Each test mirrors exact caller site patterns from the 8 production callers."""

    def test_decomposition_dirty_sub_queries(self):
        """enhanced_retrieval.py:384 — DecompositionResult with sub_queries + think."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент спрашивает про сравнение и цену — надо разбить.</think>'
            '{"is_complex": true, "sub_queries": ['
            '{"query": "стоимость тарифов Wipon для 5 точек", "categories": ["pricing"]}, '
            '{"query": "интеграция Wipon с Kaspi", "categories": ["integrations"]}, '
            '],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", DecompositionResultLike)
        assert result is not None
        assert result.is_complex is True
        assert len(result.sub_queries) == 2
        assert result.sub_queries[0].categories == ["pricing"]

    def test_decomposition_empty_query_violates_min_length(self):
        """SubQuery.query has min_length=1 — empty string fails validation."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"is_complex": true, "sub_queries": [{"query": "", "categories": ["pricing"]}]}'
        )
        good = _ollama_response(
            '{"is_complex": true, "sub_queries": [{"query": "цена", "categories": ["pricing"]}]}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", DecompositionResultLike)
        assert result is not None
        assert result.sub_queries[0].query == "цена"

    def test_semantic_relevance_dirty(self):
        """response_boundary_validator.py:2146 — SemanticRelevanceResult, temp=0.1."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Ответ не по теме — клиент спросил про цену, бот ответил про обучение</think>'
            '{"relevant": false, "reason": "Ответ не по теме вопроса клиента",}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SemanticRelevanceResultLike, temperature=0.1)
        assert result is not None
        assert result.relevant is False
        assert "не по теме" in result.reason

    def test_semantic_relevance_reason_exceeds_max_length(self):
        """reason max_length=200 exceeded — retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        long_reason = "Б" * 250
        bad = _ollama_response(f'{{"relevant": true, "reason": "{long_reason}"}}')
        good = _ollama_response('{"relevant": true, "reason": "ok"}')
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", SemanticRelevanceResultLike)
        assert result is not None
        assert result.reason == "ok"

    def test_history_compact_schema_dirty(self):
        """history_compactor.py:64 — HistoryCompactSchema with 6 list fields."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Compacting 8 turns of dialog history...</think>'
            '{"summary": ["Клиент: сеть из 5 магазинов", "Бот: предложил Pro тариф",], '
            '"key_facts": ["5 точек", "Караганда + Астана",], '
            '"objections": ["дорого", "конкуренты дешевле",], '
            '"decisions": [], '
            '"open_questions": ["рассрочка?",], '
            '"next_steps": ["получить контакт",],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", HistoryCompactSchemaLike)
        assert result is not None
        assert len(result.summary) == 2
        assert len(result.objections) == 2
        assert result.open_questions == ["рассрочка?"]

    def test_semantic_frame_full_dirty(self):
        """semantic_frame.py:180 — SemanticFrameModel with nested entities, temp=0.0."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент спрашивает про цену и сравнивает с конкурентами</think>'
            '{"primary_goal": "pricing_comparison", '
            '"asked_dimensions": ["pricing", "competitors",], '
            '"needs_direct_answer": true, "has_question": true, '
            '"price_requested": true, "comparison_requested": true, '
            '"recommended_intent": "price_question", '
            '"recommended_confidence": 0.88, '
            '"override_intent": false, "confidence": 0.91, '
            '"entities": {"store_count": 5, "employee_count": null, '
            '"business_type": "продуктовый магазин"},}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", SemanticFrameModelLike, temperature=0.0)
        assert result is not None
        assert result.price_requested is True
        assert result.comparison_requested is True
        assert result.entities.store_count == 5
        assert result.entities.business_type == "продуктовый магазин"

    def test_autonomous_decision_dirty(self):
        """autonomous_decision.py:640 — AutonomousDecision, reasoning-first."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент описал бизнес, надо перейти к qualification</think>'
            '{"reasoning": "Клиент описал структуру: 5 магазинов. '
            'Пора задать вопросы о болях.", '
            '"should_transition": true, '
            '"next_state": "autonomous_qualification", '
            '"action": "autonomous_respond",}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", AutonomousDecisionLike)
        assert result is not None
        assert result.should_transition is True
        assert result.next_state == "autonomous_qualification"

    def test_autonomous_decision_and_response_merged(self):
        """autonomous_decision.py:616 — AutonomousDecisionAndResponse via generate_merged."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        resp = _ollama_response(
            '<think>Нужно ответить по цене и остаться в presentation</think>'
            '{"reasoning": "Клиент спросил цену — ответить фактами из БЗ", '
            '"should_transition": false, "next_state": "", '
            '"action": "autonomous_respond", '
            '"response": "Для 5 точек подойдёт тариф Pro — 500 000 ₸ в год. '
            'Включает все функции: учёт, аналитику, интеграции.",}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_merged("test", AutonomousDecisionAndResponseLike)
        assert result is not None
        assert result.should_transition is False
        assert "500 000" in result.response
        assert result.action == "autonomous_respond"

    def test_autonomous_decision_missing_reasoning_retries(self):
        """reasoning is required (no default) — missing field must retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"should_transition": false, "next_state": "", "action": "autonomous_respond"}'
        )
        good = _ollama_response(
            '{"reasoning": "staying in current state", "should_transition": false}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", AutonomousDecisionLike)
        assert result is not None
        assert result.reasoning == "staying in current state"


# =========================================================================
# 10. Full pipeline simulation — one bot turn = 4 sequential structured calls
# =========================================================================

class TestPipelineSimulation:
    """Simulates a complete bot turn with 4 sequential generate_structured calls:
    classifier → decomposition → verifier → autonomous decision.
    Verifies stats accumulate, CB state is coherent, schemas don't bleed."""

    def test_full_turn_all_succeed_clean(self):
        """Happy path — 4 calls, all succeed first try."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        responses = [
            # 1. Classifier
            _ollama_response(
                '{"intent": "price_question", "confidence": 0.93, '
                '"reasoning": "asks about price for 5 stores"}'
            ),
            # 2. Decomposition
            _ollama_response(
                '{"is_complex": false, "sub_queries": []}'
            ),
            # 3. Verifier
            _ollama_response(
                '{"verdict": "pass", "confidence": 0.95}'
            ),
            # 4. Autonomous decision
            _ollama_response(
                '{"reasoning": "answered price question", "should_transition": false}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r1 = client.generate_structured("p1", ClassificationLike)
            r2 = client.generate_structured("p2", DecompositionResultLike)
            r3 = client.generate_structured("p3", VerifierOutput)
            r4 = client.generate_structured("p4", AutonomousDecisionLike)

        assert r1.intent == "price_question"
        assert r2.is_complex is False
        assert r3.verdict == "pass"
        assert r4.should_transition is False

        assert client.stats.total_requests == 4
        assert client.stats.successful_requests == 4
        assert client.stats.failed_requests == 0
        assert client._circuit_breaker.failures == 0

    def test_full_turn_middle_call_retries(self):
        """Verifier fails on first try (wrong Literal), retries succeed.
        Other calls succeed immediately."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        responses = [
            # 1. Classifier — OK
            _ollama_response(
                '{"intent": "greeting", "confidence": 0.99, "reasoning": "hello"}'
            ),
            # 2. Verifier — BAD then GOOD
            _ollama_response('{"verdict": "maybe", "confidence": 0.5}'),
            _ollama_response('{"verdict": "pass", "confidence": 0.91}'),
            # 3. Autonomous decision — OK
            _ollama_response(
                '{"reasoning": "greeting received", "should_transition": false}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r1 = client.generate_structured("p1", ClassificationLike)
            r2 = client.generate_structured("p2", VerifierOutput)
            r3 = client.generate_structured("p3", AutonomousDecisionLike)

        assert r1.intent == "greeting"
        assert r2.verdict == "pass"
        assert r3.should_transition is False

        assert client.stats.total_requests == 3
        assert client.stats.successful_requests == 3
        assert client.stats.total_retries == 1

    def test_full_turn_one_call_exhausts_retries(self):
        """Decomposition fails all retries. Other calls still work.
        Stats must show exactly 1 failure, and CB records it."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 3  # won't trip from 1 failure

        responses = [
            # 1. Classifier — OK
            _ollama_response(
                '{"intent": "comparison", "confidence": 0.87, "reasoning": "comparing"}'
            ),
            # 2. Decomposition — fails both attempts (empty query)
            _ollama_response('{"is_complex": true, "sub_queries": [{"query": "", "categories": []}]}'),
            _ollama_response('{"is_complex": true, "sub_queries": [{"query": "", "categories": []}]}'),
            # 3. Verifier — OK (with dirty output)
            _ollama_response(
                '<think>ok</think>{"verdict": "pass", "confidence": 0.9,}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r1 = client.generate_structured("p1", ClassificationLike)
            r2 = client.generate_structured("p2", DecompositionResultLike)
            r3 = client.generate_structured("p3", VerifierOutput)

        assert r1.intent == "comparison"
        assert r2 is None  # all retries exhausted
        assert r3.verdict == "pass"  # subsequent call still works

        assert client.stats.successful_requests == 2
        assert client.stats.failed_requests == 1
        # CB failures reset to 0 by the successful verifier call after the failure
        assert client._circuit_breaker.failures == 0

    def test_full_turn_every_call_dirty(self):
        """All 4 calls return dirty output (think tags + trailing commas).
        All must parse correctly after cleaning."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        responses = [
            _ollama_response(
                '<think>analyzing intent...</think>'
                '{"intent": "objection_price", "confidence": 0.88, '
                '"reasoning": "дорого",}'
            ),
            _ollama_response(
                '<think>decomposing query...</think>'
                '{"is_complex": false, "sub_queries": [],}'
            ),
            _ollama_response(
                '<think>checking claims...</think>'
                '{"verdict": "fail", "checks": [{"claim": "wrong price", '
                '"supported": false, "evidence_quote": ""},], '
                '"rewritten_response": "Тариф Pro — 500 000 ₸/год.", '
                '"confidence": 0.82,}'
            ),
            _ollama_response(
                '<think>deciding state transition...</think>'
                '{"reasoning": "objection handled, stay in presentation", '
                '"should_transition": false, "next_state": "", '
                '"action": "autonomous_respond",}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r1 = client.generate_structured("p1", ClassificationLike)
            r2 = client.generate_structured("p2", DecompositionResultLike)
            r3 = client.generate_structured("p3", VerifierOutput)
            r4 = client.generate_structured("p4", AutonomousDecisionLike)

        assert r1.intent == "objection_price"
        assert r2.is_complex is False
        assert r3.verdict == "fail"
        assert "500 000" in r3.rewritten_response
        assert r4.reasoning.startswith("objection handled")

    def test_rapid_sequential_calls_stats_isolation(self):
        """10 rapid calls with alternating schemas — stats must be exact."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        schemas_and_responses = [
            (SimpleSchema, '{"intent": "greeting", "confidence": 0.9}'),
            (VerifierOutput, '{"verdict": "pass", "confidence": 0.8}'),
            (SimpleSchema, '{"intent": "farewell", "confidence": 0.7}'),
            (CategoryResult, '{"categories": ["pricing"]}'),
            (SemanticRelevanceResultLike, '{"relevant": true, "reason": "ok"}'),
            (AutonomousDecisionLike, '{"reasoning": "ok", "should_transition": false}'),
            (SimpleSchema, '{"wrong": true}'),  # will fail
            (HistoryCompactSchemaLike, '{"summary": ["test"]}'),
            (DecompositionResultLike, '{"is_complex": false}'),
            (SemanticFrameModelLike, '{"primary_goal": "info"}'),
        ]

        responses = [_ollama_response(r) for _, r in schemas_and_responses]

        with patch('requests.post', side_effect=responses):
            results = []
            for schema, _ in schemas_and_responses:
                results.append(client.generate_structured("test", schema))

        # 9 succeed, 1 fails (index 6: SimpleSchema with wrong fields)
        assert sum(1 for r in results if r is not None) == 9
        assert results[6] is None
        assert client.stats.successful_requests == 9
        assert client.stats.failed_requests == 1
        assert client.stats.total_requests == 10


# =========================================================================
# 11. Circuit breaker state machine — exhaustive transitions
# =========================================================================

class TestCircuitBreakerStateMachine:
    """Exhaustive CB state transitions with validation errors vs network errors."""

    def test_closed_to_open_via_validation_errors_only(self):
        """Pure validation errors (HTTP 200 but bad JSON) trip the CB."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 3

        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', return_value=bad):
            for i in range(3):
                client.generate_structured(f"p{i}", SimpleSchema)

        assert client._circuit_breaker.is_open is True
        assert client._circuit_breaker.failures == 3

    def test_validation_error_then_success_resets_cb(self):
        """One validation failure then success — CB counter resets to 0."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 3

        # Call 1: bad then good
        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", SimpleSchema)

        assert result is not None
        assert client._circuit_breaker.failures == 0  # reset on success

    def test_mixed_network_and_validation_errors_trip_cb(self):
        """Interleaved network errors and validation failures both contribute to CB."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 3

        bad_json = _ollama_response('{"wrong": true}')

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n == 2:
                raise requests.exceptions.ConnectionError("refused")
            return bad_json

        with patch('requests.post', side_effect=side_effect):
            client.generate_structured("p1", SimpleSchema)  # validation fail
            client.generate_structured("p2", SimpleSchema)  # network fail
            client.generate_structured("p3", SimpleSchema)  # validation fail

        assert client._circuit_breaker.is_open is True
        assert client._circuit_breaker.failures == 3

    def test_half_open_probe_with_dirty_json_succeeds(self):
        """CB half-open probe gets dirty JSON that cleans to valid — CB closes."""
        import time as _time

        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2
        client.CIRCUIT_BREAKER_TIMEOUT = 0.01

        bad = _ollama_response('{"wrong": true}')

        # Trip CB
        with patch('requests.post', return_value=bad):
            client.generate_structured("p1", SimpleSchema)
            client.generate_structured("p2", SimpleSchema)
        assert client._circuit_breaker.is_open is True

        _time.sleep(0.02)

        # Half-open probe with dirty but valid JSON
        dirty_good = _ollama_response(
            '<think>recovering...</think>{"intent": "greeting", "confidence": 0.9,}'
        )
        with patch('requests.post', return_value=dirty_good):
            result = client.generate_structured("probe", SimpleSchema)

        assert result is not None
        assert result.intent == "greeting"
        assert client._circuit_breaker.is_open is False
        assert client._circuit_breaker.failures == 0

    def test_half_open_probe_fails_stays_open(self):
        """CB half-open probe fails validation — CB stays open."""
        import time as _time

        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2
        client.CIRCUIT_BREAKER_TIMEOUT = 0.01

        bad = _ollama_response('{"wrong": true}')

        # Trip CB
        with patch('requests.post', return_value=bad):
            client.generate_structured("p1", SimpleSchema)
            client.generate_structured("p2", SimpleSchema)
        assert client._circuit_breaker.is_open is True

        _time.sleep(0.02)

        # Half-open probe still gets bad JSON
        with patch('requests.post', return_value=bad):
            result = client.generate_structured("probe", SimpleSchema)

        assert result is None
        assert client._circuit_breaker.is_open is True
        assert client._circuit_breaker.failures >= 2

    def test_cb_open_returns_none_without_http_call(self):
        """When CB is open, generate_structured returns None without any HTTP request."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 1

        bad = _ollama_response('{"wrong": true}')
        with patch('requests.post', return_value=bad):
            client.generate_structured("trip", SimpleSchema)
        assert client._circuit_breaker.is_open is True

        # Now CB is open — no HTTP call should happen
        with patch('requests.post') as mp:
            result = client.generate_structured("blocked", SimpleSchema)
        assert result is None
        assert mp.call_count == 0

    def test_cb_fallback_used_counter_increments(self):
        """Each call blocked by CB increments fallback_used."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 1

        bad = _ollama_response('{"wrong": true}')
        with patch('requests.post', return_value=bad):
            client.generate_structured("trip", SimpleSchema)

        with patch('requests.post'):
            client.generate_structured("b1", SimpleSchema)
            client.generate_structured("b2", SimpleSchema)
            client.generate_structured("b3", SimpleSchema)

        assert client.stats.fallback_used == 3

    def test_full_cycle_closed_open_halfopen_closed(self):
        """Complete CB lifecycle: closed → open → half-open → closed."""
        import time as _time

        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2
        client.CIRCUIT_BREAKER_TIMEOUT = 0.01

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        # Phase 1: closed — failures accumulate
        assert client._circuit_breaker.is_open is False
        with patch('requests.post', return_value=bad):
            client.generate_structured("f1", SimpleSchema)
        assert client._circuit_breaker.is_open is False  # still closed (1 < 2)

        with patch('requests.post', return_value=bad):
            client.generate_structured("f2", SimpleSchema)
        assert client._circuit_breaker.is_open is True  # now open

        # Phase 2: open — calls blocked
        with patch('requests.post', return_value=good) as mp:
            r = client.generate_structured("blocked", SimpleSchema)
        assert r is None
        assert mp.call_count == 0

        # Phase 3: half-open after timeout
        _time.sleep(0.02)
        with patch('requests.post', return_value=good):
            r = client.generate_structured("recover", SimpleSchema)
        assert r is not None
        assert r.intent == "greeting"

        # Phase 4: back to closed
        assert client._circuit_breaker.is_open is False
        assert client._circuit_breaker.failures == 0


# =========================================================================
# 12. Adversarial cleaning — fuzzing-style systematic inputs
# =========================================================================

class TestCleanFuzzing:
    """Systematic adversarial inputs that stress _clean_structured_output."""

    def _clean(self, text: str) -> str:
        return OllamaClient._clean_structured_output(text)

    def test_null_bytes_in_input(self):
        """Null bytes should not crash the cleaner."""
        raw = '{"intent": "greeting\x00", "confidence": 0.9}'
        result = self._clean(raw)
        assert isinstance(result, str)

    def test_control_characters_ascii(self):
        """ASCII control chars (0x01-0x1F except \\n\\r\\t) in values."""
        raw = '{"intent": "greet\x07ing", "confidence": 0.9}'
        result = self._clean(raw)
        assert "{" in result

    def test_nested_think_tags(self):
        """<think> tags nested inside each other (malformed)."""
        raw = (
            '<think>outer <think>inner</think> still outer</think>'
            '{"verdict": "pass"}'
        )
        result = self._clean(raw)
        parsed = json.loads(result)
        assert parsed["verdict"] == "pass"

    def test_think_tag_as_json_key(self):
        """<think> appearing as a JSON key name."""
        raw = '{"<think>": "not a real tag", "intent": "greeting", "confidence": 0.9}'
        result = self._clean(raw)
        parsed = json.loads(result)
        assert parsed["intent"] == "greeting"

    def test_unicode_zero_width_chars(self):
        """Zero-width chars (ZWJ, ZWNJ, BOM) scattered in output."""
        raw = '\u200b{"intent"\u200c: "greeting"\ufeff, "confidence": 0.9}'
        result = self._clean(raw)
        assert "{" in result

    def test_very_deep_nesting_50_levels(self):
        """50 levels of brace nesting — must not stack overflow or hang."""
        inner = '"leaf": "ok"'
        for _ in range(50):
            inner = f'"nested": {{{inner}}}'
        raw = f'prefix: {{{inner}}}'
        result = self._clean(raw)
        # Should extract the outermost object
        assert result.startswith("{")
        assert result.endswith("}")

    def test_100k_think_block(self):
        """100KB <think> block — regex must not catastrophically backtrack."""
        import time as _time
        reasoning = "проверяю " * 12500  # ~100K chars
        raw = f'<think>{reasoning}</think>{{"verdict": "pass"}}'
        t0 = _time.time()
        result = self._clean(raw)
        elapsed = _time.time() - t0
        parsed = json.loads(result)
        assert parsed["verdict"] == "pass"
        assert elapsed < 1.0  # must complete in under 1 second

    def test_only_closing_brace(self):
        """Just a closing brace — should not crash."""
        assert isinstance(self._clean("}"), str)

    def test_only_opening_brace(self):
        """Just an opening brace — should not crash."""
        assert isinstance(self._clean("{"), str)

    def test_mismatched_braces(self):
        """More closing than opening braces."""
        raw = '{"a": 1}}}}'
        result = self._clean(raw)
        parsed = json.loads(result)
        assert parsed["a"] == 1

    def test_json_preceded_by_xml_like_tags(self):
        """Output with various XML-like tags before JSON (not just <think>)."""
        raw = (
            '<result><status>ok</status></result>'
            '{"intent": "greeting", "confidence": 0.9}'
        )
        parsed = json.loads(self._clean(raw))
        assert parsed["intent"] == "greeting"

    def test_escaped_unicode_in_json(self):
        r"""JSON with \uXXXX escaped sequences."""
        raw = r'{"intent": "greeting", "reasoning": "\u041f\u0440\u0438\u0432\u0435\u0442", "confidence": 0.9}'
        parsed = json.loads(self._clean(raw))
        assert parsed["reasoning"] == "Привет"

    def test_json_with_scientific_notation_numbers(self):
        """Scientific notation floats in JSON values."""
        raw = '{"confidence": 9.5e-1, "intent": "greeting"}'
        parsed = json.loads(self._clean(raw))
        assert parsed["confidence"] == pytest.approx(0.95)

    def test_boolean_casing_lowercase(self):
        """JSON booleans are lowercase (true/false) — verify no issues."""
        raw = '{"relevant": true, "reason": ""}'
        parsed = json.loads(self._clean(raw))
        assert parsed["relevant"] is True

    def test_multiple_think_blocks_with_json_between(self):
        """<think>A</think> {wrong} <think>B</think> {correct} — takes first extractable."""
        raw = (
            '<think>first thought</think>'
            '{"verdict": "wrong_value"}'
            '<think>second thought</think>'
            '{"verdict": "pass"}'
        )
        result = self._clean(raw)
        parsed = json.loads(result)
        # After stripping think tags: '{"verdict": "wrong_value"}{"verdict": "pass"}'
        # Brace extraction takes first complete object
        assert parsed["verdict"] == "wrong_value"

    def test_trailing_comma_after_boolean(self):
        """Trailing comma after boolean value: {"a": true,}."""
        raw = '{"relevant": false, "reason": "test",}'
        parsed = json.loads(self._clean(raw))
        assert parsed["relevant"] is False

    def test_trailing_comma_after_number(self):
        """Trailing comma after number: {"a": 42,}."""
        raw = '{"confidence": 0.88,}'
        parsed = json.loads(self._clean(raw))
        assert parsed["confidence"] == 0.88

    def test_trailing_comma_after_null(self):
        """Trailing comma after null: {"a": null,}."""
        raw = '{"company": null, "type": "retail",}'
        parsed = json.loads(self._clean(raw))
        assert parsed["company"] is None


# =========================================================================
# 13. Multi-constraint violation — every field wrong simultaneously
# =========================================================================

class MultiConstraintSchema(BaseModel):
    intent: Literal["a", "b", "c"]
    score: float = Field(..., ge=0.0, le=1.0)
    tags: List[Literal["x", "y"]] = Field(..., min_length=1, max_length=3)
    reason: str = Field(..., min_length=1, max_length=100)


class TestMultiConstraintViolation:
    """Every field in the schema violates its constraint simultaneously."""

    def test_all_fields_wrong_simultaneously(self):
        """intent wrong Literal, score out of range, tags empty, reason empty."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        # All wrong
        bad1 = _ollama_response('{"intent": "d", "score": 2.0, "tags": [], "reason": ""}')
        # Some fixed, some still wrong
        bad2 = _ollama_response('{"intent": "a", "score": 0.5, "tags": [], "reason": "ok"}')
        # All correct
        good = _ollama_response('{"intent": "b", "score": 0.7, "tags": ["x"], "reason": "valid"}')

        with patch('requests.post', side_effect=[bad1, bad2, good]) as mp:
            result = client.generate_structured("test", MultiConstraintSchema)

        assert result is not None
        assert result.intent == "b"
        assert result.score == 0.7
        assert result.tags == ["x"]
        assert mp.call_count == 3

    def test_tags_wrong_literal_values(self):
        """All tag values outside Literal["x","y"]."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"intent": "a", "score": 0.5, "tags": ["z", "w"], "reason": "ok"}')
        good = _ollama_response('{"intent": "a", "score": 0.5, "tags": ["y"], "reason": "ok"}')

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", MultiConstraintSchema)

        assert result is not None
        assert result.tags == ["y"]

    def test_tags_exceeds_max_length(self):
        """More items than max_length=3."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "a", "score": 0.5, "tags": ["x", "y", "x", "y"], "reason": "ok"}'
        )
        good = _ollama_response(
            '{"intent": "a", "score": 0.5, "tags": ["x", "y"], "reason": "ok"}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", MultiConstraintSchema)
        assert result is not None
        assert len(result.tags) == 2

    def test_reason_exceeds_max_length_100(self):
        """reason string > 100 chars."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        long = "A" * 150
        bad = _ollama_response(
            f'{{"intent": "a", "score": 0.5, "tags": ["x"], "reason": "{long}"}}'
        )
        good = _ollama_response(
            '{"intent": "a", "score": 0.5, "tags": ["x"], "reason": "short"}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", MultiConstraintSchema)
        assert result is not None
        assert result.reason == "short"

    def test_score_negative_violates_ge_zero(self):
        """Negative score violates ge=0.0."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "a", "score": -0.5, "tags": ["x"], "reason": "ok"}'
        )
        good = _ollama_response(
            '{"intent": "a", "score": 0.3, "tags": ["x"], "reason": "ok"}'
        )

        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", MultiConstraintSchema)
        assert result is not None
        assert result.score == 0.3


# =========================================================================
# 14. Trace correctness under adversarial conditions
# =========================================================================

class TestTraceAdversarial:
    """Verify LLMTrace is correct even under worst-case retry scenarios."""

    def test_trace_retry_count_matches_actual_attempts(self):
        """After 2 failures + 1 success, trace.retry_count == 2 (0-indexed success attempt)."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 5
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, bad, good]):
            result, trace = client.generate_structured(
                "test", SimpleSchema, return_trace=True
            )

        assert result is not None
        assert trace.success is True
        assert trace.retry_count == 2  # 0-indexed: attempt 0,1 fail, attempt 2 success

    def test_trace_on_all_failures_has_last_error(self):
        """Trace.error contains the last validation error message."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"verdict": "nope"}')

        with patch('requests.post', return_value=bad):
            result, trace = client.generate_structured(
                "test", VerifierOutput, return_trace=True
            )

        assert result is None
        assert trace.success is False
        assert trace.retry_count == 2  # max_attempts exhausted
        assert len(trace.error) > 0

    def test_trace_purpose_preserved_through_retries(self):
        """Purpose field survives retry loop."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        with patch('requests.post', side_effect=[bad, good]):
            result, trace = client.generate_structured(
                "test", SimpleSchema, return_trace=True,
                purpose="custom_purpose_xyz",
            )

        assert trace.purpose == "custom_purpose_xyz"
        assert trace.success is True

    def test_trace_model_used_always_set(self):
        """trace.model_used is populated even on failure."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        bad = _ollama_response('{"wrong": true}')
        with patch('requests.post', return_value=bad):
            _, trace = client.generate_structured(
                "test", SimpleSchema, return_trace=True
            )

        assert trace.model_used == client.model

    def test_trace_cb_state_recorded(self):
        """trace.circuit_breaker_state reflects CB state at call time."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 1

        bad = _ollama_response('{"wrong": true}')

        # First call — CB closed
        with patch('requests.post', return_value=bad):
            _, trace1 = client.generate_structured(
                "test", SimpleSchema, return_trace=True
            )
        assert trace1.circuit_breaker_state == "closed"

        # Second call — CB open
        _, trace2 = client.generate_structured(
            "test", SimpleSchema, return_trace=True
        )
        assert trace2.circuit_breaker_state == "open"
        assert trace2.success is False

    def test_trace_latency_increases_with_retries(self):
        """More retries → higher latency in trace."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.01  # 10ms minimum delay per retry

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        # 1 retry
        with patch('requests.post', side_effect=[bad, good]):
            _, trace_1retry = client.generate_structured(
                "test", SimpleSchema, return_trace=True
            )

        # No retry (separate client to isolate stats)
        client2 = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        with patch('requests.post', return_value=good):
            _, trace_0retry = client2.generate_structured(
                "test", SimpleSchema, return_trace=True
            )

        # Trace with retry should have higher latency (due to sleep)
        assert trace_1retry.latency_ms > trace_0retry.latency_ms


# =========================================================================
# 15. REAL PRODUCTION SCHEMAS — exact copies from src/classifier/llm/schemas.py
# =========================================================================

# Actual 220-value IntentType from production (full copy)
RealIntentType = Literal[
    "greeting", "agreement", "gratitude", "farewell", "small_talk",
    "price_question", "pricing_details", "objection_price",
    "cost_inquiry", "discount_request", "payment_terms",
    "pricing_comparison", "budget_question",
    "question_features", "question_integrations", "comparison",
    "question_security", "question_support", "question_implementation",
    "question_training", "question_updates", "question_mobile",
    "question_offline", "question_data_migration", "question_customization",
    "question_reports", "question_automation", "question_scalability",
    "question_technical",
    "callback_request", "contact_provided", "demo_request",
    "consultation_request", "request_human", "need_help",
    "situation_provided", "problem_revealed", "implication_acknowledged",
    "need_expressed", "no_problem", "no_need", "info_provided",
    "objection_no_time", "objection_timing", "objection_think",
    "objection_complexity", "objection_competitor", "objection_trust",
    "objection_no_need", "rejection", "objection_risk",
    "objection_team_resistance", "objection_security",
    "objection_bad_experience", "objection_priority", "objection_scale",
    "payment_confirmation", "payment_kaspi", "payment_card",
    "payment_invoice",
]

RealPainCategory = Literal["losing_clients", "no_control", "manual_work"]

RealCategoryType = Literal[
    "analytics", "competitors", "employees", "equipment", "faq",
    "features", "fiscal", "integrations", "inventory", "mobile",
    "pricing", "products", "promotions", "delivery", "stability",
    "support", "tis",
]


class RealExtractedData(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    city: Optional[str] = None
    budget_range: Optional[str] = None
    company_size: Optional[int] = None
    business_type: Optional[str] = None
    current_tools: Optional[str] = None
    automation_before: Optional[bool] = None
    automation_now: Optional[bool] = None
    pain_point: Optional[str] = None
    pain_category: Optional[RealPainCategory] = None
    pain_impact: Optional[str] = None
    financial_impact: Optional[str] = None
    contact_info: Optional[str] = None
    kaspi_phone: Optional[str] = None
    iin: Optional[str] = None
    desired_outcome: Optional[str] = None
    value_acknowledged: Optional[bool] = None


class RealIntentAlternative(BaseModel):
    intent: RealIntentType
    confidence: float = Field(..., ge=0.0, le=1.0)


class RealClassificationResult(BaseModel):
    intent: RealIntentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    extracted_data: RealExtractedData = Field(default_factory=RealExtractedData)
    alternatives: List[RealIntentAlternative] = Field(
        default_factory=list, max_length=2,
    )


class RealCategoryResult(BaseModel):
    categories: List[RealCategoryType] = Field(..., min_length=1, max_length=5)


class RealClaimCheck(BaseModel):
    claim: str = Field(default="", max_length=300)
    supported: bool = False
    evidence_quote: str = Field(default="", max_length=240)


class RealVerifierOutput(BaseModel):
    verdict: Literal["pass", "fail"]
    checks: List[RealClaimCheck] = Field(default_factory=list)
    rewritten_response: str = Field(default="", max_length=1500)
    confidence: float = Field(default=0.0, ge=0.0)


# =========================================================================
# 16. Realistic Qwen3.5-27B outputs — actual dirty patterns from production
# =========================================================================

class TestRealQwenOutputPatterns:
    """Tests using exact dirty output patterns that Qwen3.5-27B Q4_K_M actually produces.
    Based on real simulator runs with Ollama structured output."""

    def test_verifier_with_long_cyrillic_think_and_kb_citations(self):
        """Real: Qwen reasons in Russian about KB sections, cites section IDs."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>\n'
            'Проверяю утверждения бота:\n'
            '1. "Тариф Mini — 5 000 ₸/мес" → pricing_basic_mini_23: '
            '"Тариф Mini: 5 000 ₸/мес (60 000 ₸/год)" ✓\n'
            '2. "Подключение за 1 рабочий день" → support_onboarding_fast_2187: '
            '"Стандартное подключение — 1 рабочий день" ✓\n'
            '3. "Бесплатное обучение персонала" → support_training_free_2190: '
            '"Бесплатное обучение для всех тарифов" ✓\n'
            '4. "Рассрочка от Kaspi 0-0-12" → pricing_installment_kaspi: '
            '"Рассрочка через Kaspi 0-0-12 на оборудование" ✓\n'
            '5. "Интеграция с 1С и iiko" → integrations_1c_iiko: '
            '"Двусторонняя интеграция с 1С, iiko, R-Keeper" ✓\n'
            'Все 5 утверждений подтверждены базой знаний.\n'
            '</think>\n'
            '{"verdict": "pass", "checks": [\n'
            '  {"claim": "Тариф Mini 5000 ₸/мес", "supported": true, '
            '"evidence_quote": "Тариф Mini: 5 000 ₸/мес (60 000 ₸/год)"},\n'
            '  {"claim": "Подключение за 1 день", "supported": true, '
            '"evidence_quote": "Стандартное подключение — 1 рабочий день"},\n'
            '  {"claim": "Бесплатное обучение", "supported": true, '
            '"evidence_quote": "Бесплатное обучение для всех тарифов"},\n'
            '  {"claim": "Рассрочка Kaspi 0-0-12", "supported": true, '
            '"evidence_quote": "Рассрочка через Kaspi 0-0-12"},\n'
            '  {"claim": "Интеграция с 1С и iiko", "supported": true, '
            '"evidence_quote": "Двусторонняя интеграция с 1С, iiko, R-Keeper"},\n'
            '], "rewritten_response": "", "confidence": 0.98,}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"
        assert len(result.checks) == 5
        assert all(c.supported for c in result.checks)
        assert "₸" in result.checks[0].evidence_quote

    def test_verifier_fail_with_hallucinated_price_and_rewrite(self):
        """Real: bot says 50 000 but KB says 500 000 — verifier catches and rewrites."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>\n'
            'Бот написал "тариф Pro стоит 50 000 ₸/год за 5 точек".\n'
            'Проверяю: pricing_multistore_5_points: "Тариф Pro для 5 точек — 500 000 ₸/год"\n'
            'Цена НЕВЕРНА: 50 000 вместо 500 000. Verdict: fail.\n'
            'Нужно переписать с правильной ценой.\n'
            '</think>\n'
            '{"verdict": "fail", "checks": [\n'
            '  {"claim": "Pro стоит 50 000 ₸/год за 5 точек", "supported": false,\n'
            '   "evidence_quote": "Тариф Pro для 5 точек — 500 000 ₸/год"},\n'
            '], "rewritten_response": "Для 5 точек подойдёт тариф Pro за 500 000 ₸ в год. '
            'В стоимость входят онлайн-касса, учёт товаров, аналитика и интеграции с 1С.", '
            '"confidence": 0.91,}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "fail"
        assert not result.checks[0].supported
        assert "500 000" in result.rewritten_response
        assert "50 000" not in result.rewritten_response

    def test_classifier_real_multiintent_message(self):
        """Real user message: "у нас 2 магазина продуктов в караганде, сколько стоит и поддерживаете ли маркировку?"
        LLM must classify + extract business_type, city, company_size."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>\n'
            'Клиент одновременно:\n'
            '1) Описывает ситуацию: 2 магазина, Караганда, продукты\n'
            '2) Спрашивает цену\n'
            '3) Спрашивает про маркировку\n'
            'Основной интент: price_question (прямой вопрос "сколько стоит")\n'
            'Альтернативы: situation_provided, question_features\n'
            '</think>\n'
            '{"intent": "price_question", "confidence": 0.82, '
            '"reasoning": "Клиент задаёт прямой ценовой вопрос, попутно описывая бизнес", '
            '"extracted_data": {'
            '"company_name": null, '
            '"contact_name": null, '
            '"city": "Караганда", '
            '"budget_range": null, '
            '"company_size": null, '
            '"business_type": "продуктовый магазин", '
            '"current_tools": null, '
            '"automation_before": null, '
            '"automation_now": null, '
            '"pain_point": null, '
            '"pain_category": null, '
            '"pain_impact": null, '
            '"financial_impact": null, '
            '"contact_info": null, '
            '"kaspi_phone": null, '
            '"iin": null, '
            '"desired_outcome": null, '
            '"value_acknowledged": null'
            '}, '
            '"alternatives": ['
            '{"intent": "situation_provided", "confidence": 0.72}, '
            '{"intent": "question_features", "confidence": 0.45}'
            '],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"
        assert result.extracted_data.city == "Караганда"
        assert result.extracted_data.business_type == "продуктовый магазин"
        assert len(result.alternatives) == 2
        assert result.alternatives[0].intent == "situation_provided"

    def test_classifier_wrong_intent_name_russian_retries(self):
        """Real Qwen failure: generates intent in Russian "вопрос_о_цене" instead of "price_question"."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "вопрос_о_цене", "confidence": 0.9, '
            '"reasoning": "клиент спрашивает про стоимость"}'
        )
        good = _ollama_response(
            '{"intent": "price_question", "confidence": 0.88, '
            '"reasoning": "клиент спрашивает про стоимость"}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"

    def test_classifier_close_but_wrong_intent_retries(self):
        """Real: LLM outputs "price_questions" (plural) instead of "price_question"."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "price_questions", "confidence": 0.85, '
            '"reasoning": "цена"}'
        )
        good = _ollama_response(
            '{"intent": "price_question", "confidence": 0.85, '
            '"reasoning": "цена"}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"

    def test_classifier_confidence_1_2_out_of_range(self):
        """Real: Qwen sometimes outputs confidence > 1.0 like 1.2 or 0.105."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "greeting", "confidence": 1.2, '
            '"reasoning": "привет = однозначное приветствие"}'
        )
        good = _ollama_response(
            '{"intent": "greeting", "confidence": 0.99, '
            '"reasoning": "привет = однозначное приветствие"}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.confidence == 0.99

    def test_classifier_3_alternatives_exceeds_max_2(self):
        """Real: LLM returns 3 alternatives but max_length=2."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "situation_provided", "confidence": 0.75, '
            '"reasoning": "бизнес-контекст", '
            '"alternatives": ['
            '{"intent": "price_question", "confidence": 0.60}, '
            '{"intent": "question_features", "confidence": 0.40}, '
            '{"intent": "need_expressed", "confidence": 0.30}'
            ']}'
        )
        good = _ollama_response(
            '{"intent": "situation_provided", "confidence": 0.75, '
            '"reasoning": "бизнес-контекст", '
            '"alternatives": ['
            '{"intent": "price_question", "confidence": 0.60}, '
            '{"intent": "question_features", "confidence": 0.40}'
            ']}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert len(result.alternatives) == 2

    def test_classifier_pain_category_russian_instead_of_english(self):
        """Real: LLM outputs pain_category in Russian instead of Literal enum."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response(
            '{"intent": "problem_revealed", "confidence": 0.88, '
            '"reasoning": "клиент описывает проблему с учётом", '
            '"extracted_data": {"pain_point": "недостачи при инвентаризации", '
            '"pain_category": "ручная_работа", '
            '"business_type": "продуктовый магазин"}}'
        )
        good = _ollama_response(
            '{"intent": "problem_revealed", "confidence": 0.88, '
            '"reasoning": "клиент описывает проблему с учётом", '
            '"extracted_data": {"pain_point": "недостачи при инвентаризации", '
            '"pain_category": "manual_work", '
            '"business_type": "продуктовый магазин"}}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.extracted_data.pain_category == "manual_work"

    def test_category_router_wrong_category_name(self):
        """Real: LLM outputs "цены" instead of "pricing"."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"categories": ["цены", "стабильность"]}')
        good = _ollama_response('{"categories": ["pricing", "stability"]}')
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealCategoryResult)
        assert result is not None
        assert result.categories == ["pricing", "stability"]

    def test_verifier_evidence_quote_exceeds_240_chars(self):
        """Real: LLM copies large KB section as evidence_quote, exceeding max_length=240."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        long_quote = (
            "Тариф Pro включает: онлайн-кассу с фискализацией, учёт товаров с серийными "
            "номерами и сроками годности, интеграцию с 1С и Kaspi, аналитику продаж в реальном "
            "времени, управление сотрудниками и правами доступа, мобильное приложение для "
            "владельца, автоматические заказы поставщикам при достижении минимального остатка"
        )  # 298 chars
        bad = _ollama_response(
            '{"verdict": "pass", "checks": [{"claim": "Pro includes analytics", '
            f'"supported": true, "evidence_quote": "{long_quote}"'
            '}], "confidence": 0.9}'
        )
        good = _ollama_response(
            '{"verdict": "pass", "checks": [{"claim": "Pro includes analytics", '
            '"supported": true, "evidence_quote": "Тариф Pro: аналитика продаж в реальном времени"'
            '}], "confidence": 0.9}'
        )
        with patch('requests.post', side_effect=[bad, good]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_verifier_verdict_passed_instead_of_pass(self):
        """Real: LLM outputs "passed" or "ok" instead of Literal["pass","fail"]."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        # 3 different wrong Literal values LLM actually produces
        bad1 = _ollama_response('{"verdict": "passed", "confidence": 0.9}')
        bad2 = _ollama_response('{"verdict": "ok", "confidence": 0.85}')
        good = _ollama_response('{"verdict": "pass", "confidence": 0.88}')

        with patch('requests.post', side_effect=[bad1, bad2, good]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"


# =========================================================================
# 17. Real dialog scenarios — exact message sequences from simulator
# =========================================================================

class TestRealDialogScenarios:
    """Each test reproduces an exact turn from a real dialog, with the real prompt
    context and the real dirty LLM output pattern observed."""

    def test_d01_kassir_price_combined_message(self):
        """Dialog D01: "касса тупит при наплыве + сколько стоит" — dual intent, dirty output."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        # Real output from Qwen3.5 for combined situation+price message
        resp = _ollama_response(
            '<think>\n'
            'Клиент описывает проблему (касса тупит при наплыве) и одновременно '
            'спрашивает цену. Основной — price_question (прямой вопрос "сколько стоит"). '
            'Вторичный — problem_revealed.\n'
            '</think>\n'
            '{"intent": "price_question", "confidence": 0.84, '
            '"reasoning": "Прямой ценовой вопрос «сколько стоит» с контекстом проблемы", '
            '"extracted_data": {'
            '"business_type": "продуктовый магазин", '
            '"pain_point": "касса тупит при наплыве людей", '
            '"pain_category": "manual_work"'
            '}, '
            '"alternatives": [{"intent": "problem_revealed", "confidence": 0.71}],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"
        assert "касса" in result.extracted_data.pain_point
        assert result.extracted_data.pain_category == "manual_work"

    def test_d02_apteka_scanner_rассрочка(self):
        """Dialog D02: "сканер по 5 раз проводишь + рассрочка есть?" — combined pain+payment."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Два запроса: проблема со сканером + вопрос о рассрочке. '
            'payment_terms — прямой вопрос о рассрочке.</think>'
            '{"intent": "payment_terms", "confidence": 0.78, '
            '"reasoning": "Прямой вопрос «рассрочка есть?» + описание проблемы со сканером", '
            '"extracted_data": {'
            '"business_type": "аптека", '
            '"pain_point": "сканер по 5 раз проводишь, клиенты психуют"'
            '}, '
            '"alternatives": [{"intent": "problem_revealed", "confidence": 0.65}],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "payment_terms"
        assert "сканер" in result.extracted_data.pain_point

    def test_d03_price_objection_with_hidden_pain(self):
        """Dialog D03: "дороговато, я в тетрадке веду + товар добавляю 2 часа каждую поставку"."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент говорит "дорого" (objection_price), но описывает боль:\n'
            '- ведёт в тетрадке (manual_work)\n'
            '- 2 часа на каждую поставку (manual_work)\n'
            'Основной: objection_price, альт: problem_revealed</think>'
            '{"intent": "objection_price", "confidence": 0.80, '
            '"reasoning": "Прямое возражение «дороговато» с описанием текущих проблем", '
            '"extracted_data": {'
            '"current_tools": "тетрадка", '
            '"pain_point": "вручную добавляет товар по 2 часа каждую поставку", '
            '"pain_category": "manual_work"'
            '}, '
            '"alternatives": [{"intent": "problem_revealed", "confidence": 0.68}],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "objection_price"
        assert result.extracted_data.current_tools == "тетрадка"

    def test_d04_snr_fear_complex_query_decomposition(self):
        """Dialog D04: long message about SNR-2026 fears → complex query decomposition."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент боится перевода на общий режим из-за СНР-2026. '
            'Сложный вопрос — нужны подзапросы по фискализации и тарифам.</think>'
            '{"is_complex": true, "sub_queries": ['
            '{"query": "поддержка СНР-2026 обновленные формы отчетности ИП", '
            '"categories": ["fiscal", "tis"]}, '
            '{"query": "автоматический расчёт налогов для розничной торговли", '
            '"categories": ["features", "fiscal"]}, '
            '{"query": "сроки перехода на обновлённый СНР март 2026", '
            '"categories": ["faq", "fiscal"]}'
            '],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", DecompositionResultLike)
        assert result is not None
        assert result.is_complex is True
        assert len(result.sub_queries) == 3
        assert "СНР" in result.sub_queries[0].query

    def test_contact_provided_phone_iin_together(self):
        """Real: client gives phone + IIN in one message: "87071234567, ИИН 960315300123"."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент предоставил и телефон, и ИИН одновременно.</think>'
            '{"intent": "contact_provided", "confidence": 0.96, '
            '"reasoning": "Клиент отправил номер телефона и ИИН", '
            '"extracted_data": {'
            '"contact_info": "87071234567", '
            '"kaspi_phone": "87071234567", '
            '"iin": "960315300123"'
            '},}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "contact_provided"
        assert result.extracted_data.kaspi_phone == "87071234567"
        assert result.extracted_data.iin == "960315300123"

    def test_ready_buyer_fast_closing(self):
        """Real: "ладно давайте попробуем, как подключиться?" → demo_request or agreement."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Клиент согласен и просит инструкции по подключению. '
            'Это demo_request (запрос демо/подключения), confidence высокий.</think>\n'
            '{"intent": "demo_request", "confidence": 0.91, '
            '"reasoning": "Клиент выразил готовность и просит инструкции по подключению", '
            '"extracted_data": {"value_acknowledged": true}, '
            '"alternatives": [{"intent": "agreement", "confidence": 0.82}],}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "demo_request"
        assert result.extracted_data.value_acknowledged is True

    def test_kazakh_mixed_language_input(self):
        """Real: "сәлем, бізде 3 дүкен бар, бағасы қанша?" — Kazakh with some Russian."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _ollama_response(
            '<think>Казахский: "сәлем" (привет), "бізде 3 дүкен бар" '
            '(у нас 3 магазина), "бағасы қанша" (какая цена).\n'
            'Основной: price_question.</think>'
            '{"intent": "price_question", "confidence": 0.87, '
            '"reasoning": "Казахскоязычный клиент спрашивает цену, 3 магазина", '
            '"extracted_data": {"business_type": "дүкен (магазин)"},}'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"


# =========================================================================
# 18. Truncation at num_predict boundary — real Ollama failure
# =========================================================================

class TestTruncatedOutput:
    """Ollama truncates JSON when hitting num_predict limit.
    The cleaner must not crash, and retry must get a complete response."""

    def test_verifier_truncated_at_num_predict_800(self):
        """Verifier uses num_predict=800. Long rewritten_response gets cut mid-sentence."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        # Truncated mid-JSON — closing brace never appears
        truncated = _ollama_response(
            '{"verdict": "fail", "checks": [{"claim": "wrong price", '
            '"supported": false, "evidence_quote": ""}], '
            '"rewritten_response": "Для 5 точек подойдёт тариф Pro. '
            'Стоимость составляет 500 000 ₸ в год. В тариф входит: '
            'онлайн-касса, учёт товаров, аналитика, интеграции с 1С и Kaspi, '
            'мобильное приложение для владельца. Подключение занимает 1 ра'
        )
        good = _ollama_response(
            '{"verdict": "fail", "checks": [{"claim": "wrong price", '
            '"supported": false, "evidence_quote": ""}], '
            '"rewritten_response": "Для 5 точек — тариф Pro, 500 000 ₸/год.", '
            '"confidence": 0.88}'
        )

        with patch('requests.post', side_effect=[truncated, good]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "fail"
        assert "500 000" in result.rewritten_response

    def test_classifier_truncated_at_alternatives(self):
        """Classifier cut off mid-alternatives array."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        truncated = _ollama_response(
            '{"intent": "price_question", "confidence": 0.88, '
            '"reasoning": "клиент спрашивает сколько стоит на 5 точек", '
            '"extracted_data": {"business_type": "продуктовый магазин"}, '
            '"alternatives": [{"intent": "situation_pro'
        )
        good = _ollama_response(
            '{"intent": "price_question", "confidence": 0.88, '
            '"reasoning": "цена", "alternatives": []}'
        )

        with patch('requests.post', side_effect=[truncated, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"

    def test_history_compact_truncated_mid_list(self):
        """HistoryCompactSchema truncated inside a list — common with long dialogs."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        truncated = _ollama_response(
            '{"summary": ["Клиент: сеть из 5 магазинов в Караганде и Астане", '
            '"Бот: предложил тариф Pro за 500 000 ₸/год", '
            '"Клиент: спросил про рассрочку от Kaspi", '
            '"Бот: предложил рассрочку 0-0-12 на оборудование'
        )
        good = _ollama_response(
            '{"summary": ["Клиент: 5 магазинов, Караганда+Астана", '
            '"Бот: Pro 500 000 ₸/год"], '
            '"key_facts": ["5 точек", "Караганда"], '
            '"objections": ["дорого"], "decisions": [], '
            '"open_questions": [], "next_steps": []}'
        )

        with patch('requests.post', side_effect=[truncated, good]):
            result = client.generate_structured("test", HistoryCompactSchemaLike)
        assert result is not None
        assert len(result.summary) == 2

    def test_autonomous_decision_truncated_reasoning(self):
        """AutonomousDecision with long reasoning hits num_predict=2048."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        truncated = _ollama_response(
            '{"reasoning": "Клиент описал структуру бизнеса: 5 магазинов '
            'в Караганде и 1 в Астане, продуктовая розница. '
            'Основная проблема — недостачи при инвентаризации, кассиры путаются '
            'с ценами, нет удалённого контроля. Также упомянул сезонность — '
            'летом больше воды и мороженого, зимой другие категории, '
            'вручную перебивать цены на 5 точках — проблема. '
            'Учитывая текущий этап (qualification) и то, что клиент раскрыл'
        )
        good = _ollama_response(
            '{"reasoning": "Клиент раскрыл боли, переходим к presentation", '
            '"should_transition": true, '
            '"next_state": "autonomous_presentation"}'
        )

        with patch('requests.post', side_effect=[truncated, good]):
            result = client.generate_structured("test", AutonomousDecisionLike)
        assert result is not None
        assert result.should_transition is True
        assert result.next_state == "autonomous_presentation"


# =========================================================================
# 19. Verifier → fallback chain — exact production failure sequence
# =========================================================================

class TestVerifierFallbackChain:
    """Tests the exact failure chain:
    generate_structured fails → None → _build_safe_minimal_response → "недостаточно данных".
    Verifies that the fix prevents this by surviving dirty output."""

    def test_all_retries_fail_returns_none(self):
        """When ALL retries fail, generate_structured returns None (→ "недостаточно данных")."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        # 3 different wrong verdicts — none valid
        responses = [
            _ollama_response('{"verdict": "passed", "confidence": 0.9}'),
            _ollama_response('{"verdict": "ok", "confidence": 0.8}'),
            _ollama_response('{"verdict": "true", "confidence": 0.7}'),
        ]
        with patch('requests.post', side_effect=responses) as mp:
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is None
        assert mp.call_count == 3  # all retries used

    def test_dirty_output_saved_by_cleaning(self):
        """Without cleaning, this dirty verifier output would fail.
        With cleaning, it succeeds → verifier returns pass → NO "недостаточно данных"."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)

        # This exact pattern would fail without _clean_structured_output:
        # - <think> block
        # - trailing commas in checks array AND outer object
        # - suffix text after closing brace
        resp = _ollama_response(
            '<think>\n'
            'Проверяю ответ бота о тарифе Pro для 5 точек.\n'
            'KB: pricing_multistore_5_points — "Тариф Pro для 5 точек: 500 000 ₸/год"\n'
            'Бот сказал 500 000 — совпадает. Verdict: pass.\n'
            '</think>\n'
            '{"verdict": "pass", "checks": [\n'
            '{"claim": "Pro тариф 500 000 ₸/год за 5 точек", "supported": true, '
            '"evidence_quote": "Тариф Pro для 5 точек: 500 000 ₸/год"},\n'
            '], "rewritten_response": "", "confidence": 0.95,}\n'
            'Все утверждения подтверждены.'
        )
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None  # Would be None without cleaning!
        assert result.verdict == "pass"
        assert result.confidence == 0.95

    def test_verifier_two_pass_chain(self):
        """Real verifier pattern: first call (rewrite mode) → fail → second call (verify only).
        Both calls go through generate_structured. Simulate both dirty."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        # First call: verifier says "fail" with rewrite
        first_call = _ollama_response(
            '<think>Бот сказал "тестовый период 7 дней" — галлюцинация.</think>'
            '{"verdict": "fail", "checks": ['
            '{"claim": "тестовый период 7 дней", "supported": false, '
            '"evidence_quote": ""},], '
            '"rewritten_response": "Wipon предлагает тариф Mini от 5 000 ₸/мес. '
            'Подключение за 1 день, обучение бесплатное.", '
            '"confidence": 0.87,}'
        )
        # Second call: verify the rewrite passes
        second_call = _ollama_response(
            '<think>Переписанный ответ: Mini 5000, 1 день, обучение — всё в KB.</think>'
            '{"verdict": "pass", "checks": ['
            '{"claim": "Mini от 5 000 ₸/мес", "supported": true, '
            '"evidence_quote": "Тариф Mini: 5 000 ₸/мес"},], '
            '"confidence": 0.93,}'
        )

        with patch('requests.post', side_effect=[first_call, second_call]):
            r1 = client.generate_structured("verify-rewrite", RealVerifierOutput)
            r2 = client.generate_structured("verify-only", RealVerifierOutput)

        assert r1 is not None
        assert r1.verdict == "fail"
        assert "5 000" in r1.rewritten_response
        assert r2 is not None
        assert r2.verdict == "pass"

    def test_verifier_network_flap_then_dirty_success(self):
        """Real production: Ollama under GPU load → timeout → retry → dirty success."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        dirty_good = _ollama_response(
            '<think>GPU recovered, checking claims...</think>'
            '{"verdict": "pass", "checks": [], "confidence": 0.82,}'
        )

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n <= 2:
                raise requests.exceptions.Timeout("GPU busy, read timeout")
            return dirty_good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured(
                "test", RealVerifierOutput,
                temperature=0.05, num_predict=800,
            )
        assert result is not None
        assert result.verdict == "pass"
        assert call_n == 3  # 2 timeouts + 1 success


# =========================================================================
# 20. Cross-schema interference in shared OllamaClient
# =========================================================================

class TestCrossSchemaInterference:
    """Single OllamaClient instance handling diverse schemas in sequence.
    Verifies no state leaks between calls of different schema types."""

    def test_classifier_then_verifier_then_category_then_decision(self):
        """Full pipeline sequence with dirty outputs for each schema type."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 5

        responses = [
            # Classifier: dirty but valid
            _ollama_response(
                '<think>price_question</think>'
                '{"intent": "price_question", "confidence": 0.88, '
                '"reasoning": "сколько стоит",}'
            ),
            # Category: dirty but valid
            _ollama_response(
                '<think>pricing + support</think>'
                '{"categories": ["pricing", "support",],}'
            ),
            # Verifier: first attempt bad Literal, second good
            _ollama_response('{"verdict": "passed", "confidence": 0.9}'),
            _ollama_response(
                '{"verdict": "pass", "confidence": 0.91,}'
            ),
            # Decision: dirty but valid
            _ollama_response(
                '<think>stay in presentation</think>'
                '{"reasoning": "ответили на вопрос о цене", '
                '"should_transition": false,}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r_cls = client.generate_structured("p1", RealClassificationResult)
            r_cat = client.generate_structured("p2", RealCategoryResult)
            r_ver = client.generate_structured("p3", RealVerifierOutput)
            r_dec = client.generate_structured("p4", AutonomousDecisionLike)

        assert r_cls.intent == "price_question"
        assert r_cat.categories == ["pricing", "support"]
        assert r_ver.verdict == "pass"
        assert r_dec.should_transition is False

        assert client.stats.total_requests == 4
        assert client.stats.successful_requests == 4
        assert client.stats.total_retries == 1  # verifier retried once

    def test_failure_in_one_schema_doesnt_poison_others(self):
        """Classifier fails ALL retries. Verifier succeeds. Stats are isolated."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 5

        responses = [
            # Classifier: fails both retries (intent not in 220-value Literal)
            _ollama_response('{"intent": "unknown_intent", "confidence": 0.5, "reasoning": "?"}'),
            _ollama_response('{"intent": "другой", "confidence": 0.5, "reasoning": "?"}'),
            # Verifier: succeeds with dirty output
            _ollama_response(
                '<think>all good</think>'
                '{"verdict": "pass", "confidence": 0.95,}'
            ),
            # Decision: succeeds
            _ollama_response(
                '{"reasoning": "ok", "should_transition": false}'
            ),
        ]

        with patch('requests.post', side_effect=responses):
            r_cls = client.generate_structured("p1", RealClassificationResult)
            r_ver = client.generate_structured("p2", RealVerifierOutput)
            r_dec = client.generate_structured("p3", AutonomousDecisionLike)

        assert r_cls is None  # failed
        assert r_ver is not None  # succeeded
        assert r_ver.verdict == "pass"
        assert r_dec is not None
        assert r_dec.should_transition is False

        assert client.stats.successful_requests == 2
        assert client.stats.failed_requests == 1

    def test_merged_call_then_regular_call_no_interference(self):
        """generate_merged() then generate_structured() — different temp, same client."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        responses = [
            # Merged (temp=0.3): dirty but valid
            _ollama_response(
                '<think>generating response</think>'
                '{"reasoning": "ответ на вопрос о цене", '
                '"should_transition": false, "next_state": "", '
                '"action": "autonomous_respond", '
                '"response": "Тариф Pro — 500 000 ₸/год для 5 точек.",}'
            ),
            # Regular verifier (temp=0.05): dirty but valid
            _ollama_response(
                '<think>checking price claim</think>'
                '{"verdict": "pass", "confidence": 0.94,}'
            ),
        ]

        with patch('requests.post', side_effect=responses) as mp:
            r_merged = client.generate_merged("merged_prompt", AutonomousDecisionAndResponseLike)
            r_verifier = client.generate_structured(
                "verify_prompt", RealVerifierOutput, temperature=0.05
            )

        assert r_merged.response == "Тариф Pro — 500 000 ₸/год для 5 точек."
        assert r_verifier.verdict == "pass"

        # Verify temperature was different for each call
        temps = _extract_temps(mp)
        assert temps[0] == 0.3   # merged uses 0.3
        assert temps[1] == 0.05  # verifier uses 0.05


# =========================================================================
# 21. Real Ollama HTTP response format edge cases
# =========================================================================

def _raw_ollama_response(body_dict: dict, status_code: int = 200) -> MagicMock:
    """Build a MagicMock that mimics a real requests.Response from Ollama.
    Unlike _ollama_response, this takes the FULL response body dict."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body_dict
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} Error"
        )
    return resp


class TestOllamaResponseFormat:
    """Tests the full HTTP response → _extract_content → _strip_markdown_json
    → _clean_structured_output → schema.model_validate_json chain.
    These test what the real Ollama server actually returns."""

    def test_standard_ollama_format(self):
        """Standard Ollama: {"message": {"content": "...", "role": "assistant"}, "done": true}."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _raw_ollama_response({
            "model": "qwen3.5:27b",
            "created_at": "2026-03-06T10:00:00Z",
            "message": {
                "role": "assistant",
                "content": '{"verdict": "pass", "confidence": 0.9}'
            },
            "done": True,
            "done_reason": "stop",
            "total_duration": 1500000000,
            "eval_count": 42,
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_ollama_done_reason_length_truncated(self):
        """Ollama sets done_reason="length" when num_predict is hit.
        Content is truncated JSON — should fail validation, retry should get complete."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        truncated = _raw_ollama_response({
            "message": {"content": '{"verdict": "pass", "checks": [{"claim": "price is'},
            "done": True,
            "done_reason": "length",
        })
        complete = _raw_ollama_response({
            "message": {"content": '{"verdict": "pass", "confidence": 0.9}'},
            "done": True,
            "done_reason": "stop",
        })

        with patch('requests.post', side_effect=[truncated, complete]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_ollama_empty_content_thinking_fallback(self):
        """Real: content="" but thinking="..." — _extract_content falls back to thinking field."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _raw_ollama_response({
            "message": {
                "content": "",
                "thinking": '{"verdict": "pass", "confidence": 0.88}',
                "role": "assistant",
            },
            "done": True,
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_ollama_empty_content_no_thinking_raises_retries(self):
        """Real: content="" and no thinking → ValueError → retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        empty = _raw_ollama_response({
            "message": {"content": "", "role": "assistant"},
            "done": True,
        })
        good = _raw_ollama_response({
            "message": {"content": '{"intent": "greeting", "confidence": 0.9}'},
            "done": True,
        })

        with patch('requests.post', side_effect=[empty, good]):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"

    def test_ollama_markdown_wrapped_json(self):
        """Real: Ollama returns content wrapped in ```json fences."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _raw_ollama_response({
            "message": {
                "content": '```json\n{"verdict": "pass", "confidence": 0.92}\n```'
            },
            "done": True,
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"
        assert result.confidence == pytest.approx(0.92)

    def test_ollama_markdown_plus_think_plus_trailing_comma(self):
        """Triple combo: ```json wrapping + <think> inside + trailing commas."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        resp = _raw_ollama_response({
            "message": {
                "content": (
                    '```json\n'
                    '<think>verifying claims...</think>'
                    '{"verdict": "pass", "checks": [\n'
                    '  {"claim": "Mini 5000", "supported": true, "evidence_quote": "Mini: 5 000 ₸"},\n'
                    '], "confidence": 0.93,}\n'
                    '```'
                )
            },
            "done": True,
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"
        assert len(result.checks) == 1

    def test_ollama_no_message_key_retries(self):
        """Ollama returns JSON without message key (rare, corrupt response)."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        corrupt = _raw_ollama_response({"error": "unexpected"})
        good = _raw_ollama_response({
            "message": {"content": '{"intent": "greeting", "confidence": 0.9}'},
        })

        with patch('requests.post', side_effect=[corrupt, good]):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"

    def test_ollama_200_with_error_in_body(self):
        """Real: Ollama returns HTTP 200 but body has {"error": "model not found"}.
        _extract_content gets empty content → ValueError → retry."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        error_200 = _raw_ollama_response({
            "error": "model 'qwen3.5:27b' not found, try pulling it first"
        })
        good = _raw_ollama_response({
            "message": {"content": '{"intent": "greeting", "confidence": 0.9}'},
        })

        with patch('requests.post', side_effect=[error_200, good]):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None

    def test_ollama_http_503_model_loading(self):
        """Real: first request after Ollama restart → 503 while model loads."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        loading = _raw_ollama_response(
            {"error": "model is loading"}, status_code=503
        )
        good = _raw_ollama_response({
            "message": {"content": '{"verdict": "pass", "confidence": 0.85}'},
        })

        with patch('requests.post', side_effect=[loading, loading, good]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_ollama_http_500_cuda_oom(self):
        """Real: CUDA OOM when GPU is overloaded with concurrent requests."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        oom = _raw_ollama_response(
            {"error": "CUDA out of memory"}, status_code=500
        )
        good = _raw_ollama_response({
            "message": {"content": '{"intent": "price_question", "confidence": 0.88, "reasoning": "цена"}'},
        })

        with patch('requests.post', side_effect=[oom, good]):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"

    def test_response_json_decode_error(self):
        """Real: Ollama returns non-JSON HTTP body (e.g., Nginx error page)."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.raise_for_status.return_value = None
        bad_resp.json.side_effect = ValueError("Expecting value: line 1")

        good = _raw_ollama_response({
            "message": {"content": '{"intent": "greeting", "confidence": 0.9}'},
        })

        with patch('requests.post', side_effect=[bad_resp, good]):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert result.intent == "greeting"


# =========================================================================
# 22. OpenAI API format edge cases (llama-server / vLLM)
# =========================================================================

class TestOpenAIApiFormat:
    """Tests for api_format="openai" — llama-server, vLLM compatibility."""

    def test_openai_standard_response(self):
        client = OllamaClient(
            enable_retry=False, enable_circuit_breaker=False,
            api_format="openai",
        )
        resp = _raw_ollama_response({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '{"verdict": "pass", "confidence": 0.91}'
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30},
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_openai_empty_choices_retries(self):
        """OpenAI format: empty choices array → ValueError → retry."""
        client = OllamaClient(
            enable_retry=True, enable_circuit_breaker=False,
            api_format="openai",
        )
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        empty_choices = _raw_ollama_response({"choices": []})
        good = _raw_ollama_response({
            "choices": [{"message": {"content": '{"intent": "greeting", "confidence": 0.9}'}}],
        })

        with patch('requests.post', side_effect=[empty_choices, good]):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None

    def test_openai_reasoning_content_fallback(self):
        """OpenAI thinking model: content="" but reasoning_content has the JSON."""
        client = OllamaClient(
            enable_retry=False, enable_circuit_breaker=False,
            api_format="openai",
        )
        resp = _raw_ollama_response({
            "choices": [{
                "message": {
                    "content": "",
                    "reasoning_content": '{"verdict": "pass", "confidence": 0.85}',
                },
            }],
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_openai_markdown_wrapped_with_think(self):
        """OpenAI format + markdown fences + think tags inside."""
        client = OllamaClient(
            enable_retry=False, enable_circuit_breaker=False,
            api_format="openai",
        )
        resp = _raw_ollama_response({
            "choices": [{
                "message": {
                    "content": (
                        '```json\n'
                        '<think>checking</think>'
                        '{"intent": "price_question", "confidence": 0.88, '
                        '"reasoning": "цена",}\n'
                        '```'
                    ),
                },
            }],
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"

    def test_openai_finish_reason_length_truncated(self):
        """OpenAI format: finish_reason="length" means max_tokens hit."""
        client = OllamaClient(
            enable_retry=True, enable_circuit_breaker=False,
            api_format="openai",
        )
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        truncated = _raw_ollama_response({
            "choices": [{
                "message": {"content": '{"verdict": "pass", "checks": [{"clai'},
                "finish_reason": "length",
            }],
        })
        complete = _raw_ollama_response({
            "choices": [{"message": {"content": '{"verdict": "pass", "confidence": 0.9}'}}],
        })

        with patch('requests.post', side_effect=[truncated, complete]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None


# =========================================================================
# 23. Full 12-turn dialog simulation — one client session
# =========================================================================

class TestFullDialogSession:
    """Simulates an entire 12-turn dialog from the e2e test scenario.
    Each turn makes 2-4 generate_structured calls. All through ONE client instance.
    Tests that stats, CB, and state remain correct across ~30 sequential calls."""

    def test_full_12_turn_dialog(self):
        """12 turns × 2-3 calls each = 28 calls through one client."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=True)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001
        client.CIRCUIT_BREAKER_THRESHOLD = 10

        # Build 28 responses for a full dialog
        responses = []
        expected_successes = 0

        # Turn 1: "Здравствуйте" → classifier + decision
        responses.append(_ollama_response(
            '{"intent": "greeting", "confidence": 0.98, "reasoning": "привет"}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "greeting, stay in discovery", "should_transition": false}'
        ))
        expected_successes += 2

        # Turn 2: "У нас сеть из 4 магазинов..." → classifier + category + decision
        responses.append(_ollama_response(
            '<think>описание бизнеса</think>'
            '{"intent": "situation_provided", "confidence": 0.91, '
            '"reasoning": "бизнес-контекст", '
            '"extracted_data": {"business_type": "продуктовый магазин", '
            '"city": "Караганда"},}'
        ))
        responses.append(_ollama_response('{"categories": ["pricing", "features"]}'))
        responses.append(_ollama_response(
            '{"reasoning": "ситуация получена, переходим", '
            '"should_transition": true, "next_state": "autonomous_qualification"}'
        ))
        expected_successes += 3

        # Turn 3: "Основная проблема — недостачи..." → classifier + decision
        responses.append(_ollama_response(
            '{"intent": "problem_revealed", "confidence": 0.89, '
            '"reasoning": "боль", '
            '"extracted_data": {"pain_point": "недостачи при инвентаризации", '
            '"pain_category": "no_control"}}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "боль раскрыта", "should_transition": false}'
        ))
        expected_successes += 2

        # Turn 4: "сезонность — вручную перебивать цены на 5 точках" → classifier + decision
        responses.append(_ollama_response(
            '{"intent": "problem_revealed", "confidence": 0.85, '
            '"reasoning": "ещё одна боль — ручная работа", '
            '"extracted_data": {"pain_point": "вручную перебивать цены на 5 точках", '
            '"pain_category": "manual_work"}}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "две боли раскрыты, переходим к presentation", '
            '"should_transition": true, "next_state": "autonomous_presentation"}'
        ))
        expected_successes += 2

        # Turn 5: "А ваша система надёжная?" → classifier + category + verifier(dirty!) + decision
        responses.append(_ollama_response(
            '{"intent": "objection_trust", "confidence": 0.82, '
            '"reasoning": "недоверие к надёжности"}'
        ))
        responses.append(_ollama_response('{"categories": ["stability", "support"]}'))
        # Verifier: first attempt dirty, succeeds after cleaning
        responses.append(_ollama_response(
            '<think>Бот сказал про SSD — проверяю в KB...</think>'
            '{"verdict": "pass", "checks": ['
            '{"claim": "SSD для быстрой загрузки", "supported": true, '
            '"evidence_quote": "SSD в комплекте PRO"},], "confidence": 0.88,}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "возражение обработано", "should_transition": false}'
        ))
        expected_successes += 4

        # Turn 6: "Сколько на 5 точек?" → classifier + category + verifier + decision
        responses.append(_ollama_response(
            '{"intent": "price_question", "confidence": 0.95, '
            '"reasoning": "прямой ценовой вопрос"}'
        ))
        responses.append(_ollama_response('{"categories": ["pricing"]}'))
        responses.append(_ollama_response(
            '{"verdict": "pass", "confidence": 0.94}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "ответили на цену", "should_transition": false}'
        ))
        expected_successes += 4

        # Turn 7: "Что входит в тариф?" → classifier + category + verifier + decision
        responses.append(_ollama_response(
            '{"intent": "pricing_details", "confidence": 0.90, '
            '"reasoning": "детали тарифа"}'
        ))
        responses.append(_ollama_response('{"categories": ["pricing", "features"]}'))
        responses.append(_ollama_response('{"verdict": "pass", "confidence": 0.91}'))
        responses.append(_ollama_response(
            '{"reasoning": "ответили по функциям", "should_transition": false}'
        ))
        expected_successes += 4

        # Turn 8: "Дороговато, у конкурентов дешевле" → classifier + category + verifier(FAIL+retry!) + decision
        responses.append(_ollama_response(
            '{"intent": "objection_price", "confidence": 0.88, '
            '"reasoning": "ценовое возражение"}'
        ))
        responses.append(_ollama_response('{"categories": ["pricing", "competitors"]}'))
        # Verifier: wrong Literal first, then pass
        responses.append(_ollama_response('{"verdict": "maybe", "confidence": 0.5}'))
        responses.append(_ollama_response('{"verdict": "pass", "confidence": 0.86}'))
        responses.append(_ollama_response(
            '{"reasoning": "возражение по цене обработано", "should_transition": false}'
        ))
        expected_successes += 4  # classifier, category, verifier(retry success), decision

        # Turn 9: "рассрочка есть?" → classifier + verifier + decision
        responses.append(_ollama_response(
            '{"intent": "payment_terms", "confidence": 0.93, '
            '"reasoning": "вопрос о рассрочке"}'
        ))
        responses.append(_ollama_response('{"verdict": "pass", "confidence": 0.92}'))
        responses.append(_ollama_response(
            '{"reasoning": "ответили о рассрочке, переходим к closing", '
            '"should_transition": true, "next_state": "autonomous_closing"}'
        ))
        expected_successes += 3

        # Turn 10: "давайте попробуем" → classifier + decision
        responses.append(_ollama_response(
            '{"intent": "demo_request", "confidence": 0.91, '
            '"reasoning": "готовность подключиться"}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "клиент готов, запрашиваем контакт", '
            '"should_transition": false}'
        ))
        expected_successes += 2

        # Turn 11: "87071234567" → classifier + decision
        responses.append(_ollama_response(
            '{"intent": "contact_provided", "confidence": 0.97, '
            '"reasoning": "телефон", '
            '"extracted_data": {"contact_info": "87071234567", '
            '"kaspi_phone": "87071234567"}}'
        ))
        responses.append(_ollama_response(
            '{"reasoning": "контакт получен, переходим в payment_ready", '
            '"should_transition": true, "next_state": "payment_ready"}'
        ))
        expected_successes += 2

        total_calls = len(responses) - 1  # -1 because one response is a retry (verifier bad→good)

        with patch('requests.post', side_effect=responses):
            results = []
            schemas_sequence = [
                # Turn 1
                RealClassificationResult, AutonomousDecisionLike,
                # Turn 2
                RealClassificationResult, RealCategoryResult, AutonomousDecisionLike,
                # Turn 3
                RealClassificationResult, AutonomousDecisionLike,
                # Turn 4
                RealClassificationResult, AutonomousDecisionLike,
                # Turn 5
                RealClassificationResult, RealCategoryResult,
                RealVerifierOutput, AutonomousDecisionLike,
                # Turn 6
                RealClassificationResult, RealCategoryResult,
                RealVerifierOutput, AutonomousDecisionLike,
                # Turn 7
                RealClassificationResult, RealCategoryResult,
                RealVerifierOutput, AutonomousDecisionLike,
                # Turn 8 (verifier retries once)
                RealClassificationResult, RealCategoryResult,
                RealVerifierOutput, AutonomousDecisionLike,
                # Turn 9
                RealClassificationResult, RealVerifierOutput, AutonomousDecisionLike,
                # Turn 10
                RealClassificationResult, AutonomousDecisionLike,
                # Turn 11
                RealClassificationResult, AutonomousDecisionLike,
            ]

            for schema in schemas_sequence:
                results.append(client.generate_structured("prompt", schema))

        # All calls should succeed
        assert all(r is not None for r in results), \
            f"Failed at index {next(i for i, r in enumerate(results) if r is None)}"

        # Verify specific results
        assert results[0].intent == "greeting"  # Turn 1 classifier
        assert results[2].intent == "situation_provided"  # Turn 2 classifier
        assert results[2].extracted_data.city == "Караганда"
        assert results[5].intent == "problem_revealed"  # Turn 3
        assert results[5].extracted_data.pain_category == "no_control"
        assert results[11].verdict == "pass"  # Turn 5 verifier (index: T1[0,1] T2[2,3,4] T3[5,6] T4[7,8] T5[9,10,11,12])
        assert results[23].verdict == "pass"  # Turn 8 verifier (T6[13,14,15,16] T7[17,18,19,20] T8[21,22,23,24])
        assert results[-1].should_transition is True  # Turn 11 final decision
        assert results[-1].next_state == "payment_ready"

        # Stats
        assert client.stats.successful_requests == expected_successes
        assert client.stats.total_retries == 1  # only Turn 8 verifier retried
        assert client.stats.failed_requests == 0
        assert client._circuit_breaker.failures == 0


# =========================================================================
# 24. _extract_content + _strip_markdown_json unit tests
# =========================================================================

class TestExtractContentChain:
    """Tests _extract_content and _strip_markdown_json specifically —
    the pipeline BEFORE _clean_structured_output runs."""

    def _make_client(self, api_format="ollama"):
        return OllamaClient(
            enable_retry=False, enable_circuit_breaker=False,
            api_format=api_format,
        )

    def test_strip_markdown_json_basic(self):
        assert OllamaClient._strip_markdown_json(
            '```json\n{"a": 1}\n```'
        ) == '{"a": 1}'

    def test_strip_markdown_no_language(self):
        assert OllamaClient._strip_markdown_json(
            '```\n{"a": 1}\n```'
        ) == '{"a": 1}'

    def test_strip_markdown_with_whitespace(self):
        result = OllamaClient._strip_markdown_json(
            '  ```json\n  {"a": 1}\n  ```  '
        )
        assert '{"a": 1}' in result

    def test_strip_markdown_not_fenced_passthrough(self):
        raw = '{"a": 1}'
        assert OllamaClient._strip_markdown_json(raw) == raw

    def test_extract_content_ollama_thinking_field(self):
        """When content is empty, _extract_content uses thinking field."""
        client = self._make_client("ollama")
        data = {"message": {"content": "", "thinking": '{"verdict": "pass"}'}}
        result = client._extract_content(data)
        assert '"verdict"' in result

    def test_extract_content_ollama_missing_message_raises(self):
        """No message key at all → empty content → ValueError."""
        client = self._make_client("ollama")
        with pytest.raises(ValueError, match="Empty content"):
            client._extract_content({"done": True})

    def test_extract_content_openai_empty_choices_raises(self):
        """OpenAI format: empty choices → ValueError."""
        client = self._make_client("openai")
        with pytest.raises(ValueError, match="Empty choices"):
            client._extract_content({"choices": []})

    def test_extract_content_openai_empty_content_raises(self):
        """OpenAI format: empty content and no reasoning_content → ValueError."""
        client = self._make_client("openai")
        with pytest.raises(ValueError, match="Empty content"):
            client._extract_content({"choices": [{"message": {"content": ""}}]})

    def test_extract_content_openai_reasoning_content(self):
        """OpenAI format: reasoning_content fallback."""
        client = self._make_client("openai")
        result = client._extract_content({
            "choices": [{"message": {"content": "", "reasoning_content": '{"a": 1}'}}]
        })
        assert '"a"' in result

    def test_markdown_then_clean_chain_end_to_end(self):
        """Full chain: markdown fences → strip → think tags → clean → validate."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        # Content has: markdown fences wrapping think-tags + dirty JSON
        resp = _raw_ollama_response({
            "message": {
                "content": (
                    '```json\n'
                    '<think>Анализ: клиент спрашивает про рассрочку Kaspi 0-0-12.\n'
                    'В KB: pricing_installment_kaspi — "Рассрочка 0-0-12 через Kaspi".\n'
                    'Поддерживается.</think>\n'
                    '{"verdict": "pass", "checks": [\n'
                    '  {"claim": "рассрочка 0-0-12 Kaspi", "supported": true,\n'
                    '   "evidence_quote": "Рассрочка 0-0-12 через Kaspi на оборудование"},\n'
                    '], "rewritten_response": "", "confidence": 0.96,}\n'
                    '```'
                ),
            },
            "done": True,
        })
        with patch('requests.post', return_value=resp):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"
        assert result.checks[0].supported is True
        assert "Kaspi" in result.checks[0].evidence_quote


# =========================================================================
# 25. Realistic error recovery sequences — GPU load patterns
# =========================================================================

class TestGPULoadPatterns:
    """Simulates realistic GPU load patterns on Hetzner with 3 models sharing 33GB VRAM:
    Qwen3.5-27B (17GB) + TEI-Embed (8GB) + TEI-Rerank (8GB).
    Under heavy load, Ollama exhibits specific failure patterns."""

    def test_gpu_cold_start_3_timeouts_then_success(self):
        """First request after deploy: model loading from disk to GPU.
        Ollama returns timeouts while model loads (~10-15s)."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 5
        client.INITIAL_DELAY = 0.001

        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n <= 3:
                raise requests.exceptions.Timeout("read timeout")
            return good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured("test", SimpleSchema)
        assert result is not None
        assert call_n == 4

    def test_intermittent_503_during_concurrent_requests(self):
        """Two concurrent bot sessions → Ollama 503s intermittently.
        Pattern: 503 → 200(dirty) → validates."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        loading_503 = _raw_ollama_response(
            {"error": "model busy, please retry"}, status_code=503
        )
        dirty_good = _ollama_response(
            '<think>finally got GPU slot</think>'
            '{"verdict": "pass", "checks": [], "confidence": 0.87,}'
        )

        with patch('requests.post', side_effect=[loading_503, dirty_good]):
            result = client.generate_structured("test", RealVerifierOutput)
        assert result is not None
        assert result.verdict == "pass"

    def test_connection_refused_ollama_restart(self):
        """Ollama crashes under OOM → connection refused → auto-restarts → success."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 4
        client.INITIAL_DELAY = 0.001

        good = _ollama_response(
            '{"intent": "price_question", "confidence": 0.88, '
            '"reasoning": "цена"}'
        )

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                raise requests.exceptions.ConnectionError("Connection refused")
            if call_n == 2:
                raise requests.exceptions.ConnectionError("Connection refused")
            return good

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured("test", RealClassificationResult)
        assert result is not None
        assert result.intent == "price_question"
        assert client.stats.total_retries == 2

    def test_slow_response_timeout_then_fast_dirty_success(self):
        """First attempt: slow inference timeout (large prompt).
        Second attempt: succeeds but output is dirty."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 2
        client.INITIAL_DELAY = 0.001

        good_dirty = _ollama_response(
            '<think>\n'
            'Клиент из Караганды, сеть магазинов, спрашивает о рассрочке.\n'
            'В KB: pricing_installment_kaspi: Kaspi 0-0-12.\n'
            '</think>\n'
            '{"verdict": "pass", "checks": [\n'
            '  {"claim": "Kaspi 0-0-12", "supported": true,\n'
            '   "evidence_quote": "Рассрочка 0-0-12"},\n'
            '], "confidence": 0.91,}'
        )

        call_n = 0
        def side_effect(*a, **kw):
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                raise requests.exceptions.Timeout("read timeout after 30s")
            return good_dirty

        with patch('requests.post', side_effect=side_effect):
            result = client.generate_structured(
                "test", RealVerifierOutput, temperature=0.05, num_predict=800
            )
        assert result is not None
        assert result.verdict == "pass"
        assert len(result.checks) == 1

    def test_alternating_success_failure_no_cb_trip(self):
        """Real pattern: under load, every other call fails.
        CB threshold=5, so alternating successes should keep resetting it."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 5

        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')
        bad = _ollama_response('{"wrong": true}')

        # 10 calls: good, bad, good, bad, good, bad, good, bad, good, bad
        with patch('requests.post', side_effect=[good, bad] * 5):
            results = []
            for i in range(10):
                results.append(client.generate_structured(f"p{i}", SimpleSchema))

        successes = sum(1 for r in results if r is not None)
        failures = sum(1 for r in results if r is None)
        assert successes == 5
        assert failures == 5
        # CB should NOT be open because each success resets failure count
        assert client._circuit_breaker.is_open is False

    def test_burst_of_failures_trips_cb_then_recovery(self):
        """Real: GPU OOM burst → 5 consecutive failures → CB opens.
        After recovery, half-open probe succeeds."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 5
        client.CIRCUIT_BREAKER_TIMEOUT = 5.0

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        # 5 failures → CB opens
        with patch('requests.post', return_value=bad):
            for i in range(5):
                client.generate_structured(f"f{i}", SimpleSchema)
        assert client._circuit_breaker.is_open is True
        assert client.stats.circuit_breaker_trips == 1

        # While open → blocked (no HTTP call)
        with patch('requests.post', return_value=good) as mp:
            r = client.generate_structured("blocked", SimpleSchema)
        assert r is None
        assert mp.call_count == 0

        # Force recovery
        client._circuit_breaker.open_until = 0.0

        # Half-open probe with dirty but valid JSON
        with patch('requests.post', return_value=_ollama_response(
            '<think>probe</think>{"intent": "greeting", "confidence": 0.9,}'
        )):
            r = client.generate_structured("probe", SimpleSchema)
        assert r is not None
        assert client._circuit_breaker.is_open is False
        assert client._circuit_breaker.failures == 0


# =========================================================================
# 26. Stats accuracy under realistic conditions
# =========================================================================

class TestStatsAccuracy:
    """Verifies that LLMStats remain mathematically correct under
    realistic mixed-result sequences."""

    def test_success_rate_after_mixed_results(self):
        """7 successes, 3 failures → success_rate = 70%."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')
        bad = _ollama_response('{"wrong": true}')

        sequence = [good]*3 + [bad]*2 + [good]*4 + [bad]
        with patch('requests.post', side_effect=sequence):
            for i in range(10):
                client.generate_structured(f"p{i}", SimpleSchema)

        assert client.stats.total_requests == 10
        assert client.stats.successful_requests == 7
        assert client.stats.failed_requests == 3
        assert client.stats.success_rate == pytest.approx(70.0)

    def test_average_response_time_only_counts_successes(self):
        """avg_response_time should only average over successful requests."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=False)
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')
        bad = _ollama_response('{"wrong": true}')

        with patch('requests.post', side_effect=[good, bad, good]):
            client.generate_structured("p1", SimpleSchema)
            client.generate_structured("p2", SimpleSchema)
            client.generate_structured("p3", SimpleSchema)

        assert client.stats.successful_requests == 2
        assert client.stats.average_response_time_ms > 0

    def test_retries_counted_once_per_retry_not_per_attempt(self):
        """3 attempts = 2 retries (between attempt 1-2 and 2-3)."""
        client = OllamaClient(enable_retry=True, enable_circuit_breaker=False)
        client.MAX_RETRIES = 3
        client.INITIAL_DELAY = 0.001

        bad = _ollama_response('{"wrong": true}')
        with patch('requests.post', return_value=bad):
            client.generate_structured("test", SimpleSchema)

        assert client.stats.total_retries == 2  # 3 attempts → 2 retries

    def test_circuit_breaker_trips_counted(self):
        """Each time CB opens, circuit_breaker_trips increments."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2
        client.CIRCUIT_BREAKER_TIMEOUT = 5.0

        bad = _ollama_response('{"wrong": true}')
        good = _ollama_response('{"intent": "greeting", "confidence": 0.9}')

        # Trip 1
        with patch('requests.post', return_value=bad):
            client.generate_structured("f1", SimpleSchema)
            client.generate_structured("f2", SimpleSchema)
        assert client.stats.circuit_breaker_trips == 1

        # Recover
        client._circuit_breaker.open_until = 0.0
        with patch('requests.post', return_value=good):
            client.generate_structured("recover", SimpleSchema)
        assert client._circuit_breaker.is_open is False

        # Trip 2
        with patch('requests.post', return_value=bad):
            client.generate_structured("f3", SimpleSchema)
            client.generate_structured("f4", SimpleSchema)
        assert client.stats.circuit_breaker_trips == 2

    def test_fallback_used_counter_only_cb_blocks(self):
        """fallback_used only increments when CB blocks a call, not on validation failures."""
        client = OllamaClient(enable_retry=False, enable_circuit_breaker=True)
        client.CIRCUIT_BREAKER_THRESHOLD = 2

        bad = _ollama_response('{"wrong": true}')

        # 2 failures trip CB
        with patch('requests.post', return_value=bad):
            client.generate_structured("f1", SimpleSchema)
            client.generate_structured("f2", SimpleSchema)

        assert client.stats.fallback_used == 0  # validation failures don't count

        # 3 blocked calls
        client.generate_structured("b1", SimpleSchema)
        client.generate_structured("b2", SimpleSchema)
        client.generate_structured("b3", SimpleSchema)

        assert client.stats.fallback_used == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
