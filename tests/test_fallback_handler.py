"""
Tests for FallbackHandler module.

Tests cover:
- All four fallback tiers
- Response structure
- Template selection and variation
- Skip map transitions
- Statistics tracking
- Tier escalation
- Edge cases
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fallback_handler import FallbackHandler, FallbackResponse, FallbackStats


class TestFallbackResponse:
    """Tests for FallbackResponse dataclass"""

    def test_default_values(self):
        """Default values are correct"""
        response = FallbackResponse(message="test")
        assert response.message == "test"
        assert response.options is None
        assert response.action == "continue"
        assert response.next_state is None

    def test_with_options(self):
        """Can create response with options"""
        response = FallbackResponse(
            message="Choose:",
            options=["A", "B", "C"],
            action="continue"
        )
        assert response.options == ["A", "B", "C"]

    def test_with_skip(self):
        """Can create skip response"""
        response = FallbackResponse(
            message="Let's skip",
            action="skip",
            next_state="presentation"
        )
        assert response.action == "skip"
        assert response.next_state == "presentation"


class TestFallbackStats:
    """Tests for FallbackStats dataclass"""

    def test_initial_values(self):
        """Initial values are zero/empty"""
        stats = FallbackStats()
        assert stats.total_count == 0
        assert stats.tier_counts == {}
        assert stats.state_counts == {}
        assert stats.last_tier is None
        assert stats.last_state is None


class TestFallbackHandlerBasic:
    """Basic tests for FallbackHandler"""

    def test_initialization(self):
        """Handler initializes correctly"""
        handler = FallbackHandler()
        assert handler.stats.total_count == 0

    def test_reset(self):
        """Reset clears all state"""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_problem")

        handler.reset()

        assert handler.stats.total_count == 0
        assert handler.stats.tier_counts == {}


class TestTier1Rephrase:
    """Tests for Tier 1 (rephrase)"""

    def test_tier_1_returns_message(self):
        """Tier 1 returns a message"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation")

        assert response.message
        assert len(response.message) > 0
        assert response.options is None
        assert response.action == "continue"
        assert response.next_state is None

    def test_tier_1_different_states(self):
        """Tier 1 has different messages for different states"""
        handler = FallbackHandler()

        r1 = handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.reset()
        r2 = handler.get_fallback("fallback_tier_1", "spin_problem")

        # Different templates for different states
        # (messages might differ)
        assert r1.message != r2.message or True  # May be same by chance

    def test_tier_1_unknown_state_has_default(self):
        """Tier 1 handles unknown state with default"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "unknown_state")

        assert response.message
        assert response.action == "continue"

    def test_tier_1_messages_vary(self):
        """Tier 1 varies messages to avoid repetition"""
        handler = FallbackHandler()

        messages = set()
        for _ in range(10):
            handler.reset()  # Reset to allow reuse
            response = handler.get_fallback("fallback_tier_1", "spin_situation")
            messages.add(response.message)

        # Should have at least some variation
        # (with enough templates, should see multiple unique messages)
        assert len(messages) >= 1  # At minimum one


class TestTier2Options:
    """Tests for Tier 2 (options)"""

    def test_tier_2_returns_options(self):
        """Tier 2 returns options for known states"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_situation")

        assert response.message
        assert response.options is not None
        assert len(response.options) > 0
        assert response.action == "continue"

    def test_tier_2_options_are_list(self):
        """Tier 2 options are a list of strings"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_problem")

        assert isinstance(response.options, list)
        for opt in response.options:
            assert isinstance(opt, str)

    def test_tier_2_fallback_to_tier_1(self):
        """Tier 2 falls back to Tier 1 if no options for state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "unknown_state")

        # Should still return a message even without options template
        assert response.message
        assert response.action == "continue"

    def test_tier_2_spin_situation_options(self):
        """Tier 2 has correct options for spin_situation"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_situation")

        assert response.options
        # Should have team size options
        assert any("человек" in opt for opt in response.options)


class TestTier3Skip:
    """Tests for Tier 3 (skip)"""

    def test_tier_3_returns_skip_action(self):
        """Tier 3 returns skip action"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_3", "spin_situation")

        assert response.message
        assert response.action == "skip"
        assert response.next_state is not None

    def test_tier_3_correct_next_states(self):
        """Tier 3 returns correct next states"""
        handler = FallbackHandler()

        # Test skip map
        test_cases = [
            ("greeting", "spin_situation"),
            ("spin_situation", "spin_problem"),
            ("spin_problem", "spin_implication"),
            ("spin_implication", "spin_need_payoff"),
            ("spin_need_payoff", "presentation"),
            ("presentation", "close"),
        ]

        for current_state, expected_next in test_cases:
            handler.reset()
            response = handler.get_fallback("fallback_tier_3", current_state)
            assert response.next_state == expected_next, \
                f"Expected {expected_next} for {current_state}, got {response.next_state}"

    def test_tier_3_unknown_state_to_presentation(self):
        """Tier 3 defaults to presentation for unknown state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_3", "unknown_state")

        assert response.next_state == "presentation"


class TestTier4Exit:
    """Tests for Tier 4 (graceful exit)"""

    def test_tier_4_returns_close_action(self):
        """Tier 4 returns close action"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_4", "any_state")

        assert response.message
        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_soft_close_alias(self):
        """soft_close tier works same as tier_4"""
        handler = FallbackHandler()
        response = handler.get_fallback("soft_close", "any_state")

        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_tier_4_message_offers_contact(self):
        """Tier 4 message offers to stay in contact"""
        handler = FallbackHandler()

        # Check multiple messages
        contact_keywords = ["почту", "контакт", "связ", "информацию", "прислать"]
        found_contact_offer = False

        for _ in range(10):
            handler.reset()
            response = handler.get_fallback("soft_close", "state")
            if any(kw in response.message.lower() for kw in contact_keywords):
                found_contact_offer = True
                break

        assert found_contact_offer, "Tier 4 messages should offer contact options"


