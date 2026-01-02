"""
Гибридный классификатор интентов + извлечение данных

Архитектура:
1. Быстрая проверка по корням слов (INTENT_ROOTS)
2. Если confidence < threshold → fallback на pymorphy2 (лемматизация)
3. Извлечение данных (company_size, pain_point, contact_info) через regex
"""

import re
from typing import Dict, List, Tuple, Optional

try:
    from pymorphy3 import MorphAnalyzer
    PYMORPHY_AVAILABLE = True
except ImportError:
    try:
        from pymorphy2 import MorphAnalyzer
        PYMORPHY_AVAILABLE = True
    except ImportError:
        PYMORPHY_AVAILABLE = False
        MorphAnalyzer = None
        print("[WARNING] pymorphy2/pymorphy3 не установлен. Fallback на лемматизацию недоступен.")

from config import (
    INTENT_ROOTS,
    INTENT_PHRASES,
    CLASSIFIER_CONFIG
)


class RootClassifier:
    """Быстрая классификация по корням слов"""

    def __init__(self):
        self.roots = INTENT_ROOTS
        self.config = CLASSIFIER_CONFIG

    def classify(self, message: str) -> Tuple[str, float, Dict[str, int]]:
        """
        Классификация по корням

        Returns:
            (intent, confidence, scores_dict)
        """
        message_lower = message.lower()
        scores: Dict[str, int] = {}

        for intent, roots in self.roots.items():
            score = 0
            for root in roots:
                if root in message_lower:
                    score += 1
            if score > 0:
                scores[intent] = score

        if not scores:
            return "unclear", 0.0, {}

        # Находим лучший интент
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # Нормализуем confidence
        # Чем больше совпадений, тем выше уверенность
        confidence = min(best_score * self.config["root_match_weight"] / 3, 1.0)

        # Бонус если есть явный лидер (разрыв с вторым местом)
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1:
            gap = sorted_scores[0] - sorted_scores[1]
            if gap >= 2:
                confidence = min(confidence + 0.2, 1.0)

        return best_intent, confidence, scores


class LemmaClassifier:
    """Fallback классификация через pymorphy2"""

    def __init__(self):
        self.phrases = INTENT_PHRASES
        self.config = CLASSIFIER_CONFIG
        self.morph = MorphAnalyzer() if PYMORPHY_AVAILABLE else None

    def _lemmatize(self, text: str) -> List[str]:
        """Приводим слова к нормальной форме"""
        if not self.morph:
            return text.lower().split()

        words = re.findall(r'[а-яёa-z0-9]+', text.lower())
        lemmas = []
        for word in words:
            parsed = self.morph.parse(word)
            if parsed:
                lemmas.append(parsed[0].normal_form)
            else:
                lemmas.append(word)
        return lemmas

    def _lemmatize_phrase(self, phrase: str) -> str:
        """Лемматизируем фразу и склеиваем обратно"""
        return " ".join(self._lemmatize(phrase))

    def classify(self, message: str) -> Tuple[str, float, Dict[str, float]]:
        """
        Классификация через лемматизацию

        Returns:
            (intent, confidence, scores_dict)
        """
        if not PYMORPHY_AVAILABLE:
            return "unclear", 0.0, {}

        message_lemmas = self._lemmatize(message)
        message_lemma_str = " ".join(message_lemmas)

        scores: Dict[str, float] = {}

        for intent, phrases in self.phrases.items():
            best_match_score = 0.0

            for phrase in phrases:
                phrase_lemmas = self._lemmatize(phrase)
                phrase_lemma_str = " ".join(phrase_lemmas)

                # Точное совпадение лемматизированной фразы
                if phrase_lemma_str in message_lemma_str:
                    match_score = len(phrase_lemmas) * self.config["lemma_match_weight"]
                    best_match_score = max(best_match_score, match_score)
                    continue

                # Частичное совпадение (все леммы фразы есть в сообщении)
                matching_lemmas = sum(1 for l in phrase_lemmas if l in message_lemmas)
                if matching_lemmas == len(phrase_lemmas):
                    match_score = matching_lemmas * self.config["lemma_match_weight"] * 0.8
                    best_match_score = max(best_match_score, match_score)

            if best_match_score > 0:
                scores[intent] = best_match_score

        if not scores:
            return "unclear", 0.0, {}

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # Нормализуем confidence
        confidence = min(best_score / 4, 1.0)

        return best_intent, confidence, scores


