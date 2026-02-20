# src/blackboard/blackboard.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime
import logging

from src.blackboard.models import (
    Proposal, ResolvedDecision, ContextSnapshot,
    deep_freeze_dict, GoBackInfo, IntentTrackerReadOnly,
)
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.protocols import (
    IStateMachine,
    IIntentTracker,
    IFlowConfig,
    TenantConfig,
    DEFAULT_TENANT,
)
from src.intent_tracker import IntentTracker, should_skip_objection_recording as _shared_skip_objection
from src.context_envelope import ContextEnvelope
from src.config_loader import FlowConfig
# Import objection limits from YAML (single source of truth)
from src.yaml_config.constants import MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS

logger = logging.getLogger(__name__)


class DataUpdateCollisionError(Exception):
    """Raised when two sources write to the same data/flag field in strict mode."""
    pass


class DialogueBlackboard:
    """
    Central shared workspace for dialogue management.

    Implements the Blackboard architectural pattern with three layers:
    1. Context Layer (read-only) - current dialogue state
    2. Proposal Layer (write by sources) - proposed actions/transitions
    3. Decision Layer (write by resolver) - final resolved decision

    Hexagonal Architecture:
        DialogueBlackboard depends on protocols (IStateMachine, IIntentTracker, IFlowConfig)
        rather than concrete implementations. This allows easy testing and swapping
        implementations without changing Blackboard code.

    Multi-Tenancy:
        Supports tenant-specific configuration via TenantConfig. Each tenant can have
        custom persona limits, feature flags, and other settings.

    Usage:
        bb = DialogueBlackboard(state_machine, flow_config)
        bb.begin_turn(intent, extracted_data, context_envelope)

        # Knowledge Sources contribute
        source.contribute(bb)

        # Get context snapshot (read-only)
        ctx = bb.get_context()

        # Propose changes
        bb.propose_action("answer_with_pricing", Priority.HIGH, combinable=True)
        bb.propose_transition("spin_problem", Priority.NORMAL)

        # Resolve and commit
        decision = resolver.resolve(bb.get_proposals())
        bb.commit_decision(decision)
    """

    def __init__(
        self,
        state_machine: 'IStateMachine',  # Protocol type for Hexagonal Architecture
        flow_config: 'IFlowConfig',
        intent_tracker: Optional['IIntentTracker'] = None,
        tenant_config: Optional['TenantConfig'] = None,  # Multi-tenancy support
        strict_data_updates: bool = False,
    ):
        """
        Initialize the blackboard.

        Args:
            state_machine: State machine implementing IStateMachine protocol
            flow_config: Flow configuration implementing IFlowConfig protocol
            intent_tracker: Intent tracker implementing IIntentTracker protocol
                           (uses state_machine's if not provided)
            tenant_config: Tenant-specific configuration (optional, uses DEFAULT_TENANT if not provided)
        """
        self._state_machine = state_machine
        self._flow_config = flow_config
        # Try to get intent_tracker - StateMachine uses 'intent_tracker' (no underscore)
        self._intent_tracker = intent_tracker or getattr(state_machine, 'intent_tracker', None) or getattr(state_machine, '_intent_tracker', None)
        self._tenant_config = tenant_config or DEFAULT_TENANT

        # === Context Layer (populated on begin_turn) ===
        self._context: Optional[ContextSnapshot] = None

        # === Proposal Layer ===
        self._action_proposals: List[Proposal] = []
        self._transition_proposals: List[Proposal] = []
        self._data_updates: Dict[str, Any] = {}
        self._flags_to_set: Dict[str, Any] = {}
        self._context_signals: List[Dict[str, Any]] = []

        # === Decision Layer ===
        self._decision: Optional[ResolvedDecision] = None

        # === Metadata ===
        self._turn_start_time: Optional[datetime] = None
        self._current_intent: Optional[str] = None

        # === Strict collision detection (#7) ===
        self._strict_data_updates = strict_data_updates
        self._data_update_sources: Dict[str, str] = {}   # field → source_name
        self._flag_set_sources: Dict[str, str] = {}       # flag → source_name

    def _bind_tracker_to_state_machine(self, tracker: IntentTracker) -> Optional[str]:
        """Try to attach tracker to state_machine without raising."""
        for attr_name in ("intent_tracker", "_intent_tracker"):
            try:
                setattr(self._state_machine, attr_name, tracker)
                return attr_name
            except Exception:
                continue
        return None

    def _ensure_intent_tracker(self, source: str) -> 'IIntentTracker':
        """Ensure runtime tracker exists (auto-heal missing tracker)."""
        if self._intent_tracker is not None:
            return self._intent_tracker

        tracker = IntentTracker()
        self._intent_tracker = tracker
        bound_attr = self._bind_tracker_to_state_machine(tracker)
        if bound_attr:
            logger.warning(
                f"IntentTracker auto-healed in DialogueBlackboard ({source}); "
                f"bound to state_machine.{bound_attr}"
            )
        else:
            logger.warning(
                f"IntentTracker auto-healed in DialogueBlackboard ({source}); "
                "state_machine binding skipped"
            )
        return tracker

    @property
    def intent_tracker(self) -> Optional['IIntentTracker']:
        """Read-only access to intent tracker (for Orchestrator coordination)."""
        return self._ensure_intent_tracker(source="intent_tracker_property")

    @property
    def is_turn_active(self) -> bool:
        """Check if begin_turn() has been called (safe None-guard)."""
        return self._current_intent is not None

    @property
    def data_update_audit(self) -> Dict[str, str]:
        """Audit trail: which source wrote which data field."""
        return dict(self._data_update_sources)

    @property
    def tenant_id(self) -> str:
        """Get current tenant ID."""
        return self._tenant_config.tenant_id

    @property
    def tenant_config(self) -> 'TenantConfig':
        """Get current tenant configuration."""
        return self._tenant_config

    # =========================================================================
    # CONTEXT LAYER (Read-Only)
    # =========================================================================

    def begin_turn(
        self,
        intent: str,
        extracted_data: Dict[str, Any],
        context_envelope: Optional[ContextEnvelope] = None,
        user_message: str = "",
        frustration_level: int = 0,
    ) -> None:
        """
        Begin a new dialogue turn.

        This method:
        1. Records the intent in IntentTracker
        2. Updates collected_data with extracted_data
        3. Creates an immutable ContextSnapshot
        4. Clears previous proposals and decision

        Args:
            intent: Classified intent for this turn
            extracted_data: Data extracted from user message
            context_envelope: Full context envelope (Phase 5)
        """
        self._turn_start_time = datetime.now()
        self._current_intent = intent
        tracker = self._ensure_intent_tracker(source="begin_turn")

        # Record intent in tracker (MUST happen first, before condition evaluation)
        #
        # CRITICAL TIMING: This record() call is the FIRST operation in the turn.
        # IntentTracker.record() immediately updates category streaks:
        # - If intent is in "objection" category → objection streak increments
        # - If intent is NOT in "objection" category → objection streak resets to 0
        #   (see intent_tracker.py:172-179 _update_categories)
        #
        # This timing is ESSENTIAL for _update_state_before_objection() in orchestrator.py
        # which checks objection_consecutive() AFTER this point. The streak value
        # already reflects the current intent by the time the check runs.
        #
        # ИСКЛЮЧЕНИЕ: Пропускаем запись возражений если лимит уже достигнут
        # чтобы предотвратить переполнение счётчика (3→6) при продолжении soft_close
        if tracker and not self._should_skip_objection_recording(intent):
            tracker.record(intent, self._state_machine.state)

        # ALWAYS advance turn counter (independent of record skip logic)
        if tracker:
            tracker.advance_turn()

        # Update collected_data with newly extracted data
        current_collected = dict(self._state_machine.collected_data)
        for key, value in extracted_data.items():
            if value is not None and value != "":
                current_collected[key] = value
                # Persist extracted data for future turns
                self._state_machine.collected_data[key] = value

        # Get current state configuration
        state_config = self._flow_config.states.get(
            self._state_machine.state, {}
        )

        # Detect persona from collected data
        persona = current_collected.get("persona", "default")

        # Create immutable context snapshot
        # FUNDAMENTAL FIX: Pass state_to_phase mapping for custom flows
        state_to_phase = {}
        raw_state_to_phase = getattr(self._flow_config, 'state_to_phase', {})
        if isinstance(raw_state_to_phase, dict):
            state_to_phase = raw_state_to_phase
        else:
            try:
                state_to_phase = dict(raw_state_to_phase)
            except Exception:
                state_to_phase = {}

        # Pre-compute GoBackInfo for go_back_guard (read-only snapshot)
        go_back_info = None
        circular_flow = getattr(self._state_machine, 'circular_flow', None)
        circular_flow_ready = (
            circular_flow is not None
            and callable(getattr(circular_flow, "get_go_back_target", None))
            and callable(getattr(circular_flow, "is_limit_reached", None))
            and callable(getattr(circular_flow, "get_remaining_gobacks", None))
            and callable(getattr(circular_flow, "get_history", None))
            and isinstance(getattr(circular_flow, "goback_count", 0), int)
            and isinstance(getattr(circular_flow, "max_gobacks", 0), int)
        )
        if circular_flow_ready:
            transitions = state_config.get("transitions", {})
            raw_history = []
            if hasattr(circular_flow, "get_history"):
                try:
                    raw_history = circular_flow.get_history() or []
                except Exception:
                    raw_history = []
            if isinstance(raw_history, (list, tuple)):
                history = tuple(raw_history)
            else:
                try:
                    history = tuple(raw_history)
                except TypeError:
                    history = ()
            go_back_info = GoBackInfo(
                target_state=circular_flow.get_go_back_target(
                    self._state_machine.state, transitions
                ),
                limit_reached=circular_flow.is_limit_reached(),
                remaining=circular_flow.get_remaining_gobacks(),
                goback_count=circular_flow.goback_count,
                max_gobacks=circular_flow.max_gobacks,
                history=history,
            )

        flow_dict_raw = {}
        flow_to_dict = getattr(self._flow_config, "to_dict", None)
        if callable(flow_to_dict):
            try:
                flow_dict_raw = flow_to_dict() or {}
            except Exception:
                flow_dict_raw = {}
        if not isinstance(flow_dict_raw, dict):
            flow_dict_raw = {}

        raw_states = getattr(self._flow_config, "states", {})
        valid_states = frozenset(raw_states.keys()) if isinstance(raw_states, dict) else frozenset()

        self._context = ContextSnapshot(
            state=self._state_machine.state,
            collected_data=deep_freeze_dict(dict(current_collected)),
            current_intent=intent,
            intent_tracker=IntentTrackerReadOnly(tracker) if tracker else tracker,
            context_envelope=context_envelope,
            turn_number=tracker.turn_number if tracker else 0,
            persona=persona,
            state_config=deep_freeze_dict(dict(state_config)),
            flow_config=deep_freeze_dict(flow_dict_raw),
            state_to_phase=deep_freeze_dict(dict(state_to_phase)),
            state_before_objection=self._state_machine.state_before_objection if hasattr(self._state_machine, 'state_before_objection') else getattr(self._state_machine, '_state_before_objection', None),
            valid_states=valid_states,
            go_back_info=go_back_info,
            # Multi-tenancy support
            tenant_id=self._tenant_config.tenant_id,
            tenant_config=self._tenant_config,
            # Guard-class sources (ConversationGuardSource)
            user_message=user_message,
            frustration_level=frustration_level,
        )

        # Clear proposal layer
        self._action_proposals.clear()
        self._transition_proposals.clear()
        self._data_updates.clear()
        self._flags_to_set.clear()
        self._context_signals.clear()

        # Clear collision audit trail
        self._data_update_sources.clear()
        self._flag_set_sources.clear()

        # Clear decision layer
        self._decision = None

        logger.debug(
            f"Blackboard turn started: intent={intent}, state={self._state_machine.state}, "
            f"turn={tracker.turn_number if tracker else 0}"
        )

    def _should_skip_objection_recording(self, intent: str) -> bool:
        """Delegate to shared function (SSOT in intent_tracker.py)."""
        if not self._intent_tracker:
            return False
        result = _shared_skip_objection(
            intent, self._intent_tracker, self._state_machine.collected_data
        )
        if result:
            logger.debug(
                f"Skipping objection recording - limit already reached"
            )
        return result

    def get_context(self) -> ContextSnapshot:
        """
        Get the immutable context snapshot.

        This is the primary way Knowledge Sources access dialogue state.
        The snapshot is read-only - sources cannot modify it directly.

        Returns:
            ContextSnapshot with current dialogue state

        Raises:
            RuntimeError: If called before begin_turn()
        """
        if self._context is None:
            raise RuntimeError("Blackboard.get_context() called before begin_turn()")
        return self._context

    @property
    def current_intent(self) -> str:
        """Get the current turn's intent."""
        if self._current_intent is None:
            raise RuntimeError("Blackboard accessed before begin_turn()")
        return self._current_intent

    @property
    def current_state(self) -> str:
        """Get the current dialogue state."""
        return self._state_machine.state

    @property
    def collected_data(self) -> Dict[str, Any]:
        """Get collected data (from context snapshot)."""
        return self._context.collected_data if self._context else {}

    # =========================================================================
    # PROPOSAL LAYER (Write by Sources)
    # =========================================================================

    def propose_action(
        self,
        action: str,
        priority: Priority = Priority.NORMAL,
        priority_rank: Optional[int] = None,
        combinable: bool = True,
        reason_code: str = "",
        source_name: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Propose an action to be executed.

        Args:
            action: Name of the action (e.g., "answer_with_pricing")
            priority: Priority level (CRITICAL, HIGH, NORMAL, LOW)
            combinable: If True, this action can coexist with transitions.
                        If False, this action blocks all transitions.
            reason_code: Documented reason for this proposal
            source_name: Name of the Knowledge Source making this proposal
            metadata: Additional context about the proposal
        """
        proposal = Proposal(
            type=ProposalType.ACTION,
            value=action,
            priority=priority,
            source_name=source_name,
            reason_code=reason_code or f"action_{action}",
            combinable=combinable,
            metadata=metadata or {},
            priority_rank=priority_rank,
        )

        self._action_proposals.append(proposal)

        logger.debug(
            f"Action proposed: {action} (priority={priority.name}, "
            f"combinable={combinable}, source={source_name})"
        )

    def propose_transition(
        self,
        next_state: str,
        priority: Priority = Priority.NORMAL,
        priority_rank: Optional[int] = None,
        reason_code: str = "",
        source_name: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Propose a state transition.

        Args:
            next_state: Target state name (e.g., "spin_problem")
            priority: Priority level (CRITICAL, HIGH, NORMAL, LOW)
            reason_code: Documented reason for this proposal
            source_name: Name of the Knowledge Source making this proposal
            metadata: Additional context about the proposal
        """
        proposal = Proposal(
            type=ProposalType.TRANSITION,
            value=next_state,
            priority=priority,
            source_name=source_name,
            reason_code=reason_code or f"transition_to_{next_state}",
            combinable=True,  # Transitions are always combinable
            metadata=metadata or {},
            priority_rank=priority_rank,
        )

        self._transition_proposals.append(proposal)

        logger.debug(
            f"Transition proposed: {next_state} (priority={priority.name}, "
            f"source={source_name})"
        )

    def propose_data_update(
        self,
        field: str,
        value: Any,
        source_name: str = "unknown",
        reason_code: str = ""
    ) -> None:
        """
        Record a data field update (direct last-write-wins, NOT a Proposal).

        This does NOT create a Proposal and does NOT go through conflict
        resolution. Multiple sources writing the same field will silently
        overwrite — the last writer wins.

        Applied by Orchestrator._apply_side_effects(), which is the single
        owner of state mutation.

        Args:
            field: Field name to update
            value: New value for the field
            source_name: Name of the Knowledge Source making this proposal
            reason_code: Documented reason for this proposal
        """
        if field in self._data_updates:
            prev_source = self._data_update_sources.get(field, "unknown")
            msg = (
                f"Data update collision: field='{field}' overwritten by "
                f"{source_name} (was: {prev_source}, reason: {reason_code})"
            )
            if self._strict_data_updates:
                raise DataUpdateCollisionError(msg)
            logger.warning(msg)
        self._data_updates[field] = value
        self._data_update_sources[field] = source_name

        logger.debug(
            f"Data update proposed: {field}={value} (source={source_name})"
        )

    def propose_flag_set(
        self,
        flag: str,
        value: Any,
        source_name: str = "unknown",
        reason_code: str = ""
    ) -> None:
        """
        Record a flag to set (direct last-write-wins, NOT a Proposal).

        This does NOT create a Proposal and does NOT go through conflict
        resolution. Applied by Orchestrator._apply_side_effects(), which is
        the single owner of state mutation.

        Args:
            flag: Flag name to set
            value: Value to set
            source_name: Name of the Knowledge Source making this proposal
            reason_code: Documented reason for this proposal
        """
        if flag in self._flags_to_set:
            prev_source = self._flag_set_sources.get(flag, "unknown")
            msg = (
                f"Flag set collision: flag='{flag}' overwritten by "
                f"{source_name} (was: {prev_source}, reason: {reason_code})"
            )
            if self._strict_data_updates:
                raise DataUpdateCollisionError(msg)
            logger.warning(msg)
        self._flags_to_set[flag] = value
        self._flag_set_sources[flag] = source_name

        logger.debug(
            f"Flag set proposed: {flag}={value} (source={source_name})"
        )

    def get_proposals(self) -> List[Proposal]:
        """
        Get all proposals (actions + transitions).

        Returns:
            Combined list of all proposals
        """
        return self._action_proposals + self._transition_proposals

    def get_action_proposals(self) -> List[Proposal]:
        """Get only action proposals."""
        return list(self._action_proposals)

    def get_transition_proposals(self) -> List[Proposal]:
        """Get only transition proposals."""
        return list(self._transition_proposals)

    def get_data_updates(self) -> Dict[str, Any]:
        """Get proposed data updates."""
        return dict(self._data_updates)

    def get_flags_to_set(self) -> Dict[str, Any]:
        """Get proposed flags to set."""
        return dict(self._flags_to_set)

    def add_context_signal(self, source_name: str, signal: Dict[str, Any]) -> None:
        """
        Add non-binding context signal for downstream sources (e.g., LLM decision).

        Context signals are turn-local, reset in begin_turn(), and never participate
        in conflict resolution because they are not action/transition proposals.
        """
        payload = dict(signal or {})
        payload.setdefault("source", source_name)
        self._context_signals.append(payload)

        logger.debug(
            "Context signal added: source=%s keys=%s",
            source_name,
            sorted(payload.keys()),
        )

    def get_context_signals(self) -> List[Dict[str, Any]]:
        """Get turn-local context signals accumulated by prior sources."""
        return list(self._context_signals)

    # =========================================================================
    # DECISION LAYER (Write by Resolver)
    # =========================================================================

    def commit_decision(self, decision: ResolvedDecision) -> None:
        """
        Commit the resolved decision.

        Stores the decision in the decision layer. Does NOT apply data updates
        or flags — that is the Orchestrator's responsibility in
        _apply_side_effects(), which is the single owner of state mutation.
        """
        self._decision = decision

        logger.info(
            f"Decision committed: action={decision.action}, "
            f"next_state={decision.next_state}, "
            f"reasons={decision.reason_codes}"
        )

    def get_decision(self) -> Optional[ResolvedDecision]:
        """
        Get the committed decision.

        Returns:
            ResolvedDecision if committed, None otherwise
        """
        return self._decision

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_turn_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current turn for logging/debugging.

        Returns:
            Dictionary with turn summary
        """
        tracker = self.intent_tracker
        return {
            "turn_number": tracker.turn_number if tracker else 0,
            "intent": self._current_intent,
            "state": self._state_machine.state,
            "action_proposals_count": len(self._action_proposals),
            "transition_proposals_count": len(self._transition_proposals),
            "action_proposals": [str(p) for p in self._action_proposals],
            "transition_proposals": [str(p) for p in self._transition_proposals],
            "data_updates": self._data_updates,
            "decision": self._decision.to_dict() if self._decision else None,
            "turn_duration_ms": (
                (datetime.now() - self._turn_start_time).total_seconds() * 1000
                if self._turn_start_time else None
            ),
        }
