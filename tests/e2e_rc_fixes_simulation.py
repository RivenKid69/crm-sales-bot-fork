#!/usr/bin/env python3
"""
E2E Simulation: RC1-RC6 Fix Verification.

Targeted live-bot scenarios to verify all 6 root causes of "bot answers off-topic"
are fixed end-to-end through the full pipeline (LLM classifier → blackboard →
retrieval → template → generator).

RC1: Specificity factor — specific topics beat umbrella "tariffs" in retrieval
RC2: No hardcoded prices — bot uses retrieved KB facts, not template placeholders
RC3: Step 0 in objection templates — embedded questions get answered
RC4: Payment-term patterns → price_question secondary intent
RC5: Expanded demo_request patterns (видео, интерфейс, посмотреть)
RC6: advance_request intent + SKIP_RETRIEVAL bypass by secondary intents

Usage:
  python tests/e2e_rc_fixes_simulation.py                # all scenarios
  python tests/e2e_rc_fixes_simulation.py --scenario rc1  # single RC
  python tests/e2e_rc_fixes_simulation.py --compact       # summary only
  python tests/e2e_rc_fixes_simulation.py --json out.json # save JSON
"""

import sys
import os
import re
import time
import json
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot


# ═══════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TurnSpec:
    """A single scripted user message + expected outcome."""
    message: str
    description: str = ""
    # What the bot response SHOULD contain (case-insensitive substrings)
    expect_any: List[str] = field(default_factory=list)
    # What the bot response SHOULD NOT contain
    expect_not: List[str] = field(default_factory=list)
    # Expected action/template name (substring match on bot.last_action)
    expect_action: Optional[str] = None
    # Expected action should NOT be this
    expect_not_action: Optional[str] = None
    # Check that retrieved_facts are non-empty (RC6 bypass test)
    expect_retrieval: Optional[bool] = None

@dataclass
class ScenarioSpec:
    """A multi-turn scripted scenario."""
    name: str
    rc_tag: str  # e.g. "rc1", "rc3", "rc4+rc6"
    description: str
    # Warm-up turns to put bot into right state (no checks)
    warmup: List[TurnSpec] = field(default_factory=list)
    # Test turns (with checks)
    turns: List[TurnSpec] = field(default_factory=list)

@dataclass
class TurnResult:
    turn_num: int
    user_message: str
    bot_response: str
    intent: str
    action: str
    state: str
    description: str
    elapsed_ms: float
    # Check results
    checks: Dict[str, str] = field(default_factory=dict)  # check_name -> PASS/FAIL
    check_details: Dict[str, str] = field(default_factory=dict)  # details on failures

@dataclass
class ScenarioResult:
    name: str
    rc_tag: str
    turns: List[TurnResult] = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    total_elapsed_s: float = 0.0
    verdict: str = ""  # PASS / FAIL / PARTIAL


# ═══════════════════════════════════════════════════════════════════
# Scenarios
# ═══════════════════════════════════════════════════════════════════

# ---------- RC1: Specificity factor ----------

SCENARIO_RC1_INTEGRATION_VS_TARIFFS = ScenarioSpec(
    name="RC1: Вопрос об интеграции → НЕ тарифы",
    rc_tag="rc1",
    description=(
        "Клиент спрашивает про интеграцию с Kaspi/1С. "
        "До фикса umbrella-тема 'tariffs' побеждала из-за generic keywords. "
        "После RC1 specificity factor должен отдать приоритет конкретной теме."
    ),
    warmup=[
        TurnSpec(message="Здравствуйте, у меня магазин одежды в Алматы, 3 точки."),
        TurnSpec(message="Да, интересно посмотреть на ваш продукт для автоматизации."),
    ],
    turns=[
        TurnSpec(
            message="А как у вас с интеграцией с Каспи? Можно ли подключить Kaspi QR?",
            description="Конкретный вопрос об интеграции — НЕ должен получить тарифы",
            expect_any=["kaspi", "интеграц", "подключ", "qr"],
            expect_not=["тариф", "стоимость", "тенге", "₸"],
        ),
        TurnSpec(
            message="А с 1С работает? У нас 1С:Управление торговлей.",
            description="Вопрос об интеграции с 1С",
            expect_any=["1с", "интеграц", "учёт", "синхрониз"],
        ),
    ],
)

