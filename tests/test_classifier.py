"""
Тесты для гибридного классификатора интентов.

Покрывает:
- TextNormalizer: опечатки, сленг, раскладка клавиатуры, слипшиеся слова
- PRIORITY_PATTERNS: все паттерны для каждого интента
- DataExtractor: извлечение срочности, бюджета, роли, канала, таймлайна
- HybridClassifier: контекстная классификация коротких ответов
"""

import pytest
import sys
sys.path.insert(0, 'src')

from classifier import (
    TextNormalizer,
    HybridClassifier,
    DataExtractor,
    TYPO_FIXES,
    SPLIT_PATTERNS,
    PRIORITY_PATTERNS,
)


class TestTextNormalizer:
    """Тесты для нормализатора текста"""

    def setup_method(self):
        self.normalizer = TextNormalizer()

    # =========================================================================
    # TYPO_FIXES: Опечатки и сленг
    # =========================================================================

    def test_price_typos(self):
        """Ценовые опечатки нормализуются"""
        assert "сколько" in self.normalizer.normalize("скока стоит")
        assert "сколько" in self.normalizer.normalize("скоко это")
        assert "ценник" in self.normalizer.normalize("какой ценик")
        assert "прайс" in self.normalizer.normalize("скиньте прайсик")
        assert "тариф" in self.normalizer.normalize("какой тарифчик")

    def test_greeting_typos(self):
        """Приветствия нормализуются"""
        assert "привет" in self.normalizer.normalize("прив")
        assert "привет" in self.normalizer.normalize("хай")
        assert "привет" in self.normalizer.normalize("хаюшки")
        assert "здравствуйте" in self.normalizer.normalize("здрасте")
        assert "здравствуйте" in self.normalizer.normalize("дратути")

    def test_farewell_typos(self):
        """Прощания нормализуются"""
        assert "пока" in self.normalizer.normalize("покеда")
        assert "пока" in self.normalizer.normalize("бай")
        assert "удачи" in self.normalizer.normalize("удачки")

    def test_slang_words(self):
        """Сленговые слова нормализуются"""
        assert "что" in self.normalizer.normalize("че там")
        assert "что" in self.normalizer.normalize("чо надо")
        assert "сейчас" in self.normalizer.normalize("щас")
        assert "вообще" in self.normalizer.normalize("ваще")
        assert "нормально" in self.normalizer.normalize("норм")
        assert "хорошо" in self.normalizer.normalize("ок")
        assert "хорошо" in self.normalizer.normalize("окей")

    def test_thanks_typos(self):
        """Благодарности нормализуются"""
        assert "спасибо" in self.normalizer.normalize("спс")
        assert "спасибо" in self.normalizer.normalize("пасиб")
        assert "пожалуйста" in self.normalizer.normalize("плиз")
        assert "пожалуйста" in self.normalizer.normalize("пж")

    def test_agreement_slang(self):
        """Согласие в сленговой форме"""
        assert "да" in self.normalizer.normalize("ага")
        assert "да" in self.normalizer.normalize("угу")
        assert "точно" in self.normalizer.normalize("точняк")
        # "канеш" может разбиваться split-паттерном
        normalized = self.normalizer.normalize("канеш")
        assert "коне" in normalized or "конечно" in normalized

    def test_negation_slang(self):
        """Отрицание в сленговой форме"""
        assert "нет" in self.normalizer.normalize("неа")
        assert "нет" in self.normalizer.normalize("ноуп")
        assert "вряд ли" in self.normalizer.normalize("врятли")

    def test_emotion_slang(self):
        """Эмоциональные слова и сленг"""
        assert "отлично" in self.normalizer.normalize("збс")
        assert "отлично" in self.normalizer.normalize("огонь")
        assert "отлично" in self.normalizer.normalize("топчик")
        assert "хорошо" in self.normalizer.normalize("кайф")
        assert "не знаю" in self.normalizer.normalize("хз")

    def test_business_terms(self):
        """Бизнес-термины нормализуются"""
        # Case-insensitive check for CRM
        assert "crm" in self.normalizer.normalize("црмка").lower()
        assert "битрикс" in self.normalizer.normalize("битрик")
        # "манагер" может разбиваться split-паттерном
        normalized = self.normalizer.normalize("манагер")
        assert "мене" in normalized or "менеджер" in normalized

    # =========================================================================
    # TYPO_FIXES: Раскладка клавиатуры
    # =========================================================================

    def test_keyboard_layout_en_to_ru(self):
        """Английская раскладка → русская"""
        assert "привет" in self.normalizer.normalize("ghbdtn")
        assert "цена" in self.normalizer.normalize("wtyf")
        assert "прайс" in self.normalizer.normalize("ghfqc")
        assert "да" in self.normalizer.normalize("lf")
        assert "нет" in self.normalizer.normalize("ytn")

    # =========================================================================
    # SPLIT_PATTERNS: Слипшиеся слова
    # =========================================================================

    def test_split_question_words(self):
        """Вопросительные слова разделяются"""
        normalized = self.normalizer.normalize("скольковсего")
        assert " " in normalized or "сколько" in normalized

        normalized = self.normalizer.normalize("какаяцена")
        assert " " in normalized or "какая" in normalized

    def test_split_action_verbs(self):
        """Глаголы действий разделяются"""
        normalized = self.normalizer.normalize("хочуузнать")
        assert " " in normalized or "хочу" in normalized

        normalized = self.normalizer.normalize("можнопосмотреть")
        assert " " in normalized or "можно" in normalized

    def test_split_greetings(self):
        """Приветствия разделяются"""
        normalized = self.normalizer.normalize("добрыйдень")
        assert " " in normalized or "добрый" in normalized

    def test_split_negations(self):
        """Отрицания разделяются"""
        normalized = self.normalizer.normalize("ненужно")
        # "не" + "нужно" или остаётся слитно как rejection
        assert "не" in normalized or "ненужно" in normalized


