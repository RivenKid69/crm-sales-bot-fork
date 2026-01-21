"""
Tests for StateMachine with extended intent taxonomy (200+ intents).

These tests verify that the state machine correctly handles all new intent groups:
- Equipment questions (12 intents)
- Tariff questions (8 intents)
- TIS questions (10 intents)
- Tax questions (8 intents)
- Accounting questions (8 intents)
- Integration questions (14 intents)
- Operations questions (10 intents)
- Business scenarios (18 intents)
- Technical problems (6 intents)
- Fiscal questions (8 intents)
- Analytics questions (8 intents)
- Wipon products (6 intents)
- Employee questions (6 intents)
- Promo/loyalty (6 intents)
- Stability questions (6 intents)
- Region questions (6 intents)
- Delivery/service (6 intents)
- Conversational/emotional (10 intents)
- Purchase stages (8 intents)
- Positive signals (8 intents)
- Extended objections (18 intents)
- Company info (4 intents)
- Dialogue control (8 intents)
"""

import pytest
from src.state_machine import StateMachine


class TestExtendedObjections:
    """Tests for all 18 objection types."""

    @pytest.fixture
    def state_machine(self):
        """Create a fresh state machine for each test."""
        return StateMachine()

    @pytest.mark.parametrize("objection_intent", [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
        "objection_timing",
        "objection_complexity",
        "objection_trust",
        "objection_no_need",
        "objection_risk",
        "objection_team_resistance",
        "objection_security",
        "objection_bad_experience",
        "objection_priority",
        "objection_scale",
        "objection_change_management",
        "objection_contract_bound",
        "objection_company_policy",
        "objection_roi_doubt",
    ])
    def test_all_objections_handled_in_greeting(self, state_machine, objection_intent):
        """All 18 objections should transition to handle_objection from greeting."""
        state_machine.state = "greeting"
        result = state_machine.process(objection_intent)

        # Should go to handle_objection (or soft_close if limit reached)
        assert result["next_state"] in ["handle_objection", "soft_close"]

    @pytest.mark.parametrize("objection_intent", [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
        "objection_timing",
        "objection_complexity",
        "objection_trust",
        "objection_no_need",
        "objection_risk",
        "objection_team_resistance",
        "objection_security",
        "objection_bad_experience",
        "objection_priority",
        "objection_scale",
        "objection_change_management",
        "objection_contract_bound",
        "objection_company_policy",
        "objection_roi_doubt",
    ])
    def test_all_objections_handled_in_presentation(self, state_machine, objection_intent):
        """All 18 objections should transition to handle_objection from presentation."""
        state_machine.state = "presentation"
        result = state_machine.process(objection_intent)

        assert result["next_state"] == "handle_objection"

    @pytest.mark.parametrize("objection_intent", [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
        "objection_timing",
        "objection_complexity",
        "objection_trust",
        "objection_no_need",
    ])
    def test_all_objections_handled_in_close(self, state_machine, objection_intent):
        """Objections in close should transition to handle_objection."""
        state_machine.state = "close"
        result = state_machine.process(objection_intent)

        assert result["next_state"] == "handle_objection"

    def test_objection_limit_leads_to_soft_close(self, state_machine):
        """Repeated objections should eventually lead to soft_close."""
        state_machine.state = "greeting"

        # Record multiple objections to hit the limit
        for _ in range(5):
            state_machine.intent_tracker.record("objection_price", "greeting")

        result = state_machine.process("objection_price")

        # Should go to soft_close after hitting limit
        assert result["next_state"] == "soft_close"


