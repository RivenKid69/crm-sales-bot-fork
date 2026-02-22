#!/usr/bin/env python3
"""
E2E тест новых terminal states: payment_ready и video_call_scheduled.

10 прогонов:
  - 5 x ready_buyer      → ожидаем payment_ready  (kaspi_phone + iin)
  - 3 x happy_path       → ожидаем video_call_scheduled (preferred_call_time + contact)
  - 2 x startup_founder  → ожидаем video_call_scheduled

Проверяем:
  1. final_state ∈ {payment_ready, video_call_scheduled}
  2. OPERATOR_NOTIFY залогирован с правильным outcome
  3. collected_data содержит нужные поля

Использование:
    python scripts/e2e_terminal_states.py
"""

import sys
import os
import json
import time
import logging
import re
from datetime import datetime
from pathlib import Path

# Путь к проекту
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# =============================================================================
# LOG CAPTURE для OPERATOR_NOTIFY
# =============================================================================
class OperatorNotifyCapture(logging.Handler):
    """Перехватывает OPERATOR_NOTIFY записи из constants.py"""
    def __init__(self):
        super().__init__()
        self.records: list = []

    def emit(self, record):
        msg = self.format(record)
        if "OPERATOR_NOTIFY |" in msg:
            self.records.append(msg)

    def last_for_outcome(self, outcome: str) -> str | None:
        for r in reversed(self.records):
            if f"outcome={outcome}" in r:
                return r
        return None

    def clear(self):
        self.records.clear()


notify_capture = OperatorNotifyCapture()
notify_capture.setLevel(logging.INFO)
logging.getLogger("src.yaml_config.constants").addHandler(notify_capture)

# =============================================================================
# КОНСТАНТЫ
# =============================================================================
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME  = "ministral-3:14b-instruct-2512-q8_0"
FLOW        = "autonomous"

PLAN = [
    # (persona, expected_state, description)
    ("ready_buyer",     "payment_ready",         "Готов купить #1"),
    ("ready_buyer",     "payment_ready",         "Готов купить #2"),
    ("ready_buyer",     "payment_ready",         "Готов купить #3"),
    ("ready_buyer",     "payment_ready",         "Готов купить #4"),
    ("ready_buyer",     "payment_ready",         "Готов купить #5"),
    ("happy_path",      "video_call_scheduled",  "Идеальный клиент #1"),
    ("happy_path",      "video_call_scheduled",  "Идеальный клиент #2"),
    ("happy_path",      "video_call_scheduled",  "Идеальный клиент #3"),
    ("startup_founder", "video_call_scheduled",  "Только открываюсь #1"),
    ("startup_founder", "video_call_scheduled",  "Только открываюсь #2"),
]

# =============================================================================
# UTILS
# =============================================================================
SEP  = "=" * 80
SSEP = "-" * 60

def hdr(text: str):
    print(f"\n{SEP}\n  {text}\n{SEP}")

def sec(text: str):
    print(f"\n{SSEP}\n  {text}\n{SSEP}")

def ok(text: str):   print(f"  [PASS] {text}")
def fail(text: str): print(f"  [FAIL] {text}")
def info(text: str): print(f"  [INFO] {text}")

# =============================================================================
# CHECKS
# =============================================================================
def check_ollama() -> bool:
    import requests
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).status_code == 200
    except Exception:
        return False


def get_final_state(dialogue: list) -> str:
    """Достаём финальный state из последнего хода диалога."""
    if not dialogue:
        return "UNKNOWN"
    last = dialogue[-1]
    return last.get("state", "UNKNOWN")


def check_payment_ready(collected_data: dict, notify_log: str | None) -> tuple[bool, list[str]]:
    """Проверки для payment_ready."""
    issues = []
    has_kaspi   = bool(collected_data.get("kaspi_phone"))
    has_iin     = bool(collected_data.get("iin"))
    has_contact = bool(collected_data.get("contact_info"))

    if not (has_kaspi or has_contact):
        issues.append("нет kaspi_phone и нет contact_info")
    if not has_iin:
        issues.append("нет iin")
    if notify_log is None:
        issues.append("OPERATOR_NOTIFY не найден в логах")
    elif "outcome=payment_ready" not in notify_log:
        issues.append(f"неверный outcome в OPERATOR_NOTIFY: {notify_log[:120]}")

    return len(issues) == 0, issues


def check_video_call_scheduled(collected_data: dict, notify_log: str | None) -> tuple[bool, list[str]]:
    """Проверки для video_call_scheduled (Variant 3: contact_info обязателен, preferred_call_time желателен)."""
    issues = []
    has_contact = bool(collected_data.get("contact_info"))

    if not has_contact:
        issues.append("нет contact_info")
    # preferred_call_time желателен, но не блокирует (Variant 3)
    if notify_log is None:
        issues.append("OPERATOR_NOTIFY не найден в логах")
    elif "outcome=video_call_scheduled" not in notify_log:
        issues.append(f"неверный outcome в OPERATOR_NOTIFY: {notify_log[:120]}")

    return len(issues) == 0, issues


