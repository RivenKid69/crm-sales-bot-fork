"""
Тест контекста и памяти диалога.
10 сложных сценариев — проверяет помнит ли бот детали из предыдущих ходов,
избегает ли повторных вопросов, корректно ли обрабатывает ссылки на прошлое.

Для каждого хода — аннотации что проверяется. Итог: автоматический подсчёт
нарушений памяти + финальный вердикт по каждому сценарию.
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.bot import SalesBot, setup_autonomous_pipeline
from src.llm import OllamaLLM

DIVIDER = "─" * 72

# ─────────────────────────────────────────────────────────────────────────────
# 10 СЦЕНАРИЕВ ДЛЯ ПРОВЕРКИ КОНТЕКСТА И ПАМЯТИ
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = [

    # ── C01: Накопление деталей → бот должен дать персонализированный совет ──
    {
        "id": "C01",
        "name": "Накопление деталей — бот должен помнить ВСЕ три факта",
        "description": (
            "Клиент по одному сообщает: 1) тип бизнеса (аптека), "
            "2) кол-во касс (2), 3) бюджет (~5000₸/мес). "
            "В ходу 5 просит рекомендацию — бот должен ответить БЕЗ "
            "переспрашивания, ссылаясь на все три детали."
        ),
        "turns": [
            {
                "user": "Здравствуйте, хочу узнать о вашей системе",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Приветствие — нейтрально",
            },
            {
                "user": "У меня аптека в Алматы",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Бот принял тип бизнеса",
            },
            {
                "user": "Работаем на 2 кассах, пока небольшая точка",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Бот принял кол-во касс",
            },
            {
                "user": "Бюджет у нас скромный — около 5000 тенге в месяц",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Бот принял бюджет",
            },
            {
                "user": "Ну так что вы мне порекомендуете?",
                "check_not_in_bot": ["какой у вас бизнес", "расскажите о вашем бизнесе",
                                      "сколько касс", "какой бюджет"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ МОМЕНТ: бот НЕ должен переспрашивать уже известные данные. "
                        "Должен дать конкретный совет с учётом аптека+2 кассы+~5000₸.",
            },
        ],
    },

    # ── C02: Коррекция данных — бот должен обновить и использовать новое значение ──
    {
        "id": "C02",
        "name": "Коррекция данных — бот должен принять исправление",
        "description": (
            "Клиент сначала говорит '3 кассы', потом исправляется '5 касс'. "
            "В следующем ходу бот должен опираться на 5, а не 3."
        ),
        "turns": [
            {
                "user": "Добрый день! У меня магазин электроники",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт",
            },
            {
                "user": "Работаем на 3 кассах в торговом центре",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Первое значение: 3 кассы",
            },
            {
                "user": "Сколько стоит ваш тариф Lite?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Вопрос о цене",
            },
            {
                "user": "Кстати, я оговорился — у нас не 3, а 5 касс. Исправьте",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Клиент исправляет — бот должен принять корректно",
            },
            {
                "user": "Так сколько выйдет для нас всего?",
                "check_not_in_bot": ["3 касс", "3-х касс", "три кассы"],
                "check_in_bot": ["5"],
                "note": "КЛЮЧЕВОЙ: бот должен считать для 5 касс, не 3",
            },
        ],
    },

    # ── C03: Ссылка на ранее упомянутый тариф ──
    {
        "id": "C03",
        "name": "Неявная ссылка на упомянутый продукт",
        "description": (
            "Бот в одном из ходов упоминает тариф Standard. "
            "Потом клиент говорит 'тот вариант что вы упоминали' — "
            "бот должен правильно идентифицировать что речь о Standard."
        ),
        "turns": [
            {
                "user": "Привет, у меня продуктовый магазин, 1 касса",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт",
            },
            {
                "user": "Расскажите про тариф Standard",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Спрашивает про Standard — бот рассказывает",
            },
            {
                "user": "Понял. А ещё у вас есть что-то для сетей?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Уходит на другую тему",
            },
            {
                "user": "Хорошо, но мне всё равно ближе тот первый вариант что вы упоминали",
                "check_not_in_bot": ["какой вариант", "уточните какой"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: бот должен понять что 'первый вариант' = Standard (уже обсуждался), "
                        "НЕ переспрашивать 'что именно вы имеете в виду'",
            },
            {
                "user": "Ладно, давайте оформим именно его",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Готов купить — должен перейти к закрытию",
            },
        ],
    },

    # ── C04: Ранний факт — должен использоваться в конце длинного диалога ──
    {
        "id": "C04",
        "name": "Длинный диалог — ранний факт используется в ходу 8",
        "description": (
            "Клиент сообщает ИМЯ в самом начале ('Меня зовут Айдар'). "
            "После 6 ходов про продукт — в конце бот должен всё ещё помнить "
            "имя и использовать его (или хотя бы не переспрашивать)."
        ),
        "turns": [
            {
                "user": "Здравствуйте, меня зовут Айдар, у меня кафе в Нур-Султане",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Клиент назвал имя 'Айдар' и город",
            },
            {
                "user": "Сколько у вас тарифов?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Нейтральный вопрос",
            },
            {
                "user": "Чем Mini отличается от Lite?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Сравнение тарифов",
            },
            {
                "user": "Есть ли у вас интеграция с iiko?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Технический вопрос",
            },
            {
                "user": "Хорошо, а как насчёт поддержки?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Вопрос о поддержке",
            },
            {
                "user": "Сколько стоит на год для кафе?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Ценовой вопрос (6-й ход)",
            },
            {
                "user": "Понятно. Что нужно для подключения?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "7-й ход",
            },
            {
                "user": "Расскажите ещё раз кратко — что мне как владельцу кафе даёт ваша система?",
                "check_not_in_bot": ["как вас зовут", "ваше имя", "расскажите о себе"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: бот НЕ должен переспрашивать имя/кафе. "
                        "Хорошо если упомянет 'кафе в Нур-Султане' или 'Айдар' — контекст сохранён.",
            },
        ],
    },

    # ── C05: Многоступенчатые возражения — возврат к пропущенному ──
    {
        "id": "C05",
        "name": "Возврат к необработанному возражению",
        "description": (
            "Клиент поднимает возражение про ЦЕНУ (ход 2), бот отвечает. "
            "Потом клиент возражает про НАДЁЖНОСТЬ (ход 4), бот отвечает. "
            "В ходу 6 клиент говорит 'про цену вы толком не ответили' — "
            "бот должен помнить и ответить развёрнуто."
        ),
        "turns": [
            {
                "user": "Здравствуйте, рассматриваю вашу систему для сети из 3 магазинов",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт — клиент сразу даёт контекст: 3 магазина",
            },
            {
                "user": "Это дорого. Я нашёл похожее за 2000₸ в месяц",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Возражение по цене",
            },
            {
                "user": "Ладно, допустим. Но насколько надёжна ваша система? Вы же облако?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Новое возражение — надёжность/облако",
            },
            {
                "user": "А если интернет пропадёт на кассе — что будет?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Развитие возражения про надёжность",
            },
            {
                "user": "Про надёжность понял. Но к цене я вернусь — вы так и не объяснили "
                         "почему ваши 2000₸ в месяц лучше чем то что я нашёл",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: клиент возвращается к цене. Бот должен помнить "
                        "что уже обсуждали цену и дать развёрнутый ответ, не говорить "
                        "'расскажите что вы нашли' как будто это впервые.",
            },
        ],
    },

    # ── C06: Данные по частям — должны аккумулироваться ──
    {
        "id": "C06",
        "name": "Сбор контактных данных по частям",
        "description": (
            "Клиент в разных ходах сообщает: телефон (ход 3), "
            "ИИН (ход 5). Бот должен подтвердить оба когда они получены, "
            "не переспрашивать ранее полученные данные."
        ),
        "turns": [
            {
                "user": "Хочу подключить Standard для магазина",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт — намерение купить",
            },
            {
                "user": "Да, давайте оформим",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Подтверждение — должен запросить контакты",
            },
            {
                "user": "Мой номер 87012345678",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Даёт телефон — бот должен принять",
            },
            {
                "user": "Есть ещё вопрос — а рассрочка есть?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Отвлекается на вопрос — нормально",
            },
            {
                "user": "Понял. Мой ИИН: 850615300456",
                "check_not_in_bot": ["телефон", "номер телефона"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: Даёт ИИН. Бот НЕ должен снова спрашивать телефон "
                        "(уже получен в ходу 3).",
            },
        ],
    },

    # ── C07: Смена языка — контекст должен сохраняться ──
    {
        "id": "C07",
        "name": "Смена языка — казахский → русский, контекст сохраняется",
        "description": (
            "Клиент начинает на казахском, даёт детали бизнеса. "
            "Потом переходит на русский и продолжает диалог. "
            "Бот должен сохранить всё что узнал на казахском, "
            "не переспрашивать заново."
        ),
        "turns": [
            {
                "user": "Сәлем, маған кассалық жүйе керек",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Приветствие на казахском",
            },
            {
                "user": "Менің дүкенім Шымкентте, 3 касса бар",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Даёт город (Шымкент) и 3 кассы на казахском",
            },
            {
                "user": "Бағасы қанша?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Вопрос о цене на казахском",
            },
            {
                "user": "Окей, теперь по-русски. Расскажите подробнее про функционал",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Переходит на русский",
            },
            {
                "user": "И что мне конкретно подойдёт для моей ситуации?",
                "check_not_in_bot": ["где находится", "сколько касс у вас",
                                      "расскажите о своём бизнесе"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: бот должен помнить Шымкент + 3 кассы из казахских ходов, "
                        "НЕ переспрашивать.",
            },
        ],
    },

    # ── C08: Клиент намекнул на проблему — бот должен использовать позже ──
    {
        "id": "C08",
        "name": "Неявно озвученная боль — бот должен к ней вернуться",
        "description": (
            "В ходу 2 клиент мельком упоминает 'проблемы с инвентаризацией'. "
            "Это не прямой вопрос, бот мог проигнорировать. "
            "В ходу 5 бот должен сам вернуться к этой боли."
        ),
        "turns": [
            {
                "user": "Добрый день, рассматриваю варианты для магазина стройматериалов",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт",
            },
            {
                "user": "Основная проблема у нас — постоянный бардак с инвентаризацией, "
                         "не знаем что на складе. Ну и касса конечно нужна",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Клиент упомянул боль: инвентаризация",
            },
            {
                "user": "Сколько стоит?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Уходит на цену",
            },
            {
                "user": "Это приемлемо. А как насчёт интеграции с 1С?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Технический вопрос",
            },
            {
                "user": "Понятно. Что ещё порекомендуете для нашего магазина?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: бот в идеале должен упомянуть 'учёт остатков' или "
                        "'инвентаризация' — связывая с ранее упомянутой болью клиента. "
                        "Проверяем что боль не забыта.",
            },
        ],
    },

    # ── C09: Клиент возвращается к теме которую бот пропустил ──
    {
        "id": "C09",
        "name": "Клиент настаивает на пропущенном вопросе",
        "description": (
            "В ходу 1 клиент задаёт два вопроса. Бот отвечает только на один. "
            "В ходу 3 клиент напоминает о втором вопросе. "
            "Бот должен ответить, не делать вид что вопроса не было."
        ),
        "turns": [
            {
                "user": "Здравствуйте. Два вопроса сразу: 1) есть ли у вас offline-режим? "
                         "2) поддерживаете ли вы маркировку товаров?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "2 вопроса одновременно — бот может ответить на оба или на один",
            },
            {
                "user": "Понял насчёт offline. А про маркировку вы не ответили",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Клиент напоминает о пропущенном вопросе",
            },
            {
                "user": "Хорошо. И ещё — у меня магазин одежды, есть ли специфика для fashion?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Новый вопрос + контекст бизнеса",
            },
            {
                "user": "Окей. Насчёт offline — вы говорили что есть. Как долго работает без сети?",
                "check_not_in_bot": ["не уточнял", "не помню что говорил"],
                "check_in_bot": [],
                "note": "КЛЮЧЕВОЙ: бот должен ответить на уточнение про offline "
                        "помня что уже обсуждали это. НЕ отрицать что говорил про offline.",
            },
        ],
    },

    # ── C10: Противоречие в данных — бот замечает или обновляет ──
    {
        "id": "C10",
        "name": "Противоречие между ранее сказанным и текущим сообщением",
        "description": (
            "Клиент в ходу 2 говорит 'у меня 1 магазин'. "
            "В ходу 5 говорит 'надо для всех наших 4 точек'. "
            "Бот должен корректно адаптироваться — не игнорировать противоречие "
            "и не застрять на старом числе."
        ),
        "turns": [
            {
                "user": "Добрый день, хочу узнать про вашу кассовую систему",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Старт",
            },
            {
                "user": "У меня один магазин товаров для дома в Астане",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Говорит: 1 магазин",
            },
            {
                "user": "Какой тариф подойдёт?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Запрос рекомендации — должен дать для 1 точки",
            },
            {
                "user": "Понятно. А есть скидки при длительной подписке?",
                "check_not_in_bot": [],
                "check_in_bot": [],
                "note": "Вопрос о скидках",
            },
            {
                "user": "Стоп, я не сказал главного — надо подключить все наши 4 точки, "
                         "не одну. Так сколько выйдет?",
                "check_not_in_bot": ["1 магазин", "одна точка", "для одной"],
                "check_in_bot": ["4"],
                "note": "КЛЮЧЕВОЙ: клиент раскрывает реальный масштаб — 4 точки. "
                        "Бот должен пересчитать для 4 точек, НЕ продолжать говорить '1 магазин'.",
            },
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# ЗАПУСК И ОЦЕНКА
# ─────────────────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Нижний регистр, убираем знаки препинания для простого поиска."""
    return re.sub(r'[^\w\s]', ' ', text.lower())


