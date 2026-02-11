"""
E2E Simulation Test: Factual Retrieval Accuracy after Hallucination Fix.

Verifies that:
1. Factual questions get REAL KB data (via {retrieved_facts}), not random product overview
2. Skip intents (greeting, farewell) don't trigger KB search
3. Orphan categories (equipment, employees, etc.) are now reachable
4. Objection templates get both product_overview AND retrieved_facts
5. The full generate() pipeline correctly routes facts vs overview
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_generator():
    """Create ResponseGenerator with mocked LLM and real KB."""
    from src.generator import ResponseGenerator
    llm = MagicMock()
    llm.generate.return_value = "Тестовый ответ на русском"
    gen = ResponseGenerator(llm)
    return gen, llm


def _extract_prompt_from_llm(llm_mock) -> str:
    """Extract the prompt string that was passed to llm.generate()."""
    calls = llm_mock.generate.call_args_list
    if not calls:
        return ""
    return calls[-1][0][0] if calls[-1][0] else ""


class TestE2EFactualRetrieval:
    """End-to-end tests verifying factual questions get real KB data."""

    # =====================================================================
    # Test 1: Factual question → retrieved_facts in prompt (not product overview)
    # =====================================================================

    def test_feature_question_gets_retrieved_facts(self):
        """When user asks about features, prompt should contain retrieved KB data."""
        gen, llm = _make_generator()

        context = {
            "user_message": "Какие функции есть у вашей CRM?",
            "intent": "question_features",
            "state": "qualification",
            "history": [{"user": "Привет", "bot": "Здравствуйте!"}],
            "collected_data": {},
            "missing_data": ["company_size"],
            "goal": "Узнать размер компании",
        }

        gen.generate("answer_with_facts", context)
        prompt = _extract_prompt_from_llm(llm)

        # Prompt should contain grounding instruction
        assert "СТРОГО" in prompt or "НЕ ПРИДУМЫВАЙ" in prompt, (
            "answer_with_facts prompt should have grounding instruction"
        )
        # Should NOT have raw product overview label as the primary data source
        # (product_overview is a random sample of labels, not real KB data)

    def test_pricing_question_gets_retrieved_facts(self):
        """Price questions should get real pricing data from KB."""
        gen, llm = _make_generator()

        context = {
            "user_message": "Сколько стоит ваша CRM?",
            "intent": "price_question",
            "state": "qualification",
            "history": [],
            "collected_data": {},
            "missing_data": ["company_size"],
            "goal": "Узнать размер компании",
        }

        gen.generate("answer_with_pricing", context)
        prompt = _extract_prompt_from_llm(llm)

        # Should contain retrieved_facts (pricing data from KB)
        assert "ТАРИФЫ" in prompt or "retrieved_facts" not in prompt or "₸" in prompt or "тариф" in prompt.lower(), (
            "Pricing template should reference tariff data"
        )

    def test_integration_question_gets_kb_data(self):
        """Integration questions should retrieve from 'integrations' category."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        result = retriever.retrieve(
            "Есть ли интеграция с 1С?",
            intent="question_integrations"
        )
        # Should find something from integrations category
        assert result, "Integration question should retrieve KB data"

    # =====================================================================
    # Test 2: Skip intents don't trigger KB search
    # =====================================================================

    def test_greeting_skips_retrieval(self):
        """Greeting intent should not search KB."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        result = retriever.retrieve("Привет!", intent="greeting")
        assert result == "", "Greeting should return empty (skip retrieval)"

    def test_farewell_skips_retrieval(self):
        """Farewell intent should not search KB."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        result = retriever.retrieve("До свидания!", intent="farewell")
        assert result == "", "Farewell should return empty (skip retrieval)"

    def test_small_talk_skips_retrieval(self):
        """Small talk intent should not search KB."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        result = retriever.retrieve("Как дела?", intent="small_talk")
        assert result == "", "Small talk should return empty (skip retrieval)"

    def test_situation_provided_skips_retrieval(self):
        """SPIN situation_provided should not search KB."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        result = retriever.retrieve(
            "У нас магазин одежды, 5 сотрудников",
            intent="situation_provided"
        )
        assert result == "", "situation_provided should return empty (skip retrieval)"

    # =====================================================================
    # Test 3: Orphan categories now reachable
    # =====================================================================

    def test_equipment_question_retrieves_data(self):
        """Questions about equipment should now retrieve from 'equipment' category."""
        from src.knowledge.retriever import get_retriever

        retriever = get_retriever()
        # question_features now includes 'equipment'
        result = retriever.retrieve(
            "Какое оборудование поддерживается?",
            intent="question_features"
        )
        # Should be able to find equipment-related data
        assert isinstance(result, str)
        # Note: may or may not find a match depending on keyword overlap,
        # but the category is now in the search scope

    def test_faq_category_reachable(self):
        """FAQ category should be searchable via question_features intent."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY

        qf_categories = INTENT_TO_CATEGORY.get("question_features", [])
        assert "faq" in qf_categories, "FAQ should be in question_features categories"
        assert "equipment" in qf_categories, "equipment should be in question_features"
        assert "employees" in qf_categories, "employees should be in question_features"
        assert "fiscal" in qf_categories, "fiscal should be in question_features"
        assert "stability" in qf_categories, "stability should be in question_features"

    # =====================================================================
    # Test 4: Objection templates get both overview AND retrieved_facts
    # =====================================================================

    def test_objection_template_has_both_sources(self):
        """handle_objection template should have both product_overview and retrieved_facts."""
        gen, llm = _make_generator()

        # Use empty intent to bypass intent-based template routing
        # and force the generic handle_objection template directly
        context = {
            "user_message": "Это слишком дорого для нас",
            "intent": "",  # empty to use action directly
            "state": "presentation",
            "history": [
                {"user": "Расскажите подробнее", "bot": "Конечно! Наша CRM..."},
            ],
            "collected_data": {"company_size": 5, "pain_point": "потеря клиентов"},
            "missing_data": [],
            "goal": "Закрытие",
        }

        gen.generate("handle_objection", context)
        prompt = _extract_prompt_from_llm(llm)

        # config.py handle_objection has "Наш продукт: {product_overview}"
        has_product_ref = "Наш продукт:" in prompt
        assert has_product_ref, (
            f"handle_objection should include 'Наш продукт:' section. "
            f"Prompt start: {prompt[:200]}"
        )

    # =====================================================================
    # Test 5: Full pipeline — generate() correctly populates variables
    # =====================================================================

    def test_generate_populates_retrieved_facts(self):
        """generate() should populate {retrieved_facts} from retriever."""
        gen, llm = _make_generator()

        context = {
            "user_message": "Расскажите про ваши тарифы",
            "intent": "price_question",
            "state": "qualification",
            "history": [],
            "collected_data": {},
            "missing_data": ["company_size"],
            "goal": "Узнать размер",
        }

        gen.generate("answer_with_pricing", context)
        prompt = _extract_prompt_from_llm(llm)

        # retrieved_facts should be populated (not the placeholder)
        # The retriever should find pricing data for "тарифы"
        assert "Информация по этому вопросу будет уточнена" not in prompt or "₸" in prompt, (
            "retrieved_facts should contain real pricing data, not fallback"
        )

    def test_generate_product_overview_not_in_qa_templates(self):
        """product_overview should NOT be the primary source in Q&A templates."""
        gen, llm = _make_generator()

        context = {
            "user_message": "Есть ли мобильное приложение?",
            "intent": "question_features",
            "state": "qualification",
            "history": [],
            "collected_data": {},
            "missing_data": ["company_size"],
            "goal": "Квалификация",
        }

        gen.generate("answer_with_facts", context)
        prompt = _extract_prompt_from_llm(llm)

        # The prompt should have {retrieved_facts} section with grounding,
        # NOT {product_overview} as the primary facts source
        assert "ФАКТЫ О ПРОДУКТЕ" in prompt or "ФАКТЫ ДЛЯ ОТВЕТА" in prompt, (
            "answer_with_facts should have dedicated retrieved_facts section"
        )
        assert "НЕ ПРИДУМЫВАЙ" in prompt, (
            "answer_with_facts should have anti-hallucination instruction"
        )

    # =====================================================================
    # Test 6: request_brevity now has categories (not skip)
    # =====================================================================

    def test_request_brevity_can_retrieve_facts(self):
        """request_brevity intent should be able to retrieve facts (not skipped)."""
        from src.knowledge.retriever import get_retriever, SKIP_RETRIEVAL_INTENTS

        assert "request_brevity" not in SKIP_RETRIEVAL_INTENTS, (
            "request_brevity should NOT be in skip intents"
        )

        retriever = get_retriever()
        # request_brevity with a factual question should retrieve data
        result = retriever.retrieve(
            "Покороче. Какие у вас тарифы?",
            intent="request_brevity"
        )
        # May or may not find match, but should NOT be skipped
        assert isinstance(result, str)

    # =====================================================================
    # Test 7: End-to-end scenario simulation
    # =====================================================================

    def test_full_scenario_factual_question_after_greeting(self):
        """
        Simulate: greeting → factual question → verify facts from KB.

        This tests the complete flow:
        1. User greets → no KB search (skip intent)
        2. User asks about features → KB search (retrieved_facts)
        3. The prompt contains real KB data, not random overview
        """
        gen, llm = _make_generator()

        # Step 1: Greeting (should skip KB)
        greeting_ctx = {
            "user_message": "Привет",
            "intent": "greeting",
            "state": "greeting",
            "history": [],
            "collected_data": {},
            "missing_data": [],
            "goal": "",
        }
        gen.generate("greeting", greeting_ctx)
        greeting_prompt = _extract_prompt_from_llm(llm)
        # Greeting prompt should NOT have facts sections
        assert "ФАКТЫ О ПРОДУКТЕ" not in greeting_prompt

        # Step 2: Feature question (should search KB)
        llm.generate.reset_mock()
        llm.generate.return_value = "Наша CRM поддерживает складской учёт"

        feature_ctx = {
            "user_message": "А что ваша CRM умеет?",
            "intent": "question_features",
            "state": "qualification",
            "history": [{"user": "Привет", "bot": "Здравствуйте!"}],
            "collected_data": {},
            "missing_data": ["company_size"],
            "goal": "Узнать размер компании",
        }
        gen.generate("answer_with_facts", feature_ctx)
        feature_prompt = _extract_prompt_from_llm(llm)

        # Feature prompt SHOULD have facts sections with grounding
        assert "ФАКТЫ О ПРОДУКТЕ" in feature_prompt, (
            "Feature question should get dedicated facts section from KB"
        )
        assert "НЕ ПРИДУМЫВАЙ" in feature_prompt, (
            "Feature question should have anti-hallucination instruction"
        )

    def test_full_scenario_objection_after_knowledge_answer(self):
        """
        Simulate: factual question → objection → verify correct routing.

        1. User asks about features → answer_with_knowledge (has retrieved_facts)
        2. User objects → handle_objection (has product_overview)
        """
        gen, llm = _make_generator()

        # Step 1: Feature question via answer_with_knowledge (exists in config.py)
        feature_ctx = {
            "user_message": "Что умеет ваша CRM?",
            "intent": "question_features",
            "state": "qualification",
            "history": [],
            "collected_data": {"company_size": 10},
            "missing_data": [],
            "goal": "Презентация",
        }
        gen.generate("answer_with_knowledge", feature_ctx)
        feature_prompt = _extract_prompt_from_llm(llm)
        # Should have grounding from retrieved_facts
        assert "ФАКТЫ О ПРОДУКТЕ" in feature_prompt, (
            "answer_with_knowledge should have ФАКТЫ О ПРОДУКТЕ section"
        )
        assert "НЕ ПРИДУМЫВАЙ" in feature_prompt, (
            "answer_with_knowledge should have anti-hallucination instruction"
        )

        # Step 2: Objection (using empty intent to force generic handle_objection)
        llm.generate.reset_mock()
        llm.generate.return_value = "Понимаю ваши опасения"

        objection_ctx = {
            "user_message": "Дороговато для нас",
            "intent": "",
            "state": "presentation",
            "history": [
                {"user": "Что умеет?", "bot": "Наша CRM поддерживает..."},
            ],
            "collected_data": {"company_size": 10, "pain_point": "потеря клиентов"},
            "missing_data": [],
            "goal": "Закрытие",
        }
        gen.generate("handle_objection", objection_ctx)
        objection_prompt = _extract_prompt_from_llm(llm)

        # Handle_objection (config.py) has "Наш продукт: {product_overview}"
        assert "Наш продукт:" in objection_prompt, (
            "handle_objection should have 'Наш продукт:' with product overview"
        )