class DataExtractor:
    """Извлекаем структурированные данные из сообщения"""

    def extract(self, message: str) -> Dict:
        """Извлекаем данные из сообщения"""
        extracted = {}
        message_lower = message.lower()

        # === Размер компании ===
        size_patterns = [
            r'(\d+)\s*(?:человек|чел\.?|менеджер|сотрудник|продаж)',
            r'нас\s*(\d+)',
            r'команд[аы]?\s*(?:из|в|на)?\s*(\d+)',
            r'отдел[еа]?\s*(\d+)',
            r'(\d+)\s*(?:в команде|в отделе|человек)',
            r'штат[еа]?\s*(\d+)',
            r'работа[ею]т?\s*(\d+)',
        ]
        for pattern in size_patterns:
            match = re.search(pattern, message_lower)
            if match:
                size = int(match.group(1))
                if 1 <= size <= 10000:  # Разумные границы
                    extracted["company_size"] = size
                    break

        # === Боль клиента ===
        pain_patterns = {
            # Потеря клиентов
            r'теря[ею]м?\s*клиент': "теряют клиентов",
            r'клиент\w*\s*ухо': "клиенты уходят",
            r'упуска[ею]м?\s*': "упускают сделки",

            # Проблемы с менеджерами
            r'забыва[ею]т?\s*(?:перезвон|позвон)': "забывают перезванивать",
            r'менеджер\w*\s*(?:не\s*)?(?:перезван|звон)': "менеджеры не перезванивают",
            r'пропуска[ею]т?\s*': "пропускают задачи",

            # Нет контроля
            r'нет\s*контрол': "нет контроля над продажами",
            r'не\s*(?:могу|можем)\s*контролир': "не могут контролировать",
            r'не\s*вид[и|е][мт]': "нет видимости процессов",

            # Хаос в данных
            r'excel|эксел|табличк': "ведут в Excel",
            r'блокнот|записк': "записи в блокнотах",
            r'всё\s*в\s*голов': "всё в головах",
            r'нигде\s*не\s*(?:фикс|запис)': "ничего не фиксируется",
            r'разброс|раскидан': "данные разбросаны",

            # Дубли и ошибки
            r'дубл[иеяь]': "дубли клиентов",
            r'путаниц': "путаница в данных",
            r'ошиб[ко]': "ошибки в работе",

            # Общая неэффективность
            r'долго\s*(?:иск|наход)': "долго ищут информацию",
            r'не\s*успева[ею]': "не успевают",
            r'много\s*времен': "тратят много времени",
        }

        for pattern, pain in pain_patterns.items():
            if re.search(pattern, message_lower):
                extracted["pain_point"] = pain
                break

        # === Контактная информация ===
        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w{2,}', message)
        if email_match:
            extracted["contact_info"] = email_match.group(0)

        # Телефон (если email не найден)
        if "contact_info" not in extracted:
            phone_patterns = [
                r'\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
                r'8[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
                r'\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            ]
            for pattern in phone_patterns:
                phone_match = re.search(pattern, message)
                if phone_match:
                    extracted["contact_info"] = phone_match.group(0).strip()
                    break

        # === Имя клиента ===
        name_patterns = [
            r'(?:меня\s*зовут|я\s+)\s*([А-ЯЁ][а-яё]+)',
            r'(?:это\s+)?([А-ЯЁ][а-яё]+)\s*(?:на связи|пишу|беспокоит)',
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, message)
            if name_match:
                extracted["client_name"] = name_match.group(1)
                break

        return extracted


class HybridClassifier:
    """
    Гибридный классификатор: быстрый + точный

    1. Пробуем быструю классификацию по корням
    2. Если confidence >= threshold → возвращаем
    3. Иначе → fallback на pymorphy2
    4. Выбираем лучший результат
    """

    def __init__(self):
        self.root_classifier = RootClassifier()
        self.lemma_classifier = LemmaClassifier()
        self.data_extractor = DataExtractor()
        self.config = CLASSIFIER_CONFIG

    def classify(self, message: str) -> Dict:
        """
        Полная классификация сообщения

        Returns:
            {
                "intent": str,
                "confidence": float,
                "extracted_data": dict,
                "method": str  # "root" | "lemma" | "data"
            }
        """
        # 1. Извлекаем данные
        extracted = self.data_extractor.extract(message)

        # Если есть данные — это info_provided (высокий приоритет)
        if extracted.get("company_size") or extracted.get("pain_point"):
            return {
                "intent": "info_provided",
                "confidence": 0.95,
                "extracted_data": extracted,
                "method": "data"
            }

        # Если есть контакт — contact_provided
        if extracted.get("contact_info"):
            return {
                "intent": "contact_provided",
                "confidence": 0.95,
                "extracted_data": extracted,
                "method": "data"
            }

        # 2. Быстрая классификация по корням
        root_intent, root_conf, root_scores = self.root_classifier.classify(message)

        # Если уверенность высокая — возвращаем сразу
        if root_conf >= self.config["high_confidence_threshold"]:
            return {
                "intent": root_intent,
                "confidence": root_conf,
                "extracted_data": extracted,
                "method": "root",
                "debug_scores": root_scores
            }

        # 3. Fallback на лемматизацию
        lemma_intent, lemma_conf, lemma_scores = self.lemma_classifier.classify(message)

        # 4. Выбираем лучший результат
        if lemma_conf > root_conf:
            return {
                "intent": lemma_intent,
                "confidence": lemma_conf,
                "extracted_data": extracted,
                "method": "lemma",
                "debug_scores": lemma_scores
            }

        # Если оба метода дали низкую уверенность
        if root_conf < self.config["min_confidence"]:
            return {
                "intent": "unclear",
                "confidence": root_conf,
                "extracted_data": extracted,
                "method": "root",
                "debug_scores": root_scores
            }

        return {
            "intent": root_intent,
            "confidence": root_conf,
            "extracted_data": extracted,
            "method": "root",
            "debug_scores": root_scores
        }


# =============================================================================
# ТЕСТИРОВАНИЕ
# =============================================================================

if __name__ == "__main__":
    classifier = HybridClassifier()

    print("=" * 60)
    print("ТЕСТ ГИБРИДНОГО КЛАССИФИКАТОРА")
    print("=" * 60)

    test_cases = [
        # Приветствия
        ("Привет!", "greeting"),
        ("Здравствуйте, подскажите пожалуйста", "greeting"),
        ("Добрый день", "greeting"),

        # Вопросы о цене (разные формулировки)
        ("Сколько стоит?", "price_question"),
        ("Какая цена?", "price_question"),
        ("Подскажите по стоимости", "price_question"),
        ("Ценник какой?", "price_question"),
        ("А прайс есть?", "price_question"),
        ("Какие тарифы?", "price_question"),
        ("Во сколько обойдётся?", "price_question"),

        # Возражения
        ("Дорого", "objection_price"),
        ("Слишком дорого для нас", "objection_price"),
        ("Нет бюджета на это", "objection_price"),
        ("Нет времени сейчас", "objection_no_time"),
        ("Занят, перезвоните позже", "objection_no_time"),
        ("У нас уже есть CRM", "objection_competitor"),
        ("Используем Битрикс24", "objection_competitor"),

        # Согласие
        ("Да, интересно", "agreement"),
        ("Давайте попробуем", "agreement"),
        ("Расскажите подробнее", "agreement"),
        ("Хочу демо", "agreement"),

        # Отказ
        ("Не интересно", "rejection"),
        ("Нет, спасибо", "rejection"),
        ("Не нужно", "rejection"),

        # Данные
        ("У нас 15 человек в отделе", "info_provided"),
        ("Постоянно теряем клиентов", "info_provided"),
        ("Работаем в Excel, всё теряется", "info_provided"),
        ("Мой email: test@company.ru", "contact_provided"),
        ("+7 999 123-45-67", "contact_provided"),
    ]

    passed = 0
    failed = 0

    for message, expected in test_cases:
        result = classifier.classify(message)
        actual = result["intent"]
        conf = result["confidence"]
        method = result["method"]

        status = "✓" if actual == expected else "✗"
        if actual == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{message}'")
        print(f"   Ожидали: {expected}, Получили: {actual} ({conf:.2f}) [{method}]")
        if result.get("extracted_data"):
            print(f"   Данные: {result['extracted_data']}")
        print()

    print("=" * 60)
    print(f"РЕЗУЛЬТАТ: {passed}/{passed+failed} тестов пройдено")
    print("=" * 60)
