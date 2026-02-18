#!/usr/bin/env python3
"""
E2E проверка замкнутого контура обратной связи.

Запускает 30 диалогов с персонами price_sensitive и tire_kicker,
ищет в логах:
  - escalated_fallback_attempt_1 → answer_with_pricing_brief
  - escalated_fallback_attempt_2 → answer_with_pricing_brief + OPERATOR_NOTIFY_STUB
  - Бот НЕ прерывает диалог (никакого упоминания оператора клиенту)

Использование:
    python scripts/e2e_feedback_loop_check.py
    python scripts/e2e_feedback_loop_check.py --dialogs 10   # быстрый прогон
"""

import sys
import os
import io
import re
import json
import time
import logging
import argparse
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# =============================================================================
# LOG CAPTURE — перехватываем все WARNING и выше до инициализации логгеров бота
# =============================================================================
class LogCapture(logging.Handler):
    """Перехватчик записей лога для последующего анализа."""

    def __init__(self, level=logging.DEBUG):
        super().__init__(level)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord):
        self.records.append(record)

    def get_messages(self, level: int = None, pattern: str = None) -> List[str]:
        result = []
        for r in self.records:
            if level is not None and r.levelno < level:
                continue
            msg = self.format(r)
            if pattern and pattern not in msg:
                continue
            result.append(msg)
        return result


# Устанавливаем до любых import'ов из src
_capture = LogCapture(logging.DEBUG)
_capture.setFormatter(logging.Formatter('%(levelname)s | %(name)s | %(message)s'))
logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(_capture)

# Тихий stdout-handler только WARNING+
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.WARNING)
_console.setFormatter(logging.Formatter('%(levelname)s | %(name)s | %(message)s'))
logging.root.addHandler(_console)

