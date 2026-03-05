#!/usr/bin/env python3
"""
KB ACCURACY E2E — 160 вопросов (16 категорий × 10) через полный autonomous pipeline.

Проверяет точность ответов бота по обновлённой базе знаний.
Каждый вопрос отправляется через полный пайплайн:
  setup msg → question → check response keywords

Метрики:
  - must_contain_any: хотя бы одно ключевое слово присутствует
  - must_not_contain: ни одного запретного факта
  - deflection: ответ = встречный вопрос без содержания
  - per-category и overall accuracy

Использование:
    python -m scripts.kb_accuracy_e2e_160 2>/dev/null
"""

import sys
import re
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

# ═══════════════════════════════════════════════════════════════════════
# DEFLECTION PATTERNS
# ═══════════════════════════════════════════════════════════════════════

DEFLECTION_PATTERNS = [
    r"расскажите\s+подробнее",
    r"расскажите\s+о\s+(своём|вашем|себе)",
    r"какой\s+у\s+вас\s+бизнес",
    r"чем\s+(?:я\s+)?(?:могу|можем)\s+помочь",
    r"что\s+вас\s+интересует",
    r"какие?\s+задачи",
    r"давайте\s+начн[её]м\s+с",
]

# ═══════════════════════════════════════════════════════════════════════
# SETUP MESSAGES (varied to avoid pattern detection)
# ═══════════════════════════════════════════════════════════════════════

SETUP_MESSAGES = [
    "Здравствуйте, у меня продуктовый магазин в Алматы, 2 точки.",
    "Привет, у нас магазин одежды в Астане.",
    "Добрый день, у меня розничный бизнес в Караганде, 3 магазина.",
    "Здравствуйте, открываю магазин электроники в Шымкенте.",
    "Привет, у меня аптека в Костанае.",
    "Добрый день, у нас строительный магазин, 4 точки.",
    "Здравствуйте, мы продаём косметику в Актобе, 2 филиала.",
    "Привет, у меня обувной магазин в Павлодаре.",
]


def get_setup(idx: int) -> str:
    return SETUP_MESSAGES[idx % len(SETUP_MESSAGES)]


# ═══════════════════════════════════════════════════════════════════════
# TRACING HELPERS
# ═══════════════════════════════════════════════════════════════════════

def patch_llm_for_prompt_capture(llm):
    """Monkey-patch llm.generate to capture final prompts."""
    llm._captured_prompts = []
    original_generate = llm.generate

    def capturing_generate(prompt, **kwargs):
        llm._captured_prompts.append(prompt)
        return original_generate(prompt, **kwargs)

    llm.generate = capturing_generate
    return llm


def extract_trace(bot, resp):
    """Extract full e2e trace from bot after process()."""
    trace = {}

    # 1. reason_codes
    trace["reason_codes"] = resp.get("reason_codes", [])

    # 2. resolution_trace
    trace["resolution_trace"] = resp.get("resolution_trace", {})

    # 3. decision_trace (enable_tracing=True)
    dt = resp.get("decision_trace")
    if dt:
        trace["decision_trace"] = dt

    # 4. generator meta — template, fact_keys, verifier
    try:
        meta = bot.generator.get_last_generation_meta()
        trace["selected_template_key"] = meta.get("selected_template_key", "?")
        trace["fact_keys"] = meta.get("fact_keys", [])
        trace["factual_verifier_verdict"] = meta.get("factual_verifier_verdict", "?")
        trace["factual_verifier_changed"] = meta.get("factual_verifier_changed", False)
        trace["validation_events"] = meta.get("validation_events", [])
        trace["postprocess_last_mutation_rule"] = meta.get("postprocess_last_mutation_rule")
        trace["postprocess_trace"] = meta.get("postprocess_trace", [])
    except Exception as e:
        trace["generator_meta_error"] = str(e)

    # 5. retrieved_facts — from blackboard response context
    try:
        rc = bot._orchestrator.blackboard.get_response_context()
        if rc:
            trace["retrieved_facts"] = rc.get("retrieved_facts", "")
            variables = rc.get("variables", {})
            trace["question_instruction"] = variables.get("question_instruction", "")
            trace["state_gated_rules"] = variables.get("state_gated_rules", "")
            trace["address_instruction"] = variables.get("address_instruction", "")
        else:
            trace["retrieved_facts"] = "(response_context empty)"
    except Exception as e:
        trace["retrieved_facts_error"] = str(e)

    # 6. captured prompts (from monkey-patched llm)
    try:
        prompts = bot.generator.llm._captured_prompts
        if prompts:
            trace["last_prompt"] = prompts[-1]
            trace["total_prompts_in_turn"] = len(prompts)
    except Exception:
        pass

    return trace


# ═══════════════════════════════════════════════════════════════════════
# 160 TEST CASES: 16 categories × 10 questions
# ═══════════════════════════════════════════════════════════════════════