class TestPositiveSignals:
    """Tests for new positive signal intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("positive_intent", [
        "ready_to_buy",
        "budget_approved",
        "urgency_expressed",
        "internal_champion",
    ])
    def test_positive_signals_lead_to_close_from_greeting(self, state_machine, positive_intent):
        """Strong positive signals from greeting should lead to close."""
        state_machine.state = "greeting"
        result = state_machine.process(positive_intent)

        assert result["next_state"] == "close"

    @pytest.mark.parametrize("positive_intent", [
        "ready_to_buy",
        "budget_approved",
        "urgency_expressed",
        "internal_champion",
    ])
    def test_positive_signals_lead_to_close_from_presentation(self, state_machine, positive_intent):
        """Strong positive signals from presentation should lead to close."""
        state_machine.state = "presentation"
        result = state_machine.process(positive_intent)

        assert result["next_state"] == "close"

    @pytest.mark.parametrize("progression_intent", [
        "decision_maker_identified",
        "competitor_dissatisfied",
        "expansion_planned",
        "positive_feedback",
    ])
    def test_progression_signals_advance_spin_phase(self, state_machine, progression_intent):
        """Progression signals should advance the SPIN phase."""
        state_machine.state = "spin_situation"
        result = state_machine.process(progression_intent)

        # Should advance to next phase
        assert result["next_state"] == "spin_problem"


class TestPurchaseStages:
    """Tests for purchase stage intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("purchase_intent", [
        "request_proposal",
        "request_contract",
        "request_invoice",
    ])
    def test_purchase_intents_lead_to_close_from_greeting(self, state_machine, purchase_intent):
        """Purchase stage intents from greeting should lead to close."""
        state_machine.state = "greeting"
        result = state_machine.process(purchase_intent)

        assert result["next_state"] == "close"

    @pytest.mark.parametrize("purchase_intent", [
        "request_proposal",
        "request_contract",
        "request_invoice",
    ])
    def test_purchase_intents_lead_to_close_from_presentation(self, state_machine, purchase_intent):
        """Purchase stage intents from presentation should lead to close."""
        state_machine.state = "presentation"
        result = state_machine.process(purchase_intent)

        assert result["next_state"] == "close"


class TestEquipmentQuestions:
    """Tests for equipment question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("equipment_intent", [
        "question_equipment_general",
        "question_pos_monoblock",
        "question_scales",
        "question_scanner",
        "question_printer",
        "question_cash_drawer",
        "question_equipment_bundle",
        "question_equipment_specs",
        "question_equipment_warranty",
        "question_equipment_install",
        "question_equipment_compat",
        "question_second_screen",
    ])
    def test_equipment_questions_get_action_in_spin_phase(self, state_machine, equipment_intent):
        """Equipment questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(equipment_intent)

        # Should stay in same state and get factual answer
        assert action == "answer_with_facts"
        assert next_state == "spin_situation"

    def test_equipment_question_advances_from_greeting(self, state_machine):
        """Equipment question from greeting should advance to entry_state."""
        state_machine.state = "greeting"
        result = state_machine.process("question_equipment_general")

        # Should advance to spin_situation (entry_state)
        assert result["next_state"] == "spin_situation"


class TestTariffQuestions:
    """Tests for tariff question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("tariff_intent", [
        "question_tariff_mini",
        "question_tariff_lite",
        "question_tariff_standard",
        "question_tariff_pro",
        "question_tariff_comparison",
        "question_installment",
        "question_trial_period",
        "question_ofd_payment",
    ])
    def test_tariff_questions_get_action_in_spin_phase(self, state_machine, tariff_intent):
        """Tariff questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(tariff_intent)

        assert action == "answer_with_facts"
        assert next_state == "spin_situation"


class TestTISQuestions:
    """Tests for TIS (Three-component Integrated System) question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("tis_intent", [
        "question_tis_general",
        "question_tis_limits",
        "question_tis_price",
        "question_tis_requirements",
        "question_tis_benefits",
        "question_tis_2026",
        "question_tis_components",
        "question_tis_multi_location",
        "question_tis_transition",
        "question_tis_reports",
    ])
    def test_tis_questions_get_action_in_spin_phase(self, state_machine, tis_intent):
        """TIS questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(tis_intent)

        assert action == "answer_with_facts"


