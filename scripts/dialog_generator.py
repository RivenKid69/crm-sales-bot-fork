#!/usr/bin/env python3
"""
ГЕНЕРАТОР СЛУЧАЙНЫХ ДИАЛОГОВ ДЛЯ СТРЕСС-ТЕСТИРОВАНИЯ

Создаёт уникальные диалоговые сценарии при каждом запуске:
1. Вариации сообщений (синонимы, опечатки, порядок слов)
2. Случайная комбинация персон + тем
3. Динамическая генерация сценариев из templates
"""

import random
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# СЛОВАРИ ДЛЯ ВАРИАЦИЙ
# =============================================================================

# Синонимы для ключевых слов
SYNONYMS = {
    "цена": ["стоимость", "прайс", "почём", "сколько стоит", "тариф", "расценки"],
    "сколько": ["почём", "какая цена", "во сколько обойдётся", "прайс"],
    "бесплатно": ["без оплаты", "даром", "free", "бесплатный", "на халяву"],
    "касса": ["ккм", "кассовый аппарат", "онлайн-касса", "pos"],
    "функции": ["возможности", "что умеет", "фичи", "функционал"],
    "интеграция": ["подключение", "связка", "синхронизация", "коннект"],
    "помощь": ["поддержка", "саппорт", "support", "помогите"],
    "быстро": ["срочно", "скорее", "asap", "побыстрее"],
    "хорошо": ["ок", "окей", "ok", "ладно", "давайте", "согласен"],
    "нет": ["не надо", "не нужно", "отказ", "не интересно", "pass"],
    "привет": ["здравствуйте", "добрый день", "хай", "салам", "hello", "hi"],
    "спасибо": ["благодарю", "thanks", "thx", "спс"],
    "дорого": ["дороговато", "много", "не по карману", "expensive"],
    "магазин": ["точка", "торговая точка", "лавка", "shop", "маркет"],
    "товар": ["продукт", "позиция", "артикул", "sku"],
    "склад": ["хранение", "warehouse", "остатки"],
    "отчёт": ["репорт", "report", "аналитика", "статистика"],
}

# Типичные опечатки
TYPOS = {
    "сколько": ["скока", "скоко", "сколкьо", "скольок"],
    "стоит": ["стоет", "стоитт", "стоид"],
    "цена": ["цна", "ценна", "цен"],
    "прайс": ["прас", "прайз", "праис", "прайсс"],
    "касса": ["каса", "касаа", "кассса"],
    "бесплатно": ["беслатно", "бесплатна", "безплатно"],
    "интеграция": ["интеграцыя", "интиграция", "интегарция"],
    "здравствуйте": ["здраствуйте", "здрасте", "здрасьте"],
    "пожалуйста": ["пожалуста", "пожалста", "плз", "плиз", "pls"],
    "спасибо": ["спасиба", "спс", "спсб", "пасиб"],
    "хорошо": ["хорашо", "харашо", "хрш"],
    "работает": ["работаит", "работает", "робит"],
    "подключить": ["подлючить", "подключть", "падключить"],
    "оборудование": ["оборудованиe", "абарудование", "оборуд"],
    "алкоголь": ["алкоголь", "алкагол", "алко"],
}

# Сленг и разговорные формы
SLANG = {
    "программа": ["прога", "софт", "апп"],
    "компьютер": ["комп", "пк", "pc"],
    "телефон": ["мобила", "трубка", "смарт"],
    "интернет": ["инет", "сеть", "wifi"],
    "нормально": ["норм", "збс", "гуд", "ок"],
    "проблема": ["проблемка", "траблы", "косяк"],
    "деньги": ["бабки", "денюжки", "кэш"],
    "быстро": ["быстренько", "по-быстрому", "шустро"],
    "работать": ["пахать", "юзать", "работать"],
}

# Эмоциональные модификаторы
EMOTIONAL_PREFIX = [
    "", "", "",  # Часто без эмоций
    "Срочно! ", "СРОЧНО ", "!!!", "Помогите, ",
    "Пожалуйста, ", "Очень нужно ", "Подскажите, ",
]

EMOTIONAL_SUFFIX = [
    "", "", "",  # Часто без эмоций
    "!", "!!", "!!!", "?", "???",
    " пожалуйста", " плиз", " срочно", " очень нужно",
]

# Приветствия по персонам
GREETINGS = {
    "formal": [
        "Добрый день!",
        "Здравствуйте!",
        "Добрый день, подскажите пожалуйста",
        "Здравствуйте, хотел бы узнать",
    ],
    "casual": [
        "Привет",
        "Хай",
        "Прив",
        "Здарова",
        "Салам",
    ],
    "aggressive": [
        "Эй!",
        "Алло!",
        "Слушайте!",
        "Так!",
    ],
    "silent": [
        ".",
        "Да",
        "Ну",
    ],
}

