"""
Deep regression and edge-case tests for enhanced autonomous retrieval.

All tests are offline and deterministic:
- no real LLM calls,
- no semantic/embedding models.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple
from unittest.mock import MagicMock

import pytest

from src.generator import ResponseGenerator
from src.knowledge.base import KnowledgeBase, KnowledgeSection
from src.knowledge.enhanced_retrieval import (
    ComplexityDetector,
    EnhancedRetrievalPipeline,
    MultiQueryRetriever,
    QueryRewriter,
    SubQuery,
)
from src.knowledge.retriever import CascadeRetriever, MatchStage, SearchResult


def _mk_result(
    category: str,
    topic: str,
    facts: str,
    *,
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
    return SearchResult(section=section, score=1.0, stage=MatchStage.EXACT)


class DummyAutonomousFlow:
    name = "autonomous"
    states = {"autonomous_discovery": {"kb_categories": ["products", "features"]}}
    templates = {
        "custom_action": {
            "template": "{company_info}\n{retrieved_facts}\n{retrieved_urls}",
        }
    }

    def get_template(self, action: str):
        cfg = self.templates.get(action)
        if cfg:
            return cfg.get("template")
        return None


class SpyRetriever:
    def __init__(self, inner: CascadeRetriever):
        self.inner = inner
        self.calls: List[Dict[str, Any]] = []

    def search(self, query: str, category=None, categories=None, top_k: int = 3):
        self.calls.append({
            "query": query,
            "category": category,
            "categories": categories,
            "top_k": top_k,
        })
        return self.inner.search(query, category=category, categories=categories, top_k=top_k)


class StaticCategoryRouter:
    def __init__(self, categories: List[str]):
        self.categories = categories
        self.calls: List[str] = []

    def route(self, query: str) -> List[str]:
        self.calls.append(query)
        return list(self.categories)


class TestQueryRewriterDeep:
    def test_uses_only_last_three_turns_in_prompt(self):
        llm = MagicMock()
        llm.generate.return_value = "Самостоятельный запрос"
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)
        history = [
            {"user": "u1", "bot": "b1"},
            {"user": "u2", "bot": "b2"},
            {"user": "u3", "bot": "b3"},
            {"user": "u4", "bot": "b4"},
        ]

        rewriter.rewrite("А сколько это стоит?", history=history)

        prompt = llm.generate.call_args[0][0]
        assert "u1" not in prompt
        assert "u2" in prompt and "u3" in prompt and "u4" in prompt

    def test_short_query_triggers_rewrite_without_pronoun(self):
        llm = MagicMock()
        llm.generate.return_value = "Цена тарифа Basic Wipon Kassa"
        rewriter = QueryRewriter(llm=llm, rewrite_min_words=4)

        result = rewriter.rewrite(
            user_message="Сколько стоит?",
            history=[{"user": "Интересует Wipon Kassa", "bot": "Ок"}],
        )

        assert result == "Цена тарифа Basic Wipon Kassa"
        llm.generate.assert_called_once()


class TestComplexityDetectorDeep:
    def test_single_weak_marker_under_threshold_is_not_complex(self):
        detector = ComplexityDetector()
        query = "Расскажите про тарифы и подключение"
        assert detector.is_complex(query) is False

    def test_two_question_marks_is_complex(self):
        detector = ComplexityDetector()
        assert detector.is_complex("Что входит в тариф??") is True


class TestMultiQueryRetrieverDeep:
    def test_duplicate_inside_single_ranking_counted_once(self):
        a1 = _mk_result("pricing", "tariffs", "A")
        a2 = _mk_result("pricing", "tariffs", "A-dup")
        b = _mk_result("products", "kassa", "B")
        mqr = MultiQueryRetriever(rrf_k=60)

        merged = mqr.merge_rankings([[a1, a2], [b]])

        keys = [f"{r.section.category}/{r.section.topic}" for r in merged]
        assert keys.count("pricing/tariffs") == 1


class TestEnhancedPipelineDeep:
    def _mk_pipeline(self, llm=None, router=None):
        llm = llm or MagicMock()
        return EnhancedRetrievalPipeline(llm=llm, category_router=router)

    def test_empty_user_query_returns_state_context_without_separator(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        pipe = self._mk_pipeline(llm=llm, router=None)
        monkeypatch.setattr(er, "get_retriever", lambda: MagicMock())
        monkeypatch.setattr(
            er,
            "load_facts_for_state",
            lambda **kwargs: ("[features/state]\nstate facts\n", [], ["features/state"]),
        )

        facts, _, _ = pipe.retrieve(
            user_message="",
            intent="question_features",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys=set(),
            history=[],
        )

        assert facts == "[features/state]\nstate facts\n"
        assert "=== КОНТЕКСТ ЭТАПА ===" not in facts

    def test_category_router_none_passes_categories_none(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        pipe = self._mk_pipeline(llm=llm, router=None)
        pipe.complexity_detector.is_complex = lambda _: False

        retriever = MagicMock()
        retriever.search.return_value = [_mk_result("products", "kassa", "facts")]
        monkeypatch.setattr(er, "get_retriever", lambda: retriever)
        monkeypatch.setattr(
            er,
            "load_facts_for_state",
            lambda **kwargs: ("", [], []),
        )

        pipe.retrieve(
            user_message="Расскажите про Wipon Kassa",
            intent="question_features",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys=set(),
            history=[],
        )

        assert retriever.search.call_args.kwargs["categories"] is None

    def test_invalid_subquery_categories_fallback_to_all_sections(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        llm.generate.return_value = "Сколько стоит касса wipon"
        llm.generate_structured.return_value = {
            "is_complex": True,
            "sub_queries": [
                {"query": "цена кассы wipon", "categories": ["invalid_category"]},
            ],
        }

        kb = KnowledgeBase(
            company_name="Wipon",
            company_description="CRM",
            sections=[
                KnowledgeSection(
                    category="pricing",
                    topic="tariffs",
                    keywords=["цена", "стоит", "тариф"],
                    facts="Тарифы от 12 000 тг",
                    priority=8,
                ),
                KnowledgeSection(
                    category="products",
                    topic="kassa",
                    keywords=["касса", "wipon"],
                    facts="Wipon Kassa для розницы",
                    priority=7,
                ),
            ],
        )
        base_retriever = CascadeRetriever(knowledge_base=kb, use_embeddings=False)
        spy = SpyRetriever(base_retriever)

        router = StaticCategoryRouter(["pricing"])
        pipe = self._mk_pipeline(llm=llm, router=router)
        pipe.complexity_detector.is_complex = lambda _: True
        monkeypatch.setattr(er, "get_retriever", lambda: spy)
        monkeypatch.setattr(er, "load_facts_for_state", lambda **kwargs: ("", [], []))

        facts, _, _ = pipe.retrieve(
            user_message="А сколько это стоит?",
            intent="question_features",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=kb,
            recently_used_keys=set(),
            history=[{"user": "Нужна касса Wipon", "bot": "Понял"}],
        )

        assert any(call["categories"] == ["invalid_category"] for call in spy.calls)
        assert "[pricing/tariffs]" in facts

    def test_query_context_capped_at_max_chars(self):
        llm = MagicMock()
        pipe = self._mk_pipeline(llm=llm, router=None)
        pipe.max_kb_chars = 220

        results = [
            _mk_result("c", "t1", "A" * 120),
            _mk_result("c", "t2", "B" * 120),
            _mk_result("c", "t3", "C" * 120),
        ]
        text, _, _ = pipe._build_query_context(results)

        assert len(text) <= pipe.max_kb_chars + 10

    def test_merge_urls_and_fact_keys_deduplicate(self):
        llm = MagicMock()
        pipe = self._mk_pipeline(llm=llm, router=None)

        merged_urls = pipe._merge_urls(
            [{"url": "https://a", "label": "A"}, {"url": "https://b", "label": "B"}],
            [{"url": "https://b", "label": "B2"}, {"url": "https://c", "label": "C"}],
        )
        merged_keys = pipe._merge_fact_keys(
            ["pricing/tariffs", "products/kassa"],
            ["products/kassa", "features/loyalty"],
        )

        assert [u["url"] for u in merged_urls] == ["https://a", "https://b", "https://c"]
        assert merged_keys == ["pricing/tariffs", "products/kassa", "features/loyalty"]

    def test_state_recently_used_union_contains_query_keys(self, monkeypatch):
        import src.knowledge.enhanced_retrieval as er

        llm = MagicMock()
        pipe = self._mk_pipeline(llm=llm, router=None)

        retriever = MagicMock()
        retriever.search.return_value = [_mk_result("pricing", "tariffs", "price facts")]
        monkeypatch.setattr(er, "get_retriever", lambda: retriever)

        captured: Dict[str, Set[str]] = {}

        def fake_loader(**kwargs):
            captured["recently_used"] = set(kwargs["recently_used_keys"])
            return "", [], []

        monkeypatch.setattr(er, "load_facts_for_state", fake_loader)

        pipe.retrieve(
            user_message="Цена тарифа",
            intent="price_question",
            state="autonomous_discovery",
            flow_config=SimpleNamespace(states={}),
            kb=object(),
            recently_used_keys={"faq/seen"},
            history=[],
        )

        assert "faq/seen" in captured["recently_used"]
        assert "pricing/tariffs" in captured["recently_used"]


class TestGeneratorDeepIntegration:
    def _setup_common_patches(self, monkeypatch):
        import src.generator as generator_module
        import src.knowledge.loader as loader

        kb = SimpleNamespace(company_name="Wipon", company_description="CRM platform", sections=[])
        monkeypatch.setattr(loader, "load_knowledge_base", lambda: kb)
        monkeypatch.setattr(
            generator_module,
            "get_retriever",
            lambda: SimpleNamespace(kb=kb, get_company_info=lambda: "Wipon: CRM platform"),
        )
        return kb, generator_module

    def test_flag_disabled_keeps_old_state_based_retrieval(self, monkeypatch):
        kb, generator_module = self._setup_common_patches(monkeypatch)
        monkeypatch.setattr(generator_module.flags, "is_enabled", lambda flag: False)

        # Must not initialize enhanced pipeline when flag is off.
        class ShouldNotInit:
            def __init__(self, *args, **kwargs):
                raise AssertionError("enhanced pipeline should not be initialized")

        monkeypatch.setattr("src.knowledge.enhanced_retrieval.EnhancedRetrievalPipeline", ShouldNotInit)
        monkeypatch.setattr(
            "src.knowledge.autonomous_kb.load_facts_for_state",
            lambda **kwargs: ("[features/legacy]\nlegacy facts\n", [], ["features/legacy"]),
        )

        llm = MagicMock()
        llm.generate.return_value = "ok"
        gen = ResponseGenerator(llm=llm, flow=DummyAutonomousFlow())

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
        assert "[features/legacy]" in prompt
        assert gen._enhanced_pipeline is None

    def test_constructor_failure_falls_back_to_legacy_loader(self, monkeypatch):
        _, generator_module = self._setup_common_patches(monkeypatch)
        monkeypatch.setattr(
            generator_module.flags,
            "is_enabled",
            lambda flag: flag == "enhanced_autonomous_retrieval",
        )

        class FailingCtor:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("init failed")

        monkeypatch.setattr("src.knowledge.enhanced_retrieval.EnhancedRetrievalPipeline", FailingCtor)
        monkeypatch.setattr(
            "src.knowledge.autonomous_kb.load_facts_for_state",
            lambda **kwargs: ("[features/fallback]\nfallback\n", [], ["features/fallback"]),
        )

        llm = MagicMock()
        llm.generate.return_value = "ok"
        gen = ResponseGenerator(llm=llm, flow=DummyAutonomousFlow())

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

    def test_autonomous_company_info_still_comes_from_kb(self, monkeypatch):
        self._setup_common_patches(monkeypatch)
        monkeypatch.setattr(
            "src.knowledge.autonomous_kb.load_facts_for_state",
            lambda **kwargs: ("[features/facts]\nhello\n", [], ["features/facts"]),
        )

        import src.generator as generator_module

        monkeypatch.setattr(generator_module.flags, "is_enabled", lambda flag: False)

        llm = MagicMock()
        llm.generate.return_value = "ok"
        gen = ResponseGenerator(llm=llm, flow=DummyAutonomousFlow())

        context = {
            "intent": "question_features",
            "state": "autonomous_discovery",
            "user_message": "test",
            "history": [],
            "recent_fact_keys": [],
            "collected_data": {},
            "missing_data": [],
            "goal": "goal",
        }
        gen.generate("custom_action", context)
        prompt = llm.generate.call_args[0][0]
        assert "Wipon: CRM platform" in prompt
        assert "[features/facts]" in prompt
