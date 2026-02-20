#!/usr/bin/env python3
"""
Демо: Hotel-Staff Politeness в автономном флоу.
Три сценария:
  1. Имя неизвестно → бот один раз мягко спрашивает
  2. Имя "Алексей Петров" → "господин Петров"
  3. Имя "Айгерим" (только имя) → "госпожа Айгерим"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaClient
from src.bot import SalesBot

SEP  = "─" * 62
SEP2 = "═" * 62

def warmup(llm):
    import requests
    from src.settings import settings
    url = f"{settings.llm.base_url.rstrip('/')}/api/chat"
    for _ in range(5):
        try:
            r = requests.post(url, json={
                "model": settings.llm.model,
                "messages": [{"role": "user", "content": "привет"}],
                "stream": False, "options": {"num_predict": 5}
            }, timeout=90)
            if r.status_code == 200:
                return True
        except Exception:
            import time; time.sleep(2)
    return False


def run_dialog(llm, title: str, turns: list[tuple[str, str]]):
    """turns = [(client_msg, label), ...]"""
    print()
    print(SEP2)
    print(f"  {title}")
    print(SEP2)
    bot = SalesBot(llm, flow_name="autonomous")
    for client_msg, label in turns:
        print()
        print(f"  [{label}]")
        print(f"  КЛИЕНТ : {client_msg}")
        result = bot.process(client_msg)
        response = result.get("response", "").strip()
        state   = result.get("state", "?")
        collected = result.get("collected_data", {})
        name    = collected.get("contact_name") or collected.get("client_name") or "—"
        print(f"  БОТ    : {response}")
        print(f"  ↳ state={state}  contact_name={name}")
        print(f"  {SEP}")


def main():
    print()
    print(SEP2)
    print("  DEMO: Hotel-Staff Politeness")
    print(SEP2)

    print("\nПодключение к Ollama...")
    llm = OllamaClient()
    if not warmup(llm):
        print("ОШИБКА: Ollama недоступна")
        sys.exit(1)
    print("OK\n")

    # ── Диалог 1: имя неизвестно ────────────────────────────────
    run_dialog(llm, "ДИАЛОГ 1 — имя неизвестно, бот должен спросить", [
        ("Добрый день, интересует ваша система для магазина",
         "ход 1 / первый контакт"),
        ("Один магазин, продуктовый. Пока работаем на бумаге",
         "ход 2 / уточнение бизнеса"),
        ("Сколько примерно стоит базовый тариф?",
         "ход 3 / вопрос про цену"),
    ])

    # ── Диалог 2: клиент называет полное имя ────────────────────
    run_dialog(llm, "ДИАЛОГ 2 — полное имя «Алексей Петров» → «господин Петров»", [
        ("Здравствуйте, меня зовут Алексей Петров, хочу узнать про вашу кассу",
         "ход 1 / представился"),
        ("Две кассы, продукты, пока на 1С",
         "ход 2 / уточнение"),
        ("А какие тарифы есть?",
         "ход 3 / вопрос про тарифы"),
    ])

    # ── Диалог 3: клиент называет только имя (Казахстан) ────────
    run_dialog(llm, "ДИАЛОГ 3 — только имя «Айгерим» → «госпожа Айгерим»", [
        ("Сәлем, меня зовут Айгерим, у меня небольшой магазин одежды в Алматы",
         "ход 1 / представилась"),
        ("Три кассы, и мне важна интеграция с Kaspi",
         "ход 2 / детали бизнеса"),
        ("Скажите, есть ли рассрочка?",
         "ход 3 / вопрос про рассрочку"),
    ])

    print()
    print(SEP2)
    print("  DEMO завершён")
    print(SEP2)
    print()


if __name__ == "__main__":
    main()
