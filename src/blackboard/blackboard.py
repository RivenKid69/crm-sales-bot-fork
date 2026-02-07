# src/blackboard/blackboard.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime
import logging

from src.blackboard.models import Proposal, ResolvedDecision, ContextSnapshot
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.protocols import (
    IStateMachine,
    IIntentTracker,
    IFlowConfig,
    TenantConfig,
    DEFAULT_TENANT,
)
from src.intent_tracker import IntentTracker
from src.context_envelope import ContextEnvelope
from src.config_loader import FlowConfig
# Import objection limits from YAML (single source of truth)
from src.yaml_config.constants import MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS

logger = logging.getLogger(__name__)


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
        tenant_config: Optional['TenantConfig'] = None  # Multi-tenancy support
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

        # === Decision Layer ===
        self._decision: Optional[ResolvedDecision] = None

        # === Metadata ===
        self._turn_start_time: Optional[datetime] = None
        self._current_intent: Optional[str] = None

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
        if self._intent_tracker and not self._should_skip_objection_recording(intent):
            self._intent_tracker.record(intent, self._state_machine.state)

        # ALWAYS advance turn counter (independent of record skip logic)
        if self._intent_tracker:
            self._intent_tracker.advance_turn()

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
        if hasattr(self._flow_config, 'state_to_phase'):
            state_to_phase = self._flow_config.state_to_phase

        self._context = ContextSnapshot(
            state=self._state_machine.state,
            collected_data=current_collected,
            current_intent=intent,
            intent_tracker=self._intent_tracker,
            context_envelope=context_envelope,
            turn_number=self._intent_tracker.turn_number if self._intent_tracker else 0,
            persona=persona,
            state_config=state_config,
            flow_config=self._flow_config.to_dict() if hasattr(self._flow_config, 'to_dict') else {},
            state_to_phase=state_to_phase,
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

        # Clear decision layer
        self._decision = None

        logger.debug(
            f"Blackboard turn started: intent={intent}, state={self._state_machine.state}, "
            f"turn={self._intent_tracker.turn_number if self._intent_tracker else 0}"
        )

    def _should_skip_objection_recording(self, intent: str) -> bool:
        """
        Check if objection recording should be skipped.

        ======================================================================
        NOT A BUG: This is part of infinite loop prevention
        ======================================================================

        REPORTED CONCERN:
          "ObjectionGuard keeps triggering because consecutive >= max"

        WHY THIS PREVENTS THE LOOP:

        1. WHEN LIMIT IS REACHED:
           - ObjectionGuard proposes soft_close + _objection_limit_final flag
           - Transition to soft_close happens
           - is_final() returns True (due to flag override)

        2. IF CONVERSATION SOMEHOW CONTINUES (edge case):
           - User sends another objection intent
           - THIS METHOD catches it BEFORE recording
           - consecutive stays at max (e.g., 3), doesn't grow to 4, 5, 6...
           - ObjectionGuard sees same values, proposes soft_close again
           - But _objection_limit_final is ALREADY set
           - is_final() returns True → conversation ends

        3. WHY SKIP RECORDING:
           - Without this, counter would grow: 3 → 4 → 5 → ...
           - This wastes memory and confuses analytics
           - With this, counter stays at limit (3)

        TIMELINE:
          Turn N:   3rd objection → limit reached → soft_close → flag set
          Turn N+1: (if any) objection → skip recording → count=3 (not 4)
                    → is_final=True → ends

        This is defense in depth, working with:
        - _objection_limit_final flag (objection_guard.py)
        - is_final() override (state_machine.py)
        ======================================================================

        Prevents counter from growing beyond limit when soft_close
        continues the dialog (e.g., when is_final=false).

        This mirrors StateMachine._should_skip_objection_recording() for
        compatibility with existing objection handling logic.

        Args:
            intent: The intent to check

        Returns:
            True if recording should be skipped (limit already reached)
        """
        from src.yaml_config.constants import OBJECTION_INTENTS, get_persona_objection_limits

        if intent not in OBJECTION_INTENTS:
            return False

        # Get persona-aware limits
        persona = self._state_machine.collected_data.get("persona", "default")
        limits = get_persona_objection_limits(persona)
        max_consecutive = limits["consecutive"]
        max_total = limits["total"]

        # Check if limit already reached
        if self._intent_tracker:
            consecutive = self._intent_tracker.objection_consecutive()
            total = self._intent_tracker.objection_total()

            if consecutive >= max_consecutive or total >= max_total:
                logger.debug(
                    f"Skipping objection recording - limit already reached: "
                    f"consecutive={consecutive}, total={total}"
                )
                return True
        return False

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
        Propose a data field update.

        Args:
            field: Field name to update
            value: New value for the field
            source_name: Name of the Knowledge Source making this proposal
            reason_code: Documented reason for this proposal
        """
        self._data_updates[field] = value

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
        Propose setting a flag.

        Args:
            flag: Flag name to set
            value: Value to set
            source_name: Name of the Knowledge Source making this proposal
            reason_code: Documented reason for this proposal
        """
        self._flags_to_set[flag] = value

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

    # =========================================================================
    # DECISION LAYER (Write by Resolver)
    # =========================================================================

    def commit_decision(self, decision: ResolvedDecision) -> None:
        """
        Commit the resolved decision.

        This method:
        1. Stores the decision in the decision layer
        2. Applies data updates to state machine
        3. Applies flags to state machine

        Note: State transition is NOT applied here - it's done by the caller
        (SalesBot) to maintain compatibility with existing code.

        Args:
            decision: The resolved decision from ConflictResolver
        """
        self._decision = decision

        # Apply data updates
        for field, value in decision.data_updates.items():
            self._state_machine.collected_data[field] = value

        # Apply any additional data updates from proposals
        for field, value in self._data_updates.items():
            self._state_machine.collected_data[field] = value

        # Store flags (applied on state entry)
        for flag, value in decision.flags_to_set.items():
            self._flags_to_set[flag] = value

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
        return {
            "turn_number": self._intent_tracker.turn_number if self._intent_tracker else 0,
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