SCENARIO_RC1_SPECIFIC_FEATURE = ScenarioSpec(
    name="RC1: POS-функции → НЕ зонтичный tariffs",
    rc_tag="rc1",
    description=(
        "Вопрос о конкретных POS-функциях (сканер, чеки, возвраты). "
        "Не должен триггерить tariffs retrieval."
    ),
    warmup=[
        TurnSpec(message="Салем! Хочу узнать о вашей кассовой программе."),
    ],
    turns=[
        TurnSpec(
            message="Как у вас со сканером штрих-кодов? Поддерживаете ли вы ЕГАИС?",
            description="Конкретная POS-функция — не тарифы",
            expect_any=["штрих", "сканер", "код", "егаис", "маркировк"],
        ),
        TurnSpec(
            message="А чеки можно печатать? Какие кассовые аппараты поддерживаете?",
            description="Кассовые аппараты — не тарифы",
            expect_any=["чек", "касс", "печат", "аппарат", "фискал"],
        ),
    ],
)

# ---------- RC2: No hardcoded prices ----------

SCENARIO_RC2_NO_HARDCODED_PRICES = ScenarioSpec(
    name="RC2: Ценовой ответ без hardcoded цен",
    rc_tag="rc2",
    description=(
        "Прямой вопрос о ценах. Бот должен ответить из KB (retrieved_facts), "
        "а НЕ из зашитых в шаблоне примерных цифр. "
        "Проверяем что нет '4 990', '14 990', '990 ₸/мес' — это были примеры."
    ),
    warmup=[
        TurnSpec(message="Добрый день, у меня продуктовый магазин, ищу кассовую программу."),
        TurnSpec(message="Расскажите подробнее что умеет ваша система."),
    ],
    turns=[
        TurnSpec(
            message="Сколько стоит ваша программа?",
            description="Прямой ценовой вопрос — ответ должен быть из KB",
            expect_any=["тариф", "цен", "стоим", "₸", "тенге", "оплат"],
            expect_not=["4 990", "14 990", "990 ₸/мес"],
            expect_action="answer_with_pricing",
        ),
        TurnSpec(
            message="А есть рассрочка или помесячная оплата?",
            description="Детали оплаты — тоже из KB",
            expect_any=["рассрочк", "оплат", "месяц", "помесячн"],
        ),
    ],
)

# ---------- RC3: Step 0 in objection templates ----------

SCENARIO_RC3_OBJECTION_WITH_QUESTION = ScenarioSpec(
    name="RC3: Возражение + встроенный вопрос → шаг 0 ответ",
    rc_tag="rc3",
    description=(
        "Клиент возражает ('дорого') и одновременно задаёт вопрос ('а рассрочка есть?'). "
        "До RC3 бот игнорировал встроенный вопрос. "
        "После RC3 шаблон содержит шаг 0 — ответить на вопрос."
    ),
    warmup=[
        TurnSpec(message="Здравствуйте, мне порекомендовали ваш Wipon."),
        TurnSpec(message="У меня небольшой магазин, 1 точка, нужна касса."),
        TurnSpec(message="Расскажите что у вас есть для маленького магазина."),
    ],
    turns=[
        TurnSpec(
            message="Дорого! А рассрочка есть?",
            description="Возражение 'дорого' + вопрос о рассрочке → должен упомянуть рассрочку",
            expect_any=["рассрочк", "оплат", "помесячн", "частями"],
        ),
        TurnSpec(
            message="Не уверен что нам это нужно. А демо можно посмотреть?",
            description="Возражение 'не нужно' + вопрос о демо → должен упомянуть демо",
            expect_any=["демо", "показ", "посмотр", "попроб", "тест"],
        ),
    ],
)

