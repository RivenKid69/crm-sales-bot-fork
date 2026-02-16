"""
LLM-агент для имитации клиента.

Использует LLM для генерации реалистичных ответов клиента
на основе персоны и истории диалога.

Поддерживает:
- Генерацию ответов через LLM
- Обработку disambiguation (нажатие на кнопки выбора)
- Шум и персонализацию ответов
"""

import logging
import random
import re
import time
from typing import List, Dict, Any, Optional, Tuple

from src.simulator.personas import Persona
from src.simulator.noise import add_noise, add_heavy_noise, add_light_noise
from src.decision_trace import ClientAgentTrace
from src.yaml_config.constants import MAX_CONSECUTIVE_OBJECTIONS

logger = logging.getLogger(__name__)

# =============================================================================
# Disambiguation Detection & Handling
# =============================================================================

# Ключевые слова для выбора опции по персоне
# ВАЖНО: ключи - это persona.name (отображаемые имена из personas.py)
PERSONA_OPTION_PREFERENCES: Dict[str, List[str]] = {
    # Русские имена персон (как в Persona.name)
    "Ценовик": ["цен", "стоим", "прайс", "тариф", "скольк", "дорог"],
    "Пользователь конкурента": ["конкур", "poster", "iiko", "r-keeper", "сравн", "другим"],
    "Технарь": ["api", "интеграц", "безопас", "данн", "техн", "функци"],
    "Занятой": [],  # Выбирает первый вариант
    "Агрессивный": [],  # Может игнорировать кнопки
    "Идеальный клиент": ["демо", "показ", "попробов", "функци", "узнать"],
    "Скептик": ["другое", "свой"],  # Предпочитает свой вариант
    "Просто смотрю": ["подум", "потом", "другое"],
}

OBJECTION_INJECTIONS: Dict[str, List[str]] = {
    "price": ["но это дорого", "а подешевле?", "дороговато"],
    "time": ["некогда", "давайте быстрее", "нет времени"],
    "skepticism": ["не уверен", "сомневаюсь", "а это точно работает?"],
    "competitor": ["а чем лучше Poster?", "у iiko это есть"],
    "not_now": ["потом", "не сейчас", "подумаю"],
    "trust": ["не верю", "докажите"],
    "proof": ["покажите реальные кейсы", "есть подтверждённые результаты?", "нужны конкретные доказательства"],
    "busy": ["сейчас не до этого", "я очень занят", "короче, у меня мало времени"],
    "discount": ["скидка будет?", "а акция есть?", "можно дешевле по скидке?"],
    "expensive": ["слишком дорого для нас", "цена завышена", "по бюджету не проходит"],
    "migration": ["перенос данных будет сложный", "боюсь потерять данные при миграции", "как переносить базу без сбоев?"],
    "features": ["функций маловато", "нужных возможностей не вижу", "а где расширенный функционал?"],
    "waste_time": ["хватит тратить мое время", "слишком долго и без сути", "это пустая трата времени"],
    "annoyed": ["раздражает такой подход", "меня это уже бесит", "не нравится, как вы объясняете"],
    "technical": ["технически выглядит сыро", "архитектура вызывает вопросы", "не вижу нормальной техбазы"],
    "integration": ["а с нашими системами точно интегрируется?", "интеграции не хватит", "боюсь проблем с интеграцией"],
    "security": ["как с безопасностью данных?", "есть сомнения по защите", "риски по ИБ слишком высокие"],
    "just_looking": ["я пока просто смотрю", "сейчас только изучаю рынок", "мне пока просто интересно"],
    "maybe_later": ["давайте позже вернемся", "может потом", "не сейчас, позже"],
    "scalability": ["а при росте не развалится?", "масштабируемость под вопросом", "выдержит ли рост команды?"],
    "free_alternatives": ["есть бесплатные альтернативы", "зачем платить, если есть free-решения?", "мы можем на бесплатном обойтись"],
    "compliance": ["нам нужен строгий compliance", "без соответствия требованиям не подойдет", "по регуляторике есть риски"],
    "enterprise_features": ["нужны enterprise-функции", "где SSO и аудит?", "для крупной компании фич недостаточно"],
    "multi_location": ["а с несколькими точками как работать?", "мультилокация нужна из коробки", "по филиалам это не закрывает задачу"],
    "simplicity": ["слишком сложно для команды", "нужно проще", "персонал не разберется"],
    "past_issues": ["в прошлый раз были проблемы", "раньше не работало как надо", "у нас был плохой опыт"],
    "competitor_comparison": ["у конкурента удобнее", "в сравнении с другим решением вы проигрываете", "конкурент выглядит сильнее"],
    "not_decision_maker": ["я не принимаю решение", "это решает директор", "финальное слово не за мной"],
    "need_materials": ["пришлите материалы сначала", "нужны презентация и КП", "без документов не смогу продолжить"],
    "not_perfect": ["решение не идеальное", "вижу недостатки", "до идеала не дотягивает"],
    "customization": ["нужна глубокая кастомизация", "под нас нужно донастроить", "без гибкой настройки не подойдет"],
    "details": ["мало деталей", "нужно больше конкретики", "раскройте нюансы подробнее"],
    "boring": ["слишком скучно", "не цепляет", "подача совсем неинтересная"],
    "not_impressed": ["не впечатляет", "ожидал большего", "честно, не зашло"],
    "regional_features": ["нужны региональные особенности", "по регионам это не покрыто", "локальная специфика не учтена"],
    "data_sync": ["синхронизация данных вызывает сомнения", "данные между филиалами могут расходиться", "нужна надежная синхронизация"],
    "localization": ["нужна локализация под регионы", "по языкам и локали не хватает", "локализация выглядит слабой"],
}


