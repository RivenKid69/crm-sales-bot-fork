#!/usr/bin/env python3
"""
Stress test: manual dialog scenarios with the autonomous bot.
Run: python3 stress_test.py [scenario_name]
"""
import sys
import os
sys.path.insert(0, '/home/corta/crm-sales-bot-fork')

from src.bot import SalesBot
from src.llm import OllamaLLM
from src.feature_flags import flags
from src.settings import settings

RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
GRAY = "\033[90m"

def make_bot():
    flags.enable_group("phase_0")
    flags.enable_group("phase_1")
    flags.enable_group("phase_2")
    flags.enable_group("phase_3")
    flags.set_override("autonomous_flow", True)
    flags.set_override("tone_semantic_tier2", False)
    settings["retriever"]["use_embeddings"] = False
    llm = OllamaLLM()
    return SalesBot(llm, flow_name='autonomous')


def run_scenario(name, messages, pause_on_issues=True):
    print(f"\n{'='*70}")
    print(f"{BOLD}СЦЕНАРИЙ: {name}{RESET}")
    print('='*70)

    bot = make_bot()
    issues = []

    for i, msg in enumerate(messages):
        print(f"\n{BLUE}[{i+1}] Клиент:{RESET} {msg}")

        try:
            result = bot.process(msg)
        except Exception as e:
            print(f"{RED}[EXCEPTION]: {e}{RESET}")
            issues.append(f"Turn {i+1}: Exception - {e}")
            continue

        response = result.get('response', '[NO RESPONSE]')
        state = result.get('state', '?')
        action = result.get('action', '?')
        spin = result.get('spin_phase', '?')
        tone = result.get('tone', '?')
        score = result.get('lead_score', 0)
        fallback = result.get('fallback_used', False)

        intent = result.get('intent', '?')
        print(f"{GREEN}[{i+1}] Бот:{RESET} {response}")
        print(f"{GRAY}    → state={state} | intent={intent} | action={action} | spin={spin} | tone={tone} | score={score:.2f} | fallback={fallback}{RESET}")

        # Detect potential issues
        if fallback:
            issues.append(f"Turn {i+1}: Fallback triggered (tier={result.get('fallback_tier')})")
            print(f"{YELLOW}    ⚠ FALLBACK used{RESET}")

        if not response or len(response) < 10:
            issues.append(f"Turn {i+1}: Empty/short response")
            print(f"{RED}    ⚠ EMPTY RESPONSE{RESET}")

        if 'sorry' in response.lower() or 'не могу' in response.lower():
            print(f"{YELLOW}    ⚠ Bot says can't/sorry{RESET}")

        if result.get('is_final'):
            print(f"{CYAN}    → TERMINAL STATE{RESET}")
            break

    if issues:
        print(f"\n{YELLOW}ПРОБЛЕМЫ в сценарии '{name}':{RESET}")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n{GREEN}✓ Сценарий прошел чисто{RESET}")

    return issues

# ─── СЦЕНАРИИ ────────────────────────────────────────────────────────────────