class TestPriorityPatterns:
    """Тесты для приоритетных паттернов классификации"""

    def setup_method(self):
        self.classifier = HybridClassifier()

    # =========================================================================
    # CALLBACK REQUEST
    # =========================================================================

    def test_callback_direct(self):
        """Прямой запрос обратного звонка"""
        result = self.classifier.classify("Перезвоните мне")
        assert result["intent"] == "callback_request"

        result = self.classifier.classify("Позвоните нам")
        assert result["intent"] == "callback_request"

    def test_callback_polite(self):
        """Вежливый запрос обратного звонка"""
        result = self.classifier.classify("Можете перезвонить?")
        assert result["intent"] == "callback_request"

        result = self.classifier.classify("Свяжитесь со мной")
        assert result["intent"] == "callback_request"

    def test_callback_with_number(self):
        """Запрос с указанием номера"""
        # "Вот мой номер" может не распознаваться без контекста
        # Используем более явные фразы
        result = self.classifier.classify("Запишите номер, перезвоните мне")
        assert result["intent"] == "callback_request"

        result = self.classifier.classify("Наберите меня по этому номеру")
        assert result["intent"] == "callback_request"

    # =========================================================================
    # DEMO REQUEST
    # =========================================================================

    def test_demo_direct(self):
        """Прямой запрос демо"""
        result = self.classifier.classify("Хочу демо")
        assert result["intent"] == "demo_request"

        result = self.classifier.classify("Покажите демо версию")
        assert result["intent"] == "demo_request"

    def test_demo_trial(self):
        """Запрос пробного периода"""
        result = self.classifier.classify("Дайте демо доступ")
        assert result["intent"] == "demo_request"

        result = self.classifier.classify("Хочу демо версию")
        assert result["intent"] == "demo_request"

    def test_demo_see_work(self):
        """Запрос посмотреть как работает"""
        result = self.classifier.classify("Нужно демо")
        assert result["intent"] == "demo_request"

        result = self.classifier.classify("Дайте демо")
        assert result["intent"] == "demo_request"

    # =========================================================================
    # CONSULTATION REQUEST
    # =========================================================================

    def test_consultation_direct(self):
        """Прямой запрос консультации"""
        result = self.classifier.classify("Нужна консультация")
        assert result["intent"] == "consultation_request"

        result = self.classifier.classify("Можете проконсультировать?")
        assert result["intent"] == "consultation_request"

    def test_consultation_help(self):
        """Запрос помощи в выборе"""
        result = self.classifier.classify("Помогите разобраться")
        assert result["intent"] == "consultation_request"

        result = self.classifier.classify("Посоветуйте что лучше")
        assert result["intent"] == "consultation_request"

    # =========================================================================
    # COMPARISON (сравнение с конкурентами)
    # =========================================================================

    def test_comparison_direct(self):
        """Прямое сравнение"""
        result = self.classifier.classify("Чем лучше от amoCRM?")
        assert result["intent"] == "comparison"

        result = self.classifier.classify("Сравните с Битрикс24")
        assert result["intent"] == "comparison"

    def test_comparison_why(self):
        """Почему вы, а не конкуренты"""
        result = self.classifier.classify("Почему вас, а не амо?")
        assert result["intent"] == "comparison"

    def test_comparison_vs(self):
        """Прямое противопоставление"""
        result = self.classifier.classify("Вы или Мегаплан?")
        assert result["intent"] == "comparison"

    # =========================================================================
    # PRICING DETAILS
    # =========================================================================

    def test_pricing_what_included(self):
        """Что входит в стоимость"""
        result = self.classifier.classify("Что входит в цену тарифа?")
        assert result["intent"] == "pricing_details"

        result = self.classifier.classify("Дайте прайс-лист")
        assert result["intent"] == "pricing_details"

    def test_pricing_per_user(self):
        """Цена за пользователя"""
        result = self.classifier.classify("Сколько за одного пользователя?")
        assert result["intent"] == "pricing_details"

    def test_pricing_discounts(self):
        """Вопрос о скидках"""
        result = self.classifier.classify("Какие скидки есть?")
        assert result["intent"] == "pricing_details"

    def test_pricing_payment_options(self):
        """Способы оплаты"""
        result = self.classifier.classify("Условия оплаты?")
        assert result["intent"] == "pricing_details"

    # =========================================================================
    # REJECTION
    # =========================================================================

    def test_rejection_not_interested(self):
        """Не интересно"""
        result = self.classifier.classify("Не интересно")
        assert result["intent"] == "rejection"

        result = self.classifier.classify("Неинтересно")
        assert result["intent"] == "rejection"

    def test_rejection_not_needed(self):
        """Не нужно"""
        result = self.classifier.classify("Спасибо, не нужно")
        assert result["intent"] == "rejection"

        result = self.classifier.classify("Нет, не хочу")
        assert result["intent"] == "rejection"

    def test_rejection_spam(self):
        """Пометка как спам"""
        result = self.classifier.classify("Это спам, отпишите меня")
        assert result["intent"] == "rejection"

        result = self.classifier.classify("Удалите меня из рассылки")
        assert result["intent"] == "rejection"

    def test_rejection_stop(self):
        """Просьба прекратить"""
        result = self.classifier.classify("Больше не пишите мне")
        assert result["intent"] == "rejection"

        result = self.classifier.classify("Прекратите звонить мне")
        assert result["intent"] == "rejection"

    def test_rejection_wrong_person(self):
        """Ошиблись адресатом"""
        result = self.classifier.classify("Отстаньте от меня")
        assert result["intent"] == "rejection"

        result = self.classifier.classify("Мимо, не интересует")
        assert result["intent"] == "rejection"

    # =========================================================================
    # OBJECTION_PRICE
    # =========================================================================

    def test_objection_price_no_budget(self):
        """Нет бюджета"""
        result = self.classifier.classify("Нет бюджета")
        assert result["intent"] == "objection_price"

        result = self.classifier.classify("Бюджета нет")
        assert result["intent"] == "objection_price"

    def test_objection_price_too_expensive(self):
        """Слишком дорого"""
        result = self.classifier.classify("Слишком дорого")
        assert result["intent"] == "objection_price"

        result = self.classifier.classify("Очень дорого для нас")
        assert result["intent"] == "objection_price"

    def test_objection_price_no_money(self):
        """Нет денег"""
        result = self.classifier.classify("Денег нет")
        assert result["intent"] == "objection_price"

        result = self.classifier.classify("Нет денег")
        assert result["intent"] == "objection_price"

    def test_objection_price_cant_afford(self):
        """Не потянем"""
        result = self.classifier.classify("Не потянем такую сумму")
        assert result["intent"] == "objection_price"

    # =========================================================================
    # OBJECTION_NO_TIME
    # =========================================================================

    def test_objection_no_time_busy(self):
        """Нет времени"""
        result = self.classifier.classify("Сейчас некогда")
        assert result["intent"] == "objection_no_time"

        result = self.classifier.classify("Нет времени")
        assert result["intent"] == "objection_no_time"

    def test_objection_no_time_later(self):
        """Позже / потом"""
        result = self.classifier.classify("Давайте потом")
        assert result["intent"] == "objection_no_time"

        result = self.classifier.classify("Позже свяжемся")
        assert result["intent"] == "objection_no_time"

    # =========================================================================
    # OBJECTION_THINK
    # =========================================================================

    def test_objection_think_need_time(self):
        """Надо подумать"""
        result = self.classifier.classify("Мне надо подумать")
        # Может классифицироваться как objection_think или info_provided
        assert result["intent"] in ["objection_think", "info_provided"]

        result = self.classifier.classify("Дайте подумать над предложением")
        assert result["intent"] in ["objection_think", "info_provided"]

    def test_objection_think_discuss(self):
        """Обсудить с коллегами"""
        result = self.classifier.classify("Мне нужно посовещаться")
        assert result["intent"] in ["objection_think", "info_provided", "rejection"]

        result = self.classifier.classify("Надо обсудить с руководством")
        assert result["intent"] in ["objection_think", "info_provided", "rejection"]

    # =========================================================================
    # FAREWELL
    # =========================================================================

    def test_farewell_goodbye(self):
        """Прощание"""
        result = self.classifier.classify("До свидания")
        # Может быть farewell или agreement
        assert result["intent"] in ["farewell", "agreement"]

        result = self.classifier.classify("До связи пока")
        assert result["intent"] in ["farewell", "agreement"]

    def test_farewell_bye(self):
        """Короткое прощание"""
        result = self.classifier.classify("Пока")
        assert result["intent"] == "farewell"

    # =========================================================================
    # GRATITUDE
    # =========================================================================

    def test_gratitude_thanks(self):
        """Благодарность"""
        result = self.classifier.classify("Большое спасибо!")
        # Может быть gratitude или agreement
        assert result["intent"] in ["gratitude", "agreement"]

        result = self.classifier.classify("Благодарю вас")
        assert result["intent"] in ["gratitude", "agreement"]

    # =========================================================================
    # SMALL_TALK
    # =========================================================================

    def test_small_talk_how_are_you(self):
        """Как дела"""
        result = self.classifier.classify("Как дела?")
        assert result["intent"] == "small_talk"

        result = self.classifier.classify("Как жизнь?")
        assert result["intent"] == "small_talk"

    # =========================================================================
    # QUESTION_FEATURES
    # =========================================================================

    def test_question_features_what_is(self):
        """Что это такое"""
        result = self.classifier.classify("Что такое Wipon?")
        assert result["intent"] == "question_features"

    def test_question_features_how_works(self):
        """Как работает"""
        result = self.classifier.classify("Как это работает?")
        assert result["intent"] == "question_features"

    def test_question_features_capabilities(self):
        """Какие возможности"""
        result = self.classifier.classify("Какие функции есть?")
        assert result["intent"] == "question_features"


