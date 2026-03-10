from unittest.mock import patch

from src.knowledge import pain_retriever as pr


def test_pain_search_kassa_positive(monkeypatch):
    pr.reset_pain_retriever()

    # Pain retriever creates its own CascadeRetriever with use_embeddings=True,
    # but TEI may not be running in test env — patch to disable embeddings.
    with patch('src.knowledge.retriever.CascadeRetriever._init_embeddings'):
        retriever = pr.get_pain_retriever()
        results = retriever.search("зависает касса в час пик", top_k=2)

    assert results
    assert results[0].section.topic == "kassa_freeze_peak_hours_601"


def test_retrieve_pain_context_negative_greeting_returns_empty(monkeypatch):
    pr.reset_pain_retriever()

    with patch('src.knowledge.retriever.CascadeRetriever._init_embeddings'):
        assert pr.retrieve_pain_context("здравствуйте") == ""
