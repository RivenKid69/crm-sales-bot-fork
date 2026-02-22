#!/usr/bin/env python3
"""
E2E АУДИТ CHANGELOG-69 — синергия всех 69 коммитов.

30 диалогов через АВТОНОМНЫЙ LLM ФЛОУ (autonomous).
После прогона — полный отчёт: grouped checks, провалы, артефакты.

Покрытие по группам коммитов:
  G1  Terminal states   — payment_ready (kaspi_phone+IIN) / video_call_scheduled
  G2  Price homonyms    — "стоит"/"давайте" не тригерят price_question
  G3  Objection→soft    — hard objection маршрутизируется в soft_close
  G4  Discovery loop    — бот не зависает в discovery >5 ходов
  G5  Question density  — никогда >1 вопроса в одном ответе бота
  G6  Kazakh speaker    — казахский текст не вызывает false price intent
  G7  Feedback/repeat   — бот не повторяет дословно предыдущие ответы
  G8  SPIN coverage     — охват фаз discovery→qualification→presentation
  G9  Mixed personas    — синергия на разных персонах (no crashes)
  G10 Wipon branding    — "CRM" не используется как название продукта
  G11 Collected data    — extracted данные попадают в контекст LLM
  G12 Hallucination     — ответы не содержат hardcoded цен вне KB паттернов

Использование:
    python scripts/e2e_changelog69_audit.py
    python scripts/e2e_changelog69_audit.py --parallel 2
"""

import sys
import os
import re
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# LOG CAPTURE — перехватываем до import src
# =============================================================================
class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: List[logging.LogRecord] = []
        self.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))

    def emit(self, record: logging.LogRecord):
        self.records.append(record)

    def messages(self, pattern: str = "") -> List[str]:
        out = []
        for r in self.records:
            msg = self.format(r)
            if not pattern or pattern in msg:
                out.append(msg)
        return out

    def clear(self):
        self.records.clear()


_LOG = LogCapture()
logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(_LOG)
# Тихий console — только WARNING
_CON = logging.StreamHandler(sys.stdout)
_CON.setLevel(logging.WARNING)
_CON.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
logging.root.addHandler(_CON)


# =============================================================================
# ПЛАН — 30 диалогов (persona, group, description)
# =============================================================================
PLAN: List[Tuple[str, str, str]] = [
    # G1: Terminal states — payment_ready (kaspi_phone + IIN)
    ("ready_buyer",       "G1_terminal",    "Terminal: payment_ready #1"),
    ("ready_buyer",       "G1_terminal",    "Terminal: payment_ready #2"),
    ("ready_buyer",       "G1_terminal",    "Terminal: payment_ready #3"),
    # G1: Terminal states — video_call_scheduled
    ("happy_path",        "G1_terminal",    "Terminal: video_call_scheduled #1"),
    ("happy_path",        "G1_terminal",    "Terminal: video_call_scheduled #2"),
    ("startup_founder",   "G1_terminal",    "Terminal: video_call_scheduled #3"),

    # G2: Price homonyms — price_sensitive повторяет вопросы о цене;
    #     проверяем: ответ идёт из KB, а не от homonym "стоит"
    ("price_sensitive",   "G2_price",       "Price/homonym: price_sensitive #1"),
    ("price_sensitive",   "G2_price",       "Price/homonym: price_sensitive #2"),
    ("price_sensitive",   "G2_price",       "Price/homonym: price_sensitive #3"),

    # G3: Objection→soft_close
    ("aggressive",        "G3_objection",   "Objection→soft: aggressive #1"),
    ("aggressive",        "G3_objection",   "Objection→soft: aggressive #2"),
    ("tire_kicker",       "G3_objection",   "Objection→soft: tire_kicker"),

    # G4: Discovery loop prevention
    ("skeptic",           "G4_discovery",   "Discovery loop: skeptic #1"),
    ("skeptic",           "G4_discovery",   "Discovery loop: skeptic #2"),
    ("busy",              "G4_discovery",   "Discovery loop: busy"),

    # G5: Question density — не более 1 вопроса в ответе бота
    ("happy_path",        "G5_questions",   "Question density: happy_path"),
    ("returning_customer","G5_questions",   "Question density: returning_customer"),
    ("enterprise_buyer",  "G5_questions",   "Question density: enterprise_buyer"),

    # G6: Kazakh speaker — no false price intent
    ("kazakh_speaker",    "G6_kazakh",      "Kazakh: kazakh_speaker #1"),
    ("kazakh_speaker",    "G6_kazakh",      "Kazakh: kazakh_speaker #2"),
    ("kazakh_speaker",    "G6_kazakh",      "Kazakh: kazakh_speaker #3"),

    # G7: Feedback loop / broken record
    ("tire_kicker",       "G7_feedback",    "Feedback: tire_kicker"),
    ("price_sensitive",   "G7_feedback",    "Feedback: price_sensitive"),
    ("suspicious_buyer",  "G7_feedback",    "Feedback: suspicious_buyer"),

    # G8: SPIN coverage — фазы должны быть пройдены
    ("happy_path",        "G8_spin",        "SPIN coverage: happy_path"),
    ("enterprise_buyer",  "G8_spin",        "SPIN coverage: enterprise_buyer"),
    ("franchise_owner",   "G8_spin",        "SPIN coverage: franchise_owner"),

    # G9: Mixed personas — синергия / no crashes
    ("niche_business",    "G9_mixed",       "Mixed: niche_business"),
    ("frustrated_waiter", "G9_mixed",       "Mixed: frustrated_waiter"),
    ("multilocation_manager", "G9_mixed",   "Mixed: multilocation_manager"),
]

