"""
Главный класс бота — объединяет все компоненты Фаз 0-3.

Интегрированные компоненты:
- Phase 0: Logger, FeatureFlags, Metrics
- Phase 1: ConversationGuard, FallbackHandler, LLM Resilience
- Phase 2: ToneAnalyzer, ResponseVariations, Personalization
- Phase 3: LeadScorer, CircularFlow, ObjectionHandler, CTAGenerator

Архитектурные принципы:
1. FAIL-SAFE: Любой сбой → graceful degradation, не crash
2. PROGRESSIVE: Feature flags для постепенного включения
3. OBSERVABLE: Логи, метрики, трейсы с первого дня
4. TESTABLE: Каждый модуль с тестами сразу
5. REVERSIBLE: Возможность отката любого изменения
"""

import time
import uuid
from typing import Dict, List, Optional, Any

from classifier import UnifiedClassifier
from state_machine import StateMachine
from generator import ResponseGenerator

# Phase 0: Infrastructure
from logger import logger
from feature_flags import flags
from metrics import ConversationMetrics, ConversationOutcome, DisambiguationMetrics

# Phase 1: Protection and Reliability
from conversation_guard import ConversationGuard
from fallback_handler import FallbackHandler

# Phase 2: Natural Dialogue
from tone_analyzer import ToneAnalyzer

# Phase 3: SPIN Flow Optimization
from lead_scoring import LeadScorer, get_signal_from_intent
from objection_handler import ObjectionHandler
from cta_generator import CTAGenerator
from response_variations import variations

# Context Window for enhanced classification
from context_window import ContextWindow

# Phase 5: Context-aware policy overlays
from dialogue_policy import DialoguePolicy
from context_envelope import build_context_envelope
from response_directives import build_response_directives

# Phase DAG: Modular Flow System & YAML Parameterization
from src.config_loader import ConfigLoader, LoadedConfig, FlowConfig
from settings import settings

# Personalization v2: Adaptive personalization
from src.personalization import EffectiveActionTracker

# Decision Tracing: Full logging of all decision stages
from src.decision_trace import (
    DecisionTrace,
    DecisionTraceBuilder,
    ClassificationTrace,
    ToneAnalysisTrace,
    GuardCheckTrace,
    FallbackTrace,
    LeadScoreTrace,
    ObjectionTrace,
    StateMachineTrace,
    PolicyOverrideTrace,
    ResponseTrace,
    LLMTrace,
    TimingTrace,
    ContextWindowTrace,
    TurnSummary,
)


