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
import re
import json
import uuid
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Any, Set, Sequence

from src.classifier import UnifiedClassifier
from src.state_machine import StateMachine
from src.generator import ResponseGenerator

# Phase 0: Infrastructure
from src.logger import logger
from src.feature_flags import flags
from src.metrics import ConversationMetrics, ConversationOutcome, DisambiguationMetrics

# Phase 1: Protection and Reliability
from src.conversation_guard import ConversationGuard, GuardConfig
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
from src.history_compactor import HistoryCompactor

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
from src.blackboard.decision_sanitizer import (
    DecisionSanitizer,
    SanitizedTransitionResult,
    INVALID_NEXT_STATE_REASON,
)
from src.blackboard.sources.autonomous_decision import AutonomousDecisionRecord
from src.media_turn_context import (
    MEDIA_PROFILE_SAFE_FIELDS as MEDIA_PROFILE_SAFE_FIELDS_SET,
    MediaTurnContext,
    freeze_media_turn_context,
    scrub_media_card_payload,
    scrub_media_extracted_data,
    scrub_media_fact_list,
)

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


MEDIA_PROFILE_SAFE_FIELDS: Set[str] = set(MEDIA_PROFILE_SAFE_FIELDS_SET)


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
        persona: Optional[str] = None,
        client_id: Optional[str] = None,
        config_name: Optional[str] = None,
    ):
        """
        Инициализация бота со всеми компонентами.

        Args:
            llm: LLM клиент (OllamaLLM или другой)
            conversation_id: Уникальный ID диалога (генерируется если не указан)
            enable_tracing: Включить трассировку условных правил (для симуляций)
            flow_name: Имя flow для загрузки (по умолчанию из settings.flow.active)
            persona: Имя персоны клиента для ObjectionGuard лимитов (из симулятора)
            config_name: Имя tenant-конфига (если нужно загрузить не default)
        """
        # Генерируем ID диалога для трейсинга
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        logger.set_conversation(self.conversation_id)
        self.client_id = client_id

        # Phase DAG: Load modular flow configuration (REQUIRED since v2.0)
        # Legacy Python-based config is deprecated and no longer used
        self._config_loader = ConfigLoader()
        self._config: LoadedConfig
        self._flow: FlowConfig
        self._config, self._flow = self._config_loader.load_bundle(
            config_name=config_name or "default",
            flow_name=flow_name,
            validate=True,
        )
        resolved_flow = self._config.flow_name or settings.flow.active

        # Log flow resolution for debugging multi-flow scenarios
        logger.info(
            "SalesBot flow resolved",
            requested_flow=flow_name,
            resolved_flow=resolved_flow,
            flow_name=self._flow.name,
            flow_version=self._flow.version,
            states_count=len(self._flow.states),
            phase_order=self._flow.phase_order,
            entry_state=self._flow.get_entry_point("default"),
        )

        # Runtime strictness: fail fast on any config/flow drift.
        self._assert_runtime_flow_binding(
            requested_flow=flow_name,
            resolved_flow=resolved_flow,
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
        self.history_compact: Optional[Dict[str, Any]] = None
        self.history_compact_meta: Optional[Dict[str, Any]] = None

        # FIX: Store persona in collected_data for ObjectionGuard persona-specific limits
        # This fixes the bug where 99% of simulated dialogues ended in soft_close
        # because persona was not passed from simulator and default limits (3/5) were too strict
        if persona:
            self.state_machine.collected_data["persona"] = persona

        # Context from previous turn
        self.last_action: Optional[str] = None
        self.last_intent: Optional[str] = None
        self.last_bot_message: Optional[str] = None
        self._pending_media_meta: Dict[str, Any] = {}

        # Phase 0: Metrics (controlled by feature flag)
        self.metrics = ConversationMetrics(self.conversation_id)

        # Phase 1: Protection (controlled by feature flags)
        guard_overrides = self._config.guard
        if guard_overrides:
            guard_cfg = GuardConfig(
                **{k: v for k, v in guard_overrides.items()
                   if k in GuardConfig.__dataclass_fields__}
            )
        else:
            guard_cfg = GuardConfig.default()
        self.guard = ConversationGuard(config=guard_cfg)
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
            blackboard_config=self._config.blackboard,
            valid_actions=self.generator.get_valid_actions(),
        )

        # Phase 2: Natural Dialogue (controlled by feature flags)
        self.tone_analyzer = ToneAnalyzer()

        # Phase 3: SPIN Flow Optimization (controlled by feature flags)
        self.lead_scorer = LeadScorer(config=self._config)
        self.objection_handler = ObjectionHandler()
        self.cta_generator = CTAGenerator(config=self._config)

        # Phase 4: Intent Disambiguation (controlled by feature flag)
        self._disambiguation_ui = None
        self.disambiguation_metrics = DisambiguationMetrics()

        # Robust Classification: ConfidenceRouter for graceful degradation
        disambiguation_cfg = self._config.disambiguation
        self.confidence_router = ConfidenceRouter(
            high_confidence=disambiguation_cfg.get("high_confidence", 0.85),
            medium_confidence=disambiguation_cfg.get("medium_confidence", 0.65),
            low_confidence=disambiguation_cfg.get("low_confidence", 0.45),
            min_confidence=disambiguation_cfg.get("min_confidence", 0.30),
            gap_threshold=disambiguation_cfg.get("gap_threshold", 0.20),
            log_uncertain=disambiguation_cfg.get("log_uncertain", True),
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
        self._merge_flow_state_order()  # Merge flow-specific ordering

        # Personalization v2: Session memory for effective actions
        self.action_tracker: Optional[EffectiveActionTracker] = None
        if flags.personalization_session_memory:
            self.action_tracker = EffectiveActionTracker()

        # Runtime state transition hardening
        self._decision_sanitizer = DecisionSanitizer()

        # Decision Tracing: Store traces for each turn
        self._decision_traces: List[DecisionTrace] = []
        self._enable_decision_tracing = enable_tracing

        logger.info(
            "SalesBot initialized",
            conversation_id=self.conversation_id,
            enabled_flags=list(flags.get_enabled_flags()),
            flow_name=self._flow.name,
            flow_version=self._flow.version,
            config_name=getattr(self._config, "name", None),
            config_system="modular_yaml",
        )

    def _assert_runtime_flow_binding(
        self,
        requested_flow: Optional[str],
        resolved_flow: Optional[str],
    ) -> None:
        """Fail-fast check for runtime config/flow binding consistency."""
        config_flow = getattr(self._config, "flow_name", None)
        loaded_flow = getattr(self._flow, "name", None)

        if config_flow != loaded_flow:
            raise RuntimeError(
                f"Runtime flow binding mismatch: config.flow_name='{config_flow}', "
                f"flow.name='{loaded_flow}', requested='{requested_flow}', resolved='{resolved_flow}'"
            )

        if resolved_flow and config_flow != resolved_flow:
            raise RuntimeError(
                f"Runtime flow resolution mismatch: resolved='{resolved_flow}', "
                f"config.flow_name='{config_flow}', flow.name='{loaded_flow}'"
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
        self._pending_media_meta = {}

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
        self._orchestrator.reset()

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

        # История диалога (последние 4 хода) для классификации коротких ответов
        recent_turns = self.context_window.get_last_n_turns(4)
        if recent_turns:
            context["dialog_history"] = [
                {
                    "bot": (t.bot_response or "")[:250],
                    "user": t.user_message[:200],
                }
                for t in recent_turns
            ]

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

        # Autonomous quality gate:
        # Keep CTA only in closing-like states to avoid repetitive "sales push"
        # in discovery/qualification/presentation turns.
        if (
            self._flow
            and self._flow.name == "autonomous"
            and state not in {"autonomous_closing", "close", "success"}
        ):
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="autonomous_non_closing_state"
            )

        # Respect explicit "no pressure / no contact" requests — no CTA push.
        msg = str(context.get("user_message", "") or "").lower()
        history = context.get("history", [])
        recent_user_text = " ".join(
            str(turn.get("user", "") or "").lower()
            for turn in (history[-4:] if isinstance(history, list) else [])
            if isinstance(turn, dict)
        )
        no_push_source = f"{msg} {recent_user_text}"
        no_push_markers = (
            "не проси мои контакты",
            "без контактов",
            "без контакта",
            "контакты не дам",
            "контакт не дам",
            "контакт пока не даю",
            "без давления",
            "не дави",
            "я сам решу",
            "иин не дам",
            "иин пока не дам",
            "без иин",
            "пока без иин",
            "звоноксыз",
            "қоңыраусыз",
            "потом дам контакт",
            "позже дам контакт",
            "контакт позже",
        )
        if any(m in no_push_source for m in no_push_markers):
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="explicit_no_push_request"
            )

        # In high-friction autonomous turns, suppress CTA to avoid sales pressure.
        if (
            self._flow
            and self._flow.name == "autonomous"
            and int(context.get("frustration_level", 0) or 0) >= 3
        ):
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="autonomous_high_friction"
            )

        # If question is intentionally suppressed for this turn, skip CTA too.
        if context.get("question_mode") == "suppress":
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="question_mode_suppress"
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

    def _get_valid_states(self) -> Set[str]:
        """Return the valid state names for transition sanitization."""
        if hasattr(self._flow, "states"):
            return set(self._flow.states.keys())
        return set()

    def _sanitize_transition_target(
        self,
        requested_state: Optional[str],
        current_state: str,
        source: str,
    ) -> SanitizedTransitionResult:
        """Sanitize a transition target for bot-level state mutations."""
        result = self._decision_sanitizer.sanitize_target(
            requested_state=requested_state,
            current_state=current_state,
            valid_states=self._get_valid_states(),
            source=source,
        )
        if result.sanitized:
            logger.warning(
                "Bot-level transition target sanitized",
                source=source,
                requested_state=result.requested_state,
                effective_state=result.effective_state,
                reason_code=result.reason_code,
            )
        return result

    @staticmethod
    def _append_reason_code(sm_result: Dict[str, Any], reason_code: Optional[str]) -> None:
        """Append reason code to sm_result if missing."""
        if not reason_code:
            return
        reason_codes = sm_result.get("reason_codes")
        if not isinstance(reason_codes, list):
            reason_codes = []
        if reason_code not in reason_codes:
            reason_codes.append(reason_code)
        sm_result["reason_codes"] = reason_codes

    @staticmethod
    def _append_bot_sanitization_marker(
        sm_result: Dict[str, Any],
        marker: Dict[str, Any],
    ) -> None:
        """Attach bot-level transition sanitization diagnostics to resolution_trace."""
        resolution_trace = sm_result.get("resolution_trace")
        if not isinstance(resolution_trace, dict):
            resolution_trace = {}

        markers = resolution_trace.get("bot_transition_sanitization")
        if not isinstance(markers, list):
            markers = []

        markers.append(marker)
        resolution_trace["bot_transition_sanitization"] = markers
        sm_result["resolution_trace"] = resolution_trace

    def set_pending_media_meta(self, media_meta: Optional[Dict[str, Any]]) -> None:
        """Store turn-scoped media context for the next process() call."""
        self._pending_media_meta = dict(media_meta or {})

    def _consume_pending_media_meta(self) -> Dict[str, Any]:
        """Read and clear turn-scoped media context."""
        meta = dict(self._pending_media_meta or {})
        self._pending_media_meta = {}
        return meta

    def _is_autonomous_media_runtime(self, state: Optional[str] = None) -> bool:
        current_state = state or self.state_machine.state
        return bool(
            self._flow
            and self._flow.name == "autonomous"
            and (
                str(current_state).startswith("autonomous_")
                or str(current_state) == "greeting"
            )
        )

    @staticmethod
    def _merge_extracted_data(
        extracted_data: Optional[Dict[str, Any]],
        media_extracted_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(media_extracted_data or {})
        for key, value in (extracted_data or {}).items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value
        return merged

    def _get_client_media_facts(self) -> List[str]:
        if not hasattr(self, "context_window") or not hasattr(self.context_window, "episodic_memory"):
            return []
        memory = getattr(self.context_window, "episodic_memory", None)
        if memory is not None and hasattr(memory, "get_media_facts"):
            return list(memory.get_media_facts(limit=10) or [])
        if not hasattr(self, "context_window") or not hasattr(self.context_window, "episodic_memory"):
            return []
        profile = getattr(self.context_window.episodic_memory, "client_profile", None)
        facts = getattr(profile, "media_facts", []) if profile else []
        return list(facts or [])

    def _get_recent_media_knowledge_cards(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not hasattr(self, "context_window") or not hasattr(self.context_window, "episodic_memory"):
            return []
        memory = getattr(self.context_window, "episodic_memory", None)
        if memory is not None and hasattr(memory, "get_recent_media_knowledge_cards"):
            return [
                scrub_media_card_payload(card)
                for card in list(memory.get_recent_media_knowledge_cards(limit=limit) or [])
                if card
            ]
        return []

    def _store_media_knowledge_cards(self, media_cards: Optional[List[Dict[str, Any]]]) -> None:
        if not media_cards:
            return
        if not hasattr(self, "context_window") or not hasattr(self.context_window, "episodic_memory"):
            return
        memory = getattr(self.context_window, "episodic_memory", None)
        if memory is not None and hasattr(memory, "upsert_media_knowledge_cards"):
            memory.upsert_media_knowledge_cards(
                [scrub_media_card_payload(card) for card in media_cards if card]
            )

    def hydrate_external_memory(
        self,
        *,
        profile_data: Optional[Dict[str, Any]] = None,
        media_cards: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Seed bot memory from cross-session persisted knowledge."""
        profile_data = dict(profile_data or {})
        if profile_data:
            self.state_machine.update_data(profile_data)
            profile = getattr(self.context_window.episodic_memory, "client_profile", None)
            if profile is not None and hasattr(profile, "update_from_data"):
                profile.update_from_data(profile_data)
                for pain in profile_data.get("pain_points", []) or []:
                    if pain and pain not in profile.pain_points:
                        profile.pain_points.append(pain)
                for item in profile_data.get("interested_features", []) or []:
                    if item and item not in profile.interested_features:
                        profile.interested_features.append(item)
                for item in profile_data.get("objection_types", []) or []:
                    if item and item not in profile.objection_types:
                        profile.objection_types.append(item)
        if media_cards:
            self._store_media_knowledge_cards(media_cards)
            safe_fields = self._extract_safe_media_fields(media_cards)
            backfill = {
                key: value
                for key, value in safe_fields.items()
                if self.state_machine.collected_data.get(key) in (None, "", [], {})
            }
            if backfill:
                self.state_machine.update_data(backfill)

    @staticmethod
    def _extract_safe_media_fields(media_cards: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for card in media_cards or []:
            extracted = scrub_media_extracted_data(card.get("extracted_data", {}) or {})
            for key, value in extracted.items():
                if key not in MEDIA_PROFILE_SAFE_FIELDS or value in (None, "", [], {}):
                    continue
                merged[key] = value
        return merged

    @staticmethod
    def _finalize_media_cards(
        media_cards: Optional[List[Dict[str, Any]]],
        *,
        source_session_id: str,
        source_turn: int,
    ) -> List[Dict[str, Any]]:
        finalized: List[Dict[str, Any]] = []
        for raw_card in media_cards or []:
            card = scrub_media_card_payload(raw_card or {})
            if not card:
                continue
            card["source_session_id"] = card.get("source_session_id") or source_session_id
            card["source_turn"] = int(card.get("source_turn") or source_turn or 0)
            finalized.append(scrub_media_card_payload(card))
        return finalized

    def _compat_media_cards_from_meta(
        self,
        pending_media_meta: Optional[Dict[str, Any]],
        *,
        source_session_id: str,
        source_turn: int,
    ) -> List[Dict[str, Any]]:
        meta = dict(pending_media_meta or {})
        answer_context = str(meta.get("answer_context") or "").strip()
        if not answer_context:
            return []
        card = {
            "knowledge_id": f"compat-{abs(hash(answer_context))}",
            "attachment_fingerprint": f"compat-{abs(hash(answer_context))}",
            "source_session_id": source_session_id,
            "source_turn": int(source_turn or 0),
            "file_name": "",
            "media_kind": "media",
            "source_user_text": str(meta.get("source_user_text") or "").strip(),
            "summary": answer_context.splitlines()[0].strip()[:600],
            "facts": list(meta.get("media_facts", []) or [])[:8],
            "extracted_data": dict(meta.get("extracted_data", {}) or {}),
            "answer_context": answer_context[:1800],
        }
        return [scrub_media_card_payload(card)]

    def _get_media_history_candidates(self, query: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        if not hasattr(self, "context_window") or not hasattr(self.context_window, "episodic_memory"):
            return []
        memory = getattr(self.context_window, "episodic_memory", None)
        if memory is None or not hasattr(memory, "get_media_knowledge_candidates"):
            return []
        return [
            scrub_media_card_payload(card)
            for card in list(memory.get_media_knowledge_candidates(query) or [])[:limit]
            if card
        ]

    def _build_pending_media_turn_context(
        self,
        pending_media_meta: Optional[Dict[str, Any]],
        *,
        source_turn: int,
        fallback_user_message: str,
    ) -> Optional[MediaTurnContext]:
        meta = dict(pending_media_meta or {})
        if not meta:
            return None

        current_cards = self._finalize_media_cards(
            list(meta.get("knowledge_cards", []) or []),
            source_session_id=str(meta.get("source_session_id") or ""),
            source_turn=source_turn,
        )
        if not current_cards:
            current_cards = self._compat_media_cards_from_meta(
                meta,
                source_session_id=str(meta.get("source_session_id") or ""),
                source_turn=source_turn,
            )

        if (
            not current_cards
            and not meta.get("used_attachments")
            and not meta.get("skipped_attachments")
            and not meta.get("media_facts")
            and not meta.get("extracted_data")
        ):
            return None

        raw_user_text = str(meta.get("source_user_text") or fallback_user_message or "")
        safe_extracted_data = scrub_media_extracted_data(
            meta.get("extracted_data", {}) or self._extract_safe_media_fields(current_cards)
        )
        safe_media_facts = tuple(
            scrub_media_fact_list(
                meta.get("media_facts", []) or [
                    fact
                    for card in current_cards
                    for fact in list(card.get("facts", []) or [])
                ],
                limit=8,
            )
        )
        return freeze_media_turn_context(
            MediaTurnContext(
                raw_user_text=raw_user_text,
                attachment_only=not raw_user_text.strip() and bool(current_cards),
                source_session_id=str(meta.get("source_session_id") or ""),
                source_user_id=str(meta.get("source_user_id") or ""),
                used_attachments=tuple(meta.get("used_attachments", []) or []),
                skipped_attachments=tuple(meta.get("skipped_attachments", []) or []),
                current_cards=tuple(current_cards),
                historical_candidates=tuple(),
                safe_extracted_data=safe_extracted_data,
                safe_media_facts=safe_media_facts,
            )
        )

    def _build_historical_media_turn_context(self, user_message: str) -> Optional[MediaTurnContext]:
        historical_candidates = self._get_media_history_candidates(user_message)
        if not historical_candidates:
            return None
        return freeze_media_turn_context(
            MediaTurnContext(
                raw_user_text=str(user_message or ""),
                attachment_only=False,
                source_session_id="",
                source_user_id="",
                used_attachments=tuple(),
                skipped_attachments=tuple(),
                current_cards=tuple(),
                historical_candidates=tuple(historical_candidates),
                safe_extracted_data={},
                safe_media_facts=tuple(),
            )
        )

    def _enrich_media_turn_context(
        self,
        media_turn_context: Optional[MediaTurnContext],
        *,
        current_turn_number: int,
        fallback_user_message: str,
    ) -> Optional[MediaTurnContext]:
        frozen = freeze_media_turn_context(media_turn_context)
        if frozen is None:
            return None

        current_cards = self._finalize_media_cards(
            [dict(card) for card in tuple(frozen.current_cards or ())],
            source_session_id=frozen.source_session_id,
            source_turn=current_turn_number,
        )
        historical_candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw_card in list(tuple(frozen.historical_candidates or ())) + self._get_media_history_candidates(
            frozen.raw_user_text or fallback_user_message
        ):
            card = scrub_media_card_payload(raw_card)
            card_id = str(card.get("knowledge_id") or card.get("attachment_fingerprint") or "")
            if not card_id or card_id in seen:
                continue
            seen.add(card_id)
            historical_candidates.append(card)

        safe_extracted_data = scrub_media_extracted_data(
            dict(frozen.safe_extracted_data or {}) or self._extract_safe_media_fields(current_cards)
        )
        safe_media_facts = tuple(
            scrub_media_fact_list(
                tuple(frozen.safe_media_facts or ()) or [
                    fact
                    for card in current_cards
                    for fact in list(card.get("facts", []) or [])
                ],
                limit=8,
            )
        )
        raw_user_text = str(frozen.raw_user_text or fallback_user_message or "")
        return freeze_media_turn_context(
            replace(
                frozen,
                raw_user_text=raw_user_text,
                attachment_only=not raw_user_text.strip() and bool(current_cards),
                current_cards=tuple(current_cards),
                historical_candidates=tuple(historical_candidates),
                safe_extracted_data=safe_extracted_data,
                safe_media_facts=safe_media_facts,
            )
        )

    def _resolve_media_turn_context(
        self,
        *,
        explicit_media_turn_context: Optional[MediaTurnContext],
        pending_media_meta: Optional[Dict[str, Any]],
        current_turn_number: int,
        fallback_user_message: str,
    ) -> Optional[MediaTurnContext]:
        explicit = freeze_media_turn_context(explicit_media_turn_context)
        pending = dict(pending_media_meta or {})

        if explicit is not None and pending:
            logger.warning(
                "Both explicit media_turn_context and pending adapter media_meta received; using explicit context"
            )
            return self._enrich_media_turn_context(
                explicit,
                current_turn_number=current_turn_number,
                fallback_user_message=fallback_user_message,
            )

        if explicit is not None:
            return self._enrich_media_turn_context(
                explicit,
                current_turn_number=current_turn_number,
                fallback_user_message=fallback_user_message,
            )

        compat = self._build_pending_media_turn_context(
            pending,
            source_turn=current_turn_number,
            fallback_user_message=fallback_user_message,
        )
        if compat is not None:
            return self._enrich_media_turn_context(
                compat,
                current_turn_number=current_turn_number,
                fallback_user_message=fallback_user_message,
            )

        return self._build_historical_media_turn_context(fallback_user_message)

    def _build_media_card_lookup(
        self,
        media_turn_context: Optional[MediaTurnContext],
    ) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        frozen = freeze_media_turn_context(media_turn_context)
        if frozen is None:
            return lookup
        for raw_card in list(tuple(frozen.current_cards or ())) + list(tuple(frozen.historical_candidates or ())):
            card = scrub_media_card_payload(raw_card)
            card_id = str(card.get("knowledge_id") or "")
            if card_id and card_id not in lookup:
                lookup[card_id] = card
        return lookup

    def _resolve_selected_media_cards_from_context(
        self,
        *,
        media_turn_context: Optional[MediaTurnContext],
        selected_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        wanted = [str(item).strip() for item in selected_ids if str(item).strip()]
        if not wanted:
            return []
        lookup = self._build_media_card_lookup(media_turn_context)
        return [lookup[item] for item in wanted if item in lookup]

    @staticmethod
    def _extract_media_route(sm_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        trace = (sm_result or {}).get("resolution_trace", {})
        metadata = trace.get("winning_action_metadata", {}) if isinstance(trace, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}

        response_mode = str(metadata.get("response_mode") or "normal_dialog").strip().lower()
        if response_mode not in {"normal_dialog", "media_only", "hybrid"}:
            response_mode = "normal_dialog"

        selected_ids = [
            str(item).strip()
            for item in list(metadata.get("selected_media_card_ids", []) or [])
            if str(item).strip()
        ][:3]
        if response_mode != "normal_dialog" and not selected_ids:
            response_mode = "normal_dialog"

        return {
            "response_mode": response_mode,
            "selected_media_card_ids": selected_ids if response_mode != "normal_dialog" else [],
            "route_reasoning": str(metadata.get("route_reasoning") or ""),
            "route_source": str(metadata.get("route_source") or "fallback"),
        }

    @staticmethod
    def _is_content_generation_action(action: str) -> bool:
        return action in {
            "autonomous_respond",
            "continue_current_goal",
            "greet_back",
        }

    @staticmethod
    def _build_media_route_instruction(
        *,
        response_mode: str,
        selected_media_grounding: str,
    ) -> str:
        if not str(selected_media_grounding or "").strip():
            return ""
        if response_mode == "media_only":
            return (
                "MEDIA ROUTE: отвечай только по selected_media_grounding. "
                "Не смешивай ответ с KB и не добавляй product pitch вне содержимого документа."
            )
        if response_mode == "hybrid":
            return (
                "MEDIA ROUTE: используй selected_media_grounding как документальный контекст, "
                "а kb_retrieved_facts как продуктовый KB-контекст. Не смешивай их неявно."
            )
        return ""

    def _build_final_grounding_facts(
        self,
        *,
        effective_action: str,
        allow_media_grounding: bool,
        sm_result: Dict[str, Any],
        media_turn_context: Optional[MediaTurnContext],
        kb_retrieved_facts: str,
    ) -> Dict[str, Any]:
        route = self._extract_media_route(sm_result)
        kb_facts = str(kb_retrieved_facts or "").strip()

        if not allow_media_grounding or not self._is_content_generation_action(effective_action):
            return {
                "route": {"response_mode": "normal_dialog", "selected_media_card_ids": []},
                "selected_media_cards": [],
                "selected_media_facts": [],
                "final_grounding_facts": kb_facts,
            }

        selected_media_cards = self._resolve_selected_media_cards_from_context(
            media_turn_context=media_turn_context,
            selected_ids=route["selected_media_card_ids"],
        )
        if route["response_mode"] != "normal_dialog" and not selected_media_cards:
            route = {
                "response_mode": "normal_dialog",
                "selected_media_card_ids": [],
                "route_reasoning": route.get("route_reasoning", ""),
                "route_source": "fallback",
            }

        selected_media_facts = [
            fact
            for card in selected_media_cards
            for fact in list(card.get("facts", []) or [])
        ][:8]
        selected_media_grounding = self._build_media_context_from_cards(selected_media_cards)

        if route["response_mode"] == "media_only":
            final_grounding_facts = selected_media_grounding
        elif route["response_mode"] == "hybrid":
            final_grounding_facts = "\n\n".join(
                part for part in (kb_facts, selected_media_grounding) if str(part).strip()
            ).strip()
        else:
            final_grounding_facts = kb_facts

        return {
            "route": route,
            "selected_media_cards": selected_media_cards,
            "selected_media_facts": selected_media_facts,
            "selected_media_grounding": selected_media_grounding,
            "final_grounding_facts": final_grounding_facts,
        }

    @staticmethod
    def _looks_like_media_memory_question(user_text: str) -> bool:
        text = str(user_text or "").strip().lower()
        if not text:
            return False
        field_prompts = (
            "как называется компания",
            "какая компания",
            "как зовут",
            "какое имя",
            "чем занимается",
            "из какого города",
            "какой город",
            "что это за документ",
            "что было в документе",
            "что на фото",
            "что на картинке",
            "что на видео",
            "что в презентации",
            "что там было",
            "что там написано",
            "что основное",
        )
        return any(pattern in text for pattern in field_prompts)

    def _select_media_cards(
        self,
        *,
        user_question: str,
        pending_cards: Optional[List[Dict[str, Any]]] = None,
        explicit_media_reply: bool = False,
    ) -> Dict[str, Any]:
        pending_cards = list(pending_cards or [])
        candidates = list(pending_cards) if explicit_media_reply else []
        if hasattr(self, "context_window") and hasattr(self.context_window, "episodic_memory"):
            memory = getattr(self.context_window, "episodic_memory", None)
            if memory is not None and hasattr(memory, "get_media_knowledge_candidates"):
                for candidate in memory.get_media_knowledge_candidates(user_question):
                    if candidate and candidate.get("knowledge_id") not in {
                        item.get("knowledge_id")
                        for item in candidates
                    }:
                        candidates.append(candidate)

        if not candidates:
            return {"selected_card_ids": [], "answer_from_media": False, "reason": "no_media_candidates"}

        if explicit_media_reply and pending_cards:
            selected_ids = [
                str(card.get("knowledge_id") or "")
                for card in pending_cards[:3]
                if str(card.get("knowledge_id") or "")
            ]
            return {
                "selected_card_ids": selected_ids,
                "answer_from_media": True,
                "reason": "explicit_current_media",
            }

        selector_prompt = (
            "Ты выбираешь, какие карточки знаний из прошлых media-вложений релевантны текущему сообщению клиента.\n"
            "Верни JSON с ключами selected_card_ids (список строк), answer_from_media (true/false), reason (строка).\n"
            "answer_from_media=true только если на вопрос нужно отвечать именно по media-контенту, а не вести обычный sales-диалог.\n"
            "Если не уверен, выбери answer_from_media=false.\n\n"
            f"Сообщение клиента:\n{str(user_question or '').strip()}\n\n"
            "Кандидаты:\n"
        )
        candidate_lines = []
        for card in candidates[:10]:
            facts = "; ".join(list(card.get("facts", []) or [])[:3])
            candidate_lines.append(
                json.dumps(
                    {
                        "knowledge_id": card.get("knowledge_id"),
                        "file_name": card.get("file_name"),
                        "summary": card.get("summary"),
                        "facts": facts,
                    },
                    ensure_ascii=False,
                )
            )
        selector_prompt += "\n".join(candidate_lines)

        parsed: Dict[str, Any] = {}
        try:
            raw = str(
                self.generator.llm.generate(
                    selector_prompt,
                    allow_fallback=False,
                    purpose="media_selector",
                )
                or ""
            ).strip()
        except TypeError:
            raw = str(self.generator.llm.generate(selector_prompt) or "").strip()
        except Exception as exc:
            logger.warning("media selector failed", error=str(exc))
            raw = ""

        if raw:
            parsed = self._extract_json_object(raw)

        if not parsed:
            answer_from_media = self._looks_like_media_memory_question(user_question)
            selected = [
                str(card.get("knowledge_id") or "")
                for card in candidates[:3]
                if str(card.get("knowledge_id") or "")
            ]
            return {
                "selected_card_ids": selected,
                "answer_from_media": bool(answer_from_media and selected),
                "reason": "selector_fallback",
            }

        selected_ids = [
            str(item)
            for item in list(parsed.get("selected_card_ids", []) or [])
            if str(item).strip()
        ]
        candidate_ids = {
            str(card.get("knowledge_id") or "")
            for card in candidates
            if str(card.get("knowledge_id") or "")
        }
        selected_ids = [item for item in selected_ids if item in candidate_ids][:3]
        if not selected_ids and parsed.get("answer_from_media"):
            selected_ids = [
                str(card.get("knowledge_id") or "")
                for card in candidates[:3]
                if str(card.get("knowledge_id") or "")
            ]
        return {
            "selected_card_ids": selected_ids,
            "answer_from_media": bool(parsed.get("answer_from_media") and selected_ids),
            "reason": str(parsed.get("reason") or "selector_json"),
        }

    @staticmethod
    def _extract_json_object(raw_text: str) -> Dict[str, Any]:
        text = str(raw_text or "").strip()
        if not text:
            return {}
        candidates = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start:end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    def _resolve_selected_media_cards(
        self,
        *,
        selected_ids: Sequence[str],
        pending_cards: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        selected = [str(item) for item in selected_ids if str(item).strip()]
        if not selected:
            return []
        cards_by_id: Dict[str, Dict[str, Any]] = {}
        for card in list(pending_cards or []) + self._get_recent_media_knowledge_cards(limit=20):
            card_id = str(card.get("knowledge_id") or "")
            if card_id and card_id not in cards_by_id:
                cards_by_id[card_id] = card
        return [cards_by_id[item] for item in selected if item in cards_by_id]

    def _build_media_context_from_cards(self, cards: Optional[List[Dict[str, Any]]]) -> str:
        cards = list(cards or [])
        if not cards:
            return ""
        parts: List[str] = []
        for card in cards[:3]:
            label = card.get("file_name") or card.get("media_kind") or "media"
            parts.append(f"[{label}]")
            if card.get("summary"):
                parts.append(str(card["summary"]))
            facts = list(card.get("facts", []) or [])[:4]
            if facts:
                parts.append("Факты:")
                parts.extend(f"- {fact}" for fact in facts)
            if card.get("answer_context"):
                parts.append(str(card["answer_context"]))
        return "\n".join(parts).strip()

    def _generate_media_grounded_response(
        self,
        *,
        user_question: str,
        answer_context: str,
        purpose: str,
    ) -> str:
        cleaned_question = str(user_question or "").strip() or "Объясни, что содержится во вложении."
        cleaned_context = str(answer_context or "").strip()
        if not cleaned_context:
            return "Не вижу достаточно данных, чтобы точно ответить по этому вложению."

        prompt = (
            "Ты отвечаешь клиенту только по содержимому media-вложения или сохранённым фактам из него.\n"
            "Не ссылайся на базу знаний Wipon, не предлагай продукт, не проси контакты.\n"
            "Если в контексте нет ответа, честно скажи об этом.\n"
            "Ответь по-русски, коротко и по делу.\n\n"
            f"Вопрос клиента:\n{cleaned_question}\n\n"
            f"Контекст:\n{cleaned_context}\n"
        )

        try:
            response = str(
                self.generator.llm.generate(
                    prompt,
                    allow_fallback=False,
                    purpose=purpose,
                ) or ""
            ).strip()
        except TypeError:
            response = str(self.generator.llm.generate(prompt) or "").strip()
        except Exception as exc:
            logger.warning("media-grounded response generation failed", error=str(exc), purpose=purpose)
            response = ""

        if response:
            response = re.sub(
                r"^(?:здравствуйте|добрый день|добрый вечер)[^.!?]*[.!?]\s*",
                "",
                response,
                flags=re.IGNORECASE,
            ).strip()
        return response or cleaned_context.splitlines()[0].strip()

    def _build_media_process_result(
        self,
        *,
        user_message: str,
        raw_user_message: str,
        response: str,
        intent: str,
        confidence: float,
        current_state: str,
        tone_info: Dict[str, Any],
        extracted_data: Dict[str, Any],
        media_facts: Optional[List[str]],
        media_cards_to_store: Optional[List[Dict[str, Any]]] = None,
        trace_builder: Optional[DecisionTraceBuilder],
        reason_code: str,
        action: str,
    ) -> Dict[str, Any]:
        self.state_machine.update_data(extracted_data or {})
        self.history.append({"user": user_message, "bot": response})

        self.context_window.add_turn_from_dict(
            user_message=user_message,
            bot_response=response,
            intent=intent,
            confidence=confidence,
            action=action,
            state=current_state,
            next_state=current_state,
            method="media",
            extracted_data=extracted_data,
            is_fallback=False,
            fallback_tier=None,
            fact_keys_used=[],
            response_embedding=None,
        )
        self._store_media_knowledge_cards(media_cards_to_store)

        self.last_action = action
        self.last_intent = intent
        self.last_bot_message = response

        self._record_turn_metrics(
            state=current_state,
            intent=intent,
            tone=tone_info.get("tone"),
            fallback_used=False,
            fallback_tier=None,
        )
        if flags.metrics_tracking:
            for key, value in (extracted_data or {}).items():
                if value:
                    self.metrics.record_collected_data(key, value)

        if extracted_data or media_facts or media_cards_to_store:
            self.guard.record_progress()

        decision_trace_dict = None
        if trace_builder:
            trace_builder.record_response(
                template_key=reason_code,
                requested_action=action,
                response_text=response,
                elapsed_ms=0.0,
                cta_added=False,
                cta_type=None,
            )
            decision_trace_dict = self._build_decision_trace_dict(
                trace_builder=trace_builder,
                fallback_used=False,
                fallback_tier=None,
                intervention=None,
                fallback_action=None,
                fallback_message=None,
            )

        return self._build_process_result(
            response=response,
            intent=intent,
            action=action,
            state=current_state,
            is_final=False,
            confidence=confidence,
            spin_phase=self.state_machine.current_phase,
            visited_states=[current_state],
            initial_state=current_state,
            fallback_used=False,
            fallback_tier=None,
            tone=tone_info.get("tone"),
            frustration_level=tone_info.get("frustration_level"),
            lead_score=self.lead_scorer.current_score if flags.lead_scoring else None,
            objection_detected=False,
            reason_codes=[reason_code],
            resolution_trace={},
            options=None,
            cta_result=CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason=reason_code,
            ),
            decision_trace=decision_trace_dict,
        )

    def _build_forced_process_result(
        self,
        *,
        user_message: str,
        response: str,
        intent: str,
        confidence: float,
        current_state: str,
        next_state: str,
        tone_info: Dict[str, Any],
        extracted_data: Dict[str, Any],
        media_facts: Optional[List[str]],
        media_cards_to_store: Optional[List[Dict[str, Any]]],
        trace_builder: Optional[DecisionTraceBuilder],
        action: str,
        is_final: bool,
        spin_phase: Optional[str],
        visited_states: Optional[List[str]],
        initial_state: str,
        reason_codes: Optional[List[str]],
        resolution_trace: Optional[Dict[str, Any]],
        lead_score: Optional[float],
        objection_detected: bool,
        method: str,
    ) -> Dict[str, Any]:
        self.state_machine.update_data(extracted_data or {})
        self.history.append({"user": user_message, "bot": response})

        self.context_window.add_turn_from_dict(
            user_message=user_message,
            bot_response=response,
            intent=intent,
            confidence=confidence,
            action=action,
            state=current_state,
            next_state=next_state,
            method=method,
            extracted_data=extracted_data,
            is_fallback=False,
            fallback_tier=None,
            fact_keys_used=[],
            response_embedding=None,
        )
        self._store_media_knowledge_cards(media_cards_to_store)

        if self.action_tracker and self.last_action:
            turn_type = "NEUTRAL"
            if hasattr(self.context_window, "get_last_turn_type"):
                turn_type = self.context_window.get_last_turn_type() or "NEUTRAL"
            self.action_tracker.record_outcome(
                action=self.last_action,
                turn_type=turn_type,
                intent=intent,
            )

        self.last_action = action
        self.last_intent = intent
        self.last_bot_message = response

        self._record_turn_metrics(
            state=next_state,
            intent=intent,
            tone=tone_info.get("tone"),
            fallback_used=False,
            fallback_tier=None,
        )
        if flags.metrics_tracking:
            for key, value in (extracted_data or {}).items():
                if value:
                    self.metrics.record_collected_data(key, value)

        if current_state != next_state or extracted_data or media_facts or media_cards_to_store:
            self.guard.record_progress()

        decision_trace_dict = None
        if trace_builder:
            trace_builder.record_response(
                template_key=action,
                requested_action=action,
                response_text=response,
                elapsed_ms=0.0,
                cta_added=False,
                cta_type=None,
            )
            decision_trace_dict = self._build_decision_trace_dict(
                trace_builder=trace_builder,
                fallback_used=False,
                fallback_tier=None,
                intervention=None,
                fallback_action=None,
                fallback_message=None,
            )

        return self._build_process_result(
            response=response,
            intent=intent,
            action=action,
            state=next_state,
            is_final=is_final,
            confidence=confidence,
            spin_phase=spin_phase,
            visited_states=visited_states,
            initial_state=initial_state,
            fallback_used=False,
            fallback_tier=None,
            tone=tone_info.get("tone"),
            frustration_level=tone_info.get("frustration_level"),
            lead_score=lead_score,
            objection_detected=objection_detected,
            reason_codes=reason_codes or [],
            resolution_trace=resolution_trace or {},
            options=None,
            cta_result=CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="forced_misroute_response",
            ),
            decision_trace=decision_trace_dict,
        )

    def _build_decision_trace_dict(
        self,
        trace_builder: Optional[DecisionTraceBuilder],
        fallback_used: bool,
        fallback_tier: Optional[str],
        intervention: Optional[str],
        fallback_action: Optional[str],
        fallback_message: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Build and persist decision trace dict when tracing is enabled."""
        if not trace_builder:
            return None

        if fallback_used:
            trace_builder.record_fallback(
                tier=fallback_tier,
                reason=intervention,
                action=fallback_action,
                message=fallback_message,
            )

        decision_trace = trace_builder.build()
        self._decision_traces.append(decision_trace)
        return decision_trace.to_dict()

    @staticmethod
    def _build_process_result(
        *,
        response: str,
        intent: str,
        action: str,
        state: str,
        is_final: bool,
        confidence: float,
        spin_phase: Optional[str] = None,
        visited_states: Optional[List[str]] = None,
        initial_state: str = "",
        fallback_used: bool = False,
        fallback_tier: Optional[str] = None,
        tone: Optional[str] = None,
        frustration_level: Optional[int] = None,
        lead_score: Optional[float] = None,
        objection_detected: bool = False,
        reason_codes: Optional[List[str]] = None,
        resolution_trace: Optional[Dict[str, Any]] = None,
        options: Any = None,
        cta_result: Optional[CTAResult] = None,
        decision_trace: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Unified output payload for process() returns."""
        return {
            "response": response,
            "intent": intent,
            "action": action,
            "state": state,
            "is_final": is_final,
            "confidence": confidence,
            "spin_phase": spin_phase,
            "visited_states": visited_states or [],
            "initial_state": initial_state,
            "fallback_used": fallback_used,
            "fallback_tier": fallback_tier,
            "tone": tone,
            "frustration_level": frustration_level,
            "lead_score": lead_score,
            "objection_detected": objection_detected,
            "reason_codes": reason_codes or [],
            "resolution_trace": resolution_trace or {},
            "options": options,
            "cta_added": cta_result.cta_added if cta_result else False,
            "cta_text": cta_result.cta if cta_result else None,
            "decision_trace": decision_trace,
        }

    def process(
        self,
        user_message: str,
        *,
        media_turn_context: Optional[MediaTurnContext] = None,
    ) -> Dict:
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
        pending_media_meta = self._consume_pending_media_meta()
        current_turn_number = (
            self.context_window.get_total_turn_count() + 1
            if hasattr(self, "context_window") and hasattr(self.context_window, "get_total_turn_count")
            else 1
        )

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
        autonomous_media_runtime = self._is_autonomous_media_runtime(current_state)

        resolved_media_turn_context: Optional[MediaTurnContext] = None
        legacy_pending_media_cards: List[Dict[str, Any]] = []
        legacy_pending_media_safe_fields: Dict[str, Any] = {}

        if autonomous_media_runtime:
            resolved_media_turn_context = self._resolve_media_turn_context(
                explicit_media_turn_context=media_turn_context,
                pending_media_meta=pending_media_meta,
                current_turn_number=current_turn_number,
                fallback_user_message=user_message,
            )
        elif pending_media_meta:
            legacy_pending_media_cards = self._finalize_media_cards(
                list((pending_media_meta or {}).get("knowledge_cards", []) or []),
                source_session_id=str((pending_media_meta or {}).get("source_session_id") or ""),
                source_turn=current_turn_number,
            )
            if not legacy_pending_media_cards:
                legacy_pending_media_cards = self._compat_media_cards_from_meta(
                    pending_media_meta,
                    source_session_id=str((pending_media_meta or {}).get("source_session_id") or ""),
                    source_turn=current_turn_number,
                )
            legacy_pending_media_safe_fields = self._extract_safe_media_fields(legacy_pending_media_cards)

        raw_user_message = str(
            (
                resolved_media_turn_context.raw_user_text
                if resolved_media_turn_context is not None
                else (pending_media_meta.get("source_user_text") if pending_media_meta else "")
            )
            or user_message
            or ""
        ).strip()
        visible_user_message = raw_user_message if autonomous_media_runtime else str(user_message or "").strip()
        current_media_cards = (
            [scrub_media_card_payload(card) for card in tuple(resolved_media_turn_context.current_cards or ())]
            if resolved_media_turn_context is not None
            else legacy_pending_media_cards
        )
        current_media_safe_fields = (
            dict(resolved_media_turn_context.safe_extracted_data or {})
            if resolved_media_turn_context is not None
            else legacy_pending_media_safe_fields
        )
        media_facts = (
            list(resolved_media_turn_context.safe_media_facts or ())
            if resolved_media_turn_context is not None
            else list(pending_media_meta.get("media_facts", []) or [])
        )

        trace_builder: Optional[DecisionTraceBuilder] = None
        if self._enable_decision_tracing:
            trace_builder = DecisionTraceBuilder(turn=self.turn + 1, message=visible_user_message)

        # FIX: Track all visited states during this turn for accurate phase coverage
        # This is critical for cases like fallback skip where bot transitions through
        # intermediate states (e.g., greeting -> spin_situation -> spin_problem)
        initial_state = current_state
        visited_states = [initial_state]  # Start with initial state
        bot_transition_markers: List[Dict[str, Any]] = []
        pending_bot_reason_codes: List[str] = []

        # Phase 2: Analyze tone
        tone_start = time.time()
        tone_info = self._analyze_tone(visible_user_message)
        frustration_level = tone_info.get("frustration_level", 0)
        tone_elapsed = (time.time() - tone_start) * 1000

        # Decision Tracing: Record tone analysis
        if trace_builder:
            trace_builder.record_tone(tone_info, elapsed_ms=tone_elapsed)

        # FIX 1: Classify intent BEFORE guard check so guard uses current intent
        classification_start = time.time()
        classifier_input = visible_user_message
        if (
            resolved_media_turn_context is not None
            and resolved_media_turn_context.attachment_only
            and not visible_user_message.strip()
        ):
            classifier_input = "[attachment-only-media]"
        classification = self.classifier.classify(classifier_input, current_context)
        intent = classification["intent"]
        extracted = self._merge_extracted_data(
            classification.get("extracted_data", {}),
            current_media_safe_fields
            or (
                pending_media_meta.get("extracted_data", {})
                if pending_media_meta and not autonomous_media_runtime
                else {}
            ),
        )
        classification["extracted_data"] = extracted
        classification_confidence = float(classification.get("confidence", 0.0) or 0.0)
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
                message=visible_user_message,
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
                            "user": visible_user_message,
                            "bot": fb_result["response"]
                        })

                        self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)
                        if trace_builder:
                            trace_builder.record_response(
                                template_key="soft_close",
                                requested_action="soft_close",
                                response_text=fb_result["response"],
                                elapsed_ms=0.0,
                            )
                        decision_trace_dict = self._build_decision_trace_dict(
                            trace_builder=trace_builder,
                            fallback_used=True,
                            fallback_tier=intervention,
                            intervention=intervention,
                            fallback_action="close",
                            fallback_message=fb_result.get("response"),
                        )
                        return self._build_process_result(
                            response=fb_result["response"],
                            intent="fallback_close",
                            action="soft_close",
                            state="soft_close",
                            is_final=True,
                            confidence=classification_confidence,
                            visited_states=[initial_state, "soft_close"],
                            initial_state=initial_state,
                            fallback_used=True,
                            fallback_tier=intervention,
                            tone=tone_info.get("tone"),
                            frustration_level=frustration_level,
                            options=fb_result.get("options"),
                            decision_trace=decision_trace_dict,
                        )

                    # FIX: Handle "skip" action - apply state transition to break loops
                    # FIX (Distributed State Mutation): Use transition_to() for atomic update
                    elif fb_result.get("action") == "skip" and fb_result.get("next_state"):
                        skip_result = self._sanitize_transition_target(
                            requested_state=fb_result["next_state"],
                            current_state=current_state,
                            source="bot.fallback_skip",
                        )
                        bot_transition_markers.append({
                            **skip_result.diagnostic,
                            "path": "fallback_skip",
                        })
                        if skip_result.sanitized and skip_result.reason_code:
                            pending_bot_reason_codes.append(skip_result.reason_code)

                        skip_next_state = skip_result.effective_state
                        transition_ok = self.state_machine.transition_to(
                            next_state=skip_next_state,
                            action="skip",
                            source="fallback_skip",
                        )
                        if not transition_ok:
                            skip_next_state = self.state_machine.state
                            bot_transition_markers[-1]["transition_ok"] = False
                            bot_transition_markers[-1]["post_transition_state"] = skip_next_state
                        else:
                            bot_transition_markers[-1]["transition_ok"] = True
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
            competitor_name = self._extract_competitor_name(visible_user_message)
            if competitor_name:
                self.state_machine.collected_data["competitor_name"] = competitor_name

        # disambiguation_needed intent: in autonomous flow avoid options menus in the
        # middle of sales dialogue; continue with best available semantic intent.
        if intent == "disambiguation_needed":
            options = classification.get("disambiguation_options", [])
            if self._flow and self._flow.name == "autonomous":
                intent = (
                    classification.get("original_intent")
                    or (options[0].get("intent") if options and isinstance(options[0], dict) else None)
                    or "unclear"
                )
                classification["intent"] = intent
                classification["disambiguation_options"] = []
            elif not options:
                intent = classification.get("original_intent", "unclear")
                classification["intent"] = intent

        # Phase 3: Check for objection
        objection_info = None
        if not (self._flow and self._flow.name == "autonomous"):
            objection_info = self._check_objection(visible_user_message, collected_data)

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
                user_message=visible_user_message,
                last_bot_message=self.last_bot_message or "",
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
        prepared_response_ctx: Optional[Dict[str, Any]] = None

        merged_autonomous_enabled = bool(
            self._flow
            and self._flow.name == "autonomous"
            and flags.is_enabled("merged_autonomous_call")
        )
        should_prepare_autonomous_response_context = bool(
            self._flow
            and self._flow.name == "autonomous"
            and (current_state.startswith("autonomous_") or current_state == "greeting")
        )

        if should_prepare_autonomous_response_context:
            try:
                prepared_response_ctx = self.generator.prepare_response_context(
                    state=current_state,
                    context={
                        "action": "autonomous_respond",
                        "user_message": visible_user_message,
                        "intent": intent,
                        "state": current_state,
                        "history": self.history,
                        "goal": self._flow.states.get(current_state, {}).get("goal", ""),
                        "collected_data": self.state_machine.collected_data,
                        "missing_data": [
                            field
                            for field in self._flow.states.get(current_state, {}).get("required_data", [])
                            if not self.state_machine.collected_data.get(field)
                        ],
                        "spin_phase": self._flow.states.get(current_state, {}).get("phase"),
                        "tone_instruction": tone_info.get("tone_instruction", ""),
                        "style_instruction": tone_info.get("style_instruction", ""),
                        "frustration_level": frustration_level,
                        "should_apologize": tone_info.get("should_apologize", False),
                        "should_offer_exit": tone_info.get("should_offer_exit", False),
                        "objection_info": objection_info,
                        "context_envelope": context_envelope,
                        "response_directives": response_directives,
                        "recent_fact_keys": list(self.context_window.get_recent_fact_keys(3)),
                        "style_modifiers": classification.get("style_modifiers", []),
                        "secondary_signals": classification.get("secondary_signals", []),
                        "semantic_frame": classification.get("semantic_frame", {}),
                        "style_separation_applied": classification.get("style_separation_applied", False),
                        "media_turn_context": resolved_media_turn_context,
                        "terminal_state_requirements": self._flow.states.get(current_state, {}).get(
                            "terminal_state_requirements", {}
                        ),
                    },
                )
                self._orchestrator.blackboard.set_response_context(
                    prepared_response_ctx if merged_autonomous_enabled else None
                )
            except Exception as e:
                logger.warning("prepare_response_context failed", error=str(e))
                prepared_response_ctx = None
                self._orchestrator.blackboard.set_response_context(None)
        else:
            self._orchestrator.blackboard.set_response_context(None)

        # =========================================================================
        # Stage 14: Blackboard replaces state_machine.process()
        # =========================================================================
        # БЫЛО:
        #   sm_result = self.state_machine.process(
        #       intent, extracted, context_envelope=context_envelope
        #   )
        #
        # СТАЛО:
        # Собираем dialog history для decision LLM (последние 4 хода)
        decision_dialog_history = []
        _recent_for_decision = self.context_window.get_last_n_turns(4)
        for _t in _recent_for_decision:
            decision_dialog_history.append({
                "user": (_t.user_message or "")[:200],
                "bot": (_t.bot_response or "")[:250],
            })

        sm_start = time.time()
        decision = self._orchestrator.process_turn(
            intent=intent,
            extracted_data=extracted,
            context_envelope=context_envelope,
            user_message=visible_user_message,
            frustration_level=frustration_level,
            dialog_history=decision_dialog_history,
            media_turn_context=resolved_media_turn_context,
        )
        # Convert to sm_result dict for compatibility with DialoguePolicy/Generator
        sm_result = decision.to_sm_result()

        # Attach bot-level sanitization diagnostics collected before orchestrator call.
        for marker in bot_transition_markers:
            self._append_bot_sanitization_marker(sm_result, marker)
        for reason_code in pending_bot_reason_codes:
            self._append_reason_code(sm_result, reason_code)

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
                    policy_result = self._sanitize_transition_target(
                        requested_state=policy_override.next_state,
                        current_state=self.state_machine.state,
                        source="bot.policy_override",
                    )
                    policy_marker = {
                        **policy_result.diagnostic,
                        "path": "policy_override",
                        "decision": policy_override.decision.value,
                    }
                    self._append_bot_sanitization_marker(sm_result, policy_marker)
                    if policy_result.sanitized and policy_result.reason_code:
                        self._append_reason_code(sm_result, policy_result.reason_code)

                    # Apply ONLY effective state from sanitizer.
                    transition_ok = self.state_machine.transition_to(
                        next_state=policy_result.effective_state,
                        action=policy_override.action,
                        source="policy_override",
                    )
                    if transition_ok:
                        sm_result["next_state"] = policy_result.effective_state
                        policy_marker["transition_ok"] = True
                    else:
                        sm_result["next_state"] = self.state_machine.state
                        policy_marker["transition_ok"] = False
                        policy_marker["post_transition_state"] = self.state_machine.state

        # Decision Tracing: Record policy override
        if trace_builder:
            trace_builder.record_policy_override(policy_override)

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

        # Determine action
        action = sm_result["action"]
        next_state = sm_result["next_state"]
        is_final = sm_result["is_final"]
        route_media_grounding_allowed = True

        forced_misroute_responses = {
            "misroute_wipon_outage": (
                "redirect_misroute_wipon_outage",
                "Здравствуйте! Извините за неудобства. Вы обратились в отдел продаж. "
                "Пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
                "Извините за неудобства. Вы обратились в отдел продаж. "
                "Пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
            ),
            "misroute_pending_delivery": (
                "redirect_misroute_pending_delivery",
                "Здравствуйте! Извините за неудобства. Вы обратились в отдел продаж. По вопросам оборудования и доставки, "
                "пожалуйста, свяжитесь с менеджером по оборудованию: +77087010744.",
                "Извините за неудобства. Вы обратились в отдел продаж. По вопросам оборудования и доставки, "
                "пожалуйста, свяжитесь с менеджером по оборудованию: +77087010744.",
            ),
            "misroute_training_support": (
                "redirect_misroute_training_support",
                "Здравствуйте! Извините за неудобства. Вы обратились в отдел продаж. "
                "По вопросам обучения, пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
                "Извините за неудобства. Вы обратились в отдел продаж. "
                "По вопросам обучения, пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
            ),
            "misroute_technical_support": (
                "redirect_misroute_technical_support",
                "Здравствуйте! Извините за неудобства. Вы обратились в отдел продаж. Пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
                "Извините за неудобства. Вы обратились в отдел продаж. Пожалуйста, свяжитесь с технической поддержкой: +77070202019.",
            ),
        }
        if intent in forced_misroute_responses:
            forced_action, first_turn_response, followup_response = forced_misroute_responses[intent]
            forced_response = first_turn_response if not self.history else followup_response
            forced_reason_codes = list(sm_result.get("reason_codes", []))
            forced_reason_codes.append("forced_misroute_response")
            return self._build_forced_process_result(
                user_message=visible_user_message,
                response=forced_response,
                intent=intent,
                confidence=classification_confidence,
                current_state=current_state,
                next_state=next_state,
                tone_info=tone_info,
                extracted_data=extracted,
                media_facts=media_facts,
                media_cards_to_store=current_media_cards,
                trace_builder=trace_builder,
                action=forced_action,
                is_final=is_final,
                spin_phase=sm_result.get("spin_phase"),
                visited_states=visited_states,
                initial_state=initial_state,
                reason_codes=forced_reason_codes,
                resolution_trace=sm_result.get("resolution_trace", {}),
                lead_score=self.lead_scorer.current_score if flags.lead_scoring else None,
                objection_detected=objection_info is not None,
                method=classification.get("method", "unknown"),
            )

        # Autonomous action normalization:
        # In autonomous flow, non-structural actions should resolve through
        # autonomous_respond (including greeting stage), keeping generation
        # logic in a single autonomous template family.
        if (
            self._flow
            and self._flow.name == "autonomous"
            and (
                self.state_machine.state.startswith("autonomous_")
                or self.state_machine.state == "greeting"
            )
        ):
            structural_actions = {
                "guard_offer_options",
                "guard_rephrase",
                "guard_skip_phase",
                "guard_soft_close",
                "stall_guard_eject",
                "stall_guard_nudge",
                "redirect_after_repetition",
                "escalate_repeated_content",
            }
            if action in structural_actions or action == "ask_clarification":
                route_media_grounding_allowed = False
            current_state = self.state_machine.state
            keep_greeting_action = (action == "greet_back" and current_state == "greeting")
            if (
                action not in structural_actions
                and action != "autonomous_respond"
                and not keep_greeting_action
            ):
                logger.info(
                    "Autonomous action normalization: action -> autonomous_respond",
                    original_action=action,
                    current_state=current_state,
                    next_state=next_state,
                )
                action = "autonomous_respond"
                self._append_reason_code(sm_result, "autonomous_action_normalized")

            # In autonomous dialogue stages, avoid disambiguation UI jumps.
            if action == "ask_clarification":
                logger.info(
                    "Autonomous clarification normalization: ask_clarification -> autonomous_respond",
                    current_state=self.state_machine.state,
                    next_state=next_state,
                )
                action = "autonomous_respond"
                self._append_reason_code(sm_result, "autonomous_clarification_normalized")

        # In soft_close, keep template/action stable and avoid missing-template fallbacks.
        if (
            self._flow
            and self._flow.name == "autonomous"
            and self.state_machine.state == "soft_close"
            and action in {"say_goodbye", "handle_objection", "respond_briefly"}
        ):
            action = "soft_close"
            self._append_reason_code(sm_result, "autonomous_soft_close_action_normalized")

        # 9e: Set rephrase_mode for guard_rephrase action (new pipeline path)
        if flags.conversation_guard_in_pipeline and action == "guard_rephrase":
            rephrase_mode = True
            if response_directives:
                response_directives.rephrase_mode = True

        # Remap stall_guard actions to valid template actions
        if action == "stall_guard_eject":
            if (
                self._flow
                and self._flow.name == "autonomous"
            ):
                # In autonomous flow, avoid transition_to_* template paths.
                # Let state transition happen structurally via next_state.
                if next_state == "soft_close":
                    action = "soft_close"
                elif next_state == "close":
                    action = "close"
                else:
                    action = "autonomous_respond"
            else:
                action = f"transition_to_{next_state}"
                # Fallback to continue_current_goal if specific transition template doesn't exist
                if not self.generator._get_template(action):
                    action = "continue_current_goal"
        elif action == "stall_guard_nudge":
            if self._flow and self._flow.name == "autonomous":
                action = "autonomous_respond"
            else:
                action = "continue_conversation"
                if not self.generator._get_template(action):
                    action = "continue_current_goal"

        kb_retrieved_facts = ""
        retrieved_urls = ""
        grounding_contract_version = None
        if isinstance(prepared_response_ctx, dict):
            kb_retrieved_facts = str(
                prepared_response_ctx.get("kb_retrieved_facts")
                or prepared_response_ctx.get("retrieved_facts")
                or ""
            )
            retrieved_urls = str(prepared_response_ctx.get("retrieved_urls") or "")
            grounding_contract_version = prepared_response_ctx.get("grounding_contract_version")

        final_grounding = self._build_final_grounding_facts(
            effective_action=action,
            allow_media_grounding=route_media_grounding_allowed,
            sm_result=sm_result,
            media_turn_context=resolved_media_turn_context,
            kb_retrieved_facts=kb_retrieved_facts,
        )
        media_route_mode = str(final_grounding["route"].get("response_mode") or "normal_dialog")
        selected_media_cards = final_grounding["selected_media_cards"]
        selected_media_facts = final_grounding["selected_media_facts"]
        selected_media_grounding = str(final_grounding.get("selected_media_grounding") or "")
        final_grounding_facts = final_grounding["final_grounding_facts"]
        media_route_instruction = self._build_media_route_instruction(
            response_mode=media_route_mode,
            selected_media_grounding=selected_media_grounding,
        )

        if (
            context_envelope
            and self._is_content_generation_action(action)
            and media_route_mode in {"media_only", "hybrid"}
        ):
            context_envelope.client_media_facts = selected_media_facts[:3]

        if flags.context_response_directives and context_envelope:
            response_directives = build_response_directives(
                context_envelope,
                config=self._config.response_directives,
            )
        else:
            response_directives = None

        if rephrase_mode and response_directives:
            response_directives.rephrase_mode = True

        directive_instruction = response_directives.get_instruction() if response_directives else ""
        context = {
            "user_message": visible_user_message,
            "intent": intent,
            "state": sm_result["next_state"],
            "history": self.history,
            "is_first_bot_reply": len(self.history) == 0,
            "goal": sm_result["goal"],
            "collected_data": sm_result["collected_data"],
            "missing_data": sm_result["missing_data"],
            "spin_phase": sm_result.get("spin_phase"),
            "optional_data": sm_result.get("optional_data", []),
            "tone_instruction": " ".join(
                filter(None, [directive_instruction, tone_info.get("tone_instruction", "")])
            ),
            "style_instruction": tone_info.get("style_instruction", ""),
            "frustration_level": frustration_level,
            "should_apologize": tone_info.get("should_apologize", False),
            "should_offer_exit": tone_info.get("should_offer_exit", False),
            "objection_info": objection_info,
            "last_action": self.last_action,
            "policy_reason_codes": policy_override.reason_codes if policy_override else [],
            "context_envelope": context_envelope,
            "action_tracker": self.action_tracker,
            "user_messages": [turn.get("user", "") for turn in self.history[-5:]] + [visible_user_message],
            "response_directives": response_directives,
            "recent_fact_keys": list(self.context_window.get_recent_fact_keys(3)),
            "fact_keys": (prepared_response_ctx or {}).get("fact_keys", []),
            "style_modifiers": classification.get("style_modifiers", []),
            "secondary_signals": classification.get("secondary_signals", []),
            "semantic_frame": classification.get("semantic_frame", {}),
            "style_separation_applied": classification.get("style_separation_applied", False),
            "terminal_state_requirements": sm_result.get("terminal_state_requirements", {}),
            "retrieved_facts": final_grounding_facts,
            "retrieved_urls": retrieved_urls,
            "media_route_mode": media_route_mode,
            "selected_media_grounding": selected_media_grounding,
            "kb_retrieved_facts": kb_retrieved_facts,
            "final_grounding_facts": final_grounding_facts,
            "media_route_instruction": media_route_instruction,
            "media_turn_context": resolved_media_turn_context,
            "_skip_retrieval": self._is_content_generation_action(action) and isinstance(prepared_response_ctx, dict),
        }
        if grounding_contract_version is not None:
            context["grounding_contract_version"] = grounding_contract_version

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
        generator_used: bool = False
        pre_gen = self._orchestrator.blackboard.get_pre_generated_response()
        merged_retrieved_facts = final_grounding_facts

        # If objection detected and needs soft close - override state machine result
        # In autonomous states, ObjectionGuardSource (blackboard-native) handles limits
        current_state_config = self._flow.states.get(self.state_machine.state, {})
        is_autonomous = (
            current_state_config.get("autonomous", False)
            or (
                self._flow
                and self._flow.name == "autonomous"
                and self.state_machine.state == "greeting"
            )
        )
        if (objection_info and objection_info.get("should_soft_close")
                and not is_autonomous):
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
        elif pre_gen and not fallback_response and action in ("autonomous_respond", "continue_current_goal"):
            response_start = time.time()
            processed, validation_events = self.generator.post_process_only(
                response=pre_gen,
                context=context,
                requested_action=action,
                selected_template_key=action,
                retrieved_facts=merged_retrieved_facts,
            )
            response = processed
            response_elapsed = (time.time() - response_start) * 1000
            generator_used = False
            self.generator._add_to_response_history(response)
            self.generator._compute_and_cache_response_embedding(response)
            self.generator._last_generation_meta = {
                "requested_action": action,
                "selected_template_key": action,
                "validation_events": validation_events,
                "fact_keys": (prepared_response_ctx or {}).get("fact_keys", []),
                **self.generator._last_factual_verifier_meta,
                **self.generator._last_postprocess_meta,
            }
            cta_result = CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="pre_generated_response",
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
                generator_used = True
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
                generator_used = True
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
            generator_used = True
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
            generator_used = True
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
            self.history.append({"user": visible_user_message, "bot": response})
            self._finalize_metrics(ConversationOutcome.SOFT_CLOSE)
            if trace_builder:
                trace_builder.record_response(
                    template_key="soft_close",
                    requested_action="soft_close",
                    response_text=response,
                    elapsed_ms=response_elapsed,
                )
            decision_trace_dict = self._build_decision_trace_dict(
                trace_builder=trace_builder,
                fallback_used=True,
                fallback_tier="soft_close",
                intervention=intervention,
                fallback_action="guard_soft_close",
                fallback_message=response,
            )
            return self._build_process_result(
                response=response,
                intent="fallback_close",
                action="soft_close",
                state="soft_close",
                is_final=True,
                confidence=classification_confidence,
                visited_states=[initial_state, "soft_close"],
                initial_state=initial_state,
                fallback_used=True,
                fallback_tier="soft_close",
                tone=tone_info.get("tone"),
                frustration_level=frustration_level,
                decision_trace=decision_trace_dict,
            )
        else:
            # Defense-in-depth: verify template exists before generation
            if not self.generator._get_template(action):
                original_action = action
                # Universal runtime fallback: choose a neutral action with an existing template.
                preferred = (
                    "autonomous_respond"
                    if getattr(self._flow, "name", "") == "autonomous"
                    else "continue_current_goal"
                )
                fallback_candidates = (
                    preferred,
                    "continue_current_goal",
                    "answer_and_continue",
                )
                action = next(
                    (candidate for candidate in fallback_candidates if self.generator._get_template(candidate)),
                    "continue_current_goal",
                )
                logger.warning(
                    "Runtime template miss — neutral fallback applied",
                    original_action=original_action,
                    fallback_action=action,
                    intent=intent,
                    flow=self._flow.name,
                )
            # 3. Generate response (normal path)
            response_start = time.time()
            response = self.generator.generate(action, context)
            generator_used = True
            response_elapsed = (time.time() - response_start) * 1000

            # Phase 3: Apply CTA BEFORE recording response (critical fix!)
            # NOTE: CTA is independent of question suppression by design —
            # CTA drives conversion ("Хотите демо?"), not qualification questions.
            # Pass action + objection_info for semantic CTA gating
            cta_result = self._apply_cta(
                response=response,
                state=next_state,
                context={
                    "frustration_level": frustration_level,
                    "last_action": self.last_action,
                    "action": action,
                    "intent": intent,
                    "objection_info": objection_info,
                    "user_message": visible_user_message,
                    # Pass collected_data for contact gate
                    "collected_data": self.state_machine.collected_data,
                    "history": self.history,
                    # Keep CTA aligned with response directives
                    "question_mode": (
                        response_directives.question_mode if response_directives else "adaptive"
                    ),
                    "tone": tone_info.get("tone"),
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
            selected_template_key = action
            requested_action = action
            if generator_used and hasattr(self.generator, "get_last_generation_meta"):
                generation_meta = self.generator.get_last_generation_meta() or {}
                selected_template_key = generation_meta.get("selected_template_key") or action
                requested_action = generation_meta.get("requested_action") or action
            trace_builder.record_response(
                template_key=selected_template_key,
                requested_action=requested_action,
                response_text=response,
                elapsed_ms=response_elapsed,
                cta_added=cta_result.cta_added,
                cta_type=cta_result.cta[:30] if cta_result.cta else None,
            )

        # 4. Save to history
        self.history.append({
            "user": visible_user_message,
            "bot": response
        })

        # 4.1 Save to context window (расширенный контекст)
        # Extract fact_keys from generator metadata for fact rotation tracking
        _gen_meta = self.generator.get_last_generation_meta() if hasattr(self.generator, "get_last_generation_meta") else {}
        _fact_keys = _gen_meta.get("fact_keys", [])
        # Response embedding for content repetition detection.
        # Only when generator was used — for fallback/guard paths generator.generate()
        # is NOT called, so get_last_response_embedding() would return STALE data (I15).
        _response_embedding = (
            self.generator.get_last_response_embedding()
            if generator_used and hasattr(self.generator, "get_last_response_embedding")
            else None
        )
        self.context_window.add_turn_from_dict(
            user_message=visible_user_message,
            bot_response=response,
            intent=intent,
            confidence=classification_confidence,
            action=action,
            state=current_state,
            next_state=next_state,
            method=classification.get("method", "unknown"),
            extracted_data=extracted,
            is_fallback=fallback_used,
            fallback_tier=fallback_tier,
            fact_keys_used=_fact_keys,
            response_embedding=_response_embedding,
        )
        self._store_media_knowledge_cards(current_media_cards)

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
        is_success = is_final or next_state in (
            "success", "payment_ready", "video_call_scheduled"
        )

        if is_success:
            # Новые terminal states: payment_ready / video_call_scheduled
            if next_state == "payment_ready":
                from src.yaml_config.constants import notify_operator_on_success
                self._finalize_metrics(ConversationOutcome.PAYMENT_READY)
                notify_operator_on_success(
                    outcome="payment_ready",
                    collected_data=self.state_machine.collected_data,
                    conversation_id=self.conversation_id,
                )
            elif next_state == "video_call_scheduled":
                from src.yaml_config.constants import notify_operator_on_success
                self._finalize_metrics(ConversationOutcome.VIDEO_CALL_SCHEDULED)
                notify_operator_on_success(
                    outcome="video_call_scheduled",
                    collected_data=self.state_machine.collected_data,
                    conversation_id=self.conversation_id,
                )
            # Определяем тип успеха по приоритету (legacy paths)
            elif intent == "rejection":
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
        if sm_result["prev_state"] != next_state or extracted or media_facts or current_media_cards:
            self.guard.record_progress()

        # Decision Tracing: Build and store final trace
        decision_trace_dict = self._build_decision_trace_dict(
            trace_builder=trace_builder,
            fallback_used=fallback_used,
            fallback_tier=fallback_tier,
            intervention=intervention,
            fallback_action=fallback_action,
            fallback_message=fallback_message,
        )

        return self._build_process_result(
            response=response,
            intent=intent,
            action=action,
            state=next_state,
            is_final=is_final,
            confidence=classification_confidence,
            spin_phase=sm_result.get("spin_phase"),
            visited_states=visited_states,
            initial_state=initial_state,
            fallback_used=fallback_used,
            fallback_tier=fallback_tier,
            tone=tone_info.get("tone"),
            frustration_level=frustration_level,
            lead_score=self.lead_scorer.current_score if flags.lead_scoring else None,
            objection_detected=objection_info is not None,
            reason_codes=sm_result.get("reason_codes", []),
            resolution_trace=sm_result.get("resolution_trace", {}),
            options=guard_options if action == "guard_offer_options" else (
                fallback_response.get("options") if (not flags.conversation_guard_in_pipeline and fallback_response) else None
            ),
            cta_result=cta_result,
            decision_trace=decision_trace_dict,
        )

    def _merge_flow_state_order(self) -> None:
        """Merge flow-computed state ordering into context window."""
        flow_state_order = self._flow.compute_state_order()
        if flow_state_order:
            self.context_window.merge_state_order(flow_state_order)

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

        # Try to get from global config constants (LoadedConfig, not FlowConfig)
        persona_limits = self._config.constants.get("persona_limits", {})
        if persona_limits:
            return persona_limits

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

    # =========================================================================
    # Snapshot API
    # =========================================================================

    def to_snapshot(
        self,
        compact_history: bool = False,
        history_tail_size: int = 4
    ) -> Dict[str, Any]:
        """Serialize full bot state into snapshot."""
        history_compact = None
        history_compact_meta = None

        if compact_history:
            history_compact, history_compact_meta = HistoryCompactor.compact(
                history_full=self.history,
                history_tail_size=history_tail_size,
                previous_compact=getattr(self, "history_compact", None),
                previous_meta=getattr(self, "history_compact_meta", None),
                llm=getattr(self.generator, "llm", None),
                fallback_context={
                    "collected_data": self.state_machine.collected_data,
                    "metrics": self.metrics.to_dict() if hasattr(self.metrics, "to_dict") else {},
                    "context_window": self.context_window.to_dict() if hasattr(self.context_window, "to_dict") else {},
                },
            )
            # Keep for incremental compaction
            self.history_compact = history_compact
            self.history_compact_meta = history_compact_meta

        context_payload = (
            self.context_window.to_dict()
            if hasattr(self.context_window, "to_dict")
            else {"context_window": [], "_context_window_full": {}}
        )

        snapshot = {
            "version": "1.0",
            "conversation_id": self.conversation_id,
            "client_id": self.client_id,
            "timestamp": time.time(),

            "flow_name": self._flow.name if self._flow else None,
            "config_name": getattr(self._config, "name", None),

            "state_machine": self.state_machine.to_dict(),
            "guard": self.guard.to_dict(),
            "fallback": self.fallback.to_dict(),
            "objection_handler": self.objection_handler.to_dict(),
            "lead_scorer": self.lead_scorer.to_dict(),
            "metrics": self.metrics.to_dict(),

            "context_window": context_payload.get("context_window", []),
            "_context_window_full": context_payload.get("_context_window_full"),

            "history": [],
            "history_tail": list(self.history[-max(0, history_tail_size):]) if history_tail_size > 0 else [],
            "history_compact": history_compact,
            "history_compact_meta": history_compact_meta,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "last_bot_message": self.last_bot_message,
            "generator_response_history": list(getattr(self.generator, "_response_history", []) or []),
            "generator_last_generation_meta": (
                self.generator.get_last_generation_meta()
                if hasattr(self.generator, "get_last_generation_meta")
                else {}
            ),
        }

        source = self._orchestrator.get_source("AutonomousDecisionSource")
        if source is not None and hasattr(source, "decision_history"):
            records = list(getattr(source, "decision_history", []) or [])
            snapshot["autonomous_decision_history"] = [
                record.to_dict()
                for record in records[-20:]
                if hasattr(record, "to_dict")
            ]

        return snapshot

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Dict[str, Any],
        llm=None,
        history_tail: Optional[List[Dict[str, Any]]] = None,
        enable_tracing: bool = False,
    ) -> "SalesBot":
        """Restore bot from snapshot."""
        flow_name = snapshot.get("flow_name") or settings.flow.active
        config_name = snapshot.get("config_name")

        bot = cls(
            llm=llm,
            flow_name=flow_name,
            conversation_id=snapshot.get("conversation_id"),
            client_id=snapshot.get("client_id"),
            config_name=config_name,
            enable_tracing=enable_tracing,
        )

        bot.conversation_id = snapshot.get("conversation_id", bot.conversation_id)
        logger.set_conversation(bot.conversation_id)

        bot.state_machine = StateMachine.from_dict(
            snapshot.get("state_machine", {}),
            config=bot._config,
            flow=bot._flow,
        )
        bot.guard = ConversationGuard.from_dict(
            snapshot.get("guard", {}),
            config=bot.guard.config,
        )
        bot.fallback = FallbackHandler.from_dict(
            snapshot.get("fallback", {}),
            flow=bot._flow,
            config=bot._config,
            guard_config=bot.guard.config,
            product_overviews=getattr(bot.generator, "_product_overview", None),
        )
        bot.objection_handler = ObjectionHandler.from_dict(snapshot.get("objection_handler", {}))
        bot.lead_scorer = LeadScorer.from_dict(snapshot.get("lead_scorer", {}))
        bot.metrics = ConversationMetrics.from_dict(snapshot.get("metrics", {}))
        bot.metrics.conversation_id = bot.conversation_id
        bot.context_window = ContextWindow.from_dict(
            {
                "context_window": snapshot.get("context_window", []),
                "_context_window_full": snapshot.get("_context_window_full"),
            },
            config=bot._config,
        )
        bot._merge_flow_state_order()  # Re-merge after snapshot restore

        restored_history = history_tail
        if restored_history is None:
            stored_tail = snapshot.get("history_tail")
            if isinstance(stored_tail, list):
                restored_history = list(stored_tail)
            else:
                restored_history = [
                    {"user": t["user_message"], "bot": t["bot_response"]}
                    for t in snapshot.get("context_window", [])
                    if isinstance(t, dict) and "user_message" in t and "bot_response" in t
                ]
        bot.history = restored_history or []
        bot.history_compact = snapshot.get("history_compact")
        bot.history_compact_meta = snapshot.get("history_compact_meta")
        bot.last_action = snapshot.get("last_action")
        bot.last_intent = snapshot.get("last_intent")
        bot.last_bot_message = snapshot.get("last_bot_message")
        bot.generator._response_history = list(snapshot.get("generator_response_history", []) or [])
        bot.generator._last_generation_meta = dict(
            snapshot.get("generator_last_generation_meta", {}) or {}
        )

        # Sync: bot.last_action is authoritative — it reflects the actual template
        # used after potential fallback remapping (bot.py lines 1416-1426).
        if bot.last_action is not None:
            bot.state_machine.last_action = bot.last_action

        # Rebuild orchestrator to use restored components
        bot._orchestrator = create_orchestrator(
            state_machine=bot.state_machine,
            flow_config=bot._flow,
            persona_limits=bot._load_persona_limits(),
            enable_metrics=flags.metrics_tracking,
            enable_debug_logging=enable_tracing,
            guard=bot.guard,
            fallback_handler=bot.fallback,
            llm=llm,
            blackboard_config=bot._config.blackboard,
            valid_actions=bot.generator.get_valid_actions(),
        )

        history_payload = snapshot.get("autonomous_decision_history")
        if isinstance(history_payload, list):
            source = bot._orchestrator.get_source("AutonomousDecisionSource")
            if source is not None and hasattr(source, "restore_history"):
                restored_records: List[AutonomousDecisionRecord] = []
                for item in history_payload:
                    if not isinstance(item, dict):
                        continue
                    try:
                        restored_records.append(AutonomousDecisionRecord.from_dict(item))
                    except Exception as e:
                        logger.warning("Failed to restore autonomous decision record: %s", e)
                source.restore_history(restored_records)

        return bot

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


def setup_autonomous_pipeline() -> None:
    """Activate all flags required for the full autonomous pipeline.

    Call this before creating SalesBot when running with flow_name="autonomous".
    Ensures: autonomous_flow + factual_verifier + boundary validator chain.
    """
    flags.set_override("autonomous_flow", True)
    for flag in (
        "response_factual_verifier",
        "response_boundary_validator",
        "response_boundary_llm_judge",
        "response_boundary_retry",
        "response_boundary_fallback",
    ):
        flags.set_override(flag, True)


def _cleanup_gpu_before_start():
    """Kill old python3/ollama processes hogging GPU before fresh start."""
    import subprocess
    import os

    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return

        killed = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            pid, name, mem_mb = int(parts[0]), parts[1], int(parts[2])
            if pid == my_pid:
                continue
            # Kill old python3 processes; ollama handled via systemctl below
            if "python" in name.lower():
                try:
                    os.kill(pid, 9)
                    killed.append(f"  PID {pid} ({name}, {mem_mb} MB)")
                except ProcessLookupError:
                    pass
                except PermissionError:
                    killed.append(f"  PID {pid} ({name}) — нет прав, пропускаю")
            elif "ollama" in name.lower():
                killed.append(f"  PID {pid} ({name}, {mem_mb} MB) — перезапуск через systemd")

        if killed:
            print(f"[GPU Cleanup] Убил старые процессы:")
            for k in killed:
                print(k)
        else:
            print("[GPU Cleanup] Нет старых процессов на GPU")

    except FileNotFoundError:
        pass  # nvidia-smi not found
    except Exception as e:
        print(f"[GPU Cleanup] Ошибка: {e}")

    # Restart Ollama via systemd (it was killed above)
    try:
        subprocess.run(["sudo", "systemctl", "restart", "ollama"],
                       timeout=10, capture_output=True)
        print("[GPU Cleanup] Ollama перезапущена через systemd")
        # Wait for Ollama to be ready
        import time
        time.sleep(3)
    except Exception as e:
        print(f"[GPU Cleanup] Не удалось перезапустить Ollama: {e}")


if __name__ == "__main__":
    import argparse
    from src.llm import OllamaLLM

    parser = argparse.ArgumentParser(description="CRM Sales Bot interactive mode")
    parser.add_argument("--flow", type=str, default="autonomous",
                        help="Sales flow (default: autonomous). Options: autonomous, spin_selling, bant, etc.")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="Skip GPU cleanup (don't kill old processes)")
    args = parser.parse_args()

    if not args.no_cleanup:
        _cleanup_gpu_before_start()

    if args.flow == "autonomous":
        setup_autonomous_pipeline()

    llm = OllamaLLM()
    bot = SalesBot(llm, flow_name=args.flow)

    run_interactive(bot)
