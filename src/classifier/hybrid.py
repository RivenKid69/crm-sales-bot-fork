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
        # ПРИОРИТЕТ 0: DEMO_REQUEST OVERRIDE (САМЫЙ ВЫСОКИЙ)
        # =================================================================
        # Демо-запросы должны распознаваться РАНЬШЕ ВСЕХ паттернов,
        # иначе "давай попробуем", "можно показать?" классифицируются как agreement
        # =================================================================
        extracted = self.data_extractor.extract(message, context)
        demo_override_result = self._check_demo_request_override(message_lower, extracted)
        if demo_override_result:
            return demo_override_result

        # =================================================================
        # КРИТИЧЕСКИЕ ПРИОРИТЕТНЫЕ ПАТТЕРНЫ
        # =================================================================
        for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
            if pattern.search(message_lower):
                return {
                    "intent": intent,
                    "confidence": confidence,
                    "extracted_data": extracted,
                    "method": "priority_pattern"
                }

        # =================================================================
        # ПРИОРИТЕТ 0.5: ДЕТЕКЦИЯ ПАТТЕРНОВ ИЗ ИСТОРИИ (Context Window)
        # =================================================================
        # Используем историю интентов для детекции повторных вопросов,
        # застревания и осцилляций
        pattern_result = self._check_history_patterns(message_lower, context)
        if pattern_result:
            extracted = self.data_extractor.extract(message, context)
            return {
                "intent": pattern_result["intent"],
                "confidence": pattern_result["confidence"],
                "extracted_data": extracted,
                "method": "history_pattern",
                "pattern_type": pattern_result.get("pattern_type"),
            }

        # Получаем текущую SPIN-фазу
        spin_phase = context.get("spin_phase") if context else None

        # =================================================================
        # SPIN-специфичная классификация на основе извлечённых данных
        # (extracted уже получен выше в ПРИОРИТЕТ 0)
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

    def _check_history_patterns(self, message: str, context: Dict) -> Optional[Dict]:
        """
        Проверить паттерны из истории диалога (Context Window).

        Детектирует:
        1. Повторные вопросы (клиент спрашивает одно и то же)
        2. Застревание (3+ unclear подряд)
        3. Осцилляцию (колебание между позитивным и негативным)

        Args:
            message: Сообщение пользователя (lowercase)
            context: Контекст с историей интентов

        Returns:
            {"intent": str, "confidence": float, "pattern_type": str} или None
        """
        # =================================================================
        # УРОВЕНЬ 3: Паттерны из Episodic Memory (не требуют intent_history)
        # Проверяем ПЕРВЫМИ, т.к. они основаны на долгосрочной памяти
        # =================================================================

        # -----------------------------------------------------------------
        # ПАТТЕРН 11: Повторное возражение того же типа — высокая уверенность
        # -----------------------------------------------------------------
        repeated_objection_types = context.get("repeated_objection_types", [])

        if repeated_objection_types:
            # Клиент уже возражал по этой теме раньше
            price_markers = ["дорого", "цена", "стоит", "бюджет", "денег"]
            time_markers = ["времени", "некогда", "занят", "потом", "позже"]
            think_markers = ["подумать", "подумаю", "обдумать"]

            if "objection_price" in repeated_objection_types:
                if any(m in message for m in price_markers):
                    return {
                        "intent": "objection_price",
                        "confidence": 0.95,
                        "pattern_type": "repeated_objection_episodic",
                        "is_repeated": True,
                    }

            if "objection_no_time" in repeated_objection_types:
                if any(m in message for m in time_markers):
                    return {
                        "intent": "objection_no_time",
                        "confidence": 0.95,
                        "pattern_type": "repeated_objection_episodic",
                        "is_repeated": True,
                    }

            if "objection_think" in repeated_objection_types:
                if any(m in message for m in think_markers):
                    return {
                        "intent": "objection_think",
                        "confidence": 0.95,
                        "pattern_type": "repeated_objection_episodic",
                        "is_repeated": True,
                    }

        # -----------------------------------------------------------------
        # ПАТТЕРН 13: После breakthrough — склонность к согласию
        # -----------------------------------------------------------------
        has_breakthrough = context.get("has_breakthrough", False)

        if has_breakthrough and len(message) < 20:
            soft_positive = ["ну", "ладно", "ок", "понял", "хорошо", "да"]
            if any(m in message.lower() for m in soft_positive):
                return {
                    "intent": "agreement",
                    "confidence": 0.85,
                    "pattern_type": "post_breakthrough_agreement",
                }

        # -----------------------------------------------------------------
        # ПАТТЕРН 14: Много turning points — нестабильный клиент
        # -----------------------------------------------------------------
        turning_points_count = context.get("turning_points_count", 0)

        if turning_points_count >= 3 and len(message) < 15:
            agreement_words = ["да", "ок", "хорошо", "ладно"]
            if any(w == message.lower().strip().rstrip(".,!") for w in agreement_words):
                return {
                    "intent": "agreement",
                    "confidence": 0.6,
                    "pattern_type": "unstable_client_agreement",
                }

        # -----------------------------------------------------------------
        # ПАТТЕРН 15: Клиент с данными без возражений — лояльный
        # -----------------------------------------------------------------
        client_has_data = context.get("client_has_data", False)
        total_objections = context.get("total_objections", 0)

        if client_has_data and total_objections == 0 and len(message) < 40:
            interest_markers = ["интересно", "расскажите", "покажите"]
            if any(m in message.lower() for m in interest_markers):
                return {
                    "intent": "agreement",
                    "confidence": 0.9,
                    "pattern_type": "engaged_client_interest",
                }

        # =================================================================
        # УРОВЕНЬ 1-2: Паттерны из скользящего окна (требуют intent_history)
        # =================================================================

        intent_history = context.get("intent_history", [])

        # Нужна хотя бы минимальная история для Level 1-2 паттернов
        if len(intent_history) < 2:
            return None

        # -----------------------------------------------------------------
        # ПАТТЕРН 1: Повторный вопрос
        # -----------------------------------------------------------------
        # Если клиент уже задавал этот тип вопроса — это повторный запрос
        repeated_question = context.get("repeated_question")
        if repeated_question:
            # Проверяем что текущее сообщение похоже на вопрос
            question_markers = ["сколько", "как", "что", "какой", "какая", "почему", "зачем", "?"]
            is_question = any(marker in message for marker in question_markers)

            if is_question:
                # Повторный вопрос — нужно ответить, а не откладывать
                return {
                    "intent": repeated_question,
                    "confidence": 0.85,
                    "pattern_type": "repeated_question",
                }

        # -----------------------------------------------------------------
        # ПАТТЕРН 2: Застревание на unclear
        # -----------------------------------------------------------------
        # Если 3+ unclear подряд — классификатор не понимает клиента
        is_stuck = context.get("is_stuck", False)
        unclear_count = context.get("unclear_count", 0)

        if is_stuck and unclear_count >= 3:
            # Нужно предложить варианты или уточнить
            return {
                "intent": "needs_clarification",
                "confidence": 0.9,
                "pattern_type": "stuck_unclear",
            }

        # -----------------------------------------------------------------
        # ПАТТЕРН 3: Осцилляция (колебание)
        # -----------------------------------------------------------------
        # objection → agreement → objection — клиент не уверен, а не соглашается
        has_oscillation = context.get("has_oscillation", False)

        if has_oscillation:
            # Проверяем последние интенты
            last_intents = intent_history[-3:] if len(intent_history) >= 3 else intent_history

            # Если последний был "agreement" но до этого были возражения
            objection_intents = {
                "objection_price", "objection_competitor", "objection_no_time",
                "objection_think", "objection_timing", "objection_complexity"
            }

            recent_objections = sum(1 for i in last_intents if i in objection_intents)

            if recent_objections >= 1 and last_intents[-1] == "agreement":
                # Это не настоящее согласие — клиент колеблется
                # Снижаем уверенность но не меняем интент
                # (это будет учтено в state machine)
                pass  # Пока не меняем, чтобы не сломать flow

        # -----------------------------------------------------------------
        # ПАТТЕРН 4: Много возражений подряд
        # -----------------------------------------------------------------
        objection_count = context.get("objection_count", 0)

        if objection_count >= 3:
            # Проверяем, не пытается ли клиент снова возразить
            objection_markers = [
                "дорого", "дороговато", "бюджет",
                "подумать", "подумаю", "позже",
                "не нужно", "не надо", "не интересно",
                "уже есть", "используем", "конкурент"
            ]

            if any(marker in message for marker in objection_markers):
                # Много возражений — возможно надо soft close
                # Но конкретный тип определит основной классификатор
                return None  # Даём основному классификатору определить тип

        # -----------------------------------------------------------------
        # ПАТТЕРН 5: Повторный запрос цены после deflect
        # -----------------------------------------------------------------
        action_history = context.get("action_history", [])

        if "deflect_and_continue" in action_history:
            price_markers = ["цен", "стои", "сколько", "прайс", "тариф"]
            if any(marker in message for marker in price_markers):
                # Клиент снова спрашивает про цену после deflect
                # Это повторный запрос — надо ответить
                return {
                    "intent": "price_question",
                    "confidence": 0.9,
                    "pattern_type": "repeated_price_after_deflect",
                }

        # =================================================================
        # УРОВЕНЬ 2: Паттерны из структурированного контекста
        # =================================================================

        # -----------------------------------------------------------------
        # ПАТТЕРН 6: Негативный momentum + короткое сообщение = отказ
        # -----------------------------------------------------------------
        momentum_direction = context.get("momentum_direction")
        engagement_level = context.get("engagement_level")

        if momentum_direction == "negative" and engagement_level == "disengaged":
            # Клиент теряет интерес и momentum негативный
            # Короткие негативные маркеры скорее всего отказ
            rejection_markers = ["нет", "не", "пока", "потом", "позже"]
            if any(marker in message for marker in rejection_markers) and len(message) < 20:
                return {
                    "intent": "rejection",
                    "confidence": 0.8,
                    "pattern_type": "negative_momentum_disengaged",
                }

        # -----------------------------------------------------------------
        # ПАТТЕРН 7: Declining engagement + вопрос = последний шанс
        # -----------------------------------------------------------------
        engagement_trend = context.get("engagement_trend")

        if engagement_trend == "declining" and engagement_level in ("low", "disengaged"):
            # Engagement падает, но клиент задаёт вопрос
            # Это последний шанс — нужно качественно ответить
            question_markers = ["?", "как", "что", "какой", "почему"]
            if any(marker in message for marker in question_markers):
                # Помечаем как high_priority вопрос
                # Но не меняем intent — пусть определит основной классификатор
                pass

        # -----------------------------------------------------------------
        # ПАТТЕРН 8: После неэффективного action — ожидать возражение
        # -----------------------------------------------------------------
        last_objection_trigger = context.get("last_objection_trigger")

        if last_objection_trigger:
            # Знаем какой action триггернул возражение раньше
            trigger_action = last_objection_trigger.get("action")
            last_action = context.get("last_action")

            # Если повторяем тот же action — вероятно снова будет возражение
            if trigger_action == last_action:
                # Повышаем чувствительность к возражениям
                objection_markers = [
                    "дорого", "нет", "не надо", "подумаю", "потом",
                    "уже есть", "не интересно", "сложно"
                ]
                if any(marker in message for marker in objection_markers):
                    # Похоже на возражение — определим тип
                    if "дорого" in message or "бюджет" in message:
                        return {
                            "intent": "objection_price",
                            "confidence": 0.85,
                            "pattern_type": "repeated_trigger_objection",
                        }
                    elif "подумаю" in message or "подумать" in message:
                        return {
                            "intent": "objection_think",
                            "confidence": 0.85,
                            "pattern_type": "repeated_trigger_objection",
                        }

        # -----------------------------------------------------------------
        # ПАТТЕРН 9: Positive momentum + согласие = подтверждение
        # -----------------------------------------------------------------
        if momentum_direction == "positive":
            is_progressing = context.get("is_progressing", False)

            if is_progressing:
                # Клиент движется вперёд, momentum положительный
                # Короткие позитивные ответы — это подтверждение
                agreement_markers = ["да", "ок", "хорошо", "ладно", "давайте", "конечно"]
                if any(marker in message.lower() for marker in agreement_markers) and len(message) < 30:
                    return {
                        "intent": "agreement",
                        "confidence": 0.9,
                        "pattern_type": "positive_momentum_agreement",
                    }

        # -----------------------------------------------------------------
        # ПАТТЕРН 10: Regressing + длинное сообщение = детальное возражение
        # -----------------------------------------------------------------
        is_regressing = context.get("is_regressing", False)

        if is_regressing and len(message) > 50:
            # Клиент откатывается и пишет много
            # Это детальное возражение — нужно внимательно прочитать
            # Пропускаем к основному классификатору для точного определения типа
            pass

        return None

    def _check_demo_request_override(self, message: str, extracted: Dict) -> Optional[Dict]:
        """
        Критический fix: Проверка на демо-запрос ПЕРЕД SPIN-классификацией.

        Проблема: Когда клиент говорит "12 человек, хочу демо", SPIN-логика
        перехватывает это как situation_provided (из-за company_size=12),
        игнорируя явный запрос на демо.

        Решение: Если в сообщении есть явные демо-маркеры, возвращаем
        demo_request независимо от извлечённых данных.

        Args:
            message: Сообщение пользователя (lowercase)
            extracted: Извлечённые данные

        Returns:
            {"intent": "demo_request", ...} или None
        """
        # =================================================================
        # ЯВНЫЕ ДЕМО-МАРКЕРЫ (высокий приоритет)
        # =================================================================
        # Эти фразы однозначно указывают на запрос демо
        explicit_demo_patterns = [
            # Прямые запросы демо (включая разговорные формы)
            r'\bдемо\b',
            r'\bдемк[уаеи]\b',           # "демку", "демка"
            r'\bдем[уаеи]\b',             # "дему" (разговорное)
            r'\bдемонстрац',
            r'\bпрезентац',
            r'\bтриал\b',
            r'\btrial\b',
            # Хочу посмотреть/попробовать/потестировать
            r'хочу\s+(?:посмотреть|попробовать|потестировать|потестить|глянуть)',
            r'хотел\w*\s*(?:бы)?\s*(?:посмотреть|попробовать|потестировать|потестить)',
            r'(?:можно|хотелось\s*бы)\s+(?:посмотреть|попробовать|потестировать|показать)',
            r'(?:покажите|покажи)\s+(?:как|систему|продукт|в\s+действии)',
            # Запись на демо
            r'(?:запиши|запишите)\s+(?:на\s+)?демо',
            r'(?:хочу|хотим)\s+(?:на\s+)?демо',
            # Пробный период
            r'(?:пробн|тестов)\w*\s+(?:период|доступ|версия)',
            r'бесплатн\w*\s+(?:период|доступ|версия)',
            # Посмотреть как работает
            r'(?:как|что)\s+(?:это\s+)?работает',
            r'посмотреть\s+(?:на\s+)?систем',
            r'увидеть\s+(?:как|что|интерфейс)',
            # Давай посмотрим/попробуем
            r'давай\s+(?:посмотрим|глянем|попробуем)',
            r'давайте\s+(?:посмотрим|глянем|попробуем)',
            # Можно показать/попробовать
            r'можно\s+(?:показать|посмотреть|попробовать)',
            # Хотелось бы потестировать
            r'хотелось\s*бы\s+(?:потестировать|попробовать|посмотреть)',
        ]

        # Проверяем явные паттерны
        for pattern in explicit_demo_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return {
                    "intent": "demo_request",
                    "confidence": 0.95,
                    "extracted_data": extracted,
                    "method": "demo_override",
                    "matched_pattern": pattern,
                }

        # =================================================================
        # КОНТЕКСТНЫЕ ДЕМО-МАРКЕРЫ (средний приоритет)
        # =================================================================
        # Менее явные, но в сочетании с положительным контекстом = демо
        soft_demo_markers = [
            "показать", "показыва", "посмотр", "глянуть", "глянем",
            "попробовать", "попробуем", "потестить", "тестирова",
            "в действии", "на практике", "на примере", "живой пример",
        ]

        # Положительные маркеры, усиливающие демо-запрос
        positive_context = [
            "хочу", "хотим", "хотел", "интересно", "давайте", "давай",
            "можно", "было бы", "хотелось", "готов", "готовы",
        ]

        has_soft_demo = any(marker in message for marker in soft_demo_markers)
        has_positive = any(marker in message for marker in positive_context)

        if has_soft_demo and has_positive:
            return {
                "intent": "demo_request",
                "confidence": 0.85,
                "extracted_data": extracted,
                "method": "demo_override_soft",
            }

        return None