def check_violations(bot_reply: str, check_in: list, check_not_in: list) -> dict:
    """Проверяет нарушения контекста в ответе бота."""
    norm = normalize(bot_reply)
    violations = []
    warnings = []

    for phrase in check_not_in:
        if normalize(phrase) in norm:
            violations.append(f"НАРУШЕНИЕ (должно ОТСУТСТВОВАТЬ): '{phrase}'")

    # check_in — мягкая проверка (предупреждение если нет)
    for phrase in check_in:
        if normalize(phrase) not in norm:
            warnings.append(f"ПРЕДУПРЕЖДЕНИЕ (ожидалось увидеть): '{phrase}'")

    return {"violations": violations, "warnings": warnings}


def run_scenario(scenario: dict, bot) -> dict:
    bot.reset()
    results = []
    total_violations = 0
    total_warnings = 0

    for i, turn in enumerate(scenario["turns"]):
        user_msg = turn["user"]
        result = bot.process(user_msg)
        bot_reply = result.get("response", "")

        checks = check_violations(
            bot_reply,
            turn.get("check_in_bot", []),
            turn.get("check_not_in_bot", []),
        )

        total_violations += len(checks["violations"])
        total_warnings += len(checks["warnings"])

        results.append({
            "turn": i + 1,
            "user": user_msg,
            "bot": bot_reply,
            "state": result.get("state", "?"),
            "action": result.get("action", "?"),
            "spin_phase": result.get("spin_phase", "?"),
            "note": turn.get("note", ""),
            "violations": checks["violations"],
            "warnings": checks["warnings"],
            "is_final": result.get("is_final", False),
        })

        if result.get("is_final"):
            break

    passed = total_violations == 0
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "description": scenario.get("description", ""),
        "turns": results,
        "total_violations": total_violations,
        "total_warnings": total_warnings,
        "passed": passed,
    }