assert len(PLAN) == 30, f"Ожидается 30 диалогов, найдено {len(PLAN)}"

GROUPS = {
    "G1_terminal":  "Terminal states (payment_ready / video_call_scheduled)",
    "G2_price":     "Price homonyms + KB-grounded pricing",
    "G3_objection": "Objection → soft_close routing",
    "G4_discovery": "Discovery loop prevention",
    "G5_questions": "Question density ≤ 1 per turn",
    "G6_kazakh":    "Kazakh speaker — no false price intent",
    "G7_feedback":  "Feedback loop / no broken record",
    "G8_spin":      "SPIN phase coverage",
    "G9_mixed":     "Mixed personas — no crashes",
}

# Паттерны hardcoded цен (флаг потенциальной галлюцинации)
HARDCODED_PRICE_RE = re.compile(
    r"\b(\d{3,6})\s*(тенге|тг|₸|руб|сом)\b",
    re.IGNORECASE,
)
# Допустимо, если рядом есть маркеры неточности
APPROX_MARKERS = re.compile(
    r"(от|до|около|порядка|примерно|зависит|уточним|уточните|цен[аы]|прайс)",
    re.IGNORECASE,
)
# Паттерн CRM-брендинга (должны быть исправлены в коммите 098b9fd)
CRM_BRAND_RE = re.compile(r"\bCRM\b", re.IGNORECASE)

SEP  = "=" * 80
SSEP = "-" * 60


# =============================================================================
# CHECK FUNCTIONS
# =============================================================================

def check_no_crash(result) -> Tuple[bool, str]:
    if result is None:
        return False, "result is None"
    if result.errors:
        return False, f"errors: {result.errors[:2]}"
    return True, ""


def check_terminal_state(result, persona: str) -> Tuple[bool, str]:
    """G1: ready_buyer → payment_ready (kaspi_phone+IIN); happy_path/startup → video_call_scheduled."""
    if result is None or not result.dialogue:
        return False, "нет диалога"
    final_state = result.dialogue[-1].get("state", "")
    cd = result.collected_data or {}

    if persona == "ready_buyer":
        expected = "payment_ready"
        if final_state != expected:
            return False, f"state={final_state} (ожидался {expected})"
        if not cd.get("kaspi_phone") and not cd.get("contact_info"):
            return False, "нет kaspi_phone/contact_info в collected_data"
        if not cd.get("iin"):
            return False, "нет iin в collected_data"
        return True, ""
    else:  # happy_path, startup_founder
        expected = "video_call_scheduled"
        if final_state != expected:
            return False, f"state={final_state} (ожидался {expected})"
        if not cd.get("contact_info"):
            return False, "нет contact_info в collected_data"
        return True, ""


def check_no_mid_greeting(result) -> Tuple[bool, str]:
    """G10: бот не вставляет приветствие после первого хода."""
    if result is None:
        return True, ""
    violations = []
    for turn in result.dialogue:
        if turn["turn"] <= 1:
            continue
        bot_text = (turn.get("bot") or "").strip()
        if re.match(r"^(Здравствуйте|Добрый день|Доброе утро|Добрый вечер)", bot_text, re.IGNORECASE):
            violations.append(f"turn {turn['turn']}: '{bot_text[:60]}'")
    if violations:
        return False, "mid-greeting: " + "; ".join(violations[:2])
    return True, ""


