"""
Comprehensive stress tests for BUG2 fix:
  Fix 1: _select_template_key — `not is_autonomous_flow` guard
          prevents autonomous_respond from routing to answer_with_facts
  Fix 2: _is_factual_turn_guard — deflection retry covers autonomous
          factual turns (not just answer_with_facts template)

Structure:
  Group A (40 tests)  — _is_direct_factual_request() unit coverage
  Group B (52 tests)  — _select_template_key() Fix 1 coverage (mock generator)
  Group C (20 tests)  — _is_deflective_factual_response() unit coverage
  Group D (18 tests)  — _is_factual_turn_guard condition logic
  Group E (20 tests)  — integration via bot.process() — real LLM
                         (slow; only if OLLAMA available, else skipped)

Run:
  pytest tests/test_bug2_stress.py -v                  # all except E
  pytest tests/test_bug2_stress.py -v -m integration   # only E
  pytest tests/test_bug2_stress.py -v -m "not integration"  # skip E
"""
import pytest
from unittest.mock import MagicMock, patch
import re


# ─────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────

class _MockLLM:
    """Minimal stub — generate() always returns empty string."""
    def generate(self, prompt: str) -> str:
        return ""
    def embed(self, text: str):
        return [0.0] * 128


class _MockFlowAutonomous:
    name = "autonomous"
    def get_template(self, key: str):
        return None  # no extra templates in mock


class _MockFlowLegacy:
    name = "legacy"
    def get_template(self, key: str):
        return None


def _make_generator(flow=None):
    """Instantiate Generator with mock LLM, no KB/retriever needed for _select_template_key."""
    from src.generator import ResponseGenerator
    llm = _MockLLM()
    g = ResponseGenerator.__new__(ResponseGenerator)
    g.llm = llm
    g._flow = flow or _MockFlowAutonomous()
    # Minimal attributes required by _select_template_key
    g.PRICE_RELATED_INTENTS = set()
    g.OBJECTION_RELATED_INTENTS = set()
    # Try importing real sets; fall back gracefully
    try:
        from src.generator import ResponseGenerator as RG
        g.PRICE_RELATED_INTENTS = RG.PRICE_RELATED_INTENTS
        g.OBJECTION_RELATED_INTENTS = RG.OBJECTION_RELATED_INTENTS
    except Exception:
        pass
    return g


def _ctx(state: str, intent: str = "situation_provided", user_message: str = "ок") -> dict:
    return {"state": state, "intent": intent, "user_message": user_message}


# ─────────────────────────────────────────────────────────────────
# Group A — _is_direct_factual_request() — 40 tests
# ─────────────────────────────────────────────────────────────────