def print_scenario(d: dict) -> str:
    status = "✅ PASS" if d["passed"] else "❌ FAIL"
    lines = [
        f"\n{DIVIDER}",
        f"  {d['id']} | {d['name']}",
        f"  {status}  |  Нарушений: {d['total_violations']}  |  Предупреждений: {d['total_warnings']}",
        f"  {d['description']}",
        DIVIDER,
    ]
    for t in d["turns"]:
        lines.append(
            f"\n[T{t['turn']}] {t['state']} / {t['action']} / spin={t['spin_phase']}"
        )
        lines.append(f"  КЛИЕНТ: {t['user']}")
        lines.append(f"  БОТ:    {t['bot']}")
        if t["note"]:
            lines.append(f"  📝 ПРОВЕРКА: {t['note']}")
        for v in t["violations"]:
            lines.append(f"  🚨 {v}")
        for w in t["warnings"]:
            lines.append(f"  ⚠️  {w}")
        if t["is_final"]:
            lines.append("  🏁 ФИНАЛЬНОЕ СОСТОЯНИЕ")
    return "\n".join(lines)


def print_summary(all_results: list):
    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)
    total_v = sum(r["total_violations"] for r in all_results)
    total_w = sum(r["total_warnings"] for r in all_results)

    print(f"\n{'='*72}")
    print(f"  ИТОГ: {passed}/{total} PASS  |  Всего нарушений памяти: {total_v}  |  Предупреждений: {total_w}")
    print(f"{'='*72}")
    for r in all_results:
        icon = "✅" if r["passed"] else "❌"
        print(f"  {icon} {r['id']} — {r['name']}")
        for t in r["turns"]:
            for v in t["violations"]:
                print(f"       T{t['turn']}: 🚨 {v}")
            for w in t["warnings"]:
                print(f"       T{t['turn']}: ⚠️  {w}")
    print(f"{'='*72}\n")