SCENARIO_RC3_OBJECTION_COMPETITOR_WITH_Q = ScenarioSpec(
    name="RC3: Возражение 'конкурент' + вопрос об отличиях",
    rc_tag="rc3",
    description=(
        "Клиент говорит что использует конкурента и одновременно спрашивает "
        "чем Wipon лучше. Шаг 0 должен помочь ответить на конкретный вопрос."
    ),
    warmup=[
        TurnSpec(message="Привет, у нас уже стоит другая кассовая программа."),
        TurnSpec(message="Пользуемся iiko, но думаем сменить."),
    ],
    turns=[
        TurnSpec(
            message="Зачем мне менять iiko на ваш Wipon? Что у вас есть чего нет у них?",
            description="Возражение 'конкурент' + конкретный вопрос о преимуществах",
            expect_any=["преимущест", "отлич", "функц", "wipon", "возможност"],
        ),
    ],
)

# ---------- RC4: Payment-term patterns → price_question ----------

SCENARIO_RC4_INSTALLMENT = ScenarioSpec(
    name="RC4: 'рассрочка'/'частями' → price_question secondary",
    rc_tag="rc4",
    description=(
        "Клиент упоминает рассрочку, оплату частями, помесячную оплату. "
        "RC4 добавляет эти паттерны → secondary intent price_question → "
        "PriceQuestionSource → ценовой ответ из KB."
    ),
    warmup=[
        TurnSpec(message="Добрый день! У меня аптека, ищу кассу."),
        TurnSpec(message="Расскажите что умеет ваша система."),
    ],
    turns=[
        TurnSpec(
            message="А можно в рассрочку оплатить?",
            description="'рассрочку' → price_question secondary → ценовой ответ",
            expect_any=["рассрочк", "оплат", "тариф", "цен", "₸", "тенге", "помесячн"],
        ),
        TurnSpec(
            message="Можно частями платить? Без переплаты?",
            description="'частями' + 'переплата' → price_question secondary",
            expect_any=["частями", "рассрочк", "оплат", "переплат", "тариф", "цен"],
        ),
        TurnSpec(
            message="А ежемесячный платёж какой будет?",
            description="'ежемесячный' → price_question secondary",
            expect_any=["ежемесячн", "помесячн", "оплат", "тариф", "₸", "тенге", "цен"],
        ),
    ],
)

# ---------- RC5: Expanded demo_request ----------

SCENARIO_RC5_DEMO_PATTERNS = ScenarioSpec(
    name="RC5: Расширенные demo-паттерны (видео, интерфейс, посмотреть)",
    rc_tag="rc5",
    description=(
        "Клиент хочет увидеть продукт в разных формулировках: "
        "'покажите видео', 'как выглядит интерфейс', 'можно на примере посмотреть'. "
        "RC5 расширяет demo_request → бот предлагает демо."
    ),
    warmup=[
        TurnSpec(message="Здравствуйте, интересует ваша программа для магазина."),
        TurnSpec(message="У меня строительный магазин, 2 точки."),
    ],
    turns=[
        TurnSpec(
            message="А можно посмотреть на примере как это работает?",
            description="'посмотреть на примере' → demo_request",
            expect_any=["демо", "показ", "посмотр", "попроб", "пример", "видео"],
        ),
        TurnSpec(
            message="Есть какое-нибудь видео вашей программы?",
            description="'видео' → demo_request",
            expect_any=["видео", "демо", "показ", "посмотр"],
        ),
        TurnSpec(
            message="Как выглядит ваш интерфейс? Покажите скриншоты.",
            description="'интерфейс' + 'скриншот' → demo_request",
            expect_any=["интерфейс", "демо", "показ", "скриншот", "экран"],
        ),
    ],
)