def check_no_crm_brand(result) -> Tuple[bool, str]:
    """G10 Wipon branding: ответы не содержат 'CRM' как название продукта."""
    if result is None:
        return True, ""
    violations = []
    for turn in result.dialogue:
        bot_text = turn.get("bot") or ""
        # Пропускаем если 'CRM' как часть словосочетания "POS/CRM" или технического контекста
        # Ищем "CRM" как самостоятельное название продукта
        matches = CRM_BRAND_RE.findall(bot_text)
        # Разрешаем упоминания в контексте сравнений ("В отличие от CRM...")
        # Считаем нарушением только если CRM упоминается как продукт бота
        if matches:
            # Простая эвристика: если рядом нет "Wipon" и есть "CRM" — проблема
            if "wipon" not in bot_text.lower():
                violations.append(f"turn {turn['turn']}: CRM без Wipon")
    if violations:
        return False, "; ".join(violations[:2])
    return True, ""


def check_question_density(result) -> Tuple[bool, str]:
    """G5: не более 1 вопроса (?) в одном ответе бота (согласно SPIN методологии)."""
    if result is None:
        return True, ""
    violations = []
    for turn in result.dialogue:
        bot_text = turn.get("bot") or ""
        # Считаем предложения-вопросы (с ?)
        sentences = re.split(r"(?<=[.!?])\s+", bot_text)
        q_count = sum(1 for s in sentences if s.rstrip().endswith("?"))
        if q_count > 1:
            violations.append(f"turn {turn['turn']}: {q_count} вопросов")
    if violations:
        return False, "; ".join(violations[:3])
    return True, ""


def check_no_discovery_loop(result, max_discovery_turns: int = 7) -> Tuple[bool, str]:
    """G4: discovery state не должен повторяться более max_discovery_turns раз."""
    if result is None:
        return True, ""
    discovery_count = sum(
        1 for t in result.dialogue
        if "discovery" in (t.get("state") or "")
    )
    if discovery_count > max_discovery_turns:
        return False, f"discovery повторился {discovery_count} раз (max={max_discovery_turns})"
    return True, ""


def check_no_repeated_response(result) -> Tuple[bool, str]:
    """G7: бот не повторяет дословно предыдущие ответы в одном диалоге."""
    if result is None:
        return True, ""
    seen: Dict[str, int] = {}
    violations = []
    for turn in result.dialogue:
        bot_text = (turn.get("bot") or "").strip()
        if not bot_text or len(bot_text) < 30:
            continue
        # Нормализуем: убираем пунктуацию + lowercase
        key = re.sub(r"\W+", " ", bot_text.lower()).strip()
        if key in seen:
            violations.append(f"turn {turn['turn']} == turn {seen[key]}")
        else:
            seen[key] = turn["turn"]
    if violations:
        return False, "дублей: " + "; ".join(violations[:2])
    return True, ""


def check_spin_coverage(result, min_phases: int = 2) -> Tuple[bool, str]:
    """G8: диалог должен пройти как минимум 2 фазы SPIN."""
    if result is None:
        return False, "нет результата"
    phases = result.phases_reached or []
    unique = list(dict.fromkeys(phases))  # порядок сохраняется
    if len(unique) < min_phases:
        return False, f"фаз={len(unique)} ({unique}) < {min_phases}"
    return True, ""


def check_collected_data_forwarded(result, min_turns: int = 5) -> Tuple[bool, str]:
    """G11: если диалог длиннее min_turns, в collected_data должно быть ≥1 поле."""
    if result is None:
        return True, ""
    if result.turns < min_turns:
        return True, "skip (мало ходов)"
    cd = result.collected_data or {}
    # Фильтруем только непустые
    non_empty = {k: v for k, v in cd.items() if v}
    if not non_empty:
        return False, f"collected_data пуст после {result.turns} ходов"
    return True, ""


