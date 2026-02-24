#!/usr/bin/env python3
"""
Итерация 2: Расширенные нестандартные диалоги.
- Агрессивный клиент
- Клиент-скептик
- Клиент с Kazakh noise
- Клиент который задаёт вопросы не по теме
- Длинный диалог (10+ ходов)
- Клиент который сразу даёт контакт
"""
import sys
import json
import time
sys.path.insert(0, '/home/corta/crm-sales-bot-fork')

from src.bot import SalesBot
from src.llm import OllamaClient

_llm = OllamaClient()

def run_dialog(name, messages, verbose=True):
    print(f"\n{'='*70}")
    print(f"  СЦЕНАРИЙ: {name}")
    print(f"{'='*70}")
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


def analyze_dialog(results, name):
    """Analyze dialog for quality issues."""
    issues = []
    import re

    for r in results:
        bot = r['bot']
        bot_low = bot.lower()

        # Маскулинные формы
        for pat, label in [
            (r'\bрад\b(?!а)', 'рад'), (r'\bготов\b(?!а)', 'готов'),
            (r'\bпонял\b(?!а)', 'понял'), (r'\bподобрал\b(?!а)', 'подобрал'),
        ]:
            if re.search(pat, bot_low):
                issues.append(f"T{r['turn']}: маскулин '{label}'")

        # Списки (- item, • item, 1. item)
        if re.search(r'(?:^|\n)\s*[-•]\s+\w', bot) or re.search(r'(?:^|\n)\s*\d+\.\s+\w', bot):
            issues.append(f"T{r['turn']}: буллет-лист в ответе")

        # Слишком длинный ответ
        if r['word_count'] > 70:
            issues.append(f"T{r['turn']}: слишком длинный ({r['word_count']} слов)")

        # Запрещённые фразы
        banned = ['отлично!', 'чем могу помочь?', 'как вас зовут']
        for b in banned:
            if b in bot_low:
                issues.append(f"T{r['turn']}: запрещённая фраза '{b}'")

        # Упоминание конкурентов
        competitors = ['1с', 'битрикс', 'wisepos', 'wms']
        for c in competitors:
            # Only flag if it's a recommendation, not answering about integration
            if c in bot_low and r['intent'] not in ('question_integrations', 'question_features'):
                if 'интеграц' not in bot_low and 'совместим' not in bot_low:
                    issues.append(f"T{r['turn']}: упомянут конкурент '{c}'")

        # Пустой или слишком короткий ответ
        if len(bot) < 20:
            issues.append(f"T{r['turn']}: слишком короткий ответ ({len(bot)} символов)")

    if issues:
        print(f"\n  ⚠️  ПРОБЛЕМЫ ({name}):")
        for i in issues:
            print(f"    - {i}")
    else:
        print(f"\n  ✅ {name}: всё ОК")

    return issues


def main():
    all_results = {}
    all_issues = {}

    # 1. Агрессивный клиент
    r = run_dialog("Агрессивный клиент", [
        "Здравствуйте",
        "Вы опять звоните? Я уже сказал что мне ничего не нужно!",
        "Перестаньте мне звонить!",
        "Ладно, а что вообще предлагаете?",
        "Ну и сколько это стоит?",
    ])
    all_results['aggressive'] = r
    all_issues['aggressive'] = analyze_dialog(r, "Агрессивный")

    # 2. Скептик
    r = run_dialog("Скептик", [
        "Добрый день",
        "У меня аптека, 10 сотрудников",
        "А чем вы лучше Poster или iiko?",
        "Не верю, все так говорят",
        "А если мне не понравится, могу вернуть деньги?",
    ])
    all_results['skeptic'] = r
    all_issues['skeptic'] = analyze_dialog(r, "Скептик")

    # 3. Казахский с noise
    r = run_dialog("Казахский клиент", [
        "Сәлеметсіз бе",
        "Менде кішкентай дүкен бар",
        "Бағасы қанша?",
        "Рахмет, ойланамын",
    ])
    all_results['kazakh'] = r
    all_issues['kazakh'] = analyze_dialog(r, "Казахский")

    # 4. Off-topic вопросы
    r = run_dialog("Off-topic клиент", [
        "Привет",
        "А вы случайно не знаете курс доллара?",
        "Ладно, а что такое Wipon?",
        "А можно ли через вас заказать пиццу?",
    ])
    all_results['offtopic'] = r
    all_issues['offtopic'] = analyze_dialog(r, "Off-topic")

    # 5. Длинный диалог (стресс-тест на повторения)
    r = run_dialog("Длинный диалог", [
        "Здравствуйте",
        "У нас кафе в Шымкенте, 7 официантов",
        "Какие тарифы у вас есть?",
        "А Mini что включает?",
        "А Lite?",
        "А Standard?",
        "А Pro?",
        "Нам нужна касса, учёт и Kaspi. Что порекомендуете?",
        "Хорошо, а есть ли рассрочка?",
        "Давайте оформим Lite",
    ])
    all_results['long_dialog'] = r
    all_issues['long_dialog'] = analyze_dialog(r, "Длинный диалог")

    # 6. Клиент сразу даёт контакт
    r = run_dialog("Прямой контакт", [
        "Здравствуйте, вот мой номер 87071234567. Когда можете перезвонить?",
    ])
    all_results['direct_contact'] = r
    all_issues['direct_contact'] = analyze_dialog(r, "Прямой контакт")

    # 7. Клиент переключается между темами
    r = run_dialog("Переключение тем", [
        "Привет",
        "А есть ли у вас склад?",
        "Стоп, а сколько стоит?",
        "А поддержка 24/7?",
        "Вернёмся к складу — как он работает?",
    ])
    all_results['topic_switch'] = r
    all_issues['topic_switch'] = analyze_dialog(r, "Переключение тем")

    # Summary
    print(f"\n{'='*70}")
    print(f"  ИТОГО:")
    total_issues = sum(len(v) for v in all_issues.values())
    total_turns = sum(len(v) for v in all_results.values())
    print(f"  Всего ходов: {total_turns}")
    print(f"  Всего проблем: {total_issues}")
    for name, issues in all_issues.items():
        status = "✅" if not issues else f"⚠️ ({len(issues)})"
        print(f"    {name}: {status}")
    print(f"{'='*70}")

    with open('/home/corta/crm-sales-bot-fork/results/test_iter2_results.json', 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"  Результаты: results/test_iter2_results.json")


if __name__ == '__main__':
    main()