# Прощания/согласия по персонам
AGREEMENTS = {
    "formal": [
        "Хорошо, давайте попробуем",
        "Согласен, оставлю заявку",
        "Да, подключайте",
        "Отлично, как оформить?",
    ],
    "casual": [
        "Ок, погнали",
        "Давай",
        "Ну ок",
        "Го",
        "Лан, беру",
    ],
    "aggressive": [
        "Ладно, давайте быстрее",
        "Хорошо, только быстро!",
        "Окей, оформляйте",
    ],
    "silent": [
        "Да",
        "Ок",
        "+",
    ],
}

# Отказы по персонам
REJECTIONS = {
    "formal": [
        "Спасибо, но пока не интересно",
        "Я подумаю, спасибо за информацию",
        "Не совсем то, что нужно",
    ],
    "casual": [
        "Не, пас",
        "Неа",
        "Не надо",
        "Не катит",
    ],
    "aggressive": [
        "Нет! Дорого!",
        "Не интересует!",
        "Отстаньте",
    ],
    "silent": [
        "Нет",
        "-",
        "Не",
    ],
}


# =============================================================================
# ТЕМЫ ДЛЯ ГЕНЕРАЦИИ
# =============================================================================

@dataclass
class TopicTemplate:
    """Шаблон темы для генерации вопросов"""
    topic: str
    category: str
    questions: List[str]
    expected_keywords: List[str]
    follow_ups: List[str] = field(default_factory=list)