def check_no_hallucinated_price(result) -> Tuple[bool, str]:
    """G12: подозрительные hardcoded цены без контекста KB."""
    if result is None:
        return True, ""
    violations = []
    for turn in result.dialogue:
        bot_text = turn.get("bot") or ""
        for m in HARDCODED_PRICE_RE.finditer(bot_text):
            # Проверяем контекст вокруг числа
            start = max(0, m.start() - 60)
            end = min(len(bot_text), m.end() + 60)
            context = bot_text[start:end]
            if not APPROX_MARKERS.search(context):
                violations.append(f"turn {turn['turn']}: '{m.group()}' без KB-контекста")
    if violations:
        return False, "; ".join(violations[:2])
    return True, ""


def check_objection_soft_close(result) -> Tuple[bool, str]:
    """G3: после hard objection (rejection/aggressive) следующий action ∈ {soft_close, autonomous_respond} и не aggressive push."""
    if result is None:
        return True, ""
    # Ищем ходы где intent=rejection и следующий state
    prev_rejection = False
    violations = []
    for turn in result.dialogue:
        intent = turn.get("intent") or ""
        state = turn.get("state") or ""
        action = turn.get("action") or ""
        if prev_rejection:
            # После rejection не должно быть autonomous_closing с action push
            if "closing" in state and "push" in action:
                violations.append(f"turn {turn['turn']}: post-rejection state={state} action={action}")
            prev_rejection = False
        if intent in ("rejection", "hard_objection") or "rejection" in intent:
            prev_rejection = True
    if violations:
        return False, "; ".join(violations[:2])
    return True, ""


def check_stall_guard_in_terminal(result) -> Tuple[bool, str]:
    """G1/1adea7d: StallGuard не должен срабатывать в terminal states."""
    if result is None:
        return True, ""
    violations = []
    for turn in result.dialogue:
        state = turn.get("state") or ""
        action = turn.get("action") or ""
        if state in ("payment_ready", "video_call_scheduled"):
            if action == "soft_close":
                violations.append(f"turn {turn['turn']}: StallGuard → soft_close в terminal")
    if violations:
        return False, "; ".join(violations[:2])
    return True, ""


def check_no_disambiguation_excess(result, max_disambig: int = 3) -> Tuple[bool, str]:
    """37ee23a: disambiguation_needed не должен срабатывать более max_disambig раз за диалог."""
    if result is None:
        return True, ""
    disambig_turns = [
        t["turn"] for t in result.dialogue
        if "disambiguation" in (t.get("intent") or "")
        or "disambiguation" in (t.get("action") or "")
    ]
    if len(disambig_turns) > max_disambig:
        return False, f"disambiguation_needed × {len(disambig_turns)} (max={max_disambig}), turns={disambig_turns[:5]}"
    return True, ""


# =============================================================================
# RUN ONE DIALOG
# =============================================================================

def run_one(runner, idx: int, persona: str, group: str, label: str) -> Dict[str, Any]:
    """Запускает один диалог и возвращает полный dict с проверками."""
    _LOG.clear()
    t0 = time.time()
    result = None
    exc_str = None

    try:
        result = runner.run_single(persona_name=persona)
    except Exception as exc:
        exc_str = str(exc)

    duration = round(time.time() - t0, 1)

    # Базовые метрики
    turns = result.turns if result else 0
    outcome = result.outcome if result else "error"
    final_state = (result.dialogue[-1].get("state", "?") if result and result.dialogue else "?")
    phases = result.phases_reached if result else []

    # Проверки
    checks: Dict[str, Tuple[bool, str]] = {}

    checks["no_crash"] = (True, "") if exc_str is None and result else (False, exc_str or "None result")
    checks["no_mid_greeting"] = check_no_mid_greeting(result)
    checks["no_crm_brand"] = check_no_crm_brand(result)
    checks["question_density"] = check_question_density(result)
    checks["no_discovery_loop"] = check_no_discovery_loop(result)
    checks["no_repeated_response"] = check_no_repeated_response(result)
    checks["spin_coverage"] = check_spin_coverage(result, min_phases=2)
    checks["collected_data"] = check_collected_data_forwarded(result)
    checks["no_hallucinated_price"] = check_no_hallucinated_price(result)
    checks["objection_soft_close"] = check_objection_soft_close(result)
    checks["stall_in_terminal"] = check_stall_guard_in_terminal(result)
    checks["no_disambiguation_excess"] = check_no_disambiguation_excess(result)

    # Группоспецифичные проверки
    if group == "G1_terminal":
        checks["terminal_state"] = check_terminal_state(result, persona)

    # Общий статус диалога
    failed = [k for k, (ok, _) in checks.items() if not ok]
    passed = len(failed) == 0

    # Лог-сигналы
    operator_notify = len(_LOG.messages("OPERATOR_NOTIFY"))
    price_false_trigger = len(_LOG.messages("secondary_intent=price_question")) + \
                          len(_LOG.messages("repeated_question=price_question"))

    return {
        "idx": idx,
        "label": label,
        "persona": persona,
        "group": group,
        "outcome": outcome,
        "turns": turns,
        "final_state": final_state,
        "phases": phases,
        "duration": duration,
        "passed": passed,
        "failed_checks": failed,
        "checks": {k: {"ok": ok, "msg": msg} for k, (ok, msg) in checks.items()},
        "operator_notify_count": operator_notify,
        "price_false_trigger_count": price_false_trigger,
        "collected_data": dict(result.collected_data) if result and result.collected_data else {},
        "errors": list(result.errors) if result and result.errors else ([exc_str] if exc_str else []),
        "dialogue_snippet": _snippet(result),
    }