class TestTaxQuestions:
    """Tests for tax question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("tax_intent", [
        "question_retail_tax_general",
        "question_retail_tax_rates",
        "question_retail_tax_oked",
        "question_retail_tax_reports",
        "question_retail_tax_transition",
        "question_snr_comparison",
        "question_vat_registration",
        "question_tax_optimization",
    ])
    def test_tax_questions_get_action_in_spin_phase(self, state_machine, tax_intent):
        """Tax questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(tax_intent)

        assert action == "answer_with_facts"


class TestAccountingQuestions:
    """Tests for accounting question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("accounting_intent", [
        "question_accounting_services",
        "question_esf_snt",
        "question_form_910",
        "question_form_200",
        "question_form_300",
        "question_business_registration",
        "question_business_closure",
        "question_document_flow",
    ])
    def test_accounting_questions_get_action_in_spin_phase(self, state_machine, accounting_intent):
        """Accounting questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(accounting_intent)

        assert action == "answer_with_facts"


class TestIntegrationQuestions:
    """Tests for integration question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("integration_intent", [
        "question_bank_terminal",
        "question_kaspi_integration",
        "question_halyk_integration",
        "question_1c_integration",
        "question_iiko_integration",
        "question_ofd_connection",
        "question_marking_ismet",
        "question_cashback_loyalty",
        "question_glovo_wolt",
        "question_telegram_bot",
        "question_whatsapp_business",
        "question_instagram_shop",
        "question_website_widget",
        "question_delivery_services",
    ])
    def test_integration_questions_get_action_in_spin_phase(self, state_machine, integration_intent):
        """Integration questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(integration_intent)

        assert action == "answer_with_facts"


class TestOperationsQuestions:
    """Tests for operations question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("operations_intent", [
        "question_inventory",
        "question_revision",
        "question_purchase_mgmt",
        "question_sales_mgmt",
        "question_cash_operations",
        "question_returns_mgmt",
        "question_employee_control",
        "question_multi_location",
        "question_promo_discounts",
        "question_price_labels",
    ])
    def test_operations_questions_get_action_in_spin_phase(self, state_machine, operations_intent):
        """Operations questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(operations_intent)

        assert action == "answer_with_facts"


class TestBusinessScenarios:
    """Tests for business scenario question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("scenario_intent", [
        "question_grocery_store",
        "question_restaurant_cafe",
        "question_pharmacy",
        "question_clothing_store",
        "question_small_business",
        "question_network_stores",
        "question_market_stall",
        "question_alcohol_tobacco",
        "question_beauty_salon",
        "question_construction",
        "question_wholesale",
        "question_auto_parts",
        "question_electronics",
        "question_pet_shop",
        "question_flower_shop",
        "question_hotel",
        "question_service_center",
        "question_sports_shop",
    ])
    def test_business_scenario_questions_get_action_in_spin_phase(self, state_machine, scenario_intent):
        """Business scenario questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(scenario_intent)

        assert action == "answer_with_facts"

    @pytest.mark.parametrize("scenario_intent", [
        "question_grocery_store",
        "question_restaurant_cafe",
        "question_pharmacy",
    ])
    def test_business_scenario_advances_from_greeting(self, state_machine, scenario_intent):
        """Business scenario question from greeting should advance to entry_state."""
        state_machine.state = "greeting"
        result = state_machine.process(scenario_intent)

        # Should advance to spin_situation (entry_state)
        assert result["next_state"] == "spin_situation"


class TestTechnicalProblems:
    """Tests for technical problem intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("problem_intent,expected_action", [
        ("problem_technical", "offer_support"),
        ("problem_connection", "offer_support"),
        ("problem_sync", "offer_support"),
        ("problem_fiscal", "offer_support"),
        ("request_technical_support", "connect_to_support"),
        ("request_configuration", "offer_setup_help"),
    ])
    def test_technical_problems_get_support_action(self, state_machine, problem_intent, expected_action):
        """Technical problems should get appropriate support action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(problem_intent)

        assert action == expected_action


