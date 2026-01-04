"""
Лемматизатор для русского языка.

Приводит слова к начальной форме:
- "предпринимателя" → "предприниматель"
- "розничного" → "розничный"
- "работают" → "работать"
"""

import re
from typing import List, Set, Optional
from functools import lru_cache

# Пробуем pymorphy3 (для Python 3.11+), затем pymorphy2
try:
    import pymorphy3 as pymorphy
    PYMORPHY_AVAILABLE = True
except ImportError:
    try:
        import pymorphy2 as pymorphy
        PYMORPHY_AVAILABLE = True
    except ImportError:
        PYMORPHY_AVAILABLE = False
        pymorphy = None
        print("[WARNING] pymorphy3/pymorphy2 not installed. Install with: pip install pymorphy3")


class Lemmatizer:
    """Лемматизатор с кэшированием."""

    def __init__(self):
        if PYMORPHY_AVAILABLE and pymorphy:
            self._morph = pymorphy.MorphAnalyzer()
        else:
            self._morph = None

        # Стоп-слова (предлоги, союзы, частицы)
        self._stop_words = {
            'и', 'в', 'на', 'с', 'к', 'по', 'за', 'из', 'от', 'до', 'о', 'об',
            'для', 'при', 'без', 'под', 'над', 'между', 'через', 'после', 'перед',
            'а', 'но', 'или', 'что', 'как', 'если', 'то', 'же', 'бы', 'ли',
            'не', 'ни', 'да', 'нет', 'вот', 'это', 'тот', 'этот', 'такой',
            'который', 'какой', 'чей', 'сам', 'самый', 'весь', 'все', 'всё',
            'мой', 'твой', 'его', 'её', 'их', 'наш', 'ваш', 'свой',
            'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они',
            'быть', 'есть', 'был', 'была', 'было', 'были', 'будет', 'будут',
            'можно', 'нужно', 'надо', 'ли', 'же', 'бы',
        }

    @lru_cache(maxsize=10000)
    def lemmatize_word(self, word: str) -> str:
        """
        Лемматизировать одно слово.

        Args:
            word: Слово для лемматизации

        Returns:
            Лемма (начальная форма) слова
        """
        if not word or len(word) < 2:
            return word.lower()

        word_lower = word.lower()

        if not self._morph:
            # Fallback: просто lowercase
            return word_lower

        parsed = self._morph.parse(word_lower)
        if parsed:
            return parsed[0].normal_form
        return word_lower

    def tokenize(self, text: str) -> List[str]:
        """
        Разбить текст на токены (слова).

        Args:
            text: Входной текст

        Returns:
            Список токенов
        """
        # Оставляем только буквы и цифры
        text = text.lower()
        tokens = re.findall(r'[a-zа-яёA-ZА-ЯЁ0-9]+', text)
        return tokens

    def lemmatize_text(self, text: str, remove_stop_words: bool = True) -> List[str]:
        """
        Лемматизировать текст.

        Args:
            text: Входной текст
            remove_stop_words: Удалять ли стоп-слова

        Returns:
            Список лемм
        """
        tokens = self.tokenize(text)
        lemmas = []

        for token in tokens:
            if remove_stop_words and token in self._stop_words:
                continue
            lemma = self.lemmatize_word(token)
            if lemma and len(lemma) >= 2:
                lemmas.append(lemma)

        return lemmas

    def lemmatize_to_set(self, text: str, remove_stop_words: bool = True) -> Set[str]:
        """
        Лемматизировать текст и вернуть множество уникальных лемм.

        Args:
            text: Входной текст
            remove_stop_words: Удалять ли стоп-слова

        Returns:
            Множество уникальных лемм
        """
        return set(self.lemmatize_text(text, remove_stop_words))


# Singleton
_lemmatizer: Optional[Lemmatizer] = None


def get_lemmatizer() -> Lemmatizer:
    """Получить глобальный экземпляр лемматизатора."""
    global _lemmatizer
    if _lemmatizer is None:
        _lemmatizer = Lemmatizer()
    return _lemmatizer
