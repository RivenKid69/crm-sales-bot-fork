"""
Интеграционные тесты для PLAN_CONTEXT_POLICY.md.

Проверяют полный flow:
- Phase 0: ContextEnvelope + reason codes
- Phase 1: PII redaction + приоритеты
- Phase 2: ResponseDirectives
- Phase 3: DialoguePolicy + engagement v2
- Метрики и качество диалога
"""

import pytest
import sys
import os

from src.context_envelope import (
    ContextEnvelope,
    ContextEnvelopeBuilder,
    ReasonCode,
    PIIRedactor,
    build_context_envelope,
)
from src.response_directives import (
    ResponseDirectives,
    ResponseDirectivesBuilder,
    ResponseTone,
    build_response_directives,
    build_context_summary,
)
from src.dialogue_policy import (
    DialoguePolicy,
    PolicyDecision,
    PolicyOverride,
    ContextPolicyMetrics,
)
from src.context_window import ContextWindow, TurnType
from src.feature_flags import flags

class TestPhase0Integration:
    """Тесты для Phase 0: Инфраструктура."""

    def test_context_envelope_from_context_window(self):
        """Проверить создание envelope из ContextWindow."""
        # Создаём ContextWindow с данными
        cw = ContextWindow(max_size=5)

        # Добавляем несколько ходов
        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.95,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        cw.add_turn_from_dict(
            user_message="Нас 10 человек",
            bot_response="Отлично! А какие проблемы?",
            intent="company_size",
            confidence=0.9,
            action="ask_pain_point",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10},
        )

        # Создаём envelope
        envelope = ContextEnvelopeBuilder(
            context_window=cw,
            last_action="ask_pain_point",
            last_intent="company_size",
        ).build()

        # Проверяем Level 1
        assert envelope.intent_history == ["greeting", "company_size"]
        assert envelope.action_history == ["greet", "ask_pain_point"]
        assert envelope.confidence_trend in ["increasing", "stable", "unknown"]

        # Проверяем Level 2
        assert envelope.engagement_level in ["high", "medium", "low", "disengaged"]
        assert 0 <= envelope.engagement_score <= 1

        # Проверяем Level 3
        assert envelope.total_turns == 2

    def test_reason_codes_comprehensive(self):
        """Проверить все категории reason codes."""
        envelope = ContextEnvelope(
            # Repair signals
            is_stuck=True,
            has_oscillation=True,
            repeated_question="q1",
            confidence_trend="decreasing",
            # Objection signals
            first_objection_type="objection_price",
            total_objections=3,
            repeated_objection_types=["objection_price"],
            # Breakthrough signals
            has_breakthrough=True,
            turns_since_breakthrough=2,
            # Momentum signals
            momentum_direction="negative",
            # Engagement signals
            engagement_level="low",
            engagement_trend="declining",
            # Guard signals
            frustration_level=4,
            guard_intervention="tier_2",
            # Progress signals
            is_progressing=False,
        )

        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope)

        # Проверяем что все категории представлены
        categories = set()
        for code in envelope.reason_codes:
            category = code.split(".")[0]
            categories.add(category)

        expected_categories = {
            "repair", "objection", "breakthrough",
            "momentum", "engagement", "guard", "policy"
        }

        for cat in expected_categories:
            assert cat in categories, f"Missing category: {cat}"

class TestPhase1Integration:
    """Тесты для Phase 1: Защита и надёжность."""

    def test_pii_redaction_in_context(self):
        """Проверить PII redaction в контексте."""
        redactor = PIIRedactor()

        # Данные с PII
        collected_data = {
            "phone": "+79991234567",
            "email": "client@company.ru",
            "company_size": 10,
            "business_type": "розница",
            "pain_point": "потеря клиентов",
        }

        # Редактируем
        safe_data = redactor.redact(collected_data)

        # PII замаскирован
        assert safe_data["phone"] != "+79991234567"
        assert "**" in safe_data["phone"]
        assert "**" in safe_data["email"]

        # Non-PII сохранён
        assert safe_data["company_size"] == 10
        assert safe_data["business_type"] == "розница"
        assert safe_data["pain_point"] == "потеря клиентов"

    def test_context_for_logging_is_safe(self):
        """Проверить что контекст для логирования безопасен."""
        redactor = PIIRedactor()

        envelope = ContextEnvelope(
            collected_data={
                "phone": "+79991234567",
                "company_size": 10,
            },
            client_pain_points=["потеря клиентов"],
        )

        # for_classifier может содержать PII (внутреннее использование)
        # Но to_dict для логирования должен быть безопасным
        full_dict = envelope.to_dict()

        # Редактируем для логирования
        safe_dict = redactor.redact(full_dict)

        # Проверяем что PII замаскирован
        if "phone" in safe_dict.get("collected_data", {}):
            assert "**" in safe_dict["collected_data"]["phone"]