# =============================================================================
# MAIN
# =============================================================================
def main():
    hdr("E2E ТЕСТ: payment_ready + video_call_scheduled (10 прогонов)")
    print(f"  Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Flow: {FLOW} | Модель: {MODEL_NAME}")
    print(f"  Прогонов: {len(PLAN)}")

    # Проверка Ollama
    if not check_ollama():
        print("\n[ERROR] Ollama не доступна. Запустите: ollama serve")
        sys.exit(1)
    info("Ollama: OK")

    # Инициализация LLM
    from src.llm import OllamaClient
    from src.simulator.runner import SimulationRunner
    from src.simulator.kb_questions import load_kb_question_pool

    llm    = OllamaClient()
    kb_pool = load_kb_question_pool()
    runner = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,
        verbose=False,
        flow_name=FLOW,
        kb_question_pool=kb_pool,
    )
    info(f"KB pool: {kb_pool.total_questions if kb_pool else 0} вопросов")

    # ==========================================================================
    # ПРОГОНЫ
    # ==========================================================================
    results = []
    total_pass = 0
    total_fail = 0

    for idx, (persona, expected_state, label) in enumerate(PLAN, 1):
        sec(f"[{idx:02d}/{len(PLAN)}] {label} | persona={persona} | ожидаем={expected_state}")

        notify_capture.clear()
        t0 = time.time()

        try:
            result = runner.run_single(persona_name=persona)
        except Exception as exc:
            fail(f"Симуляция упала с ошибкой: {exc}")
            results.append({
                "idx": idx, "label": label, "persona": persona,
                "expected": expected_state, "actual": "ERROR",
                "passed": False, "issues": [str(exc)],
                "duration": round(time.time() - t0, 1),
            })
            total_fail += 1
            continue

        duration = round(time.time() - t0, 1)
        final_state   = get_final_state(result.dialogue)
        collected     = result.collected_data
        notify_log    = notify_capture.last_for_outcome(expected_state)

        info(f"Ходов: {result.turns} | Длительность: {duration}s")
        info(f"Финальный state: {final_state}")
        info(f"Outcome (runner): {result.outcome}")
        info(f"collected_data: {json.dumps(collected, ensure_ascii=False)}")
        if notify_log:
            info(f"OPERATOR_NOTIFY: {notify_log.strip()}")
        else:
            info("OPERATOR_NOTIFY: <не найден>")

        # Проверка соответствия state
        state_ok = final_state == expected_state

        # Проверка collected_data + OPERATOR_NOTIFY
        if expected_state == "payment_ready":
            data_ok, issues = check_payment_ready(collected, notify_log)
        else:
            data_ok, issues = check_video_call_scheduled(collected, notify_log)

        passed = state_ok and data_ok
        all_issues = []
        if not state_ok:
            all_issues.append(f"state={final_state} (ожидали={expected_state})")
        all_issues.extend(issues)

        if passed:
            ok(f"ПРОШЁЛ — state={final_state}, data OK, OPERATOR_NOTIFY OK")
            total_pass += 1
        else:
            fail(f"ПРОВАЛ — проблемы: {'; '.join(all_issues)}")
            total_fail += 1

        results.append({
            "idx": idx,
            "label": label,
            "persona": persona,
            "expected": expected_state,
            "actual": final_state,
            "turns": result.turns,
            "duration": duration,
            "passed": passed,
            "issues": all_issues,
            "collected": {k: collected.get(k) for k in
                          ("kaspi_phone", "iin", "preferred_call_time", "contact_info", "contact_type")},
            "notify_logged": notify_log is not None,
        })

    # ==========================================================================
    # ИТОГОВЫЙ ОТЧЁТ
    # ==========================================================================
    hdr("ИТОГОВЫЙ ОТЧЁТ")

    print(f"\n  {'#':>3}  {'Персона':<20} {'Ожидали':<25} {'Факт':<25} {'Статус'}")
    print(f"  {'-'*3}  {'-'*20} {'-'*25} {'-'*25} {'-'*6}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {r['idx']:>3}  {r['persona']:<20} {r['expected']:<25} {r['actual']:<25} {status}")

    print()
    print(f"  ИТОГО: {total_pass}/{len(PLAN)} прошли")

    # Детали провалов
    failed = [r for r in results if not r["passed"]]
    if failed:
        print("\n  ПРОВАЛЫ:")
        for r in failed:
            print(f"    [{r['idx']:02d}] {r['label']}: {'; '.join(r['issues'])}")

    # Сводка по state distribution
    state_counts: dict[str, int] = {}
    for r in results:
        state_counts[r["actual"]] = state_counts.get(r["actual"], 0) + 1
    print(f"\n  Распределение финальных state:")
    for st, cnt in sorted(state_counts.items()):
        print(f"    {st:<30} {cnt} диалогов")

    # Сохранение JSON отчёта
    report_path = ROOT / "reports" / f"e2e_terminal_states_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"summary": {"pass": total_pass, "fail": total_fail, "total": len(PLAN)},
                   "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\n  Отчёт сохранён: {report_path}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    # Подавляем debug-шум из внутренностей бота
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("src.yaml_config.constants").setLevel(logging.INFO)
    main()
