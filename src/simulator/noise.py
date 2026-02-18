"""
Генератор реалистичного шума для сообщений клиентов.

Добавляет:
- Опечатки
- Сленг и сокращения
- Пропуск заглавных букв
- Пропуск знаков препинания
"""

import random
import re
from typing import Dict, List


# Типичные опечатки (слово -> варианты с ошибками)
TYPOS: Dict[str, List[str]] = {
    "сколько": ["скока", "скольк", "сколко", "скока"],
    "привет": ["прив", "привет)", "приветт", "превет"],
    "хорошо": ["хорош", "хорошл", "харашо", "хорошь"],
    "понятно": ["понятн", "панятно", "понятнл", "панятн"],
    "интересно": ["интерсно", "интересн", "инетерсно", "интерестно"],
    "спасибо": ["спс", "спасиб", "пасиб", "спс)"],
    "пожалуйста": ["пж", "пожлста", "пожалуста", "пжлст"],
    "здравствуйте": ["здраствуйте", "здрасте", "здрасьте"],
    "подскажите": ["подскажте", "падскажите", "подскжите"],
    "стоимость": ["стоимсть", "стоимоть", "стоимсоть"],
    "система": ["систма", "ситема", "систама"],
    "работает": ["работет", "роботает", "работаит"],
    "компания": ["компаня", "кампания", "компани"],
    "клиенты": ["клиэнты", "клиены", "клиентов"],
    "проблема": ["праблема", "проблемма", "проблма"],
    "дорого": ["дорага", "дороко", "дорого)"],
    "можно": ["можна", "можн", "мона"],
    "нужно": ["нужна", "нужн", "нужнa"],
    "почему": ["почму", "пачему", "почи|му"],
    "конечно": ["канечно", "конечн", "канешн"],
    "оборудование": ["оборудовани", "оборудоания", "оборудованые"],
    "программа": ["програма", "програмка", "программ"],
    "установка": ["установк", "установки", "устновка"],
    "подключение": ["подключени", "подклюение", "подключени"],
    "рассрочка": ["рассрочк", "расрочка", "расрочк"],
}

# Казахские слова-вставки для реалистичности (характерны для рынка Казахстана)
KAZAKH_INSERTS: List[str] = [
    "жаксы",    # хорошо
    "иә",       # да
    "болады",   # можно/окей
    "рахмет",   # спасибо
    "жоқ",      # нет
    "ок",       # ок (используется и в казахской речи)
]

# Казахские приветствия для замены "здравствуйте"
KAZAKH_GREETINGS: List[str] = [
    "Саляматсызба",
    "Сәлеметсіз бе",
    "Сәлем",
    "Салем",
]

# Сокращения разговорной речи
SHORTENINGS: Dict[str, str] = {
    "что": "чо",
    "сейчас": "щас",
    "вообще": "ваще",
    "нормально": "норм",
    "наверное": "наверн",
    "хорошо": "ок",
    "ладно": "лан",
    "сегодня": "седня",
    "потому что": "потому чо",
    "в общем": "короч",
}

# Частицы и слова-паразиты для добавления
FILLER_WORDS = [
    "ну", "типа", "как бы", "вот", "это", "короче",
]


def add_noise(text: str, intensity: float = 0.15) -> str:
    """
    Добавляет реалистичные ошибки в текст.

    Args:
        text: Исходный текст
        intensity: Интенсивность шума (0.0-1.0)

    Returns:
        Текст с добавленным шумом
    """
    if not text:
        return text

    # 30% - убрать заглавную букву в начале
    if random.random() < 0.3:
        text = text[0].lower() + text[1:] if len(text) > 1 else text.lower()

    # 25% - убрать точку в конце
    if random.random() < 0.25:
        text = text.rstrip('.')

    # 20% - убрать запятые
    if random.random() < 0.2:
        text = text.replace(',', '')

    # intensity% - добавить опечатку
    if random.random() < intensity:
        text = _add_typo(text)

    # 10% - использовать сокращение
    if random.random() < 0.1:
        text = _add_shortening(text)

    # 5% - дублировать букву
    if random.random() < 0.05 and len(text) > 3:
        text = _duplicate_letter(text)

    # 5% - добавить слово-паразит в начало
    if random.random() < 0.05:
        filler = random.choice(FILLER_WORDS)
        text = f"{filler} {text}"

    # 3% - пропустить пробел
    if random.random() < 0.03 and ' ' in text:
        text = _skip_space(text)

    return text


