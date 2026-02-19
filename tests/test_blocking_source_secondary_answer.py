"""
Тесты для фундаментального решения блокирующих источников (combinable=False).

Три сценария:
  1. request_human + secondary price_question → template escalate_to_human (Шаг 2)
  2. objection_limit_reached + secondary price_question → template blocking_with_pricing (Шаг 3)
  3. EscalationSource не блокирует (priority=HIGH, combinable=True) когда contact уже собран

Примечание: guard_offer_options и ask_clarification НЕ тестируются через generator,
т.к. bot.py обходит generator для этих action'ов.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# =============================================================================
# СЦЕНАРИЙ 1: escalate_to_human шаблон присутствует в prompts.yaml
# =============================================================================

class TestEscalateToHumanTemplate:
    """
    Шаг 2: escalate_to_human шаблон должен быть зарегистрирован в FlowConfig.
    До фикса: template отсутствовал → generator тихо откатывался к continue_current_goal.
    """

    def test_escalate_to_human_template_loaded(self):
        """escalate_to_human присутствует в prompts.yaml и корректно парсится."""
        import yaml
        import os
        prompts_path = os.path.join(
            os.path.dirname(__file__),
            "../src/yaml_config/templates/autonomous/prompts.yaml"
        )
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        templates = data.get("templates", {})
        assert "escalate_to_human" in templates, (
            "escalate_to_human отсутствует в prompts.yaml — generator откатится к continue_current_goal"
        )
        tmpl = templates["escalate_to_human"]
        assert "template" in tmpl, "escalate_to_human не содержит поле 'template'"
        # Шаблон должен давать инструкцию про ценовой вопрос
        assert "БАЗЕ ЗНАНИЙ" in tmpl["template"], (
            "escalate_to_human не содержит инструкцию использовать базу знаний"
        )
        assert "менеджер" in tmpl["template"].lower() or "менеджер" in tmpl["template"], (
            "escalate_to_human не содержит обещание связать с менеджером"
        )

    def test_blocking_with_pricing_template_loaded(self):
        """blocking_with_pricing присутствует в prompts.yaml и содержит нужные слоты."""
        import yaml
        import os
        prompts_path = os.path.join(
            os.path.dirname(__file__),
            "../src/yaml_config/templates/autonomous/prompts.yaml"
        )
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        templates = data.get("templates", {})
        assert "blocking_with_pricing" in templates, (
            "blocking_with_pricing отсутствует в prompts.yaml"
        )
        tmpl = templates["blocking_with_pricing"]
        template_str = tmpl.get("template", "")
        # Слоты присутствуют в variables dict (SafeDict не вызовет KeyError)
        for slot in ["{system}", "{retrieved_facts}", "{history}", "{user_message}"]:
            assert slot in template_str, (
                f"blocking_with_pricing не содержит слот {slot}"
            )
        assert "БАЗЕ ЗНАНИЙ" in template_str, (
            "blocking_with_pricing не содержит инструкцию использовать базу знаний"
        )

    def test_escalate_to_human_no_hallucinated_prices(self):
        """escalate_to_human содержит явный запрет выдумывать цены."""
        import yaml
        import os
        prompts_path = os.path.join(
            os.path.dirname(__file__),
            "../src/yaml_config/templates/autonomous/prompts.yaml"
        )
        with open(prompts_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        tmpl_str = data["templates"]["escalate_to_human"]["template"]
        # Антигаллюцинационная инструкция
        assert "НЕ выдумывай" in tmpl_str or "не придумывай" in tmpl_str.lower(), (
            "escalate_to_human должен запрещать выдумывать данные"
        )


# =============================================================================
# СЦЕНАРИЙ 2: Generator inject blocking_with_pricing для objection_limit_reached
# =============================================================================

class TestGeneratorSecondaryAnswerInjection:
    """
    Шаг 3: _should_inject_secondary_answer() должен возвращать True для
    objection_limit_reached + secondary price_question, и False для других комбинаций.
    """

    def _make_generator(self):
        """Создаёт минимальный экземпляр Generator без реального LLM."""
        from src.generator import ResponseGenerator
        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._flow = None
        gen._enhanced_pipeline = None
        return gen

    def _make_context_with_secondary(self, secondary_intents: list) -> dict:
        """Формирует context dict с заполненным context_envelope."""
        envelope = MagicMock()
        envelope.secondary_intents = secondary_intents
        return {"context_envelope": envelope}

    # --- _should_inject_secondary_answer ---

    def test_objection_limit_price_secondary_triggers_inject(self):
        """objection_limit_reached + secondary price_question → inject=True."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["price_question"])
        assert gen._should_inject_secondary_answer("objection_limit_reached", ctx) is True

    def test_go_back_limit_price_secondary_triggers_inject(self):
        """go_back_limit_reached + secondary price_question → inject=True."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["price_question"])
        assert gen._should_inject_secondary_answer("go_back_limit_reached", ctx) is True

    def test_escalate_to_human_not_injected(self):
        """escalate_to_human исключён из BLOCKING_ACTIONS_FOR_SECONDARY_INJECT.
        Покрывается шаблоном напрямую (Шаг 2)."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["price_question"])
        assert gen._should_inject_secondary_answer("escalate_to_human", ctx) is False

    def test_autonomous_respond_not_injected(self):
        """Обычные autonomous action'ы не должны инжектироваться."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["price_question"])
        assert gen._should_inject_secondary_answer("autonomous_respond", ctx) is False

    def test_no_price_secondary_no_inject(self):
        """objection_limit_reached без price в secondary → inject=False."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["gratitude"])
        assert gen._should_inject_secondary_answer("objection_limit_reached", ctx) is False

    def test_empty_secondary_no_inject(self):
        """Пустой secondary_intents → inject=False."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary([])
        assert gen._should_inject_secondary_answer("objection_limit_reached", ctx) is False

    def test_no_context_envelope_no_inject(self):
        """Отсутствие context_envelope → inject=False (не крашится)."""
        gen = self._make_generator()
        ctx = {}
        assert gen._should_inject_secondary_answer("objection_limit_reached", ctx) is False

    def test_multiple_secondary_including_price(self):
        """Несколько secondary intents, один из которых price_question → inject=True."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["gratitude", "price_question"])
        assert gen._should_inject_secondary_answer("objection_limit_reached", ctx) is True

    # --- _get_secondary_intents ---

    def test_get_secondary_intents_returns_list(self):
        """_get_secondary_intents возвращает список из context_envelope."""
        gen = self._make_generator()
        ctx = self._make_context_with_secondary(["price_question", "feature_question"])
        result = gen._get_secondary_intents(ctx)
        assert result == ["price_question", "feature_question"]

    def test_get_secondary_intents_missing_envelope_returns_empty(self):
        """Нет context_envelope → пустой список, без исключения."""
        gen = self._make_generator()
        result = gen._get_secondary_intents({})
        assert result == []

    def test_get_secondary_intents_none_secondary_returns_empty(self):
        """secondary_intents=None → пустой список."""
        gen = self._make_generator()
        envelope = MagicMock()
        envelope.secondary_intents = None
        ctx = {"context_envelope": envelope}
        result = gen._get_secondary_intents(ctx)
        assert result == []


