from src.factual_verifier import FactualVerifier
from src.generator import ResponseGenerator
from src.unknown_kb_fallbacks import (
    LEGACY_KB_FALLBACK_RE,
    is_approved_unknown_kb_fallback,
)


def test_approved_unknown_fallback_is_not_legacy_handoff():
    text = "Я уточню этот вопрос и чуть позже отпишу вам."
    assert is_approved_unknown_kb_fallback(text) is True
    assert LEGACY_KB_FALLBACK_RE.search(text) is None


def test_legacy_handoff_still_detected_as_forbidden():
    text = "Я уточню у коллег и позже вернусь с ответом."
    assert LEGACY_KB_FALLBACK_RE.search(text) is not None


def test_generator_does_not_strip_approved_unknown_fallback():
    text = "Я уточню этот вопрос и чуть позже отпишу вам."
    assert ResponseGenerator._COLLEAGUE_FALLBACK_RE.search(text) is None


def test_factual_verifier_forbidden_fallback_regex_excludes_approved_unknown_text():
    text = "Я уточню этот вопрос и чуть позже отпишу вам."
    assert FactualVerifier._FORBIDDEN_FALLBACK_RE.search(text) is None