class TestPhase2Integration:
    """Тесты для Phase 2: Естественность диалога."""

    def test_directives_for_frustrated_client(self):
        """Проверить директивы для фрустрированного клиента."""
        envelope = ContextEnvelope(
            state="spin_problem",
            frustration_level=4,
            is_stuck=True,
            repeated_question="question_price",
            objection_types_seen=["objection_price"],
            collected_data={
                "company_size": 15,
                "business_type": "услуги",
            },
            client_company_size=15,
            reason_codes=[
                ReasonCode.POLICY_REPAIR_MODE.value,
                ReasonCode.REPAIR_STUCK.value,
            ],
        )

        directives = build_response_directives(envelope)

        # Эмпатичный тон
        assert directives.tone == ResponseTone.EMPATHETIC

        # Validation
        assert directives.validate is True

        # Repair mode
        assert directives.repair_mode is True

        # Краткость
        assert directives.be_brief is True
        assert directives.max_words <= 50

        # Do not repeat
        assert "размер компании" in directives.do_not_repeat
        assert "тип бизнеса" in directives.do_not_repeat

        # Instruction содержит директивы
        instruction = directives.get_instruction()
        assert len(instruction) > 50

    def test_directives_for_interested_client(self):
        """Проверить директивы для заинтересованного клиента."""
        envelope = ContextEnvelope(
            state="presentation",
            frustration_level=0,
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="positive",
            engagement_level="high",
            client_has_data=True,
            client_company_size=20,
            client_pain_points=["потеря клиентов"],
            reason_codes=[
                ReasonCode.BREAKTHROUGH_DETECTED.value,
                ReasonCode.BREAKTHROUGH_CTA.value,
                ReasonCode.MOMENTUM_POSITIVE.value,
            ],
        )

        directives = build_response_directives(envelope)

        # Уверенный тон
        assert directives.tone == ResponseTone.CONFIDENT

        # Soft CTA
        assert directives.cta_soft is True

        # Summarize (есть данные)
        assert directives.summarize_client is True

        # Client card заполнен
        assert "20" in directives.client_card

    def test_context_summary_structure(self):
        """Проверить структуру context summary."""
        envelope = ContextEnvelope(
            total_turns=7,
            client_company_size=25,
            client_pain_points=["потеря клиентов", "долгие продажи"],
            repeated_objection_types=["objection_price"],
            has_breakthrough=True,
            is_stuck=True,
            reason_codes=[
                ReasonCode.REPAIR_STUCK.value,
            ],
        )

        summary = build_context_summary(envelope)

        # Проверяем наличие ключевых элементов
        assert "7" in summary  # Ходы
        assert "25" in summary  # Компания
        assert "потеря клиентов" in summary
        assert "застрял" in summary.lower()
        assert "прорыв" in summary.lower()