# ---------- RC6: advance_request + SKIP_RETRIEVAL bypass ----------

SCENARIO_RC6_ADVANCE_WITH_GREETING = ScenarioSpec(
    name="RC6a: 'что ещё можете' после greeting → retrieval НЕ скипается",
    rc_tag="rc6",
    description=(
        "Клиент здоровается и сразу спрашивает 'что ещё можете предложить'. "
        "Greeting → SKIP_RETRIEVAL, но advance_request secondary → bypass → KB retrieval."
    ),
    warmup=[],
    turns=[
        TurnSpec(
            message="Привет! А что вы вообще можете предложить?",
            description="greeting + advance_request → bypass SKIP_RETRIEVAL",
            expect_any=["wipon", "касс", "программ", "магазин", "функц", "возможност", "продукт", "автоматиз", "торгов"],
            expect_retrieval=True,
        ),
    ],
)

SCENARIO_RC6_ADVANCE_MIDCONV = ScenarioSpec(
    name="RC6b: 'что ещё' / 'дальше' в середине разговора",
    rc_tag="rc6",
    description=(
        "Клиент в середине разговора говорит 'а что ещё?' или 'дальше'. "
        "advance_request secondary должен триггерить KB retrieval."
    ),
    warmup=[
        TurnSpec(message="Добрый день! У меня цветочный магазин."),
        TurnSpec(message="Нужна программа для учёта товаров и продаж."),
        TurnSpec(message="Расскажите основные возможности."),
    ],
    turns=[
        TurnSpec(
            message="Ок, понял. А что ещё можете предложить?",
            description="'что ещё' → advance_request → new KB content",
            expect_any=["wipon", "функц", "возможност", "интеграц", "аналитик", "отчёт", "склад", "маркировк"],
        ),
        TurnSpec(
            message="Дальше. Что ещё есть интересного?",
            description="'дальше' → advance_request",
            expect_any=["wipon", "функц", "возможност", "интеграц", "аналитик", "отчёт", "склад", "касс"],
        ),
    ],
)

SCENARIO_RC6_SMALL_TALK_WITH_QUESTION = ScenarioSpec(
    name="RC6c: small_talk + 'сколько стоит' → bypass SKIP_RETRIEVAL",
    rc_tag="rc6",
    description=(
        "Клиент начинает с small_talk ('спасибо за информацию') и тут же "
        "спрашивает цену. small_talk → SKIP_RETRIEVAL, но price_question secondary → bypass."
    ),
    warmup=[
        TurnSpec(message="Здравствуйте, расскажите о вашей программе для магазина."),
        TurnSpec(message="Хорошо, спасибо за информацию."),
    ],
    turns=[
        TurnSpec(
            message="Ладно, спасибо. А сколько всё это стоит?",
            description="gratitude + price_question → bypass → pricing from KB",
            expect_any=["тариф", "цен", "стоим", "₸", "тенге", "оплат"],
            expect_retrieval=True,
        ),
    ],
)

# ---------- RC6d: Short message threshold ----------

SCENARIO_RC6D_SHORT_MESSAGES = ScenarioSpec(
    name="RC6d: Короткие сообщения (5-9 символов) проходят secondary detection",
    rc_tag="rc6",
    description=(
        "До RC6d порог был 10 символов — короткие сообщения не проверялись. "
        "После RC6d порог 5 — 'цена?' (5 символов) должен сработать."
    ),
    warmup=[
        TurnSpec(message="Привет, расскажите о вашем продукте."),
        TurnSpec(message="Ок, интересно."),
    ],
    turns=[
        TurnSpec(
            message="цена?",
            description="5 символов — должен пройти порог и получить ценовой ответ",
            expect_any=["тариф", "цен", "стоим", "₸", "тенге", "оплат"],
        ),
        TurnSpec(
            message="видео?",
            description="6 символов — тоже проходит порог",
            expect_any=["видео", "демо", "показ", "посмотр"],
        ),
    ],
)