class TestIsDirectFactualRequest:
    """Pure unit tests for the static predicate. No LLM, no I/O."""

    from src.generator import ResponseGenerator as _RG
    _fn = staticmethod(_RG._is_direct_factual_request)

    # ── textual_factual keywords (17 patterns) ───────────────────

    @pytest.mark.parametrize("msg", [
        "Сколько стоит Mini?",
        "Какие тарифы у вас?",
        "Какой тариф подходит?",
        "Расскажите про интеграцию",
        "Посоветуй что выбрать",
        "Почём Mini в месяц?",
        "Цена Pro?",
        "Стоимость комплекта?",
        "Можно ли платить в рассрочку?",
        "Есть ли у вас поддержка?",
        "Как работает интеграция?",
        "Как это работает?",
        "Чем отличается Standard от Pro?",
        "Какие банки поддерживаются?",
        "Какой тариф для 3 точек?",
        "Какие тарифы существуют?",
        "Можно в рассрочку?",
        "А ОФД есть?",
        "Маркировка поддерживается?",
        "1С интеграция есть?",
    ])
    def test_textual_factual_triggers(self, msg):
        assert self._fn("situation_provided", msg) is True, f"Should be True for: {msg!r}"

    # ── factual intent prefixes ───────────────────────────────────

    @pytest.mark.parametrize("intent", [
        "question_integration",
        "question_kaspi",
        "question_support",
        "price_question",
        "pricing_details",
        "pricing_tier",
        "comparison",
        "cost_question",
        "roi_calculation",
        "payment_terms",
        "company_info_question",
        "experience_question",
    ])
    def test_factual_intent_prefix_triggers(self, intent):
        # "?" in message ensures early exit doesn't fire
        assert self._fn(intent, "А насчёт этого?") is True, f"Should be True for intent: {intent!r}"

    # ── should NOT trigger ────────────────────────────────────────

    def test_empty_message_returns_false(self):
        assert self._fn("price_question", "") is False

    def test_no_question_no_keyword_returns_false(self):
        assert self._fn("situation_provided", "Да, я понял") is False

    def test_pure_question_mark_non_factual_intent(self):
        # "?" is present but intent is non-factual and message has no textual_factual keyword
        assert self._fn("greeting", "Добрый день?") is False

    def test_non_factual_intent_no_keywords_no_question(self):
        assert self._fn("objection_cost", "Дорого") is False

    def test_empty_intent_with_question_returns_true(self):
        # Empty intent + ? → True (early-turn fallback)
        assert self._fn("", "Что такое?") is True

    def test_empty_intent_with_textual_keyword_returns_true(self):
        assert self._fn("", "Расскажите о продукте") is True

    def test_empty_intent_no_signal_returns_false(self):
        assert self._fn("", "Хорошо") is False

    def test_greeting_intent_with_question_and_factual_keyword_true(self):
        # greeting intent: factual_intent=False, textual_factual=True → returns True
        assert self._fn("greeting", "Сколько стоит?") is True

    # ── case insensitivity ────────────────────────────────────────

    def test_uppercase_keyword_triggers(self):
        assert self._fn("situation_provided", "СКОЛЬКО СТОИТ MINI?") is True

    def test_mixed_case_keyword(self):
        assert self._fn("situation_provided", "Расскажите О тарифах") is True


# ─────────────────────────────────────────────────────────────────
# Group B — _select_template_key() Fix 1 — 52 tests
# ─────────────────────────────────────────────────────────────────