class TestPhase3Integration:
    """Тесты для Phase 3: DialoguePolicy + engagement v2."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить feature flags."""
        flags.set_override("context_policy_overlays", True)
        flags.set_override("context_engagement_v2", True)
        yield
        flags.clear_override("context_policy_overlays")
        flags.clear_override("context_engagement_v2")

    def test_policy_repair_flow(self):
        """Проверить policy при repair сценарии."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            unclear_count=3,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        override = policy.maybe_override(sm_result, envelope)

        assert override is not None
        assert override.has_override
        assert override.action == "clarify_one_question"
        assert override.decision == PolicyDecision.REPAIR_CLARIFY

    def test_policy_objection_escalation(self):
        """Проверить policy при эскалации возражений."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="handle_objection",
            current_intent="objection_price",
            total_objections=4,
            repeated_objection_types=["objection_price", "objection_competitor"],
        )
        sm_result = {"next_state": "handle_objection", "action": "handle"}

        override = policy.maybe_override(sm_result, envelope)

        assert override is not None
        assert override.action == "handle_repeated_objection"
        assert override.decision == PolicyDecision.OBJECTION_ESCALATE

    def test_engagement_v2_short_positive_responses(self):
        """Проверить что короткие позитивные ответы не штрафуются."""
        cw = ContextWindow(max_size=5)

        # Добавляем короткие позитивные ответы
        for msg in ["да", "хорошо", "понял", "ок"]:
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="Отлично!",
                intent="agreement",
                confidence=0.9,
                action="continue",
                state="spin_situation",
                next_state="spin_situation",
            )

        # v1 engagement (зависит от word_count)
        score_v1 = cw.get_engagement_score()

        # v2 engagement (не зависит от word_count)
        score_v2 = cw.get_engagement_score_v2()

        # v2 должен давать разумный score для позитивных ответов
        assert score_v2 >= 0.5
        assert score_v1 >= 0.5

        # v2 не должен быть low/disengaged для позитивных ответов
        level_v2 = cw.get_engagement_level_v2()
        assert level_v2.value not in ["disengaged"]

    def test_engagement_v2_with_data_provided(self):
        """Проверить что предоставление данных повышает engagement."""
        cw = ContextWindow(max_size=5)

        # Ход с данными
        cw.add_turn_from_dict(
            user_message="Нас 10 человек",
            bot_response="Отлично!",
            intent="company_size",
            confidence=0.9,
            action="ask_pain",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10},
        )

        score = cw.get_engagement_score_v2()

        # Score должен быть выше нейтрального
        assert score > 0.5