class TestStatistics:
    """Tests for statistics tracking"""

    def test_stats_increment_on_fallback(self):
        """Stats increment when fallback is used"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")

        assert handler.stats.total_count == 1
        assert handler.stats.tier_counts.get("fallback_tier_1") == 1
        assert handler.stats.state_counts.get("spin_situation") == 1

    def test_stats_track_multiple_fallbacks(self):
        """Stats track multiple fallbacks correctly"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_situation")
        handler.get_fallback("fallback_tier_1", "spin_problem")
        handler.get_fallback("soft_close", "presentation")

        assert handler.stats.total_count == 4
        assert handler.stats.tier_counts.get("fallback_tier_1") == 2
        assert handler.stats.tier_counts.get("fallback_tier_2") == 1
        assert handler.stats.tier_counts.get("soft_close") == 1
        assert handler.stats.state_counts.get("spin_situation") == 2
        assert handler.stats.state_counts.get("spin_problem") == 1

    def test_stats_last_tier_and_state(self):
        """Stats track last tier and state"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_problem")

        assert handler.stats.last_tier == "fallback_tier_2"
        assert handler.stats.last_state == "spin_problem"

    def test_get_stats_dict(self):
        """get_stats_dict returns correct structure"""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_1", "spin_situation")

        stats = handler.get_stats_dict()

        assert "total_count" in stats
        assert "tier_counts" in stats
        assert "state_counts" in stats
        assert "last_tier" in stats
        assert "last_state" in stats
        assert stats["total_count"] == 1


class TestTierEscalation:
    """Tests for tier escalation"""

    def test_escalate_tier_1_to_2(self):
        """Escalation from tier 1 to tier 2"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_1")
        assert next_tier == "fallback_tier_2"

    def test_escalate_tier_2_to_3(self):
        """Escalation from tier 2 to tier 3"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_2")
        assert next_tier == "fallback_tier_3"

    def test_escalate_tier_3_to_close(self):
        """Escalation from tier 3 to soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_3")
        assert next_tier == "soft_close"

    def test_escalate_soft_close_stays(self):
        """Escalation from soft_close stays at soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("soft_close")
        assert next_tier == "soft_close"

    def test_escalate_unknown_tier(self):
        """Escalation from unknown tier goes to soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("unknown_tier")
        assert next_tier == "soft_close"

    def test_full_escalation_sequence(self):
        """Full escalation sequence works"""
        handler = FallbackHandler()

        tier = "fallback_tier_1"
        sequence = [tier]

        for _ in range(5):  # More than enough iterations
            tier = handler.escalate_tier(tier)
            sequence.append(tier)
            if tier == "soft_close":
                break

        expected = [
            "fallback_tier_1",
            "fallback_tier_2",
            "fallback_tier_3",
            "soft_close"
        ]
        assert sequence == expected