TEST_CASES = [
    # ─────────────────────────────────────────────────
    # CATEGORY 1: EQUIPMENT (10)
    # ─────────────────────────────────────────────────
    {"cat": "equipment", "q": "Сколько стоит моноблок POS DUO?",
     "must": ["220 000", "15.6", "i5", "8"], "not": ["240 000", "300 000"]},
    {"cat": "equipment", "q": "Что входит в комплект PRO оборудования и сколько он стоит?",
     "must": ["360 000", "POS DUO", "сканер", "принтер", "ящик"], "not": ["500 000", "тариф"]},
    {"cat": "equipment", "q": "Сколько стоит комплект Standard оборудования?",
     "must": ["168 000", "POS i3", "сканер", "принтер"], "not": ["220 000", "тариф Standard"]},
    {"cat": "equipment", "q": "Чем отличаются сканеры WP930Z и WPB930?",
     "must": ["WP930Z", "проводн", "10 000", "WPB930", "беспроводн", "17 000"], "not": ["45 000"]},
    {"cat": "equipment", "q": "Какие принтеры чеков у вас есть? Чем они отличаются?",
     "must": ["58 мм", "80 мм", "принтер"], "not": ["этикет"]},
    {"cat": "equipment", "q": "Сколько стоят весы Rongta RLS1100?",
     "must": ["200 000", "30 кг"], "not": ["100 000"]},
    {"cat": "equipment", "q": "Есть ли у вас умные весы? Сколько стоят?",
     "must": ["100 000", "30 кг"], "not": ["200 000", "Rongta"]},
    {"cat": "equipment", "q": "Чем отличается Wipon Triple от Wipon Quadro?",
     "must": ["Triple", "330 000", "Quadro", "365 000"], "not": ["220 000"]},
    {"cat": "equipment", "q": "Сколько стоит экран покупателя Wipon Screen?",
     "must": ["60 000", "10.1"], "not": ["100 000"]},
    {"cat": "equipment", "q": "Сколько стоит денежный ящик Wipon?",
     "must": ["21 000", "купюр"], "not": ["10 000"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 2: PRICING (10)
    # ─────────────────────────────────────────────────
    {"cat": "pricing", "q": "Какие тарифы есть у Wipon и сколько они стоят?",
     "must": ["Mini", "5 000", "Lite", "150 000", "Standard", "220 000", "Pro", "500 000"], "not": ["бесплатн"]},
    {"cat": "pricing", "q": "Сколько стоит тариф Mini?",
     "must": ["5 000", "месяц", "1 точк"], "not": ["год"]},
    {"cat": "pricing", "q": "Чем Standard отличается от Lite?",
     "must": ["Standard", "220 000", "Lite", "150 000"], "not": ["500 000"]},
    {"cat": "pricing", "q": "Что включает тариф Pro?",
     "must": ["500 000", "год", "склад"], "not": ["360 000", "комплект"]},
    {"cat": "pricing", "q": "Сколько стоит подключение ТИС?",
     "must": ["220 000", "год"], "not": ["бесплатно"]},
    {"cat": "pricing", "q": "Есть ли рассрочка на оборудование?",
     "must": ["рассрочк", "12", "Kaspi"], "not": ["кредит", "аренд"]},
    {"cat": "pricing", "q": "Можно ли взять оборудование в аренду?",
     "must": ["нет", "рассрочк"], "not": ["можно арендовать"]},
    {"cat": "pricing", "q": "Входит ли программа в стоимость оборудования?",
     "must": ["отдельно", "програм", "тариф"], "not": ["входит в стоимость оборудования"]},
    {"cat": "pricing", "q": "Что такое Wipon PRO УКМ и сколько стоит?",
     "must": ["12 000", "акциз", "алкоголь", "модуль"], "not": ["500 000", "360 000"]},
    {"cat": "pricing", "q": "Сколько стоит дополнительная торговая точка?",
     "must": ["50 000", "год"], "not": ["бесплатно"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 3: PRODUCTS (10)
    # ─────────────────────────────────────────────────
    {"cat": "products", "q": "Что такое Wipon Kassa?",
     "must": ["бесплатн", "онлайн-касс", "ОФД", "фискализац"], "not": ["платн"]},
    {"cat": "products", "q": "Wipon подходит для кофейни с рецептами?",
     "must": ["рецепт", "калькуляц"], "not": ["полностью подходит для кофейни"]},
    {"cat": "products", "q": "С какого года работает компания Wipon?",
     "must": ["2014", "50 000"], "not": ["2010", "2020"]},
    {"cat": "products", "q": "Что такое Wipon Desktop?",
     "must": ["Windows", "учёт", "товар"], "not": ["бесплатно", "Mac"]},
    {"cat": "products", "q": "Подходит ли Wipon для аптеки?",
     "must": ["маркировк", "срок", "годност"], "not": ["не подходит"]},
    {"cat": "products", "q": "Что такое Wipon Duo?",
     "must": ["два экран", "кассир", "покупател"], "not": ["один экран"]},
    {"cat": "products", "q": "У меня 5 магазинов. Какой тариф подойдёт?",
     "must": ["Pro", "500 000", "точк"], "not": ["Mini", "Lite"]},
    {"cat": "products", "q": "Я торгую алкоголем. Подходит ли ваша система?",
     "must": ["УКМ", "акциз", "алкоголь"], "not": ["не поддерж"]},
    {"cat": "products", "q": "Что входит в Wipon Розница?",
     "must": ["товар", "учёт", "склад", "касс", "фискализац"], "not": ["бесплатно"]},
    {"cat": "products", "q": "Какие продукты есть в экосистеме Wipon?",
     "must": ["Kassa", "Desktop", "ТИС"], "not": ["CRM"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 4: TIS (10)
    # ─────────────────────────────────────────────────
    {"cat": "tis", "q": "Что такое ТИС и как расшифровывается?",
     "must": ["рёхкомпонентн", "интегрирован", "систем"], "not": ["CRM"]},
    {"cat": "tis", "q": "Кому подходит ТИС? Могу ли я подключить, если у меня ТОО?",
     "must": ["ИП", "упрощён"], "not": ["ТОО может подключить ТИС"]},
    {"cat": "tis", "q": "Какие лимиты повышает ТИС для ИП?",
     "must": ["НДС", "567", "78"], "not": ["лимиты не меняются"]},
    {"cat": "tis", "q": "Как быстро можно подключить ТИС?",
     "must": ["1-2 дн", "ЭЦП", "удалённо"], "not": ["неделя", "месяц"]},
    {"cat": "tis", "q": "Что видит налоговая при подключении ТИС?",
     "must": ["чек", "доход"], "not": ["видит всё", "видит закупочные"]},
    {"cat": "tis", "q": "С какого года ТИС Wipon официально признана?",
     "must": ["2021", "реестр"], "not": ["2020", "2023"]},
    {"cat": "tis", "q": "Что входит в функционал ТИС?",
     "must": ["склад", "касс", "фискализац", "отчётност"], "not": ["только касса"]},
    {"cat": "tis", "q": "Входят ли продажи через Wildberries и Ozon в лимиты ТИС?",
     "must": ["не входят"], "not": ["входят в лимит", "учитываются"]},
    {"cat": "tis", "q": "Сколько стоит выезд специалиста для установки ТИС?",
     "must": ["30 000"], "not": ["бесплатно", "50 000"]},
    {"cat": "tis", "q": "Что предложить для ТОО вместо ТИС?",
     "must": ["Розниц"], "not": ["ТОО может ТИС"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 5: SUPPORT (10)
    # ─────────────────────────────────────────────────
    {"cat": "support", "q": "Как быстро отвечает техподдержка Wipon?",
     "must": ["10", "15", "минут"], "not": ["мгновенно", "5 минут", "99.9%"]},
    {"cat": "support", "q": "Работает ли техподдержка в выходные?",
     "must": ["ежедневн", "выходн"], "not": ["только будни"]},
    {"cat": "support", "q": "Как проходит настройка — приедет мастер или удалённо?",
     "must": ["удалённо", "AnyDesk"], "not": ["выезд по всему Казахстану"]},
    {"cat": "support", "q": "Можно ли перенести базу данных из другой программы?",
     "must": ["перенос", "бесплатно"], "not": ["платно", "невозможно"]},
    {"cat": "support", "q": "Сколько времени занимает подключение Wipon?",
     "must": ["час", "дн"], "not": ["неделя", "месяц"]},
    {"cat": "support", "q": "Есть ли обучение после подключения? Платное?",
     "must": ["бесплатно", "обучени"], "not": ["платное обучение"]},
    {"cat": "support", "q": "Что такое Wipon Consulting?",
     "must": ["бухгалтер", "учёт", "консалтинг"], "not": ["CRM", "маркетинг"]},
    {"cat": "support", "q": "Можно ли работать без бухгалтера с Wipon Consulting?",
     "must": ["берём на себя", "бухгалтер"], "not": ["нужен бухгалтер обязательно"]},
    {"cat": "support", "q": "Помогут ли зарегистрировать ТОО через Wipon Consulting?",
     "must": ["регистрац", "ТОО", "БИН"], "not": ["только ИП"]},
    {"cat": "support", "q": "До скольки работают менеджеры Wipon?",
     "must": ["18:00"], "not": ["круглосуточно", "24/7"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 6: DELIVERY (10)
    # ─────────────────────────────────────────────────
    {"cat": "delivery", "q": "В какие города Казахстана доставляете оборудование?",
     "must": ["Казахстан", "Алматы", "Астан"], "not": ["только Алматы"]},
    {"cat": "delivery", "q": "Бесплатная ли доставка по Астане?",
     "must": ["бесплатно", "40 000"], "not": ["всегда платно"]},
    {"cat": "delivery", "q": "За сколько дней доставите оборудование в Алматы?",
     "must": ["1-2", "рабоч"], "not": ["5 дней", "неделя"]},
    {"cat": "delivery", "q": "Сколько дней занимает доставка в Актау?",
     "must": ["3-5", "рабоч"], "not": ["1-2 дня"]},
    {"cat": "delivery", "q": "Где находятся офисы Wipon?",
     "must": ["Астан", "Алматы", "Шымкент"], "not": ["Караганда офис"]},
    {"cat": "delivery", "q": "Можно ли забрать оборудование самовывозом?",
     "must": ["самовывоз"], "not": ["невозможен"]},
    {"cat": "delivery", "q": "В каких городах доступен выезд специалиста?",
     "must": ["Алматы", "Астан", "Шымкент"], "not": ["все города"]},
    {"cat": "delivery", "q": "Сколько дней доставка в Караганду?",
     "must": ["2-3", "рабоч"], "not": ["неделя"]},
    {"cat": "delivery", "q": "Доставляете ли в сёла и отдалённые населённые пункты?",
     "must": ["да", "Казахстан"], "not": ["только крупные города"]},
    {"cat": "delivery", "q": "Где находится головной офис Wipon?",
     "must": ["Астан"], "not": ["Алматы головной"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 7: INVENTORY (10)
    # ─────────────────────────────────────────────────
    {"cat": "inventory", "q": "Как Wipon помогает контролировать остатки, чтобы товар не закончился?",
     "must": ["уведомлени", "остатк", "вовремя"], "not": []},
    {"cat": "inventory", "q": "Можно ли проводить ревизию, не закрывая магазин?",
     "must": ["без остановки", "продаж"], "not": ["нужно закрыть"]},
    {"cat": "inventory", "q": "Если не успел закончить ревизию — данные потеряются?",
     "must": ["сохранен", "продолж"], "not": ["начать заново", "теряются"]},
    {"cat": "inventory", "q": "У меня несколько магазинов. Как синхронизировать остатки?",
     "must": ["синхронизац", "автоматическ"], "not": ["вручную"]},
    {"cat": "inventory", "q": "Мы работаем со штучным и весовым товаром. Нужны две программы?",
     "must": ["штучн", "весов", "один"], "not": ["две программы"]},
    {"cat": "inventory", "q": "Можно ли хранить контакты поставщиков в системе?",
     "must": ["контрагент", "поставщик", "карточк"], "not": ["только в Excel"]},
    {"cat": "inventory", "q": "Есть ли аналитика по складу — отчёты, недостачи?",
     "must": ["отчёт", "остатк", "движени"], "not": ["нет аналитики"]},
    {"cat": "inventory", "q": "Как оформить закупку товара в Wipon?",
     "must": ["приходн", "накладн", "поставщик"], "not": ["только вручную"]},
    {"cat": "inventory", "q": "Обновятся ли остатки автоматически после оприходования?",
     "must": ["автоматическ", "сразу"], "not": ["вручную"]},
    {"cat": "inventory", "q": "Можно ли проводить частичную ревизию — по отдельным категориям?",
     "must": ["частичн", "выборочн", "категори"], "not": ["только полная"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 8: FEATURES (10)
    # ─────────────────────────────────────────────────
    {"cat": "features", "q": "Какие способы оплаты поддерживает касса Wipon?",
     "must": ["наличн", "карт", "долг", "смешанн"], "not": ["только наличные"]},
    {"cat": "features", "q": "Касса работает без интернета?",
     "must": ["офлайн", "автономн", "синхронизац"], "not": ["нет, нужен интернет"]},
    {"cat": "features", "q": "Есть ли ограничение по количеству товаров в системе?",
     "must": ["без ограничен"], "not": ["максимум"]},
    {"cat": "features", "q": "Можно ли отправить чек клиенту на WhatsApp?",
     "must": ["WhatsApp", "электронн"], "not": ["только бумажный"]},
    {"cat": "features", "q": "Как искать товары при продаже на кассе?",
     "must": ["назван", "штрихкод", "артикул"], "not": ["только вручную"]},
    {"cat": "features", "q": "Можно ли оформить отложенную продажу?",
     "must": ["отложи", "чек", "позже"], "not": ["нет такой функции"]},
    {"cat": "features", "q": "Нужно ли вручную вводить сумму на POS-терминале?",
     "must": ["не требуется", "автоматическ"], "not": ["да, нужно вручную"]},
    {"cat": "features", "q": "Можно ли работать с алкогольной продукцией и акцизными марками?",
     "must": ["алкогол", "акциз", "поддерж"], "not": ["не поддерживает"]},
    {"cat": "features", "q": "Есть ли веб-версия Wipon?",
     "must": ["веб-верси", "браузер"], "not": ["нет веб-версии"]},
    {"cat": "features", "q": "Сколько прайслистов доступно на тарифах Standard и Pro?",
     "must": ["Standard", "1", "Pro", "3"], "not": ["безлимитно"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 9: INTEGRATIONS (10)
    # ─────────────────────────────────────────────────
    {"cat": "integrations", "q": "С какими маркетплейсами работает Wipon?",
     "must": ["Kaspi", "Halyk"], "not": ["Ozon", "Wildberries"]},
    {"cat": "integrations", "q": "Есть ли интеграция с Ozon или Wildberries?",
     "must": ["нет"], "not": ["поддерживается Ozon"]},
    {"cat": "integrations", "q": "С какими банками работают POS-терминалы?",
     "must": ["Forte", "Halyk", "Kaspi"], "not": ["Сбербанк"]},
    {"cat": "integrations", "q": "Через какую систему работает маркировка в Казахстане?",
     "must": ["ISMET", "маркировк"], "not": ["Честный Знак"]},
    {"cat": "integrations", "q": "С какими учётными системами интегрируется Wipon ТИС?",
     "must": ["1С", "iiko"], "not": ["SAP"]},
    {"cat": "integrations", "q": "Поддерживает ли Wipon бесконтактную оплату NFC?",
     "must": ["NFC", "поддерж"], "not": ["не поддерживается"]},
    {"cat": "integrations", "q": "Можно ли формировать и отправлять ЭСФ через Wipon?",
     "must": ["ЭСФ", "формирован"], "not": ["не поддерживается"]},
    {"cat": "integrations", "q": "Можно ли подключить несколько POS-терминалов к одной кассе?",
     "must": ["поддерж", "несколько"], "not": ["только один"]},
    {"cat": "integrations", "q": "Какие модули Wipon работают вместе?",
     "must": ["склад", "финанс", "касс"], "not": ["работают отдельно"]},
    {"cat": "integrations", "q": "Нужно ли кассиру вручную вводить сумму на терминале?",
     "must": ["автоматическ", "не нужно"], "not": ["вручную вводить"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 10: FISCAL (10)
    # ─────────────────────────────────────────────────
    {"cat": "fiscal", "q": "Сколько стоит ОФД в месяц?",
     "must": ["1 120", "тенге"], "not": ["бесплатно", "входит в тариф"]},
    {"cat": "fiscal", "q": "ОФД входит в тариф Wipon или оплачивается отдельно?",
     "must": ["отдельно"], "not": ["включён в тариф"]},
    {"cat": "fiscal", "q": "Как понять, ушёл ли чек в ОФД?",
     "must": ["статус", "серый", "синий"], "not": ["зелёный", "красный"]},
    {"cat": "fiscal", "q": "Какие налоговые формы формирует Wipon?",
     "must": ["910", "913"], "not": ["не формирует"]},
    {"cat": "fiscal", "q": "Можно ли работать только с POS-терминалом без онлайн-кассы?",
     "must": ["онлайн-касс", "обязательн", "фискализац"], "not": ["можно без кассы"]},
    {"cat": "fiscal", "q": "Передаются ли все мои данные о продажах в налоговую?",
     "must": ["только", "чек"], "not": ["все продажи передаются"]},
    {"cat": "fiscal", "q": "Можно ли подключить только ОФД без программы Wipon?",
     "must": ["не подключается", "только вместе"], "not": ["можно отдельно"]},
    {"cat": "fiscal", "q": "Нужна ли ЭЦП для подключения онлайн-кассы?",
     "must": ["нужна", "ЭЦП"], "not": ["не нужна"]},
    {"cat": "fiscal", "q": "Как оформить возврат товара через Wipon?",
     "must": ["возврат", "чек", "ОФД"], "not": ["невозможно"]},
    {"cat": "fiscal", "q": "Можно ли отправить чек клиенту онлайн?",
     "must": ["WhatsApp", "email"], "not": ["только бумажный"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 11: ANALYTICS (10)
    # ─────────────────────────────────────────────────
    {"cat": "analytics", "q": "Какая аналитика по продажам есть в Wipon?",
     "must": ["продаж", "выручк", "прибыл"], "not": ["CRM"]},
    {"cat": "analytics", "q": "Можно ли смотреть аналитику в реальном времени?",
     "must": ["реальн", "врем"], "not": ["задержка", "раз в сутки"]},
    {"cat": "analytics", "q": "Можно ли выгрузить отчёты в Excel?",
     "must": ["Excel"], "not": ["нет экспорта"]},
    {"cat": "analytics", "q": "Есть ли отчёт по маржинальности товаров?",
     "must": ["маржинальност", "прибыл"], "not": ["нет отчёта"]},
    {"cat": "analytics", "q": "Как посмотреть прибыль за месяц?",
     "must": ["прибыл", "период"], "not": ["только за год"]},
    {"cat": "analytics", "q": "Где видно, кто из клиентов мне должен?",
     "must": ["задолженност", "должен", "долг"], "not": ["нет учёта долгов"]},
    {"cat": "analytics", "q": "Можно ли вести учёт расходов магазина?",
     "must": ["расход", "учёт"], "not": ["нет учёта расходов"]},
    {"cat": "analytics", "q": "Нужно ли вручную собирать отчёты по нескольким точкам?",
     "must": ["синхронизац", "автоматическ"], "not": ["вручную"]},
    {"cat": "analytics", "q": "Можно ли увидеть продажи по часам и дням недели?",
     "must": ["час", "дн"], "not": ["нет часовой"]},
    {"cat": "analytics", "q": "Можно ли сравнить продажи за разные периоды?",
     "must": ["сравнен", "период"], "not": ["нет сравнения"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 12: EMPLOYEES (10)
    # ─────────────────────────────────────────────────
    {"cat": "employees", "q": "Какие роли и уровни доступа есть для сотрудников?",
     "must": ["владелец", "администратор", "кассир"], "not": ["одна роль"]},
    {"cat": "employees", "q": "Можно ли скрыть от кассира закупочные цены и отчёты?",
     "must": ["скрыть", "закуп", "настройк"], "not": ["все видят всё"]},
    {"cat": "employees", "q": "Сколько сотрудников можно добавить в систему?",
     "must": ["без ограничен"], "not": ["максимум"]},
    {"cat": "employees", "q": "Можно ли запретить кассиру делать скидки?",
     "must": ["запретить", "скидк"], "not": ["нет ограничений"]},
    {"cat": "employees", "q": "Как контролировать действия кассиров?",
     "must": ["журнал", "операц", "кассир"], "not": ["нет контроля"]},
    {"cat": "employees", "q": "Есть ли кадровый учёт — зарплата, рабочее время?",
     "must": ["кадров", "зарплат", "рабоч"], "not": ["нет кадрового"]},
    {"cat": "employees", "q": "У каждого кассира свой логин?",
     "must": ["отдельн", "логин", "персональн"], "not": ["общий аккаунт"]},
    {"cat": "employees", "q": "Как узнать, кто пробил ошибочный чек?",
     "must": ["чек", "привязан", "кассир"], "not": ["невозможно"]},
    {"cat": "employees", "q": "Как заблокировать уволенного сотрудника в системе?",
     "must": ["удалени", "отключ", "доступ"], "not": ["нельзя заблокировать"]},
    {"cat": "employees", "q": "Можно ли подключить внешнего бухгалтера с ограниченным доступом?",
     "must": ["внешн", "бухгалтер", "ограниченн"], "not": ["нет такой возможности"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 13: STABILITY (10)
    # ─────────────────────────────────────────────────
    {"cat": "stability", "q": "Работает ли Wipon без интернета?",
     "must": ["офлайн", "синхронизац"], "not": ["не работает без интернета"]},
    {"cat": "stability", "q": "Что будет с чеками, если интернет отключится?",
     "must": ["сохран", "локальн", "ОФД", "восстановлен"], "not": ["потеряется"]},
    {"cat": "stability", "q": "У меня магазин в ауле, связь слабая. Подойдёт ли Wipon?",
     "must": ["сельск", "офлайн"], "not": ["не подходит"]},
    {"cat": "stability", "q": "Можно ли работать через мобильный интернет?",
     "must": ["мобильн", "интернет", "Wi-Fi"], "not": ["нужен проводной"]},
    {"cat": "stability", "q": "Если отключат свет — данные потеряются?",
     "must": ["автосохранен", "восстановлен", "не теряются"], "not": ["данные пропадут"]},
    {"cat": "stability", "q": "Как часто обновляется программа?",
     "must": ["автоматическ", "обновлен"], "not": ["вручную"]},
    {"cat": "stability", "q": "Обновления не мешают продажам?",
     "must": ["фон", "не останавлива"], "not": ["останавливается"]},
    {"cat": "stability", "q": "Если поменяю компьютер — данные сохранятся?",
     "must": ["облак", "сохран"], "not": ["привязаны к устройству"]},
    {"cat": "stability", "q": "Какие требования к компьютеру для Wipon?",
     "must": ["Windows"], "not": ["мощный компьютер"]},
    {"cat": "stability", "q": "Офлайн-режим доступен на всех тарифах?",
     "must": ["все тариф", "офлайн"], "not": ["только Pro"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 14: MOBILE (10)
    # ─────────────────────────────────────────────────
    {"cat": "mobile", "q": "Есть ли у Wipon мобильное приложение?",
     "must": ["да", "мобильн", "приложени"], "not": ["нет мобильного"]},
    {"cat": "mobile", "q": "Что можно делать в мобильном приложении?",
     "must": ["продаж", "учёт", "аналитик"], "not": ["только просмотр"]},
    {"cat": "mobile", "q": "На каких платформах работает мобильное приложение?",
     "must": ["Android", "iOS"], "not": ["только Android"]},
    {"cat": "mobile", "q": "Можно ли использовать Wipon на планшете?",
     "must": ["планшет", "да"], "not": ["не поддерживается"]},
    {"cat": "mobile", "q": "Можно ли вести складской учёт с телефона?",
     "must": ["да", "склад", "мобильн"], "not": ["только на компьютере"]},
    {"cat": "mobile", "q": "Можно ли контролировать магазин удалённо?",
     "must": ["удалённ", "контроль", "мобильн"], "not": ["нужно быть в магазине"]},
    {"cat": "mobile", "q": "Смогу ли я следить за бизнесом из-за границы?",
     "must": ["из любой точки", "мобильн"], "not": ["не работает за рубежом"]},
    {"cat": "mobile", "q": "У меня несколько магазинов — можно контролировать с телефона?",
     "must": ["все точки", "переключен"], "not": ["только одна"]},
    {"cat": "mobile", "q": "Обязательно ли нужен компьютер или можно работать только с телефона?",
     "must": ["мобильн", "веб-верси"], "not": ["компьютер обязателен"]},
    {"cat": "mobile", "q": "Можно ли в приложении делать приёмку и ревизию?",
     "must": ["приёмк", "ревизи", "мобильн"], "not": ["только на ПК"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 15: PROMOTIONS (10)
    # ─────────────────────────────────────────────────
    {"cat": "promotions", "q": "Можно ли настроить акцию на автозапуск по расписанию?",
     "must": ["автоматическ", "расписани"], "not": ["только вручную"]},
    {"cat": "promotions", "q": "Как ограничить акцию по датам?",
     "must": ["дата начала", "дата окончания", "автоматическ"], "not": ["вручную отключать"]},
    {"cat": "promotions", "q": "Можно ли запустить акцию только в одном магазине?",
     "must": ["да", "выбранн", "точк"], "not": ["только на всю сеть"]},
    {"cat": "promotions", "q": "Есть ли программа лояльности или кэшбэк?",
     "must": ["Cashback", "бонус", "лояльност"], "not": ["нет программы лояльности"]},
    {"cat": "promotions", "q": "Можно ли настроить разные уровни лояльности?",
     "must": ["уровн", "групп", "процент"], "not": ["один уровень для всех"]},
    {"cat": "promotions", "q": "Касса сама применит скидку при продаже?",
     "must": ["автоматическ", "касс", "акци"], "not": ["вручную"]},
    {"cat": "promotions", "q": "Можно ли сделать скидку только по определённым дням недели?",
     "must": ["да", "дн", "недел"], "not": ["только по датам"]},
    {"cat": "promotions", "q": "Есть ли накопительная скидка для клиентов?",
     "must": ["накопительн", "Cashback"], "not": ["нет накопительной"]},
    {"cat": "promotions", "q": "Бывают ли у Wipon сезонные акции или скидки на подключение?",
     "must": ["акци", "скидк"], "not": ["никогда не бывает"]},
    {"cat": "promotions", "q": "Слышал, что в Шымкенте есть скидка. Это правда?",
     "must": ["30%", "Шымкент", "Lite", "Standard"], "not": ["нет акции"]},

    # ─────────────────────────────────────────────────
    # CATEGORY 16: COMPETITORS (10)
    # ─────────────────────────────────────────────────
    {"cat": "competitors", "q": "Чем Wipon лучше конкурентов?",
     "must": ["облачн", "ТИС", "Kaspi"], "not": ["нужен сервер"]},
    {"cat": "competitors", "q": "Зачем мне Wipon, если есть 1С?",
     "must": ["без программист", "браузер", "Kaspi"], "not": ["1С лучше"]},
    {"cat": "competitors", "q": "Чем Wipon отличается от iiko?",
     "must": ["проще", "дешевл"], "not": ["iiko дешевле"]},
    {"cat": "competitors", "q": "В чём разница между Wipon и Poster?",
     "must": ["складск", "учёт"], "not": ["Poster лучше"]},
    {"cat": "competitors", "q": "Чем вы лучше UMAG?",
     "must": ["облачн", "ТИС"], "not": ["UMAG лучше"]},
    {"cat": "competitors", "q": "Я сейчас на UMAG, хочу перейти — это сложно?",
     "must": ["бесплатн", "перенос"], "not": ["перенос платный"]},
    {"cat": "competitors", "q": "Чем Wipon отличается от Beksar?",
     "must": ["облачн", "ТИС", "Kaspi"], "not": ["нужен сервер"]},
    {"cat": "competitors", "q": "Что скажете про Paloma — в чём ваше преимущество?",
     "must": ["облачн", "ТИС"], "not": ["привязка к оборудованию"]},
    {"cat": "competitors", "q": "Если перейду с другой системы — можно перенести данные?",
     "must": ["бесплатн", "перенос", "Excel"], "not": ["невозможен"]},
    {"cat": "competitors", "q": "Почему стоит выбрать именно Wipon?",
     "must": ["облачн", "учёт", "касс", "Kaspi"], "not": ["только касса"]},
]


# ═══════════════════════════════════════════════════════════════════════
# CHECK LOGIC
# ═══════════════════════════════════════════════════════════════════════

def is_deflective(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 200:
        for pat in DEFLECTION_PATTERNS:
            if re.search(pat, t, re.IGNORECASE):
                return True
    return False


def check_response(response: str, tc: dict) -> dict:
    """Check bot response against test case expectations."""
    low = response.lower()
    result = {
        "must_contain_pass": False,
        "must_not_contain_pass": True,
        "deflection": False,
        "missing_keywords": [],
        "forbidden_found": [],
    }

    # Check must_contain_any (at least ONE keyword present)
    must_kw = tc.get("must", [])
    if must_kw:
        found = [kw for kw in must_kw if kw.lower() in low]
        missing = [kw for kw in must_kw if kw.lower() not in low]
        # PASS if at least 30% of keywords found (flexible — bot may rephrase)
        threshold = max(1, len(must_kw) * 0.3)
        result["must_contain_pass"] = len(found) >= threshold
        result["missing_keywords"] = missing
        result["found_keywords"] = found
    else:
        result["must_contain_pass"] = True

    # Check must_not_contain
    not_kw = tc.get("not", [])
    for kw in not_kw:
        if kw.lower() in low:
            result["must_not_contain_pass"] = False
            result["forbidden_found"].append(kw)

    # Check deflection
    result["deflection"] = is_deflective(response)

    # Overall pass: must_contain + must_not_contain + no deflection
    result["passed"] = (
        result["must_contain_pass"]
        and result["must_not_contain_pass"]
        and not result["deflection"]
    )

    return result


# ═══════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════

def run_test(tc: dict, idx: int, bot, llm) -> dict:
    """Run single test case: setup → question → check response + trace."""
    bot.reset()
    setup = get_setup(idx)

    t0 = time.time()
    # Turn 1: setup
    try:
        bot.process(setup)
    except Exception as e:
        return {
            "idx": idx,
            "cat": tc["cat"],
            "question": tc["q"],
            "setup": setup,
            "response": "",
            "error": str(e),
            "check": {"passed": False, "must_contain_pass": False,
                      "must_not_contain_pass": True, "deflection": False,
                      "missing_keywords": tc.get("must", []),
                      "forbidden_found": [], "found_keywords": []},
            "elapsed_s": round(time.time() - t0, 2),
            "state": "error",
            "intent": "error",
            "action": "error",
            "trace": {},
        }

    # Reset captured prompts before the test question
    llm._captured_prompts = []

    # Turn 2: actual question
    trace = {}
    try:
        result = bot.process(tc["q"])
        response = result.get("response", "")
        trace = extract_trace(bot, result)
    except Exception as e:
        return {
            "idx": idx,
            "cat": tc["cat"],
            "question": tc["q"],
            "setup": setup,
            "response": "",
            "error": str(e),
            "check": {"passed": False, "must_contain_pass": False,
                      "must_not_contain_pass": True, "deflection": False,
                      "missing_keywords": tc.get("must", []),
                      "forbidden_found": [], "found_keywords": []},
            "elapsed_s": round(time.time() - t0, 2),
            "state": "error",
            "intent": "error",
            "action": "error",
            "trace": {},
        }

    elapsed = round(time.time() - t0, 2)
    chk = check_response(response, tc)

    return {
        "idx": idx,
        "cat": tc["cat"],
        "question": tc["q"],
        "setup": setup,
        "response": response,
        "error": None,
        "check": chk,
        "elapsed_s": elapsed,
        "state": result.get("state", "?"),
        "intent": result.get("intent", "?"),
        "action": result.get("action", "?"),
        "template_key": result.get("template_key", "?"),
        "trace": trace,
    }


# ═══════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════

def build_report(all_results: list, duration: float) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(all_results)
    passed = sum(1 for r in all_results if r["check"]["passed"])
    errors = sum(1 for r in all_results if r.get("error"))
    deflections = sum(1 for r in all_results if r["check"]["deflection"])

    lines = [
        f"# KB Accuracy E2E — {ts}",
        f"**Total**: {total} вопросов | **PASS**: {passed} ({100*passed//total}%) "
        f"| **FAIL**: {total-passed} | Errors: {errors} | Deflections: {deflections}",
        f"**Duration**: {duration:.0f}s ({duration/60:.1f} min)",
        "",
    ]

    # Per-category stats
    cat_stats = defaultdict(lambda: {"total": 0, "passed": 0, "deflections": 0})
    for r in all_results:
        cat = r["cat"]
        cat_stats[cat]["total"] += 1
        if r["check"]["passed"]:
            cat_stats[cat]["passed"] += 1
        if r["check"]["deflection"]:
            cat_stats[cat]["deflections"] += 1

    lines.append("## По категориям")
    lines.append("")
    lines.append("| Категория | Всего | PASS | % | Deflect |")
    lines.append("|-----------|-------|------|---|---------|")

    for cat in sorted(cat_stats.keys()):
        s = cat_stats[cat]
        pct = 100 * s["passed"] // s["total"] if s["total"] > 0 else 0
        icon = "✅" if pct >= 80 else ("⚠️" if pct >= 50 else "❌")
        lines.append(
            f"| {icon} {cat} | {s['total']} | {s['passed']} | {pct}% | {s['deflections']} |"
        )
    lines.append("")

    # Failures detail
    failed = [r for r in all_results if not r["check"]["passed"]]
    if failed:
        lines.append(f"## Провалы ({len(failed)})")
        lines.append("")
        for r in failed:
            chk = r["check"]
            reasons = []
            if not chk["must_contain_pass"]:
                reasons.append(f"missing: {chk['missing_keywords'][:5]}")
            if not chk["must_not_contain_pass"]:
                reasons.append(f"forbidden: {chk['forbidden_found']}")
            if chk["deflection"]:
                reasons.append("DEFLECTION")
            if r.get("error"):
                reasons.append(f"ERROR: {r['error'][:100]}")

            lines.append(f"### #{r['idx']} [{r['cat']}] — {' | '.join(reasons)}")
            lines.append(f"**Q:** {r['question']}")
            lines.append(f"**Bot:** {r['response'][:300]}")
            if chk.get("found_keywords"):
                lines.append(f"**Found:** {chk['found_keywords']}")
            lines.append(f"**State:** {r.get('state', '?')} | Intent: {r.get('intent', '?')} | Action: {r.get('action', '?')}")
            # Trace details for failures
            tr = r.get("trace", {})
            if tr:
                lines.append(f"**Template:** {tr.get('selected_template_key', '?')}")
                lines.append(f"**FactKeys:** {tr.get('fact_keys', [])}")
                lines.append(f"**ReasonCodes:** {tr.get('reason_codes', [])}")
                lines.append(f"**VerifierVerdict:** {tr.get('factual_verifier_verdict', '?')} | Changed: {tr.get('factual_verifier_changed', False)}")
                lines.append(f"**PostprocessLastMutation:** {tr.get('postprocess_last_mutation_rule')}")
                ve = tr.get("validation_events", [])
                if ve:
                    lines.append(f"**ValidationEvents:** {ve}")
                pp_trace = tr.get("postprocess_trace", [])
                if pp_trace:
                    lines.append(f"**PostprocessTraceSteps:** {len(pp_trace)}")
                qi = tr.get("question_instruction", "")
                if qi:
                    lines.append(f"**QuestionInstruction:** {qi[:200]}")
                rf = tr.get("retrieved_facts", "")
                if rf:
                    lines.append(f"**RetrievedFacts (first 400):** {rf[:400]}")
            lines.append("")

    # All results detail
    lines.append("## Все результаты")
    lines.append("")
    for r in all_results:
        chk = r["check"]
        mark = "✅" if chk["passed"] else "❌"
        lines.append(f"---")
        lines.append(f"{mark} **#{r['idx']}** [{r['cat']}] ({r['elapsed_s']}s)")
        lines.append(f"**Q:** {r['question']}")
        lines.append(f"**Bot:** {r['response'][:400]}")
        if not chk["passed"]:
            if chk["missing_keywords"]:
                lines.append(f"**Missing:** {chk['missing_keywords'][:5]}")
            if chk["forbidden_found"]:
                lines.append(f"**Forbidden:** {chk['forbidden_found']}")
            if chk["deflection"]:
                lines.append(f"**DEFLECTION detected**")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    from src.bot import SalesBot, setup_autonomous_pipeline
    from src.llm import OllamaClient

    setup_autonomous_pipeline()

    llm = OllamaClient()
    patch_llm_for_prompt_capture(llm)
    bot = SalesBot(llm, flow_name="autonomous", enable_tracing=True)

    # Optional limit: python -m scripts.kb_accuracy_e2e_160 40
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(TEST_CASES)
    test_cases = TEST_CASES[:limit]
    total = len(test_cases)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)

    print(f"\n{'='*80}")
    print(f"  KB ACCURACY E2E — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {total} вопросов (16 категорий × 10)")
    print(f"  LLM: {llm.model} @ {llm.base_url}")
    print(f"  Pipeline: autonomous, все валидаторы ON")
    print(f"{'='*80}\n")

    all_results = []
    cat_running = defaultdict(lambda: {"pass": 0, "total": 0})
    start_total = time.time()

    for i, tc in enumerate(test_cases):
        cat = tc["cat"]
        print(f"  [{i+1}/{total}] [{cat}] {tc['q'][:60]}...", end="", flush=True)

        result = run_test(tc, i, bot, llm)
        all_results.append(result)

        chk = result["check"]
        cat_running[cat]["total"] += 1
        if chk["passed"]:
            cat_running[cat]["pass"] += 1

        mark = "✅" if chk["passed"] else "❌"
        details = ""
        if not chk["passed"]:
            if chk["deflection"]:
                details = " [DEFLECTION]"
            elif not chk["must_contain_pass"]:
                details = f" [missing {len(chk['missing_keywords'])} kw]"
            elif not chk["must_not_contain_pass"]:
                details = f" [forbidden: {chk['forbidden_found'][:2]}]"
            elif result.get("error"):
                details = f" [ERROR]"

        print(f" {mark} {result['elapsed_s']}s{details}")
        print(f"         → {result['response'][:200]}", flush=True)

    duration = time.time() - start_total

    # ── Summary ──
    passed = sum(1 for r in all_results if r["check"]["passed"])
    deflections = sum(1 for r in all_results if r["check"]["deflection"])

    print(f"\n{'='*80}")
    print(f"  ИТОГ: {passed}/{total} PASS ({100*passed//total}%)")
    print(f"  Duration: {duration:.0f}s ({duration/60:.1f} min)")
    print(f"  Deflections: {deflections}")
    print(f"{'='*80}\n")

    print("  По категориям:")
    for cat in sorted(cat_running.keys()):
        s = cat_running[cat]
        pct = 100 * s["pass"] // s["total"] if s["total"] > 0 else 0
        icon = "✅" if pct >= 80 else ("⚠️" if pct >= 50 else "❌")
        print(f"    {icon} {cat}: {s['pass']}/{s['total']} ({pct}%)")

    # ── Save JSON ──
    json_path = results_dir / f"kb_accuracy_e2e_{ts}.json"
    json_data = {
        "timestamp": ts,
        "total": total,
        "passed": passed,
        "pass_rate": round(100 * passed / total, 1),
        "deflections": deflections,
        "duration_s": round(duration, 1),
        "llm_model": llm.model,
        "categories": {},
        "results": [],
    }

    for cat in sorted(cat_running.keys()):
        s = cat_running[cat]
        json_data["categories"][cat] = {
            "total": s["total"],
            "passed": s["pass"],
            "pass_rate": round(100 * s["pass"] / s["total"], 1) if s["total"] else 0,
        }

    for r in all_results:
        tr = r.get("trace", {})
        entry = {
            "idx": r["idx"],
            "cat": r["cat"],
            "question": r["question"],
            "response": r["response"][:500],
            "passed": r["check"]["passed"],
            "must_contain_pass": r["check"]["must_contain_pass"],
            "must_not_contain_pass": r["check"]["must_not_contain_pass"],
            "deflection": r["check"]["deflection"],
            "missing_keywords": r["check"]["missing_keywords"],
            "forbidden_found": r["check"]["forbidden_found"],
            "found_keywords": r["check"].get("found_keywords", []),
            "elapsed_s": r["elapsed_s"],
            "state": r.get("state", "?"),
            "intent": r.get("intent", "?"),
            "action": r.get("action", "?"),
            "error": r.get("error"),
            "trace": {
                "selected_template_key": tr.get("selected_template_key", "?"),
                "fact_keys": tr.get("fact_keys", []),
                "retrieved_facts": tr.get("retrieved_facts", "")[:800],
                "question_instruction": tr.get("question_instruction", "")[:300],
                "state_gated_rules": tr.get("state_gated_rules", "")[:300],
                "reason_codes": tr.get("reason_codes", []),
                "factual_verifier_verdict": tr.get("factual_verifier_verdict", "?"),
                "factual_verifier_changed": tr.get("factual_verifier_changed", False),
                "validation_events": tr.get("validation_events", []),
                "postprocess_last_mutation_rule": tr.get("postprocess_last_mutation_rule"),
                "postprocess_trace": tr.get("postprocess_trace", []),
                "total_prompts_in_turn": tr.get("total_prompts_in_turn", 0),
                "last_prompt": tr.get("last_prompt", "")[-1500:],
            },
        }
        json_data["results"].append(entry)

    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── Save MD report ──
    md_path = results_dir / f"kb_accuracy_e2e_{ts}.md"
    report = build_report(all_results, duration)
    md_path.write_text(report, encoding="utf-8")

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")

    # Exit code: pass if >= 60% overall
    sys.exit(0 if passed >= total * 0.6 else 1)


if __name__ == "__main__":
    main()