# =============================================================================
# СЦЕНАРИЙ 3: EscalationSource — снижение приоритета когда contact собран
# =============================================================================

class TestEscalationSourcePriorityReduction:
    """
    Шаг 4: EscalationSource должен снижать priority с CRITICAL до HIGH и
    выставлять combinable=True, когда contact_info или kaspi_phone уже собраны.
    """

    def _make_blackboard(self, intent: str, collected_data: dict) -> MagicMock:
        """Создаёт мок blackboard с заданными данными."""
        ctx = MagicMock()
        ctx.current_intent = intent
        ctx.collected_data = collected_data
        ctx.turn_number = 5
        ctx.intent_tracker = MagicMock()
        ctx.intent_tracker.total_count.return_value = 0
        ctx.intent_tracker.category_total.return_value = 0

        # Минимальный flow_config чтобы _get_escalation_state не упал
        ctx.flow_config = {
            "entry_points": {"escalation": "soft_close"},
            "states": {"soft_close": {}},
        }

        bb = MagicMock()
        bb.current_intent = intent
        bb.get_context.return_value = ctx
        return bb

    def test_escalation_critical_when_no_contact(self):
        """Без contact → CRITICAL + combinable=False (поведение до фикса = без изменений)."""
        from src.blackboard.sources.escalation import EscalationSource
        from src.blackboard.enums import Priority

        source = EscalationSource()
        bb = self._make_blackboard("request_human", collected_data={})
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["priority"] == Priority.CRITICAL
        assert call_kwargs["combinable"] is False

    def test_escalation_downgraded_when_contact_info_present(self):
        """contact_info собран → HIGH + combinable=True."""
        from src.blackboard.sources.escalation import EscalationSource
        from src.blackboard.enums import Priority

        source = EscalationSource()
        bb = self._make_blackboard(
            "request_human",
            collected_data={"contact_info": "+77001234567"}
        )
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["priority"] == Priority.HIGH, (
            "Когда contact_info собран, escalation должен снизиться до HIGH"
        )
        assert call_kwargs["combinable"] is True, (
            "Когда contact_info собран, combinable должен быть True для MERGED решений"
        )

    def test_escalation_downgraded_when_kaspi_phone_present(self):
        """kaspi_phone собран (ready_buyer) → HIGH + combinable=True."""
        from src.blackboard.sources.escalation import EscalationSource
        from src.blackboard.enums import Priority

        source = EscalationSource()
        bb = self._make_blackboard(
            "request_human",
            collected_data={"kaspi_phone": "+77771234567"}
        )
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["combinable"] is True

    def test_escalation_sensitive_topic_critical_no_contact(self):
        """sensitive_topic без contact → остаётся CRITICAL+combinable=False."""
        from src.blackboard.sources.escalation import EscalationSource
        from src.blackboard.enums import Priority

        source = EscalationSource()
        # sensitive_topic должен быть в SENSITIVE_INTENTS; используем любой из fallback
        sensitive_intent = next(iter(EscalationSource._FALLBACK_SENSITIVE))
        # Принудительно загружаем fallback если YAML не содержит sensitive
        if not EscalationSource.SENSITIVE_INTENTS:
            EscalationSource.SENSITIVE_INTENTS = EscalationSource._FALLBACK_SENSITIVE

        bb = self._make_blackboard(sensitive_intent, collected_data={})
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["priority"] == Priority.CRITICAL
        assert call_kwargs["combinable"] is False

    def test_escalation_sensitive_topic_high_when_contact_present(self):
        """sensitive_topic + contact собран → HIGH + combinable=True."""
        from src.blackboard.sources.escalation import EscalationSource
        from src.blackboard.enums import Priority

        source = EscalationSource()
        sensitive_intent = next(iter(EscalationSource._FALLBACK_SENSITIVE))
        if not EscalationSource.SENSITIVE_INTENTS:
            EscalationSource.SENSITIVE_INTENTS = EscalationSource._FALLBACK_SENSITIVE

        bb = self._make_blackboard(
            sensitive_intent,
            collected_data={"contact_info": "+77001234567"}
        )
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["combinable"] is True

    def test_metadata_contact_collected_flag(self):
        """metadata содержит contact_already_collected для диагностики."""
        from src.blackboard.sources.escalation import EscalationSource

        source = EscalationSource()
        bb = self._make_blackboard(
            "request_human",
            collected_data={"contact_info": "+77001234567"}
        )
        source.contribute(bb)

        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["metadata"]["contact_already_collected"] is True


# =============================================================================
# ИНТЕГРАЦИЯ: constants module-level в generator.py
# =============================================================================

class TestGeneratorConstants:
    """Проверяет что константы существуют и содержат правильные значения."""

    def test_blocking_actions_constant_exists(self):
        from src.generator import BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        assert "objection_limit_reached" in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        assert "go_back_limit_reached" in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        # НЕ должны попасть в inject-список
        assert "escalate_to_human" not in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        assert "ask_clarification" not in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        assert "guard_offer_options" not in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT

    def test_secondary_answer_eligible_constant_exists(self):
        from src.generator import SECONDARY_ANSWER_ELIGIBLE
        assert "price_question" in SECONDARY_ANSWER_ELIGIBLE