class SalesBot:
    """
    CRM Sales Bot с полной интеграцией всех компонентов.

    Использует feature flags для постепенного включения функций.
    Все ошибки обрабатываются gracefully без падения бота.
    """

    def __init__(
        self,
        llm,
        conversation_id: Optional[str] = None,
        enable_tracing: bool = False,
        flow_name: Optional[str] = None
    ):
        """
        Инициализация бота со всеми компонентами.

        Args:
            llm: LLM клиент (OllamaLLM или другой)
            conversation_id: Уникальный ID диалога (генерируется если не указан)
            enable_tracing: Включить трассировку условных правил (для симуляций)
            flow_name: Имя flow для загрузки (по умолчанию из settings.flow.active)
        """
        # Генерируем ID диалога для трейсинга
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        logger.set_conversation(self.conversation_id)

        # Phase DAG: Load modular flow configuration (REQUIRED since v2.0)
        # Legacy Python-based config is deprecated and no longer used
        self._config_loader = ConfigLoader()
        self._config: LoadedConfig = self._config_loader.load()

        # Load flow from parameter, settings, or default
        # IMPORTANT: flow_name must be non-empty string to override settings
        active_flow = flow_name if flow_name else settings.flow.active
        self._flow: FlowConfig = self._config_loader.load_flow(active_flow)

        # Log flow resolution for debugging multi-flow scenarios
        logger.info(
            "SalesBot flow resolved",
            requested_flow=flow_name,
            resolved_flow=active_flow,
            flow_name=self._flow.name,
            flow_version=self._flow.version,
            states_count=len(self._flow.states),
            phase_order=self._flow.phase_order,
            entry_state=self._flow.get_entry_point("default"),
        )

        # Validate flow was loaded correctly
        if self._flow.name != active_flow:
            logger.warning(
                "Flow name mismatch",
                requested=active_flow,
                loaded=self._flow.name,
            )

        # Core components (always active)
        self.classifier = UnifiedClassifier()
        self.state_machine = StateMachine(
            enable_tracing=enable_tracing,
            config=self._config,
            flow=self._flow,
        )
        self.generator = ResponseGenerator(llm)
        self.history: List[Dict] = []

        # Context from previous turn
        self.last_action: Optional[str] = None
        self.last_intent: Optional[str] = None

        # Phase 0: Metrics (controlled by feature flag)
        self.metrics = ConversationMetrics(self.conversation_id)

        # Phase 1: Protection (controlled by feature flags)
        self.guard = ConversationGuard()
        self.fallback = FallbackHandler()

        # Phase 2: Natural Dialogue (controlled by feature flags)
        self.tone_analyzer = ToneAnalyzer()

        # Phase 3: SPIN Flow Optimization (controlled by feature flags)
        self.lead_scorer = LeadScorer()
        self.objection_handler = ObjectionHandler()
        self.cta_generator = CTAGenerator()

        # Phase 4: Intent Disambiguation (controlled by feature flag)
        self._disambiguation_ui = None
        self.disambiguation_metrics = DisambiguationMetrics()

        # Phase 5: Context-aware policy overlays (controlled by feature flag)
        self.dialogue_policy = DialoguePolicy(
            shadow_mode=False,  # Применять решения (не только логировать)
            trace_enabled=enable_tracing
        )

        # Context Window: расширенный контекст для классификатора
        # Хранит последние 5 ходов с полной информацией (intent, action, confidence)
        # Pass config for state_order, phase_order from YAML (v2.0)
        self.context_window = ContextWindow(max_size=5, config=self._config)

        # Personalization v2: Session memory for effective actions
        self.action_tracker: Optional[EffectiveActionTracker] = None
        if flags.personalization_session_memory:
            self.action_tracker = EffectiveActionTracker()

        # Decision Tracing: Store traces for each turn
        self._decision_traces: List[DecisionTrace] = []
        self._enable_decision_tracing = enable_tracing

        logger.info(
            "SalesBot initialized",
            conversation_id=self.conversation_id,
            enabled_flags=list(flags.get_enabled_flags()),
            flow_name=self._flow.name,
            flow_version=self._flow.version,
            config_system="modular_yaml",
        )

    def reset(self):
        """Сброс для нового диалога."""
        # Логируем завершение предыдущего диалога
        if self.metrics.turns > 0:
            self._finalize_metrics(ConversationOutcome.ABANDONED)

        # Генерируем новый ID
        self.conversation_id = str(uuid.uuid4())[:8]
        logger.set_conversation(self.conversation_id)

        # Reset core
        self.state_machine.reset()
        self.history = []
        self.last_action = None
        self.last_intent = None

        # Reset Phase 0
        self.metrics = ConversationMetrics(self.conversation_id)

        # Reset Phase 1
        self.guard.reset()
        self.fallback.reset()

        # Reset Phase 2
        self.tone_analyzer.reset()
        variations.reset()

        # Reset Phase 3
        self.lead_scorer.reset()
        self.objection_handler.reset()
        self.cta_generator.reset()

        # Reset Phase 4
        self.disambiguation_metrics = DisambiguationMetrics()

        # Reset Phase 5
        self.dialogue_policy.reset()

        # Reset Context Window
        self.context_window.reset()

        # Reset Personalization v2
        if self.action_tracker:
            self.action_tracker.reset()

        # Reset Decision Traces
        self._decision_traces = []

        logger.info("SalesBot reset", conversation_id=self.conversation_id)

    @property
    def disambiguation_ui(self):
        """Lazy initialization of DisambiguationUI."""
        if self._disambiguation_ui is None:
            from disambiguation_ui import DisambiguationUI
            self._disambiguation_ui = DisambiguationUI()
        return self._disambiguation_ui

    def _get_classification_context(self) -> Dict:
        """
        Получить контекст для классификатора.

        Включает:
        - Базовый контекст (state, spin_phase, missing_data)
        - Расширенный контекст из ContextWindow (история интентов, паттерны)
        """
        # Use YAML flow config as source of truth (v2.0)
        state_config = self._flow.states.get(self.state_machine.state, {})
        required = state_config.get("required_data", [])
        collected = self.state_machine.collected_data

        missing = [f for f in required if not collected.get(f)]
        spin_phase = state_config.get("phase")

        # Базовый контекст
        context = {
            "state": self.state_machine.state,
            "collected_data": collected.copy(),
            "missing_data": missing,
            "spin_phase": spin_phase,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "turns_since_last_disambiguation": self.state_machine.turns_since_last_disambiguation,
        }

        # Добавляем флаг disambiguation если активен
        if self.state_machine.in_disambiguation:
            context["in_disambiguation"] = True

        # =================================================================
        # РАСШИРЕННЫЙ КОНТЕКСТ из ContextWindow (Уровень 1)
        # =================================================================
        # История интентов и actions для детекции паттернов
        context["intent_history"] = self.context_window.get_intent_history()
        context["action_history"] = self.context_window.get_action_history()

        # Счётчики для быстрого доступа
        context["objection_count"] = self.context_window.get_objection_count()
        context["positive_count"] = self.context_window.get_positive_count()
        context["question_count"] = self.context_window.get_question_count()
        context["unclear_count"] = self.context_window.get_unclear_count()

        # Паттерны поведения
        context["has_oscillation"] = self.context_window.detect_oscillation()
        context["is_stuck"] = self.context_window.detect_stuck_pattern()
        context["repeated_question"] = self.context_window.detect_repeated_question()

        # Тренд уверенности
        context["confidence_trend"] = self.context_window.get_confidence_trend()

        return context

    def _analyze_tone(self, user_message: str) -> Dict:
        """
        Анализировать тон сообщения (Phase 2).

        Returns:
            Dict с tone_instruction и guidance
        """
        if not flags.tone_analysis:
            return {
                "tone_instruction": "",
                "style_instruction": "",
                "frustration_level": 0,
                "should_apologize": False,
                "should_offer_exit": False,
            }

        try:
            analysis = self.tone_analyzer.analyze(user_message)
            guidance = self.tone_analyzer.get_response_guidance(analysis)

            # Синхронизируем frustration с ConversationGuard
            if flags.conversation_guard:
                self.guard.set_frustration_level(analysis.frustration_level)

            logger.debug(
                "Tone analyzed",
                tone=analysis.tone.value,
                frustration=analysis.frustration_level,
                style=analysis.style.value
            )

            return {
                "tone_instruction": guidance.get("tone_instruction", ""),
                "style_instruction": guidance.get("style_instruction", ""),
                "frustration_level": analysis.frustration_level,
                "should_apologize": guidance.get("should_apologize", False),
                "should_offer_exit": guidance.get("should_offer_exit", False),
                "max_words": guidance.get("max_words", 50),
                "tone": analysis.tone.value,
                "style": analysis.style.value,
            }
        except Exception as e:
            logger.error("Tone analysis failed", error=str(e))
            return {
                "tone_instruction": "",
                "style_instruction": "",
                "frustration_level": 0,
                "should_apologize": False,
                "should_offer_exit": False,
            }

    def _check_guard(
        self,
        state: str,
        message: str,
        collected_data: Dict,
        frustration_level: int,
        last_intent: str = ""  # BUG-001 FIX: Pass intent for informative check
    ) -> Optional[str]:
        """
        Проверить ConversationGuard (Phase 1).

        Returns:
            None если всё OK, иначе intervention action
        """
        if not flags.conversation_guard:
            return None

        try:
            can_continue, intervention = self.guard.check(
                state=state,
                message=message,
                collected_data=collected_data,
                frustration_level=frustration_level,
                last_intent=last_intent  # BUG-001 FIX: Pass intent for informative check
            )

            if not can_continue:
                logger.warning(
                    "Guard stopped conversation",
                    intervention=intervention,
                    state=state
                )
                return intervention

            if intervention:
                logger.info(
                    "Guard intervention",
                    intervention=intervention,
                    state=state
                )
                return intervention

            return None
        except Exception as e:
            logger.error("Guard check failed", error=str(e))
            return None

    def _apply_fallback(
        self,
        intervention: str,
        state: str,
        context: Dict
    ) -> Dict:
        """
        Применить fallback response (Phase 1).

        Returns:
            Dict с response и опциональным next_state
        """
        if not flags.multi_tier_fallback:
            return {"response": None, "next_state": None}

        try:
            fallback_response = self.fallback.get_fallback(
                tier=intervention,
                state=state,
                context=context
            )

            # NOTE: Метрика fallback записывается централизованно в record_turn()
            # через параметры fallback_used/fallback_tier, поэтому здесь НЕ вызываем
            # record_fallback() чтобы избежать двойного подсчёта.

            logger.info(
                "Fallback applied",
                tier=intervention,
                action=fallback_response.action
            )

            return {
                "response": fallback_response.message,
                "options": fallback_response.options,
                "action": fallback_response.action,
                "next_state": fallback_response.next_state,
            }
        except Exception as e:
            logger.error("Fallback application failed", error=str(e))
            return {"response": None, "next_state": None}

    def _check_objection(self, user_message: str, collected_data: Dict) -> Optional[Dict]:
        """
        Проверить и обработать возражение (Phase 3).

        Returns:
            None если нет возражения, иначе Dict с стратегией
        """
        if not flags.objection_handler:
            return None

        try:
            result = self.objection_handler.handle_objection(
                message=user_message,
                collected_data=collected_data
            )

            if result.objection_type is None:
                return None

            # Записываем в метрики
            if flags.metrics_tracking:
                self.metrics.record_objection(
                    objection_type=result.objection_type.value,
                    resolved=not result.should_soft_close
                )

            logger.info(
                "Objection handled",
                type=result.objection_type.value,
                attempt=result.attempt_number,
                soft_close=result.should_soft_close
            )

            return {
                "objection_type": result.objection_type.value,
                "strategy": result.strategy,
                "should_soft_close": result.should_soft_close,
                "response_parts": result.response_parts,
            }
        except Exception as e:
            logger.error("Objection handling failed", error=str(e))
            return None

    def _extract_competitor_name(self, message: str) -> Optional[str]:
        """Extract competitor name from message."""
        competitors = {
            "Битрикс": ["битрикс", "bitrix", "bitrix24"],
            "AmoCRM": ["амо", "amocrm", "amo crm", "амосрм"],
            "iiko": ["iiko", "ийко", "айко"],
            "Poster": ["poster", "постер"],
            "1С": ["1с", "1c", "1с:crm"],
            "Мегаплан": ["мегаплан", "megaplan"],
            "R-Keeper": ["r-keeper", "r_keeper", "ркипер"],
        }
        msg_lower = message.lower()
        for display_name, patterns in competitors.items():
            if any(p in msg_lower for p in patterns):
                return display_name
        return None

    def _update_lead_score(self, intent: str) -> None:
        """Обновить lead score на основе интента (Phase 3)."""
        if not flags.lead_scoring:
            return

        try:
            signal = get_signal_from_intent(intent)
            if signal:
                score = self.lead_scorer.add_signal(signal)

                if flags.metrics_tracking:
                    self.metrics.record_lead_score(
                        score=score.score,
                        temperature=score.temperature.value,
                        signal=signal
                    )

                logger.debug(
                    "Lead score updated",
                    signal=signal,
                    score=score.score,
                    temperature=score.temperature.value
                )
        except Exception as e:
            logger.error("Lead scoring failed", error=str(e))

    def _apply_cta(
        self,
        response: str,
        state: str,
        context: Dict
    ) -> str:
        """Добавить CTA к ответу если уместно (Phase 3)."""
        if not flags.cta_generator:
            return response

        try:
            self.cta_generator.increment_turn()
            result = self.cta_generator.append_cta(response, state, context)
            return result
        except Exception as e:
            logger.error("CTA generation failed", error=str(e))
            return response

    def _record_turn_metrics(
        self,
        state: str,
        intent: str,
        tone: Optional[str],
        fallback_used: bool,
        fallback_tier: Optional[str]
    ) -> None:
        """Записать метрики хода (Phase 0)."""
        if not flags.metrics_tracking:
            return

        try:
            self.metrics.record_turn(
                state=state,
                intent=intent,
                tone=tone,
                fallback_used=fallback_used,
                fallback_tier=fallback_tier
            )
        except Exception as e:
            logger.error("Metrics recording failed", error=str(e))

    def _finalize_metrics(self, outcome: ConversationOutcome) -> None:
        """Финализировать метрики диалога."""
        if not flags.metrics_tracking:
            return

        try:
            self.metrics.set_outcome(outcome)
            summary = self.metrics.to_log_dict()

            logger.info(
                "Conversation finished",
                **summary
            )
        except Exception as e:
            logger.error("Metrics finalization failed", error=str(e))

    def process(self, user_message: str) -> Dict:
        """
        Обработать сообщение клиента.

        Полный pipeline с интеграцией всех компонентов:
        1. Start metrics timer
        2. Analyze tone (Phase 2)
        3. Check guard (Phase 1)
        4. Classify intent
        5. Check objection (Phase 3)
        6. Update lead score (Phase 3)
        7. Run state machine
        8. Generate response
        9. Apply CTA (Phase 3)
        10. Record metrics (Phase 0)

        Args:
            user_message: Сообщение от клиента

        Returns:
            Dict с response, intent, action, state, is_final и др.
        """
        # Decision Tracing: Create trace builder for this turn
        trace_builder: Optional[DecisionTraceBuilder] = None
        if self._enable_decision_tracing:
            trace_builder = DecisionTraceBuilder(turn=self.turn + 1, message=user_message)

        # Phase 4: Increment turn counter for disambiguation cooldown
        self.state_machine.increment_turn()

        # Phase 3: Reset turn decay flag and apply turn-based decay to lead score
        # Это обеспечивает "затухание" старых сигналов даже без новых сигналов
        if flags.lead_scoring:
            self.lead_scorer.end_turn()  # Сброс флага от предыдущего хода
            self.lead_scorer.apply_turn_decay()

        # Start metrics timer
        if flags.metrics_tracking:
            self.metrics.start_turn_timer()

        # =================================================================
        # Phase 4: Handle disambiguation response if in disambiguation mode
        # =================================================================
        if self.state_machine.in_disambiguation:
            return self._handle_disambiguation_response(user_message)

        # Get current context
        current_context = self._get_classification_context()
        current_state = self.state_machine.state
        collected_data = self.state_machine.collected_data

        # Phase 2: Analyze tone
        tone_start = time.time()
        tone_info = self._analyze_tone(user_message)
        frustration_level = tone_info.get("frustration_level", 0)
        tone_elapsed = (time.time() - tone_start) * 1000

        # Decision Tracing: Record tone analysis
        if trace_builder:
            trace_builder.record_tone(tone_info, elapsed_ms=tone_elapsed)

        # Phase 1: Check guard for intervention
        guard_start = time.time()
        intervention = self._check_guard(
            state=current_state,
            message=user_message,
            collected_data=collected_data,
            frustration_level=frustration_level,
            last_intent=self.last_intent  # BUG-001 FIX: Pass intent for informative check
        )
        guard_elapsed = (time.time() - guard_start) * 1000

        # Decision Tracing: Record guard check
        if trace_builder:
            trace_builder.record_guard(
                intervention=intervention,
                frustration=frustration_level,
                elapsed_ms=guard_elapsed
            )

        fallback_used = False
        fallback_tier = None
        fallback_response = None

        if intervention:
            fallback_used = True
            fallback_tier = intervention

            # Apply fallback
            fb_result = self._apply_fallback(
                intervention=intervention,
                state=current_state,
                context={
                    "collected_data": collected_data,
                    "last_intent": self.last_intent,
                    "last_action": self.last_action,
                    "frustration_level": frustration_level,
                }
            )

            if fb_result.get("response"):
                fallback_response = fb_result

                # If fallback action is "close" or "skip", update state
                if fb_result.get("action") == "close":
                    self._record_turn_metrics(
                        state=current_state,
                        intent="fallback_close",
                        tone=tone_info.get("tone"),
                        fallback_used=True,
                        fallback_tier=intervention
                    )

                    self.history.append({
                        "user": user_message,
                        "bot": fb_result["response"]
                    })

                    self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)

                    return {
                        "response": fb_result["response"],
                        "intent": "fallback_close",
                        "action": "soft_close",
                        "state": "soft_close",
                        "is_final": True,
                        "fallback_used": True,
                        "fallback_tier": intervention,
                        "options": fb_result.get("options"),
                    }

                # FIX: Handle "skip" action - apply state transition to break loops
                elif fb_result.get("action") == "skip" and fb_result.get("next_state"):
                    skip_next_state = fb_result["next_state"]
                    self.state_machine.state = skip_next_state
                    logger.info(
                        "Fallback skip applied - resetting fallback for normal generation",
                        from_state=current_state,
                        to_state=skip_next_state,
                        original_tier=intervention
                    )
                    # Update current_state for rest of processing
                    current_state = skip_next_state
                    # ✅ FIX BUG-001: Сбрасываем fallback_response чтобы сгенерировать
                    # нормальный ответ вместо tier_3 шаблона
                    fallback_response = None

        # 1. Classify intent
        classification_start = time.time()
        classification = self.classifier.classify(user_message, current_context)
        intent = classification["intent"]
        extracted = classification["extracted_data"]
        classification_elapsed = (time.time() - classification_start) * 1000

        # Decision Tracing: Record classification
        if trace_builder:
            trace_builder.record_classification(
                result=classification,
                all_scores=classification.get("all_scores", {intent: classification.get("confidence", 0.0)}),
                elapsed_ms=classification_elapsed,
            )

        # Track competitor mention for dynamic CTA
        if intent == "objection_competitor":
            self.state_machine.collected_data["competitor_mentioned"] = True
            competitor_name = self._extract_competitor_name(user_message)
            if competitor_name:
                self.state_machine.collected_data["competitor_name"] = competitor_name

        # =================================================================
        # Phase 4: Handle disambiguation_needed intent
        # =================================================================
        if intent == "disambiguation_needed":
            options = classification.get("disambiguation_options", [])
            if not options:
                # Fallback to original intent if no options
                intent = classification.get("original_intent", "unclear")
                classification["intent"] = intent
            else:
                return self._initiate_disambiguation(
                    classification=classification,
                    user_message=user_message,
                    context=current_context,
                    tone_info=tone_info
                )

        # Phase 3: Check for objection
        objection_info = self._check_objection(user_message, collected_data)

        # Decision Tracing: Record objection
        if trace_builder and objection_info:
            trace_builder.record_objection(
                detected=True,
                objection_type=objection_info.get("objection_type"),
                strategy=objection_info.get("strategy"),
                soft_close=objection_info.get("should_soft_close", False),
            )

        # Phase 3: Update lead score
        prev_lead_score = self.lead_scorer.current_score if flags.lead_scoring else 0
        self._update_lead_score(intent)
        new_lead_score = self.lead_scorer.current_score if flags.lead_scoring else 0

        # Decision Tracing: Record lead score
        if trace_builder and flags.lead_scoring:
            trace_builder.record_lead_score(
                previous=prev_lead_score,
                new=new_lead_score,
                signals=self.lead_scorer.get_recent_signals() if hasattr(self.lead_scorer, 'get_recent_signals') else [],
                temperature=self.lead_scorer.get_summary().get("temperature", "cold"),
            )

        # =================================================================
        # Phase 5: Build ContextEnvelope for context-aware decisions
        # =================================================================
        context_envelope = None
        if flags.context_full_envelope or flags.context_policy_overlays:
            context_envelope = build_context_envelope(
                state_machine=self.state_machine,
                context_window=self.context_window,
                tone_info=tone_info,
                guard_info={"intervention": intervention} if intervention else None,
                last_action=self.last_action,
                last_intent=self.last_intent,
            )

        # Build ResponseDirectives if flag enabled
        response_directives = None
        if flags.context_response_directives and context_envelope:
            response_directives = build_response_directives(context_envelope)

        # 2. Run state machine with context envelope
        sm_start = time.time()
        sm_result = self.state_machine.process(
            intent, extracted, context_envelope=context_envelope
        )
        sm_elapsed = (time.time() - sm_start) * 1000

        # Decision Tracing: Record state machine result
        if trace_builder:
            trace_builder.record_state_machine(sm_result, elapsed_ms=sm_elapsed)

        # =================================================================
        # Phase 5: Apply DialoguePolicy overlay if enabled
        # =================================================================
        policy_override = None
        if flags.context_policy_overlays:
            policy_override = self.dialogue_policy.maybe_override(sm_result, context_envelope)
        if policy_override and policy_override.has_override:
            logger.info(
                "DialoguePolicy override applied",
                original_action=sm_result["action"],
                override_action=policy_override.action,
                reason_codes=policy_override.reason_codes,
                decision=policy_override.decision.value,
            )
            # Apply the override
            if policy_override.action:
                sm_result["action"] = policy_override.action
            if policy_override.next_state:
                # Validate: next_state without action is inconsistent
                if not policy_override.action:
                    logger.warning(
                        "PolicyOverride has next_state without action - skipping next_state",
                        next_state=policy_override.next_state,
                        decision=policy_override.decision.value,
                    )
                else:
                    sm_result["next_state"] = policy_override.next_state
                    self.state_machine.state = policy_override.next_state

        # Decision Tracing: Record policy override
        if trace_builder:
            trace_builder.record_policy_override(policy_override)

        # Build context for response generation
        # При наличии ResponseDirectives используем их instruction
        directive_instruction = ""
        if response_directives:
            directive_instruction = response_directives.get_instruction()

        context = {
            "user_message": user_message,
            "intent": intent,
            "state": sm_result["next_state"],
            "history": self.history,
            "goal": sm_result["goal"],
            "collected_data": sm_result["collected_data"],
            "missing_data": sm_result["missing_data"],
            "spin_phase": sm_result.get("spin_phase"),
            "optional_data": sm_result.get("optional_data", []),
            # Phase 2: Tone and style instructions
            # ResponseDirectives instruction имеет приоритет если доступен
            "tone_instruction": directive_instruction or tone_info.get("tone_instruction", ""),
            "style_instruction": tone_info.get("style_instruction", ""),
            "frustration_level": frustration_level,
            "should_apologize": tone_info.get("should_apologize", False),
            "should_offer_exit": tone_info.get("should_offer_exit", False),
            # Phase 3: Objection info
            "objection_info": objection_info,
            # For CTA
            "last_action": self.last_action,
            # Phase 5: Policy reason codes for generator
            "policy_reason_codes": policy_override.reason_codes if policy_override else [],
            # Personalization v2: Context envelope and action tracker
            "context_envelope": context_envelope,
            "action_tracker": self.action_tracker,
            "user_messages": [turn.get("user", "") for turn in self.history[-5:]] + [user_message],
            # Phase 2: ResponseDirectives для generator
            "response_directives": response_directives,
        }

        # Determine action
        action = sm_result["action"]
        next_state = sm_result["next_state"]
        is_final = sm_result["is_final"]

        # If objection detected and needs soft close - override state machine result
        if objection_info and objection_info.get("should_soft_close"):
            action = "soft_close"
            next_state = "soft_close"  # Синхронизируем состояние с action
            is_final = True  # soft_close - финальное состояние
            # Безопасный доступ к response_parts с fallback
            response_parts = objection_info.get("response_parts") or {}
            response = response_parts.get("message") or "Хорошо, свяжитесь когда будет удобно."
            logger.info(
                "Soft close triggered by objection handler",
                objection_type=objection_info.get("objection_type"),
                attempt_number=objection_info.get("attempt_number")
            )
        else:
            # 3. Generate response
            response_start = time.time()
            if fallback_response:
                response = fallback_response["response"]
            else:
                response = self.generator.generate(action, context)
            response_elapsed = (time.time() - response_start) * 1000

            # Decision Tracing: Record response generation
            if trace_builder:
                trace_builder.record_response(
                    template_key=action,
                    response_text=response,
                    elapsed_ms=response_elapsed,
                )

        # Phase 3: Apply CTA if appropriate
        if not fallback_response and not (objection_info and objection_info.get("should_soft_close")):
            response = self._apply_cta(
                response=response,
                state=next_state,  # Используем локальную переменную
                context={
                    "frustration_level": frustration_level,
                    "last_action": self.last_action,
                }
            )

        # 4. Save to history
        self.history.append({
            "user": user_message,
            "bot": response
        })

        # 4.1 Save to context window (расширенный контекст)
        self.context_window.add_turn_from_dict(
            user_message=user_message,
            bot_response=response,
            intent=intent,
            confidence=classification.get("confidence", 0.0),
            action=action,
            state=current_state,
            next_state=next_state,
            method=classification.get("method", "unknown"),
            extracted_data=extracted,
            is_fallback=fallback_used,
            fallback_tier=fallback_tier,
        )

        # 4.2 Record action outcome for personalization v2
        if self.action_tracker and self.last_action:
            # Получаем turn_type из context_window
            turn_type = "NEUTRAL"
            if hasattr(self.context_window, 'get_last_turn_type'):
                turn_type = self.context_window.get_last_turn_type() or "NEUTRAL"
            self.action_tracker.record_outcome(
                action=self.last_action,
                turn_type=turn_type,
                intent=intent,
            )

        # 5. Save context for next turn
        self.last_action = action
        self.last_intent = intent

        # 6. Record metrics
        self._record_turn_metrics(
            state=next_state,  # Используем локальную переменную
            intent=intent,
            tone=tone_info.get("tone"),
            fallback_used=fallback_used,
            fallback_tier=fallback_tier
        )

        # Record collected data in metrics
        if flags.metrics_tracking:
            for key, value in extracted.items():
                if value:
                    self.metrics.record_collected_data(key, value)

        # =================================================================
        # КРИТИЧЕСКИЙ FIX: Улучшенная логика определения успешного завершения
        # =================================================================
        # Проблема: is_final = True только для state с is_final: True (success)
        # Но диалог может успешно завершиться и в других состояниях:
        # - close с demo_request/agreement → переход в success
        # - soft_close с demo_request → переход в close
        #
        # Решение: Проверяем не только is_final, но и:
        # 1. next_state == "success" (явный успех)
        # 2. Наличие ключевых интентов в истории для определения типа успеха
        # =================================================================

        # Определяем успешное завершение
        is_success = is_final or next_state == "success"

        if is_success:
            # Определяем тип успеха по приоритету
            if intent == "rejection":
                self._finalize_metrics(ConversationOutcome.REJECTED)
            elif "contact_provided" in self.metrics.intents_sequence:
                # Контакт предоставлен — полный успех
                self._finalize_metrics(ConversationOutcome.SUCCESS)
            elif intent == "contact_provided":
                # Текущий интент — контакт
                self._finalize_metrics(ConversationOutcome.SUCCESS)
            elif "demo_request" in self.metrics.intents_sequence or intent == "demo_request":
                # Демо-запрос — успешное назначение демо
                self._finalize_metrics(ConversationOutcome.DEMO_SCHEDULED)
            elif intent == "agreement" and sm_result.get("prev_state") == "close":
                # Согласие в close фазе — считаем успехом
                self._finalize_metrics(ConversationOutcome.DEMO_SCHEDULED)
            elif intent in ("callback_request", "consultation_request"):
                # Запрос колбека/консультации — успех
                self._finalize_metrics(ConversationOutcome.DEMO_SCHEDULED)
            else:
                self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)

        # Record progress if state changed or data collected
        if sm_result["prev_state"] != next_state or extracted:
            self.guard.record_progress()

        # Decision Tracing: Build and store final trace
        decision_trace_dict = None
        if trace_builder:
            # Record fallback if used
            if fallback_used:
                trace_builder.record_fallback(
                    tier=fallback_tier,
                    reason=intervention,
                )

            # Build final trace
            decision_trace = trace_builder.build()
            self._decision_traces.append(decision_trace)
            decision_trace_dict = decision_trace.to_dict()

        return {
            "response": response,
            "intent": intent,
            "action": action,
            "state": next_state,  # Используем локальную переменную
            "is_final": is_final,
            "spin_phase": sm_result.get("spin_phase"),
            # Additional info
            "fallback_used": fallback_used,
            "fallback_tier": fallback_tier,
            "tone": tone_info.get("tone"),
            "frustration_level": frustration_level,
            "lead_score": self.lead_scorer.current_score if flags.lead_scoring else None,
            "objection_detected": objection_info is not None,
            "options": fallback_response.get("options") if fallback_response else None,
            # Decision Tracing
            "decision_trace": decision_trace_dict,
        }

    def get_metrics_summary(self) -> Dict:
        """Получить сводку метрик текущего диалога."""
        if flags.metrics_tracking:
            return self.metrics.get_summary()
        return {}

    def get_lead_score(self) -> Dict:
        """Получить текущий lead score."""
        if flags.lead_scoring:
            return self.lead_scorer.get_summary()
        return {}

    def get_guard_stats(self) -> Dict:
        """Получить статистику ConversationGuard."""
        if flags.conversation_guard:
            return self.guard.get_stats()
        return {}

    def get_disambiguation_metrics(self) -> Dict:
        """Получить метрики disambiguation."""
        return self.disambiguation_metrics.get_summary()

    def get_decision_traces(self) -> List[DecisionTrace]:
        """Получить все трейсы решений."""
        return self._decision_traces

    def get_last_decision_trace(self) -> Optional[DecisionTrace]:
        """Получить последний трейс решений."""
        return self._decision_traces[-1] if self._decision_traces else None

    @property
    def turn(self) -> int:
        """Текущий номер хода."""
        return len(self.history)

    # =========================================================================
    # Phase 4: Disambiguation Methods
    # =========================================================================

    def _initiate_disambiguation(
        self,
        classification: Dict,
        user_message: str,
        context: Dict,
        tone_info: Dict
    ) -> Dict:
        """
        Инициировать режим disambiguation.

        Args:
            classification: Результат классификации с disambiguation_options
            user_message: Исходное сообщение пользователя
            context: Текущий контекст
            tone_info: Информация о тоне

        Returns:
            Dict с ответом disambiguation
        """
        options = classification["disambiguation_options"]
        question = classification.get("disambiguation_question", "")
        extracted_data = classification.get("extracted_data", {})

        # Входим в режим disambiguation
        self.state_machine.enter_disambiguation(
            options=options,
            extracted_data=extracted_data
        )

        # Форматируем вопрос пользователю
        response = self.disambiguation_ui.format_question(
            question=question,
            options=options,
            context={
                **context,
                "frustration_level": tone_info.get("frustration_level", 0)
            }
        )

        # Сохраняем в историю
        self.history.append({
            "user": user_message,
            "bot": response,
            "disambiguation": True,
        })

        # Записываем метрики
        self.disambiguation_metrics.record_disambiguation(
            options=[o["intent"] for o in options],
            scores=classification.get("original_scores", {})
        )

        # Логируем
        logger.info(
            "Disambiguation triggered",
            options=[o["intent"] for o in options],
            top_confidence=classification.get("confidence"),
            original_intent=classification.get("original_intent")
        )

        return {
            "response": response,
            "intent": "disambiguation_needed",
            "action": "ask_clarification",
            "state": self.state_machine.state,
            "is_final": False,
            "disambiguation_options": options,
        }

    def _handle_disambiguation_response(self, user_message: str) -> Dict:
        """
        Обработать ответ пользователя в режиме disambiguation.

        Args:
            user_message: Ответ пользователя

        Returns:
            Dict с результатом обработки
        """
        context = self.state_machine.disambiguation_context
        if not context:
            # Guard: если контекста нет, выходим из disambiguation
            self.state_machine.exit_disambiguation()
            logger.warning("Disambiguation context is None, exiting")
            return self._continue_with_classification(
                classification={
                    "intent": "unclear",
                    "confidence": 0.3,
                    "extracted_data": {},
                    "method": "disambiguation_error"
                },
                user_message=user_message  # Передаём сообщение пользователя
            )

        options = context["options"]
        extracted_data = context.get("extracted_data", {})
        attempt = context.get("attempt", 1)

        # Сначала проверяем критические интенты (контакт, отказ, демо)
        # Они имеют приоритет над disambiguation
        current_context = self._get_classification_context()
        current_context["in_disambiguation"] = True

        quick_check = self.classifier.classify(user_message, current_context)

        if quick_check["intent"] in ["contact_provided", "rejection", "demo_request"]:
            # Критический интент - выходим из disambiguation и обрабатываем
            self.state_machine.exit_disambiguation()
            merged_extracted = {**extracted_data, **quick_check.get("extracted_data", {})}
            quick_check["extracted_data"] = merged_extracted

            logger.info(
                "Disambiguation interrupted by critical intent",
                intent=quick_check["intent"]
            )

            return self._continue_with_classification(
                classification=quick_check,
                user_message=user_message
            )

        # Пробуем распознать ответ на disambiguation
        resolved_intent = self.disambiguation_ui.parse_answer(
            answer=user_message,
            options=options
        )

        # Проверяем, выбрал ли пользователь "свой вариант" или написал что-то нераспознанное
        from disambiguation_ui import DisambiguationUI
        is_custom_input = (
            resolved_intent == DisambiguationUI.CUSTOM_INPUT_MARKER
            or resolved_intent is None
        )

        if is_custom_input:
            # Пользователь ввёл свой вариант - классифицируем его сообщение напрямую
            self.state_machine.exit_disambiguation()

            self.disambiguation_metrics.record_resolution(
                resolved_intent="custom_input",
                attempt=attempt,
                success=True
            )

            logger.info(
                "Disambiguation: user provided custom input, classifying",
                attempt=attempt,
                user_message=user_message
            )

            # Классифицируем сообщение пользователя напрямую
            new_classification = self.classifier.classify(user_message, current_context)
            merged_extracted = {**extracted_data, **new_classification.get("extracted_data", {})}
            new_classification["extracted_data"] = merged_extracted

            return self._continue_with_classification(
                classification=new_classification,
                user_message=user_message
            )

        # Успешно распознали ответ как одну из опций
        current_state, intent = self.state_machine.resolve_disambiguation(resolved_intent)

        self.disambiguation_metrics.record_resolution(
            resolved_intent=resolved_intent,
            attempt=attempt,
            success=True
        )

        logger.info(
            "Disambiguation resolved",
            resolved_intent=resolved_intent,
            attempt=attempt
        )

        return self._continue_with_classification(
            classification={
                "intent": resolved_intent,
                "confidence": 0.9,
                "extracted_data": extracted_data,
                "method": "disambiguation_resolved"
            },
            user_message=user_message
        )

    def _continue_with_classification(
        self,
        classification: Dict,
        user_message: str = ""
    ) -> Dict:
        """
        Продолжить обработку с заданной классификацией.

        Включает все фазы защиты:
        - Phase 1: Guard check
        - Phase 2: Tone analysis
        - Phase 3: Objection handling
        - Phase 5: Policy overlay

        Args:
            classification: Результат классификации
            user_message: Сообщение пользователя (для истории)

        Returns:
            Dict с результатом обработки
        """
        intent = classification["intent"]
        extracted = classification.get("extracted_data", {})
        confidence = classification.get("confidence", 0.5)

        current_state = self.state_machine.state
        collected_data = self.state_machine.collected_data

        # =================================================================
        # Phase 2: Analyze tone (важно для frustration и guidance)
        # =================================================================
        tone_info = self._analyze_tone(user_message) if user_message else {
            "tone_instruction": "",
            "style_instruction": "",
            "frustration_level": 0,
            "should_apologize": False,
            "should_offer_exit": False,
        }
        frustration_level = tone_info.get("frustration_level", 0)

        # =================================================================
        # Phase 1: Check guard for intervention
        # =================================================================
        intervention = self._check_guard(
            state=current_state,
            message=user_message,
            collected_data=collected_data,
            frustration_level=frustration_level,
            last_intent=self.last_intent  # BUG-001 FIX: Pass intent for informative check
        ) if user_message else None

        fallback_used = False
        fallback_tier = None

        if intervention:
            fallback_used = True
            fallback_tier = intervention

            fb_result = self._apply_fallback(
                intervention=intervention,
                state=current_state,
                context={
                    "collected_data": collected_data,
                    "last_intent": self.last_intent,
                    "last_action": self.last_action,
                    "frustration_level": frustration_level,
                }
            )

            if fb_result.get("response") and fb_result.get("action") == "close":
                self._record_turn_metrics(
                    state=current_state,
                    intent="fallback_close",
                    tone=tone_info.get("tone"),
                    fallback_used=True,
                    fallback_tier=intervention
                )

                self.history.append({
                    "user": user_message,
                    "bot": fb_result["response"]
                })

                self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)

                return {
                    "response": fb_result["response"],
                    "intent": "fallback_close",
                    "action": "soft_close",
                    "state": "soft_close",
                    "is_final": True,
                    "fallback_used": True,
                    "fallback_tier": intervention,
                }

        # =================================================================
        # Phase 3: Check for objection
        # =================================================================
        objection_info = self._check_objection(user_message, collected_data) if user_message else None

        # Обновляем собранные данные
        if extracted:
            self.state_machine.update_data(extracted)

        # Обрабатываем через state machine
        sm_result = self.state_machine.process(intent, extracted)

        # =================================================================
        # Phase 5: Build ContextEnvelope for policy overlay
        # =================================================================
        context_envelope = None
        if flags.context_full_envelope or flags.context_policy_overlays:
            context_envelope = build_context_envelope(
                state_machine=self.state_machine,
                context_window=self.context_window,
                tone_info=tone_info,
                guard_info={"intervention": intervention} if intervention else None,
                last_action=self.last_action,
                last_intent=self.last_intent,
            )

        # Build ResponseDirectives if flag enabled
        response_directives = None
        if flags.context_response_directives and context_envelope:
            response_directives = build_response_directives(context_envelope)

        # Phase 5: Apply dialogue policy overlays
        if flags.context_policy_overlays and context_envelope:
            override = self.dialogue_policy.maybe_override(sm_result, context_envelope)
            if override and override.has_override:
                logger.info(
                    "Policy override applied (disambiguation path)",
                    original_action=sm_result["action"],
                    override_action=override.action,
                    reason=override.reason
                )
                sm_result["action"] = override.action
                if override.next_state:
                    sm_result["next_state"] = override.next_state

        # Контекст для генерации ответа
        # При наличии ResponseDirectives используем их instruction
        directive_instruction = ""
        if response_directives:
            directive_instruction = response_directives.get_instruction()

        context = {
            "user_message": user_message,
            "intent": intent,
            "state": sm_result["next_state"],
            "history": self.history,
            "goal": sm_result["goal"],
            "collected_data": sm_result["collected_data"],
            "missing_data": sm_result["missing_data"],
            "spin_phase": sm_result.get("spin_phase"),
            "optional_data": sm_result.get("optional_data", []),
            # Phase 2: Tone and style guidance
            # ResponseDirectives instruction имеет приоритет если доступен
            "tone_instruction": directive_instruction or tone_info.get("tone_instruction", ""),
            "style_instruction": tone_info.get("style_instruction", ""),
            "should_apologize": tone_info.get("should_apologize", False),
            "should_offer_exit": tone_info.get("should_offer_exit", False),
            "max_words": tone_info.get("max_words", 50),
            # Phase 3: Objection info
            "objection_info": objection_info,
            # Phase 2: ResponseDirectives для generator
            "response_directives": response_directives,
        }

        action = sm_result["action"]
        response = self.generator.generate(action, context)

        # Сохраняем в историю (с реальным сообщением пользователя)
        self.history.append({
            "user": user_message,  # Сохраняем ответ пользователя на disambiguation
            "bot": response,
            "intent": intent,
            "action": action,
        })

        # Сохраняем в context_window (для синхронизации с history)
        self.context_window.add_turn_from_dict(
            user_message=user_message,
            bot_response=response,
            intent=intent,
            confidence=confidence,
            action=action,
            state=current_state,
            next_state=sm_result["next_state"],
            method=classification.get("method", "disambiguation_resolved"),
            extracted_data=extracted,
            is_fallback=fallback_used,
            fallback_tier=fallback_tier,
        )

        # Обновляем контекст
        self.last_action = action
        self.last_intent = intent

        # Записываем метрики (с информацией о тоне и fallback)
        self._record_turn_metrics(
            state=sm_result["next_state"],
            intent=intent,
            tone=tone_info.get("tone"),
            fallback_used=fallback_used,
            fallback_tier=fallback_tier
        )

        # Проверяем финальное состояние
        is_final = sm_result["is_final"]
        if is_final:
            if intent == "rejection":
                self._finalize_metrics(ConversationOutcome.REJECTED)
            elif "contact_provided" in self.metrics.intents_sequence:
                self._finalize_metrics(ConversationOutcome.SUCCESS)
            elif "demo_request" in self.metrics.intents_sequence:
                self._finalize_metrics(ConversationOutcome.DEMO_SCHEDULED)
            else:
                self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)

        return {
            "response": response,
            "intent": intent,
            "confidence": confidence,
            "action": action,
            "state": sm_result["next_state"],
            "extracted_data": extracted,
            "is_final": is_final,
            "spin_phase": sm_result.get("spin_phase"),
        }

    def _fallback_from_disambiguation(self, user_message: str = "") -> Dict:
        """
        Выйти из disambiguation с fallback на unclear.

        Args:
            user_message: Последнее сообщение пользователя (для истории)

        Returns:
            Dict с результатом
        """
        context = self.state_machine.disambiguation_context
        extracted_data = context.get("extracted_data", {}) if context else {}
        attempt = context.get("attempt", 0) if context else 0

        self.disambiguation_metrics.record_resolution(
            resolved_intent="unclear",
            attempt=attempt,
            success=False
        )

        logger.warning(
            "Disambiguation failed, falling back to unclear",
            attempts=attempt
        )

        self.state_machine.exit_disambiguation()

        return self._continue_with_classification(
            classification={
                "intent": "unclear",
                "confidence": 0.3,
                "extracted_data": extracted_data,
                "method": "disambiguation_fallback"
            },
            user_message=user_message
        )

    def _repeat_disambiguation_question(self, context: Dict) -> Dict:
        """
        Повторить вопрос disambiguation.

        Args:
            context: Контекст disambiguation

        Returns:
            Dict с повторным вопросом
        """
        options = context["options"]
        response = self.disambiguation_ui.format_repeat_question(options)

        logger.info(
            "Disambiguation repeat",
            attempt=context.get("attempt", 2)
        )

        return {
            "response": response,
            "intent": "disambiguation_needed",
            "action": "repeat_clarification",
            "state": self.state_machine.state,
            "is_final": False,
        }