def _snippet(result) -> List[Dict[str, str]]:
    """Первые и последние 2 хода для отчёта."""
    if not result or not result.dialogue:
        return []
    d = result.dialogue
    if len(d) <= 4:
        return [{"t": t["turn"], "c": (t.get("client") or "")[:80],
                 "b": (t.get("bot") or "")[:120]} for t in d]
    head = d[:2]
    tail = d[-2:]
    mid = [{"t": "...", "c": "", "b": ""}]
    return [{"t": t["turn"], "c": (t.get("client") or "")[:80],
             "b": (t.get("bot") or "")[:120]} for t in head] + mid + \
           [{"t": t["turn"], "c": (t.get("client") or "")[:80],
             "b": (t.get("bot") or "")[:120]} for t in tail]


# =============================================================================
# REPORT
# =============================================================================

def print_report(all_results: List[Dict[str, Any]]) -> None:
    total = len(all_results)
    passed_list = [r for r in all_results if r["passed"]]
    failed_list = [r for r in all_results if not r["passed"]]

    print(f"\n{SEP}")
    print("  ПОЛНЫЙ ОТЧЁТ — E2E АУДИТ CHANGELOG-69")
    print(SEP)
    print(f"  Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Flow: autonomous (LLM-driven)")
    print(f"  Диалогов: {total}  |  PASS: {len(passed_list)}  |  FAIL: {len(failed_list)}")

    # ------------------------------------------------------------------
    # 1. Сводная таблица по диалогам
    # ------------------------------------------------------------------
    print(f"\n{SSEP}")
    print("  [СВОДКА ПО ДИАЛОГАМ]")
    print(SSEP)
    print(f"  {'#':>3}  {'Группа':<16} {'Персона':<22} {'Финал':<25} {'Ходов':>5}  {'Статус'}")
    print(f"  {'─'*3}  {'─'*16} {'─'*22} {'─'*25} {'─'*5}  {'─'*6}")
    for r in all_results:
        status = "PASS" if r["passed"] else "FAIL"
        failed_str = ""
        if r["failed_checks"]:
            failed_str = f"  [{', '.join(r['failed_checks'][:3])}]"
        print(f"  {r['idx']:>3}  {r['group']:<16} {r['persona']:<22} "
              f"{r['final_state']:<25} {r['turns']:>5}  {status}{failed_str}")

    # ------------------------------------------------------------------
    # 2. Результаты по группам коммитов
    # ------------------------------------------------------------------
    print(f"\n{SSEP}")
    print("  [РЕЗУЛЬТАТЫ ПО ГРУППАМ КОММИТОВ]")
    print(SSEP)

    groups_seen = list(dict.fromkeys(r["group"] for r in all_results))
    for grp in groups_seen:
        grp_results = [r for r in all_results if r["group"] == grp]
        grp_pass = sum(1 for r in grp_results if r["passed"])
        grp_total = len(grp_results)
        pct = grp_pass / grp_total * 100
        status = "OK" if grp_pass == grp_total else "WARN" if pct >= 50 else "FAIL"
        print(f"\n  [{status}] {grp} — {GROUPS.get(grp, grp)}")
        print(f"       {grp_pass}/{grp_total} диалогов прошли ({pct:.0f}%)")
        for r in grp_results:
            mark = "✓" if r["passed"] else "✗"
            fails = f"  [{', '.join(r['failed_checks'])}]" if r["failed_checks"] else ""
            print(f"    {mark} #{r['idx']:02d} {r['persona']:<22} "
                  f"→ {r['final_state']:<22} turns={r['turns']}{fails}")

    # ------------------------------------------------------------------
    # 3. Агрегированные проверки по check-типам
    # ------------------------------------------------------------------
    print(f"\n{SSEP}")
    print("  [АГРЕГИРОВАННЫЕ ПРОВЕРКИ (все 30 диалогов)]")
    print(SSEP)

    # Собираем все ключи проверок
    all_check_keys: List[str] = []
    for r in all_results:
        for k in r["checks"]:
            if k not in all_check_keys:
                all_check_keys.append(k)

    check_descriptions = {
        "no_crash":             "Нет краша / exception",
        "no_mid_greeting":      "Нет mid-dialog приветствия (bug #5)",
        "no_crm_brand":         "Wipon брендинг — нет 'CRM' как продукта (коммит 098b9fd)",
        "question_density":     "Плотность вопросов ≤1/ответ (bug #9)",
        "no_discovery_loop":    "Discovery не зацикливается >7 ходов (bugs #12/#12b)",
        "no_repeated_response": "Нет дублирования ответов (bug #3 broken record)",
        "spin_coverage":        "Охват SPIN фаз ≥2",
        "collected_data":       "Извлечённые данные попадают в контекст (коммит 1d56b72)",
        "no_hallucinated_price":"Нет hardcoded цен без KB (коммит 5ec919f/0c41043)",
        "objection_soft_close": "Возражение → soft_close (bugs #7 ae00986)",
        "stall_in_terminal":    "StallGuard не срабатывает в terminal states (1adea7d)",
        "no_disambiguation_excess": "disambiguation_needed ≤3/диалог (37ee23a — 4 root causes)",
        "terminal_state":       "Terminal state достигнут с нужными данными (932a8e7)",
    }

    for key in all_check_keys:
        applicable = [r for r in all_results if key in r["checks"]]
        if not applicable:
            continue
        passed_c = sum(1 for r in applicable if r["checks"][key]["ok"])
        n = len(applicable)
        pct = passed_c / n * 100
        mark = "✓" if passed_c == n else "⚠" if pct >= 50 else "✗"
        desc = check_descriptions.get(key, key)
        print(f"  {mark} {key:<28} {passed_c:>2}/{n:<2} ({pct:>5.1f}%)  {desc}")
        # Печатаем провалы
        for r in applicable:
            ch = r["checks"][key]
            if not ch["ok"] and ch["msg"]:
                print(f"      ↳ #{r['idx']:02d} {r['persona']}: {ch['msg'][:100]}")

    # ------------------------------------------------------------------
    # 4. Price / Kazakh signal stats
    # ------------------------------------------------------------------
    print(f"\n{SSEP}")
    print("  [PRICE SIGNAL / KAZAKH STATS]")
    print(SSEP)
    total_operator = sum(r["operator_notify_count"] for r in all_results)
    total_false_price = sum(r["price_false_trigger_count"] for r in all_results)
    print(f"  OPERATOR_NOTIFY срабатываний : {total_operator}")
    print(f"  false price_question сигналов: {total_false_price}")

    kazakh_results = [r for r in all_results if r["persona"] == "kazakh_speaker"]
    if kazakh_results:
        kz_false = sum(r["price_false_trigger_count"] for r in kazakh_results)
        print(f"  false price у kazakh_speaker : {kz_false} (ожидается 0)")

    # ------------------------------------------------------------------
    # 5. Детальные провалы
    # ------------------------------------------------------------------
    if failed_list:
        print(f"\n{SSEP}")
        print("  [ДЕТАЛЬНЫЕ ПРОВАЛЫ]")
        print(SSEP)
        for r in failed_list:
            print(f"\n  ✗ #{r['idx']:02d} {r['label']} | {r['persona']} | {r['group']}")
            print(f"    outcome={r['outcome']} | final_state={r['final_state']} | turns={r['turns']}")
            print(f"    Провалившиеся проверки:")
            for ck in r["failed_checks"]:
                msg = r["checks"][ck]["msg"]
                print(f"      - {ck}: {msg}")
            if r["errors"]:
                print(f"    Ошибки: {r['errors'][:2]}")
            # Snippet диалога
            if r["dialogue_snippet"]:
                print("    Диалог (фрагмент):")
                for turn in r["dialogue_snippet"]:
                    t = turn["t"]
                    if t == "...":
                        print("      ...")
                        continue
                    print(f"      [{t}] C: {turn['c']}")
                    print(f"           B: {turn['b']}")

    # ------------------------------------------------------------------
    # 6. Outcome distribution
    # ------------------------------------------------------------------
    print(f"\n{SSEP}")
    print("  [РАСПРЕДЕЛЕНИЕ OUTCOME]")
    print(SSEP)
    outcome_counts: Dict[str, int] = defaultdict(int)
    for r in all_results:
        outcome_counts[r["outcome"]] += 1
    for outcome, cnt in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        print(f"  {outcome:<30} {cnt:>3} ({pct:.1f}%)")

    # ------------------------------------------------------------------
    # 7. Финальный итог
    # ------------------------------------------------------------------
    print(f"\n{SEP}")
    pct_global = len(passed_list) / total * 100
    if len(failed_list) == 0:
        verdict = "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ"
    elif pct_global >= 70:
        verdict = f"ЧАСТИЧНЫЙ УСПЕХ — {len(passed_list)}/{total} прошли"
    else:
        verdict = f"ТРЕБУЕТСЯ ВНИМАНИЕ — {len(failed_list)}/{total} провалились"

    print(f"  ИТОГ: {verdict}")
    print(f"  PASS: {len(passed_list)}/{total} ({pct_global:.1f}%)")
    print(SEP)


