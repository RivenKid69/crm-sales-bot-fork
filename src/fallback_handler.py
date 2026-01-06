"""
Multi-Tier Fallback Handler для CRM Sales Bot.

4-уровневая система fallback для восстановления диалога.

Уровни:
- Tier 1: Переформулировать вопрос
- Tier 2: Предложить варианты (кнопки)
- Tier 3: Предложить skip
- Tier 4: Graceful exit

По исследованию Nexus Flow: 74% диалогов восстанавливаются с правильным fallback.

Использование:
    from fallback_handler import FallbackHandler

    handler = FallbackHandler()
    response = handler.get_fallback("fallback_tier_1", "spin_situation", context)
"""

from dataclasses import dataclass, field
from random import choice
from typing import Any, Dict, List, Optional

from logger import logger


@dataclass
class FallbackResponse:
    """Структура ответа fallback"""
    message: str
    options: Optional[List[str]] = None  # Для tier_2
    action: str = "continue"             # continue, skip, close
    next_state: Optional[str] = None     # Куда перейти при skip


@dataclass
class FallbackStats:
    """Статистика использования fallback"""
    total_count: int = 0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    state_counts: Dict[str, int] = field(default_factory=dict)
    last_tier: Optional[str] = None
    last_state: Optional[str] = None
    # Dynamic CTA tracking
    dynamic_cta_counts: Dict[str, int] = field(default_factory=dict)