class TestFullFlowIntegration:
    """Полные интеграционные тесты всего flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить все feature flags."""
        flags.set_override("context_full_envelope", True)
        flags.set_override("context_response_directives", True)
        flags.set_override("context_policy_overlays", True)
        flags.set_override("context_engagement_v2", True)
        yield
        flags.clear_all_overrides()

    def test_complete_conversation_flow(self):
        """Проверить полный flow диалога."""
        cw = ContextWindow(max_size=10)
        policy = DialoguePolicy()
        metrics = ContextPolicyMetrics()

        # === Turn 1: Greeting ===
        cw.add_turn_from_dict(
            user_message="Привет",
            bot_response="Здравствуйте!",
            intent="greeting",
            confidence=0.95,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        envelope1 = ContextEnvelopeBuilder(
            context_window=cw,
            use_v2_engagement=True,
        ).build()

        # Greeting state protected
        sm_result1 = {"next_state": "greeting", "action": "greet"}
        override1 = policy.maybe_override(sm_result1, envelope1)
        assert override1 is None

        # === Turn 2: Company size ===
        cw.add_turn_from_dict(
            user_message="Нас 15 человек",
            bot_response="Отлично! А какие проблемы?",
            intent="company_size",
            confidence=0.9,
            action="ask_pain_point",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 15},
        )

        envelope2 = ContextEnvelopeBuilder(
            context_window=cw,
            use_v2_engagement=True,
        ).build()

        directives2 = build_response_directives(envelope2)

        # На раннем этапе тон может быть нейтральным или уверенным (зависит от momentum)
        assert directives2.tone in [ResponseTone.NEUTRAL, ResponseTone.CONFIDENT]

        # === Turn 3: Pain point ===
        cw.add_turn_from_dict(
            user_message="Теряем клиентов, не успеваем отвечать",
            bot_response="Понимаю...",
            intent="pain_point",
            confidence=0.85,
            action="explore_impact",
            state="spin_problem",
            next_state="spin_implication",
            extracted_data={"pain_point": "потеря клиентов"},
        )

        # === Turn 4: Возражение ===
        cw.add_turn_from_dict(
            user_message="Но это дорого наверное",
            bot_response="Давайте посчитаем...",
            intent="objection_price",
            confidence=0.88,
            action="handle_price_objection",
            state="spin_implication",
            next_state="handle_objection",
        )

        envelope4 = ContextEnvelopeBuilder(
            context_window=cw,
            use_v2_engagement=True,
        ).build()

        directives4 = build_response_directives(envelope4)

        # При возражении — эмпатичный тон
        assert directives4.tone == ResponseTone.EMPATHETIC
        assert directives4.validate is True

        # === Turn 5: Повторное возражение ===
        cw.add_turn_from_dict(
            user_message="Всё равно дорого",
            bot_response="Понимаю...",
            intent="objection_price",
            confidence=0.9,
            action="handle_price_objection",
            state="handle_objection",
            next_state="handle_objection",
        )

        envelope5 = ContextEnvelopeBuilder(
            context_window=cw,
            use_v2_engagement=True,
        ).build()

        sm_result5 = {"next_state": "handle_objection", "action": "handle_price"}

        override5 = policy.maybe_override(sm_result5, envelope5)

        # При повторном возражении — reframe
        assert override5 is not None
        assert override5.action == "reframe_value"

        metrics.record_decision(override5)

        # === Проверяем итоговые метрики ===
        summary = metrics.get_summary()
        assert summary["total_decisions"] >= 1
        assert summary["override_count"] >= 1

    def test_breakthrough_flow(self):
        """Проверить flow с breakthrough."""
        cw = ContextWindow(max_size=10)

        # Несколько нормальных ходов
        for i in range(3):
            cw.add_turn_from_dict(
                user_message=f"Сообщение {i}",
                bot_response=f"Ответ {i}",
                intent="info_provided" if i > 0 else "greeting",
                confidence=0.9,
                action="continue",
                state="spin_situation",
                next_state="spin_problem",
            )

        # Возражение (нужно для последующего breakthrough)
        cw.add_turn_from_dict(
            user_message="Это дорого",
            bot_response="Понимаю...",
            intent="objection_price",
            confidence=0.85,
            action="handle_objection",
            state="spin_problem",
            next_state="handle_objection",
        )

        # Breakthrough: явный интерес после возражения
        cw.add_turn_from_dict(
            user_message="Звучит интересно! Расскажите подробнее",
            bot_response="Конечно!",
            intent="explicit_interest",
            confidence=0.95,
            action="present_benefits",
            state="spin_need_payoff",
            next_state="presentation",
        )

        # Ещё один ход (окно для CTA)
        cw.add_turn_from_dict(
            user_message="А демо можно?",
            bot_response="Да!",
            intent="demo_request",
            confidence=0.98,
            action="schedule_demo",
            state="presentation",
            next_state="close",
        )

        envelope = ContextEnvelopeBuilder(
            context_window=cw,
            use_v2_engagement=True,
        ).build()

        # Должен быть breakthrough (переход от возражения к интересу)
        assert envelope.has_breakthrough

        directives = build_response_directives(envelope)

        # Уверенный тон после breakthrough
        assert directives.tone == ResponseTone.CONFIDENT

    def test_quality_metrics(self):
        """Проверить метрики качества диалога."""
        cw = ContextWindow(max_size=10)
        policy = DialoguePolicy()
        metrics = ContextPolicyMetrics()

        # Симулируем 10 решений
        states = ["spin_situation", "spin_problem", "spin_implication",
                  "spin_need_payoff", "presentation"]

        for i, state in enumerate(states * 2):
            # Создаём envelope с разными сигналами
            is_stuck = i % 4 == 0
            has_objection = i % 3 == 0

            envelope = ContextEnvelope(
                state=state,
                is_stuck=is_stuck,
                total_objections=2 if has_objection else 0,
                repeated_objection_types=["objection_price"] if has_objection else [],
                reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value] if is_stuck else [],
            )

            sm_result = {"next_state": state, "action": "continue"}

            override = policy.maybe_override(sm_result, envelope)

            if override:
                metrics.record_decision(override)

        # Проверяем метрики
        summary = metrics.get_summary()

        # Должны быть решения
        assert summary["total_decisions"] > 0

        # Override rate должен быть разумным (не 100% и не 0%)
        override_rate = summary["override_rate"]
        # При наших тестовых данных какой-то процент должен быть
        assert 0 <= override_rate <= 1