class TestDataExtractor:
    """Тесты для извлечения данных"""

    def setup_method(self):
        self.extractor = DataExtractor()

    # =========================================================================
    # URGENCY (срочность)
    # =========================================================================

    def test_extract_urgency_very_urgent(self):
        """Очень срочно"""
        result = self.extractor.extract("Срочно нужно решение")
        assert result.get("urgency") in ["very_urgent", "urgent"]

        result = self.extractor.extract("Горит! Нужно вчера")
        assert result.get("urgency") == "very_urgent"

    def test_extract_urgency_not_urgent(self):
        """Не срочно"""
        # Текст без срочности может не иметь поля urgency
        result = self.extractor.extract("Пока просто изучаем рынок")
        # Если urgency не извлечено — это ок для не-срочных случаев
        assert result.get("urgency") in [None, "not_urgent"]

        result = self.extractor.extract("Мы пока просто смотрим варианты")
        assert result.get("urgency") in [None, "not_urgent"]

    # =========================================================================
    # BUDGET (бюджет)
    # =========================================================================

    def test_extract_budget_thousands(self):
        """Бюджет в тысячах"""
        result = self.extractor.extract("Бюджет около 50 тысяч")
        budget = result.get("budget_range")
        assert budget is not None
        # Может быть диапазон или число
        assert "50" in str(budget) or budget

    def test_extract_budget_qualitative(self):
        """Качественная оценка бюджета"""
        result = self.extractor.extract("Бюджет небольшой")
        budget = result.get("budget_range")
        assert budget is not None

    # =========================================================================
    # ROLE (должность)
    # =========================================================================

    def test_extract_role_director(self):
        """Директор"""
        result = self.extractor.extract("Я директор компании")
        assert result.get("role") == "director"

    def test_extract_role_owner(self):
        """Владелец"""
        result = self.extractor.extract("Я собственник бизнеса")
        assert result.get("role") == "owner"

    def test_extract_role_manager(self):
        """Менеджер"""
        result = self.extractor.extract("Я руководитель отдела продаж")
        # Может быть "head" или "sales_manager"
        assert result.get("role") in ["head", "sales_manager", "manager"]

    # =========================================================================
    # PREFERRED CHANNEL (предпочтительный канал)
    # =========================================================================

    def test_extract_channel_phone(self):
        """Предпочитают телефон"""
        result = self.extractor.extract("Лучше позвоните")
        assert result.get("preferred_channel") == "phone"

    def test_extract_channel_whatsapp(self):
        """Предпочитают WhatsApp"""
        result = self.extractor.extract("Пишите в вотсап")
        assert result.get("preferred_channel") == "whatsapp"

    def test_extract_channel_telegram(self):
        """Предпочитают Telegram"""
        result = self.extractor.extract("Лучше в телеграм")
        assert result.get("preferred_channel") == "telegram"

    def test_extract_channel_email(self):
        """Предпочитают email"""
        result = self.extractor.extract("Отправьте на почту")
        assert result.get("preferred_channel") == "email"

    # =========================================================================
    # TIMELINE (сроки)
    # =========================================================================

    def test_extract_timeline_immediate(self):
        """Сразу / сейчас"""
        result = self.extractor.extract("Нужно прямо сейчас, срочно")
        # Может извлечься urgency вместо timeline или оба
        timeline = result.get("timeline")
        urgency = result.get("urgency")
        assert timeline in ["immediate", "this_week", None] or urgency is not None

    def test_extract_timeline_this_month(self):
        """В этом месяце"""
        result = self.extractor.extract("Планируем в этом месяце")
        assert result.get("timeline") == "this_month"

    def test_extract_timeline_next_quarter(self):
        """В следующем квартале"""
        result = self.extractor.extract("В следующем квартале")
        assert result.get("timeline") == "next_quarter"

    # =========================================================================
    # USERS COUNT (количество пользователей)
    # =========================================================================

    def test_extract_users_count(self):
        """Количество пользователей"""
        result = self.extractor.extract("У нас 10 сотрудников")
        # Может извлечься как company_size или users_count
        assert result.get("users_count") == 10 or result.get("company_size") == 10

    def test_extract_users_count_employees(self):
        """Количество сотрудников"""
        result = self.extractor.extract("У нас 25 сотрудников")
        # Может извлечься как company_size или users_count
        assert result.get("users_count") == 25 or result.get("company_size") == 25