class TestFiscalQuestions:
    """Tests for fiscal question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("fiscal_intent", [
        "question_fiscal_general",
        "question_fiscal_receipt",
        "question_fiscal_z_report",
        "question_fiscal_x_report",
        "question_fiscal_kkm",
        "question_fiscal_ofd_wipon",
        "question_fiscal_correction",
        "question_fiscal_replacement",
    ])
    def test_fiscal_questions_get_action_in_spin_phase(self, state_machine, fiscal_intent):
        """Fiscal questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(fiscal_intent)

        assert action == "answer_with_facts"


class TestAnalyticsQuestions:
    """Tests for analytics question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("analytics_intent", [
        "question_analytics_sales",
        "question_analytics_abc",
        "question_analytics_profit",
        "question_analytics_comparison",
        "question_analytics_realtime",
        "question_analytics_export",
        "question_analytics_custom",
        "question_analytics_dashboard",
    ])
    def test_analytics_questions_get_action_in_spin_phase(self, state_machine, analytics_intent):
        """Analytics questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(analytics_intent)

        assert action == "answer_with_facts"


class TestWiponProducts:
    """Tests for Wipon product question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("wipon_intent", [
        "question_wipon_pro",
        "question_wipon_desktop",
        "question_wipon_kassa",
        "question_wipon_consulting",
        "question_wipon_cashback_app",
        "question_product_comparison",
    ])
    def test_wipon_product_questions_get_action_in_spin_phase(self, state_machine, wipon_intent):
        """Wipon product questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(wipon_intent)

        assert action == "answer_with_facts"


class TestEmployeeQuestions:
    """Tests for employee question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("employee_intent", [
        "question_employees_salary",
        "question_employees_schedule",
        "question_employees_permissions",
        "question_employees_tracking",
        "question_employees_motivation",
        "question_employees_onboarding",
    ])
    def test_employee_questions_get_action_in_spin_phase(self, state_machine, employee_intent):
        """Employee questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(employee_intent)

        assert action == "answer_with_facts"


class TestPromoLoyalty:
    """Tests for promo/loyalty question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("promo_intent", [
        "question_loyalty_program",
        "question_bonus_system",
        "question_discount_cards",
        "question_gift_cards",
        "question_customer_database",
        "question_sms_marketing",
    ])
    def test_promo_loyalty_questions_get_action_in_spin_phase(self, state_machine, promo_intent):
        """Promo/loyalty questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(promo_intent)

        assert action == "answer_with_facts"


class TestStabilityQuestions:
    """Tests for stability question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("stability_intent", [
        "question_backup_restore",
        "question_uptime_sla",
        "question_server_location",
        "question_data_encryption",
        "question_disaster_recovery",
        "question_system_requirements",
    ])
    def test_stability_questions_get_action_in_spin_phase(self, state_machine, stability_intent):
        """Stability questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(stability_intent)

        assert action == "answer_with_facts"


class TestRegionQuestions:
    """Tests for region question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("region_intent", [
        "question_region_almaty",
        "question_region_astana",
        "question_region_shymkent",
        "question_region_other",
        "question_pickup_office",
        "question_courier_service",
    ])
    def test_region_questions_get_action_in_spin_phase(self, state_machine, region_intent):
        """Region questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(region_intent)

        assert action == "answer_with_facts"


class TestDeliveryService:
    """Tests for delivery/service question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("delivery_intent", [
        "question_delivery",
        "question_delivery_time",
        "question_office_location",
        "question_working_hours",
    ])
    def test_delivery_questions_get_action_in_spin_phase(self, state_machine, delivery_intent):
        """Delivery questions should get answer_with_facts action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(delivery_intent)

        assert action == "answer_with_facts"