SCENARIOS = {

    # 1. Холодный нерешительный — не хочет тратить время
    'cold_skeptic': [
        "Привет",
        "Смотрю ваш сайт, но честно — не стоит тратить время, я не думаю что нам это нужно",
        "У нас и так всё нормально работает",
        "Ну и сколько это стоит вообще?",
        "Дорого. Нам это не по бюджету",
        "Ладно, что вы конкретно предлагаете?",
    ],

    # 2. Готовый покупатель — сразу к делу
    'ready_buyer': [
        "Здравствуйте, хочу купить Wipon для моего магазина",
        "У меня розничный магазин одежды в Алматы, 2 кассы",
        "Сколько будет стоить подключение?",
        "Ок, меня устраивает. Как оплатить?",
        "Вот мой номер для Kaspi: 87771234567",
        "ИИН: 900101300123",
    ],

    # 3. Технический скептик — сыпет вопросами
    'tech_skeptic': [
        "Добрый день, я ИТ-директор сети магазинов",
        "Расскажите об интеграциях с 1С",
        "А с каким именно 1С? 8.3 или 8.2?",
        "Есть ли API для кастомных интеграций?",
        "Как работает офлайн-режим при отсутствии интернета?",
        "Сколько данных хранится локально?",
        "Какая СУБД используется?",
        "Ладно, допустим меня устраивает технически. Какой SLA на поддержку?",
    ],

    # 4. Казахский speaker — мешает языки
    'kazakh_speaker': [
        "Сәлем, мен Wipon туралы білгім келеді",
        "Иә, магазин бар менде, Алматыда",
        "Бағасы қанша?",
        "Ол қымбат емес пе? Рахмет",
        "Жарайды, байланысайық",
    ],

    # 5. Агрессивный — давит и перебивает
    'aggressive': [
        "Алло",
        "Слушайте, у меня нет времени. Просто скажите цену.",
        "Вы опять уходите от ответа! ЦЕНА?",
        "Ладно 15000 — это в месяц или разово?",
        "Это дорого. Я видел у конкурентов дешевле.",
        "У вас есть скидки или нет?",
        "Хорошо, допустим. Но я хочу сначала попробовать бесплатно.",
    ],

    # 6. Человек который уже пользовался — возвращается
    'returning': [
        "Здравствуйте, я уже был вашим клиентом год назад",
        "Мы тогда не продолжили из-за бюджета",
        "Сейчас открываю новую точку в Астане",
        "Что нового появилось за этот год?",
        "А цены выросли?",
        "Ок можем созвониться на этой неделе?",
    ],

    # 7. Сломанный SPIN — клиент уходит от темы
    'off_topic': [
        "Здравствуйте",
        "Вы занимаетесь POS-системами?",
        "А вы вообще казахстанская компания?",
        "Хм. А где ваш офис?",
        "Кстати, вы не знаете хорошего бухгалтера в Алматы?",
        "Ладно это не важно. Расскажите про ваш продукт",
        "А Kaspi-интеграция есть?",
    ],

    # 8. Многоточечный предприниматель
    'multi_store': [
        "Добрый день, у меня 5 магазинов в разных городах",
        "Алматы, Астана, Шымкент, Актобе, Усть-Каменогорск",
        "Мне нужно единое управление всеми точками",
        "Можно смотреть аналитику по каждому городу отдельно?",
        "А что с фискализацией? У нас разные ОФД в разных городах?",
        "Сколько будет стоить на 5 точек?",
        "Есть ли скидка за объем?",
    ],

    # 9. Тихий/неуверенный — мало говорит
    'shy': [
        "Привет",
        "Да",
        "Маленький магазин",
        "Не знаю",
        "Наверное да",
        "Сколько стоит?",
        "Ок",
    ],

    # 10. Возражение по конкурентам
    'competitor': [
        "Здравствуйте",
        "Я уже смотрел iiko и Poster",
        "У Poster дешевле",
        "В iiko больше функций",
        "Чем вы лучше?",
        "А поддержка 24/7 есть?",
        "Хорошо, убедили попробовать. Есть демо?",
    ],

    # 11. Смешанный язык — переключается с казахского на русский
    'lang_switch': [
        "Сәлем, менің сауда нүктем бар",
        "Иә, Алматыда. Қымбат па?",
        "Хорошо, а на русском можно говорить?",
        "У меня небольшой продуктовый магазин",
        "Какие тарифы есть?",
        "Ок, мне подходит. Как начать?",
        "87012345678",
    ],

    # 12. Частичная платёжная информация — даёт kaspi но не IIN
    'partial_payment': [
        "Привет, хочу подключить Wipon",
        "У меня магазин электроники в Астане",
        "Хорошо, давайте оформим",
        "Вот мой номер Kaspi: 87771234567",
        "А зачем вам ИИН? Я не хочу давать",
        "Хорошо ладно: 900101300123",
    ],

    # 13. Клиент с ложными воспоминаниями — утверждает что уже пробовал
    'false_memory': [
        "Здравствуйте",
        "Я уже пробовал Wipon год назад, у вас было очень дорого — 2 миллиона в год",
        "И интерфейс был ужасный",
        "Что-то изменилось с тех пор?",
        "А цены теперь нормальные?",
        "Ладно, расскажите подробнее про тарифы",
    ],

    # 14. Клиент-молчун с неожиданным разворотом
    'silent_pivot': [
        "Добрый день",
        "...",
        "Просто смотрю",
        "Хм",
        "Слушайте, а у вас есть интеграция с Kaspi магазином?",
        "И с WhatsApp?",
        "Интересно. Хочу демо.",
    ],

    # 15. Срочный покупатель — открывается завтра
    'urgent_buyer': [
        "Мне нужно срочно! Открываюсь завтра",
        "Магазин одежды, одна касса",
        "Сколько времени занимает подключение?",
        "То есть за один день реально?",
        "Отлично. Оформляйте.",
        "87771112233",
        "ИИН: 850101450123",
    ],
}

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None

    all_issues = {}

    if target:
        if target in SCENARIOS:
            issues = run_scenario(target, SCENARIOS[target])
            all_issues[target] = issues
        else:
            print(f"Unknown scenario: {target}")
            print(f"Available: {', '.join(SCENARIOS.keys())}")
    else:
        # Run all
        for name, msgs in SCENARIOS.items():
            issues = run_scenario(name, msgs)
            all_issues[name] = issues

    # Summary
    print(f"\n{'='*70}")
    print(f"{BOLD}ИТОГ СТРЕСС-ТЕСТА{RESET}")
    print('='*70)
    total_issues = sum(len(v) for v in all_issues.values())
    print(f"Сценариев: {len(all_issues)} | Проблем: {total_issues}")
    for name, issues in all_issues.items():
        status = f"{GREEN}✓{RESET}" if not issues else f"{RED}✗ ({len(issues)} issues){RESET}"
        print(f"  {status} {name}")
        for issue in issues:
            print(f"      - {issue}")
