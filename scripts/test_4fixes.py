#!/usr/bin/env python3
"""
Прогон тестовых диалогов для проверки 4 фиксов:
1) Корректное приветствие
2) Представляется как Айбот, женский род
3) Эмпатия и элитный сервис
4) Не ломается при внезапном желании купить

Запуск: python3 scripts/test_4fixes.py
"""
import sys
import json
import time
sys.path.insert(0, '/home/corta/crm-sales-bot-fork')

from src.bot import SalesBot
from src.llm import OllamaClient

_llm = OllamaClient()

def run_dialog(name: str, messages: list, check_fn=None):
    """Run a dialog and print results."""
    print(f"\n{'='*70}")
    print(f"  СЦЕНАРИЙ: {name}")
    print(f"{'='*70}")

    bot = SalesBot(llm=_llm, flow_name='autonomous')
    results = []

    for i, msg in enumerate(messages):
        print(f"\n  [Ход {i+1}] Клиент: {msg}")
        t0 = time.time()
        result = bot.process(msg)
        dt = time.time() - t0
        resp = result.get('response', '[NO RESPONSE]')
        state = result.get('state', '?')
        intent = result.get('intent', '?')
        action = result.get('action', '?')

        print(f"  Бот ({dt:.1f}с): {resp}")
        print(f"  [state={state}, intent={intent}, action={action}]")
        results.append({
            'turn': i+1,
            'user': msg,
            'bot': resp,
            'state': state,
            'intent': intent,
            'action': action,
            'time': round(dt, 1),
        })

    if check_fn:
        issues = check_fn(results)
        if issues:
            print(f"\n  ⚠️  ПРОБЛЕМЫ:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print(f"\n  ✅ ВСЁ ОК")

    return results


def check_greeting(results):
    """Проверка фикса 1+2: приветствие + Айбот + женский род."""
    issues = []
    r = results[0]
    bot = r['bot'].lower()

    # Должна представиться как Айбот
    if 'айбот' not in bot:
        issues.append(f"Не представилась как Айбот: '{r['bot'][:80]}'")

    # Женский род
    masc_markers = ['рад ', 'рад,', 'готов ', 'готов,', 'понял', 'подобрал']
    for m in masc_markers:
        if m in bot:
            issues.append(f"Маскулинная форма '{m}' в приветствии")

    # Не должно быть грубости / быдлячества (word boundaries to avoid false positives)
    import re as _re
    rude_patterns = [
        (r'\bздорова\b', 'здорова'),
        (r'\bздарова\b', 'здарова'),
        (r'\bчё\b', 'чё'),
        (r'\bчо\b', 'чо'),
        (r'\bну давай\b', 'ну давай'),
        (r'\bхай\b', 'хай'),
    ]
    for pattern, label in rude_patterns:
        if _re.search(pattern, bot):
            issues.append(f"Грубый маркер '{label}' в приветствии")

    return issues


def check_feminine(results):
    """Проверка женского рода во всех ответах."""
    import re
    issues = []
    # Use word-boundary regex to avoid false positives (подобрал in подобрала, etc.)
    masc_patterns = [
        (r'\bрад\b(?!а)', 'рад'),
        (r'\bготов\b(?!а)', 'готов'),
        (r'\bпонял\b(?!а)', 'понял'),
        (r'\bподобрал\b(?!а)', 'подобрал'),
        (r'\bуточнил\b(?!а)', 'уточнил'),
    ]
    for r in results:
        bot = r['bot'].lower()
        for pattern, label in masc_patterns:
            if re.search(pattern, bot):
                issues.append(f"Ход {r['turn']}: маскулинная форма '{label}' → '{r['bot'][:60]}'")
    return issues


def check_sudden_buy(results):
    """Проверка фикса 4: не ломается при внезапной покупке."""
    issues = []
    # Последний ход — клиент хочет купить, бот должен перейти в closing
    last = results[-1]
    if 'closing' not in last['state'] and 'payment' not in last['state'] and 'video' not in last['state']:
        issues.append(f"Не перешёл в closing/payment после ready_to_buy (state={last['state']})")

    # Бот не должен игнорировать желание купить
    bot = last['bot'].lower()
    ignore_markers = ['расскажите о бизнесе', 'сколько сотрудников', 'какой у вас бизнес']
    for m in ignore_markers:
        if m in bot:
            issues.append(f"Бот проигнорировал желание купить, задал '{m}'")

    return issues


def main():
    all_results = {}

    # ===== СЦЕНАРИЙ 1: Обычное приветствие =====
    all_results['greeting_ru'] = run_dialog(
        "Приветствие (русский)",
        ["Привет"],
        check_fn=check_greeting,
    )

    # ===== СЦЕНАРИЙ 2: Формальное приветствие =====
    all_results['greeting_formal'] = run_dialog(
        "Формальное приветствие",
        ["Добрый день"],
        check_fn=check_greeting,
    )

    # ===== СЦЕНАРИЙ 3: Казахское приветствие =====
    all_results['greeting_kz'] = run_dialog(
        "Казахское приветствие",
        ["Сәлем"],
        check_fn=lambda r: [],  # just observe
    )

    # ===== СЦЕНАРИЙ 4: Полный диалог с проверкой женского рода =====
    all_results['full_dialog'] = run_dialog(
        "Полный диалог (жен. род + эмпатия)",
        [
            "Здравствуйте",
            "У меня магазин одежды в Алматы, 3 продавца",
            "Какие у вас тарифы?",
            "А есть ли интеграция с Kaspi?",
            "Спасибо за информацию",
        ],
        check_fn=check_feminine,
    )

    # ===== СЦЕНАРИЙ 5: Внезапная покупка из discovery =====
    all_results['sudden_buy_discovery'] = run_dialog(
        "Внезапная покупка из discovery",
        [
            "Добрый день",
            "У меня небольшой магазин",
            "Хочу купить, выставите счёт",
        ],
        check_fn=check_sudden_buy,
    )

    # ===== СЦЕНАРИЙ 6: Внезапная покупка из qualification =====
    all_results['sudden_buy_qualification'] = run_dialog(
        "Внезапная покупка из qualification",
        [
            "Здравствуйте, интересует POS-система",
            "У нас сеть из 5 магазинов в Нур-Султане",
            "Нам нужна интеграция с 1С и ОФД",
            "Всё, готовы покупать. Давайте оформлять",
        ],
        check_fn=check_sudden_buy,
    )

    # ===== СЦЕНАРИЙ 7: Прямая покупка с первого сообщения =====
    all_results['direct_buy'] = run_dialog(
        "Прямая покупка с первого сообщения",
        [
            "Здравствуйте, хочу подключить Wipon. Куда платить?",
        ],
        check_fn=lambda r: (
            ["Не перешёл в closing (state=" + r[0]['state'] + ")"]
            if 'closing' not in r[0]['state'] and 'payment' not in r[0]['state']
            else []
        ),
    )

    # ===== СЦЕНАРИЙ 8: Эмпатия при проблеме =====
    all_results['empathy'] = run_dialog(
        "Эмпатия при проблеме клиента",
        [
            "Здравствуйте",
            "У нас постоянные проблемы с учётом, кассиры ошибаются, товар теряется",
            "Ничего не помогает, уже 3 раза меняли систему",
        ],
        check_fn=check_feminine,
    )

    # Сохраняем результаты
    with open('/home/corta/crm-sales-bot-fork/results/test_4fixes_results.json', 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f"  РЕЗУЛЬТАТЫ СОХРАНЕНЫ: results/test_4fixes_results.json")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