# ---------- Combined / Cross-RC Edge Cases ----------

SCENARIO_CROSS_OBJECTION_INSTALLMENT = ScenarioSpec(
    name="RC3+RC4: Возражение + рассрочка (cross-RC)",
    rc_tag="rc3+rc4",
    description=(
        "Клиент возражает по цене И спрашивает про рассрочку в одном сообщении. "
        "RC3: шаг 0 отвечает на вопрос. RC4: рассрочка → price_question secondary."
    ),
    warmup=[
        TurnSpec(message="Добрый день, мне нужна кассовая программа для магазина."),
        TurnSpec(message="У нас 1 точка, небольшой продуктовый."),
        TurnSpec(message="Сколько стоит ваша программа?"),
    ],
    turns=[
        TurnSpec(
            message="Слишком дорого для нас! А в рассрочку можно? Без переплаты?",
            description="RC3: objection(price) + RC4: рассрочка → ценовой ответ + рассрочка",
            expect_any=["рассрочк", "оплат", "переплат", "частями", "помесячн"],
        ),
    ],
)

SCENARIO_CROSS_GREETING_DEMO = ScenarioSpec(
    name="RC5+RC6: greeting + 'покажите видео' (cross-RC)",
    rc_tag="rc5+rc6",
    description=(
        "Клиент здоровается и сразу просит видео. "
        "RC5: demo_request видео. RC6: bypass SKIP_RETRIEVAL."
    ),
    warmup=[],
    turns=[
        TurnSpec(
            message="Привет! А есть видео вашей программы? Хочу посмотреть.",
            description="greeting + demo_request(видео) → bypass + demo response",
            expect_any=["видео", "демо", "показ", "посмотр"],
        ),
    ],
)

