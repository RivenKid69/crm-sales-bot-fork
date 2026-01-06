"""
Гибридный классификатор интентов

Оркестрирует:
- TextNormalizer: нормализация текста
- RootClassifier: быстрая классификация по корням
- LemmaClassifier: fallback через pymorphy
- DataExtractor: извлечение структурированных данных
- DisambiguationAnalyzer: уточнение намерения при близких scores
"""

import re
from typing import Dict, Optional

from config import CLASSIFIER_CONFIG
from feature_flags import flags
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
        self._disambiguation_analyzer = None

    @property
    def disambiguation_analyzer(self):
        """Lazy initialization of DisambiguationAnalyzer."""
        if self._disambiguation_analyzer is None:
            from .disambiguation import DisambiguationAnalyzer
            self._disambiguation_analyzer = DisambiguationAnalyzer(self.config)
        return self._disambiguation_analyzer

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
        context = context or {}

        # Определяем короткое ли сообщение (1-3 слова)
        words = message_lower.split()
        is_short_message = len(words) <= 3

        # =================================================================
        # ПРИОРИТЕТ 0: КОНТЕКСТНАЯ КЛАССИФИКАЦИЯ КОРОТКИХ ОТВЕТОВ
        # =================================================================
        # Короткие ответы ("да", "нет", "ок") требуют контекста для правильной
        # интерпретации. Если есть контекст (last_action, spin_phase, state),
        # используем его ПЕРЕД обычными паттернами.
        # НО: пропускаем если в режиме disambiguation (ответ обрабатывается отдельно)
        if is_short_message:
            has_context = (
                context.get("last_action") or
                context.get("spin_phase") or
                context.get("state")
            )
            if has_context and not context.get("in_disambiguation"):
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

        # =================================================================
        # КРИТИЧЕСКИЕ ПРИОРИТЕТНЫЕ ПАТТЕРНЫ
        # =================================================================
        for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
            if pattern.search(message_lower):
                # Извлекаем данные для найденного интента
                extracted = self.data_extractor.extract(message, context)
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "extracted_data": extracted,
                    "method": "priority_pattern"
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

        # =================================================================
        # ПРИОРИТЕТ 8: DISAMBIGUATION
        # =================================================================
        # Если feature flag включён и мы НЕ в режиме disambiguation,
        # проверяем нужно ли уточнить намерение пользователя
        if flags.intent_disambiguation:
            if not context.get("in_disambiguation"):
                disambiguation_result = self.disambiguation_analyzer.analyze(
                    root_scores=root_scores,
                    lemma_scores=lemma_scores,
                    context=context
                )

                if disambiguation_result.needs_disambiguation:
                    return {
                        "intent": "disambiguation_needed",
                        "confidence": disambiguation_result.top_confidence,
                        "extracted_data": extracted,
                        "method": "disambiguation",
                        "disambiguation_options": disambiguation_result.options,
                        "disambiguation_question": disambiguation_result.question,
                        "original_scores": disambiguation_result.merged_scores,
                        "original_intent": (
                            root_intent if root_conf > lemma_conf else lemma_intent
                        ),
                    }

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
        в зависимости от контекста: что сделал бот (last_action),
        на какой интент отвечал (last_intent), в какой фазе диалог.

        Args:
            message: Нормализованное сообщение (lowercase)
            context: Контекст диалога

        Returns:
            {"intent": str, "confidence": float} или None если не определено
        """
        # Не обрабатываем короткие ответы в режиме disambiguation
        if context.get("in_disambiguation"):
            return None

        last_action = context.get("last_action")
        last_intent = context.get("last_intent")
        spin_phase = context.get("spin_phase")
        state = context.get("state")
        missing_data = context.get("missing_data") or []

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

        # -----------------------------------------------------------------
        # ПРИОРИТЕТ 1: По last_action (что бот сделал в прошлый раз)
        # -----------------------------------------------------------------

        # Бот в фазе закрытия (предлагает демо/контакт)
        if last_action in ["close", "transition_to_close"]:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.9}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.85}

        # Бот презентовал продукт
        if last_action in ["presentation", "transition_to_presentation"]:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.8}

        # Бот отработал возражение
        if last_action == "handle_objection":
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.8}

        # Бот ответил на вопрос — смотрим какой был вопрос (last_intent)
        if last_action == "answer_question" and last_intent:
            # Ответили на вопрос о цене
            if last_intent in ["price_question", "pricing_details"]:
                if is_positive:
                    return {"intent": "agreement", "confidence": 0.85}
                if is_negative:
                    return {"intent": "objection_price", "confidence": 0.8}
            # Ответили на вопрос о функциях/интеграциях
            if last_intent in ["question_features", "question_integrations"]:
                if is_positive:
                    return {"intent": "agreement", "confidence": 0.8}
                if is_negative:
                    return {"intent": "unclear", "confidence": 0.6}

        # Бот отложил вопрос о цене (deflect)
        if last_action == "deflect_and_continue":
            if is_positive:
                return {"intent": "agreement", "confidence": 0.8}
            if is_negative:
                return {"intent": "objection_price", "confidence": 0.75}

        # -----------------------------------------------------------------
        # ПРИОРИТЕТ 2: По state (текущее состояние диалога)
        # -----------------------------------------------------------------

        # В фазе закрытия
        if state == "close" or "contact_info" in missing_data:
            if is_positive:
                return {"intent": "agreement", "confidence": 0.85}
            if is_negative:
                return {"intent": "rejection", "confidence": 0.85}

        # В фазе soft_close (мягкое закрытие после rejection)
        if state == "soft_close":
            if is_positive:
                return {"intent": "agreement", "confidence": 0.8}

        # -----------------------------------------------------------------
        # ПРИОРИТЕТ 3: По spin_phase (SPIN-фаза диалога)
        # -----------------------------------------------------------------

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

        # -----------------------------------------------------------------
        # ПРИОРИТЕТ 4: По last_action для SPIN-фаз
        # -----------------------------------------------------------------

        # Бот спрашивал о проблемах
        if last_action in ["spin_problem", "transition_to_spin_problem"]:
            if is_positive:
                return {"intent": "problem_revealed", "confidence": 0.75}
            if is_negative:
                return {"intent": "no_problem", "confidence": 0.7}

        # Бот спрашивал о последствиях
        if last_action in ["spin_implication", "transition_to_spin_implication"]:
            if is_positive:
                return {"intent": "implication_acknowledged", "confidence": 0.8}

        # Бот спрашивал о ценности
        if last_action in ["spin_need_payoff", "transition_to_spin_need_payoff"]:
            if is_positive:
                return {"intent": "need_expressed", "confidence": 0.85}
            if is_negative:
                return {"intent": "no_need", "confidence": 0.7}

        # -----------------------------------------------------------------
        # ПРИОРИТЕТ 5: Общие случаи
        # -----------------------------------------------------------------

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