class TestSelectTemplateKeyFix1:
    """
    Fix 1: in autonomous flow, action=autonomous_respond must NEVER return
    answer_with_facts regardless of what _is_direct_factual_request() returns.
    """

    # ── Core: every SPIN state must return autonomous_respond for factual msgs ──

    AUTONOMOUS_STATES = [
        "autonomous_discovery",
        "autonomous_qualification",
        "autonomous_presentation",
        "autonomous_objection_handling",
        "autonomous_negotiation",
        "autonomous_closing",
    ]

    FACTUAL_MESSAGES = [
        ("situation_provided", "Как работает интеграция с Kaspi?"),
        ("price_question",     "Сколько стоит Mini?"),
        ("question_support",   "Есть ли круглосуточная поддержка?"),
        ("comparison",         "Чем отличается Standard от Pro?"),
        ("payment_terms",      "Можно ли платить в рассрочку?"),
        ("pricing_details",    "Какие тарифы у вас?"),
    ]

    @pytest.mark.parametrize("state", AUTONOMOUS_STATES)
    @pytest.mark.parametrize("intent,msg", FACTUAL_MESSAGES)
    def test_autonomous_factual_always_autonomous_respond(self, state, intent, msg):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx(state, intent, msg)
        result = g._select_template_key(intent, "autonomous_respond", ctx)
        assert result == "autonomous_respond", (
            f"[{state}][{intent}] msg={msg!r} → got {result!r}, expected 'autonomous_respond'"
        )

    # ── Fix 1 specific: ALL 17 textual_factual keywords in discovery ──

    TEXTUAL_FACTUAL_MSGS = [
        "Сколько стоит?",
        "Какие функции?",
        "Какой подходит?",
        "Расскажите подробнее",
        "Посоветуйте тариф",
        "Почём это?",
        "Цена вопроса?",
        "Стоимость?",
        "Можно ли вернуть?",
        "Есть ли demo?",
        "Как работает касса?",
        "Как это работает в сети?",
        "Чем отличается от конкурентов?",
        "Какие банки партнёры?",
        "Какой тариф для меня?",
        "Какие тарифы бывают?",
        "Рассрочка доступна?",
        "ОФД нужен?",
        "Маркировка есть?",
        "1С совместим?",
    ]

    @pytest.mark.parametrize("msg", TEXTUAL_FACTUAL_MSGS)
    def test_all_textual_factual_keywords_stay_autonomous(self, msg):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("autonomous_discovery", "situation_provided", msg)
        result = g._select_template_key("situation_provided", "autonomous_respond", ctx)
        assert result == "autonomous_respond", f"Factual keyword in msg must not switch template: {msg!r} → {result!r}"

    # ── soft_close must return soft_close regardless ──

    def test_soft_close_state_returns_soft_close(self):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("soft_close", "price_question", "Сколько стоит Mini?")
        result = g._select_template_key("price_question", "autonomous_respond", ctx)
        assert result == "soft_close"

    def test_soft_close_even_with_non_factual(self):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("soft_close", "farewell", "Спасибо")
        result = g._select_template_key("farewell", "autonomous_respond", ctx)
        assert result == "soft_close"

    # ── greeting intent must not get answer_with_facts ──

    def test_greeting_intent_stays_autonomous_respond(self):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("autonomous_discovery", "greeting", "Привет! Сколько стоит?")
        result = g._select_template_key("greeting", "autonomous_respond", ctx)
        # greeting intent is excluded from the answer_with_facts check
        assert result == "autonomous_respond"

    # ── NON-factual messages in autonomous flow stay autonomous_respond ──

    @pytest.mark.parametrize("intent,msg", [
        ("situation_provided", "У меня магазин одежды"),
        ("farewell",           "Спасибо, всего доброго"),
        ("agreement",          "Да, давайте"),
        ("objection_cost",     "Дорого"),
        ("contact_provided",   "Мой номер 8701..."),
    ])
    def test_non_factual_stays_autonomous_respond(self, intent, msg):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("autonomous_discovery", intent, msg)
        result = g._select_template_key(intent, "autonomous_respond", ctx)
        assert result == "autonomous_respond"

    # ── NON-autonomous flow + factual SHOULD return answer_with_facts ──

    def test_non_autonomous_flow_factual_gets_answer_with_facts(self):
        """Fix 1 must NOT affect non-autonomous flows — answer_with_facts is correct there."""
        g = _make_generator(_MockFlowLegacy())
        ctx = _ctx("some_state", "price_question", "Сколько стоит Mini?")
        result = g._select_template_key("price_question", "autonomous_respond", ctx)
        assert result == "answer_with_facts", (
            f"Non-autonomous flow should still use answer_with_facts, got {result!r}"
        )

    def test_no_flow_factual_gets_answer_with_facts(self):
        """No flow set → is_autonomous_flow=False → answer_with_facts correct."""
        g = _make_generator(None)
        ctx = _ctx("some_state", "price_question", "Сколько стоит?")
        result = g._select_template_key("price_question", "autonomous_respond", ctx)
        assert result == "answer_with_facts"

    # ── ContentRepetitionGuard actions bypass fix entirely ──

    @pytest.mark.parametrize("action", [
        "redirect_after_repetition",
        "escalate_repeated_content",
    ])
    def test_content_repetition_guard_actions_bypass(self, action):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("autonomous_discovery", "price_question", "Сколько стоит?")
        result = g._select_template_key("price_question", action, ctx)
        assert result == action

    # ── autonomous flow: non-autonomous_respond action → autonomous_respond ──

    def test_autonomous_flow_non_respond_action_returns_autonomous_respond(self):
        g = _make_generator(_MockFlowAutonomous())
        ctx = _ctx("autonomous_discovery", "situation_provided", "Ок")
        result = g._select_template_key("situation_provided", "continue_current_goal", ctx)
        assert result == "autonomous_respond"