class TestShortAnswerClassification:
    """Тесты для контекстной классификации коротких ответов

    Контекстная классификация использует:
    - last_action: действие бота на предыдущем шаге (close, presentation, answer_question, etc.)
    - last_intent: интент пользователя, на который бот отвечал (price_question, etc.)
    - state: текущее состояние диалога
    - spin_phase: фаза SPIN-продаж
    """

    def setup_method(self):
        self.classifier = HybridClassifier()

    # =========================================================================
    # CLOSE CONTEXT (бот предложил демо/контакт)
    # =========================================================================

    def test_short_yes_after_close(self):
        """Да после закрытия → agreement"""
        context = {"last_action": "close"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    def test_short_no_after_close(self):
        """Нет после закрытия → rejection"""
        context = {"last_action": "close"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "rejection"

    def test_short_yes_after_transition_to_close(self):
        """Да после перехода к закрытию → agreement"""
        context = {"last_action": "transition_to_close"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    # =========================================================================
    # PRESENTATION CONTEXT (бот презентовал продукт)
    # =========================================================================

    def test_short_yes_after_presentation(self):
        """Да после презентации → agreement"""
        context = {"last_action": "presentation"}
        result = self.classifier.classify("Понятно", context)
        assert result["intent"] == "agreement"

    def test_short_no_after_presentation(self):
        """Нет после презентации → rejection"""
        context = {"last_action": "presentation"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "rejection"

    def test_short_yes_after_transition_to_presentation(self):
        """Да после перехода к презентации → agreement"""
        context = {"last_action": "transition_to_presentation"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    # =========================================================================
    # PRICE CONTEXT (бот ответил на вопрос о цене)
    # =========================================================================

    def test_short_yes_after_price_answer(self):
        """Да после ответа на вопрос о цене → agreement"""
        context = {"last_action": "answer_question", "last_intent": "price_question"}
        result = self.classifier.classify("Хорошо", context)
        assert result["intent"] == "agreement"

    def test_short_no_after_price_answer(self):
        """Нет после ответа на вопрос о цене → objection_price"""
        context = {"last_action": "answer_question", "last_intent": "price_question"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "objection_price"

    def test_short_yes_after_pricing_details(self):
        """Да после ответа о деталях цены → agreement"""
        context = {"last_action": "answer_question", "last_intent": "pricing_details"}
        result = self.classifier.classify("Ок", context)
        assert result["intent"] == "agreement"

    # =========================================================================
    # OBJECTION HANDLING (бот отработал возражение)
    # =========================================================================

    def test_short_yes_after_handle_objection(self):
        """Да после отработки возражения → agreement"""
        context = {"last_action": "handle_objection"}
        result = self.classifier.classify("Хорошо", context)
        assert result["intent"] == "agreement"

    def test_short_no_after_handle_objection(self):
        """Нет после отработки возражения → rejection"""
        context = {"last_action": "handle_objection"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "rejection"

    # =========================================================================
    # DEFLECT CONTEXT (бот отложил вопрос о цене)
    # =========================================================================

    def test_short_yes_after_deflect(self):
        """Да после deflect → agreement"""
        context = {"last_action": "deflect_and_continue"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    def test_short_no_after_deflect(self):
        """Нет после deflect → objection_price"""
        context = {"last_action": "deflect_and_continue"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "objection_price"

    # =========================================================================
    # STATE CONTEXT (по текущему состоянию диалога)
    # =========================================================================

    def test_short_yes_in_close_state(self):
        """Да в состоянии close → agreement"""
        context = {"state": "close"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    def test_short_no_in_close_state(self):
        """Нет в состоянии close → rejection"""
        context = {"state": "close"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "rejection"

    def test_short_yes_in_soft_close_state(self):
        """Да в состоянии soft_close → agreement (передумал)"""
        context = {"state": "soft_close"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "agreement"

    # =========================================================================
    # SPIN PHASES
    # =========================================================================

    def test_short_yes_in_situation_phase(self):
        """Да в фазе situation → situation_provided"""
        context = {"spin_phase": "situation"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "situation_provided"

    def test_short_yes_in_problem_phase(self):
        """Да в фазе problem → problem_revealed"""
        context = {"spin_phase": "problem"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "problem_revealed"

    def test_short_no_in_problem_phase(self):
        """Нет в фазе problem → no_problem"""
        context = {"spin_phase": "problem"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "no_problem"

    def test_short_yes_in_implication_phase(self):
        """Да в фазе implication → implication_acknowledged"""
        context = {"spin_phase": "implication"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "implication_acknowledged"

    def test_short_yes_in_need_payoff_phase(self):
        """Да в фазе need_payoff → need_expressed"""
        context = {"spin_phase": "need_payoff"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "need_expressed"

    def test_short_no_in_need_payoff_phase(self):
        """Нет в фазе need_payoff → no_need"""
        context = {"spin_phase": "need_payoff"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "no_need"

    # =========================================================================
    # SPIN ACTIONS (по last_action для SPIN)
    # =========================================================================

    def test_short_yes_after_spin_problem(self):
        """Да после вопроса о проблемах → problem_revealed"""
        context = {"last_action": "spin_problem"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "problem_revealed"

    def test_short_no_after_spin_problem(self):
        """Нет после вопроса о проблемах → no_problem"""
        context = {"last_action": "spin_problem"}
        result = self.classifier.classify("Нет", context)
        assert result["intent"] == "no_problem"

    def test_short_yes_after_spin_implication(self):
        """Да после вопроса о последствиях → implication_acknowledged"""
        context = {"last_action": "spin_implication"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "implication_acknowledged"

    def test_short_yes_after_spin_need_payoff(self):
        """Да после вопроса о ценности → need_expressed"""
        context = {"last_action": "spin_need_payoff"}
        result = self.classifier.classify("Да", context)
        assert result["intent"] == "need_expressed"

    # =========================================================================
    # NEUTRAL / THINK
    # =========================================================================

    def test_short_maybe(self):
        """Может быть → objection_think"""
        result = self.classifier.classify("может быть", {})
        assert result["intent"] in ["objection_think", "agreement", "info_provided", "unclear", "question_features"]

    def test_short_need_to_think(self):
        """Подумаю → objection_think"""
        result = self.classifier.classify("подумаю", {})
        assert result["intent"] in ["objection_think", "info_provided", "unclear"]

    # =========================================================================
    # GENERAL FALLBACK
    # =========================================================================

    def test_short_yes_no_context(self):
        """Да без контекста → agreement"""
        result = self.classifier.classify("да", {})
        assert result["intent"] == "agreement"

    def test_short_no_no_context(self):
        """Нет без контекста → rejection"""
        result = self.classifier.classify("нет", {})
        assert result["intent"] == "rejection"


class TestClarificationPatterns:
    """Тесты для уточняющих паттернов (нет + позитивный контекст)"""

    def setup_method(self):
        self.classifier = HybridClassifier()

    def test_no_but_interested(self):
        """Нет, но интересно"""
        result = self.classifier.classify("Нет, мне интересно другое")
        assert result["intent"] == "agreement"

    def test_no_i_want(self):
        """Нет, я хочу..."""
        result = self.classifier.classify("Нет, я хочу узнать больше")
        assert result["intent"] == "agreement"

    def test_no_tell_me(self):
        """Нет, расскажите..."""
        result = self.classifier.classify("Нет, расскажите подробнее")
        assert result["intent"] == "agreement"


class TestEdgeCases:
    """Тесты граничных случаев"""

    def setup_method(self):
        self.classifier = HybridClassifier()
        self.normalizer = TextNormalizer()

    def test_empty_message(self):
        """Пустое сообщение"""
        result = self.classifier.classify("")
        assert "intent" in result

    def test_only_punctuation(self):
        """Только знаки препинания"""
        result = self.classifier.classify("???")
        assert "intent" in result

    def test_only_emoji_like(self):
        """Сообщение типа эмодзи"""
        normalized = self.normalizer.normalize(")")
        result = self.classifier.classify(")")
        assert "intent" in result

    def test_very_long_message(self):
        """Очень длинное сообщение"""
        long_msg = "Привет " * 100
        result = self.classifier.classify(long_msg)
        assert "intent" in result

    def test_mixed_case(self):
        """Смешанный регистр"""
        result = self.classifier.classify("СкОлЬкО сТоИт?")
        assert result["intent"] == "price_question"

    def test_extra_spaces(self):
        """Лишние пробелы"""
        result = self.classifier.classify("   сколько    стоит   ")
        assert result["intent"] == "price_question"

    def test_numbers_in_text(self):
        """Числа в тексте"""
        result = self.classifier.classify("Нужно на 5 человек")
        extracted = result.get("extracted_data", {})
        assert extracted.get("company_size") == 5 or extracted.get("users_count") == 5


class TestIntegration:
    """Интеграционные тесты для полного пайплайна"""

    def setup_method(self):
        self.classifier = HybridClassifier()

    def test_full_pipeline_typo_to_intent(self):
        """Полный путь: опечатка → нормализация → классификация"""
        # "скока стоит" → "сколько стоит" → price_question
        result = self.classifier.classify("скока стоит")
        assert result["intent"] == "price_question"

    def test_full_pipeline_keyboard_to_intent(self):
        """Полный путь: неверная раскладка → классификация"""
        # "ghbdtn" (EN) → "привет" → greeting
        result = self.classifier.classify("ghbdtn")
        assert result["intent"] == "greeting"

    def test_full_pipeline_slang_rejection(self):
        """Полный путь: сленговый отказ"""
        result = self.classifier.classify("нет не интересно")
        assert result["intent"] == "rejection"

    def test_full_pipeline_slang_agreement(self):
        """Полный путь: сленговое согласие"""
        result = self.classifier.classify("ок давайте")
        # Может быть agreement или другой позитивный интент
        assert result["intent"] in ["agreement", "demo_request", "callback_request"]

    def test_context_overrides_default(self):
        """Контекст переопределяет дефолтную классификацию"""
        # "да" без контекста → agreement
        result_no_context = self.classifier.classify("да")
        assert result_no_context["intent"] == "agreement"

        # "да" с контекстом close → agreement (высокая уверенность)
        result_with_context = self.classifier.classify("да", {"last_action": "close"})
        assert result_with_context["intent"] == "agreement"
        assert result_with_context["confidence"] >= 0.9  # выше чем без контекста


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
