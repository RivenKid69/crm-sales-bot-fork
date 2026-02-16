"""
Targeted tests for enhanced autonomous retrieval pipeline.

No real LLM calls, no semantic models/embeddings.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from src.feature_flags import FeatureFlags
from src.generator import ResponseGenerator
from src.knowledge.base import KnowledgeSection
from src.knowledge.enhanced_retrieval import (
    ComplexityDetector,
    DecompositionResult,
    EnhancedRetrievalPipeline,
    LongContextReorder,
    MultiQueryRetriever,
    QueryDecomposer,
    QueryRewriter,
    SubQuery,
)
from src.knowledge.retriever import MatchStage, SearchResult


def _mk_result(
    category: str,
    topic: str,
    facts: str,
    *,
    score: float = 1.0,
    sensitive: bool = False,
    urls: Optional[List[Dict[str, str]]] = None,
) -> SearchResult:
    section = KnowledgeSection(
        category=category,
        topic=topic,
        keywords=[topic],
        facts=facts,
        priority=5,
        sensitive=sensitive,
        urls=urls or [],
    )
    return SearchResult(section=section, score=score, stage=MatchStage.EXACT)


class FakeRetriever:
    def __init__(self, mapping: Dict[Tuple[str, Optional[Tuple[str, ...]]], List[SearchResult]]):
        self.mapping = mapping
        self.calls: List[Dict[str, Any]] = []

    def search(self, query: str, categories=None, top_k: int = 3) -> List[SearchResult]:
        categories_key = tuple(categories) if categories else None
        self.calls.append({
            "query": query,
            "categories": categories,
            "top_k": top_k,
        })
        results = self.mapping.get((query, categories_key))
        if results is None:
            results = self.mapping.get((query, None), [])
        return list(results)[:top_k]


class FakeCategoryRouter:
    def __init__(self, categories: List[str]):
        self.categories = categories
        self.calls: List[str] = []

    def route(self, query: str) -> List[str]:
        self.calls.append(query)
        return list(self.categories)


class DummyFlow:
    name = "autonomous"
    states = {
        "autonomous_discovery": {"kb_categories": ["products", "features"]},
    }
    templates: Dict[str, Any] = {}

    def get_template(self, action: str):
        return None


class TestQueryRewriter:
    def test_rewrites_followup_with_history(self):
        llm = MagicMock()
        llm.generate.return_value = "Сколько стоит Wipon Kassa?\nКомментарий"
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        result = rewriter.rewrite(
            user_message="А сколько это стоит?",
            history=[{"user": "Расскажите про Wipon Kassa", "bot": "Это касса для розницы"}],
        )

        assert result == "Сколько стоит Wipon Kassa?"
        llm.generate.assert_called_once()
        _, kwargs = llm.generate.call_args
        assert kwargs["allow_fallback"] is False

    def test_fallback_to_original_on_llm_error(self):
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("timeout")
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        original = "А сколько это стоит?"
        result = rewriter.rewrite(
            user_message=original,
            history=[{"user": "Про Wipon", "bot": "..."}, {"user": "ок", "bot": "..."}],
        )

        assert result == original

    def test_no_rewrite_without_history(self):
        llm = MagicMock()
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        original = "А сколько это стоит?"
        result = rewriter.rewrite(user_message=original, history=[])

        assert result == original
        llm.generate.assert_not_called()

    def test_noisy_output_is_cleaned(self):
        llm = MagicMock()
        llm.generate.return_value = "Переписанный запрос:   Сколько стоит тариф Basic?\nПояснение"
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        result = rewriter.rewrite(
            user_message="Сколько это стоит?",
            history=[{"user": "Мы смотрим тариф Basic", "bot": "Хорошо"}],
        )

        assert result == "Сколько стоит тариф Basic?"

    def test_non_followup_skips_llm(self):
        llm = MagicMock()
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        message = "Расскажите про интеграцию с Kaspi Pay"
        result = rewriter.rewrite(user_message=message, history=[{"user": "x", "bot": "y"}])

        assert result == message
        llm.generate.assert_not_called()


class TestComplexityDetector:
    def test_simple_query_is_not_complex(self):
        detector = ComplexityDetector()
        assert detector.is_complex("Какие есть интеграции с Kaspi?") is False

    def test_strong_marker_detected(self):
        detector = ComplexityDetector()
        query = "Сравните тарифы Wipon для кафе и ресторана с учётом оборудования"
        assert detector.is_complex(query) is True

    def test_weak_markers_need_more_evidence(self):
        detector = ComplexityDetector()
        query = "Расскажите про тарифы и оборудование и интеграции для сети ресторанов"
        assert detector.is_complex(query) is True

    def test_pattern_complexity_detected(self):
        detector = ComplexityDetector()
        query = "Как подключить эквайринг и сколько это будет стоить для кафе"
        assert detector.is_complex(query) is True


class TestQueryDecomposer:
    def test_decomposition_uses_structured_output(self):
        llm = MagicMock()
        llm.generate_structured.return_value = DecompositionResult(
            is_complex=True,
            sub_queries=[
                SubQuery(query="Сколько стоит Wipon Kassa для кафе", categories=["pricing", "products"]),
                SubQuery(query="Какое оборудование нужно для Wipon Kassa в кафе", categories=["equipment"]),
            ],
        )
        decomposer = QueryDecomposer(llm=llm, max_sub_queries=4)

        result = decomposer.decompose("Сравните тарифы и оборудование для кафе")

        assert result is not None
        assert len(result.sub_queries) == 2
        prompt = llm.generate_structured.call_args[0][0]
        assert "Допустимые категории" in prompt
        assert "integrations" in prompt

    def test_decomposition_failure_returns_none(self):
        llm = MagicMock()
        llm.generate_structured.side_effect = RuntimeError("LLM error")
        decomposer = QueryDecomposer(llm=llm, max_sub_queries=4)

        assert decomposer.decompose("Сложный запрос") is None


class TestMultiQueryRetriever:
    def test_rrf_merge_ranks_by_reciprocal_fusion(self):
        a = _mk_result("products", "a", "A")
        b = _mk_result("pricing", "b", "B")
        c = _mk_result("features", "c", "C")
        d = _mk_result("equipment", "d", "D")

        mqr = MultiQueryRetriever(rrf_k=60)
        merged = mqr.merge_rankings([[a, b, c], [b, d, a]])

        assert [r.section.topic for r in merged] == ["b", "a", "d", "c"]

    def test_run_uses_subquery_categories_and_deduplicates(self):
        base = _mk_result("products", "kassa", "Wipon Kassa")
        price = _mk_result("pricing", "tariffs", "Тарифы")
        eq = _mk_result("equipment", "terminal", "Терминалы")

        retriever = FakeRetriever({
            ("anchor", ("products",)): [base, price],
            ("q1", ("pricing",)): [price],
            ("q2", ("equipment",)): [eq, base],
        })
        mqr = MultiQueryRetriever(rrf_k=60)
        _, merged, _ = mqr.run(
            retriever=retriever,
            base_query="anchor",
            base_categories=["products"],
            sub_queries=[
                SubQuery(query="q1", categories=["pricing"]),
                SubQuery(query="q2", categories=["equipment"]),
            ],
            top_k_per_query=3,
        )

        assert len(retriever.calls) == 3
        assert retriever.calls[1]["categories"] == ["pricing"]
        assert retriever.calls[2]["categories"] == ["equipment"]
        assert len({f"{r.section.category}/{r.section.topic}" for r in merged}) == len(merged)


class TestLongContextReorder:
    def test_zigzag_order(self):
        ordered = [
            _mk_result("c", "t1", "1"),
            _mk_result("c", "t2", "2"),
            _mk_result("c", "t3", "3"),
            _mk_result("c", "t4", "4"),
            _mk_result("c", "t5", "5"),
        ]

        result = LongContextReorder.reorder(ordered)

        assert [r.section.topic for r in result] == ["t1", "t3", "t5", "t4", "t2"]


class TestEnhancedRetrievalPipeline:
    def test_full_pipeline_with_decomposition_and_sensitive_filter(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        rewritten_query = "Сравните тарифы Wipon Kassa и оборудование для кафе"
        llm.generate.return_value = rewritten_query
        llm.generate_structured.return_value = DecompositionResult(
            is_complex=True,
            sub_queries=[
                SubQuery(query="Сколько стоит Wipon Kassa для кафе", categories=["pricing"]),
                SubQuery(query="Какое оборудование нужно для Wipon Kassa в кафе", categories=["equipment"]),
            ],
        )

        router = FakeCategoryRouter(["pricing", "products"])
        pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=router)
        pipeline.max_kb_chars = 40000
        pipeline.top_k_per_sub_query = 3

        sensitive = _mk_result("support", "demo_creds", "Login: admin Password: 123456", sensitive=True)
        pricing = _mk_result("pricing", "tariffs", "Тариф Basic 12 000 тг", urls=[{"url": "https://u/price", "label": "Pricing"}])
        product = _mk_result("products", "wipon_kassa", "Wipon Kassa для кафе", urls=[{"url": "https://u/product", "label": "Product"}])
        equipment = _mk_result("equipment", "terminal", "Поддержка терминалов и сканеров", urls=[{"url": "https://u/equipment", "label": "Equipment"}])

        retriever = FakeRetriever({
            (rewritten_query, ("pricing", "products")): [sensitive, pricing, product],
            ("Сколько стоит Wipon Kassa для кафе", ("pricing",)): [pricing],
            ("Какое оборудование нужно для Wipon Kassa в кафе", ("equipment",)): [equipment],
        })
        monkeypatch.setattr(er, "get_retriever", lambda: retriever)

        captured: Dict[str, Any] = {}

        def fake_state_loader(**kwargs):
            captured["recently_used_keys"] = kwargs["recently_used_keys"]
            return (
                "[features/loyalty]\nЕсть программа лояльности.\n",
                [{"url": "https://u/state", "label": "State"}],
                ["features/loyalty"],
            )

        monkeypatch.setattr(er, "load_facts_for_state", fake_state_loader)

        facts, urls, fact_keys = pipeline.retrieve(
            user_message="А сколько это стоит и какое оборудование нужно?",
            intent="question_features",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={"autonomous_discovery": {"kb_categories": ["products"]}}),
            kb=object(),
            recently_used_keys={"faq/greeting"},
            history=[{"user": "Нужна Wipon Kassa", "bot": "Понял"}],
        )

        assert "demo_creds" not in facts
        assert "Password" not in facts
        assert "[pricing/tariffs]" in facts
        assert "[equipment/terminal]" in facts
        assert "=== КОНТЕКСТ ЭТАПА ===" in facts
        assert "[features/loyalty]" in facts
        assert len(retriever.calls) == 3
        assert router.calls == [rewritten_query]
        assert {"pricing/tariffs", "products/wipon_kassa", "equipment/terminal"}.issubset(
            set(captured["recently_used_keys"])
        )
        assert {"pricing/tariffs", "features/loyalty"}.issubset(set(fact_keys))
        assert {u["url"] for u in urls} == {
            "https://u/price",
            "https://u/product",
            "https://u/equipment",
            "https://u/state",
        }

    def test_skip_intent_uses_only_state_facts(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=FakeCategoryRouter(["faq"]))

        monkeypatch.setattr(er, "get_retriever", lambda: (_ for _ in ()).throw(AssertionError("should not call retriever")))
        monkeypatch.setattr(
            er,
            "load_facts_for_state",
            lambda **kwargs: ("[faq/base]\nSTATE\n", [{"url": "https://state", "label": "state"}], ["faq/base"]),
        )

        facts, urls, keys = pipeline.retrieve(
            user_message="Привет",
            intent="greeting",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys=set(),
            history=[],
        )

        assert facts == "[faq/base]\nSTATE\n"
        assert urls == [{"url": "https://state", "label": "state"}]
        assert keys == ["faq/base"]
        llm.generate.assert_not_called()

    def test_decomposition_failure_preserves_base_results(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        llm.generate.return_value = "Сравните тарифы и оборудование для кафе"
        llm.generate_structured.side_effect = RuntimeError("decomposer failed")

        pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=None)
        base = _mk_result("pricing", "tariffs", "Базовые тарифы")
        retriever = FakeRetriever({
            ("Сравните тарифы и оборудование для кафе", None): [base],
        })
        monkeypatch.setattr(er, "get_retriever", lambda: retriever)
        monkeypatch.setattr(
            er,
            "load_facts_for_state",
            lambda **kwargs: ("[features/base]\nstate\n", [], ["features/base"]),
        )

        facts, _, _ = pipeline.retrieve(
            user_message="А сколько это стоит и какое оборудование?",
            intent="question_features",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys=set(),
            history=[{"user": "Мы смотрим Wipon", "bot": "Хорошо"}],
        )

        assert "[pricing/tariffs]" in facts
        assert len(retriever.calls) == 1

    def test_state_context_is_truncated_to_remaining_budget(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        pipeline = EnhancedRetrievalPipeline(llm=llm, category_router=None)
        pipeline.max_kb_chars = 180

        query_result = _mk_result("pricing", "tariffs", "Q" * 120)
        retriever = FakeRetriever({
            ("Расскажите стоимость тарифа Basic для кафе", None): [query_result],
        })
        monkeypatch.setattr(er, "get_retriever", lambda: retriever)

        state_text = "[features/state]\n" + ("S" * 300)
        monkeypatch.setattr(er, "load_facts_for_state", lambda **kwargs: (state_text, [], []))

        query_text, _, _ = pipeline._build_query_context([query_result])
        expected_state_part = state_text[: max(0, pipeline.max_kb_chars - len(query_text))]

        facts, _, _ = pipeline.retrieve(
            user_message="Расскажите стоимость тарифа Basic для кафе",
            intent="price_question",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys=set(),
            history=[],
        )

        assert facts.endswith(expected_state_part)
        assert "[pricing/tariffs]" in facts


class TestGeneratorIntegration:
    def test_generator_uses_lazy_enhanced_pipeline_once(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er
        import src.knowledge.loader as loader
        import src.generator as generator_module

        kb = SimpleNamespace(company_name="Wipon", company_description="CRM", sections=[])
        monkeypatch.setattr(loader, "load_knowledge_base", lambda: kb)
        monkeypatch.setattr(
            generator_module,
            "get_retriever",
            lambda: SimpleNamespace(kb=kb, get_company_info=lambda: "Wipon: CRM"),
        )
        monkeypatch.setattr(
            generator_module.flags,
            "is_enabled",
            lambda flag: flag == "enhanced_autonomous_retrieval",
        )

        init_calls: List[Any] = []
        retrieve_calls: List[Dict[str, Any]] = []

        class StubPipeline:
            def __init__(self, llm, category_router):
                init_calls.append((llm, category_router))

            def retrieve(self, **kwargs):
                retrieve_calls.append(kwargs)
                return (
                    "[pricing/tariffs]\nТариф Basic\n",
                    [{"url": "https://u/price", "label": "Pricing"}],
                    ["pricing/tariffs"],
                )

        monkeypatch.setattr(er, "EnhancedRetrievalPipeline", StubPipeline)
        monkeypatch.setattr(
            "src.knowledge.autonomous_kb.load_facts_for_state",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("fallback should not be called")),
        )

        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        gen = ResponseGenerator(llm=llm, flow=DummyFlow())

        context = {
            "intent": "question_features",
            "state": "autonomous_discovery",
            "user_message": "Сколько стоит?",
            "history": [{"user": "Нужна касса", "bot": "Есть решение"}],
            "recent_fact_keys": ["faq/greeting"],
            "collected_data": {},
            "missing_data": [],
            "goal": "goal",
        }

        gen.generate("answer_with_facts", context)
        gen.generate("answer_with_facts", context)

        assert len(init_calls) == 1
        assert len(retrieve_calls) == 2
        assert retrieve_calls[0]["history"] == context["history"]
        prompt = llm.generate.call_args[0][0]
        assert "[pricing/tariffs]" in prompt

    def test_generator_falls_back_to_state_retrieval_on_enhanced_failure(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er
        import src.knowledge.loader as loader
        import src.generator as generator_module

        kb = SimpleNamespace(company_name="Wipon", company_description="CRM", sections=[])
        monkeypatch.setattr(loader, "load_knowledge_base", lambda: kb)
        monkeypatch.setattr(
            generator_module,
            "get_retriever",
            lambda: SimpleNamespace(kb=kb, get_company_info=lambda: "Wipon: CRM"),
        )
        monkeypatch.setattr(
            generator_module.flags,
            "is_enabled",
            lambda flag: flag == "enhanced_autonomous_retrieval",
        )

        class FailingPipeline:
            def __init__(self, llm, category_router):
                pass

            def retrieve(self, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(er, "EnhancedRetrievalPipeline", FailingPipeline)
        monkeypatch.setattr(
            "src.knowledge.autonomous_kb.load_facts_for_state",
            lambda **kwargs: ("[features/fallback]\nfallback facts\n", [], ["features/fallback"]),
        )

        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        gen = ResponseGenerator(llm=llm, flow=DummyFlow())

        context = {
            "intent": "question_features",
            "state": "autonomous_discovery",
            "user_message": "Что умеет система?",
            "history": [],
            "recent_fact_keys": [],
            "collected_data": {},
            "missing_data": [],
            "goal": "goal",
        }

        gen.generate("answer_with_facts", context)

        prompt = llm.generate.call_args[0][0]
        assert "[features/fallback]" in prompt


def test_feature_flag_for_enhanced_retrieval_exists():
    ff = FeatureFlags()
    assert "enhanced_autonomous_retrieval" in FeatureFlags.DEFAULTS
    assert "enhanced_autonomous_retrieval" in FeatureFlags.GROUPS["autonomous"]
    assert isinstance(ff.enhanced_autonomous_retrieval, bool)