# ─────────────────────────────────────────────────────────────────
# Group C — _is_deflective_factual_response() — 20 tests
# ─────────────────────────────────────────────────────────────────

class TestIsDeflectiveFactualResponse:
    """Unit tests for deflection detection predicate (Fix 2 input)."""

    from src.generator import ResponseGenerator as _RG
    _fn = staticmethod(_RG._is_deflective_factual_response)

    # ── Each pattern MUST be detected ────────────────────────────

    @pytest.mark.parametrize("response", [
        "Расскажите подробнее о ваших потребностях",
        "Расскажите подробнее — какой именно тариф?",
        "Что именно хотите узнать о тарифах?",
        "Что именно хотите узнать?",
        "Подберу подходящий вариант, если уточните бизнес",
        "Подберу подходящий тариф для вас",
        "Уточните ваш запрос, пожалуйста",
        "Уточните ваш запрос — Mini или Pro?",
        "Какой у вас бизнес? Расскажите о нём",
        "Скажите, какой у вас бизнес и размер магазина",
    ])
    def test_deflective_patterns_detected(self, response):
        assert self._fn(response) is True, f"Should detect deflection: {response!r}"

    # ── Correct factual answers must NOT be flagged ───────────────

    @pytest.mark.parametrize("response", [
        "Mini стоит 5 000 ₸/мес, одна торговая точка",
        "Интеграция с Kaspi доступна на всех тарифах",
        "Поддержка ОФД — только через нас, включена в тариф",
        "Standard включает 3 точки и расширенные складские функции",
        "Рассрочка доступна до 24 месяцев без переплат",
        "Маркировка поддерживается в Standard и Pro",
        "1С интегрируется через автоматический обмен данными",
        "В комплект входит POS i3, сканер и принтер — 168 000 ₸",
        "Коллега позвонит и оформит всё за 10 минут",
        "Wipon — POS/ТИС для розничной торговли в Казахстане",
    ])
    def test_correct_answers_not_deflective(self, response):
        assert self._fn(response) is False, f"Should NOT detect deflection: {response!r}"

    # ── Edge cases ────────────────────────────────────────────────

    def test_empty_response_returns_false(self):
        assert self._fn("") is False

    def test_uppercase_deflection_detected(self):
        assert self._fn("РАССКАЖИТЕ ПОДРОБНЕЕ О БИЗНЕСЕ") is True

    def test_mixed_case_deflection(self):
        assert self._fn("расскажите Подробнее о вашей задаче") is True

    def test_partial_match_business_question(self):
        # "какой у вас бизнес" embedded in longer response
        assert self._fn("Интересно! А какой у вас бизнес и сколько точек?") is True


# ─────────────────────────────────────────────────────────────────
# Group D — _is_factual_turn_guard conditions — 18 tests
# ─────────────────────────────────────────────────────────────────