class TestConversationalIntents:
    """Tests for conversational/emotional intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("positive_emotion,expected_action", [
        ("compliment", "acknowledge_and_continue"),
        ("joke_response", "acknowledge_and_continue"),
        ("surprise_expression", "acknowledge_and_continue"),
        ("relief_expression", "acknowledge_and_continue"),
    ])
    def test_positive_emotions_get_acknowledge_action(self, state_machine, positive_emotion, expected_action):
        """Positive emotional intents should get acknowledge action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(positive_emotion)

        assert action == expected_action

    @pytest.mark.parametrize("negative_emotion,expected_action", [
        ("frustration_expression", "empathize_and_help"),
        ("skepticism_expression", "address_concerns"),
        ("confusion_expression", "clarify_and_help"),
        ("impatience_expression", "prioritize_response"),
        ("empathy_request", "show_understanding"),
    ])
    def test_negative_emotions_get_empathy_action(self, state_machine, negative_emotion, expected_action):
        """Negative emotional intents should get empathy/help action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(negative_emotion)

        assert action == expected_action


class TestCompanyInfo:
    """Tests for company info question intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("company_intent,expected_action", [
        ("company_info_question", "answer_with_facts"),
        ("experience_question", "answer_with_facts"),
        ("case_study_request", "provide_case_study"),
        ("roi_question", "answer_with_roi"),
    ])
    def test_company_info_questions_get_appropriate_action(self, state_machine, company_intent, expected_action):
        """Company info questions should get appropriate action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(company_intent)

        assert action == expected_action


class TestDialogueControl:
    """Tests for dialogue control intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    @pytest.mark.parametrize("dialogue_intent,expected_action", [
        ("request_brevity", "respond_briefly"),
        ("clarification_request", "clarify_and_continue"),
        ("repeat_request", "repeat_previous"),
        ("example_request", "provide_example"),
        ("summary_request", "provide_summary"),
    ])
    def test_dialogue_control_intents_get_appropriate_action(self, state_machine, dialogue_intent, expected_action):
        """Dialogue control intents should get appropriate action."""
        state_machine.state = "spin_situation"
        action, next_state = state_machine.apply_rules(dialogue_intent)

        assert action == expected_action


