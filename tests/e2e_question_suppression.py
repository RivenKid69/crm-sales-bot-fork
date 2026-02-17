#!/usr/bin/env python3
"""
E2E Test: Question Suppression (BUG #9) — Enhanced Field Simulation.

Full pipeline verification of the 3-level question suppression system:
  density == 0 → mandatory (bot MUST ask a question)
  density == 1 → optional  (bot MAY ask a question)
  density >= 2 → suppress  (bot MUST NOT ask questions)

Tests the 5 defensive layers end-to-end:
  Layer 1: SYSTEM_PROMPT — no "→ Один вопрос"
  Layer 2: {question_instruction} in templates — dynamic instruction
  Layer 3: hidden missing_data/available_questions when suppressed
  Layer 4: ResponseDirectives override (question_mode)
  Layer 5: Post-processing _strip_trailing_question

All scenarios run through AUTONOMOUS flow exclusively.

Scenarios:
  1. QUESTION_FLOOD — client asks 5 questions in a row → bot stops asking
  2. MIXED_DIALOG — alternating questions/info → optional mode works
  3. RECOVERY — suppress → client stops asking → bot resumes questions
  4. LONG_OSCILLATING — 20-turn dialog with multiple question/info waves
  5. AUTONOMOUS_FULL — 12-turn realistic dialog with question patterns
  6. FRUSTRATED_CLIENT — aggressive questioning mixed with complaints
  7. TOPIC_JUMPER — client switches topics unpredictably every 1-2 turns
  8. OBJECTION_QUESTION_MIX — objections interleaved with questions
  9. DOUBLE_WAVE — two question floods separated by info recovery
 10. EDGE_CASES — short questions, multi-question messages, embedded questions

Usage:
  python tests/e2e_question_suppression.py                        # all scenarios
  python tests/e2e_question_suppression.py --scenario flood       # single scenario
  python tests/e2e_question_suppression.py --compact              # summary only
  python tests/e2e_question_suppression.py --json results.json    # save JSON
"""

import sys
import os
import re
import time
import json
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot
from src.context_envelope import ContextEnvelopeBuilder
from src.yaml_config.constants import INTENT_CATEGORIES, get_persona_question_thresholds


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

ALL_QUESTION_INTENTS = set(INTENT_CATEGORIES.get("all_questions", []))


def compute_question_density(intent_history: List[str], current_intent: Optional[str], window: int = 5) -> int:
    """Mirror of ContextEnvelopeBuilder._compute_question_density for validation."""
    return ContextEnvelopeBuilder._compute_question_density(intent_history, current_intent, window)


def count_questions_in_text(text: str) -> int:
    """Count question sentences in text."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return sum(1 for s in sentences if s.rstrip().endswith('?'))


def ends_with_question(text: str) -> bool:
    """Check if text ends with a question mark (trailing question)."""
    stripped = text.rstrip()
    return stripped.endswith('?')


def last_sentence_is_question(text: str) -> bool:
    """Check if the last sentence specifically is a question."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if not sentences:
        return False
    return sentences[-1].rstrip().endswith('?')


# CTA patterns — conversion-oriented questions that are independent of suppression.
# Includes: demo offers, scheduling, contact collection — all close/conversion actions.
CTA_PATTERNS = [
    r"хотите\s+(посмотреть|увидеть|попробовать|узнать|тестовый)",
    r"могу\s+показать",
    r"запланируем\s+демо",
    r"интересно\s+увидеть",
    r"готовы\s+посмотреть",
    r"буквально\s+10\s+минут",
    r"показать\s+на\s+(примере|демо|практике)",
    r"хотите\s+тестовый",
    r"оставьте\s+(контакт|номер|email)",
    # Close-state: scheduling and contact collection
    r"когда\s+удобно",
    r"удобно\s+созвониться",
    r"какой\s+контакт",
    r"как\s+с\s+вами\s+связаться",
    r"когда\s+можно\s+(позвонить|созвониться|встретиться)",
    r"оставите\s+(номер|контакт|email|почту)",
    r"напишите\s+(номер|контакт|email|почту)",
    r"куда\s+(прислать|отправить)",
    r"давайте\s+(запланируем|назначим|созвонимся)",
    r"на\s+какой\s+(email|номер|телефон|почту|адрес)",
    r"какой\s+(email|телефон|номер)\s+(для|удобн)",
]
_CTA_RE = re.compile("|".join(CTA_PATTERNS), re.IGNORECASE)


