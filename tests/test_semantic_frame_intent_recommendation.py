"""Tests for semantic-frame intent recommendation fields."""

from src.classifier.semantic_frame import SemanticFrameExtractor


class _NoopLLM:
    def generate_structured(self, *args, **kwargs):
        return None


def test_heuristic_frame_sets_recommended_intent_to_primary():
    extractor = SemanticFrameExtractor(_NoopLLM())

    frame = extractor._heuristic_frame(
        message="какие функции есть?",
        primary_intent="question_features",
        secondary_signals=[],
    )

    assert frame["recommended_intent"] == "question_features"
    assert frame["override_intent"] is False


def test_merge_frame_falls_back_to_primary_for_unknown_recommended_intent():
    extractor = SemanticFrameExtractor(_NoopLLM())

    heuristic = extractor._heuristic_frame(
        message="какие продукты подойдут",
        primary_intent="question_features",
        secondary_signals=[],
    )
    merged = extractor._merge_frames(
        heuristic,
        {
            "recommended_intent": "unknown_intent_name",
            "override_intent": True,
            "recommended_confidence": 0.92,
        },
    )

    assert merged["recommended_intent"] == "question_features"
    assert merged["override_intent"] is False


def test_merge_frame_infers_recommended_intent_when_llm_silent():
    extractor = SemanticFrameExtractor(_NoopLLM())

    heuristic = extractor._heuristic_frame(
        message="какие продукты мне подойдут для 8 точек?",
        primary_intent="situation_provided",
        secondary_signals=[],
    )
    merged = extractor._merge_frames(heuristic, {})

    assert merged["recommended_intent"] == "question_features"
    assert merged["override_intent"] is True
    assert merged["recommended_confidence"] > 0.8
