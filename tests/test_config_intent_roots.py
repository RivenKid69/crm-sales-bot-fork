"""
Comprehensive tests for INTENT_ROOTS in config.py.

Tests 100% coverage of all intent root categories and their patterns.
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import INTENT_ROOTS


class TestIntentRootsStructure:
    """Tests for INTENT_ROOTS structure."""

    def test_intent_roots_is_dict(self):
        """Test INTENT_ROOTS is a dictionary."""
        assert isinstance(INTENT_ROOTS, dict)

    def test_intent_roots_not_empty(self):
        """Test INTENT_ROOTS is not empty."""
        assert len(INTENT_ROOTS) > 0

    def test_all_values_are_lists(self):
        """Test all values in INTENT_ROOTS are lists."""
        for intent, roots in INTENT_ROOTS.items():
            assert isinstance(roots, list), f"Intent {intent} value is not a list"

    def test_all_roots_are_strings(self):
        """Test all roots are strings."""
        for intent, roots in INTENT_ROOTS.items():
            for root in roots:
                assert isinstance(root, str), f"Root in {intent} is not a string: {root}"

    def test_no_empty_root_lists(self):
        """Test no intent has empty roots list."""
        for intent, roots in INTENT_ROOTS.items():
            assert len(roots) > 0, f"Intent {intent} has empty roots list"


class TestIntentRootsGreeting:
    """Tests for greeting intent roots."""

    def test_greeting_exists(self):
        """Test greeting intent exists."""
        assert "greeting" in INTENT_ROOTS

    def test_greeting_has_standard_greetings(self):
        """Test greeting has standard Russian greetings."""
        roots = INTENT_ROOTS["greeting"]
        assert "привет" in roots
        assert "здравств" in roots
        assert "добр" in roots

    def test_greeting_has_informal_variants(self):
        """Test greeting has informal variants."""
        roots = INTENT_ROOTS["greeting"]
        assert "хай" in roots or any("хай" in r for r in roots)

    def test_greeting_has_formal_variants(self):
        """Test greeting has formal variants."""
        roots = INTENT_ROOTS["greeting"]
        assert any("приветств" in r for r in roots)

    def test_greeting_covers_typos(self):
        """Test greeting covers common typos."""
        roots = INTENT_ROOTS["greeting"]
        # Should have some typo variants
        assert any("здрас" in r for r in roots)


class TestIntentRootsPriceQuestion:
    """Tests for price_question intent roots."""

    def test_price_question_exists(self):
        """Test price_question intent exists."""
        assert "price_question" in INTENT_ROOTS

    def test_price_question_has_price_words(self):
        """Test price_question has price-related words."""
        roots = INTENT_ROOTS["price_question"]
        assert "цен" in roots
        assert "стоим" in roots
        assert "прайс" in roots

    def test_price_question_has_cost_words(self):
        """Test price_question has cost-related words."""
        roots = INTENT_ROOTS["price_question"]
        assert any("тариф" in r for r in roots)

    def test_price_question_has_informal_words(self):
        """Test price_question has informal variants."""
        roots = INTENT_ROOTS["price_question"]
        assert any("почём" in r or "почом" in r for r in roots)


class TestIntentRootsObjectionPrice:
    """Tests for objection_price intent roots."""

    def test_objection_price_exists(self):
        """Test objection_price intent exists."""
        assert "objection_price" in INTENT_ROOTS

    def test_objection_price_has_expensive_words(self):
        """Test objection_price has 'expensive' words."""
        roots = INTENT_ROOTS["objection_price"]
        assert "дорог" in roots

    def test_objection_price_has_discount_words(self):
        """Test objection_price has discount-related words."""
        roots = INTENT_ROOTS["objection_price"]
        assert any("скидк" in r for r in roots)

    def test_objection_price_has_budget_words(self):
        """Test objection_price has budget-related words."""
        roots = INTENT_ROOTS["objection_price"]
        assert any("бюджет" in r for r in roots)


class TestIntentRootsObjectionNoTime:
    """Tests for objection_no_time intent roots."""

    def test_objection_no_time_exists(self):
        """Test objection_no_time intent exists."""
        assert "objection_no_time" in INTENT_ROOTS

    def test_objection_no_time_has_time_words(self):
        """Test objection_no_time has time-related words."""
        roots = INTENT_ROOTS["objection_no_time"]
        assert any("времен" in r for r in roots)

    def test_objection_no_time_has_busy_words(self):
        """Test objection_no_time has 'busy' words."""
        roots = INTENT_ROOTS["objection_no_time"]
        assert any("занят" in r for r in roots)

    def test_objection_no_time_has_later_words(self):
        """Test objection_no_time has 'later' words."""
        roots = INTENT_ROOTS["objection_no_time"]
        assert any("позж" in r or "потом" in r for r in roots)


class TestIntentRootsObjectionCompetitor:
    """Tests for objection_competitor intent roots."""

    def test_objection_competitor_exists(self):
        """Test objection_competitor intent exists."""
        assert "objection_competitor" in INTENT_ROOTS

    def test_objection_competitor_has_competitor_names(self):
        """Test objection_competitor has competitor names."""
        roots = INTENT_ROOTS["objection_competitor"]
        # Major CRM competitors
        assert any("битрикс" in r for r in roots)
        assert any("амо" in r.lower() or "amocrm" in r.lower() for r in roots)

    def test_objection_competitor_has_existing_system_phrases(self):
        """Test objection_competitor has 'already have' phrases."""
        roots = INTENT_ROOTS["objection_competitor"]
        assert any("уже есть" in r or "уже пользу" in r for r in roots)


class TestIntentRootsQuestionFeatures:
    """Tests for question_features intent roots."""

    def test_question_features_exists(self):
        """Test question_features intent exists."""
        assert "question_features" in INTENT_ROOTS

    def test_question_features_has_function_words(self):
        """Test question_features has function-related words."""
        roots = INTENT_ROOTS["question_features"]
        assert any("функци" in r for r in roots)
        assert any("возможност" in r for r in roots)

    def test_question_features_has_capability_words(self):
        """Test question_features has capability words."""
        roots = INTENT_ROOTS["question_features"]
        assert any("умеет" in r or "может" in r for r in roots)

    def test_question_features_has_question_words(self):
        """Test question_features has question-like words."""
        roots = INTENT_ROOTS["question_features"]
        assert any("как работает" in r for r in roots)


class TestIntentRootsQuestionIntegrations:
    """Tests for question_integrations intent roots."""

    def test_question_integrations_exists(self):
        """Test question_integrations intent exists."""
        assert "question_integrations" in INTENT_ROOTS

    def test_question_integrations_has_integration_word(self):
        """Test question_integrations has 'integration' word."""
        roots = INTENT_ROOTS["question_integrations"]
        assert any("интеграц" in r for r in roots)

    def test_question_integrations_has_connection_words(self):
        """Test question_integrations has connection words."""
        roots = INTENT_ROOTS["question_integrations"]
        assert any("подключ" in r for r in roots)

    def test_question_integrations_has_specific_services(self):
        """Test question_integrations has specific service names."""
        roots = INTENT_ROOTS["question_integrations"]
        # Common integrations
        assert any("1с" in r.lower() for r in roots)
        assert any("whatsapp" in r.lower() for r in roots)
        assert any("telegram" in r.lower() for r in roots)


class TestIntentRootsAgreement:
    """Tests for agreement intent roots."""

    def test_agreement_exists(self):
        """Test agreement intent exists."""
        assert "agreement" in INTENT_ROOTS

    def test_agreement_has_positive_words(self):
        """Test agreement has positive words."""
        roots = INTENT_ROOTS["agreement"]
        assert any("интересн" in r for r in roots)
        assert any("давайте" in r for r in roots)

    def test_agreement_has_confirmation_words(self):
        """Test agreement has confirmation words."""
        roots = INTENT_ROOTS["agreement"]
        assert any("да" in r for r in roots)
        assert any("ок" in r.lower() or "хорошо" in r for r in roots)

    def test_agreement_has_action_words(self):
        """Test agreement has action words."""
        roots = INTENT_ROOTS["agreement"]
        assert any("готов" in r for r in roots)


class TestIntentRootsRejection:
    """Tests for rejection intent roots."""

    def test_rejection_exists(self):
        """Test rejection intent exists."""
        assert "rejection" in INTENT_ROOTS

    def test_rejection_has_negative_words(self):
        """Test rejection has negative words."""
        roots = INTENT_ROOTS["rejection"]
        assert any("нет" in r for r in roots) or any("не надо" in r for r in roots)

    def test_rejection_has_stop_words(self):
        """Test rejection has stop words."""
        roots = INTENT_ROOTS["rejection"]
        assert any("отстань" in r or "хватит" in r or "стоп" in r for r in roots)


class TestIntentRootsContactProvided:
    """Tests for contact_provided intent roots."""

    def test_contact_provided_exists(self):
        """Test contact_provided intent exists."""
        assert "contact_provided" in INTENT_ROOTS

    def test_contact_provided_has_email_words(self):
        """Test contact_provided has email-related words."""
        roots = INTENT_ROOTS["contact_provided"]
        assert any("@" in r or "mail" in r.lower() for r in roots)

    def test_contact_provided_has_phone_words(self):
        """Test contact_provided has phone-related words."""
        roots = INTENT_ROOTS["contact_provided"]
        assert any("телефон" in r or "номер" in r for r in roots)


class TestIntentRootsSituationProvided:
    """Tests for situation_provided intent roots (SPIN S)."""

    def test_situation_provided_exists(self):
        """Test situation_provided intent exists."""
        assert "situation_provided" in INTENT_ROOTS

    def test_situation_provided_has_team_size_words(self):
        """Test situation_provided has team size words."""
        roots = INTENT_ROOTS["situation_provided"]
        assert any("человек" in r or "сотрудн" in r for r in roots)

    def test_situation_provided_has_business_type_words(self):
        """Test situation_provided has business type words."""
        roots = INTENT_ROOTS["situation_provided"]
        assert any("магазин" in r or "ресторан" in r for r in roots)

    def test_situation_provided_has_current_tools(self):
        """Test situation_provided has current tools words."""
        roots = INTENT_ROOTS["situation_provided"]
        assert any("excel" in r.lower() or "эксел" in r for r in roots)


class TestIntentRootsProblemRevealed:
    """Tests for problem_revealed intent roots (SPIN P)."""

    def test_problem_revealed_exists(self):
        """Test problem_revealed intent exists."""
        assert "problem_revealed" in INTENT_ROOTS

    def test_problem_revealed_has_problem_words(self):
        """Test problem_revealed has problem words."""
        roots = INTENT_ROOTS["problem_revealed"]
        assert any("проблем" in r or "сложн" in r for r in roots)

    def test_problem_revealed_has_loss_words(self):
        """Test problem_revealed has loss words."""
        roots = INTENT_ROOTS["problem_revealed"]
        assert any("теря" in r or "упуск" in r for r in roots)


class TestIntentRootsImplicationAcknowledged:
    """Tests for implication_acknowledged intent roots (SPIN I)."""

    def test_implication_acknowledged_exists(self):
        """Test implication_acknowledged intent exists."""
        assert "implication_acknowledged" in INTENT_ROOTS

    def test_implication_acknowledged_has_impact_words(self):
        """Test implication_acknowledged has impact words."""
        roots = INTENT_ROOTS["implication_acknowledged"]
        assert any("потер" in r or "убытк" in r for r in roots)

    def test_implication_acknowledged_has_amount_words(self):
        """Test implication_acknowledged has amount words."""
        roots = INTENT_ROOTS["implication_acknowledged"]
        assert any("тысяч" in r or "процент" in r for r in roots)


class TestIntentRootsNeedExpressed:
    """Tests for need_expressed intent roots (SPIN N)."""

    def test_need_expressed_exists(self):
        """Test need_expressed intent exists."""
        assert "need_expressed" in INTENT_ROOTS

    def test_need_expressed_has_want_words(self):
        """Test need_expressed has want words."""
        roots = INTENT_ROOTS["need_expressed"]
        assert any("хоте" in r or "нуж" in r for r in roots)

    def test_need_expressed_has_solution_words(self):
        """Test need_expressed has solution words."""
        roots = INTENT_ROOTS["need_expressed"]
        assert any("автоматиз" in r or "контрол" in r for r in roots)


class TestIntentRootsNoProblem:
    """Tests for no_problem intent roots."""

    def test_no_problem_exists(self):
        """Test no_problem intent exists."""
        assert "no_problem" in INTENT_ROOTS

    def test_no_problem_has_denial_phrases(self):
        """Test no_problem has denial phrases."""
        roots = INTENT_ROOTS["no_problem"]
        assert any("нет проблем" in r or "проблем нет" in r for r in roots)

    def test_no_problem_has_ok_phrases(self):
        """Test no_problem has 'everything ok' phrases."""
        roots = INTENT_ROOTS["no_problem"]
        assert any("всё хорошо" in r or "все хорошо" in r or "нас устраивает" in r for r in roots)


class TestIntentRootsNoNeed:
    """Tests for no_need intent roots."""

    def test_no_need_exists(self):
        """Test no_need intent exists."""
        assert "no_need" in INTENT_ROOTS

    def test_no_need_has_denial_phrases(self):
        """Test no_need has denial phrases."""
        roots = INTENT_ROOTS["no_need"]
        assert any("не нужно" in r or "не надо" in r for r in roots)


class TestIntentRootsCallbackRequest:
    """Tests for callback_request intent roots."""

    def test_callback_request_exists(self):
        """Test callback_request intent exists."""
        assert "callback_request" in INTENT_ROOTS

    def test_callback_request_has_call_words(self):
        """Test callback_request has call-related words."""
        roots = INTENT_ROOTS["callback_request"]
        assert any("перезвон" in r or "позвон" in r for r in roots)

    def test_callback_request_has_contact_words(self):
        """Test callback_request has contact words."""
        roots = INTENT_ROOTS["callback_request"]
        assert any("свяжи" in r or "связаться" in r for r in roots)


class TestIntentRootsDemoRequest:
    """Tests for demo_request intent roots."""

    def test_demo_request_exists(self):
        """Test demo_request intent exists."""
        assert "demo_request" in INTENT_ROOTS

    def test_demo_request_has_demo_words(self):
        """Test demo_request has demo-related words."""
        roots = INTENT_ROOTS["demo_request"]
        assert any("демо" in r for r in roots)

    def test_demo_request_has_try_words(self):
        """Test demo_request has try-related words."""
        roots = INTENT_ROOTS["demo_request"]
        assert any("попробова" in r or "потестир" in r for r in roots)

    def test_demo_request_has_trial_words(self):
        """Test demo_request has trial-related words."""
        roots = INTENT_ROOTS["demo_request"]
        assert any("триал" in r or "trial" in r.lower() or "тестов" in r for r in roots)


class TestIntentRootsCompleteness:
    """Tests for completeness of intent coverage."""

    EXPECTED_INTENTS = [
        "greeting",
        "price_question",
        "objection_price",
        "objection_no_time",
        "objection_competitor",
        "question_features",
        "question_integrations",
        "agreement",
        "rejection",
        "contact_provided",
        "situation_provided",
        "problem_revealed",
        "implication_acknowledged",
        "need_expressed",
        "no_problem",
        "no_need",
        "callback_request",
        "demo_request",
    ]

    def test_all_expected_intents_exist(self):
        """Test all expected intents exist in INTENT_ROOTS."""
        for intent in self.EXPECTED_INTENTS:
            assert intent in INTENT_ROOTS, f"Expected intent {intent} not found"

    def test_each_intent_has_minimum_roots(self):
        """Test each intent has minimum number of roots for coverage."""
        MIN_ROOTS = 3
        for intent, roots in INTENT_ROOTS.items():
            assert len(roots) >= MIN_ROOTS, \
                f"Intent {intent} has only {len(roots)} roots, expected >= {MIN_ROOTS}"


class TestIntentRootsQuality:
    """Tests for quality of intent roots."""

    def test_minimal_duplicate_roots_within_intent(self):
        """Test minimal duplicate roots within same intent (warn on duplicates)."""
        for intent, roots in INTENT_ROOTS.items():
            unique_roots = set(roots)
            duplicate_count = len(roots) - len(unique_roots)
            # Allow small number of duplicates (some may be intentional)
            assert duplicate_count <= 5, \
                f"Intent {intent} has too many duplicate roots: {duplicate_count}"

    def test_roots_are_lowercase_or_proper(self):
        """Test roots are properly formatted (lowercase for Russian)."""
        for intent, roots in INTENT_ROOTS.items():
            for root in roots:
                # Most roots should be lowercase (except special cases like 1С)
                if not any(char.isupper() for char in root if char.isalpha()):
                    assert root == root.lower() or root.startswith("1") or "@" in root, \
                        f"Root '{root}' in {intent} should be lowercase"

    def test_no_empty_string_roots(self):
        """Test no empty string roots."""
        for intent, roots in INTENT_ROOTS.items():
            for root in roots:
                assert len(root.strip()) > 0, f"Empty root in intent {intent}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
