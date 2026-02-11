"""
Regression tests for the Factual Hallucination Chain fix.

Tests cover:
1. Template grounding — Q&A templates use {retrieved_facts}, not {product_overview} alone
2. Rename completeness — {facts} is gone, {product_overview} is used where needed
3. Category coverage — all KB categories are reachable via INTENT_TO_CATEGORY
4. Skip retrieval — SKIP_RETRIEVAL_INTENTS works correctly
"""

import re
import warnings
import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

# =========================================================================
# Helpers
# =========================================================================

BASE_PROMPTS_PATH = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "_base" / "prompts.yaml"
SPIN_PROMPTS_PATH = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "spin_selling" / "prompts.yaml"


def _load_yaml_templates(path: Path) -> dict:
    """Load YAML and return templates dict."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("templates", {})


def _get_all_yaml_templates() -> dict:
    """Load all YAML templates from _base and spin_selling."""
    templates = {}
    if BASE_PROMPTS_PATH.exists():
        templates.update(_load_yaml_templates(BASE_PROMPTS_PATH))
    if SPIN_PROMPTS_PATH.exists():
        templates.update(_load_yaml_templates(SPIN_PROMPTS_PATH))
    return templates


# =========================================================================
# 1. Template Grounding Tests
# =========================================================================

class TestTemplateGrounding:
    """Templates that answer questions MUST use {retrieved_facts} for grounding."""

    # Templates that have addresses_question=true but are action-oriented
    # (scheduling, empathy, brief responses) — they don't need KB retrieval.
    ACTION_ONLY_TEMPLATES = frozenset({
        "handle_objection_no_time", "handle_objection_think",
        "schedule_demo", "schedule_callback", "provide_references",
        "schedule_consultation",
        "calculate_roi_response", "share_value", "answer_briefly",
    })

    def test_answering_templates_have_retrieved_facts(self):
        """Q&A templates with addresses_question: true MUST contain {retrieved_facts}."""
        templates = _get_all_yaml_templates()
        violations = []
        for name, tpl in templates.items():
            if tpl.get("addresses_question") and name not in self.ACTION_ONLY_TEMPLATES:
                content = tpl.get("template", "")
                if "{retrieved_facts}" not in content:
                    violations.append(name)
        assert not violations, (
            f"Q&A templates with addresses_question=true missing {{retrieved_facts}}: {violations}"
        )

    def test_answering_templates_not_only_product_overview(self):
        """NO template with addresses_question=true should use {product_overview} as ONLY facts source."""
        templates = _get_all_yaml_templates()
        violations = []
        for name, tpl in templates.items():
            if tpl.get("addresses_question"):
                content = tpl.get("template", "")
                has_overview = "{product_overview}" in content
                has_retrieved = "{retrieved_facts}" in content
                if has_overview and not has_retrieved:
                    violations.append(name)
        assert not violations, (
            f"Templates with addresses_question=true using ONLY {{product_overview}}: {violations}"
        )

    def test_config_py_answering_templates_have_retrieved_facts(self):
        """config.py PROMPT_TEMPLATES that answer questions should use {retrieved_facts}."""
        from src.config import PROMPT_TEMPLATES

        # Templates that answer factual questions
        answering_templates = [
            "answer_with_facts",
            "answer_and_continue",
            "answer_with_knowledge",
            "answer_with_summary",
            "handle_objection_competitor",
        ]
        violations = []
        for name in answering_templates:
            tpl = PROMPT_TEMPLATES.get(name, "")
            if tpl and "{retrieved_facts}" not in tpl:
                violations.append(name)
        assert not violations, (
            f"config.py answering templates missing {{retrieved_facts}}: {violations}"
        )


# =========================================================================
# 2. Rename Completeness Tests
# =========================================================================

class TestRenameCompleteness:
    """{facts} should not appear anywhere in templates or generator."""

    def test_no_facts_in_yaml_templates(self):
        """{facts} does NOT appear in any YAML template."""
        templates = _get_all_yaml_templates()
        violations = []
        for name, tpl in templates.items():
            content = tpl.get("template", "")
            params = tpl.get("parameters", {})
            required = params.get("required", [])
            optional = params.get("optional", [])
            all_params = required + optional
            if "{facts}" in content or "facts" in all_params:
                violations.append(name)
        assert not violations, (
            f"Templates still referencing {{facts}}: {violations}"
        )

    def test_no_facts_in_config_py_templates(self):
        """{facts} does NOT appear in any config.py PROMPT_TEMPLATES."""
        from src.config import PROMPT_TEMPLATES
        violations = []
        for name, tpl in PROMPT_TEMPLATES.items():
            if "{facts}" in tpl:
                violations.append(name)
        assert not violations, (
            f"config.py PROMPT_TEMPLATES still referencing {{facts}}: {violations}"
        )

    def test_generator_uses_product_overview_key(self):
        """generator.py variables dict has 'product_overview' key, NOT 'facts'."""
        import inspect
        from src.generator import ResponseGenerator
        source = inspect.getsource(ResponseGenerator.generate)
        # Should have "product_overview" key
        assert '"product_overview"' in source, "generator.generate() should use 'product_overview' key"
        # Should NOT have "facts" key (except in retrieved_facts)
        # Check for standalone "facts" key assignment
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"facts"') and "retrieved_facts" not in stripped:
                pytest.fail(f"Found 'facts' key in generator.generate(): {stripped}")

    def test_product_overview_in_templates_that_need_it(self):
        """{product_overview} appears in templates that legitimately need product overview."""
        templates = _get_all_yaml_templates()
        overview_templates = [
            "presentation", "handle_objection",
            "reframe_value", "handle_repeated_objection", "empathize_and_redirect",
            "compare_with_competitor", "answer_with_roi",
            "answer_technical_question", "answer_security_question",
            "explain_support_options", "explain_training_options",
            "explain_implementation_process",
        ]
        missing = []
        for name in overview_templates:
            tpl = templates.get(name, {})
            content = tpl.get("template", "")
            if "{product_overview}" not in content:
                missing.append(name)
        assert not missing, (
            f"Templates that should have {{product_overview}} but don't: {missing}"
        )


# =========================================================================
# 3. Category Coverage Tests
# =========================================================================

class TestCategoryCoverage:
    """All KB categories should be reachable via INTENT_TO_CATEGORY."""

    def test_question_features_includes_orphan_categories(self):
        """question_features includes all 5 previously orphan categories."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY
        qf = INTENT_TO_CATEGORY.get("question_features", [])
        orphans = {"equipment", "employees", "fiscal", "stability", "faq"}
        for cat in orphans:
            assert cat in qf, f"Orphan category '{cat}' missing from question_features"

    def test_no_empty_lists_in_intent_to_category(self):
        """No empty [] values in INTENT_TO_CATEGORY."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY
        empty = [k for k, v in INTENT_TO_CATEGORY.items() if v == []]
        assert not empty, f"INTENT_TO_CATEGORY has empty [] for intents: {empty}"

    def test_all_mapped_categories_exist_in_kb(self):
        """All categories in INTENT_TO_CATEGORY values exist in KB FILE_TO_CATEGORY."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY
        from src.knowledge.loader import FILE_TO_CATEGORY

        kb_categories = set(FILE_TO_CATEGORY.values())
        mapped = set()
        for cats in INTENT_TO_CATEGORY.values():
            mapped.update(cats)

        unknown = mapped - kb_categories
        assert not unknown, (
            f"INTENT_TO_CATEGORY references non-existent categories: {unknown}"
        )

    def test_validation_warns_on_orphan_categories(self):
        """_validate_category_coverage warns when categories are orphaned."""
        from src.knowledge.retriever import _validate_category_coverage

        # All categories covered — no warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _validate_category_coverage({"features", "products"})
            orphan_warnings = [x for x in w if "KB categories not in INTENT_TO_CATEGORY" in str(x.message)]
            assert len(orphan_warnings) == 0, "Should not warn when all categories are covered"

        # Add unknown category — should warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _validate_category_coverage({"features", "products", "totally_new_category"})
            orphan_warnings = [x for x in w if "KB categories not in INTENT_TO_CATEGORY" in str(x.message)]
            assert len(orphan_warnings) == 1, "Should warn about orphan category"
            assert "totally_new_category" in str(orphan_warnings[0].message)