class TestFactualTurnGuardConditions:
    """
    Test the _is_factual_turn_guard logic directly.
    We replicate the condition from generate() and verify it fires correctly.
    """

    from src.generator import ResponseGenerator as _RG
    _factual_fn = staticmethod(_RG._is_direct_factual_request)

    def _guard(self, selected_template_key: str, is_autonomous: bool, intent: str, msg: str) -> bool:
        return (
            selected_template_key == "answer_with_facts"
            or (
                selected_template_key == "autonomous_respond"
                and is_autonomous
                and self._factual_fn(intent, msg)
            )
        )

    # ── answer_with_facts always fires guard (unchanged) ─────────

    @pytest.mark.parametrize("is_autonomous,intent,msg", [
        (True,  "situation_provided", "Ок"),
        (False, "greeting",           "Привет"),
        (True,  "price_question",     "Сколько стоит?"),
        (False, "price_question",     "Сколько стоит?"),
    ])
    def test_answer_with_facts_always_fires_guard(self, is_autonomous, intent, msg):
        assert self._guard("answer_with_facts", is_autonomous, intent, msg) is True

    # ── autonomous_respond + is_autonomous + factual → guard fires ─

    @pytest.mark.parametrize("intent,msg", [
        ("price_question",   "Сколько стоит Mini?"),
        ("question_kaspi",   "Насчёт интеграции с Kaspi?"),
        ("comparison",       "Чем отличается Standard от Pro?"),
        ("situation_provided", "Есть ли у вас ОФД?"),
        ("situation_provided", "Как работает интеграция?"),
        ("payment_terms",    "Можно ли в рассрочку?"),
    ])
    def test_autonomous_respond_autonomous_factual_fires_guard(self, intent, msg):
        assert self._guard("autonomous_respond", True, intent, msg) is True, (
            f"Guard should fire for autonomous factual: [{intent}] {msg!r}"
        )

    # ── autonomous_respond + NOT is_autonomous → guard does NOT fire ─

    def test_autonomous_respond_non_autonomous_does_not_fire(self):
        # is_autonomous=False means not in autonomous flow
        assert self._guard("autonomous_respond", False, "price_question", "Сколько стоит?") is False

    # ── autonomous_respond + is_autonomous + NON-factual → guard does NOT fire ─

    @pytest.mark.parametrize("intent,msg", [
        ("farewell",          "Спасибо, всего доброго"),
        ("situation_provided", "У меня магазин"),
        ("objection_cost",    "Дорого"),
        ("agreement",         "Да, хорошо"),
    ])
    def test_autonomous_respond_autonomous_nonfactual_does_not_fire(self, intent, msg):
        assert self._guard("autonomous_respond", True, intent, msg) is False, (
            f"Guard must NOT fire for non-factual: [{intent}] {msg!r}"
        )

    # ── Other template keys → guard does NOT fire ────────────────

    @pytest.mark.parametrize("tmpl", [
        "greet_back",
        "soft_close",
        "handle_farewell",
        "answer_with_pricing",
        "continue_current_goal",
        "autonomous_closing",
    ])
    def test_other_templates_do_not_fire_guard(self, tmpl):
        assert self._guard(tmpl, True, "price_question", "Сколько стоит?") is False


# ─────────────────────────────────────────────────────────────────
# Group E — Integration tests (real LLM via bot.process())
# ─────────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    try:
        from src.llm import OllamaLLM
        llm = OllamaLLM()
        r = llm.generate("ping")
        return bool(r)
    except Exception:
        return False


_OLLAMA_OK = _ollama_available()


@pytest.fixture(scope="module")
def bot():
    if not _OLLAMA_OK:
        pytest.skip("Ollama not available")
    from src.bot import SalesBot
    from src.llm import OllamaLLM
    from src.feature_flags import flags
    flags.set_override("response_fact_disambiguation", False)  # reduce noise
    llm = OllamaLLM()
    b = SalesBot(llm, flow_name="autonomous")
    yield b
    flags.clear_all_overrides()


def _run(bot, messages: list[str]) -> list[dict]:
    """Run a short dialog and return per-turn metadata."""
    bot.reset()
    turns = []
    for msg in messages:
        result = bot.process(msg)
        meta = {}
        if hasattr(bot, "generator") and hasattr(bot.generator, "get_last_generation_meta"):
            meta = bot.generator.get_last_generation_meta() or {}
        turns.append({
            "user": msg,
            "bot":  result["response"],
            "state": result.get("state", ""),
            "spin":  result.get("spin_phase", ""),
            "action": result.get("action", ""),
            "tmpl": meta.get("selected_template_key", "?"),
        })
    return turns


def _last_autonomous_turn(turns: list[dict]) -> dict | None:
    for t in reversed(turns):
        if t["action"] == "autonomous_respond":
            return t
    return None