class FallbackHandler:
    """
    4-уровневая система fallback для восстановления диалога.

    Tier 1: Переформулировать вопрос (разные варианты)
    Tier 2: Предложить варианты (кнопки)
    Tier 3: Предложить skip
    Tier 4: Graceful exit
    """

    # Tier 1: Переформулировать вопрос (разные варианты по состояниям)
    REPHRASE_TEMPLATES: Dict[str, List[str]] = {
        "greeting": [
            "Добрый день! Чем могу помочь?",
            "Здравствуйте! Расскажите, что вас интересует?",
        ],
        "spin_situation": [
            "Давайте я спрошу иначе — сколько примерно человек работает с клиентами?",
            "Можете подсказать хотя бы порядок — 5-10 человек, 10-20, или больше?",
            "Просто для понимания: вы работаете один или есть команда?",
            "Подскажите размер вашей команды — это поможет подобрать решение.",
        ],
        "spin_problem": [
            "Попробую по-другому: что сейчас отнимает больше всего времени в работе?",
            "Скажите, какая задача самая «больная» прямо сейчас?",
            "Если одним словом — что хотелось бы улучшить в первую очередь?",
            "С какими сложностями чаще всего сталкиваетесь в работе?",
        ],
        "spin_implication": [
            "А если примерно — сколько клиентов/заказов теряется из-за этого?",
            "Как это влияет на выручку, хотя бы приблизительно?",
            "Это случается часто или скорее редко?",
            "Насколько серьёзно это влияет на бизнес?",
        ],
        "spin_need_payoff": [
            "Если бы это решилось — что изменилось бы в первую очередь?",
            "Что было бы идеальным результатом?",
            "Какой результат вас бы устроил?",
            "Что должно измениться, чтобы вы были довольны?",
        ],
        "presentation": [
            "Хотите расскажу подробнее как это работает?",
            "Может покажу на примере?",
            "Интересует что-то конкретное?",
        ],
        "close": [
            "Оставьте контакт — пришлю детали.",
            "Куда удобнее прислать информацию?",
            "Как с вами лучше связаться?",
        ],
        "handle_objection": [
            "Понимаю ваши сомнения. Что именно смущает?",
            "Какой момент вызывает вопросы?",
            "Давайте разберём что беспокоит.",
        ],
    }

    # Tier 2: Предложить варианты (кнопки)
    OPTIONS_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "spin_situation": {
            "question": "Подскажите размер команды:",
            "options": ["1-5 человек", "6-15 человек", "16-30 человек", "Больше 30"]
        },
        "spin_problem": {
            "question": "Какая основная сложность?",
            "options": ["Теряем клиентов", "Много ручной работы", "Нет контроля", "Другое"]
        },
        "spin_implication": {
            "question": "Как часто это происходит?",
            "options": ["Ежедневно", "Несколько раз в неделю", "Редко", "Не знаю"]
        },
        "spin_need_payoff": {
            "question": "Что для вас важнее всего?",
            "options": ["Экономия времени", "Рост продаж", "Контроль команды", "Всё вместе"]
        },
        "presentation": {
            "question": "Что хотите узнать?",
            "options": ["Как работает", "Сколько стоит", "Как внедрить", "Показать демо"]
        },
    }

    # Динамические подсказки по контексту (priority descending)
    DYNAMIC_CTA_OPTIONS: Dict[str, Dict[str, Any]] = {
        "competitor_mentioned": {
            "question": "Что важнее всего при выборе системы?",
            "options": [
                "Сравнить функции с {competitor}",
                "Узнать о переходе с {competitor}",
                "Посмотреть демо",
                "Узнать цены"
            ],
            "priority": 10
        },
        "pain_losing_clients": {
            "question": "Что поможет решить эту проблему?",
            "options": [
                "Автоматические напоминания клиентам",
                "Контроль работы менеджеров",
                "Аналитика по клиентам",
                "Посмотреть как это работает"
            ],
            "priority": 8
        },
        "pain_no_control": {
            "question": "Какой контроль для вас важнее?",
            "options": [
                "Видеть всех клиентов в одном месте",
                "Контроль задач и сроков",
                "Отчёты и аналитика",
                "Посмотреть как это работает"
            ],
            "priority": 8
        },
        "pain_manual_work": {
            "question": "Что хотелось бы автоматизировать?",
            "options": [
                "Напоминания и follow-up",
                "Отчёты и документы",
                "Распределение заявок",
                "Посмотреть возможности"
            ],
            "priority": 8
        },
        "large_company": {
            "question": "Что важнее для вашей команды?",
            "options": [
                "Интеграции с другими системами",
                "Права доступа и роли",
                "Масштабируемость",
                "Запланировать демо"
            ],
            "priority": 5
        },
        "small_company": {
            "question": "С чего хотите начать?",
            "options": [
                "Узнать базовые функции",
                "Быстрый старт за 15 минут",
                "Узнать стоимость",
                "Попробовать бесплатно"
            ],
            "priority": 5
        },
        "after_price_question": {
            "question": "Что ещё хотите узнать?",
            "options": [
                "Условия оплаты",
                "Есть ли пробный период",
                "Что входит в тариф",
                "Запланировать демо"
            ],
            "priority": 7
        },
        "after_features_question": {
            "question": "Какие функции интересуют больше всего?",
            "options": [
                "Автоматизация рутины",
                "Аналитика и отчёты",
                "Интеграции",
                "Показать всё на демо"
            ],
            "priority": 6
        },
    }

    # Маппинг pain_point → тип динамических подсказок
    PAIN_POINT_MAPPING: Dict[str, str] = {
        "потеря клиентов": "pain_losing_clients",
        "теряем клиентов": "pain_losing_clients",
        "клиенты уходят": "pain_losing_clients",
        "отток": "pain_losing_clients",
        "упускаем сделки": "pain_losing_clients",
        "теряем заявки": "pain_losing_clients",
        "лиды остывают": "pain_losing_clients",
        "нет контроля": "pain_no_control",
        "нет видимости": "pain_no_control",
        "не вижу": "pain_no_control",
        "хаос": "pain_no_control",
        "бардак": "pain_no_control",
        "excel": "pain_no_control",
        "в головах": "pain_no_control",
        "ручная работа": "pain_manual_work",
        "много рутины": "pain_manual_work",
        "трачу время": "pain_manual_work",
        "долго": "pain_manual_work",
    }

    # Подпись для текстовых вариантов
    OPTIONS_FOOTER = "\nНапишите номер или ответьте своими словами."

    # Tier 3: Предложить skip
    SKIP_TEMPLATES: List[str] = [
        "Если сложно ответить — можем пропустить этот вопрос и перейти дальше.",
        "Не страшно, давайте пока пропустим это и вернёмся позже если нужно.",
        "Окей, двигаемся дальше — этот вопрос не критичен.",
        "Давайте пропустим и перейдём к следующему шагу.",
    ]

    # Карта переходов при skip
    SKIP_MAP: Dict[str, str] = {
        "greeting": "spin_situation",
        "spin_situation": "spin_problem",
        "spin_problem": "spin_implication",
        "spin_implication": "spin_need_payoff",
        "spin_need_payoff": "presentation",
        "presentation": "close",
        "handle_objection": "soft_close",
    }

    # Tier 4: Graceful exit
    EXIT_TEMPLATES: List[str] = [
        "Похоже, сейчас не лучшее время для подробного разговора. Могу прислать информацию на почту — удобно?",
        "Давайте так: я оставлю контакты, и вы свяжетесь когда будет удобно. Хорошо?",
        "Понимаю, что времени мало. Могу просто прислать краткую информацию — посмотрите когда будет время.",
        "Не буду отнимать время. Оставьте контакт — пришлю информацию, а вы решите.",
    ]

    # Дефолтные fallback сообщения
    DEFAULT_REPHRASE = "Давайте попробую спросить иначе..."
    DEFAULT_OPTIONS = {
        "question": "Что вас интересует?",
        "options": ["Подробнее о системе", "Цены", "Демо", "Связаться позже"]
    }

    def __init__(self):
        self._stats = FallbackStats()
        self._used_templates: Dict[str, List[str]] = {}  # Для избежания повторов

    def reset(self) -> None:
        """Сбросить состояние для нового диалога"""
        self._stats = FallbackStats()
        self._used_templates.clear()

    @property
    def stats(self) -> FallbackStats:
        """Статистика использования"""
        return self._stats

    def get_fallback(
        self,
        tier: str,
        state: str,
        context: Optional[Dict] = None
    ) -> FallbackResponse:
        """
        Получить fallback response для указанного уровня и состояния.

        Args:
            tier: Уровень fallback (fallback_tier_1, ..., soft_close)
            state: Текущее состояние FSM
            context: Дополнительный контекст (pain_point, company_size, etc.)

        Returns:
            FallbackResponse с сообщением и возможными опциями
        """
        context = context or {}

        # Обновляем статистику
        self._stats.total_count += 1
        self._stats.tier_counts[tier] = self._stats.tier_counts.get(tier, 0) + 1
        self._stats.state_counts[state] = self._stats.state_counts.get(state, 0) + 1
        self._stats.last_tier = tier
        self._stats.last_state = state

        logger.info(
            "Fallback triggered",
            tier=tier,
            state=state,
            total_fallbacks=self._stats.total_count
        )

        if tier == "fallback_tier_1":
            return self._tier_1_rephrase(state, context)
        elif tier == "fallback_tier_2":
            return self._tier_2_options(state, context)
        elif tier == "fallback_tier_3":
            return self._tier_3_skip(state, context)
        else:  # tier_4 or soft_close
            return self._tier_4_exit(context)

    def _tier_1_rephrase(self, state: str, context: Dict) -> FallbackResponse:
        """Tier 1: Переформулировать вопрос"""
        templates = self.REPHRASE_TEMPLATES.get(state, [self.DEFAULT_REPHRASE])

        # Выбираем не использованный недавно шаблон
        message = self._get_unused_template(f"rephrase_{state}", templates)

        return FallbackResponse(
            message=message,
            options=None,
            action="continue",
            next_state=None
        )

    def _tier_2_options(self, state: str, context: Dict) -> FallbackResponse:
        """
        Tier 2: Предложить варианты (текстовые подсказки).

        Динамические подсказки на основе контекста:
        1. competitor_mentioned → сравнение и переход
        2. pain_point → решение конкретной проблемы
        3. last_intent → релевантные follow-up
        4. company_size → масштаб решения
        5. Fallback к статичным если контекст пуст
        """
        from feature_flags import flags

        if not flags.is_enabled("dynamic_cta_fallback"):
            return self._get_static_tier_2_options(state, context)

        collected = context.get("collected_data", {})
        last_intent = context.get("last_intent")

        best = self._select_dynamic_options(collected, last_intent, state)

        if best:
            option_type = best.get("_type", "unknown")
            self._stats.dynamic_cta_counts[option_type] = \
                self._stats.dynamic_cta_counts.get(option_type, 0) + 1

            logger.info("Dynamic CTA selected", option_type=option_type, state=state)

            # Форматируем сообщение с нумерованными вариантами
            message = self._format_options_message(
                question=best["question"],
                options=best["options"][:4],
                collected_data=collected
            )

            return FallbackResponse(
                message=message,
                options=best["options"][:4],  # Сохраняем для аналитики
                action="continue",
                next_state=None
            )

        return self._get_static_tier_2_options(state, context)

    def _get_static_tier_2_options(self, state: str, context: Dict) -> FallbackResponse:
        """Статичные варианты (оригинальное поведение)."""
        template = self.OPTIONS_TEMPLATES.get(state)

        if template:
            collected = context.get("collected_data", {})
            message = self._format_options_message(
                question=template["question"],
                options=template["options"],
                collected_data=collected
            )
            return FallbackResponse(
                message=message,
                options=template["options"].copy(),
                action="continue",
                next_state=None
            )

        return self._tier_1_rephrase(state, context)

    def _format_options_message(
        self,
        question: str,
        options: List[str],
        collected_data: Dict
    ) -> str:
        """
        Форматирует сообщение с нумерованными вариантами.

        Пример вывода:
            Что важнее всего при выборе системы?

            1. Сравнить функции с Битрикс
            2. Узнать о переходе
            3. Посмотреть демо
            4. Узнать цены

            Напишите номер или ответьте своими словами.
        """
        # Подставляем имя конкурента если есть placeholder
        competitor_name = collected_data.get("competitor_name", "текущей системой")
        formatted_options = []

        for i, opt in enumerate(options, 1):
            formatted_opt = opt.format(competitor=competitor_name)
            formatted_options.append(f"{i}. {formatted_opt}")

        options_text = "\n".join(formatted_options)

        return f"{question}\n\n{options_text}{self.OPTIONS_FOOTER}"

    def _select_dynamic_options(
        self,
        collected: Dict,
        last_intent: Optional[str],
        state: str
    ) -> Optional[Dict]:
        """
        Выбрать лучшие динамические подсказки по приоритету.

        Приоритеты:
            10 - competitor_mentioned (самый высокий)
             8 - pain_point
             7 - last_intent (price, features)
             5 - company_size
        """
        candidates = []

        # Priority 10: Competitor
        if collected.get("competitor_mentioned"):
            opt = self.DYNAMIC_CTA_OPTIONS.get("competitor_mentioned")
            if opt:
                candidates.append({**opt, "_type": "competitor_mentioned"})

        # Priority 8: Pain point
        pain = collected.get("pain_point", "")
        if pain:
            pain_lower = pain.lower()
            for keyword, option_key in self.PAIN_POINT_MAPPING.items():
                if keyword in pain_lower:
                    opt = self.DYNAMIC_CTA_OPTIONS.get(option_key)
                    if opt:
                        candidates.append({**opt, "_type": option_key})
                    break

        # Priority 7: Last intent
        if last_intent:
            if last_intent in ["price_question", "pricing_details", "objection_price"]:
                opt = self.DYNAMIC_CTA_OPTIONS.get("after_price_question")
                if opt:
                    candidates.append({**opt, "_type": "after_price_question"})
            elif last_intent in ["question_features", "question_integrations", "question_how_works"]:
                opt = self.DYNAMIC_CTA_OPTIONS.get("after_features_question")
                if opt:
                    candidates.append({**opt, "_type": "after_features_question"})

        # Priority 5: Company size
        size = collected.get("company_size", 0)
        if isinstance(size, str):
            try:
                size = int(size)
            except ValueError:
                size = 0

        if size > 20:
            opt = self.DYNAMIC_CTA_OPTIONS.get("large_company")
            if opt:
                candidates.append({**opt, "_type": "large_company"})
        elif 0 < size <= 5:
            opt = self.DYNAMIC_CTA_OPTIONS.get("small_company")
            if opt:
                candidates.append({**opt, "_type": "small_company"})

        # Сортируем по приоритету и возвращаем лучший
        if candidates:
            candidates.sort(key=lambda x: x.get("priority", 0), reverse=True)
            return candidates[0]

        return None

    def _tier_3_skip(self, state: str, context: Dict) -> FallbackResponse:
        """Tier 3: Предложить skip"""
        next_state = self.SKIP_MAP.get(state, "presentation")
        message = self._get_unused_template("skip", self.SKIP_TEMPLATES)

        return FallbackResponse(
            message=message,
            options=None,
            action="skip",
            next_state=next_state
        )

    def _tier_4_exit(self, context: Dict) -> FallbackResponse:
        """Tier 4: Graceful exit"""
        message = self._get_unused_template("exit", self.EXIT_TEMPLATES)

        return FallbackResponse(
            message=message,
            options=None,
            action="close",
            next_state="soft_close"
        )

    def _get_unused_template(self, key: str, templates: List[str]) -> str:
        """
        Получить шаблон, не использованный недавно.
        Помогает избежать повторений.
        """
        if not templates:
            return self.DEFAULT_REPHRASE

        if key not in self._used_templates:
            self._used_templates[key] = []

        used = self._used_templates[key]
        available = [t for t in templates if t not in used]

        if not available:
            # Все использованы — сбросить историю
            self._used_templates[key] = []
            available = templates

        selected = choice(available)
        self._used_templates[key].append(selected)

        # Ограничиваем историю
        max_history = max(1, len(templates) // 2)
        if len(self._used_templates[key]) > max_history:
            self._used_templates[key] = self._used_templates[key][-max_history:]

        return selected

    def get_stats_dict(self) -> Dict:
        """Получить статистику в виде словаря"""
        return {
            "total_count": self._stats.total_count,
            "tier_counts": self._stats.tier_counts.copy(),
            "state_counts": self._stats.state_counts.copy(),
            "last_tier": self._stats.last_tier,
            "last_state": self._stats.last_state,
            "dynamic_cta_counts": self._stats.dynamic_cta_counts.copy(),
        }

    def escalate_tier(self, current_tier: str) -> str:
        """
        Получить следующий уровень fallback (эскалация).

        Args:
            current_tier: Текущий уровень

        Returns:
            Следующий уровень или soft_close
        """
        tier_order = [
            "fallback_tier_1",
            "fallback_tier_2",
            "fallback_tier_3",
            "soft_close"
        ]

        try:
            current_index = tier_order.index(current_tier)
            next_index = min(current_index + 1, len(tier_order) - 1)
            return tier_order[next_index]
        except ValueError:
            return "soft_close"


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("FALLBACK HANDLER DEMO")
    print("=" * 60)

    handler = FallbackHandler()

    # Демо всех уровней
    tiers = ["fallback_tier_1", "fallback_tier_2", "fallback_tier_3", "soft_close"]
    states = ["spin_situation", "spin_problem", "presentation"]

    for tier in tiers:
        print(f"\n--- {tier.upper()} ---")
        for state in states:
            response = handler.get_fallback(tier, state, {})
            print(f"\nState: {state}")
            print(f"  Message: {response.message}")
            if response.options:
                print(f"  Options: {response.options}")
            print(f"  Action: {response.action}")
            if response.next_state:
                print(f"  Next state: {response.next_state}")

    print("\n" + "=" * 60)
    print("STATS")
    print("=" * 60)
    print(json.dumps(handler.get_stats_dict(), indent=2, ensure_ascii=False))

    print("\n--- Tier Escalation ---")
    tier = "fallback_tier_1"
    for _ in range(4):
        print(f"{tier} -> ", end="")
        tier = handler.escalate_tier(tier)
    print(tier)

    print("\n" + "=" * 60)