class TestSPINPhaseProgression:
    """Tests for SPIN phase progression with new intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    def test_spin_situation_to_problem_with_positive_signal(self, state_machine):
        """Positive signals should advance SPIN from situation to problem."""
        state_machine.state = "spin_situation"
        result = state_machine.process("competitor_dissatisfied")

        assert result["next_state"] == "spin_problem"

    def test_spin_problem_to_implication_with_positive_signal(self, state_machine):
        """Positive signals should advance SPIN from problem to implication."""
        state_machine.state = "spin_problem"
        result = state_machine.process("expansion_planned")

        assert result["next_state"] == "spin_implication"

    def test_spin_implication_to_need_payoff_with_positive_signal(self, state_machine):
        """Positive signals should advance SPIN from implication to need_payoff."""
        state_machine.state = "spin_implication"
        result = state_machine.process("positive_feedback")

        assert result["next_state"] == "spin_need_payoff"

    def test_spin_need_payoff_to_presentation_with_positive_signal(self, state_machine):
        """Positive signals should advance SPIN from need_payoff to presentation."""
        state_machine.state = "spin_need_payoff"
        result = state_machine.process("decision_maker_identified")

        assert result["next_state"] == "presentation"


class TestEndToEndFlows:
    """End-to-end tests for complete dialogue flows with new intents."""

    @pytest.fixture
    def state_machine(self):
        return StateMachine()

    def test_equipment_inquiry_flow(self, state_machine):
        """Test complete flow: greeting -> equipment question -> SPIN."""
        # Start at greeting
        assert state_machine.state == "greeting"

        # Ask about equipment - should advance to spin_situation
        result = state_machine.process("question_equipment_general")
        assert result["next_state"] == "spin_situation"

        # Ask more equipment questions - should stay in spin_situation
        result = state_machine.process("question_pos_monoblock")
        assert result["next_state"] == "spin_situation"
        assert result["action"] == "answer_with_facts"

    def test_hot_lead_flow_with_purchase_intent(self, state_machine):
        """Test hot lead flow: greeting -> purchase intent -> close."""
        # Start at greeting
        assert state_machine.state == "greeting"

        # Client immediately asks for proposal - should go to close
        result = state_machine.process("request_proposal")
        assert result["next_state"] == "close"

        # Client confirms readiness - should go to success
        state_machine.collected_data["contact_info"] = True  # Simulate collected contact
        result = state_machine.process("ready_to_buy")
        # May need more conditions for success, but should stay or advance
        assert result["next_state"] in ["close", "success"]

    def test_objection_handling_flow(self, state_machine):
        """Test objection handling flow through multiple states."""
        state_machine.state = "presentation"

        # New objection type - should go to handle_objection
        result = state_machine.process("objection_roi_doubt")
        assert result["next_state"] == "handle_objection"

        # Agreement in handle_objection - should go to close
        result = state_machine.process("agreement")
        assert result["next_state"] == "close"

    def test_technical_support_flow(self, state_machine):
        """Test technical support flow."""
        state_machine.state = "spin_situation"

        # Client has technical problem
        result = state_machine.process("problem_technical")
        assert result["action"] == "offer_support"
        assert result["next_state"] == "spin_situation"  # Stay in same state

        # Client requests support
        result = state_machine.process("request_technical_support")
        assert result["action"] == "connect_to_support"

    def test_emotional_dialogue_flow(self, state_machine):
        """Test emotional dialogue handling."""
        state_machine.state = "spin_problem"

        # Client expresses frustration
        result = state_machine.process("frustration_expression")
        assert result["action"] == "empathize_and_help"
        assert result["next_state"] == "spin_problem"  # Stay, don't advance

        # Client expresses relief after good answer
        result = state_machine.process("relief_expression")
        assert result["action"] == "acknowledge_and_continue"


class TestConstantsYAMLCategories:
    """Tests to verify constants.yaml categories are properly loaded."""

    def test_objection_category_contains_all_18_objections(self):
        """Verify objection category has all 18 objection types via ConfigLoader."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        objection_intents = config.constants.get("intents", {}).get("categories", {}).get("objection", [])

        expected_objections = [
            "objection_price", "objection_competitor", "objection_no_time",
            "objection_think", "objection_timing", "objection_complexity",
            "objection_trust", "objection_no_need", "objection_risk",
            "objection_team_resistance", "objection_security", "objection_bad_experience",
            "objection_priority", "objection_scale", "objection_change_management",
            "objection_contract_bound", "objection_company_policy", "objection_roi_doubt",
            "rejection"
        ]

        for intent in expected_objections:
            assert intent in objection_intents, f"Missing objection: {intent}"

    def test_positive_category_contains_new_signals(self):
        """Verify positive category has new positive signal intents."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        positive_intents = config.constants.get("intents", {}).get("categories", {}).get("positive", [])

        new_signals = [
            "ready_to_buy", "budget_approved", "decision_maker_identified",
            "urgency_expressed", "competitor_dissatisfied", "expansion_planned",
            "positive_feedback", "internal_champion"
        ]

        for intent in new_signals:
            assert intent in positive_intents, f"Missing positive signal: {intent}"

    def test_equipment_category_exists(self):
        """Verify equipment_questions category exists."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        equipment_intents = config.constants.get("intents", {}).get("categories", {}).get("equipment_questions", [])

        assert equipment_intents is not None
        assert len(equipment_intents) >= 12

    def test_business_scenarios_category_exists(self):
        """Verify business_scenarios category exists."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        scenario_intents = config.constants.get("intents", {}).get("categories", {}).get("business_scenarios", [])

        assert scenario_intents is not None
        assert len(scenario_intents) >= 18
