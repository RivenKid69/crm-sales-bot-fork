#!/usr/bin/env python3
"""
Итерация 4: Фокус на оставшиеся проблемы.
- Discovery pacing (не прыгать к тарифу)
- 24/7 support claim
- Competitor comparison (списки)
- Garbled text
"""
import sys
import json
import time
import re
sys.path.insert(0, '/home/corta/crm-sales-bot-fork')

from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaClient

_llm = OllamaClient()


def run_dialog(name, messages, verbose=True):
    print(f"\n{'='*70}")
    print(f"  СЦЕНАРИЙ: {name}")
    print(f"{'='*70}")
    setup_autonomous_pipeline()
    bot = SalesBot(llm=_llm, flow_name='autonomous')
    results = []
    for i, msg in enumerate(messages):
        if verbose:
            print(f"\n  [{i+1}] Клиент: {msg}")
        t0 = time.time()
        r = bot.process(msg)
        dt = time.time() - t0
        resp = r.get('response', '[NO RESPONSE]')
        state = r.get('state', '?')
        intent = r.get('intent', '?')
        action = r.get('action', '?')
        if verbose:
            print(f"  Бот ({dt:.1f}с): {resp}")
            print(f"  [state={state}, intent={intent}, action={action}]")
        results.append({
            'turn': i+1, 'user': msg, 'bot': resp,
            'state': state, 'intent': intent, 'action': action,
            'time': round(dt, 1), 'word_count': len(resp.split()),
        })
    return results


def analyze_all(all_results):
    total_issues = []
    for name, results in all_results.items():
        issues = []
        for r in results:
            bot = r['bot']
            bot_low = bot.lower()
            turn = r['turn']

            # Маскулинные формы
            for pat, label in [
                (r'\bрад\b(?!а)', 'рад'), (r'\bготов\b(?!а)', 'готов'),
                (r'\bпонял\b(?!а)', 'понял'), (r'\bподобрал\b(?!а)', 'подобрал'),
            ]:
                if re.search(pat, bot_low):
                    issues.append(f"T{turn}: маскулин '{label}'")

            # Списки
            if re.search(r'(?:^|\n)\s*[-•]\s+\w', bot):
                issues.append(f"T{turn}: буллет-лист")
            if re.search(r'(?:^|\n)\s*\d+[.)]\s+\w', bot):
                issues.append(f"T{turn}: нумерованный список")

            # Длина
            if r['word_count'] > 60:
                issues.append(f"T{turn}: длинный ответ ({r['word_count']} слов)")

            # Markdown
            if '**' in bot or '__' in bot:
                issues.append(f"T{turn}: markdown bold")

            # 24/7 / круглосуточная поддержка (false — actual: будни до 00, выходные до 21)
            if '24/7' in bot or '24 / 7' in bot:
                issues.append(f"T{turn}: ложное 24/7")
            if 'круглосуточн' in bot_low and ('поддержк' in bot_low or 'техподдержк' in bot_low or 'помощ' in bot_low):
                issues.append(f"T{turn}: ложная круглосуточная поддержка")

            # Акции/скидки
            if re.search(r'скидк\w+\s+\d+\s*%', bot_low):
                issues.append(f"T{turn}: выдуманная скидка %")

            # Запрещённые фразы
            if 'как вас зовут' in bot_low:
                issues.append(f"T{turn}: запрещёнка 'как вас зовут'")

        if issues:
            print(f"\n  ⚠️  {name}: {len(issues)} проблем")
            for i in issues:
                print(f"    - {i}")
        else:
            print(f"\n  ✅ {name}: чисто")
        total_issues.extend([(name, i) for i in issues])
    return total_issues


def main():
    all_results = {}

    # 1. Discovery pacing — разные типы бизнеса
    all_results['discovery_clothes'] = run_dialog("Discovery: магазин одежды", [
        "Привет",
        "У меня магазин одежды в Алматы, 3 продавца",
    ])

    all_results['discovery_cafe'] = run_dialog("Discovery: кафе", [
        "Здравствуйте",
        "У нас кафе на 50 посадочных мест",
    ])

    all_results['discovery_pharmacy'] = run_dialog("Discovery: аптека", [
        "Добрый день",
        "У меня аптека в Астане, 8 фармацевтов",
    ])

    # 2. Поддержка — проверка 24/7 claim
    all_results['support_question'] = run_dialog("Вопрос про поддержку", [
        "Привет",
        "У нас продуктовый магазин",
        "А поддержка у вас круглосуточная?",
    ])

    # 3. Сравнение с конкурентами (списки пролезают)
    all_results['competitor_poster'] = run_dialog("Сравнение с Poster", [
        "Здравствуйте",
        "Сейчас используем Poster, думаем перейти. Чем вы лучше?",
    ])

    all_results['competitor_iiko'] = run_dialog("Сравнение с iiko", [
        "Здравствуйте",
        "Мы ресторан, сравниваем iiko и Wipon. В чём разница?",
    ])

    # 4. Прямая покупка — разные формулировки
    all_results['buy_invoice'] = run_dialog("Хочу счёт", [
        "Здравствуйте, выставьте счёт на Wipon Standard",
    ])

    all_results['buy_demo'] = run_dialog("Хочу демо", [
        "Привет, можно демо Wipon?",
    ])

    # 5. Рассрочка
    all_results['installment'] = run_dialog("Рассрочка", [
        "Здравствуйте",
        "Можно ли в рассрочку оплатить?",
    ])

    # 6. Молчаливый → раскрывается
    all_results['warming_up'] = run_dialog("Разогрев молчуна", [
        "Здравствуйте",
        "Ну, посмотрим",
        "У нас супермаркет в Караганде",
        "Нам нужен учёт товаров и касса",
        "Сколько стоит?",
    ])

    # Analysis
    print(f"\n{'='*70}")
    print("  ИТОГО АНАЛИЗ")
    print(f"{'='*70}")
    issues = analyze_all(all_results)
    total_turns = sum(len(v) for v in all_results.values())
    print(f"\n  Всего ходов: {total_turns}")
    print(f"  Всего проблем: {len(issues)}")
    print(f"{'='*70}")

    with open('/home/corta/crm-sales-bot-fork/results/test_iter4_results.json', 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"  Результаты: results/test_iter4_results.json")


if __name__ == '__main__':
    main()