def run_interactive(bot: SalesBot):
    """Интерактивный режим для тестирования."""
    print("\n" + "=" * 60)
    print("CRM Sales Bot (Phase 4 Integration)")
    print("Команды: /reset /status /metrics /lead /flags /quit")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("Клиент: ").strip()

            if not user_input:
                continue

            if user_input == "/quit":
                break

            if user_input == "/reset":
                bot.reset()
                print("[Диалог сброшен]\n")
                continue

            if user_input == "/status":
                sm = bot.state_machine
                print(f"\nСостояние: {sm.state}")
                print(f"Данные: {sm.collected_data}")
                print(f"Guard: {bot.get_guard_stats()}\n")
                continue

            if user_input == "/metrics":
                print(f"\nМетрики: {bot.get_metrics_summary()}\n")
                continue

            if user_input == "/lead":
                print(f"\nLead Score: {bot.get_lead_score()}\n")
                continue

            if user_input == "/flags":
                print(f"\nEnabled flags: {list(flags.get_enabled_flags())}\n")
                continue

            result = bot.process(user_input)

            print(f"Бот: {result['response']}")

            # Status line
            status_parts = [f"[{result['state']}]", result['action']]
            if result.get('spin_phase'):
                status_parts.append(f"SPIN:{result['spin_phase']}")
            if result.get('fallback_used'):
                status_parts.append(f"FB:{result['fallback_tier']}")
            if result.get('tone'):
                status_parts.append(f"Tone:{result['tone']}")
            if result.get('lead_score') is not None:
                status_parts.append(f"Score:{result['lead_score']}")

            print(f"  {' | '.join(status_parts)}\n")

            if result.get("options"):
                print(f"  Варианты: {result['options']}\n")

            if result["is_final"]:
                print("[Диалог завершён]")
                if input("Новый диалог? (y/n): ").lower() == 'y':
                    bot.reset()
                else:
                    break

        except KeyboardInterrupt:
            print("\n\nПока!")
            break


if __name__ == "__main__":
    from llm import OllamaLLM

    # Enable all flags for testing
    flags.enable_group("phase_0")
    flags.enable_group("phase_1")
    flags.enable_group("phase_2")
    flags.enable_group("phase_3")

    llm = OllamaLLM()
    bot = SalesBot(llm)

    run_interactive(bot)