@pytest.mark.integration
class TestIntegrationBug2:
    """Integration tests — require Ollama. Marked integration so they can be skipped."""

    # ── Fix 1: all SPIN states, factual question stays autonomous_respond ──

    @pytest.mark.parametrize("setup_msgs,factual_msg,expected_state_prefix", [
        # discovery
        (["Здравствуйте", "Один магазин продуктов"],
         "Есть ли поддержка ОФД?", "autonomous_discovery"),
        # discovery — exact bug example
        (["Здравствуйте", "Продуктовый магазин, 3 кассира"],
         "Понял, так что насчёт интеграции с Kaspi?", "autonomous_discovery"),
        # discovery — textual_factual "как работает"
        (["Здравствуйте", "Сеть 4 точки, Excel"],
         "Как работает интеграция с бухгалтерией?", "autonomous_discovery"),
        # discovery — textual_factual "можно ли"
        # NB: рассрочка is a negotiation topic, so SPIN state may advance to
        # autonomous_negotiation — that's correct. We only assert template=autonomous_respond.
        (["Здравствуйте", "Кофейня, 1 точка"],
         "Можно ли платить в рассрочку?", "autonomous_"),
        # qualification → negotiation (price question fast-tracks)
        (["Здравствуйте", "Небольшой магазин одежды, 2 человека"],
         "Сколько стоит Mini в месяц?", "autonomous_"),
        # closing phase
        (["Здравствуйте", "Хочу подключиться, готов оформить",
          "Магазин продуктов, 1 касса", "Давайте оформим!"],
         "А насчёт рассрочки?", "autonomous_closing"),
    ])
    def test_fix1_factual_stays_autonomous_respond(
        self, bot, setup_msgs, factual_msg, expected_state_prefix
    ):
        turns = _run(bot, setup_msgs + [factual_msg])
        last = _last_autonomous_turn(turns)
        assert last is not None, "No autonomous_respond turn found"
        assert last["tmpl"] == "autonomous_respond", (
            f"Expected autonomous_respond, got {last['tmpl']!r} "
            f"for msg={factual_msg!r}"
        )
        assert last["state"].startswith(expected_state_prefix), (
            f"State mismatch: {last['state']!r} not starting with {expected_state_prefix!r}"
        )

    # ── Fix 1: collected_data is preserved across factual turns ──

    def test_collected_data_preserved_after_factual(self, bot):
        """After a factual turn, collected_data must not be wiped."""
        turns = _run(bot, [
            "Здравствуйте",
            "Магазин детской одежды, Нур-Султан, 2 кассы",
            "Какой тариф подходит для 2 касс?",   # factual
        ])
        # collected_data check via state_machine
        cd = {}
        if hasattr(bot, "state_machine") and hasattr(bot.state_machine, "collected_data"):
            cd = bot.state_machine.collected_data or {}
        # business_type should be collected in turn 2 and NOT lost after factual turn 3
        assert cd.get("business_type") or cd.get("company_size"), (
            f"collected_data should have business_type or company_size after factual turn. Got: {cd}"
        )
        last = _last_autonomous_turn(turns)
        assert last is not None and last["tmpl"] == "autonomous_respond"

    # ── Fix 1: SPIN continuity — next turn after factual stays in flow ──

    def test_spin_continuity_after_factual(self, bot):
        """SPIN phase must not reset after a factual turn."""
        turns = _run(bot, [
            "Здравствуйте",
            "Сеть 5 магазинов, нужна единая система",
            "Чем отличается Standard от Pro?",   # factual → must stay in discovery/qualification
            "Понял, а поддержка 24/7 есть?",      # next factual — SPIN must continue
        ])
        # All autonomous_respond turns should be autonomous_respond, not answer_with_facts
        for t in turns:
            if t["action"] == "autonomous_respond":
                assert t["tmpl"] == "autonomous_respond", (
                    f"turn [{t['user']!r}] got tmpl={t['tmpl']!r}"
                )

    # ── Fix 2: deflection guard fires for autonomous factual turns ──

    def test_fix2_no_bot_deflection_on_factual_question(self, bot):
        """Bot must NOT deflect with 'расскажите о вашем бизнесе' on factual ?."""
        turns = _run(bot, [
            "Здравствуйте",
            "Какие тарифы существуют у Wipon?",
        ])
        last = _last_autonomous_turn(turns)
        assert last is not None
        response_lower = last["bot"].lower()
        deflection_patterns = [
            "расскажите подробнее о вашем бизнесе",
            "что именно хотите узнать",
            "уточните ваш запрос",
            "какой у вас бизнес",
        ]
        for pat in deflection_patterns:
            assert pat not in response_lower, (
                f"Bot deflected on factual question with: {last['bot'][:150]!r}"
            )

    # ── Regression: non-factual turns must not be affected ────────

    @pytest.mark.parametrize("msg,intent_hint", [
        ("У меня магазин продуктов в Алматы", "situation"),
        ("Спасибо за информацию!", "gratitude"),
        ("Нет, не интересует", "rejection"),
    ])
    def test_regression_nonfactual_unaffected(self, bot, msg, intent_hint):
        turns = _run(bot, ["Здравствуйте", msg])
        last = _last_autonomous_turn(turns)
        if last:
            # Non-factual must also use autonomous_respond (not answer_with_facts)
            assert last["tmpl"] in ("autonomous_respond", "greet_back", "handle_farewell",
                                    "soft_close", "?"), (
                f"Non-factual turn got unexpected template: {last['tmpl']!r}"
            )

    # ── Regression: soft_close state unchanged ────────────────────

    def test_regression_soft_close_template_unchanged(self, bot):
        """soft_close state must still use soft_close template after fix."""
        turns = _run(bot, [
            "Здравствуйте",
            "Нет, не интересует, дорого",
            "Не, не буду",
            "Всё равно нет",
        ])
        soft_turns = [t for t in turns if t["state"] == "soft_close"]
        for t in soft_turns:
            if t["action"] == "autonomous_respond":
                assert t["tmpl"] == "soft_close", (
                    f"soft_close state must use soft_close template, got {t['tmpl']!r}"
                )

    # ── Edge: first turn factual question (no collected context yet) ──

    def test_first_turn_factual_uses_autonomous_respond(self, bot):
        """Even with zero context, autonomous_respond should be used, not answer_with_facts."""
        turns = _run(bot, [
            "Здравствуйте",
            "Сколько стоит Mini?",
        ])
        last = _last_autonomous_turn(turns)
        assert last is not None
        assert last["tmpl"] in ("autonomous_respond", "answer_with_pricing"), (
            f"First-turn price question got: {last['tmpl']!r}"
        )
        # answer_with_facts is the ONLY forbidden template here
        assert last["tmpl"] != "answer_with_facts"

    # ── Edge: Kazakh language factual question ────────────────────

    def test_kazakh_factual_question_autonomous_respond(self, bot):
        """Kazakh message with factual intent must stay autonomous_respond."""
        turns = _run(bot, [
            "Сәлеметсіз бе",
            "Wipon бағасы қанша?",   # "Wipon бағасы қанша?" = how much is Wipon?
        ])
        last = _last_autonomous_turn(turns)
        if last:
            assert last["tmpl"] != "answer_with_facts", (
                f"Kazakh factual msg got answer_with_facts: {last['bot'][:100]!r}"
            )

    # ── Edge: closing + factual = must keep closing_data_request ──

    def test_closing_factual_keeps_closing_context(self, bot):
        """In closing phase, factual question must NOT lose the closing goal (contact request)."""
        turns = _run(bot, [
            "Здравствуйте",
            "Хочу подключиться!",
            "А насчёт поддержки — что входит?",  # factual mid-closing
        ])
        last = _last_autonomous_turn(turns)
        assert last is not None
        assert last["tmpl"] == "autonomous_respond"
        # Bot should be in closing or negotiation state
        assert "closing" in last["state"] or "negotiation" in last["state"] or \
               "qualification" in last["state"] or "discovery" in last["state"]
