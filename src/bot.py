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
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from src.classifier import UnifiedClassifier
from src.state_machine import StateMachine
from src.generator import ResponseGenerator

# Phase 0: Infrastructure
from src.logger import logger
from src.feature_flags import flags
from src.metrics import ConversationMetrics, ConversationOutcome, DisambiguationMetrics

# Phase 1: Protection and Reliability
from src.conversation_guard import ConversationGuard
from src.fallback_handler import FallbackHandler

# Phase 2: Natural Dialogue
from src.tone_analyzer import ToneAnalyzer

# Phase 3: SPIN Flow Optimization
from src.lead_scoring import LeadScorer, get_signal_from_intent
from src.objection_handler import ObjectionHandler
from src.cta_generator import CTAGenerator, CTAResult
from src.response_variations import variations

# Context Window for enhanced classification
from src.context_window import ContextWindow

# Robust Classification: ConfidenceRouter for graceful degradation
from src.classifier.confidence_router import ConfidenceRouter

# Phase 5: Context-aware policy overlays
from src.dialogue_policy import DialoguePolicy
from src.context_envelope import build_context_envelope
from src.response_directives import build_response_directives

# Phase DAG: Modular Flow System & YAML Parameterization
from src.config_loader import ConfigLoader, LoadedConfig, FlowConfig
from src.settings import settings

# Blackboard Architecture: DialogueOrchestrator (Stage 14)
from src.blackboard import create_orchestrator

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