# =========================================================================
# 4. Skip Retrieval Tests
# =========================================================================

class TestSkipRetrieval:
    """SKIP_RETRIEVAL_INTENTS should prevent unnecessary KB lookups."""

    def test_skip_retrieval_intents_exists(self):
        """SKIP_RETRIEVAL_INTENTS exists as frozenset."""
        from src.knowledge.retriever import SKIP_RETRIEVAL_INTENTS
        assert isinstance(SKIP_RETRIEVAL_INTENTS, frozenset)

    def test_skip_intents_content(self):
        """greeting, farewell ARE in SKIP_RETRIEVAL_INTENTS."""
        from src.knowledge.retriever import SKIP_RETRIEVAL_INTENTS
        assert "greeting" in SKIP_RETRIEVAL_INTENTS
        assert "farewell" in SKIP_RETRIEVAL_INTENTS
        assert "small_talk" in SKIP_RETRIEVAL_INTENTS
        assert "situation_provided" in SKIP_RETRIEVAL_INTENTS
        assert "problem_revealed" in SKIP_RETRIEVAL_INTENTS

    def test_request_brevity_not_in_skip(self):
        """request_brevity NOT in SKIP_RETRIEVAL_INTENTS (it needs facts for brief answers)."""
        from src.knowledge.retriever import SKIP_RETRIEVAL_INTENTS
        assert "request_brevity" not in SKIP_RETRIEVAL_INTENTS

    def test_retrieve_returns_empty_for_skip_intents(self):
        """retrieve() returns empty string for skip intents."""
        from src.knowledge.retriever import CascadeRetriever, SKIP_RETRIEVAL_INTENTS
        from src.knowledge.base import KnowledgeBase, KnowledgeSection

        # Create a retriever with minimal KB
        section = KnowledgeSection(
            category="faq",
            topic="test",
            keywords=["привет", "здравствуйте"],
            facts="Тестовый факт",
            priority=5,
        )
        kb = KnowledgeBase(
            company_name="Test",
            company_description="Test",
            sections=[section],
        )
        retriever = CascadeRetriever(knowledge_base=kb, use_embeddings=False)

        # Skip intents should return empty
        for intent in ["greeting", "farewell", "small_talk"]:
            result = retriever.retrieve("привет", intent=intent)
            assert result == "", f"retrieve() should return '' for skip intent '{intent}', got: {result}"

    def test_retrieve_with_urls_returns_empty_for_skip_intents(self):
        """retrieve_with_urls() returns ('', []) for skip intents."""
        from src.knowledge.retriever import CascadeRetriever
        from src.knowledge.base import KnowledgeBase, KnowledgeSection

        section = KnowledgeSection(
            category="faq",
            topic="test",
            keywords=["привет"],
            facts="Тестовый факт",
            priority=5,
        )
        kb = KnowledgeBase(
            company_name="Test",
            company_description="Test",
            sections=[section],
        )
        retriever = CascadeRetriever(knowledge_base=kb, use_embeddings=False)

        facts, urls = retriever.retrieve_with_urls("привет", intent="greeting")
        assert facts == "", f"Expected empty facts for greeting, got: {facts}"
        assert urls == [], f"Expected empty urls for greeting, got: {urls}"


# =========================================================================
# 5. Generator Integration Tests
# =========================================================================

class TestGeneratorIntegration:
    """Generator correctly uses product_overview vs retrieved_facts."""

    def _make_generator(self):
        """Create generator with mocked dependencies."""
        from src.generator import ResponseGenerator
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        gen = ResponseGenerator(llm)
        return gen

    def test_get_product_overview_method_exists(self):
        """get_product_overview() method exists on ResponseGenerator."""
        gen = self._make_generator()
        assert hasattr(gen, "get_product_overview"), "ResponseGenerator should have get_product_overview method"

    def test_get_product_overview_returns_empty_for_price_intents(self):
        """get_product_overview() returns empty for price intents."""
        gen = self._make_generator()
        result = gen.get_product_overview(intent="price_question")
        assert result == "", "get_product_overview() should return '' for price_question"
        result = gen.get_product_overview(intent="pricing_details")
        assert result == "", "get_product_overview() should return '' for pricing_details"

    def test_get_product_overview_returns_overview_for_non_price(self):
        """get_product_overview() returns product overview for non-price intents."""
        gen = self._make_generator()
        result = gen.get_product_overview(intent="greeting")
        assert isinstance(result, str)
        # May be empty if KB has no overview sections, but should not raise
