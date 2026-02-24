"""
Итерационный тест качества диалогов — программные сценарии.
Каждый сценарий: серия сообщений клиента → анализ ответов бота.
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import OllamaLLM
from src.bot import SalesBot


def run_scenario(name: str, messages: list[str], flow: str = "autonomous") -> list[dict]:
    """Прогнать один сценарий и вернуть результаты."""
    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name=flow, enable_tracing=True)
    results = []

    print(f"\n{'='*70}")
    print(f"СЦЕНАРИЙ: {name}")
    print(f"{'='*70}")

    for i, msg in enumerate(messages):
        print(f"\n--- Ход {i+1} ---")
        print(f"Клиент: {msg}")

        result = bot.process(msg)

        response = result.get("response", "")
        state = result.get("state", "")
        intent = result.get("intent", "")
        action = result.get("action", "")
        spin = result.get("spin_phase", "")
        score = result.get("lead_score", 0)
        is_final = result.get("is_final", False)

        print(f"Бот: {response}")
        print(f"  [state={state} | intent={intent} | action={action} | spin={spin} | score={score}]")

        results.append({
            "turn": i + 1,
            "user": msg,
            "bot": response,
            "state": state,
            "intent": intent,
            "action": action,
            "spin_phase": spin,
            "lead_score": score,
            "is_final": is_final,
            "word_count": len(response.split()),
        })

        if is_final:
            print(f"\n  >>> ТЕРМИНАЛЬНОЕ СОСТОЯНИЕ: {state}")
            break

    return results


SCENARIOS = {
    # 1. Обычный happy path — открытый клиент
    "happy_path": [
        "Здравствуйте",
        "У меня 3 магазина одежды в Алматы, ищу кассовую систему",
        "Сейчас на бумаге всё, кассовые аппараты старые, учёт в тетрадке",
        "Да, основная боль — не знаю точно что на складе, постоянные пересорты",
        "Сколько стоит для 3 магазинов?",
        "А можно попробовать бесплатно?",
        "Давайте запишемся на демо. Мой номер 87071234567",
    ],

    # 2. Клиент сразу спрашивает цену без контекста
    "price_first": [
        "Сколько стоит ваша система?",
        "Мне нужно на 5 касс, точнее даже 5 точек по 1 кассе",
        "А почему так дорого? У конкурентов дешевле",
        "Какие конкретно есть тарифы?",
        "Мне нужен самый базовый без наворотов",
    ],

    # 3. Скептик / tire_kicker — не верит, сомневается
    "skeptic": [
        "Привет",
        "Мне друг посоветовал, но я не особо верю в эти системы",
        "У нас маленький магазинчик, 1 точка, зачем мне вообще POS?",
        "Мы и так нормально работаем, зачем тратить деньги?",
        "Ну допустим, а что будет если интернет пропадёт?",
        "Не знаю, надо подумать. Не давите",
    ],

    # 4. Агрессивный клиент
    "aggressive": [
        "Мне ваш менеджер уже 3 раза звонил, задолбали",
        "Я сказал не звоните! Зачем вы опять пишете?",
        "Ладно, раз уж написали — что конкретно вы предлагаете и за сколько?",
        "Это дорого, мне таких денег жалко на непонятно что",
    ],

    # 5. Казахский язык / смешение
    "kazakh_mixed": [
        "Сәлеметсіз бе",
        "Маған POS жүйе керек, 2 дүкен бар Астанада",
        "Бағасы қанша?",
        "Рахмет, ойланамын",
    ],

    # 6. Клиент меняет тему / уходит от продажи
    "topic_changer": [
        "Здравствуйте, я хочу узнать про вашу систему",
        "А вы вообще давно на рынке? Кто ваши клиенты?",
        "А какие у вас серверы? Где хранятся данные?",
        "Ой, кстати, а вы не знаете хороший магазин обуви в Алматы?",
        "Ладно, вернёмся к делу. Мне нужна касса для кофейни",
    ],

    # 7. Клиент даёт мало информации — проверка discovery
    "minimal_info": [
        "Привет",
        "Нужна касса",
        "Да",
        "Не знаю",
        "Ну расскажите что у вас есть",
    ],

    # 8. Возврат к теме цены после возражений
    "price_objection_loop": [
        "Здравствуйте, сколько стоит POS система?",
        "Это слишком дорого для нас",
        "А есть рассрочка?",
        "А можно дешевле если на год оплатить?",
        "Ладно, какие документы нужны для оформления?",
    ],

    # 9. Ready buyer — хочет купить сразу
    "ready_buyer": [
        "Мне нужен Wipon Mini на 2 кассы, готов оплатить сейчас",
        "ИИН 123456789012, Kaspi номер 87071112233",
        "Да, оформляйте",
    ],

    # 10. Длинное сообщение с кучей информации
    "info_dump": [
        "Здравствуйте, меня зовут Аскар, у меня сеть из 10 продуктовых магазинов в Шымкенте и Туркестане, сейчас используем 1С но она постоянно глючит и не интегрируется с Kaspi, нам нужна система которая будет работать с маркировкой, вести складской учёт, и чтобы я мог видеть аналитику по всем точкам с телефона. Бюджет примерно 500 тысяч тенге в год. Что посоветуете?",
    ],
}


def main():
    all_results = {}

    # Если передан аргумент — запускаем только конкретный сценарий
    if len(sys.argv) > 1:
        scenario_names = sys.argv[1:]
    else:
        scenario_names = list(SCENARIOS.keys())

    for name in scenario_names:
        if name not in SCENARIOS:
            print(f"Сценарий '{name}' не найден. Доступные: {list(SCENARIOS.keys())}")
            continue
        try:
            results = run_scenario(name, SCENARIOS[name])
            all_results[name] = results
        except Exception as e:
            print(f"\nОШИБКА в сценарии {name}: {e}")
            import traceback
            traceback.print_exc()
            all_results[name] = [{"error": str(e)}]

    # Сохранить результаты
    output_path = "results/dialog_quality_iter1.json"
    os.makedirs("results", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n\nРезультаты сохранены в {output_path}")

    # Краткая сводка
    print(f"\n{'='*70}")
    print("СВОДКА")
    print(f"{'='*70}")
    for name, results in all_results.items():
        if results and "error" not in results[0]:
            turns = len(results)
            final = results[-1].get("is_final", False)
            final_state = results[-1].get("state", "?")
            avg_words = sum(r.get("word_count", 0) for r in results) / max(turns, 1)
            print(f"  {name}: {turns} ходов, final={final} ({final_state}), avg_words={avg_words:.0f}")
        else:
            print(f"  {name}: ОШИБКА")


if __name__ == "__main__":
    main()