@dataclass
class GuardResult:
    """Result of a guard check, preserving both can_continue and intervention."""
    can_continue: bool
    intervention: Optional[str]


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
        flow_name: Optional[str] = None,
        persona: Optional[str] = None
    ):
        """
        Инициализация бота со всеми компонентами.

        Args:
            llm: LLM клиент (OllamaLLM или другой)
            conversation_id: Уникальный ID диалога (генерируется если не указан)
            enable_tracing: Включить трассировку условных правил (для симуляций)
            flow_name: Имя flow для загрузки (по умолчанию из settings.flow.active)
            persona: Имя персоны клиента для ObjectionGuard лимитов (из симулятора)
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
        self.generator = ResponseGenerator(llm, flow=self._flow)
        self.history: List[Dict] = []

        # FIX: Store persona in collected_data for ObjectionGuard persona-specific limits
        # This fixes the bug where 99% of simulated dialogues ended in soft_close
        # because persona was not passed from simulator and default limits (3/5) were too strict
        if persona:
            self.state_machine.collected_data["persona"] = persona

        # Context from previous turn
        self.last_action: Optional[str] = None
        self.last_intent: Optional[str] = None
        self.last_bot_message: Optional[str] = None

        # Phase 0: Metrics (controlled by feature flag)
        self.metrics = ConversationMetrics(self.conversation_id)

        # Phase 1: Protection (controlled by feature flags)
        self.guard = ConversationGuard()
        # FIX: Pass flow to FallbackHandler so it uses flow-specific skip_map
        # instead of DEFAULT_SKIP_MAP with hardcoded spin_situation
        # FIX 3: Pass guard_config for configurable tier_2 escalation threshold
        # Pass product_overviews from generator for KB-sourced CTA options
        self.fallback = FallbackHandler(
            flow=self._flow, config=self._config, guard_config=self.guard.config,
            product_overviews=self.generator._product_overview,
        )

        # =========================================================================
        # Stage 14: Blackboard DialogueOrchestrator
        # =========================================================================
        # Blackboard Orchestrator replaces state_machine.process() for dialogue
        # management. StateMachine is still used for state/collected_data storage.
        # NOTE: Must be after self.guard and self.fallback initialization.
        self._orchestrator = create_orchestrator(
            state_machine=self.state_machine,
            flow_config=self._flow,
            persona_limits=self._load_persona_limits(),
            enable_metrics=flags.metrics_tracking,
            enable_debug_logging=enable_tracing,
            guard=self.guard,
            fallback_handler=self.fallback,
            llm=llm,
        )

        # Phase 2: Natural Dialogue (controlled by feature flags)
        self.tone_analyzer = ToneAnalyzer()

        # Phase 3: SPIN Flow Optimization (controlled by feature flags)
        self.lead_scorer = LeadScorer()
        self.objection_handler = ObjectionHandler()
        self.cta_generator = CTAGenerator()

        # Phase 4: Intent Disambiguation (controlled by feature flag)
        self._disambiguation_ui = None
        self.disambiguation_metrics = DisambiguationMetrics()

        # Robust Classification: ConfidenceRouter for graceful degradation
        self.confidence_router = ConfidenceRouter(
            high_confidence=0.85,
            medium_confidence=0.65,
            low_confidence=0.45,
            min_confidence=0.30,
            gap_threshold=0.20,
            log_uncertain=True
        )

        # Phase 5: Context-aware policy overlays (controlled by feature flag)
        self.dialogue_policy = DialoguePolicy(
            shadow_mode=False,  # Применять решения (не только логировать)
            trace_enabled=enable_tracing,
            flow=self._flow,
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
        self.last_bot_message = None

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
            from src.disambiguation_ui import DisambiguationUI
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
            "last_bot_message": self.last_bot_message,
            "turns_since_last_disambiguation": self.state_machine.turns_since_last_disambiguation,
        }

        # Добавляем флаг disambiguation если активен
        if self.state_machine.in_disambiguation:
            context["in_disambiguation"] = True
            context["disambiguation_options"] = (
                self.state_machine.disambiguation_context.get("options", [])
                if self.state_machine.disambiguation_context else []
            )

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
        last_intent: str = ""  # Pass intent for informative check
    ) -> GuardResult:
        """
        Проверить ConversationGuard (Phase 1).

        Returns:
            GuardResult with can_continue flag and optional intervention
        """
        if not flags.conversation_guard:
            return GuardResult(can_continue=True, intervention=None)

        try:
            can_continue, intervention = self.guard.check(
                state=state,
                message=message,
                collected_data=collected_data,
                frustration_level=frustration_level,
                last_intent=last_intent  # Pass intent for informative check
            )

            if not can_continue:
                logger.warning(
                    "Guard stopped conversation",
                    intervention=intervention,
                    state=state
                )
                return GuardResult(can_continue=False, intervention=intervention)

            if intervention:
                logger.info(
                    "Guard intervention",
                    intervention=intervention,
                    state=state
                )
                return GuardResult(can_continue=True, intervention=intervention)

            return GuardResult(can_continue=True, intervention=None)
        except Exception as e:
            logger.error("Guard check failed", error=str(e))
            return GuardResult(can_continue=True, intervention=None)

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
    ) -> CTAResult:
        """
        Добавить CTA к ответу если уместно (Phase 3).

        Returns:
            CTAResult with full information about CTA decision:
            - cta_added: bool - whether CTA was added
            - cta: Optional[str] - the CTA text if added
            - final_response: str - response with or without CTA
            - skip_reason: Optional[str] - why CTA was skipped
        """
        # Feature flag disabled - return result with cta_added=False
        if not flags.cta_generator:
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="feature_flag_disabled"
            )

        try:
            self.cta_generator.increment_turn()
            # Use generate_cta_result() to get full CTAResult with tracking info
            result = self.cta_generator.generate_cta_result(response, state, context)

            if result.cta_added:
                logger.info(
                    "CTA applied to response",
                    state=state,
                    cta=result.cta[:30] if result.cta else None,
                )
            else:
                logger.debug(
                    "CTA skipped",
                    state=state,
                    reason=result.skip_reason,
                )

            return result

        except Exception as e:
            logger.error("CTA generation failed", error=str(e))
            # Graceful degradation: return original response without CTA
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason=f"error_{type(e).__name__}"
            )

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

        # Get current context
        current_context = self._get_classification_context()
        current_state = self.state_machine.state
        collected_data = self.state_machine.collected_data
        was_in_disambiguation = self.state_machine.in_disambiguation

        # FIX: Track all visited states during this turn for accurate phase coverage
        # This is critical for cases like fallback skip where bot transitions through
        # intermediate states (e.g., greeting -> spin_situation -> spin_problem)
        initial_state = current_state
        visited_states = [initial_state]  # Start with initial state

        # Phase 2: Analyze tone
        tone_start = time.time()
        tone_info = self._analyze_tone(user_message)
        frustration_level = tone_info.get("frustration_level", 0)
        tone_elapsed = (time.time() - tone_start) * 1000

        # Decision Tracing: Record tone analysis
        if trace_builder:
            trace_builder.record_tone(tone_info, elapsed_ms=tone_elapsed)

        # FIX 1: Classify intent BEFORE guard check so guard uses current intent
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

        # Exit disambiguation: if we were in disambiguation mode at the start of this
        # turn, the user's message is a response to the disambiguation question.
        # DisambiguationResolutionLayer already resolved options (Path B → REFINED).
        # For Path A (critical intent) and Path C (custom input), the LLM classification
        # is the answer. In all cases, exit disambiguation now.
        if was_in_disambiguation:
            resolved_intent = classification.get("intent", "custom_input")
            attempt = (
                self.state_machine.disambiguation_context.get("attempt", 1)
                if self.state_machine.disambiguation_context else 1
            )
            self.state_machine.exit_disambiguation()
            self.disambiguation_metrics.record_resolution(
                resolved_intent=resolved_intent,
                attempt=attempt,
                success=True,
            )

        # Phase 1: Check guard for intervention
        # guard_options: used for guard_offer_options action in new pipeline path
        guard_options = None

        if flags.conversation_guard_in_pipeline:
            # New path: Guard runs inside Blackboard pipeline as ConversationGuardSource
            # No external guard check, no fallback_response, no defense-in-depth block
            intervention = None
            fallback_response = None
            fallback_used = False
            fallback_tier = None
            fallback_action = None
            fallback_message = None
            rephrase_mode = False

            # Decision Tracing: Record guard check as skipped (handled by pipeline)
            if trace_builder:
                trace_builder.record_guard(
                    intervention=None,
                    can_continue=True,
                    frustration=frustration_level,
                    elapsed_ms=0.0,
                )
        else:
            # Old path: external guard check + fallback + defense-in-depth
            guard_start = time.time()
            guard_result = self._check_guard(
                state=current_state,
                message=user_message,
                collected_data=collected_data,
                frustration_level=frustration_level,
                last_intent=intent  # FIX 1: Use current intent, not self.last_intent
            )
            intervention = guard_result.intervention
            guard_elapsed = (time.time() - guard_start) * 1000

            # Decision Tracing: Record guard check
            if trace_builder:
                trace_builder.record_guard(
                    intervention=intervention,
                    can_continue=guard_result.can_continue,
                    frustration=frustration_level,
                    elapsed_ms=guard_elapsed
                )

            fallback_used = False
            fallback_tier = None
            fallback_response = None
            # FIX Defect 3: Track fallback action/message for decision trace
            fallback_action = None
            fallback_message = None
            rephrase_mode = False

            if intervention:
                fallback_used = True
                fallback_tier = intervention

                # Apply fallback
                fb_result = self._apply_fallback(
                    intervention=intervention,
                    state=current_state,
                    context={
                        "collected_data": {**collected_data, **extracted},  # FIX 1: Merge extracted for skip validation
                        "last_intent": intent,  # FIX 1: Use current intent
                        "last_action": self.last_action,
                        "frustration_level": frustration_level,
                    }
                )

                if fb_result.get("response"):
                    if fb_result.get("action") == "continue":
                        # Tier 1 rephrase: don't use template as full response.
                        # Let generator produce actual rephrased question.
                        fallback_response = None
                        rephrase_mode = True
                        # Still track for metrics
                        fallback_action = "continue"
                        fallback_message = fb_result.get("response")
                    else:
                        fallback_response = fb_result
                        # FIX Defect 3: Capture fallback details for decision trace
                        fallback_action = fb_result.get("action")
                        fallback_message = fb_result.get("response")

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
                            # FIX: Include visited_states for phase coverage tracking
                            "visited_states": [initial_state, "soft_close"],
                            "initial_state": initial_state,
                            "fallback_used": True,
                            "fallback_tier": intervention,
                            "options": fb_result.get("options"),
                        }

                    # FIX: Handle "skip" action - apply state transition to break loops
                    # FIX (Distributed State Mutation): Use transition_to() for atomic update
                    elif fb_result.get("action") == "skip" and fb_result.get("next_state"):
                        skip_next_state = fb_result["next_state"]
                        self.state_machine.transition_to(
                            next_state=skip_next_state,
                            action="skip",
                            source="fallback_skip",
                        )
                        logger.info(
                            "Fallback skip applied - resetting fallback for normal generation",
                            from_state=current_state,
                            to_state=skip_next_state,
                            original_tier=intervention
                        )
                        # Update current_state for rest of processing
                        current_state = skip_next_state
                        # FIX: Record the skipped-to state for phase coverage tracking
                        if skip_next_state not in visited_states:
                            visited_states.append(skip_next_state)
                        # Reset fallback_response to generate normal response
                        fallback_response = None

        # Track competitor mention for dynamic CTA
        if intent == "objection_competitor":
            self.state_machine.collected_data["competitor_mentioned"] = True
            competitor_name = self._extract_competitor_name(user_message)
            if competitor_name:
                self.state_machine.collected_data["competitor_name"] = competitor_name

        # disambiguation_needed intent: fallback to original intent if no options
        # (with options, DisambiguationSource handles it via Blackboard)
        if intent == "disambiguation_needed":
            options = classification.get("disambiguation_options", [])
            if not options:
                intent = classification.get("original_intent", "unclear")
                classification["intent"] = intent

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
                current_intent=intent,
                classification_result=classification,
            )

        # === Structural Frustration Detection (P3) ===
        if flags.is_enabled("structural_frustration_detection") and context_envelope:
            from src.tone_analyzer.structural_frustration import StructuralFrustrationDetector
            sf = StructuralFrustrationDetector().analyze(self.context_window)
            if sf.delta > 0:
                new_level = self.tone_analyzer.frustration_tracker.apply_structural_delta(
                    delta=sf.delta,
                    suppress_decay=(sf.delta >= 2),
                    signals=sf.signals,
                )
                tone_info["frustration_level"] = new_level
                context_envelope.frustration_level = new_level

        # Defer ResponseDirectives until AFTER policy override
        response_directives = None

        # =========================================================================
        # Stage 14: Blackboard replaces state_machine.process()
        # =========================================================================
        # БЫЛО:
        #   sm_result = self.state_machine.process(
        #       intent, extracted, context_envelope=context_envelope
        #   )
        #
        # СТАЛО:
        sm_start = time.time()
        decision = self._orchestrator.process_turn(
            intent=intent,
            extracted_data=extracted,
            context_envelope=context_envelope,
            user_message=user_message,
            frustration_level=frustration_level,
        )
        # Convert to sm_result dict for compatibility with DialoguePolicy/Generator
        sm_result = decision.to_sm_result()
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
                    # FIX (Distributed State Mutation): Use transition_to() for atomic update
                    # This ensures current_phase is consistent with the new state
                    self.state_machine.transition_to(
                        next_state=policy_override.next_state,
                        action=policy_override.action,
                        source="policy_override",
                    )

        # Decision Tracing: Record policy override
        if trace_builder:
            trace_builder.record_policy_override(policy_override)

        # Build ResponseDirectives AFTER policy override.
        # Ensures directives reflect the final action, not pre-override state.
        if flags.context_response_directives and context_envelope:
            response_directives = build_response_directives(context_envelope)

        # Propagate rephrase_mode to directives (moved from pre-override location)
        if rephrase_mode and response_directives:
            response_directives.rephrase_mode = True

        # === Defense-in-depth block (old path only) ===
        # In new pipeline path, conflict resolution handles all of this.
        if not flags.conversation_guard_in_pipeline:
            # === Universal: Policy override takes precedence over guard fallback ===
            if (fallback_response
                    and policy_override
                    and policy_override.has_override):
                logger.info(
                    "Policy override clears guard fallback",
                    original_fallback_tier=fallback_tier,
                    override_action=policy_override.action,
                    override_decision=policy_override.decision.value,
                )
                fallback_response = None
                fallback_used = False

            # === Defense-in-depth: Disambiguation takes precedence over guard fallback ===
            if (fallback_response
                    and sm_result.get("action") == "ask_clarification"
                    and sm_result.get("disambiguation_options")):
                logger.info(
                    "Disambiguation clears guard fallback",
                    original_fallback_tier=fallback_tier,
                    disambiguation_options_count=len(sm_result["disambiguation_options"]),
                )
                fallback_response = None
                fallback_used = False

            # === StallGuard takes precedence over guard fallback ===
            if (fallback_response
                    and sm_result.get("action") in ("stall_guard_eject", "stall_guard_nudge")):
                logger.info(
                    "StallGuard clears guard fallback",
                    original_fallback_tier=fallback_tier,
                    stall_guard_action=sm_result["action"],
                )
                fallback_response = None
                fallback_used = False

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
            # FIXED: Concatenate both instructions to preserve apology from tone_info
            # SSoT: src/apology_ssot.py
            "tone_instruction": " ".join(filter(None, [
                directive_instruction,
                tone_info.get("tone_instruction", "")
            ])),
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

        # 9e: Set rephrase_mode for guard_rephrase action (new pipeline path)
        if flags.conversation_guard_in_pipeline and action == "guard_rephrase":
            rephrase_mode = True
            if response_directives:
                response_directives.rephrase_mode = True

        # Remap stall_guard actions to valid template actions
        if action == "stall_guard_eject":
            action = f"transition_to_{next_state}"
            # Fallback to continue_current_goal if specific transition template doesn't exist
            if not self.generator._get_template(action):
                action = "continue_current_goal"
        elif action == "stall_guard_nudge":
            action = "continue_conversation"
            if not self.generator._get_template(action):
                action = "continue_current_goal"

        # FIX: Record the final state for phase coverage tracking
        if next_state not in visited_states:
            visited_states.append(next_state)

        # =================================================================
        # Response Generation and CTA Application (refactored for proper tracking)
        # =================================================================
        # Initialize CTA result for tracking
        cta_result: CTAResult = CTAResult(
            original_response="",
            cta=None,
            final_response="",
            cta_added=False,
            skip_reason="not_applicable"
        )
        response_elapsed: float = 0.0

        # If objection detected and needs soft close - override state machine result
        if objection_info and objection_info.get("should_soft_close"):
            action = "soft_close"
            next_state = "soft_close"  # Синхронизируем состояние с action
            is_final = True  # soft_close - финальное состояние
            # Безопасный доступ к response_parts с fallback
            response_parts = objection_info.get("response_parts") or {}
            response = response_parts.get("message") or "Хорошо, свяжитесь когда будет удобно."
            # CTA not applicable for soft_close
            cta_result = CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="soft_close_path"
            )
            logger.info(
                "Soft close triggered by objection handler",
                objection_type=objection_info.get("objection_type"),
                attempt_number=objection_info.get("attempt_number")
            )
        elif fallback_response:
            # Fallback path - CTA not applicable
            response_start = time.time()
            response = fallback_response["response"]
            # FIX Defect 2: Propagate fallback action to output action variable
            action = fallback_response.get("action", action)
            response_elapsed = (time.time() - response_start) * 1000
            cta_result = CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="fallback_path"
            )
        elif action == "ask_clarification":
            disambiguation_options = sm_result.get("disambiguation_options", [])
            disambiguation_question = sm_result.get("disambiguation_question", "")

            if not disambiguation_options:
                # Defense Layer 2: empty options → generate normal response
                logger.warning(
                    "ask_clarification with empty disambiguation_options, "
                    "falling back to continue_conversation"
                )
                action = "continue_conversation"  # Fix action for context_window recording
                response_start = time.time()
                response = self.generator.generate(action, context)
                response_elapsed = (time.time() - response_start) * 1000
                cta_result = CTAResult(
                    original_response=response,
                    cta=None,
                    final_response=response,
                    cta_added=False,
                    skip_reason="disambiguation_empty_fallback",
                )
            else:
                # Normal disambiguation path
                extracted = classification.get("extracted_data", {})

                response = self.disambiguation_ui.format_question(
                    question=disambiguation_question,
                    options=disambiguation_options,
                    context={**current_context, "frustration_level": frustration_level},
                )

                self.state_machine.enter_disambiguation(
                    options=disambiguation_options,
                    extracted_data=extracted,
                )

                self.disambiguation_metrics.record_disambiguation(
                    options=[o["intent"] for o in disambiguation_options],
                    scores=classification.get("original_scores", {}),
                )

                cta_result = CTAResult(
                    original_response=response,
                    cta=None,
                    final_response=response,
                    cta_added=False,
                    skip_reason="disambiguation_path",
                )
        elif action == "offer_options":
            # Phase-exhausted options path — decision from Blackboard PhaseExhaustedSource.
            # Since combinable=True, a transition may have also been applied.
            # If state progressed → generate normal response (transition wins over options).
            # If state unchanged → show options menu (bot is truly stuck).
            response_start = time.time()
            if next_state != current_state:
                # Transition happened — progress, don't show stale options
                action = "continue_conversation"
                response = self.generator.generate(action, context)
            else:
                # No transition — truly stuck, show options menu
                fb_result = self.fallback.generate_options_menu(
                    state=current_state,
                    context={
                        "collected_data": {**collected_data, **extracted},
                        "last_intent": intent,
                        "last_action": self.last_action,
                        "frustration_level": frustration_level,
                    }
                )
                response = fb_result.message
            response_elapsed = (time.time() - response_start) * 1000
            cta_result = CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="phase_exhausted_options",
            )
        elif action == "guard_rephrase":
            # TIER_1: generator produces rephrased question (state-aware resolution)
            response_start = time.time()
            rephrase_template = f"{current_state}_continue_goal"
            if not self.generator._get_template(rephrase_template):
                rephrase_template = "continue_current_goal"
            response = self.generator.generate(rephrase_template, context)
            response_elapsed = (time.time() - response_start) * 1000
            cta_result = CTAResult(
                original_response=response, cta=None, final_response=response,
                cta_added=False, skip_reason="guard_rephrase_path",
            )
        elif action == "guard_offer_options":
            # TIER_2: fallback options menu
            response_start = time.time()
            guard_fb = self.fallback.get_fallback(
                tier="fallback_tier_2",
                state=current_state,
                context={
                    "collected_data": {**collected_data, **extracted},
                    "last_intent": intent,
                    "last_action": self.last_action,
                    "frustration_level": frustration_level,
                }
            )
            response = guard_fb.message
            guard_options = guard_fb.options
            response_elapsed = (time.time() - response_start) * 1000
            fallback_used = True
            fallback_tier = "fallback_tier_2"
            fallback_action = "guard_offer_options"
            fallback_message = response
            intervention = sm_result.get("resolution_trace", {}).get(
                "winning_action_metadata", {}
            ).get("tier")
            cta_result = CTAResult(
                original_response=response, cta=None, final_response=response,
                cta_added=False, skip_reason="guard_options_path",
            )
        elif action == "guard_skip_phase":
            # TIER_3: state already transitioned by orchestrator _apply_side_effects
            response_start = time.time()
            response = self.generator.generate("continue_conversation", context)
            response_elapsed = (time.time() - response_start) * 1000
            fallback_used = True
            fallback_tier = "fallback_tier_3"
            fallback_action = "guard_skip_phase"
            fallback_message = response
            intervention = sm_result.get("resolution_trace", {}).get(
                "winning_action_metadata", {}
            ).get("tier")
            cta_result = CTAResult(
                original_response=response, cta=None, final_response=response,
                cta_added=False, skip_reason="guard_skip_path",
            )
        elif action == "guard_soft_close":
            # TIER_4: graceful exit
            response_start = time.time()
            guard_fb = self.fallback.get_fallback(
                tier="soft_close",
                state=current_state,
                context={
                    "collected_data": {**collected_data, **extracted},
                    "last_intent": intent,
                    "last_action": self.last_action,
                    "frustration_level": frustration_level,
                }
            )
            response = guard_fb.message
            response_elapsed = (time.time() - response_start) * 1000
            is_final = True
            fallback_used = True
            fallback_tier = "soft_close"
            cta_result = CTAResult(
                original_response=response, cta=None, final_response=response,
                cta_added=False, skip_reason="guard_soft_close_path",
            )
            # Finalize metrics
            self._record_turn_metrics(
                state=current_state, intent="fallback_close",
                tone=tone_info.get("tone"), fallback_used=True, fallback_tier="soft_close",
            )
            self.history.append({"user": user_message, "bot": response})
            self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)
            return {
                "response": response, "intent": "fallback_close",
                "action": "soft_close", "state": "soft_close", "is_final": True,
                "visited_states": [initial_state, "soft_close"],
                "initial_state": initial_state,
                "fallback_used": True, "fallback_tier": "soft_close",
                "options": None,
            }
        else:
            # Defense-in-depth: verify template exists before generation
            if not self.generator._get_template(action):
                original_action = action
                # Context-aware fallback based on intent type
                from src.yaml_config.constants import PRICING_CORRECT_ACTIONS
                from src.yaml_config.constants import QUESTION_INTENTS
                if intent in PRICING_CORRECT_ACTIONS or intent in self.generator.PRICE_RELATED_INTENTS:
                    action = "answer_with_pricing"
                elif intent in QUESTION_INTENTS:
                    action = "answer_with_facts"
                else:
                    action = "continue_current_goal"
                logger.warning(
                    "Runtime template miss — context-aware fallback applied",
                    original_action=original_action,
                    fallback_action=action,
                    intent=intent,
                    flow=self._flow.name,
                )
            # 3. Generate response (normal path)
            response_start = time.time()
            response = self.generator.generate(action, context)
            response_elapsed = (time.time() - response_start) * 1000

            # Phase 3: Apply CTA BEFORE recording response (critical fix!)
            # Pass action + objection_info for semantic CTA gating
            cta_result = self._apply_cta(
                response=response,
                state=next_state,
                context={
                    "frustration_level": frustration_level,
                    "last_action": self.last_action,
                    "action": action,
                    "objection_info": objection_info,
                    # Pass collected_data for contact gate
                    "collected_data": self.state_machine.collected_data,
                    # Flow context for dynamic CTA phase resolution
                    "flow_context": {
                        "phase_order": list(self.state_machine.phase_order),
                        "phase_states": dict(self.state_machine.phase_states),
                    }
                }
            )
            # Update response with CTA result
            response = cta_result.final_response

        # Decision Tracing: Record response generation WITH CTA info
        if trace_builder:
            trace_builder.record_response(
                template_key=action,
                response_text=response,
                elapsed_ms=response_elapsed,
                cta_added=cta_result.cta_added,
                cta_type=cta_result.cta[:30] if cta_result.cta else None,
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
        self.last_bot_message = response

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
                    action=fallback_action,
                    message=fallback_message,
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
            # FIX: All visited states during this turn for accurate phase coverage
            # Critical for fallback skip scenarios where bot transitions through
            # intermediate states (e.g., greeting -> spin_situation -> spin_problem)
            "visited_states": visited_states,
            "initial_state": initial_state,
            # Additional info
            "fallback_used": fallback_used,
            "fallback_tier": fallback_tier,
            "tone": tone_info.get("tone"),
            "frustration_level": frustration_level,
            "lead_score": self.lead_scorer.current_score if flags.lead_scoring else None,
            "objection_detected": objection_info is not None,
            "options": guard_options if action == "guard_offer_options" else (
                fallback_response.get("options") if (not flags.conversation_guard_in_pipeline and fallback_response) else None
            ),
            # CTA tracking
            "cta_added": cta_result.cta_added if cta_result else False,
            "cta_text": cta_result.cta if cta_result else None,
            # Decision Tracing
            "decision_trace": decision_trace_dict,
        }

    def _load_persona_limits(self) -> Dict[str, Dict[str, int]]:
        """
        Load persona limits from flow configuration.

        Returns:
            Dict mapping persona names to their limits (consecutive, total)

        FIX: Names must match personas.py exactly (e.g., "skeptic" not "skeptical")
        Limits are calibrated based on objection_probability from personas.py:
        - Higher objection_probability → higher limits to avoid premature soft_close
        """
        # Default limits (used if not configured in YAML)
        # FIX: Include all personas from simulator/personas.py with matching names
        default_limits = {
            # From personas.py with matching names:
            "happy_path": {"consecutive": 3, "total": 5},      # objection_prob=0.1
            "skeptic": {"consecutive": 4, "total": 7},         # objection_prob=0.6
            "busy": {"consecutive": 3, "total": 5},            # objection_prob=0.4
            "price_sensitive": {"consecutive": 5, "total": 9}, # objection_prob=0.8
            "competitor_user": {"consecutive": 4, "total": 7}, # objection_prob=0.5
            "aggressive": {"consecutive": 5, "total": 8},      # objection_prob=0.7
            "technical": {"consecutive": 4, "total": 6},       # objection_prob=0.3
            "tire_kicker": {"consecutive": 6, "total": 12},    # objection_prob=0.9
            # Legacy names (for backwards compatibility):
            "analytical": {"consecutive": 4, "total": 6},
            "friendly": {"consecutive": 4, "total": 7},
            # Fallback:
            "default": {"consecutive": 4, "total": 6},         # Increased from 3/5
        }

        # Try to get from flow config constants
        if hasattr(self._flow, 'constants') and self._flow.constants:
            limits = self._flow.constants.get("persona_limits", {})
            if limits:
                return limits

        return default_limits

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
    import argparse
    from src.llm import OllamaLLM

    parser = argparse.ArgumentParser(description="CRM Sales Bot interactive mode")
    parser.add_argument("--flow", type=str, default=None,
                        help="Sales flow to use (e.g. aida, bant, spin_selling, challenger)")
    args = parser.parse_args()

    # Enable all flags for testing
    flags.enable_group("phase_0")
    flags.enable_group("phase_1")
    flags.enable_group("phase_2")
    flags.enable_group("phase_3")

    # Auto-enable autonomous_flow flag when --flow autonomous
    # Disable GPU-heavy models (FRIDA embeddings, semantic tone) to avoid CUDA OOM
    if args.flow == "autonomous":
        flags.set_override("autonomous_flow", True)
        flags.set_override("tone_semantic_tier2", False)
        settings["retriever"]["use_embeddings"] = False

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name=args.flow)

    run_interactive(bot)