class ClientAgent:
    """LLM-агент для имитации клиента"""

    SYSTEM_PROMPT = """Ты играешь роль потенциального клиента CRM системы Wipon в Казахстане.

ПЕРСОНА: {persona_name}
{persona_description}

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Отвечай КОРОТКО - максимум 1-2 предложения (не больше 30 слов)
2. Пиши как реальный человек в мессенджере:
   - Можно без заглавных букв
   - Можно с опечатками
   - Используй разговорную речь
3. НЕ будь слишком вежливым - это подозрительно
4. НЕ используй формальные фразы типа "Благодарю за информацию"
5. Веди себя СТРОГО согласно персоне
6. Если продавец просит контакт (телефон или email), то дай реальный контакт
   (если в описании персоны НЕ сказано "не даёшь контакты")

МОЖЕШЬ:
- Отвлекаться от темы
- Задавать неожиданные вопросы
- Выражать сомнения
- Торопиться или грубить (если персона такая)
- Уйти из разговора если надоело

ИСТОРИЯ ДИАЛОГА:
{history}

ПОСЛЕДНЕЕ СООБЩЕНИЕ ПРОДАВЦА:
{bot_message}

Ответь как клиент (1-2 коротких предложения, максимум 30 слов):"""

    def __init__(self, llm: Any, persona: Persona, kb_pool=None, persona_key: Optional[str] = None):
        """
        Инициализация агента клиента.

        Args:
            llm: LLM для генерации ответов
            persona: Персона клиента
            kb_pool: KBQuestionPool instance (optional)
            persona_key: Persona key string for KB pool lookups (e.g. "technical")
        """
        self.llm = llm
        self.persona = persona
        self.kb_pool = kb_pool
        self._persona_key = persona_key or "happy_path"
        self._asked_topics: set = set()
        self._kb_questions_used: int = 0
        self._kb_starter_topic: Optional[str] = None
        self.history: List[Dict[str, str]] = []
        self.turn = 0
        self._decided_to_leave = False
        self._objection_count = 0
        self._last_response = ""
        self._repeat_count = 0
        self._last_trace: Optional[ClientAgentTrace] = None
        self._enable_tracing = True
        self._provided_contact = False
        self._contact_value: Optional[str] = None
        self._contact_type: Optional[str] = None
        self._objection_keys_validated = False
        self._missing_objection_keys: set[str] = set()

    def start_conversation(self) -> str:
        """
        Генерирует первое сообщение клиента.

        May use a KB-grounded question as starter with capped probability
        to preserve persona intent diversity.

        Returns:
            Стартовое сообщение
        """
        # Cap at 0.4 for starters — original starters are designed for correct intent classification
        starter_prob = min(self.persona.kb_question_probability, 0.4)

        if self.kb_pool and random.random() < starter_prob:
            kb_q = self.kb_pool.get_starter(self._persona_key)
            if kb_q:
                self._asked_topics.add(kb_q.source_topic)
                self._kb_questions_used += 1
                self._kb_starter_topic = kb_q.source_topic
                return self._apply_persona_noise(kb_q.text)

        # Fallback to original behavior
        starter = random.choice(self.persona.conversation_starters)
        starter = self._apply_persona_noise(starter)
        return starter

    # =========================================================================
    # Disambiguation Handling (Button/Option Selection)
    # =========================================================================

    def _detect_disambiguation(self, bot_message: str) -> bool:
        """
        Определяет, содержит ли сообщение бота disambiguation (кнопки выбора).

        ВАЖНО: Детектируем только ЯВНЫЕ disambiguation кейсы:
        - Нумерованные списки: "1. ... 2. ..."
        - Специальные фразы: "Уточните, пожалуйста"

        НЕ детектируем:
        - Простые вопросы с "или": "скорость или функционал?"
          (это SPIN/Challenger вопросы, не disambiguation)

        FIX: Убран паттерн r"или\s+.+\?$" - слишком широкий,
        ловил обычные вопросы типа "скорость или функционал?"
        и клиент отвечал "1" вместо natural ответа.

        Args:
            bot_message: Сообщение от бота

        Returns:
            True если это ЯВНЫЙ disambiguation
        """
        # Строгие паттерны - только явный disambiguation
        strict_patterns = [
            r"Уточните.*пожалуйста",  # Явная просьба уточнить
            r"^\d+\.\s+.+",  # Начинается с "1. ..." (нумерованный список)
            r"\n\d+\.\s+",  # Содержит перенос + "2. ..." (многострочный список)
            r"Правильно ли я понял",  # Подтверждение
            r"Что именно вас интересует",  # Уточнение
            # FIX: Убран широкий паттерн r"или\s+.+\?$"
        ]

        for pattern in strict_patterns:
            if re.search(pattern, bot_message, re.IGNORECASE | re.MULTILINE):
                return True

        # Специальный случай: "Вы хотите X или Y?" - это disambiguation
        # только если это единственный вопрос (не часть SPIN)
        if re.search(r"^Вы хотите\s+.+\s+или\s+.+\?$", bot_message.strip(), re.IGNORECASE):
            return True

        return False

    def _extract_options(self, bot_message: str) -> List[str]:
        """
        Извлекает варианты выбора из сообщения бота.

        Args:
            bot_message: Сообщение от бота

        Returns:
            Список вариантов (labels)
        """
        options = []

        # Паттерн для нумерованных опций: "1. Узнать цену"
        numbered_pattern = r"(\d+)\.\s+([^\n]+)"
        matches = re.findall(numbered_pattern, bot_message)

        if matches:
            for num, label in matches:
                label = label.strip()
                # Исключаем служебные фразы
                if "напишите" not in label.lower() and "своими словами" not in label.lower():
                    options.append(label)

        # Паттерн для inline формата: "X или Y?"
        if not options:
            inline_pattern = r"Вы хотите\s+(.+?)\s+или\s+(.+?)\?"
            match = re.search(inline_pattern, bot_message, re.IGNORECASE)
            if match:
                options.append(match.group(1).strip())
                options.append(match.group(2).strip())

        # Паттерн для простого "X или Y?"
        if not options:
            simple_or_pattern = r"(.+?)\s+или\s+(.+?)\?$"
            match = re.search(simple_or_pattern, bot_message.strip())
            if match:
                options.append(match.group(1).strip())
                options.append(match.group(2).strip())

        return options

    def _choose_option(self, options: List[str], bot_message: str) -> Tuple[int, str]:
        """
        Выбирает опцию на основе персоны клиента.

        Логика выбора:
        - busy/aggressive: первая опция (быстро)
        - skeptic/tire_kicker: "другое" или последняя
        - price_sensitive: ищет ценовые опции
        - technical: ищет технические опции
        - competitor_user: ищет опции про конкурентов
        - happy_path: первая релевантная или первая

        Args:
            options: Список вариантов
            bot_message: Оригинальное сообщение (для контекста)

        Returns:
            Tuple[index, reason] - индекс выбранной опции и причина
        """
        if not options:
            return 0, "no_options"

        persona_name = self.persona.name

        # Занятой/Агрессивный - просто первый вариант
        if persona_name in ["Занятой", "Агрессивный"]:
            return 0, "quick_choice"

        # Скептик/Просто смотрю - с вероятностью выбирает "другое"
        if persona_name in ["Скептик", "Просто смотрю"]:
            if random.random() < 0.4:
                # Ищем "другое" или последний вариант
                for i, opt in enumerate(options):
                    if "друг" in opt.lower():
                        return i, "prefers_custom"
                return len(options) - 1, "avoids_commitment"

        # Поиск по ключевым словам персоны
        preferences = PERSONA_OPTION_PREFERENCES.get(persona_name, [])
        if preferences:
            for i, opt in enumerate(options):
                opt_lower = opt.lower()
                for keyword in preferences:
                    if keyword in opt_lower:
                        return i, f"keyword_match:{keyword}"

        # По умолчанию - первый вариант
        return 0, "default_first"

    def _generate_disambiguation_response(
        self,
        option_index: int,
        options: List[str],
        reason: str
    ) -> str:
        """
        Генерирует ответ на disambiguation в стиле персоны.

        Возможные форматы:
        - Числовой: "1", "2"
        - Словесный: "первый", "второй"
        - Ключевое слово: "цена", "функции"
        - Игнорирование кнопок (aggressive): свой текст

        Args:
            option_index: Индекс выбранной опции
            options: Список вариантов
            reason: Причина выбора

        Returns:
            Ответ клиента
        """
        persona_name = self.persona.name

        # Агрессивный иногда игнорирует кнопки
        if persona_name == "Агрессивный" and random.random() < 0.3:
            ignore_responses = [
                "да говорите уже",
                "ну давай короче",
                "хватит вопросов, рассказывай",
            ]
            return random.choice(ignore_responses)

        # Занятой всегда выбирает вариант числом — это ожидается тестами
        # и упрощает парсинг disambiguation в симуляции.
        if persona_name == "Занятой":
            return str(option_index + 1)

        # Выбираем формат ответа случайно
        response_type = random.choice(["numeric", "keyword", "natural"])

        if response_type == "numeric":
            # "1", "2", "3"
            return str(option_index + 1)

        elif response_type == "keyword" and option_index < len(options):
            # Берём ключевое слово из опции
            opt = options[option_index].lower()
            # Убираем "узнать", "обсудить" и т.п.
            for prefix in ["узнать ", "обсудить ", "получить ", "заказать "]:
                opt = opt.replace(prefix, "")
            # Берём первые 2 слова
            words = opt.split()[:2]
            if words:
                return " ".join(words)
            return str(option_index + 1)

        else:
            # Natural response - "да, первое", "второй вариант"
            ordinals = ["первое", "второе", "третье", "четвёртое"]
            if option_index < len(ordinals):
                prefixes = ["", "да, ", "ну ", "хм, "]
                prefix = random.choice(prefixes)
                return f"{prefix}{ordinals[option_index]}"

        return str(option_index + 1)

    def respond(self, bot_message: str) -> str:
        """
        Генерирует ответ клиента на сообщение бота.

        Если бот показывает disambiguation (кнопки выбора), клиент
        "нажимает" на подходящую кнопку на основе своей персоны.

        Args:
            bot_message: Сообщение бота

        Returns:
            Ответ клиента
        """
        # Initialize trace for this turn
        trace = ClientAgentTrace(
            persona_name=self.persona.name,
            persona_description=self.persona.description[:200] if self.persona.description else "",
        ) if self._enable_tracing else None

        start_time = time.time()

        # Проверяем, решил ли клиент уйти
        if self._should_leave_now():
            response = self._generate_leave_message()
            if trace:
                trace.leave_decision = {"should_leave": True, "reason": "persona_behavior"}
                trace.cleaned_response = response
                trace.llm_latency_ms = 0
                self._last_trace = trace
            return response

        # =====================================================================
        # Contact Request Handling
        # =====================================================================
        if self._is_contact_request(bot_message):
            response = self._handle_contact_request()
            if trace:
                trace.cleaned_response = response
                trace.llm_latency_ms = 0
                trace.leave_decision = {"should_leave": False, "reason": "contact_request"}
                self._last_trace = trace

            # Сохраняем в историю
            self.history.append({
                "bot": bot_message,
                "client": response
            })
            self.turn += 1
            self._last_response = response
            return response

        # =====================================================================
        # Disambiguation Handling: "Нажатие на кнопку"
        # =====================================================================
        if self._detect_disambiguation(bot_message):
            options = self._extract_options(bot_message)
            if options:
                option_index, reason = self._choose_option(options, bot_message)
                response = self._generate_disambiguation_response(option_index, options, reason)

                # Trace disambiguation decision
                if trace:
                    trace.disambiguation_decision = {
                        "detected": True,
                        "options": options,
                        "chosen_index": option_index,
                        "chosen_option": options[option_index] if option_index < len(options) else "N/A",
                        "reason": reason,
                    }
                    trace.cleaned_response = response
                    trace.llm_latency_ms = 0
                    trace.leave_decision = {"should_leave": False, "reason": None}
                    self._last_trace = trace

                # Сохраняем в историю
                self.history.append({
                    "bot": bot_message,
                    "client": response
                })
                self.turn += 1

                return response

        # =====================================================================
        # Regular LLM-based Response Generation
        # =====================================================================

        # Build insistence block based on persona
        insistence_block = ""
        if self.persona.insistence_probability > 0.5:
            insistence_block = """
ВАЖНО: Если ты задал вопрос (особенно про цену), а собеседник не ответил прямо
и вместо этого задал свой вопрос — НАСТАИВАЙ на своём вопросе.
Переформулируй вопрос или скажи что тебе не ответили.
НЕ отвечай на контр-вопрос пока не получишь ответ на свой."""
        elif self.persona.insistence_probability > 0.2:
            insistence_block = """
Если ты задал вопрос, а собеседник не ответил — можешь ответить на его вопрос,
но потом верни разговор к своему вопросу."""

        # Build description with insistence
        full_description = self.persona.description
        if insistence_block:
            full_description = self.persona.description + insistence_block

        # Строим промпт
        prompt = self.SYSTEM_PROMPT.format(
            persona_name=self.persona.name,
            persona_description=full_description,
            history=self._format_history(),
            bot_message=bot_message
        )

        # Dynamic insistence: if bot deflected and client had a pending question
        if (self.persona.insistence_probability > 0
            and "?" in bot_message
            and self._has_pending_question()
            and random.random() < self.persona.insistence_probability):
            prompt += "\nСЕЙЧАС: Собеседник не ответил на твой предыдущий вопрос. НАСТАИВАЙ!"

        if trace:
            trace.prompt_sent_to_llm = prompt

        # Генерируем ответ через LLM
        raw_response = ""
        try:
            raw_response = self.llm.generate(prompt)
            response = self._clean_response(raw_response)
            if trace:
                trace.raw_llm_response = raw_response
        except Exception:
            # Fallback если LLM не работает
            response = self._generate_fallback_response()
            if trace:
                trace.raw_llm_response = f"ERROR: fallback used"

        # Track LLM latency
        llm_elapsed = (time.time() - start_time) * 1000
        if trace:
            trace.llm_latency_ms = llm_elapsed

        # === KB Follow-up Injection (before noise/objection) ===
        # Only inject when bot is NOT asking a question (to preserve phase progression)
        kb_injected = False
        bot_is_asking = bot_message.rstrip().endswith("?")

        if (
            self.kb_pool is not None
            and not bot_is_asking
            and self._kb_questions_used < 4
            and random.random() < self.persona.kb_question_probability * 0.4
        ):
            kb_q = self.kb_pool.get_followup(self._persona_key, self._asked_topics)
            if kb_q:
                self._asked_topics.add(kb_q.source_topic)
                self._kb_questions_used += 1
                ack = random.choice(["ок", "понял", "ага", "хорошо", "ну ладно"])
                response = f"{ack}. {kb_q.text}"
                kb_injected = True
                if trace:
                    trace.kb_question_used = kb_q.text
                    trace.kb_question_source = kb_q.source_topic

        # Skip noise/objection if KB question replaced the response
        if not kb_injected:
            # Проверяем на повтор и форсируем разнообразие
            original_response = response
            response = self._ensure_variety(response)
            if trace and response != original_response:
                trace.variety_check = {"similar_to_last": True, "forced_alternative": True}
            else:
                if trace:
                    trace.variety_check = {"similar_to_last": False, "forced_alternative": False}

            # Применяем шум согласно персоне
            before_noise = response
            response = self._apply_persona_noise(response)
            if trace and response != before_noise:
                # Track what noise was applied
                trace.noise_applied = {"modified": True}

            # Проверяем, нужно ли добавить возражение
            objection_roll = random.random()
            objection_threshold = self.persona.objection_probability * 0.3
            should_add_objection = (
                self._objection_count < MAX_CONSECUTIVE_OBJECTIONS
                and objection_roll < objection_threshold
            )

            if trace:
                trace.objection_decision = {
                    "roll": round(objection_roll, 3),
                    "threshold": round(objection_threshold, 3),
                    "injected": should_add_objection,
                }

            if should_add_objection:
                before_objection = response
                response = self._inject_objection(response)
                if trace and response != before_objection:
                    # Extract the injected objection
                    injected_part = response.replace(before_objection, "").strip()
                    trace.objection_injected = injected_part

        if trace:
            trace.cleaned_response = response
            trace.leave_decision = {"should_leave": False, "reason": None}
            self._last_trace = trace

        # Сохраняем в историю
        self.history.append({
            "bot": bot_message,
            "client": response
        })
        self.turn += 1

        return response

    # =========================================================================
    # Contact Request Detection & Response
    # =========================================================================

    def _is_contact_request(self, bot_message: str) -> bool:
        """Heuristic detection for contact request from the bot."""
        if not bot_message:
            return False

        patterns = [
            r"остав(?:ь|ьте)\s+(?:контакт|телефон|номер|почт|e-?mail)",
            r"остав(?:ите|ишь)\s+(?:контакт|телефон|номер|почт|e-?mail)",
            r"подскаж(?:ите|и)\s+(?:номер|телефон|почт|e-?mail|контакт)",
            r"как\s+(?:с\s+вами\s+)?связаться",
            r"номер\s+(?:телефон|для\s+связи)",
            r"контакт(?:ы|ный)?\s+для\s+связи",
            r"ваш\s+(?:номер|телефон|почт|e-?mail)",
            r"на\s+какой\s+e-?mail",
            r"на\s+какую\s+почту",
            r"куда\s+(?:прислать|отправить)\s+(?:информацию|детали|презентацию)",
        ]

        for pattern in patterns:
            if re.search(pattern, bot_message, re.IGNORECASE):
                return True

        return False

    def _handle_contact_request(self) -> str:
        """Return contact info or refusal based on persona."""
        if self.persona.name == "Просто смотрю":
            refusals = [
                "пока без контактов",
                "контакты не оставляю",
                "не хочу давать номер",
                "пока просто смотрю, без контактов",
            ]
            return random.choice(refusals)

        return self._generate_contact_response()

    def _generate_contact_response(self) -> str:
        """Generate a valid contact response (phone or email)."""
        if not self._provided_contact or not self._contact_value:
            contact_type = self._choose_contact_type()
            contact_value = self._generate_contact_value(contact_type)
            self._contact_type = contact_type
            self._contact_value = contact_value
            self._provided_contact = True

        contact_type = self._contact_type or "email"
        contact_value = self._contact_value or ""

        persona = self.persona.name
        if contact_type == "phone":
            if persona == "Занятой":
                return f"тел {contact_value}"
            if persona == "Агрессивный":
                return f"номер {contact_value}. быстро"
            return random.choice([
                f"мой номер {contact_value}",
                f"телефон {contact_value}",
                f"можете звонить на {contact_value}",
            ])

        # email
        if persona == "Занятой":
            return f"почта {contact_value}"
        if persona == "Агрессивный":
            return f"пиши на {contact_value}"
        return random.choice([
            f"почта {contact_value}",
            f"можно написать на {contact_value}",
            f"отправьте на {contact_value}",
        ])

    def _choose_contact_type(self) -> str:
        """Choose contact type based on persona."""
        persona = self.persona.name
        if persona in ["Занятой", "Агрессивный", "Ценовик"]:
            return "phone"
        if persona in ["Технарь", "Пользователь конкурента"]:
            return "email"
        return random.choice(["phone", "email"])

    def _generate_contact_value(self, contact_type: str) -> str:
        """Return a valid phone/email suitable for validators."""
        if contact_type == "phone":
            phones = [
                "+7 999 234-56-78",
                "+7 925 456-78-90",
                "+7 916 321-45-67",
                "+7 903 548-12-39",
            ]
            return random.choice(phones)

        emails = [
            "ivan.petrov@mail.ru",
            "olga.kim@gmail.com",
            "sergey.ivanov@yandex.ru",
            "aida.n@mail.ru",
        ]
        return random.choice(emails)

    def is_budget_exhausted(self) -> bool:
        """Check if hard turn limit has been reached (no random factor).

        Unlike should_continue(), this is a pure deterministic check
        suitable for post-respond boundary validation in the runner.
        """
        return self.turn >= self.persona.max_turns

    def should_continue(self) -> bool:
        """
        Решает, продолжать ли диалог.

        Returns:
            True если клиент хочет продолжать
        """
        # Явно решил уйти
        if self._decided_to_leave:
            return False

        # Достигли максимума ходов
        if self.turn >= self.persona.max_turns:
            return False

        # Случайный уход для некоторых персон
        if self.persona.name in ["Занятой", "Агрессивный", "Просто смотрю"]:
            if self.turn > 3 and random.random() < 0.15:
                self._decided_to_leave = True
                return False

        return True

    def _format_history(self) -> str:
        """Форматирует историю диалога для промпта"""
        if not self.history:
            return "(начало диалога)"

        lines = []
        for turn in self.history[-5:]:  # Последние 5 ходов
            lines.append(f"Продавец: {turn['bot']}")
            lines.append(f"Вы: {turn['client']}")

        return "\n".join(lines)

    def _clean_response(self, response: str) -> str:
        """Очищает ответ LLM от лишнего"""
        # Убираем кавычки если есть
        response = response.strip('"\'')

        # Убираем префиксы типа "Клиент:" или "Ответ:"
        prefixes = ["Клиент:", "Ответ:", "Client:", "Response:", "Вы:"]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix):].strip()

        # Ограничиваем длину
        words = response.split()
        if len(words) > 35:
            response = ' '.join(words[:35])

        # Убираем слишком формальные фразы
        formal_phrases = [
            "Благодарю за информацию",
            "Спасибо за подробный ответ",
            "Очень интересно",
            "Это замечательно",
        ]
        for phrase in formal_phrases:
            response = response.replace(phrase, "")

        return response.strip()

    def _apply_persona_noise(self, text: str) -> str:
        """Применяет шум согласно персоне"""
        if self.persona.name in ["Агрессивный", "Занятой"]:
            return add_heavy_noise(text)
        elif self.persona.name in ["Технарь"]:
            return add_light_noise(text)
        else:
            return add_noise(text)

    def _should_add_objection(self) -> bool:
        """Решает, добавить ли возражение"""
        # Use configurable limit from constants.yaml
        if self._objection_count >= MAX_CONSECUTIVE_OBJECTIONS:
            return False
        return random.random() < self.persona.objection_probability * 0.3

    def _inject_objection(self, response: str) -> str:
        """Добавляет возражение к ответу"""
        if not self.persona.preferred_objections:
            return response

        if not self._objection_keys_validated:
            self._objection_keys_validated = True
            missing_keys = sorted(set(self.persona.preferred_objections) - set(OBJECTION_INJECTIONS))
            if missing_keys:
                self._missing_objection_keys = set(missing_keys)
                logger.warning(
                    "Persona '%s' has unknown preferred_objections keys: %s",
                    self.persona.name,
                    ", ".join(missing_keys),
                )

        # Fail fast to avoid silent partial injection with invalid persona config.
        if self._missing_objection_keys:
            return response

        objection_type = random.choice(self.persona.preferred_objections)
        objection = random.choice(OBJECTION_INJECTIONS[objection_type])
        response = f"{response} {objection}"
        self._objection_count += 1

        return response

    def _has_pending_question(self) -> bool:
        """Check if client had an unanswered question."""
        if not self.history:
            return False
        last = self.history[-1].get("client", "")
        return "?" in last or any(
            w in last.lower() for w in ["стоит", "цен", "скольк", "прайс"]
        )

    def _should_leave_now(self) -> bool:
        """Проверяет, пора ли уходить"""
        if self._decided_to_leave:
            return True

        # tire_kicker уходит рано
        if self.persona.name == "Просто смотрю" and self.turn > 4:
            if random.random() < 0.4:
                self._decided_to_leave = True
                return True

        return False

    def _generate_leave_message(self) -> str:
        """Генерирует сообщение об уходе"""
        leave_messages = {
            "Занятой": ["всё, некогда", "потом", "ладно пока"],
            "Агрессивный": ["всё хватит", "надоело", "пока"],
            "Просто смотрю": ["спс, подумаю", "ок понял, потом", "ладн посмотрим"],
            "default": ["ладно, потом", "пока подумаю", "спасибо, до свидания"]
        }

        messages = leave_messages.get(self.persona.name, leave_messages["default"])
        return random.choice(messages)

    def _generate_fallback_response(self) -> str:
        """Генерирует fallback ответ если LLM не работает"""
        fallbacks = [
            "ага",
            "понял",
            "ок",
            "хм, интересно",
            "а подробнее?",
            "и что дальше?",
        ]
        return random.choice(fallbacks)

    def _ensure_variety(self, response: str) -> str:
        """
        Prevent identical client responses.

        Threshold raised from 2 to 4 to allow streak-based conditions
        (price_repeated_3x, objection_consecutive_3x, etc.) to fire in simulation.
        """
        # Нормализуем для сравнения
        normalized = response.lower().strip()[:50]
        last_normalized = self._last_response.lower().strip()[:50]

        # Проверяем на повтор
        if normalized == last_normalized or self._is_similar(normalized, last_normalized):
            self._repeat_count += 1

            # При повторах - меняем стратегию (threshold raised from 2 to 4)
            if self._repeat_count >= 4:
                # Варианты выхода из цикла
                alternatives = [
                    "ладно, давай дальше",
                    "ок понял, что еще?",
                    "хорошо, продолжай",
                    "угу, а что дальше?",
                    "ну ок",
                    "да да, слышу",
                ]
                response = random.choice(alternatives)
                self._repeat_count = 0
        else:
            self._repeat_count = 0

        self._last_response = response
        return response

    def _is_similar(self, a: str, b: str) -> bool:
        """Проверяет схожесть двух строк (простая эвристика)"""
        if not a or not b:
            return False
        # Если совпадает >70% слов - считаем похожими
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return False
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return (intersection / union) > 0.7 if union > 0 else False

    def get_summary(self) -> Dict[str, Any]:
        """Возвращает summary по клиенту"""
        return {
            "persona": self.persona.name,
            "turns": self.turn,
            "objections": self._objection_count,
            "left_early": self._decided_to_leave,
            "kb_questions_used": self._kb_questions_used,
            "kb_topics_covered": list(self._asked_topics),
            "kb_starter_topic": self._kb_starter_topic,
        }

    def get_last_trace(self) -> Optional[ClientAgentTrace]:
        """Возвращает последний трейс клиентского агента."""
        return self._last_trace
