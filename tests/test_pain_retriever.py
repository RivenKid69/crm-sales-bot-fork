import numpy as np

from src.knowledge import pain_retriever as pr


class _MainRetrieverNoEmbeddings:
    embedder = None
    np = None
    _use_prefixes = False


class _DummyEmbedder:
    def encode(self, texts):
        if isinstance(texts, str):
            return np.array([0.1, 0.2], dtype=float)
        return [np.array([0.1, 0.2], dtype=float) for _ in texts]


class _MainRetrieverWithEmbeddings:
    def __init__(self):
        self.embedder = _DummyEmbedder()
        self.np = np
        self._use_prefixes = True


def test_pain_search_kassa_positive_without_main_embedder(monkeypatch):
    pr.reset_pain_retriever()
    monkeypatch.setattr(pr, "get_retriever", lambda: _MainRetrieverNoEmbeddings())

    retriever = pr.get_pain_retriever()
    results = retriever.search("зависает касса в час пик", top_k=2)

    assert results
    assert results[0].section.topic == "kassa_freeze_peak_hours_601"


def test_retrieve_pain_context_negative_greeting_returns_empty(monkeypatch):
    pr.reset_pain_retriever()
    monkeypatch.setattr(pr, "get_retriever", lambda: _MainRetrieverNoEmbeddings())

    assert pr.retrieve_pain_context("здравствуйте") == ""


def test_pain_retriever_shares_main_embedder_object(monkeypatch):
    pr.reset_pain_retriever()
    main = _MainRetrieverWithEmbeddings()
    monkeypatch.setattr(pr, "get_retriever", lambda: main)

    retriever = pr.get_pain_retriever()

    assert retriever.embedder is main.embedder
    assert retriever.use_embeddings is True
    assert retriever.kb.sections[0].embedding is not None