SCENARIO_CROSS_ADVANCE_OBJECTION = ScenarioSpec(
    name="RC3+RC6: Возражение + 'а что ещё есть' (cross-RC)",
    rc_tag="rc3+rc6",
    description=(
        "Клиент возражает 'не уверен' и тут же спрашивает 'а что ещё есть'. "
        "RC3: шаг 0 отвечает. RC6: advance_request → KB retrieval."
    ),
    warmup=[
        TurnSpec(message="Здравствуйте, расскажите о вашей кассовой программе."),
        TurnSpec(message="Ну, пока не уверен что нам это подходит."),
    ],
    turns=[
        TurnSpec(
            message="Не знаю, не убедили пока. А что ещё можете предложить?",
            description="Objection + advance_request → step 0 + KB content",
            expect_any=["wipon", "функц", "возможност", "предлож", "аналитик", "интеграц", "преимущест"],
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# All scenarios
# ═══════════════════════════════════════════════════════════════════

ALL_SCENARIOS = [
    # RC1
    SCENARIO_RC1_INTEGRATION_VS_TARIFFS,
    SCENARIO_RC1_SPECIFIC_FEATURE,
    # RC2
    SCENARIO_RC2_NO_HARDCODED_PRICES,
    # RC3
    SCENARIO_RC3_OBJECTION_WITH_QUESTION,
    SCENARIO_RC3_OBJECTION_COMPETITOR_WITH_Q,
    # RC4
    SCENARIO_RC4_INSTALLMENT,
    # RC5
    SCENARIO_RC5_DEMO_PATTERNS,
    # RC6
    SCENARIO_RC6_ADVANCE_WITH_GREETING,
    SCENARIO_RC6_ADVANCE_MIDCONV,
    SCENARIO_RC6_SMALL_TALK_WITH_QUESTION,
    SCENARIO_RC6D_SHORT_MESSAGES,
    # Cross-RC
    SCENARIO_CROSS_OBJECTION_INSTALLMENT,
    SCENARIO_CROSS_GREETING_DEMO,
    SCENARIO_CROSS_ADVANCE_OBJECTION,
]

RC_SCENARIO_MAP = {}
for s in ALL_SCENARIOS:
    for tag in s.rc_tag.split("+"):
        tag = tag.strip()
        RC_SCENARIO_MAP.setdefault(tag, []).append(s)


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

def run_scenario(scenario: ScenarioSpec, compact: bool = False) -> ScenarioResult:
    """Run a single scenario through the live bot."""
    print(f"\n{'=' * 80}")
    print(f"  SCENARIO: {scenario.name}")
    print(f"  RC: {scenario.rc_tag}")
    print(f"  {scenario.description[:120]}...")
    print(f"  Warmup: {len(scenario.warmup)} turns | Test: {len(scenario.turns)} turns")
    print(f"{'=' * 80}")

    llm = OllamaLLM()
    bot = SalesBot(llm=llm, flow_name="autonomous", enable_tracing=True)

    result = ScenarioResult(name=scenario.name, rc_tag=scenario.rc_tag)
    start_total = time.time()

    # ── Warmup turns (no checks) ──
    for i, turn in enumerate(scenario.warmup):
        t0 = time.time()
        try:
            proc = bot.process(turn.message)
            resp = proc.get("response", "[NO RESPONSE]")
        except Exception as e:
            resp = f"[ERROR: {e}]"
        elapsed = (time.time() - t0) * 1000

        if not compact:
            print(f"\n  [warmup {i+1}] CLIENT: {turn.message[:80]}")
            print(f"            BOT:    {resp[:120]}...")
            print(f"            state={bot.state_machine.state}  intent={bot.last_intent}  action={bot.last_action}  {elapsed:.0f}ms")

    # ── Test turns (with checks) ──
    for i, turn in enumerate(scenario.turns):
        turn_num = i + 1
        t0 = time.time()
        try:
            proc = bot.process(turn.message)
            resp = proc.get("response", "[NO RESPONSE]")
            intent = proc.get("intent", "?")
            action = proc.get("action", "?")
            state = proc.get("state", "?")
        except Exception as e:
            resp = f"[ERROR: {e}]"
            intent = action = state = "error"
        elapsed = (time.time() - t0) * 1000

        # Actual action from bot (more reliable than process result)
        actual_action = bot.last_action or action

        checks = {}
        check_details = {}
        resp_lower = resp.lower()

        # Check: expect_any — at least one keyword present
        if turn.expect_any:
            found = [kw for kw in turn.expect_any if kw.lower() in resp_lower]
            if found:
                checks["expect_any"] = "PASS"
                check_details["expect_any"] = f"found: {found}"
            else:
                checks["expect_any"] = "FAIL"
                check_details["expect_any"] = f"NONE of {turn.expect_any} found in response"

        # Check: expect_not — none of these should appear
        if turn.expect_not:
            bad_found = [kw for kw in turn.expect_not if kw.lower() in resp_lower]
            if bad_found:
                checks["expect_not"] = "FAIL"
                check_details["expect_not"] = f"UNWANTED found: {bad_found}"
            else:
                checks["expect_not"] = "PASS"
                check_details["expect_not"] = f"none of {turn.expect_not} found (good)"

        # Check: expect_action
        if turn.expect_action:
            if turn.expect_action.lower() in (actual_action or "").lower():
                checks["expect_action"] = "PASS"
                check_details["expect_action"] = f"action={actual_action}"
            else:
                checks["expect_action"] = "FAIL"
                check_details["expect_action"] = f"expected '{turn.expect_action}' in action, got '{actual_action}'"

        # Check: expect_not_action
        if turn.expect_not_action:
            if turn.expect_not_action.lower() in (actual_action or "").lower():
                checks["expect_not_action"] = "FAIL"
                check_details["expect_not_action"] = f"action '{actual_action}' should NOT contain '{turn.expect_not_action}'"
            else:
                checks["expect_not_action"] = "PASS"

        # Check: expect_retrieval
        if turn.expect_retrieval is not None:
            # Look for retrieved_facts in the decision trace
            dt = bot.get_last_decision_trace()
            has_retrieval = False
            if dt and dt.response:
                trace_dict = dt.to_dict()
                resp_trace = trace_dict.get("response", {})
                # Check if template_vars has non-empty retrieved_facts
                tvars = resp_trace.get("template_vars", {})
                rf = tvars.get("retrieved_facts", "")
                if rf and len(rf.strip()) > 10:
                    has_retrieval = True
            if turn.expect_retrieval and has_retrieval:
                checks["expect_retrieval"] = "PASS"
                check_details["expect_retrieval"] = f"retrieved_facts present ({len(rf)} chars)"
            elif turn.expect_retrieval and not has_retrieval:
                checks["expect_retrieval"] = "FAIL"
                check_details["expect_retrieval"] = "expected retrieval but retrieved_facts empty"
            elif not turn.expect_retrieval and has_retrieval:
                checks["expect_retrieval"] = "FAIL"
                check_details["expect_retrieval"] = "expected NO retrieval but got facts"
            else:
                checks["expect_retrieval"] = "PASS"

        # Record result
        turn_result = TurnResult(
            turn_num=turn_num,
            user_message=turn.message,
            bot_response=resp,
            intent=intent,
            action=actual_action,
            state=state,
            description=turn.description,
            elapsed_ms=elapsed,
            checks=checks,
            check_details=check_details,
        )
        result.turns.append(turn_result)

        # Update counters
        for check_name, status in checks.items():
            result.total_checks += 1
            if status == "PASS":
                result.passed_checks += 1
            else:
                result.failed_checks += 1

        # Print
        pass_str = " ".join(
            f"{'✓' if v == 'PASS' else '✗'}{k}"
            for k, v in checks.items()
        )
        status_icon = "✓" if all(v == "PASS" for v in checks.values()) else "✗"

        print(f"\n  [{status_icon}] TURN {turn_num}: {turn.description}")
        print(f"      CLIENT: {turn.message}")
        print(f"      BOT:    {resp[:200]}{'...' if len(resp) > 200 else ''}")
        print(f"      state={state}  intent={intent}  action={actual_action}  {elapsed:.0f}ms")
        print(f"      checks: {pass_str}")

        # Print failures in detail
        for ck, st in checks.items():
            if st == "FAIL":
                print(f"      *** FAIL {ck}: {check_details.get(ck, '')}")

    result.total_elapsed_s = time.time() - start_total

    if result.failed_checks == 0:
        result.verdict = "PASS"
    elif result.passed_checks > 0:
        result.verdict = "PARTIAL"
    else:
        result.verdict = "FAIL"

    print(f"\n  {'─' * 70}")
    v_icon = {"PASS": "✓", "FAIL": "✗", "PARTIAL": "~"}.get(result.verdict, "?")
    print(f"  [{v_icon}] VERDICT: {result.verdict} — "
          f"{result.passed_checks}/{result.total_checks} checks passed  "
          f"({result.total_elapsed_s:.1f}s)")
    print(f"  {'─' * 70}")

    return result


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="E2E RC1-RC6 fix verification")
    parser.add_argument("--scenario", "-s", type=str, default=None,
                        help="Filter: 'rc1', 'rc2', ..., 'rc6', or scenario index (0-based)")
    parser.add_argument("--compact", "-c", action="store_true", help="Summary only")
    parser.add_argument("--json", "-j", type=str, default=None, help="Save results to JSON")
    args = parser.parse_args()

    # Filter scenarios
    scenarios = ALL_SCENARIOS
    if args.scenario:
        s = args.scenario.lower()
        if s.startswith("rc"):
            scenarios = RC_SCENARIO_MAP.get(s, [])
            if not scenarios:
                print(f"No scenarios for tag '{s}'. Available: {list(RC_SCENARIO_MAP.keys())}")
                sys.exit(1)
        elif s.isdigit():
            idx = int(s)
            if 0 <= idx < len(ALL_SCENARIOS):
                scenarios = [ALL_SCENARIOS[idx]]
            else:
                print(f"Index {idx} out of range (0-{len(ALL_SCENARIOS)-1})")
                sys.exit(1)

    print(f"\n{'═' * 80}")
    print(f"  E2E RC1-RC6 FIX VERIFICATION")
    print(f"  Scenarios: {len(scenarios)} | Flow: autonomous")
    print(f"{'═' * 80}")

    results: List[ScenarioResult] = []
    total_start = time.time()

    for scenario in scenarios:
        try:
            result = run_scenario(scenario, compact=args.compact)
            results.append(result)
        except Exception as e:
            print(f"\n  *** SCENARIO ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append(ScenarioResult(
                name=scenario.name, rc_tag=scenario.rc_tag,
                verdict="ERROR",
            ))

    total_elapsed = time.time() - total_start

    # ── Summary ──
    print(f"\n\n{'═' * 80}")
    print(f"  SUMMARY")
    print(f"{'═' * 80}")

    total_checks = sum(r.total_checks for r in results)
    total_passed = sum(r.passed_checks for r in results)
    total_failed = sum(r.failed_checks for r in results)

    for r in results:
        v_icon = {"PASS": "✓", "FAIL": "✗", "PARTIAL": "~", "ERROR": "!"}.get(r.verdict, "?")
        print(f"  [{v_icon}] {r.rc_tag:>8}  {r.name:<55}  {r.passed_checks}/{r.total_checks} checks  {r.total_elapsed_s:.1f}s")

    print(f"\n  {'─' * 70}")
    passed_scenarios = sum(1 for r in results if r.verdict == "PASS")
    print(f"  TOTAL: {passed_scenarios}/{len(results)} scenarios PASS, "
          f"{total_passed}/{total_checks} checks PASS, "
          f"{total_failed} FAIL")
    print(f"  Time: {total_elapsed:.1f}s")

    # Per-RC summary
    rc_results: Dict[str, List[str]] = {}
    for r in results:
        for tag in r.rc_tag.split("+"):
            tag = tag.strip()
            rc_results.setdefault(tag, []).append(r.verdict)

    print(f"\n  Per-RC:")
    for rc in sorted(rc_results.keys()):
        verdicts = rc_results[rc]
        all_pass = all(v == "PASS" for v in verdicts)
        icon = "✓" if all_pass else "✗"
        print(f"    [{icon}] {rc}: {verdicts}")

    print(f"{'═' * 80}\n")

    # ── Save JSON ──
    if args.json:
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_scenarios": len(results),
            "passed_scenarios": passed_scenarios,
            "total_checks": total_checks,
            "passed_checks": total_passed,
            "failed_checks": total_failed,
            "total_elapsed_s": total_elapsed,
            "scenarios": [],
        }
        for r in results:
            s_data = {
                "name": r.name,
                "rc_tag": r.rc_tag,
                "verdict": r.verdict,
                "total_checks": r.total_checks,
                "passed_checks": r.passed_checks,
                "failed_checks": r.failed_checks,
                "elapsed_s": r.total_elapsed_s,
                "turns": [],
            }
            for t in r.turns:
                s_data["turns"].append({
                    "turn": t.turn_num,
                    "description": t.description,
                    "user_message": t.user_message,
                    "bot_response": t.bot_response[:500],
                    "intent": t.intent,
                    "action": t.action,
                    "state": t.state,
                    "elapsed_ms": t.elapsed_ms,
                    "checks": t.checks,
                    "check_details": t.check_details,
                })
            output["scenarios"].append(s_data)

        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  Results saved to {args.json}")

    # Exit code
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
