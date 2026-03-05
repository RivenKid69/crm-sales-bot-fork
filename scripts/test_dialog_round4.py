#!/usr/bin/env python3
"""
Раунд 4: Реалистичные сложные диалоги для обычных клиентов.
Без фантастических сценариев — только реальные ситуации из KZ ритейла.
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


def check_issues(results):
    issues = []
    for r in results:
        bot = r['bot']
        bot_low = bot.lower()
        t = r['turn']

        # Маскулинные формы
        for pat, label in [
            (r'\bрад\b(?!а)', 'рад'), (r'\bготов\b(?!а)', 'готов'),
            (r'\bпонял\b(?!а)', 'понял'), (r'\bподобрал\b(?!а)', 'подобрал'),
            (r'\bуточнил\b(?!а)', 'уточнил'),
        ]:
            if re.search(pat, bot_low):
                issues.append(f"T{t}: МУЖ.РОД '{label}'")

        # Списки / markdown
        if re.search(r'(?:^|\n)\s*[-•]\s+\w', bot):
            issues.append(f"T{t}: буллет-лист")
        if re.search(r'(?:^|\n)\s*\d+[.)]\s+\w', bot):
            issues.append(f"T{t}: нумерованный список")
        if '**' in bot or '__' in bot:
            issues.append(f"T{t}: markdown bold")

        # Длина
        if r['word_count'] > 60:
            issues.append(f"T{t}: длинный ({r['word_count']} слов)")

        # 24/7 ложь
        if re.search(r'круглосуточн|24\s*/?\s*7', bot_low):
            issues.append(f"T{t}: ложь 24/7")

        # Демо/тест/пробный
        if 'демо' in bot_low:
            issues.append(f"T{t}: ДЕМО")
        if re.search(r'тестов\w+\s+(?:доступ|период|верси)', bot_low):
            issues.append(f"T{t}: ТЕСТОВЫЙ ДОСТУП")
        if re.search(r'пробн\w+\s+(?:период|верси|доступ)', bot_low):
            issues.append(f"T{t}: ПРОБНЫЙ")

        # Видео-звонок
        if re.search(r'видео[-\s]?\w+', bot_low):
            issues.append(f"T{t}: видео-звонок")

        # Метанарратив
        if re.search(r'(?:Цель|Примечание|Комментарий)\s*:', bot):
            issues.append(f"T{t}: метанарратив")

        # "менеджер свяжется" (должно быть "коллега")
        if re.search(r'менеджер\s+свяжется', bot_low):
            issues.append(f"T{t}: МЕНЕДЖЕР СВЯЖЕТСЯ")
        # "нет демо" (не должны говорить что нет)
        if 'нет демо' in bot_low or 'нет тестов' in bot_low:
            issues.append(f"T{t}: ГОВОРИТ НЕТ ДЕМО")

        # Цены — проверяем что не путает год/месяц (sentence-level, не через весь текст)
        for sent in re.split(r'[.!?]+', bot_low):
            s = sent.strip()
            if re.search(r'(?:150|220|500)\s*000', s) and 'мес' in s and 'год' not in s:
                issues.append(f"T{t}: ЦЕНА ГОД→МЕСЯЦ ('{s[:60]}...')")
            if re.search(r'5\s*000', s) and 'mini' in s and 'год' in s and 'мес' not in s:
                issues.append(f"T{t}: Mini цена год (должно быть мес)")

    return issues


# ============================================================
# СЦЕНАРИИ
# ============================================================

SCENARIOS = {}

# 25: Нетерпеливый клиент — хочет цену сразу
SCENARIOS["25_нетерпеливый_цена"] = [
    "Здравствуйте, сколько стоит ваша программа?",
    "У меня магазин продуктов, цену скажите",
    "Один магазин, мне не нужна консультация, просто цену скажите",
    "Ладно, а какая разница между Mini и Lite?",
    "Standard на 3 точки подойдет? Или нужно Pro?",
]

# 26: Клиент сравнивает тарифы
SCENARIOS["26_сравнение_тарифов"] = [
    "Привет, какие тарифы есть?",
    "А что входит в каждый? Мне нужен учет товаров и аналитика",
    "У меня 2 магазина одежды и склад, что посоветуете?",
    "А сколько стоит Standard? И можно ли потом перейти на Pro?",
    "Хорошо, давайте Standard. Как подключиться?",
]

# 27: Сомневающийся клиент — дорого, надо подумать
SCENARIOS["27_сомневающийся"] = [
    "Салем, у меня аптека, нужна автоматизация",
    "Да, учет остатков, маркировка, касса. Сколько стоит?",
    "Это дорого для одной точки, мне надо подумать",
    "А есть рассрочка?",
    "Ладно, перезвоните мне, номер 87071234567",
]

# 28: Конкретный запрос — склад + касса
SCENARIOS["28_конкретный_запрос"] = [
    "Здравствуйте, мне нужна программа для учета товаров на складе и POS-касса",
    "У меня 2 магазина электроники в Алматы",
    "Какой тариф подойдет для двух точек с учетом на складе?",
    "Ок, давайте Standard. Куда платить?",
    "ИИН 870515300123, каспи телефон 87075554433",
]

# 29: Рассрочка и оплата через Kaspi
SCENARIOS["29_рассрочка_kaspi"] = [
    "Здравствуйте, есть ли у вас рассрочка?",
    "Магазин строительных материалов, одна точка",
    "Мне нужен тариф с аналитикой, какие варианты?",
    "А Lite можно в рассрочку? Через Kaspi?",
    "Хорошо, давайте оформим. 87012223344",
]

# 30: Клиент с большим количеством точек — нужен ТИС
SCENARIOS["30_много_точек_тис"] = [
    "Здравствуйте, у нас сеть из 8 магазинов по Казахстану",
    "Да, Алматы, Астана, Караганда, Шымкент. Нужна единая система",
    "Какой тариф подойдет для 8 точек?",
    "А что такое ТИС? И сколько это стоит?",
    "Хорошо, оставлю номер: 87015556677",
]

# 31: Клиент меняет решение — сначала Mini, потом хочет больше
SCENARIOS["31_апгрейд_решения"] = [
    "Привет, мне нужен самый простой тариф, у меня одна точка",
    "Продуктовый магазин, 50 кв.м., я один работаю",
    "А можно Mini потом обновить до Standard если бизнес вырастет?",
    "А какие функции я потеряю на Mini по сравнению с Lite?",
    "Ладно, давайте начнём с Lite. Как оформить?",
]

# 32: Клиент не понимает что такое Wipon — нужно объяснить
SCENARIOS["32_что_это"] = [
    "Мне друг посоветовал Wipon, но я не понимаю что это",
    "У меня небольшой магазин обуви",
    "А, это как 1С? Или что-то другое?",
    "Понятно. А оборудование нужно какое-то покупать?",
    "Ладно, пусть менеджер позвонит. 87021112233",
]

# 33: Клиент торопится — хочет быстро
SCENARIOS["33_быстро_подключить"] = [
    "Нужно подключить кассу срочно, у меня открытие через неделю",
    "Кофейня в Астане, одна точка",
    "Мне нужна касса с Kaspi QR и учет продуктов",
    "Какой тариф и сколько? Быстро можно подключить?",
    "Давайте Standard, вот мой номер 87079998877, ИИН 950712350456",
]

# 34: Клиент расспрашивает подробно про функции
SCENARIOS["34_подробные_функции"] = [
    "Здравствуйте, расскажите подробнее про учёт товаров",
    "А маркировка товаров поддерживается? Мне нужно для аптеки",
    "А можно ли настроить автозакупки когда товар заканчивается?",
    "А есть мобильное приложение для проверки остатков?",
    "Интересно, сколько стоит Standard для одной аптеки?",
    "Хорошо, подключайте. Телефон 87051119988",
]


if __name__ == '__main__':
    all_results = {}
    all_issues = {}

    for name, msgs in SCENARIOS.items():
        results = run_dialog(name, msgs)
        all_results[name] = results
        issues = check_issues(results)
        all_issues[name] = issues

    # Summary
    print(f"\n\n{'='*70}")
    print("  ИТОГО")
    print(f"{'='*70}")
    total_ok = 0
    total_bad = 0
    for name, issues in all_issues.items():
        if issues:
            total_bad += 1
            print(f"\n  ❌ {name}:")
            for iss in issues:
                print(f"     - {iss}")
        else:
            total_ok += 1
            print(f"  ✅ {name}: чисто")

    print(f"\n  Результат: {total_ok}/{total_ok+total_bad} чистых")

    # Save
    with open('/home/corta/crm-sales-bot-fork/results/dialog_round4.json', 'w') as f:
        json.dump({'results': all_results, 'issues': all_issues}, f, ensure_ascii=False, indent=2)
    print("  Сохранено: results/dialog_round4.json")