def main():
    llm = OllamaLLM()
    setup_autonomous_pipeline()
    bot = SalesBot(llm, flow_name="autonomous")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = Path(__file__).parent.parent / "results" / f"context_memory_{ts}.json"
    out_md   = Path(__file__).parent.parent / "results" / f"context_memory_{ts}.md"
    out_json.parent.mkdir(exist_ok=True)

    print(f"\n{'='*72}")
    print(f"  ТЕСТ КОНТЕКСТА И ПАМЯТИ ДИАЛОГА — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  10 сценариев × 5 ходов = проверка контекстной памяти бота")
    print(f"{'='*72}")

    all_results = []
    md_lines = [
        f"# Тест контекста и памяти диалога",
        f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for scenario in SCENARIOS:
        print(f"\n>>> [{scenario['id']}] {scenario['name']}")
        result = run_scenario(scenario, bot)
        all_results.append(result)
        output = print_scenario(result)
        print(output)
        md_lines.append(output)

    print_summary(all_results)
    md_lines.append("\n## ИТОГОВАЯ ТАБЛИЦА\n")
    passed = sum(1 for r in all_results if r["passed"])
    total_v = sum(r["total_violations"] for r in all_results)
    md_lines.append(f"**PASS: {passed}/{len(all_results)}** | Нарушений памяти: {total_v}")
    md_lines.append("")
    md_lines.append("| Сценарий | Название | Нарушения | Статус |")
    md_lines.append("|---|---|---|---|")
    for r in all_results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        md_lines.append(f"| {r['id']} | {r['name']} | {r['total_violations']} | {status} |")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "scenarios": all_results}, f, ensure_ascii=False, indent=2)

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"JSON: {out_json}")
    print(f"MD:   {out_md}")


if __name__ == "__main__":
    main()