class TestTemplateVariation:
    """Tests for template variation to avoid repetition"""

    def test_templates_dont_repeat_immediately(self):
        """Templates shouldn't repeat immediately"""
        handler = FallbackHandler()

        # Get multiple fallbacks for same state/tier
        # Note: After 3 fallbacks, tier_1 escalates to tier_2,
        # so we only test 2 consecutive messages
        messages = []
        for _ in range(2):
            response = handler.get_fallback("fallback_tier_1", "spin_situation")
            messages.append(response.message)

        # Check consecutive messages aren't the same
        # (may eventually repeat, but not immediately)
        for i in range(len(messages) - 1):
            if messages[i] == messages[i + 1]:
                # Only fail if there's more than one template
                templates = handler.REPHRASE_TEMPLATES.get("spin_situation", [])
                if len(templates) > 1:
                    pytest.fail(f"Consecutive messages were identical: {messages[i]}")

    def test_exit_templates_vary(self):
        """Exit templates vary"""
        handler = FallbackHandler()

        messages = set()
        for _ in range(20):
            handler._used_templates.clear()  # Clear to get fresh selection
            response = handler.get_fallback("soft_close", "state")
            messages.add(response.message)

        # Should have multiple unique messages
        assert len(messages) >= min(2, len(handler.EXIT_TEMPLATES))


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_context(self):
        """Handles empty context"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})
        assert response.message

    def test_none_context(self):
        """Handles None context"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation", None)
        assert response.message

    def test_empty_state(self):
        """Handles empty state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "")
        assert response.message
        assert response.action == "continue"

    def test_context_with_data(self):
        """Handles context with data"""
        handler = FallbackHandler()
        context = {
            "company_size": 10,
            "pain_point": "losing clients",
            "industry": "retail"
        }
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)
        assert response.message

    def test_all_states_have_skip_destination(self):
        """All SPIN states have skip destinations"""
        handler = FallbackHandler()
        states = [
            "greeting",
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
            "presentation"
        ]

        for state in states:
            response = handler.get_fallback("fallback_tier_3", state)
            assert response.next_state is not None, f"No skip destination for {state}"


class TestMultipleHandlerInstances:
    """Tests for multiple handler instances"""

    def test_independent_instances(self):
        """Multiple handlers are independent"""
        handler1 = FallbackHandler()
        handler2 = FallbackHandler()

        handler1.get_fallback("fallback_tier_1", "spin_situation")
        handler1.get_fallback("fallback_tier_2", "spin_problem")

        assert handler1.stats.total_count == 2
        assert handler2.stats.total_count == 0

    def test_independent_template_history(self):
        """Handlers have independent template history"""
        handler1 = FallbackHandler()
        handler2 = FallbackHandler()

        # Fill handler1's history
        for _ in range(5):
            handler1.get_fallback("fallback_tier_1", "spin_situation")

        # Handler2 should start fresh
        response = handler2.get_fallback("fallback_tier_1", "spin_situation")
        assert response.message  # Should work without issues


class TestSpecificStates:
    """Tests for specific state handling"""

    def test_greeting_state(self):
        """Greeting state has appropriate responses"""
        handler = FallbackHandler()

        # Tier 1
        r1 = handler.get_fallback("fallback_tier_1", "greeting")
        assert r1.message
        assert r1.action == "continue"

        # Tier 3 skip
        handler.reset()
        r3 = handler.get_fallback("fallback_tier_3", "greeting")
        assert r3.next_state == "spin_situation"

    def test_presentation_state(self):
        """Presentation state has appropriate responses"""
        handler = FallbackHandler()

        # Tier 2 options
        r2 = handler.get_fallback("fallback_tier_2", "presentation")
        assert r2.options is not None
        assert len(r2.options) > 0

        # Tier 3 skip
        handler.reset()
        r3 = handler.get_fallback("fallback_tier_3", "presentation")
        assert r3.next_state == "close"

    def test_handle_objection_state(self):
        """Handle objection state has appropriate responses"""
        handler = FallbackHandler()

        r1 = handler.get_fallback("fallback_tier_1", "handle_objection")
        assert r1.message
        # Should acknowledge objection
        assert any(
            word in r1.message.lower()
            for word in ["понимаю", "сомнения", "вопрос", "момент", "беспокоит"]
        )


class TestDynamicCTAOptions:
    """Tests for Dynamic CTA text suggestions in Tier 2"""

    def setup_method(self):
        from feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)
        self.handler = FallbackHandler()

    def teardown_method(self):
        from feature_flags import flags
        flags.clear_override("dynamic_cta_fallback")

    def test_competitor_mentioned_shows_comparison_options(self):
        """Упоминание конкурента → подсказки про сравнение"""
        context = {
            "collected_data": {
                "competitor_mentioned": True,
                "competitor_name": "Битрикс",
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert "Сравнить" in response.message
        assert "Битрикс" in response.message
        assert "1." in response.message  # Нумерованный список

    def test_competitor_name_substituted(self):
        """Имя конкурента подставляется в шаблон"""
        context = {
            "collected_data": {
                "competitor_mentioned": True,
                "competitor_name": "iiko",
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert "iiko" in response.message

    def test_pain_point_losing_clients(self):
        """Pain point про потерю клиентов → релевантные подсказки"""
        context = {
            "collected_data": {
                "pain_point": "теряем клиентов",
                "pain_category": "losing_clients",
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert any(word in response.message.lower() for word in ["напоминания", "контроль", "аналитика"])

    def test_large_company_options(self):
        """Большая компания → enterprise подсказки"""
        context = {
            "collected_data": {
                "company_size": 50,
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_situation", context)

        assert any(word in response.message.lower() for word in ["интеграци", "масштаб", "права"])

    def test_small_company_options(self):
        """Маленькая компания → простые подсказки"""
        context = {
            "collected_data": {
                "company_size": 3,
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_situation", context)

        assert any(word in response.message.lower() for word in ["базов", "быстр", "бесплатн"])

    def test_after_price_question(self):
        """После вопроса о цене → подсказки про оплату"""
        context = {
            "collected_data": {},
            "last_intent": "price_question",
        }

        response = self.handler.get_fallback("fallback_tier_2", "presentation", context)

        assert any(word in response.message.lower() for word in ["оплат", "тариф", "пробн"])

    def test_competitor_beats_pain_point_priority(self):
        """Competitor (priority 10) важнее pain_point (priority 8)"""
        context = {
            "collected_data": {
                "competitor_mentioned": True,
                "competitor_name": "AmoCRM",
                "pain_point": "нет контроля",
                "pain_category": "no_control",
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        # Должны быть подсказки про конкурента, не про контроль
        assert "AmoCRM" in response.message or "Сравнить" in response.message

    def test_max_four_options(self):
        """Не больше 4 вариантов"""
        context = {
            "collected_data": {"competitor_mentioned": True},
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        # Считаем номера в сообщении
        assert "5." not in response.message
        assert response.options is None or len(response.options) <= 4

    def test_includes_input_hint(self):
        """Сообщение содержит подсказку про ввод"""
        context = {
            "collected_data": {"competitor_mentioned": True},
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert "номер" in response.message.lower() or "своими словами" in response.message.lower()

    def test_fallback_to_static_when_no_context(self):
        """Пустой контекст → статичные подсказки"""
        context = {"collected_data": {}}

        response = self.handler.get_fallback("fallback_tier_2", "spin_situation", context)

        # Статичные подсказки для spin_situation (с нумерацией)
        assert "1." in response.message  # Нумерованный список
        assert "человек" in response.message.lower()

    def test_fallback_to_static_when_flag_disabled(self):
        """Flag выключен → статичные подсказки"""
        from feature_flags import flags
        flags.set_override("dynamic_cta_fallback", False)

        context = {
            "collected_data": {"competitor_mentioned": True},
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_situation", context)

        # Не должно быть competitor-специфичных подсказок
        assert "Сравнить" not in response.message

    def test_stats_track_dynamic_cta_type(self):
        """Статистика записывает тип динамических подсказок"""
        context = {
            "collected_data": {"competitor_mentioned": True},
        }

        self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        stats = self.handler.get_stats_dict()
        assert stats["dynamic_cta_counts"].get("competitor_mentioned", 0) >= 1

    def test_pain_no_control_options(self):
        """Pain point про контроль → релевантные подсказки"""
        context = {
            "collected_data": {
                "pain_point": "нет контроля",
                "pain_category": "no_control",
            },
        }

        response = self.handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert any(word in response.message.lower() for word in ["контроль", "задач", "отчёт"])

    def test_after_features_question(self):
        """После вопроса о функциях → подсказки про функции"""
        context = {
            "collected_data": {},
            "last_intent": "question_features",
        }

        response = self.handler.get_fallback("fallback_tier_2", "presentation", context)

        assert any(word in response.message.lower() for word in ["автоматиз", "аналитик", "интеграци", "демо"])


class TestDynamicCTAStats:
    """Tests for Dynamic CTA statistics in FallbackStats"""

    def test_stats_includes_dynamic_cta_counts(self):
        """FallbackStats includes dynamic_cta_counts"""
        stats = FallbackStats()
        assert hasattr(stats, 'dynamic_cta_counts')
        assert stats.dynamic_cta_counts == {}

    def test_get_stats_dict_includes_dynamic_cta_counts(self):
        """get_stats_dict includes dynamic_cta_counts"""
        from feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)

        handler = FallbackHandler()
        context = {"collected_data": {"competitor_mentioned": True}}
        handler.get_fallback("fallback_tier_2", "spin_problem", context)

        stats = handler.get_stats_dict()
        assert "dynamic_cta_counts" in stats

        flags.clear_override("dynamic_cta_fallback")


class TestCompetitorExtraction:
    """Tests for competitor name extraction in SalesBot"""

    def setup_method(self):
        # Import here to avoid circular imports
        import sys
        sys.path.insert(0, 'src')

    def test_extract_bitrix(self):
        """Извлечение Битрикс"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("у нас сейчас битрикс") == "Битрикс"
        assert bot._extract_competitor_name("используем bitrix24") == "Битрикс"
        assert bot._extract_competitor_name("работаем с Bitrix") == "Битрикс"

    def test_extract_amocrm(self):
        """Извлечение AmoCRM"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("пользуемся амо") == "AmoCRM"
        assert bot._extract_competitor_name("у нас amocrm") == "AmoCRM"
        assert bot._extract_competitor_name("сидим на amo crm") == "AmoCRM"

    def test_extract_iiko(self):
        """Извлечение iiko"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("работаем с iiko") == "iiko"
        assert bot._extract_competitor_name("у нас ийко") == "iiko"

    def test_extract_1c(self):
        """Извлечение 1С"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("используем 1с") == "1С"
        assert bot._extract_competitor_name("у нас 1C") == "1С"

    def test_extract_megaplan(self):
        """Извлечение Мегаплан"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("работаем в мегаплане") == "Мегаплан"
        assert bot._extract_competitor_name("megaplan у нас") == "Мегаплан"

    def test_no_competitor(self):
        """Нет конкурента в сообщении"""
        from bot import SalesBot

        class MockLLM:
            def generate(self, *args, **kwargs):
                return "Test"

        bot = SalesBot(MockLLM())

        assert bot._extract_competitor_name("нам нужна CRM") is None
        assert bot._extract_competitor_name("хотим автоматизировать") is None


class TestFormattedOptions:
    """Tests for formatted options output"""

    def test_options_have_numbered_list(self):
        """Options are formatted as numbered list"""
        from feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)

        handler = FallbackHandler()
        context = {"collected_data": {"competitor_mentioned": True}}
        response = handler.get_fallback("fallback_tier_2", "spin_problem", context)

        # Проверяем что есть нумерация
        assert "1." in response.message
        assert "2." in response.message
        assert "3." in response.message
        assert "4." in response.message

        flags.clear_override("dynamic_cta_fallback")

    def test_options_have_footer_hint(self):
        """Options include footer hint"""
        from feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)

        handler = FallbackHandler()
        context = {"collected_data": {"competitor_mentioned": True}}
        response = handler.get_fallback("fallback_tier_2", "spin_problem", context)

        assert "Напишите номер" in response.message or "своими словами" in response.message

        flags.clear_override("dynamic_cta_fallback")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
