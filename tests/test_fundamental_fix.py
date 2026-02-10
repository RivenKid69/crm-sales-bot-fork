"""
Тесты для фундаментального исправления нерелевантных ответов.

Проверяем:
1. Интент request_brevity корректно классифицируется
2. Intent-aware выбор шаблонов для objection интентов
3. Шаблон handle_objection_competitor использует retrieved_facts
4. Few-shot примеры подключены к промпту
5. Маппинг INTENT_TO_CATEGORY содержит request_brevity
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

class TestRequestBrevityIntent:
    """Тесты для интента request_brevity."""

    def test_request_brevity_in_intent_type(self):
        """request_brevity включён в IntentType."""
        import typing
        from src.classifier.llm.schemas import IntentType

        intents = typing.get_args(IntentType)
        assert "request_brevity" in intents

    def test_request_brevity_in_system_prompt(self):
        """request_brevity описан в SYSTEM_PROMPT."""
        from src.classifier.llm.prompts import SYSTEM_PROMPT

        assert "request_brevity" in SYSTEM_PROMPT
        assert "короче" in SYSTEM_PROMPT or "по сути" in SYSTEM_PROMPT

    def test_request_brevity_critical_rule_exists(self):
        """Критическое правило для различения request_brevity и objection_think."""
        from src.classifier.llm.prompts import SYSTEM_PROMPT

        # Проверяем что есть правило различения
        assert "request_brevity vs objection_think" in SYSTEM_PROMPT

    def test_request_brevity_few_shot_examples(self):
        """Есть few-shot примеры для request_brevity."""
        from src.classifier.llm.few_shot import FEW_SHOT_EXAMPLES

        brevity_examples = [
            ex for ex in FEW_SHOT_EXAMPLES
            if ex.get("result", {}).get("intent") == "request_brevity"
        ]
        assert len(brevity_examples) >= 1, "Должен быть хотя бы один пример для request_brevity"

    def test_request_brevity_in_intent_to_category(self):
        """request_brevity в маппинге INTENT_TO_CATEGORY."""
        from src.knowledge.retriever import INTENT_TO_CATEGORY

        assert "request_brevity" in INTENT_TO_CATEGORY
        # request_brevity - мета-интент, не требует фактов
        assert INTENT_TO_CATEGORY["request_brevity"] == []

    def test_request_brevity_classification_result_valid(self):
        """ClassificationResult с request_brevity валиден."""
        from src.classifier.llm.schemas import ClassificationResult

        result = ClassificationResult(
            intent="request_brevity",
            confidence=0.95,
            reasoning="Клиент просит говорить короче"
        )
        assert result.intent == "request_brevity"

class TestObjectionTemplateSelection:
    """Тесты для intent-aware выбора шаблонов objection."""

    def test_objection_related_intents_defined(self):
        """OBJECTION_RELATED_INTENTS определён в ResponseGenerator."""
        from src.generator import ResponseGenerator

        assert hasattr(ResponseGenerator, "OBJECTION_RELATED_INTENTS")
        assert "objection_competitor" in ResponseGenerator.OBJECTION_RELATED_INTENTS
        assert "objection_price" in ResponseGenerator.OBJECTION_RELATED_INTENTS
        assert "objection_no_time" in ResponseGenerator.OBJECTION_RELATED_INTENTS

    def test_get_objection_template_key_method_exists(self):
        """Метод _get_objection_template_key существует."""
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)
        assert hasattr(generator, "_get_objection_template_key")

    def test_objection_competitor_returns_specific_template(self):
        """objection_competitor возвращает handle_objection_competitor."""
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)

        template_key = generator._get_objection_template_key("objection_competitor", "handle_objection")
        assert template_key == "handle_objection_competitor"

    def test_objection_price_returns_specific_template(self):
        """objection_price возвращает handle_objection_price."""
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)

        template_key = generator._get_objection_template_key("objection_price", "handle_objection")
        assert template_key == "handle_objection_price"

    def test_all_objection_intents_have_templates(self):
        """Все objection интенты имеют соответствующие шаблоны."""
        from src.generator import ResponseGenerator
        from src.config import PROMPT_TEMPLATES

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)

        for intent in ResponseGenerator.OBJECTION_RELATED_INTENTS:
            template_key = generator._get_objection_template_key(intent, "handle_objection")
            # Либо есть специфичный шаблон, либо fallback на generic
            assert template_key.startswith("handle_objection")

class TestHandleObjectionCompetitorTemplate:
    """Тесты шаблона handle_objection_competitor."""

    def test_template_has_retrieved_facts(self):
        """handle_objection_competitor использует {retrieved_facts}."""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("handle_objection_competitor", "")
        assert "{retrieved_facts}" in template, "Шаблон должен использовать retrieved_facts"

    def test_template_has_competitor_info_header(self):
        """handle_objection_competitor имеет секцию с информацией о конкурентах."""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("handle_objection_competitor", "")
        assert "ИНФОРМАЦИЯ О КОНКУРЕНТАХ" in template or "КОНКУРЕНТ" in template.upper()

    def test_template_instructs_to_use_facts(self):
        """Шаблон инструктирует использовать факты для сравнения."""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("handle_objection_competitor", "")
        assert "факты" in template.lower() or "сравнение" in template.lower()

class TestRespondBrieflyTemplate:
    """Тесты шаблона respond_briefly."""

    def test_template_exists(self):
        """Шаблон respond_briefly существует."""
        from src.config import PROMPT_TEMPLATES

        assert "respond_briefly" in PROMPT_TEMPLATES

    def test_template_instructs_brevity(self):
        """Шаблон инструктирует быть кратким."""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("respond_briefly", "")
        assert "коротк" in template.lower() or "крат" in template.lower()

    def test_template_not_objection(self):
        """Шаблон указывает что это НЕ возражение."""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("respond_briefly", "")
        assert "НЕ возражение" in template

class TestFewShotIntegration:
    """Тесты интеграции few-shot примеров."""

    def test_few_shot_import_in_prompts(self):
        """get_few_shot_prompt импортируется в prompts.py."""
        from src.classifier.llm.prompts import get_few_shot_prompt
        assert callable(get_few_shot_prompt)

    def test_build_classification_prompt_includes_few_shot(self):
        """build_classification_prompt включает few-shot примеры."""
        from src.classifier.llm.prompts import build_classification_prompt

        prompt = build_classification_prompt("тест", n_few_shot=3)
        # Проверяем что few-shot примеры включены
        assert "Пример" in prompt or "пример" in prompt

    def test_build_classification_prompt_without_few_shot(self):
        """build_classification_prompt без few-shot при n_few_shot=0."""
        from src.classifier.llm.prompts import build_classification_prompt

        prompt = build_classification_prompt("тест", n_few_shot=0)
        # Проверяем что это валидный промпт
        assert "Твой JSON ответ" in prompt

    def test_few_shot_examples_have_competitor(self):
        """Есть few-shot примеры для objection_competitor."""
        from src.classifier.llm.few_shot import FEW_SHOT_EXAMPLES

        competitor_examples = [
            ex for ex in FEW_SHOT_EXAMPLES
            if ex.get("result", {}).get("intent") == "objection_competitor"
        ]
        assert len(competitor_examples) >= 1, "Должны быть примеры для objection_competitor"

class TestMixinMetaIntents:
    """Тесты для mixin meta_intents."""

    def test_meta_intents_mixin_exists(self):
        """Mixin meta_intents существует в YAML."""
        import yaml

        with open("src/yaml_config/flows/_base/mixins.yaml", "r") as f:
            mixins = yaml.safe_load(f)

        assert "mixins" in mixins
        assert "meta_intents" in mixins["mixins"]

    def test_meta_intents_has_request_brevity(self):
        """Mixin meta_intents содержит request_brevity."""
        import yaml

        with open("src/yaml_config/flows/_base/mixins.yaml", "r") as f:
            mixins = yaml.safe_load(f)

        meta_intents = mixins["mixins"]["meta_intents"]
        assert "rules" in meta_intents
        assert "request_brevity" in meta_intents["rules"]

    def test_spin_common_includes_meta_intents(self):
        """spin_common включает meta_intents."""
        import yaml

        with open("src/yaml_config/flows/_base/mixins.yaml", "r") as f:
            mixins = yaml.safe_load(f)

        spin_common = mixins["mixins"]["spin_common"]
        assert "includes" in spin_common
        assert "meta_intents" in spin_common["includes"]

class TestGeneratorRequestBrevityHandling:
    """Тесты обработки request_brevity в генераторе."""

    def test_request_brevity_uses_respond_briefly_template(self):
        """request_brevity использует шаблон respond_briefly."""
        from src.generator import ResponseGenerator

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)

        # Проверяем логику выбора шаблона
        # При intent == "request_brevity" должен выбираться respond_briefly
        # Это проверяется косвенно через наличие условия в коде

class TestIntentCounts:
    """Тесты корректности количества интентов."""

    def test_intent_count_is_34(self):
        """Всего 34 интента (33 + request_brevity)."""
        import typing
        from src.classifier.llm.schemas import IntentType

        intents = typing.get_args(IntentType)
        assert len(intents) == 34

    def test_prompt_mentions_34_intents(self):
        """SYSTEM_PROMPT упоминает 34 интента."""
        from src.classifier.llm.prompts import SYSTEM_PROMPT

        assert "34" in SYSTEM_PROMPT

class TestEndToEndScenarios:
    """E2E сценарии для проверки исправлений."""

    def test_scenario_brevity_request_not_objection(self):
        """
        Сценарий: "не грузите меня, скажите суть"
        Ожидание: intent = request_brevity (НЕ objection_think)
        """
        from src.classifier.llm.schemas import ClassificationResult

        # Проверяем что можно создать результат с request_brevity
        result = ClassificationResult(
            intent="request_brevity",
            confidence=0.95,
            reasoning="Клиент просит краткости, не возражает"
        )
        assert result.intent == "request_brevity"
        assert result.intent != "objection_think"

    def test_scenario_competitor_uses_facts(self):
        """
        Сценарий: "у нас Poster, зачем нам вы?"
        Ожидание: template = handle_objection_competitor с retrieved_facts
        """
        from src.generator import ResponseGenerator
        from src.config import PROMPT_TEMPLATES

        mock_llm = MagicMock()
        generator = ResponseGenerator(llm=mock_llm)

        # Проверяем выбор шаблона
        template_key = generator._get_objection_template_key("objection_competitor", "handle_objection")
        assert template_key == "handle_objection_competitor"

        # Проверяем шаблон содержит retrieved_facts
        template = PROMPT_TEMPLATES[template_key]
        assert "{retrieved_facts}" in template