def _add_typo(text: str) -> str:
    """Добавляет опечатку в текст"""
    text_lower = text.lower()
    for word, typos in TYPOS.items():
        if word in text_lower:
            typo = random.choice(typos)
            # Сохраняем регистр первой буквы если была заглавная
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            match = pattern.search(text)
            if match:
                original = match.group()
                if original[0].isupper() and typo:
                    typo = typo[0].upper() + typo[1:]
                text = pattern.sub(typo, text, count=1)
            break
    return text


def _add_shortening(text: str) -> str:
    """Заменяет слова на сокращения"""
    for full, short in SHORTENINGS.items():
        if full in text.lower():
            pattern = re.compile(re.escape(full), re.IGNORECASE)
            text = pattern.sub(short, text, count=1)
            break
    return text


def _duplicate_letter(text: str) -> str:
    """Дублирует случайную букву"""
    if len(text) < 3:
        return text

    # Выбираем случайную позицию (не первую и не последнюю)
    pos = random.randint(1, len(text) - 2)

    # Дублируем только буквы
    if text[pos].isalpha():
        text = text[:pos] + text[pos] + text[pos:]

    return text


def _skip_space(text: str) -> str:
    """Пропускает случайный пробел"""
    spaces = [i for i, c in enumerate(text) if c == ' ']
    if spaces:
        pos = random.choice(spaces)
        text = text[:pos] + text[pos+1:]
    return text


def add_heavy_noise(text: str) -> str:
    """Добавляет много шума - для агрессивных/занятых персон"""
    return add_noise(text, intensity=0.3)


def add_light_noise(text: str) -> str:
    """Добавляет мало шума - для технических персон"""
    return add_noise(text, intensity=0.05)


def add_kazakh_noise(text: str) -> str:
    """
    Добавляет казахский языковой шум — для казахоязычных персон.

    Имитирует реальных клиентов из Казахстана, которые пишут на казахском
    или смешивают казахский с русским (как в реальных диалогах ОП).
    """
    if not text:
        return text

    # 40% — убрать заглавную букву (казахские сообщения часто без регистра)
    if random.random() < 0.4:
        text = text[0].lower() + text[1:] if len(text) > 1 else text.lower()

    # 30% — убрать знаки препинания в конце
    if random.random() < 0.3:
        text = text.rstrip('.,!?')

    # 25% — заменить "здравствуйте" на казахское приветствие
    text_lower = text.lower()
    if random.random() < 0.25 and any(g in text_lower for g in ["здравствуй", "здраст", "привет", "добрый"]):
        greeting = random.choice(KAZAKH_GREETINGS)
        for ru_greeting in ["здравствуйте", "здрасте", "привет", "добрый день", "добрый вечер"]:
            if ru_greeting in text_lower:
                pattern = re.compile(re.escape(ru_greeting), re.IGNORECASE)
                text = pattern.sub(greeting, text, count=1)
                break

    # 20% — заменить "да" / "хорошо" / "спасибо" на казахский эквивалент
    if random.random() < 0.2:
        replacements = {
            "да": "иә",
            "хорошо": "жаксы",
            "спасибо": "рахмет",
            "можно": "болады",
            "нет": "жоқ",
            "ок": "болды",
        }
        for ru_word, kk_word in replacements.items():
            # Только если это отдельное слово (не часть другого)
            pattern = re.compile(r'\b' + re.escape(ru_word) + r'\b', re.IGNORECASE)
            if pattern.search(text):
                text = pattern.sub(kk_word, text, count=1)
                break

    # 10% — добавить казахское слово-вставку в конце
    if random.random() < 0.1:
        insert = random.choice(KAZAKH_INSERTS)
        text = f"{text} {insert}"

    return text
