#!/usr/bin/env python3
"""
Итерация 3: Комплексная проверка качества диалога.
Фокус: длина ответов, маскулинные формы, повторения, логичность.
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
    """Analyze all dialogs for quality issues."""
    total_issues = []

    for name, results in all_results.items():
        issues = []
        for r in results:
            bot = r['bot']
            bot_low = bot.lower()
            turn = r['turn']

            # 1. Маскулинные формы (должны быть убиты пост-процессором)
            for pat, label in [
                (r'\bрад\b(?!а)', 'рад'), (r'\bготов\b(?!а)', 'готов'),
                (r'\bпонял\b(?!а)', 'понял'), (r'\bподобрал\b(?!а)', 'подобрал'),
                (r'\bуточнил\b(?!а)', 'уточнил'),
            ]:
                if re.search(pat, bot_low):
                    issues.append(f"T{turn}: маскулин '{label}'")

            # 2. Списки (запрещены)
            if re.search(r'(?:^|\n)\s*[-•]\s+\w', bot):
                issues.append(f"T{turn}: буллет-лист")
            if re.search(r'(?:^|\n)\s*\d+[.)]\s+\w', bot):
                issues.append(f"T{turn}: нумерованный список")

            # 3. Слишком длинный ответ (>60 слов — мягкий лимит)
            if r['word_count'] > 60:
                issues.append(f"T{turn}: длинный ответ ({r['word_count']} слов)")

            # 4. Пустой / слишком короткий
            if len(bot) < 15:
                issues.append(f"T{turn}: слишком коротко ({len(bot)} симв.)")

            # 5. Запрещённые фразы
            banned = ['чем могу помочь', 'как вас зовут']
            for b in banned:
                if b in bot_low:
                    issues.append(f"T{turn}: запрещёнка '{b}'")

            # 6. Markdown остатки
            if '**' in bot or '__' in bot:
                issues.append(f"T{turn}: markdown bold")
            if re.search(r'\[.+?\]\(.+?\)', bot):
                issues.append(f"T{turn}: markdown ссылка")

            # 7. Ложные обещания действий (word boundary to avoid подготовила→подготовил)
            action_promise_patterns = [
                (r'\bотправил\b(?!а)', 'отправил'),
                (r'\bзаписал\b(?!а)', 'записал'),
                (r'\bсохранил\b(?!а)', 'сохранил'),
                (r'\bоформил\b(?!а)', 'оформил'),
                (r'\bподготовил\b(?!а)', 'подготовил'),
                (r'\bвыслал\b(?!а)', 'выслал'),
                (r'\bнастроил\b(?!а)', 'настроил'),
            ]
            for pat, label in action_promise_patterns:
                if re.search(pat, bot_low) and 'менеджер' not in bot_low:
                    issues.append(f"T{turn}: обещание действия '{label}'")

            # 8. Эмодзи
            if re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', bot):
                issues.append(f"T{turn}: эмодзи")

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

    # 1. Базовое приветствие
    all_results['greeting'] = run_dialog("Приветствие", [
        "Привет",
    ])

    # 2. Полный цикл: discovery → closing
    all_results['full_cycle'] = run_dialog("Полный цикл", [
        "Здравствуйте",
        "У меня магазин одежды в Алматы, 3 продавца",
        "Какие тарифы есть?",
        "А Lite что включает?",
        "Хорошо, давайте оформим Lite",
    ])

    # 3. Агрессивный → смягчается
    all_results['aggressive'] = run_dialog("Агрессивный клиент", [
        "Здравствуйте",
        "Вы опять звоните? Я уже сказал что мне ничего не нужно!",
        "Перестаньте мне звонить!",
        "Ладно, а что вообще предлагаете?",
        "Ну и сколько это стоит?",
    ])

    # 4. Скептик с возражениями
    all_results['skeptic'] = run_dialog("Скептик", [
        "Добрый день",
        "У меня аптека, 10 сотрудников",
        "А чем вы лучше конкурентов?",
        "Не верю, все так говорят",
        "А если не понравится?",
    ])

    # 5. Off-topic вопросы
    all_results['offtopic'] = run_dialog("Off-topic", [
        "Привет",
        "А вы случайно не знаете курс доллара?",
        "Ладно, а что такое Wipon?",
        "А можно через вас заказать пиццу?",
    ])

    # 6. Длинный диалог (повторения, стагнация)
    all_results['long_dialog'] = run_dialog("Длинный диалог", [
        "Здравствуйте",
        "У нас кафе в Шымкенте, 7 официантов",
        "Какие тарифы?",
        "А Mini что включает?",
        "А Lite?",
        "А Standard?",
        "А Pro?",
        "Нам нужна касса, учёт и Kaspi. Что порекомендуете?",
        "Хорошо, а есть ли рассрочка?",
        "Давайте оформим Lite",
    ])

    # 7. Клиент сразу даёт контакт
    all_results['direct_contact'] = run_dialog("Прямой контакт", [
        "Здравствуйте, вот мой номер 87071234567. Когда перезвоните?",
    ])

    # 8. Переключение тем
    all_results['topic_switch'] = run_dialog("Переключение тем", [
        "Привет",
        "Есть ли у вас складской учёт?",
        "Стоп, а сколько стоит?",
        "А поддержка 24/7?",
        "Вернёмся к складу — как он работает?",
    ])

    # 9. Прямая покупка с 1-го сообщения
    all_results['direct_buy'] = run_dialog("Прямая покупка", [
        "Здравствуйте, хочу подключить Wipon. Куда платить?",
    ])

    # 10. Клиент в печали / фрустрации
    all_results['frustrated'] = run_dialog("Фрустрированный клиент", [
        "Здравствуйте",
        "У нас постоянные проблемы с учётом, всё теряется",
        "Уже 3 раза меняли систему, ничего не помогает",
        "А у вас точно не так же будет?",
    ])

    # 11. Клиент-молчун (короткие ответы)
    all_results['silent'] = run_dialog("Молчун", [
        "Да",
        "Ага",
        "Нет",
        "Не знаю",
        "Может быть",
    ])

    # 12. Клиент спрашивает про конкурентов
    all_results['competitor'] = run_dialog("Конкуренты", [
        "Здравствуйте",
        "А чем вы отличаетесь от Poster?",
        "А от iiko?",
        "У них дешевле",
    ])

    # Анализ
    print(f"\n{'='*70}")
    print("  ИТОГО АНАЛИЗ")
    print(f"{'='*70}")
    issues = analyze_all(all_results)

    total_turns = sum(len(v) for v in all_results.values())
    print(f"\n  Всего ходов: {total_turns}")
    print(f"  Всего проблем: {len(issues)}")
    print(f"{'='*70}")

    with open('/home/corta/crm-sales-bot-fork/results/test_iter3_results.json', 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"  Результаты: results/test_iter3_results.json")


if __name__ == '__main__':
    main()
