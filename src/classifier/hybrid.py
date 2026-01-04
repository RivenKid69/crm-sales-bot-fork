"""
Гибридный классификатор интентов

Оркестрирует:
- TextNormalizer: нормализация текста
- RootClassifier: быстрая классификация по корням
- LemmaClassifier: fallback через pymorphy
- DataExtractor: извлечение структурированных данных
"""

import re
from typing import Dict, Optional

from config import CLASSIFIER_CONFIG
from .normalizer import TextNormalizer
from .intents import RootClassifier, LemmaClassifier, COMPILED_PRIORITY_PATTERNS
from .extractors import DataExtractor


class HybridClassifier:
    """
    Гибридный классификатор: быстрый + точный

    1. Нормализация текста (TextNormalizer)
    2. Пробуем быструю классификацию по корням
    3. Если confidence >= threshold → возвращаем
    4. Иначе → fallback на pymorphy2
    5. Выбираем лучший результат
    """

    def __init__(self):
        self.normalizer = TextNormalizer()
        self.root_classifier = RootClassifier()
        self.lemma_classifier = LemmaClassifier()
        self.data_extractor = DataExtractor()
        self.config = CLASSIFIER_CONFIG

    def classify(self, message: str, context: Dict = None) -> Dict:
        """
        Полная классификация сообщения

        Args:
            message: Сообщение пользователя
            context: Контекст диалога (missing_data, collected_data, spin_phase, last_bot_intent)

        Returns:
            {
                "intent": str,
                "confidence": float,
                "extracted_data": dict,
                "method": str  # "root" | "lemma" | "data" | "spin" | "context"
            }
        """
        # 0. Нормализация текста (опечатки, слипшиеся слова, ё→е и т.д.)
        message = self.normalizer.normalize(message)
        message_lower = message.lower().strip()

        # =================================================================
        # КРИТИЧЕСКИЕ ПРИОРИТЕТНЫЕ ПАТТЕРНЫ (проверяются первыми!)
        # =================================================================
        for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
            if pattern.search(message_lower):
                # Извлекаем данные для найденного интента
                extracted = self.data_extractor.extract(message, context) if context else {}
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "extracted_data": extracted,
                    "method": "priority_pattern"
                }

        # =================================================================
        # КОНТЕКСТНАЯ КЛАССИФИКАЦИЯ КОРОТКИХ ОТВЕТОВ
        # =================================================================
        # Короткие ответы (1-3 слова) требуют контекста для правильной интерпретации
        words = message_lower.split()
        is_short_message = len(words) <= 3

        if is_short_message and context:
            context_result = self._classify_short_answer(message_lower, context)
            if context_result:
                # Извлекаем данные с учётом контекстного интента
                extracted = self.data_extractor.extract(message, context)
                return {
                    "intent": context_result["intent"],
                    "confidence": context_result["confidence"],
                    "extracted_data": extracted,
                    "method": "context"
                }

        # 1. Извлекаем данные (с учётом контекста и SPIN-фазы)
        extracted = self.data_extractor.extract(message, context)

        # Получаем текущую SPIN-фазу
        spin_phase = context.get("spin_phase") if context else None

        # =================================================================
        # SPIN-специфичная классификация на основе извлечённых данных
        # =================================================================

        # Если в фазе situation и получили данные о ситуации
        if spin_phase == "situation":
            if extracted.get("company_size") or extracted.get("current_tools") or extracted.get("business_type"):
                return {
                    "intent": "situation_provided",
                    "confidence": 0.9,
                    "extracted_data": extracted,
                    "method": "spin"
                }

        # Если в фазе problem и получили информацию о боли
        if spin_phase == "problem":
            if extracted.get("pain_point"):
                return {
                    "intent": "problem_revealed",
                    "confidence": 0.9,
                    "extracted_data": extracted,
                    "method": "spin"
                }

        # Если в фазе implication и клиент осознаёт последствия
        if spin_phase == "implication":
            if extracted.get("pain_impact") or extracted.get("financial_impact"):
                return {
                    "intent": "implication_acknowledged",
                    "confidence": 0.9,
                    "extracted_data": extracted,
                    "method": "spin"
                }

        # Если в фазе need_payoff и клиент выразил желаемый результат
        if spin_phase == "need_payoff":
            if extracted.get("desired_outcome") or extracted.get("value_acknowledged"):
                return {
                    "intent": "need_expressed",
                    "confidence": 0.9,
                    "extracted_data": extracted,
                    "method": "spin"
                }

        # =================================================================
        # Стандартная классификация (если не SPIN-специфичная)
        # =================================================================

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

    def _classify_short_answer(self, message: str, context: Dict) -> Optional[Dict]:
        """
        Контекстная классификация коротких ответов.

        Короткие ответы типа "да", "нет", "ок", "понял" интерпретируются
        в зависимости от контекста: что спросил бот, в какой фазе диалог.

        Args:
            message: Нормализованное сообщение (lowercase)
            context: Контекст диалога

        Returns:
            {"intent": str, "confidence": float} или None если не определено
        """
        last_bot_intent = context.get("last_bot_intent")
        spin_phase = context.get("spin_phase")
        current_state = context.get("current_state")
        missing_data = context.get("missing_data", [])

        # =================================================================
        # УТВЕРДИТЕЛЬНЫЕ КОРОТКИЕ ОТВЕТЫ
        # =================================================================
        positive_markers = [
            r'^да[,!.\s]*$', r'^ага[,!.\s]*$', r'^угу[,!.\s]*$',
            r'^конечно[,!.\s]*$', r'^естественно[,!.\s]*$',
            r'^разумеется[,!.\s]*$', r'^точно[,!.\s]*$',
            r'^верно[,!.\s]*$', r'^согласен[,!.\s]*$',
            r'^ок[,!.\s]*$', r'^окей[,!.\s]*$', r'^хорошо[,!.\s]*$',
            r'^ладно[,!.\s]*$', r'^давайте[,!.\s]*$', r'^давай[,!.\s]*$',
            r'^можно[,!.\s]*$', r'^готов[,!.\s]*$', r'^готовы[,!.\s]*$',
            r'^понял[,!.\s]*$', r'^понятно[,!.\s]*$', r'^ясно[,!.\s]*$',
            r'^так\s*точно[,!.\s]*$', r'^именно[,!.\s]*$',
            r'^да\s*да[,!.\s]*$', r'^ну\s*да[,!.\s]*$',
            r'^в\s*принципе\s*да[,!.\s]*$', r'^скорее\s*да[,!.\s]*$',
        ]

        is_positive = any(re.match(p, message) for p in positive_markers)

        # =================================================================
        # ОТРИЦАТЕЛЬНЫЕ КОРОТКИЕ ОТВЕТЫ
        # =================================================================
        negative_markers = [
            r'^нет[,!.\s]*$', r'^неа[,!.\s]*$', r'^не[,!.\s]*$',
            r'^ноуп[,!.\s]*$', r'^ни\s*в\s*коем[,!.\s]*$',
            r'^ни\s*за\s*что[,!.\s]*$', r'^точно\s*нет[,!.\s]*$',
            r'^не\s*надо[,!.\s]*$', r'^не\s*нужно[,!.\s]*$',
            r'^отстаньте[,!.\s]*$', r'^хватит[,!.\s]*$',
            r'^стоп[,!.\s]*$', r'^нет\s*нет[,!.\s]*$',
            r'^вряд\s*ли[,!.\s]*$', r'^сомневаюсь[,!.\s]*$',
            r'^не\s*думаю[,!.\s]*$', r'^скорее\s*нет[,!.\s]*$',
        ]

        is_negative = any(re.match(p, message) for p in negative_markers)

        # =================================================================
        # НЕЙТРАЛЬНЫЕ / УТОЧНЯЮЩИЕ
        # =================================================================
        neutral_markers = [
            r'^может\s*быть[,!.\s]*$', r'^возможно[,!.\s]*$',
            r'^не\s*знаю[,!.\s]*$', r'^хз[,!.\s]*$',
            r'^посмотрим[,!.\s]*$', r'^подумаю[,!.\s]*$',
            r'^надо\s*подумать[,!.\s]*$',
        ]

        is_neutral = any(re.match(p, message) for p in neutral_markers)

        # =================================================================
        # ИНТЕРПРЕТАЦИЯ В ЗАВИСИМОСТИ ОТ КОНТЕКСТА
        # =================================================================

        # Если бот предложил демо и клиент согласился
        if last_bot_intent in ["offer_demo", "ask_demo", "demo_question"]:
            if is_positive:
                return {"intent": "demo_request", "confidence": 0.9}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.85}

        # Если бот предложил созвониться
        if last_bot_intent in ["offer_call", "ask_callback", "callback_question"]:
            if is_positive:
                return {"intent": "callback_request", "confidence": 0.9}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.8}

        # Если бот задавал вопрос о цене и ждёт реакции
        if last_bot_intent in ["price_answer", "pricing_provided"]:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "objection_price", "confidence": 0.8}

        # В SPIN-фазах
        if spin_phase == "situation":
            if is_positive:
                return {"intent": "situation_provided", "confidence": 0.7}

        if spin_phase == "problem":
            if is_positive:
                return {"intent": "problem_revealed", "confidence": 0.75}
            if is_negative:
                # Клиент отрицает наличие проблемы — это тоже информация
                return {"intent": "no_problem", "confidence": 0.7}

        if spin_phase == "implication":
            if is_positive:
                return {"intent": "implication_acknowledged", "confidence": 0.8}

        if spin_phase == "need_payoff":
            if is_positive:
                return {"intent": "need_expressed", "confidence": 0.85}
            if is_negative:
                return {"intent": "no_need", "confidence": 0.7}

        # Если в фазе закрытия и спрашивали контакт
        if current_state == "close" or "contact_info" in missing_data:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.85}

        # Если бот спрашивал о проблемах/болях
        if last_bot_intent in ["ask_problem", "ask_pain", "problem_question"]:
            if is_positive:
                return {"intent": "problem_revealed", "confidence": 0.75}
            if is_negative:
                return {"intent": "no_problem", "confidence": 0.7}

        # Если бот презентовал продукт
        if last_bot_intent in ["presentation", "feature_presentation", "value_proposition"]:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.8}

        # "Надо подумать" и похожие — objection_think
        if is_neutral:
            return {"intent": "objection_think", "confidence": 0.75}

        # Если ничего не подходит — общая интерпретация
        if is_positive:
            return {"intent": "agreement", "confidence": 0.7}
        if is_negative:
            return {"intent": "rejection", "confidence": 0.7}

        # Не удалось определить
        return None