TOPIC_TEMPLATES = [
    TopicTemplate(
        topic="tariffs",
        category="pricing",
        questions=[
            "Сколько стоит {product}?",
            "Какая цена на {product}?",
            "Прайс на {product}",
            "Тарифы какие?",
            "Почём {product}?",
            "Цена?",
        ],
        expected_keywords=["тариф", "Mini", "Lite"],
        follow_ups=[]  # Follow-ups убраны, т.к. они контекстно-зависимы
    ),
    TopicTemplate(
        topic="free",
        category="pricing",
        questions=[
            "Есть бесплатная версия?",
            "Можно попробовать бесплатно?",
            "Триал есть?",
            "Демо можно?",
            "Бесплатно что-то есть?",
        ],
        expected_keywords=["бесплатн"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="wipon_kassa",
        category="products",
        questions=[
            "Расскажите про кассу",
            "Нужна онлайн-касса",
            "Как пробивать чеки?",
            "ОФД подключен?",
            "Касса на телефон есть?",
        ],
        expected_keywords=["касс", "ОФД"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="wipon_pro",
        category="products",
        questions=[
            "Как проверять алкоголь?",
            "УКМ марки как сканировать?",
            "Нужна проверка алкогольных марок",
            "Wipon Pro что это?",
        ],
        expected_keywords=["алкоголь", "УКМ"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="marketplaces",
        category="integrations",
        questions=[
            "Работаете с Kaspi?",
            "Есть интеграция с маркетплейсами?",
            "Каспи магазин подключается?",
            "Халык банк работает?",
        ],
        expected_keywords=["Kaspi", "Halyk", "маркетплейс"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="1c",
        category="integrations",
        questions=[
            "Есть выгрузка в 1С?",
            "1С подключается?",
            "Данные в 1С как передавать?",
        ],
        expected_keywords=["1С", "выгрузк"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="hardware",
        category="equipment",
        questions=[
            "Какое оборудование нужно?",
            "Сканер какой подойдёт?",
            "Принтер чеков совместим?",
            "Весы подключаются?",
        ],
        expected_keywords=["сканер", "принтер", "оборудован", "весы"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="coverage",
        category="regions",
        questions=[
            "Работаете в {city}?",
            "В {city} есть представитель?",
            "По всему Казахстану работаете?",
            "Доставляете в регионы?",
        ],
        expected_keywords=["Казахстан", "Алматы", "доставк"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="help",
        category="support",
        questions=[
            "Есть техподдержка?",
            "Обучение проводите?",
            "Как получить помощь?",
        ],
        expected_keywords=["поддержк", "обучен"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="switching",
        category="migration",
        questions=[
            "Данные можно перенести?",
            "Импорт из Excel есть?",
            "Как перейти с другой программы?",
        ],
        expected_keywords=["перенос", "импорт", "переход"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="data_protection",
        category="security",
        questions=[
            "Данные защищены?",
            "Бэкапы делаете?",
            "Шифрование есть?",
        ],
        expected_keywords=["защит", "бэкап", "шифрован"],
        follow_ups=[]
    ),
    TopicTemplate(
        topic="vs_others",
        category="competitors",
        questions=[
            "Чем лучше iiko?",
            "Почему не Poster?",
            "В чём отличие от конкурентов?",
        ],
        expected_keywords=["iiko", "Poster", "дешевле", "проще"],
        follow_ups=[]
    ),
]

# Переменные для подстановки
PRODUCTS = ["программу", "систему", "кассу", "учёт", "Wipon", "подписку"]
CITIES = ["Алматы", "Астане", "Караганде", "Шымкенте", "Актобе", "регионах"]
COMPETITORS = ["1С", "iiko", "Poster", "R-Keeper", "другой программы", "Excel"]
BUSINESS_TYPES = ["магазин продуктов", "аптеку", "ресторан", "кафе", "алкомаркет", "оптовый склад"]


# =============================================================================
# ГЕНЕРАТОР ВАРИАЦИЙ
# =============================================================================

class MessageVariator:
    """Генератор вариаций сообщений"""

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)

    def apply_typos(self, text: str, probability: float = 0.3) -> str:
        """Добавить случайные опечатки"""
        if random.random() > probability:
            return text

        words = text.split()
        for i, word in enumerate(words):
            word_lower = word.lower()
            if word_lower in TYPOS and random.random() < 0.5:
                typo = random.choice(TYPOS[word_lower])
                # Сохраняем регистр первой буквы
                if word[0].isupper():
                    typo = typo.capitalize()
                words[i] = typo
        return " ".join(words)

    def apply_synonyms(self, text: str, probability: float = 0.4) -> str:
        """Заменить слова на синонимы"""
        if random.random() > probability:
            return text

        result = text
        for word, syns in SYNONYMS.items():
            if word in result.lower() and random.random() < 0.5:
                syn = random.choice(syns)
                # Заменяем с учётом регистра
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                result = pattern.sub(syn, result, count=1)
        return result

    def apply_slang(self, text: str, probability: float = 0.2) -> str:
        """Заменить на сленг"""
        if random.random() > probability:
            return text

        result = text
        for word, slangs in SLANG.items():
            if word in result.lower() and random.random() < 0.5:
                slang = random.choice(slangs)
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                result = pattern.sub(slang, result, count=1)
        return result

    def apply_emotions(self, text: str, probability: float = 0.3) -> str:
        """Добавить эмоциональные модификаторы"""
        if random.random() > probability:
            return text

        prefix = random.choice(EMOTIONAL_PREFIX)
        suffix = random.choice(EMOTIONAL_SUFFIX)
        return f"{prefix}{text}{suffix}"

    def change_case(self, text: str, probability: float = 0.2) -> str:
        """Изменить регистр"""
        if random.random() > probability:
            return text

        choice = random.choice(["lower", "upper", "normal"])
        if choice == "lower":
            return text.lower()
        elif choice == "upper":
            return text.upper()
        return text

    def shuffle_words(self, text: str, probability: float = 0.1) -> str:
        """Перемешать порядок слов (осторожно)"""
        if random.random() > probability or len(text.split()) < 3:
            return text

        words = text.split()
        # Перемешиваем только часть слов, сохраняя смысл
        if len(words) > 2:
            mid = words[1:-1]
            random.shuffle(mid)
            words = [words[0]] + mid + [words[-1]]
        return " ".join(words)

    def generate_variation(self, text: str, persona: str = "casual") -> str:
        """Сгенерировать вариацию сообщения"""
        result = text

        # Настройки по персоне
        if persona == "formal":
            result = self.apply_synonyms(result, 0.2)
        elif persona == "casual":
            result = self.apply_typos(result, 0.3)
            result = self.apply_slang(result, 0.3)
            result = self.change_case(result, 0.3)
        elif persona == "aggressive":
            result = self.apply_emotions(result, 0.6)
            result = self.change_case(result, 0.3)
        elif persona == "techie":
            result = self.apply_synonyms(result, 0.3)
        elif persona == "newbie":
            result = self.apply_typos(result, 0.2)
            result = self.apply_emotions(result, 0.4)
        elif persona == "silent":
            # Укоротить сообщение, но сохранить минимум 2 слова для контекста
            words = result.split()
            if len(words) > 3:
                result = " ".join(words[:random.randint(2, 3)])
        else:
            result = self.apply_typos(result, 0.2)
            result = self.apply_synonyms(result, 0.3)

        return result


# =============================================================================
# ГЕНЕРАТОР СЦЕНАРИЕВ
# =============================================================================

@dataclass
class GeneratedTurn:
    """Сгенерированный ход диалога"""
    user_message: str
    original_message: str
    expected_topic: str
    expected_keywords: List[str]


@dataclass
class GeneratedScenario:
    """Сгенерированный сценарий"""
    name: str
    persona: str
    business_type: str
    turns: List[GeneratedTurn]


class ScenarioGenerator:
    """Генератор случайных сценариев"""

    def __init__(self, seed: int = None):
        self.variator = MessageVariator(seed)
        if seed is not None:
            random.seed(seed)

    def generate_scenario(self, persona: str = None, topics: List[str] = None) -> GeneratedScenario:
        """Сгенерировать один сценарий"""
        # Случайная персона если не указана
        if persona is None:
            persona = random.choice(["formal", "casual", "aggressive", "techie", "newbie", "silent"])

        # Случайный тип бизнеса
        business_type = random.choice(BUSINESS_TYPES)

        # Случайный набор тем если не указан
        if topics is None:
            num_topics = random.randint(2, 5)
            topics = random.sample([t.topic for t in TOPIC_TEMPLATES], num_topics)

        turns = []

        # 1. Приветствие (50% шанс)
        if random.random() < 0.5:
            greeting = random.choice(GREETINGS.get(persona, GREETINGS["casual"]))
            turns.append(GeneratedTurn(
                user_message=self.variator.generate_variation(greeting, persona),
                original_message=greeting,
                expected_topic="greeting",
                expected_keywords=[]
            ))

        # 2. Генерируем вопросы по темам
        for topic_name in topics:
            template = next((t for t in TOPIC_TEMPLATES if t.topic == topic_name), None)
            if not template:
                continue

            # Основной вопрос
            question = random.choice(template.questions)

            # Подстановка переменных
            question = question.replace("{product}", random.choice(PRODUCTS))
            question = question.replace("{city}", random.choice(CITIES))
            question = question.replace("{competitor}", random.choice(COMPETITORS))

            varied_question = self.variator.generate_variation(question, persona)

            turns.append(GeneratedTurn(
                user_message=varied_question,
                original_message=question,
                expected_topic=template.topic,
                expected_keywords=template.expected_keywords
            ))

            # Follow-up вопрос (30% шанс)
            if template.follow_ups and random.random() < 0.3:
                follow_up = random.choice(template.follow_ups)
                varied_follow_up = self.variator.generate_variation(follow_up, persona)
                turns.append(GeneratedTurn(
                    user_message=varied_follow_up,
                    original_message=follow_up,
                    expected_topic=template.topic,
                    expected_keywords=template.expected_keywords
                ))

        # 3. Завершение (согласие или отказ)
        if random.random() < 0.7:
            # Согласие
            agreement = random.choice(AGREEMENTS.get(persona, AGREEMENTS["casual"]))
            turns.append(GeneratedTurn(
                user_message=self.variator.generate_variation(agreement, persona),
                original_message=agreement,
                expected_topic="agreement",
                expected_keywords=[]
            ))
        else:
            # Отказ
            rejection = random.choice(REJECTIONS.get(persona, REJECTIONS["casual"]))
            turns.append(GeneratedTurn(
                user_message=self.variator.generate_variation(rejection, persona),
                original_message=rejection,
                expected_topic="rejection",
                expected_keywords=[]
            ))

        return GeneratedScenario(
            name=f"generated_{persona}_{business_type.replace(' ', '_')}_{random.randint(1000, 9999)}",
            persona=persona,
            business_type=business_type,
            turns=turns
        )

    def generate_batch(self, count: int = 10) -> List[GeneratedScenario]:
        """Сгенерировать пачку сценариев"""
        scenarios = []
        personas = ["formal", "casual", "aggressive", "techie", "newbie", "silent"]

        for i in range(count):
            # Распределяем персоны равномерно
            persona = personas[i % len(personas)]
            scenario = self.generate_scenario(persona=persona)
            scenarios.append(scenario)

        return scenarios

    def generate_edge_cases(self) -> List[GeneratedScenario]:
        """Сгенерировать граничные случаи"""
        edge_cases = []

        # 1. Очень короткие сообщения
        short_scenario = GeneratedScenario(
            name="edge_case_short",
            persona="silent",
            business_type="магазин",
            turns=[
                GeneratedTurn("?", "?", "unknown", []),
                GeneratedTurn("цена", "цена", "tariffs", ["тариф"]),
                GeneratedTurn("да", "да", "agreement", []),
            ]
        )
        edge_cases.append(short_scenario)

        # 2. Очень длинные сообщения
        long_message = """Здравствуйте, у меня такая ситуация. Я владею сетью из 3 магазинов продуктов
        в Алматы и области. Сейчас использую Excel для учёта, но это очень неудобно,
        постоянно теряются данные, нет синхронизации между точками.
        Мне нужна система которая умеет: учёт товаров, онлайн-кассу, интеграцию с Kaspi,
        аналитику продаж, учёт сотрудников. Ещё важно чтобы работало на телефоне.
        Бюджет ограничен, хотелось бы что-то недорогое. Что посоветуете?"""

        long_scenario = GeneratedScenario(
            name="edge_case_long",
            persona="confused",
            business_type="сеть магазинов",
            turns=[
                GeneratedTurn(long_message, long_message, "overview", ["Wipon"]),
                GeneratedTurn("Сколько это будет стоить?", "Сколько стоит?", "tariffs", ["тариф"]),
            ]
        )
        edge_cases.append(long_scenario)

        # 3. Только эмодзи и символы
        emoji_scenario = GeneratedScenario(
            name="edge_case_emoji",
            persona="casual",
            business_type="неизвестно",
            turns=[
                GeneratedTurn("👋", "👋", "greeting", []),
                GeneratedTurn("💰?", "💰?", "tariffs", []),
                GeneratedTurn("👍", "👍", "agreement", []),
            ]
        )
        edge_cases.append(emoji_scenario)

        # 4. Смешанный язык
        mixed_scenario = GeneratedScenario(
            name="edge_case_mixed_lang",
            persona="techie",
            business_type="it компания",
            turns=[
                GeneratedTurn("Hi, нужна POS система for retail", "Hi, нужна POS система", "overview", ["Wipon"]),
                GeneratedTurn("API есть? REST or GraphQL?", "API есть?", "common_questions", ["API"]),
                GeneratedTurn("Price list please", "Price list", "tariffs", ["тариф"]),
            ]
        )
        edge_cases.append(mixed_scenario)

        # 5. Агрессивные опечатки
        typo_scenario = GeneratedScenario(
            name="edge_case_typos",
            persona="casual",
            business_type="магазин",
            turns=[
                GeneratedTurn("прив скока стоет ваша праграма?", "привет сколько стоит программа", "tariffs", ["тариф"]),
                GeneratedTurn("а каспы падключить можна?", "а каспи подключить можно?", "marketplaces", ["Kaspi"]),
                GeneratedTurn("лан бирём", "ладно берём", "agreement", []),
            ]
        )
        edge_cases.append(typo_scenario)

        # 6. Негатив и возражения
        negative_scenario = GeneratedScenario(
            name="edge_case_negative",
            persona="aggressive",
            business_type="магазин",
            turns=[
                GeneratedTurn("У ВАС ДОРОГО!!!", "дорого", "objection_price", ["бесплатн"]),
                GeneratedTurn("У iiko лучше и дешевле!", "iiko лучше", "vs_others", ["iiko"]),
                GeneratedTurn("Ваш support отстой", "support плохой", "help", ["поддержк"]),
                GeneratedTurn("НЕТ СПАСИБО", "нет", "rejection", []),
            ]
        )
        edge_cases.append(negative_scenario)

        return edge_cases


# =============================================================================
# ТЕСТОВЫЙ ЗАПУСК
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ТЕСТ ГЕНЕРАТОРА ДИАЛОГОВ")
    print("=" * 60)

    generator = ScenarioGenerator()

    # Генерируем несколько сценариев
    print("\n--- Случайные сценарии ---")
    scenarios = generator.generate_batch(5)
    for sc in scenarios:
        print(f"\n[{sc.name}] Персона: {sc.persona}, Бизнес: {sc.business_type}")
        for turn in sc.turns:
            print(f"  User: {turn.user_message[:60]}...")
            print(f"  → Topic: {turn.expected_topic}")

    # Граничные случаи
    print("\n--- Граничные случаи ---")
    edge_cases = generator.generate_edge_cases()
    for sc in edge_cases:
        print(f"\n[{sc.name}]")
        for turn in sc.turns:
            print(f"  User: {turn.user_message[:60]}...")

    # Тест вариатора
    print("\n--- Тест вариатора ---")
    variator = MessageVariator()
    test_messages = [
        "Сколько стоит программа?",
        "Здравствуйте, расскажите о вашей системе",
        "Есть интеграция с Kaspi?",
    ]
    for msg in test_messages:
        print(f"\nОригинал: {msg}")
        for _ in range(3):
            varied = variator.generate_variation(msg, random.choice(["casual", "formal", "aggressive"]))
            print(f"  → {varied}")