def is_cta_question(text: str) -> bool:
    """Check if trailing question is a CTA (conversion) question, not qualification."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if not sentences:
        return False
    last = sentences[-1]
    if not last.rstrip().endswith('?'):
        return False
    return bool(_CTA_RE.search(last))


def has_non_cta_trailing_question(text: str) -> bool:
    """Check if text has a trailing question that is NOT a CTA."""
    if not last_sentence_is_question(text):
        return False
    return not is_cta_question(text)


def get_expected_mode(density: int, persona: str = "") -> str:
    """Compute expected question_mode for given density and persona."""
    thresholds = get_persona_question_thresholds(persona)
    if density >= thresholds.get("suppress", 2):
        return "suppress"
    elif density >= thresholds.get("optional", 1):
        return "optional"
    return "mandatory"


# ═══════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TurnSpec:
    """Specification for a single conversation turn."""
    message: str
    description: str = ""
    # Expected classification intent (approximate — real LLM may vary)
    expected_intent_category: str = ""  # "question", "info", "objection", "positive", etc.
    # Suppression checks
    expect_bot_question: Optional[bool] = None  # True=MUST ask, False=MUST NOT, None=don't check
    expect_question_mode: Optional[str] = None  # "mandatory", "optional", "suppress"
    # Content checks
    expect_keywords: List[str] = field(default_factory=list)
    expect_no_keywords: List[str] = field(default_factory=list)


@dataclass
class TurnResult:
    """Result of a single turn."""
    turn_num: int
    user_message: str
    bot_response: str
    description: str
    # Classification
    intent: str
    intent_is_question: bool
    confidence: float
    # State
    state: str
    action: str
    # Question density
    intent_history: List[str]
    question_density: int          # density as bot saw it (pre-turn CW + current intent)
    post_turn_density: int         # density after CW update (for diagnostics)
    expected_mode: str
    # Response analysis
    response_question_count: int
    response_ends_with_question: bool
    response_last_sentence_is_question: bool
    # Checks
    check_bot_question: Optional[str] = None  # "PASS", "FAIL", None
    check_question_mode: Optional[str] = None  # "PASS", "FAIL", None
    check_keywords: Optional[str] = None  # "PASS", "FAIL", None
    missing_keywords: List[str] = field(default_factory=list)
    # Timing
    elapsed_ms: float = 0.0


@dataclass
class ScenarioSpec:
    """A complete test scenario."""
    name: str
    description: str
    flow_name: str  # Always "autonomous" per design requirement
    turns: List[TurnSpec]
    persona: str = ""  # Persona for SalesBot initialization


@dataclass
class ScenarioResult:
    """Result of a complete scenario."""
    scenario_name: str
    flow_name: str
    persona: str
    turns: List[TurnResult]
    total_elapsed_s: float = 0.0
    # Aggregates
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    # Per-check-type breakdown
    question_check_pass: int = 0
    question_check_fail: int = 0
    mode_check_pass: int = 0
    mode_check_fail: int = 0
    keyword_check_pass: int = 0
    keyword_check_fail: int = 0


# ═══════════════════════════════════════════════════════════════════
# Scenario 1: QUESTION FLOOD — 5 rapid-fire questions
# ═══════════════════════════════════════════════════════════════════

SCENARIO_QUESTION_FLOOD = ScenarioSpec(
    name="Question Flood — 5 consecutive questions → bot suppresses",
    description="Client asks 5 consecutive questions. After density≥2 the bot must stop asking.",
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Здравствуйте, расскажите о вашей CRM-системе.",
            description="Greeting + inquiry (density=1 → optional)",
            expected_intent_category="question",
            expect_bot_question=None,
            expect_question_mode="optional",
        ),
        TurnSpec(
            message="А какие основные функции у вас есть?",
            description="Features question (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        TurnSpec(
            message="Сколько стоит? Какие тарифы?",
            description="Pricing (density→3 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        TurnSpec(
            message="А с 1С интегрируется? А с телефонией?",
            description="Integration (density→4 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        TurnSpec(
            message="Есть мобильное приложение? Работает оффлайн?",
            description="Mobile (density→5 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 2: MIXED DIALOG — alternating questions and info
# ═══════════════════════════════════════════════════════════════════

SCENARIO_MIXED_DIALOG = ScenarioSpec(
    name="Mixed Dialog — alternating questions and information",
    description="Client alternates between questions and info. Density oscillates.",
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Добрый день, мы из компании ТехноПром, у нас 80 сотрудников.",
            description="Info (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="А сколько стоит ваша система на 80 человек?",
            description="Question (density→1 → optional)",
            expected_intent_category="question",
            expect_bot_question=None,
        ),
        TurnSpec(
            message="Понятно. У нас сейчас всё ведётся в Google Sheets, очень неудобно.",
            description="Info — pain point (density may decrease)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="Сколько стоит лицензия на 80 сотрудников? Какие тарифы?",
            description="Pricing question (density rises)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А какая у вас безопасность? Данные где хранятся?",
            description="Security question (density depends on window — may be optional or suppress)",
            expected_intent_category="question",
            # NOTE: density may be 1 (optional) if prior turns weren't classified as question intents
        ),
        TurnSpec(
            message="Ясно, спасибо. У нас бюджет примерно 500 тысяч в год, руководитель — Иван Петров.",
            description="Info — budget + contact (density should drop)",
            expected_intent_category="info",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 3: RECOVERY — suppress → back to mandatory
# ═══════════════════════════════════════════════════════════════════

SCENARIO_RECOVERY = ScenarioSpec(
    name="Recovery — suppress → info flood → bot resumes questions",
    description="Client asks 3 questions (→suppress), then 5+ info turns push questions out of window.",
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Что такое CRM?",
            description="Question #1 (density=1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А сколько стоит ваша система?",
            description="Question #2 (density→2 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        TurnSpec(
            message="А какие есть интеграции с 1С?",
            description="Question #3 (density→3 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        TurnSpec(
            message="Ладно, понял. У нас небольшой магазин, 10 сотрудников.",
            description="Info — team size",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Мы продаём стройматериалы, работаем в Казани.",
            description="Info — industry + location",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Основная проблема — менеджеры забывают перезванивать клиентам.",
            description="Info — pain point",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="И ещё клиенты жалуются что мы долго отвечаем на заявки.",
            description="Info — second pain point",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Сейчас все записи ведём на бумаге, нужна автоматизация.",
            description="Info — current process (density=0 → mandatory → bot asks again!)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 4: LONG OSCILLATING DIALOG — 20 turns with multiple waves
# ═══════════════════════════════════════════════════════════════════

SCENARIO_LONG_OSCILLATING = ScenarioSpec(
    name="Long Oscillating Dialog — 20 turns with question/info waves",
    description="""
    20-turn realistic dialog simulating a client who asks in bursts:
    asks 2-3 questions, provides info for a few turns, asks again.
    Tests that the sliding window correctly manages density across
    multiple wave cycles and the system doesn't accumulate errors.
    """,
    flow_name="autonomous",
    turns=[
        # === Wave 1: Opening info ===
        TurnSpec(
            message="Добрый день! Меня зовут Марат, я директор сети аптек в Алматы.",
            description="Greeting + info (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="У нас 12 аптек, около 60 сотрудников. Ищем CRM для учёта.",
            description="Info — size (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        # === Wave 2: First question burst ===
        TurnSpec(
            message="А ваша система подходит для аптек? Есть ли учёт лекарств?",
            description="Question #1 about pharmacy (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А как с маркировкой товаров? Поддерживает ли система ИСМЕТ?",
            description="Question #2 about marking (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        TurnSpec(
            message="А интеграция с налоговой есть? Электронные счета-фактуры?",
            description="Question #3 about tax integration (density→3 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # === Wave 3: Info recovery ===
        TurnSpec(
            message="Хорошо, спасибо за информацию. Сейчас мы используем 1С для бухгалтерии.",
            description="Info — current tools (density dropping)",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Основная проблема — в каждой аптеке свой учёт, нет единой картины.",
            description="Info — pain point (density dropping)",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Из-за этого бывает пересортица — в одной аптеке излишки, в другой дефицит.",
            description="Info — implication (density dropping)",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Нам нужна система которая объединит все точки в одну базу.",
            description="Info — desired outcome (density ~0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        # === Wave 4: Second question burst ===
        TurnSpec(
            message="Можно ли управлять всеми 12 аптеками с одного аккаунта?",
            description="Question about multi-location (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А ревизию можно проводить через систему? Инвентаризацию?",
            description="Question about inventory (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # === Wave 5: More info ===
        TurnSpec(
            message="Понятно. Ещё важный момент — у нас строгие требования к отчётности для аптек.",
            description="Info — compliance requirement",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="И нужна интеграция с нашим складским ПО, это критично.",
            description="Info — integration requirement",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Бюджет у нас ограничен, не более 200 тысяч тенге в месяц на все точки.",
            description="Info — budget constraint",
            expected_intent_category="info",
        ),
        # === Wave 6: Third question burst ===
        TurnSpec(
            message="Какой у вас тариф для 12 точек подключения?",
            description="Question about pricing (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А есть ли скидка если оплачивать за год сразу?",
            description="Question about discount (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # === Wave 7: Closing info ===
        TurnSpec(
            message="Ладно, это в нашем бюджете. Нам подходит.",
            description="Positive signal (density drops)",
            expected_intent_category="positive",
        ),
        TurnSpec(
            message="У нас ещё вопрос по обучению — 60 человек нужно обучить.",
            description="Question about training (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="Хорошо, давайте попробуем. Мой email: marat@apteki.kz",
            description="Close — contact (density drops)",
            expected_intent_category="positive",
        ),
        TurnSpec(
            message="Спасибо за подробную консультацию, ждём демо.",
            description="Positive close (density=0 → mandatory)",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 5: AUTONOMOUS FULL — 12-turn realistic dialog
# ═══════════════════════════════════════════════════════════════════

SCENARIO_AUTONOMOUS_FULL = ScenarioSpec(
    name="Autonomous Full Dialog — 12 turns with mixed intents",
    description="Realistic autonomous flow with questions, objections, and positive signals.",
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Здравствуйте! Ищем CRM для отдела продаж.",
            description="Greeting",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="У нас 50 менеджеров, работаем в сфере недвижимости.",
            description="Info — size + industry",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="Сколько стоит на 50 человек?",
            description="Question: pricing (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А есть интеграция с Авито и ЦИАН?",
            description="Question: integration (density→2 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        TurnSpec(
            message="А что с безопасностью? Данные шифруются?",
            description="Question: security (density→3 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        TurnSpec(
            message="Это дорого, у конкурентов дешевле.",
            description="Objection: price (not a question — density may drop)",
        ),
        TurnSpec(
            message="А чем вы лучше amoCRM?",
            description="Question: comparison (density depends on window)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="Интересно, покажите как работает воронка.",
            description="Positive: demo interest",
            expected_intent_category="positive",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="А можно тестовый период?",
            description="Question: trial (density→1)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="Хорошо, давайте попробуем. Мой email: manager@realty.ru",
            description="Close: contact provided",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 6: FRUSTRATED CLIENT — aggressive questioning + complaints
# ═══════════════════════════════════════════════════════════════════

SCENARIO_FRUSTRATED_CLIENT = ScenarioSpec(
    name="Frustrated Client — aggressive questions mixed with complaints",
    description="""
    An angry client who alternates between demanding questions and
    expressing frustration. Tests suppression under emotional pressure:
    questions still count toward density even when aggressive in tone.
    Objections/complaints do NOT increase density.
    """,
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Здравствуйте, нам срочно нужна CRM, у нас полный бардак в продажах.",
            description="Urgent greeting + pain (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="Мы уже потеряли 3 крупных клиента из-за отсутствия нормальной системы!",
            description="Emotional pain (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        TurnSpec(
            message="Сколько это вообще стоит? Только не надо заоблачных цен!",
            description="Aggressive pricing question (density→1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А за сколько дней можно запустить? У нас нет времени ждать месяцами!",
            description="Urgent question with pressure — may classify as urgency/no_problem",
            expected_intent_category="question",
            # NOTE: classifier may see this as urgency/objection, not question → don't enforce suppress
        ),
        # Frustration/complaint — not a question, shouldn't increase density
        TurnSpec(
            message="Предыдущую CRM нам настраивали 3 месяца и всё равно ничего не работало!",
            description="Complaint about past experience (not question → density may drop)",
            expected_intent_category="objection",
        ),
        TurnSpec(
            message="А у вас поддержка нормальная? Или тоже будем неделями ждать ответа?",
            description="Support question with frustration (density depends on window)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="У нас 40 менеджеров, работаем по всему Казахстану, 5 филиалов.",
            description="Info dump — size + geography (density drops)",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Нам нужно чтобы все филиалы видели единую базу клиентов в реальном времени.",
            description="Info — requirement (density drops further)",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="А данные из нашей старой системы можно перенести? У нас 50 тысяч контактов!",
            description="Migration question (density→1 → optional after recovery)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="Ладно, покажите демо. Но если снова разочаруемся — уйдём к конкурентам.",
            description="Conditional positive + threat (positive signal)",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 7: TOPIC JUMPER — client switches topics unpredictably
# ═══════════════════════════════════════════════════════════════════

SCENARIO_TOPIC_JUMPER = ScenarioSpec(
    name="Topic Jumper — client switches topics every 1-2 turns",
    description="""
    A client who can't stay on one topic: asks about pricing, then
    security, then circles back to features, asks about support, etc.
    Tests that question density tracks correctly across topic switches
    and the bot handles context jumps gracefully under suppression.
    """,
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Добрый день, у нас автосервис на 25 человек.",
            description="Info — business (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        # Topic 1: Pricing
        TurnSpec(
            message="Сколько стоит ваша CRM?",
            description="Pricing question (density→1 → optional)",
            expected_intent_category="question",
        ),
        # Topic jump → Integration
        TurnSpec(
            message="А, подождите, главное — есть ли интеграция с 1С?",
            description="Integration question — topic jump (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # Topic jump → Security
        TurnSpec(
            message="Ещё вопрос — данные на ваших серверах или на наших?",
            description="Security question — another topic (density→3 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # Topic jump back → Pricing (but gives info this time)
        TurnSpec(
            message="А, ну ладно. Наш бюджет — примерно 100 тысяч в месяц.",
            description="Info — budget (density starts dropping)",
            expected_intent_category="info",
        ),
        # Topic jump → Mobile
        TurnSpec(
            message="Кстати, а мобильное приложение для мастеров есть?",
            description="Mobile question (density depends on window)",
            expected_intent_category="question",
        ),
        # Info — but about a new topic
        TurnSpec(
            message="У нас мастера работают на выезде, им нужно смотреть заказы с телефона.",
            description="Info — workflow detail",
            expected_intent_category="info",
        ),
        # Topic jump → Reports
        TurnSpec(
            message="А отчёты по выручке и загрузке мастеров есть?",
            description="Reports question (density depends on window)",
            expected_intent_category="question",
        ),
        # Topic jump → Back to competition
        TurnSpec(
            message="У нас коллеги используют amoCRM, чем вы лучше?",
            description="Comparison question (density→suppress likely)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # Finally settles
        TurnSpec(
            message="Ладно, убедили. Давайте попробуем.",
            description="Positive close (density drops)",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 8: OBJECTION + QUESTION MIX — stress test interaction
# ═══════════════════════════════════════════════════════════════════

SCENARIO_OBJECTION_QUESTION_MIX = ScenarioSpec(
    name="Objection + Question Mix — objections don't inflate density",
    description="""
    Tests that objections (which are NOT in all_questions) don't increase
    question density, but questions after objections do. Also tests the
    interaction between objection handling and question suppression.
    """,
    flow_name="autonomous",
    turns=[
        TurnSpec(
            message="Здравствуйте, у нас ресторан, 30 сотрудников.",
            description="Info (density=0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
        ),
        # Objection — should NOT increase question density
        TurnSpec(
            message="Это слишком дорого для ресторана.",
            description="Objection: price (density stays 0 — objection is NOT a question)",
            expected_intent_category="objection",
        ),
        TurnSpec(
            message="У нас уже есть iiko, зачем нам ещё одна система?",
            description="Objection: competitor (density stays ~0, may be classified as question or objection)",
            expected_intent_category="objection",
        ),
        # First question after objections — density should be low
        TurnSpec(
            message="А в чём конкретно вы лучше iiko для ресторанов?",
            description="Question: comparison (density should be ~1 after objections → optional)",
            expected_intent_category="question",
        ),
        # Second question — density rises (but may be optional if T4 was classified as objection)
        TurnSpec(
            message="А есть модуль для резервирования столиков?",
            description="Question: features (density depends on T4 classification)",
            expected_intent_category="question",
            # NOTE: density may be 1 (optional) if T4 "чем лучше iiko" was classified as objection
        ),
        # More objection — should NOT push density further
        TurnSpec(
            message="Не уверен что нам нужна такая сложная система.",
            description="Objection: complexity (density should NOT increase — objection)",
            expected_intent_category="objection",
        ),
        # Info turn
        TurnSpec(
            message="Ладно. У нас основная боль — потери при закрытии кассы. Не сходится выручка.",
            description="Info — pain point (density drops)",
            expected_intent_category="info",
        ),
        # Question after recovery
        TurnSpec(
            message="У вас есть Z-отчёты и сверка кассы?",
            description="Question about fiscal (density ~1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А инвентаризацию продуктов можно делать через вашу систему?",
            description="Question about inventory (density→2 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # Final positive
        TurnSpec(
            message="Ок, покажите демо для ресторана.",
            description="Positive — demo request",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 9: RAPID BURST DOUBLE WAVE — two floods with recovery
# ═══════════════════════════════════════════════════════════════════

SCENARIO_DOUBLE_WAVE = ScenarioSpec(
    name="Double Wave — two question floods separated by info recovery",
    description="""
    Client asks 3 questions (→suppress), provides info to recover,
    then asks 3 more questions (→suppress again). Tests that recovery
    is truly stateless and the second wave triggers suppress cleanly.
    """,
    flow_name="autonomous",
    turns=[
        # === Wave 1: Question flood ===
        TurnSpec(
            message="Привет, что за система у вас?",
            description="Question #1 (density=1 → optional)",
            expected_intent_category="question",
        ),
        TurnSpec(
            message="А сколько стоит подключение?",
            description="Question #2 (density→2 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        TurnSpec(
            message="А мобильное приложение есть?",
            description="Question #3 (density→3 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        # === Recovery: 5 info turns to push all questions out of window ===
        TurnSpec(
            message="Понял, спасибо. У нас автомастерская, 15 человек.",
            description="Info #1 — recovery starts",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Мы делаем кузовной ремонт и покраску автомобилей.",
            description="Info #2",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Клиенты жалуются что мы не перезваниваем по готовности.",
            description="Info #3 — pain point",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Средний чек у нас около 150 тысяч тенге.",
            description="Info #4",
            expected_intent_category="info",
        ),
        TurnSpec(
            message="Нам нужна система для записи клиентов и контроля заказов.",
            description="Info #5 (density should be 0 → mandatory)",
            expected_intent_category="info",
            expect_bot_question=True,
            expect_question_mode="mandatory",
        ),
        # === Wave 2: Second question flood ===
        TurnSpec(
            message="А можно вести историю ремонтов каждого автомобиля?",
            description="Question #1 wave2 (density→1 → optional)",
            expected_intent_category="question",
            expect_question_mode="optional",
        ),
        TurnSpec(
            message="А СМС-уведомления клиентам есть?",
            description="Question #2 wave2 (density→2 → SUPPRESS again!)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        TurnSpec(
            message="А фотоотчёт по ремонту можно прикрепить к заказу?",
            description="Question #3 wave2 (density→3 → SUPPRESS)",
            expected_intent_category="question",
            expect_bot_question=False,
            expect_question_mode="suppress",
        ),
        # === Close ===
        TurnSpec(
            message="Хорошо, мне нравится. Давайте попробуем тестовый период.",
            description="Positive close (density drops)",
            expected_intent_category="positive",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Scenario 10: EDGE CASES — unusual message patterns
# ═══════════════════════════════════════════════════════════════════

SCENARIO_EDGE_CASES = ScenarioSpec(
    name="Edge Cases — short/tricky messages and unusual patterns",
    description="""
    Tests edge cases: very short messages, single-word questions,
    multi-question messages, questions embedded in statements,
    and rhetorical-seeming questions. Validates robustness of the
    suppression system under unusual input.
    """,
    flow_name="autonomous",
    turns=[
        # Ultra-short greeting
        TurnSpec(
            message="Здравствуйте.",
            description="Minimal greeting (density=0 → mandatory)",
            expect_bot_question=True,
        ),
        # Single-word answer
        TurnSpec(
            message="Магазин.",
            description="Ultra-short info — business type",
            expected_intent_category="info",
        ),
        # Terse question
        TurnSpec(
            message="Цена?",
            description="Single-word question (density→1 → optional)",
            expected_intent_category="question",
        ),
        # Multi-question in one message
        TurnSpec(
            message="Сколько стоит? Какие тарифы? Есть скидки? А рассрочка?",
            description="4 questions in 1 message (density→2 → suppress)",
            expected_intent_category="question",
            expect_bot_question=False,
        ),
        # Long info with embedded question-like phrasing
        TurnSpec(
            message="Мы уже 5 лет работаем без CRM, не знаю почему раньше не подключили. 20 сотрудников у нас.",
            description="Info with embedded 'почему' (should classify as info, not question)",
            expected_intent_category="info",
        ),
        # Very specific technical question
        TurnSpec(
            message="Поддерживаете ли вы ЕГАИС для алкоголя и маркировку Честный Знак?",
            description="Specific technical question (density depends on window)",
            expected_intent_category="question",
        ),
        # Confused/rambling with question at end
        TurnSpec(
            message="Ну вот я не знаю, у нас тут бардак полный, всё на бумаге, менеджеры путают заказы... А у вас реально можно это наладить?",
            description="Rambling pain + question at end",
            expected_intent_category="question",
        ),
        # Client corrects himself
        TurnSpec(
            message="Нет, подождите, я ошибся. У нас не 20 а 30 сотрудников.",
            description="Correction — info update",
            expected_intent_category="info",
        ),
        # Question that sounds like a statement
        TurnSpec(
            message="Интересно было бы посмотреть как это работает вживую.",
            description="Implicit demo request (statement-like, not a question)",
            expected_intent_category="positive",
        ),
        # Final question
        TurnSpec(
            message="Когда можно демо?",
            description="Short scheduling question",
            expected_intent_category="question",
        ),
    ],
)


# ═══════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════

def run_scenario(scenario: ScenarioSpec, compact: bool = False) -> ScenarioResult:
    """Run a single e2e scenario."""
    print(f"\n{'=' * 80}")
    print(f"  SCENARIO: {scenario.name}")
    persona_label = scenario.persona or "default"
    thresholds = get_persona_question_thresholds(scenario.persona)
    print(f"  Flow: {scenario.flow_name} | Persona: {persona_label} | "
          f"Thresholds: suppress≥{thresholds.get('suppress', 2)}, "
          f"optional≥{thresholds.get('optional', 1)}, window={thresholds.get('window', 5)}")
    print(f"  Turns: {len(scenario.turns)}")
    print(f"{'=' * 80}")

    llm = OllamaLLM()
    bot_kwargs = dict(llm=llm, flow_name=scenario.flow_name, enable_tracing=True)
    if scenario.persona:
        bot_kwargs["persona"] = scenario.persona
    bot = SalesBot(**bot_kwargs)

    result = ScenarioResult(
        scenario_name=scenario.name,
        flow_name=scenario.flow_name,
        persona=scenario.persona,
        turns=[],
    )

    start_total = time.time()

    for i, turn_spec in enumerate(scenario.turns):
        turn_num = i + 1

        # === Send message ===
        t0 = time.time()
        try:
            proc_result = bot.process(turn_spec.message)
            response = proc_result.get("response", "[NO RESPONSE]")
            intent = proc_result.get("intent", "?")
            confidence = proc_result.get("confidence", 0.0)
            state = proc_result.get("state", "?")
            action = proc_result.get("action", "?")
        except Exception as e:
            response = f"[ERROR: {e}]"
            intent = "error"
            confidence = 0.0
            state = "error"
            action = "error"
        elapsed_ms = (time.time() - t0) * 1000

        # === Compute question density (mirrors what the system does) ===
        # Bot computes density BEFORE adding current turn to CW.
        # After process(), CW already includes this turn. To match the bot's
        # view, use history[:-1] (pre-turn state) + current_intent.
        full_intent_history = list(bot.context_window.get_intent_history())
        pre_turn_history = full_intent_history[:-1]  # CW state BEFORE this turn
        current_intent = intent
        persona_for_density = scenario.persona
        thresholds_d = get_persona_question_thresholds(persona_for_density)
        window = thresholds_d.get("window", 5)
        density = compute_question_density(pre_turn_history, current_intent, window=window)
        post_turn_density = density
        intent_is_question = intent in ALL_QUESTION_INTENTS
        expected_mode = get_expected_mode(density, persona_for_density)

        # === Analyze response ===
        q_count = count_questions_in_text(response)
        resp_ends_q = ends_with_question(response)
        last_sent_q = last_sentence_is_question(response)
        is_cta = is_cta_question(response)
        has_non_cta_q = has_non_cta_trailing_question(response)

        # === Run checks ===
        check_bot_q = None
        if turn_spec.expect_bot_question is True:
            check_bot_q = "PASS" if q_count > 0 else "FAIL"
        elif turn_spec.expect_bot_question is False:
            # When suppress: no NON-CTA trailing question
            # CTA questions ("Хотите демо?") are independent of suppression by design
            check_bot_q = "PASS" if not has_non_cta_q else "FAIL"

        check_mode = None
        if turn_spec.expect_question_mode:
            check_mode = "PASS" if expected_mode == turn_spec.expect_question_mode else "FAIL"

        check_kw = None
        missing_kw = []
        if turn_spec.expect_keywords:
            resp_lower = response.lower()
            missing_kw = [kw for kw in turn_spec.expect_keywords if kw.lower() not in resp_lower]
            check_kw = "PASS" if not missing_kw else "FAIL"

        # === Record ===
        turn_result = TurnResult(
            turn_num=turn_num,
            user_message=turn_spec.message,
            bot_response=response,
            description=turn_spec.description,
            intent=intent,
            intent_is_question=intent_is_question,
            confidence=confidence,
            state=state,
            action=action,
            intent_history=pre_turn_history[-5:],
            question_density=density,
            post_turn_density=post_turn_density,
            expected_mode=expected_mode,
            response_question_count=q_count,
            response_ends_with_question=resp_ends_q,
            response_last_sentence_is_question=last_sent_q,
            check_bot_question=check_bot_q,
            check_question_mode=check_mode,
            check_keywords=check_kw,
            missing_keywords=missing_kw,
            elapsed_ms=elapsed_ms,
        )
        result.turns.append(turn_result)

        # Update aggregate counters
        for check_name, check_val, pass_attr, fail_attr in [
            ("question", check_bot_q, "question_check_pass", "question_check_fail"),
            ("mode", check_mode, "mode_check_pass", "mode_check_fail"),
            ("keyword", check_kw, "keyword_check_pass", "keyword_check_fail"),
        ]:
            if check_val is not None:
                result.total_checks += 1
                if check_val == "PASS":
                    result.passed_checks += 1
                    setattr(result, pass_attr, getattr(result, pass_attr) + 1)
                else:
                    result.failed_checks += 1
                    setattr(result, fail_attr, getattr(result, fail_attr) + 1)

        # === Print ===
        _print_turn(turn_result, turn_spec, compact)

    result.total_elapsed_s = time.time() - start_total
    return result


def _print_turn(tr: TurnResult, spec: TurnSpec, compact: bool):
    """Print a single turn result."""
    # Status emoji
    checks = [tr.check_bot_question, tr.check_question_mode, tr.check_keywords]
    active_checks = [c for c in checks if c is not None]
    if not active_checks:
        emoji = "⚪"
    elif all(c == "PASS" for c in active_checks):
        emoji = "✅"
    elif any(c == "FAIL" for c in active_checks):
        emoji = "❌"
    else:
        emoji = "🟡"

    mode_icon = {"mandatory": "📋", "optional": "💭", "suppress": "🔇"}.get(tr.expected_mode, "?")
    q_flag = "🔹" if tr.intent_is_question else "  "

    if compact:
        resp_short = tr.bot_response.replace('\n', ' ')[:80]
        check_str = ""
        if tr.check_bot_question:
            check_str += f" q:{tr.check_bot_question}"
        if tr.check_question_mode:
            check_str += f" m:{tr.check_question_mode}"
        print(
            f"  {emoji} T{tr.turn_num:2d} {q_flag} {mode_icon} d={tr.question_density}({tr.post_turn_density}) "
            f"| {tr.intent:30s} | {tr.state:20s} | {tr.elapsed_ms:5.0f}ms "
            f"| q?={tr.response_question_count} trail?={'Y' if tr.response_last_sentence_is_question else 'N'}"
            f"{check_str}"
        )
    else:
        print(f"\n  {'─' * 75}")
        print(f"  {emoji} Turn {tr.turn_num} — {tr.description}")
        print(f"  {'─' * 75}")
        print(f"  User: {spec.message[:120]}")

        resp_display = tr.bot_response.replace('\n', ' ')
        if len(resp_display) > 250:
            resp_display = resp_display[:250] + "..."
        print(f"  Bot:  {resp_display}")

        print(f"  Intent: {q_flag} {tr.intent} (conf={tr.confidence:.2f})")
        print(f"  State: {tr.state} | Action: {tr.action}")
        print(f"  Density: {tr.question_density} (post-turn: {tr.post_turn_density}) → {mode_icon} {tr.expected_mode}")
        print(f"  History window (pre-turn): {tr.intent_history}")
        print(f"  Response: {tr.response_question_count} questions, "
              f"trailing?={'YES' if tr.response_last_sentence_is_question else 'no'}")
        print(f"  Time: {tr.elapsed_ms:.0f}ms")

        # Check results
        if tr.check_bot_question:
            check_emoji = "✅" if tr.check_bot_question == "PASS" else "❌"
            expect_str = "has question" if spec.expect_bot_question else "NO trailing question"
            actual_str = f"q_count={tr.response_question_count}, trailing={tr.response_last_sentence_is_question}"
            print(f"  {check_emoji} QUESTION CHECK: expect={expect_str}, actual={actual_str}")
        if tr.check_question_mode:
            check_emoji = "✅" if tr.check_question_mode == "PASS" else "❌"
            print(f"  {check_emoji} MODE CHECK: expect={spec.expect_question_mode}, actual={tr.expected_mode}")
        if tr.check_keywords:
            check_emoji = "✅" if tr.check_keywords == "PASS" else "❌"
            print(f"  {check_emoji} KEYWORD CHECK: missing={tr.missing_keywords or 'none'}")


def print_summary(results: List[ScenarioResult]):
    """Print final summary."""
    print(f"\n{'═' * 80}")
    print(f"  FINAL SUMMARY — Question Suppression E2E (Enhanced Field Simulation)")
    print(f"{'═' * 80}")

    total_checks = sum(r.total_checks for r in results)
    total_pass = sum(r.passed_checks for r in results)
    total_fail = sum(r.failed_checks for r in results)
    total_turns = sum(len(r.turns) for r in results)

    for r in results:
        pct = (r.passed_checks / r.total_checks * 100) if r.total_checks else 0
        emoji = "✅" if r.failed_checks == 0 else "❌"
        persona_label = r.persona or "default"
        print(f"\n  {emoji} {r.scenario_name}")
        print(f"    Flow: {r.flow_name} | Persona: {persona_label} | "
              f"Turns: {len(r.turns)} | Time: {r.total_elapsed_s:.1f}s")
        print(f"    Checks: {r.passed_checks}/{r.total_checks} passed ({pct:.0f}%)")
        if r.question_check_fail:
            print(f"    ❌ Question checks failed: {r.question_check_fail}")
        if r.mode_check_fail:
            print(f"    ❌ Mode checks failed: {r.mode_check_fail}")
        if r.keyword_check_fail:
            print(f"    ❌ Keyword checks failed: {r.keyword_check_fail}")

        # Show failed turns
        for t in r.turns:
            fails = []
            if t.check_bot_question == "FAIL":
                fails.append(f"q_check(expect={('has_q' if t.response_question_count==0 else 'no_trail_q')}, "
                             f"got trail={t.response_last_sentence_is_question})")
            if t.check_question_mode == "FAIL":
                fails.append(f"mode(expect={t.expected_mode})")
            if t.check_keywords == "FAIL":
                fails.append(f"kw_missing={t.missing_keywords}")
            if fails:
                print(f"      T{t.turn_num}: {', '.join(fails)}")

    # Overall
    print(f"\n  {'─' * 70}")
    if total_checks:
        pct = total_pass / total_checks * 100
        print(f"  OVERALL: {total_pass}/{total_checks} checks passed ({pct:.0f}%)")
        print(f"  TOTAL TURNS: {total_turns} across {len(results)} scenarios")
    else:
        print(f"  OVERALL: No checks defined")

    # Density distribution analysis
    print(f"\n  {'─' * 70}")
    print(f"  DENSITY DISTRIBUTION ACROSS ALL TURNS:")
    density_counts = defaultdict(int)
    for r in results:
        for t in r.turns:
            density_counts[t.question_density] += 1
    for d in sorted(density_counts.keys()):
        mode = get_expected_mode(d)
        bar = "█" * density_counts[d]
        print(f"    density={d} ({mode:10s}): {density_counts[d]:3d} turns {bar}")

    # Per-persona density distribution
    print(f"\n  {'─' * 70}")
    print(f"  DENSITY DISTRIBUTION PER PERSONA:")
    persona_density = defaultdict(lambda: defaultdict(int))
    for r in results:
        p = r.persona or "default"
        for t in r.turns:
            persona_density[p][t.question_density] += 1
    for p in sorted(persona_density.keys()):
        thresholds = get_persona_question_thresholds(p)
        print(f"\n    [{p}] suppress≥{thresholds.get('suppress', 2)} optional≥{thresholds.get('optional', 1)}")
        for d in sorted(persona_density[p].keys()):
            mode = get_expected_mode(d, p)
            bar = "█" * persona_density[p][d]
            print(f"      d={d} ({mode:10s}): {persona_density[p][d]:3d} {bar}")

    # Question in response analysis
    print(f"\n  {'─' * 70}")
    print(f"  QUESTION PRESENCE IN BOT RESPONSES:")
    for r in results:
        suppress_turns_with_q = 0
        suppress_turns_cta_only = 0
        suppress_turns_total = 0
        mandatory_turns_no_q = 0
        mandatory_turns_total = 0
        for t in r.turns:
            if t.expected_mode == "suppress":
                suppress_turns_total += 1
                if t.response_last_sentence_is_question:
                    if is_cta_question(t.bot_response):
                        suppress_turns_cta_only += 1
                    else:
                        suppress_turns_with_q += 1
            elif t.expected_mode == "mandatory":
                mandatory_turns_total += 1
                if t.response_question_count == 0:
                    mandatory_turns_no_q += 1

        persona_label = r.persona or "default"
        print(f"\n    [{r.scenario_name}] (persona={persona_label})")
        if suppress_turns_total:
            leak_pct = suppress_turns_with_q / suppress_turns_total * 100
            print(f"      Suppress mode: {suppress_turns_with_q}/{suppress_turns_total} "
                  f"leaked NON-CTA questions ({leak_pct:.0f}%)")
            if suppress_turns_cta_only:
                print(f"      Suppress mode: {suppress_turns_cta_only}/{suppress_turns_total} "
                      f"CTA-only questions (OK by design)")
        if mandatory_turns_total:
            miss_pct = mandatory_turns_no_q / mandatory_turns_total * 100
            print(f"      Mandatory mode: {mandatory_turns_no_q}/{mandatory_turns_total} "
                  f"missing questions ({miss_pct:.0f}%)")

    # Timing statistics
    print(f"\n  {'─' * 70}")
    print(f"  TIMING STATISTICS:")
    all_elapsed = [t.elapsed_ms for r in results for t in r.turns]
    if all_elapsed:
        avg_ms = sum(all_elapsed) / len(all_elapsed)
        p95_ms = sorted(all_elapsed)[int(len(all_elapsed) * 0.95)]
        max_ms = max(all_elapsed)
        total_s = sum(r.total_elapsed_s for r in results)
        print(f"    Avg per turn:  {avg_ms:.0f}ms")
        print(f"    P95 per turn:  {p95_ms:.0f}ms")
        print(f"    Max per turn:  {max_ms:.0f}ms")
        print(f"    Total runtime: {total_s:.1f}s")

    # Verdict
    if total_checks:
        pct = total_pass / total_checks * 100
        if pct >= 90:
            print(f"\n  🟢 VERDICT: Question suppression working well ({pct:.0f}%)")
        elif pct >= 70:
            print(f"\n  🟡 VERDICT: Question suppression partially working ({pct:.0f}%)")
        else:
            print(f"\n  🔴 VERDICT: Question suppression has significant issues ({pct:.0f}%)")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

ALL_SCENARIOS = {
    "flood": SCENARIO_QUESTION_FLOOD,
    "mixed": SCENARIO_MIXED_DIALOG,
    "recovery": SCENARIO_RECOVERY,
    "oscillating": SCENARIO_LONG_OSCILLATING,
    "autonomous": SCENARIO_AUTONOMOUS_FULL,
    "frustrated": SCENARIO_FRUSTRATED_CLIENT,
    "topic_jumper": SCENARIO_TOPIC_JUMPER,
    "objection_mix": SCENARIO_OBJECTION_QUESTION_MIX,
    "double_wave": SCENARIO_DOUBLE_WAVE,
    "edge_cases": SCENARIO_EDGE_CASES,
}


def main():
    parser = argparse.ArgumentParser(description="E2E Question Suppression Test")
    parser.add_argument("--scenario", default=None,
                        choices=list(ALL_SCENARIOS.keys()),
                        help="Run only this scenario")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument("--json", default=None, help="Save JSON results to file")
    args = parser.parse_args()

    scenarios = (
        [ALL_SCENARIOS[args.scenario]] if args.scenario
        else list(ALL_SCENARIOS.values())
    )

    all_results = []

    total_turns = sum(len(s.turns) for s in scenarios)
    personas_used = sorted(set(s.persona or "default" for s in scenarios))

    print("=" * 80)
    print("  E2E Question Suppression Test — Enhanced Field Simulation (BUG #9)")
    print(f"  Scenarios: {len(scenarios)} | Total turns: {total_turns}")
    print(f"  Personas: {', '.join(personas_used)}")
    print(f"  Flow: autonomous (all scenarios)")
    print(f"  Layers: SYSTEM_PROMPT, {{question_instruction}}, hidden triggers, "
          f"ResponseDirectives, post-processing strip")
    print("=" * 80)

    for scenario in scenarios:
        try:
            result = run_scenario(scenario, compact=args.compact)
            all_results.append(result)
        except Exception as e:
            print(f"\n  ❌ SCENARIO FAILED: {scenario.name}")
            print(f"     Error: {e}")
            import traceback
            traceback.print_exc()

    print_summary(all_results)

    # Save JSON
    output_path = args.json or os.path.join(
        os.path.dirname(__file__), "e2e_question_suppression_results.json"
    )
    json_data = []
    for r in all_results:
        json_data.append({
            "scenario": r.scenario_name,
            "flow": r.flow_name,
            "persona": r.persona,
            "total_elapsed_s": r.total_elapsed_s,
            "checks": {
                "total": r.total_checks,
                "passed": r.passed_checks,
                "failed": r.failed_checks,
            },
            "turns": [
                {
                    "turn": t.turn_num,
                    "user": t.user_message,
                    "bot": t.bot_response,
                    "intent": t.intent,
                    "intent_is_question": t.intent_is_question,
                    "state": t.state,
                    "action": t.action,
                    "density": t.question_density,
                    "post_turn_density": t.post_turn_density,
                    "expected_mode": t.expected_mode,
                    "response_questions": t.response_question_count,
                    "trailing_question": t.response_last_sentence_is_question,
                    "checks": {
                        "bot_question": t.check_bot_question,
                        "question_mode": t.check_question_mode,
                        "keywords": t.check_keywords,
                    },
                    "elapsed_ms": t.elapsed_ms,
                }
                for t in r.turns
            ],
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
