"""
Response Directives — директивы для генерации "человечных" ответов.

Phase 2: Естественность диалога (docs/PLAN_CONTEXT_POLICY.md)

ResponseDirectives управляют СТИЛЕМ ответа, не меняя ЛОГИКУ (state machine).
Они помогают сделать бота "не роботом":
- Grounding: ссылка на ранее сказанное
- Validation: признание эмоции/ситуации
- One-question rule: максимум 1 вопрос
- Repair mode: стратегии восстановления понимания
- Memory: краткая карточка клиента

Использование:
    from response_directives import ResponseDirectivesBuilder

    builder = ResponseDirectivesBuilder(envelope)
    directives = builder.build()
    summary = builder.build_context_summary()

    # В генераторе
    context["directives"] = directives
    context["context_summary"] = summary
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any
from enum import Enum

from src.context_envelope import ContextEnvelope, ReasonCode


class ResponseTone(Enum):
    """Тон ответа."""
    EMPATHETIC = "empathetic"    # Эмпатичный (при фрустрации, возражениях)
    NEUTRAL = "neutral"          # Нейтральный (стандартный)
    CONFIDENT = "confident"      # Уверенный (при прогрессе)
    SUPPORTIVE = "supportive"    # Поддерживающий (при stuck)


class DialogueMove(Enum):
    """Диалоговое действие для структуры ответа."""
    VALIDATE = "validate"           # Признать эмоцию/ситуацию
    SUMMARIZE_CLIENT = "summarize"  # Суммировать что знаем о клиенте
    ASK_CLARIFYING = "clarify"      # Задать уточняющий вопрос
    OFFER_CHOICES = "choices"       # Предложить варианты ответа
    CTA_SOFT = "cta_soft"           # Мягкий call-to-action
    REPAIR = "repair"               # Восстановить понимание


@dataclass
class ResponseDirectives:
    """
    Директивы для генерации ответа.

    Не меняют state machine, но управляют стилем и структурой ответа.

    Attributes:
        # === Стиль ===
        tone: Тон ответа (empathetic, neutral, confident, supportive)
        max_words: Максимальная длина ответа в словах
        one_question: Ограничить до 1 вопроса
        use_bullets: Использовать списки
        be_brief: Быть кратким (при низком engagement)

        # === Диалоговые действия ===
        validate: Признать эмоцию/ситуацию клиента
        summarize_client: Сослаться на ранее сказанное
        ask_clarifying: Задать уточняющий вопрос (repair)
        offer_choices: Предложить варианты ответа (при stuck)
        cta_soft: Добавить мягкий CTA (при breakthrough)
        repair_mode: Режим восстановления понимания

        # === Память ===
        client_card: Краткое резюме фактов о клиенте
        objection_summary: Что уже обсуждали (возражения)
        do_not_repeat: Что не спрашивать снова
        reference_pain: Ссылка на боль клиента

        # === Meta ===
        reason_codes: Reason codes которые привели к директивам
        instruction: Текстовая инструкция для LLM
    """

    # === Стиль ===
    tone: ResponseTone = ResponseTone.NEUTRAL
    max_words: int = 60
    one_question: bool = True
    use_bullets: bool = False
    be_brief: bool = False

    # === Диалоговые действия ===
    validate: bool = False
    summarize_client: bool = False
    ask_clarifying: bool = False
    offer_choices: bool = False
    cta_soft: bool = False
    repair_mode: bool = False
    repair_trigger: str = ""       # "stuck" | "oscillation" | "repeated_question"
    repair_context: str = ""       # Context about what triggered repair
    rephrase_mode: bool = False    # Parallel to repair_mode: rephrase current question
    prioritize_contact: bool = False  # Fast-track contact collection for rushed clients

    # === Apology (SSoT: src/apology_ssot.py) ===
    should_apologize: bool = False
    should_offer_exit: bool = False

    # === Память ===
    client_card: str = ""
    objection_summary: str = ""
    do_not_repeat: List[str] = field(default_factory=list)
    do_not_repeat_responses: List[str] = field(default_factory=list)  # НОВОЕ: предыдущие ответы бота
    reference_pain: str = ""

    # === Meta ===
    reason_codes: List[str] = field(default_factory=list)
    instruction: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        return {
            "style": {
                "tone": self.tone.value,
                "max_words": self.max_words,
                "one_question": self.one_question,
                "use_bullets": self.use_bullets,
                "be_brief": self.be_brief,
            },
            "dialogue_moves": {
                "validate": self.validate,
                "summarize_client": self.summarize_client,
                "ask_clarifying": self.ask_clarifying,
                "offer_choices": self.offer_choices,
                "cta_soft": self.cta_soft,
                "repair_mode": self.repair_mode,
                "repair_trigger": self.repair_trigger,
                "repair_context": self.repair_context,
            },
            "apology": {
                "should_apologize": self.should_apologize,
                "should_offer_exit": self.should_offer_exit,
            },
            "memory": {
                "client_card": self.client_card,
                "objection_summary": self.objection_summary,
                "do_not_repeat": self.do_not_repeat,
                "do_not_repeat_responses": self.do_not_repeat_responses,  # НОВОЕ
                "reference_pain": self.reference_pain,
            },
            "reason_codes": self.reason_codes,
            "instruction": self.instruction,
        }

    def get_instruction(self) -> str:
        """
        Сгенерировать текстовую инструкцию для LLM.

        Returns:
            Строка с инструкциями для генератора
        """
        if self.instruction:
            return self.instruction

        parts = []

        # === Apology instructions (FIRST priority - must be at start) ===
        # SSoT: src/apology_ssot.py
        if self.should_apologize:
            from src.apology_ssot import get_apology_instruction
            parts.append(get_apology_instruction())

        if self.should_offer_exit:
            from src.apology_ssot import get_exit_instruction
            parts.append(get_exit_instruction())

        # Тон
        tone_map = {
            ResponseTone.EMPATHETIC: "Используй эмпатичный тон, признай ситуацию клиента.",
            ResponseTone.CONFIDENT: "Используй уверенный тон, подчеркни преимущества.",
            ResponseTone.SUPPORTIVE: "Используй поддерживающий тон, помоги разобраться.",
            ResponseTone.NEUTRAL: "",
        }
        if tone_map.get(self.tone):
            parts.append(tone_map[self.tone])

        # Структура
        if self.validate:
            parts.append("Начни с признания ситуации клиента (1 фраза).")

        if self.summarize_client and self.client_card:
            parts.append(f"Можешь сослаться на: {self.client_card}")

        if self.rephrase_mode:
            parts.append(
                "Переформулируй текущий вопрос другими словами. "
                "Не повторяй его дословно."
            )

        if self.repair_mode:
            repair_parts = ["Режим восстановления диалога."]
            if self.repair_trigger == "stuck":
                repair_parts.append(
                    "Клиент застрял — предложи 2-3 конкретных варианта "
                    "следующего шага (демо, консультация, информация)."
                )
            elif self.repair_trigger == "oscillation":
                repair_parts.append(
                    "Диалог зациклился — кратко суммируй что обсудили "
                    "и предложи конкретный следующий шаг."
                )
            elif self.repair_trigger == "repeated_question":
                repair_parts.append(
                    f"Клиент повторяет вопрос. {self.repair_context} "
                    "Ответь по-другому, используя конкретные факты и цифры."
                )
            else:
                repair_parts.append("Перефразируй и уточни понимание.")
            parts.append(" ".join(repair_parts))

        if self.ask_clarifying:
            parts.append("Задай один конкретный уточняющий вопрос.")

        if self.offer_choices:
            parts.append("Предложи 2-3 варианта ответа.")

        if self.prioritize_contact:
            parts.append(
                "Клиент торопится. Запроси контактные данные (телефон или email) "
                "для продолжения разговора. Встрой запрос естественно в ответ."
            )

        if self.cta_soft:
            parts.append("Добавь мягкий призыв к следующему шагу.")

        # Ограничения
        if self.one_question:
            parts.append("Максимум 1 вопрос в конце ответа.")

        if self.be_brief:
            parts.append("Будь краток и по делу.")

        if self.max_words < 50:
            parts.append(f"Ответ не более {self.max_words} слов.")

        # Что не повторять
        if self.do_not_repeat:
            parts.append(f"Не спрашивай повторно: {', '.join(self.do_not_repeat)}")

        # НОВОЕ: Не повторять предыдущие ответы
        if self.do_not_repeat_responses:
            # Берём первые 80 символов каждого ответа для краткости
            recent = [r[:80] + "..." if len(r) > 80 else r for r in self.do_not_repeat_responses[-3:]]
            parts.append(f"НЕ ПОВТОРЯЙ дословно эти фразы: {recent}")

        # Возражения
        if self.objection_summary:
            parts.append(f"Учти предыдущие возражения: {self.objection_summary}")

        return " ".join(parts) if parts else ""


class ResponseDirectivesBuilder:
    """
    Builder для создания ResponseDirectives из ContextEnvelope.

    Анализирует контекст и генерирует директивы для "человечного" ответа.

    Usage:
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()
        summary = builder.build_context_summary()
    """

    # Defaults (используются если конфиг недоступен)
    _DEFAULT_MAX_SUMMARY_LINES = 6
    _DEFAULT_TONE_THRESHOLDS = {
        "empathetic_frustration": 5,
        "validate_frustration": 4,
    }
    _DEFAULT_MAX_WORDS = {
        "high_frustration": 40,
        "low_engagement": 50,
        "repair_mode": 50,
        "default": 60,
        "instruction_threshold": 50,
    }
    _DEFAULT_OBJECTION_TRANSLATIONS = {
        "objection_price": "цена",
        "objection_competitor": "конкурент",
        "objection_no_time": "нет времени",
        "objection_think": "подумать",
        "objection_timing": "не сейчас",
        "objection_complexity": "сложно",
        "objection_no_need": "не нужно",
        "objection_trust": "доверие",
    }
    _DEFAULT_COLLECTED_FIELD_NAMES = {
        "company_size": "размер компании",
        "company_name": "название компании",
        "business_type": "тип бизнеса",
        "pain_point": "проблема",
        "current_tools": "текущие инструменты",
    }
    _DEFAULT_TONE_INSTRUCTIONS = {
        "empathetic": "Используй эмпатичный тон, признай ситуацию клиента.",
        "confident": "Используй уверенный тон, подчеркни преимущества.",
        "supportive": "Используй поддерживающий тон, помоги разобраться.",
        "neutral": "",
    }

    def __init__(self, envelope: ContextEnvelope, config: Dict[str, Any] = None):
        """
        Args:
            envelope: ContextEnvelope с полным контекстом
            config: Опциональный конфиг (по умолчанию из get_config())
        """
        self.envelope = envelope

        # Загружаем конфиг response_directives
        if config is None:
            try:
                from src.config_loader import get_config
                config = get_config().response_directives
            except Exception:
                config = {}
        self._config = config

    @property
    def max_summary_lines(self) -> int:
        """Максимум строк в context_summary."""
        return self._config.get("max_summary_lines", self._DEFAULT_MAX_SUMMARY_LINES)

    @property
    def tone_thresholds(self) -> Dict[str, int]:
        """Пороги для определения тона."""
        return self._config.get("tone_thresholds", self._DEFAULT_TONE_THRESHOLDS)

    @property
    def max_words_config(self) -> Dict[str, int]:
        """Лимиты длины ответа."""
        return self._config.get("max_words", self._DEFAULT_MAX_WORDS)

    @property
    def objection_translations(self) -> Dict[str, str]:
        """Переводы типов возражений."""
        return self._config.get("objection_translations", self._DEFAULT_OBJECTION_TRANSLATIONS)

    @property
    def collected_field_names(self) -> Dict[str, str]:
        """Названия полей для do_not_repeat."""
        return self._config.get("collected_field_names", self._DEFAULT_COLLECTED_FIELD_NAMES)

    @property
    def tone_instructions(self) -> Dict[str, str]:
        """Тексты инструкций по тонам."""
        return self._config.get("tone_instructions", self._DEFAULT_TONE_INSTRUCTIONS)

    def build(self) -> ResponseDirectives:
        """
        Построить директивы на основе контекста.

        Returns:
            ResponseDirectives
        """
        directives = ResponseDirectives()

        # Копируем reason codes
        directives.reason_codes = self.envelope.reason_codes.copy()

        # === Определяем тон ===
        directives.tone = self._determine_tone()

        # === Определяем стиль ===
        self._apply_style(directives)

        # === Определяем диалоговые действия ===
        self._apply_dialogue_moves(directives)

        # === Заполняем память ===
        self._fill_memory(directives)

        # === Apology flags (SSoT: src/apology_ssot.py) ===
        self._fill_apology(directives)

        # === Генерируем инструкцию ===
        directives.instruction = directives.get_instruction()

        return directives

    def _determine_tone(self) -> ResponseTone:
        """Определить тон ответа."""
        envelope = self.envelope
        empathetic_threshold = self.tone_thresholds.get("empathetic_frustration", 3)

        # Высокая фрустрация → эмпатичный
        if envelope.frustration_level >= empathetic_threshold:
            return ResponseTone.EMPATHETIC

        # Прогресс и breakthrough → уверенный (важнее чем возражения, т.к. клиент их преодолел)
        if envelope.has_reason(ReasonCode.BREAKTHROUGH_DETECTED):
            return ResponseTone.CONFIDENT

        # Повторные возражения → эмпатичный
        if envelope.has_reason(ReasonCode.OBJECTION_REPEAT):
            return ResponseTone.EMPATHETIC

        # Первое возражение → эмпатичный
        if envelope.first_objection_type:
            return ResponseTone.EMPATHETIC

        # Repair mode → поддерживающий
        if envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE):
            return ResponseTone.SUPPORTIVE

        # Положительный momentum → уверенный
        if envelope.has_reason(ReasonCode.MOMENTUM_POSITIVE):
            return ResponseTone.CONFIDENT

        return ResponseTone.NEUTRAL

    def _apply_style(self, directives: ResponseDirectives) -> None:
        """Применить стилистические директивы."""
        envelope = self.envelope
        empathetic_threshold = self.tone_thresholds.get("empathetic_frustration", 3)
        max_words = self.max_words_config

        # Ограничение длины
        if envelope.frustration_level >= empathetic_threshold:
            directives.max_words = max_words.get("high_frustration", 40)
            directives.be_brief = True
        elif envelope.engagement_level in ("low", "disengaged"):
            directives.max_words = max_words.get("low_engagement", 50)
            directives.be_brief = True
        elif envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE):
            directives.max_words = max_words.get("repair_mode", 50)
        else:
            directives.max_words = max_words.get("default", 60)

        # One question rule (почти всегда)
        directives.one_question = True

        # Bullets при сложных объяснениях
        if envelope.repeated_question:
            directives.use_bullets = True

    def _apply_dialogue_moves(self, directives: ResponseDirectives) -> None:
        """Применить диалоговые действия."""
        envelope = self.envelope
        validate_threshold = self.tone_thresholds.get("validate_frustration", 2)

        # Validate: при фрустрации или возражениях
        if envelope.frustration_level >= validate_threshold:
            directives.validate = True

        if envelope.first_objection_type:
            directives.validate = True

        # Repair mode
        if envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE):
            directives.repair_mode = True

            # При stuck предлагаем варианты
            if envelope.is_stuck:
                directives.offer_choices = True
                directives.ask_clarifying = True
                directives.repair_trigger = "stuck"
            elif getattr(envelope, 'has_oscillation', False):
                directives.repair_trigger = "oscillation"
            elif envelope.repeated_question:
                directives.repair_trigger = "repeated_question"
                # Don't set ask_clarifying when repeated question is a
                # known answerable type (price, technical, features, etc.)
                # For these, the policy overlay + generator will select the correct
                # answer template. Adding "ask clarifying" conflicts with answer-first.
                from src.yaml_config.constants import INTENT_CATEGORIES
                _answerable = (
                    set(INTENT_CATEGORIES.get("price_related", []))
                    | set(INTENT_CATEGORIES.get("question", []))
                )
                if envelope.repeated_question not in _answerable:
                    directives.ask_clarifying = True
                # Category-aware repair context
                _price = set(INTENT_CATEGORIES.get("price_related", []))
                if envelope.repeated_question in _price:
                    directives.repair_context = (
                        "Клиент ПОВТОРНО спрашивает о цене! "
                        "ОБЯЗАТЕЛЬНО назови конкретные цены тарифов из базы знаний."
                    )
                else:
                    directives.repair_context = (
                        f"Повторяющийся вопрос: {envelope.repeated_question}"
                    )
            # If repeated_question was already handled in stuck block, skip
            elif not envelope.is_stuck:
                pass  # Default repair_trigger stays ""

        # Summarize: если есть данные и не repair
        if envelope.client_has_data and not directives.repair_mode:
            directives.summarize_client = True

        # CTA soft: при breakthrough window
        if envelope.has_reason(ReasonCode.BREAKTHROUGH_CTA):
            directives.cta_soft = True

        # Fast-track: rushed client + no contact + sufficient engagement
        if self._should_fast_track_contact():
            directives.prioritize_contact = True

    def _should_fast_track_contact(self) -> bool:
        """Fast-track contact collection for time-constrained conversations.

        Uses Tone enum value (lowercase) and has_valid_contact from SSOT module.
        """
        envelope = self.envelope

        # Only for RUSHED clients (Tone.RUSHED.value = "rushed", lowercase!)
        if envelope.tone != "rushed":
            return False

        # Already have contact — use SSOT validator
        try:
            from src.conditions.state_machine.contact_validator import has_valid_contact
            if has_valid_contact(envelope.collected_data):
                return False
        except ImportError:
            # Defense-in-depth: if validator unavailable, check raw fields
            if any(k in envelope.collected_data for k in ("contact_info", "email", "phone")):
                return False

        # Need minimum engagement (4+ turns)
        # Field is total_turns (not turn_number!) per context_envelope.py:238
        if envelope.total_turns < 4:
            return False

        return True

    def _fill_memory(self, directives: ResponseDirectives) -> None:
        """Заполнить память для персонализации."""
        envelope = self.envelope

        # Client card (краткое резюме)
        directives.client_card = self._build_client_card()

        # Objection summary
        if envelope.objection_types_seen:
            objection_names = self._translate_objections(envelope.objection_types_seen)
            directives.objection_summary = ", ".join(objection_names)

        # Do not repeat (уже собранные данные)
        directives.do_not_repeat = self._get_collected_fields()

        # НОВОЕ: Do not repeat responses (предыдущие ответы бота)
        directives.do_not_repeat_responses = self._get_recent_bot_responses()

        # Reference pain
        if envelope.client_pain_points:
            # Берём первую боль (без PII)
            directives.reference_pain = envelope.client_pain_points[0]

    def _build_client_card(self) -> str:
        """
        Построить краткую карточку клиента.

        Returns:
            Строка с фактами о клиенте (без PII)
        """
        envelope = self.envelope
        parts = []

        # Размер компании
        if envelope.client_company_size:
            parts.append(f"компания ~{envelope.client_company_size} чел")

        # Боли
        if envelope.client_pain_points:
            pain = envelope.client_pain_points[0]
            parts.append(f"боль: {pain}")

        # Отрасль (из collected_data)
        collected = envelope.collected_data
        if collected.get("business_type"):
            parts.append(f"сфера: {collected['business_type']}")

        # Ограничиваем длину
        if len(parts) > 3:
            parts = parts[:3]

        return "; ".join(parts) if parts else ""

    def _get_collected_fields(self) -> List[str]:
        """Получить список уже собранных полей (для do_not_repeat)."""
        collected = self.envelope.collected_data
        fields = []

        for key, name in self.collected_field_names.items():
            if collected.get(key):
                fields.append(name)

        return fields

    def _get_recent_bot_responses(self, n: int = 3) -> List[str]:
        """
        НОВОЕ: Получить последние N ответов бота для предотвращения повторов.

        Args:
            n: Количество ответов для возврата

        Returns:
            Список последних ответов бота (первые 100 символов каждого)
        """
        responses = []

        # Пытаемся получить из envelope.bot_responses (если есть)
        if hasattr(self.envelope, 'bot_responses') and self.envelope.bot_responses:
            responses = self.envelope.bot_responses[-n:]
        # Fallback: пытаемся получить из history
        elif hasattr(self.envelope, 'history') and self.envelope.history:
            for turn in self.envelope.history[-n:]:
                if isinstance(turn, dict) and turn.get("bot"):
                    responses.append(turn["bot"])

        # Ограничиваем длину каждого ответа для краткости
        return [r[:100] for r in responses if r]

    def _translate_objections(self, objection_types: List[str]) -> List[str]:
        """Перевести типы возражений в читаемый вид."""
        return [self.objection_translations.get(o, o) for o in objection_types]

    def _fill_apology(self, directives: ResponseDirectives) -> None:
        """
        Fill apology flags from envelope using SSoT.

        Uses apology_ssot module for threshold logic to ensure consistency
        with frustration_thresholds SSoT.

        IMPORTANT: For should_offer_exit, we must also consider pre_intervention_triggered
        which is set by FrustrationIntensityCalculator at WARNING level (5-6) with certain
        conditions (RUSHED tone, multiple signals). This ensures exit is offered not just
        at HIGH frustration (7+), but also when pre-intervention is triggered.

        SSoT: src/apology_ssot.py
        """
        from src.apology_ssot import should_apologize, should_offer_exit

        # Use SSoT functions for threshold logic
        frustration_level = self.envelope.frustration_level
        pre_intervention = getattr(self.envelope, 'pre_intervention_triggered', False)

        # Pass tone for tone-aware apology thresholds (SSOT)
        tone = getattr(self.envelope, 'tone', None)
        directives.should_apologize = should_apologize(frustration_level, tone=tone)
        # Pass pre_intervention_triggered to ensure exit is offered at WARNING level too
        directives.should_offer_exit = should_offer_exit(frustration_level, pre_intervention)

    def build_context_summary(self) -> str:
        """
        Построить краткий текстовый summary контекста.

        Используется для передачи в промпт генератора.
        Ограничен max_summary_lines строками.

        Returns:
            Текстовый summary (без PII)
        """
        envelope = self.envelope
        lines = []

        # 1. Состояние диалога
        if envelope.total_turns > 0:
            lines.append(f"Ход диалога: {envelope.total_turns}")

        # 2. Клиент
        if envelope.client_company_size:
            lines.append(f"Компания: ~{envelope.client_company_size} сотрудников")

        if envelope.client_pain_points:
            lines.append(f"Боль клиента: {envelope.client_pain_points[0]}")

        # 3. Паттерны
        if envelope.has_reason(ReasonCode.REPAIR_STUCK):
            lines.append("Внимание: клиент застрял, нужно уточнение")

        if envelope.has_reason(ReasonCode.REPAIR_OSCILLATION):
            lines.append("Внимание: клиент колеблется")

        if envelope.repeated_question:
            lines.append("Внимание: повторный вопрос от клиента")

        # 4. Возражения
        if envelope.repeated_objection_types:
            obj_names = self._translate_objections(envelope.repeated_objection_types)
            lines.append(f"Повторные возражения: {', '.join(obj_names)}")
        elif envelope.first_objection_type:
            obj_name = self._translate_objections([envelope.first_objection_type])[0]
            lines.append(f"Первое возражение: {obj_name}")

        # 5. Прогресс
        if envelope.has_breakthrough:
            lines.append("Был прорыв: клиент показал интерес")

        # Ограничиваем количество строк
        if len(lines) > self.max_summary_lines:
            lines = lines[:self.max_summary_lines]

        return "\n".join(lines) if lines else ""


def build_response_directives(envelope: ContextEnvelope) -> ResponseDirectives:
    """
    Удобная функция для создания ResponseDirectives.

    Args:
        envelope: ContextEnvelope

    Returns:
        ResponseDirectives
    """
    return ResponseDirectivesBuilder(envelope).build()


def build_context_summary(envelope: ContextEnvelope) -> str:
    """
    Удобная функция для создания context summary.

    Args:
        envelope: ContextEnvelope

    Returns:
        Текстовый summary
    """
    return ResponseDirectivesBuilder(envelope).build_context_summary()