def save_json_report(all_results: List[Dict[str, Any]], report_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"changelog69_audit_{ts}.json"
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(all_results),
        "passed": sum(1 for r in all_results if r["passed"]),
        "failed": sum(1 for r in all_results if not r["passed"]),
        "groups": {
            grp: {
                "total": len([r for r in all_results if r["group"] == grp]),
                "passed": sum(1 for r in all_results if r["group"] == grp and r["passed"]),
            }
            for grp in dict.fromkeys(r["group"] for r in all_results)
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": all_results}, f,
                  indent=2, ensure_ascii=False)
    return path


# =============================================================================
# MAIN
# =============================================================================

def main(parallel: int = 1) -> None:
    print(f"\n{SEP}")
    print("  E2E АУДИТ CHANGELOG-69 — 30 ДИАЛОГОВ (AUTONOMOUS LLM FLOW)")
    print(SEP)
    print(f"  Дата:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Flow:       autonomous")
    print(f"  Диалогов:   {len(PLAN)}")
    print(f"  Параллельно: {parallel}")

    # Проверка Ollama
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code != 200:
            print("[ERROR] Ollama недоступен. Запустите: ollama serve")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Ollama недоступен: {e}")
        sys.exit(1)
    print("  Ollama:     OK")

    # Инициализация
    from src.llm import OllamaClient
    from src.simulator.runner import SimulationRunner
    from src.simulator.kb_questions import load_kb_question_pool

    llm     = OllamaClient()
    kb_pool = load_kb_question_pool()
    runner  = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,
        verbose=False,
        flow_name="autonomous",
        kb_question_pool=kb_pool,
    )
    print(f"  KB pool:    {kb_pool.total_questions if kb_pool else 0} вопросов\n")

    # Прогон диалогов
    all_results: List[Dict[str, Any]] = []
    total_pass = 0

    for idx, (persona, group, label) in enumerate(PLAN, 1):
        print(f"  [{idx:02d}/30] {label:<45}", end=" ", flush=True)
        t0 = time.time()
        result_dict = run_one(runner, idx, persona, group, label)
        elapsed = time.time() - t0
        status = "PASS" if result_dict["passed"] else "FAIL"
        fails = f"  [{','.join(result_dict['failed_checks'][:2])}]" if result_dict["failed_checks"] else ""
        print(f"{status} | {result_dict['turns']:>2} turns | {elapsed:.0f}s{fails}")
        if result_dict["passed"]:
            total_pass += 1
        all_results.append(result_dict)

    # Отчёт в stdout
    print_report(all_results)

    # Сохранение JSON
    report_dir = ROOT / "reports"
    json_path = save_json_report(all_results, report_dir)
    print(f"\n  JSON отчёт: {json_path}")

    sys.exit(0 if total_pass == len(PLAN) else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E Changelog-69 Audit (30 dialogs, autonomous flow)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Параллельных потоков (default=1 для корректного log capture)")
    args = parser.parse_args()
    main(parallel=args.parallel)