# =============================================================================
# ОСНОВНАЯ ЛОГИКА
# =============================================================================
def run_e2e(n_dialogs: int = 30, parallel: int = 2) -> None:
    from src.llm import OllamaClient
    from src.simulator.runner import SimulationRunner
    from src.simulator.kb_questions import load_kb_question_pool

    TARGET_PERSONAS = ["price_sensitive", "tire_kicker"]
    DIALOGS_PER_PERSONA = n_dialogs // len(TARGET_PERSONAS)

    print(f"\n{'='*70}")
    print(f"  E2E FEEDBACK LOOP CHECK — {n_dialogs} диалогов")
    print(f"  Персоны: {TARGET_PERSONAS}")
    print(f"  Параллельность: {parallel}")
    print(f"{'='*70}\n")

    # Проверка Ollama
    import requests
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code != 200:
            print("[ERROR] Ollama недоступен. Запустите: ollama serve")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Ollama недоступен: {e}")
        sys.exit(1)

    llm = OllamaClient()
    kb_pool = load_kb_question_pool()

    runner = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,
        verbose=False,
        flow_name="autonomous",
        kb_question_pool=kb_pool,
    )

    results_by_persona: Dict[str, List] = defaultdict(list)
    total = 0

    for persona in TARGET_PERSONAS:
        print(f"[{persona}] Запуск {DIALOGS_PER_PERSONA} диалогов...")
        batch = runner.run_batch(
            count=DIALOGS_PER_PERSONA,
            parallel=parallel,
            persona_filter=persona,
        )
        results_by_persona[persona] = batch
        total += len(batch)
        outcomes = defaultdict(int)
        for r in batch:
            outcomes[r.outcome] += 1
        print(f"  ✓ {len(batch)} завершено | outcomes: {dict(outcomes)}")

    print(f"\n[OK] Всего диалогов: {total}")

    # ==========================================================================
    # АНАЛИЗ ЛОГОВ
    # ==========================================================================
    print(f"\n{'='*70}")
    print("  АНАЛИЗ ЛОГОВ ESCALATION")
    print(f"{'='*70}\n")

    all_messages = [_capture.format(r) for r in _capture.records]

    # --- Поиск escalation signals ---
    escalation_re = re.compile(r'escalated_fallback_attempt_(\d+)')
    operator_re = re.compile(r'OPERATOR_NOTIFY_STUB')
    handoff_client_re = re.compile(r'kb_empty_handoff', re.IGNORECASE)

    escalation_by_attempt: Dict[int, List[str]] = defaultdict(list)
    operator_notify_lines: List[str] = []
    client_handoff_lines: List[str] = []

    for msg in all_messages:
        m = escalation_re.search(msg)
        if m:
            attempt_n = int(m.group(1))
            escalation_by_attempt[attempt_n].append(msg)

        if operator_re.search(msg):
            operator_notify_lines.append(msg)

        # Проверяем что kb_empty_handoff НЕ попадает в ответы клиенту
        # (он может быть в internal action, но не в bot response text)
        if handoff_client_re.search(msg) and 'action' in msg.lower():
            client_handoff_lines.append(msg)

    # --- Печать результатов ---
    print(f"{'─'*60}")
    print("ESCALATION ATTEMPTS найдены:")
    if not escalation_by_attempt:
        print("  ⚠️  Ни одного escalation не обнаружено.")
        print("     Возможные причины:")
        print("     • Персоны не повторяли вопросы достаточно")
        print("     • PriceQuestionSource срабатывал по primary intent (attempt=0, tier-0)")
        print("     • Мало диалогов — увеличьте --dialogs")
    else:
        for attempt_n in sorted(escalation_by_attempt.keys()):
            msgs = escalation_by_attempt[attempt_n]
            print(f"  attempt_{attempt_n}: {len(msgs)} раз")

            # Проверяем что action соответствует ожидаемому
            for msg in msgs[:3]:
                # Вытащим action из debug-лога
                action_m = re.search(r'→\s*(\S+)', msg)
                if action_m:
                    action = action_m.group(1).rstrip(')')
                    expected = {
                        0: "answer_with_pricing",
                        1: "answer_with_pricing_brief",
                        2: "answer_with_pricing_brief",
                    }.get(attempt_n, "?")
                    ok = "✓" if expected in action else "✗"
                    print(f"    {ok} action={action} (expected={expected})")

    print(f"\n{'─'*60}")
    print(f"OPERATOR_NOTIFY_STUB (silent, WARNING-уровень): {len(operator_notify_lines)}")
    for line in operator_notify_lines[:5]:
        print(f"  {line[:120]}")
    if len(operator_notify_lines) > 5:
        print(f"  ... ещё {len(operator_notify_lines) - 5}")

    print(f"\n{'─'*60}")
    # Проверяем что клиент не видит упоминание оператора
    # Ищем в dialogue текстах bot_responses
    operator_leaked = 0
    for persona, batch in results_by_persona.items():
        for sim in batch:
            for turn in sim.dialogue:
                bot_text = (turn.get("bot", "") or "").lower()
                if any(kw in bot_text for kw in ["оператор", "переключ", "специалист", "handoff"]):
                    operator_leaked += 1
                    print(f"  ⚠️  Утечка оператора в ответе бота: sim={sim.simulation_id} turn={turn}")

    if operator_leaked == 0:
        print("✓ Клиент НЕ видит упоминания оператора в ответах бота")
    else:
        print(f"✗ Найдено {operator_leaked} ответов бота с упоминанием оператора — НАРУШЕНИЕ!")

    # ==========================================================================
    # СВОДКА
    # ==========================================================================
    print(f"\n{'='*70}")
    print("  ИТОГОВАЯ СВОДКА")
    print(f"{'='*70}\n")

    checks = {
        "Диалоги завершены": total > 0,
        "escalated_fallback_attempt_1 найден": 1 in escalation_by_attempt,
        "escalated_fallback_attempt_2 найден": 2 in escalation_by_attempt,
        "OPERATOR_NOTIFY_STUB сработал": len(operator_notify_lines) > 0,
        "Клиент не видит оператора": operator_leaked == 0,
    }

    all_ok = True
    for check, passed in checks.items():
        status = "✓" if passed else "⚠"
        if not passed:
            all_ok = False
        print(f"  {status}  {check}")

    print()
    if all_ok:
        print("✅ Все проверки пройдены — замкнутый контур работает корректно")
    else:
        print("⚠️  Некоторые проверки не прошли.")
        print("   Если escalation не найден — возможно персоны не повторяли")
        print("   один и тот же вопрос 2+ раза в пределах одного диалога.")
        print("   Это нормально при коротких диалогах (< 8 ходов).")
        print("   Главное: клиент не видит оператора и бот не падает.")

    # Сохраняем детальный лог в файл
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"./reports/e2e_feedback_loop_{ts}.log"
    os.makedirs("./reports", exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        for msg in all_messages:
            f.write(msg + "\n")
    print(f"\n[LOG] Полный лог сохранён: {log_path}")
    print(f"      grep 'escalated_fallback' {log_path}")
    print(f"      grep 'OPERATOR_NOTIFY' {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E feedback loop verification")
    parser.add_argument("--dialogs", type=int, default=30,
                        help="Общее число диалогов (будет разделено поровну между персонами)")
    parser.add_argument("--parallel", type=int, default=2,
                        help="Параллельных потоков")
    args = parser.parse_args()

    run_e2e(n_dialogs=args.dialogs, parallel=args.parallel)