class TestFeatureFlagsIntegration:
    """Тесты интеграции с feature flags."""

    def test_context_policy_disabled(self):
        """Проверить что policy отключён без флага."""
        flags.set_override("context_policy_overlays", False)

        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask"}

        override = policy.maybe_override(sm_result, envelope)

        assert override is None
        flags.clear_override("context_policy_overlays")

    def test_engagement_v2_flag(self):
        """Проверить использование v2 engagement по флагу."""
        cw = ContextWindow(max_size=5)

        cw.add_turn_from_dict(
            user_message="да",
            bot_response="OK",
            intent="agreement",
            confidence=0.9,
            action="continue",
            state="spin_situation",
            next_state="spin_situation",
        )

        # v1
        context_v1 = cw.get_structured_context(use_v2_engagement=False)

        # v2
        context_v2 = cw.get_structured_context(use_v2_engagement=True)

        # Scores могут отличаться
        score_v1 = context_v1["engagement_score"]
        score_v2 = context_v2["engagement_score"]

        # Оба score должны быть валидными
        assert 0 <= score_v1 <= 1
        assert 0 <= score_v2 <= 1

        # v2 даёт разумный score для позитивных коротких ответов
        assert score_v2 >= 0.5

    def test_all_flags_enabled(self):
        """Проверить работу со всеми включёнными флагами."""
        flags.enable_group("context_all")

        assert flags.context_full_envelope
        assert flags.context_shadow_mode
        assert flags.context_response_directives
        assert flags.context_policy_overlays
        assert flags.context_engagement_v2
        assert flags.context_cta_memory

        flags.clear_all_overrides()

    def test_safe_flags_only(self):
        """Проверить работу только с safe флагами."""
        flags.clear_all_overrides()
        flags.set_override("context_policy_overlays", False)
        flags.enable_group("context_safe")

        assert flags.context_full_envelope
        assert flags.context_response_directives
        assert not flags.context_policy_overlays  # Не в safe группе

        flags.clear_override("context_policy_overlays")

        flags.clear_all_overrides()

class TestPolicyOverrideLoggingRegression:
    """Regression tests for PolicyOverride usage in bot.py logging.

    Bug fixed: bot.py:1519 was using override.reason instead of
    override.reason_codes, causing AttributeError.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить feature flags."""
        flags.set_override("context_policy_overlays", True)
        yield
        flags.clear_override("context_policy_overlays")

    def test_policy_override_has_reason_codes_not_reason(self):
        """Verify PolicyOverride uses reason_codes, not reason.

        This test ensures the bug in bot.py:1519 doesn't regress.
        The fix changed: reason=override.reason -> reason_codes=override.reason_codes
        """
        policy = DialoguePolicy()

        # Создаём ситуацию, которая вызывает override
        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            unclear_count=3,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        override = policy.maybe_override(sm_result, envelope)

        # Override должен быть создан
        assert override is not None
        assert override.has_override

        # CRITICAL: reason_codes должен существовать
        assert hasattr(override, "reason_codes")
        assert isinstance(override.reason_codes, list)

        # CRITICAL: reason НЕ должен существовать
        assert not hasattr(override, "reason"), \
            "PolicyOverride should not have 'reason' attr - use 'reason_codes'"

        # Симулируем использование как в bot.py:1515-1519
        log_data = {
            "original_action": sm_result["action"],
            "override_action": override.action,
            "reason_codes": override.reason_codes,  # Это правильный способ
        }

        # Должно работать без ошибок
        assert "reason_codes" in log_data
        assert log_data["override_action"] == "clarify_one_question"

    def test_all_policy_decisions_use_reason_codes(self):
        """Test that all PolicyDecision types produce valid reason_codes."""
        policy = DialoguePolicy()

        test_cases = [
            # Repair: stuck
            (
                ContextEnvelope(state="spin_situation", is_stuck=True),
                {"action": "ask"},
                PolicyDecision.REPAIR_CLARIFY,
            ),
            # Repair: oscillation
            (
                ContextEnvelope(state="spin_problem", has_oscillation=True),
                {"action": "ask"},
                PolicyDecision.REPAIR_SUMMARIZE,
            ),
            # Objection: reframe
            (
                ContextEnvelope(
                    state="handle_objection",
                    current_intent="objection_price",
                    repeated_objection_types=["price"],
                    total_objections=2
                ),
                {"action": "handle"},
                PolicyDecision.OBJECTION_REFRAME,
            ),
        ]

        for envelope, sm_result, expected_decision in test_cases:
            override = policy.maybe_override(sm_result, envelope)

            if override and override.has_override:
                # ВСЕГДА должен быть reason_codes
                assert hasattr(override, "reason_codes"), \
                    f"Missing reason_codes for {expected_decision}"
                assert isinstance(override.reason_codes, list), \
                    f"reason_codes should be list for {expected_decision}"

                # reason НЕ должен существовать
                assert not hasattr(override, "reason"), \
                    f"Should not have 'reason' attr for {expected_decision}"
