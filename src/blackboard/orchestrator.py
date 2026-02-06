# src/blackboard/orchestrator.py

from typing import List, Dict, Any, Optional, Tuple, Type
from datetime import datetime
import logging
import time

from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.knowledge_source import KnowledgeSource
from src.blackboard.conflict_resolver import ConflictResolver
from src.blackboard.priority_assigner import PriorityAssigner
from src.blackboard.proposal_validator import ProposalValidator, ValidationError
from src.blackboard.event_bus import (
    DialogueEventBus,
    TurnStartedEvent,
    SourceContributedEvent,
    ProposalValidatedEvent,
    ConflictResolvedEvent,
    DecisionCommittedEvent,
    StateTransitionedEvent,
    ErrorOccurredEvent,
)
from src.blackboard.models import ResolvedDecision
from src.blackboard.enums import Priority

# Hexagonal Architecture: Import protocols (ports)
from src.blackboard.protocols import (
    IStateMachine,
    IFlowConfig,
    TenantConfig,
    DEFAULT_TENANT,
)

# Import SourceRegistry (Plugin System)
from src.blackboard.source_registry import SourceRegistry, register_builtin_sources

# Import intent categories for objection tracking
from src.yaml_config.constants import OBJECTION_INTENTS, POSITIVE_INTENTS

logger = logging.getLogger(__name__)

# Register built-in sources on module import
register_builtin_sources()


class DialogueOrchestrator:
    """
    Main coordinator for the Dialogue Blackboard System.

    Hexagonal Architecture:
        Orchestrator is the APPLICATION LAYER that coordinates domain logic.
        It depends on PROTOCOLS (ports) rather than concrete implementations:
        - IStateMachine: input port for state management
        - IFlowConfig: input port for configuration
        - IContextEnvelope: input port for context data

    Responsibilities:
        - Initialize and manage Knowledge Sources
        - Coordinate the turn processing pipeline
        - Handle validation and error recovery
        - Emit events for observability

    Multi-Tenancy:
        Supports tenant-specific configuration via TenantConfig.
        Each tenant can have custom feature flags, persona limits, etc.

    Pipeline:
        1. begin_turn() - Initialize blackboard for new turn
        2. Knowledge Sources contribute proposals
        3. Validate proposals
        4. Resolve conflicts
        5. Commit decision
        6. Return result to caller (SalesBot)

    Usage:
        orchestrator = DialogueOrchestrator(state_machine, flow_config)
        decision = orchestrator.process_turn(intent, extracted_data, context_envelope)
        # decision.action, decision.next_state, decision.reason_codes
    """

    def __init__(
        self,
        state_machine: 'IStateMachine',  # Protocol type (Hexagonal Architecture port)
        flow_config: 'IFlowConfig',       # Protocol type (Hexagonal Architecture port)
        event_bus: Optional[DialogueEventBus] = None,
        enable_validation: bool = True,
        strict_validation: bool = False,
        persona_limits: Optional[Dict[str, Dict[str, int]]] = None,
        tenant_config: Optional['TenantConfig'] = None,  # Multi-tenancy support
        guard: Optional[Any] = None,
        fallback_handler: Optional[Any] = None,
        llm: Optional[Any] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            state_machine: State machine implementing IStateMachine protocol
            flow_config: Flow configuration implementing IFlowConfig protocol
            event_bus: Event bus for observability (created if not provided)
            enable_validation: Whether to validate proposals
            strict_validation: Whether to treat warnings as errors
            persona_limits: Custom persona limits for ObjectionGuardSource
            tenant_config: Tenant-specific configuration (uses DEFAULT_TENANT if not provided)
            llm: LLM instance for AutonomousDecisionSource (None for non-autonomous flows)
        """
        self._state_machine = state_machine
        self._flow_config = flow_config
        self._tenant_config = tenant_config or DEFAULT_TENANT
        self._guard = guard
        self._fallback_handler = fallback_handler

        # Initialize blackboard with tenant config
        self._blackboard = DialogueBlackboard(
            state_machine=state_machine,
            flow_config=flow_config,
            tenant_config=self._tenant_config,
        )

        # Initialize event bus
        self._event_bus = event_bus or DialogueEventBus()

        # Initialize validator
        self._enable_validation = enable_validation
        self._validator = ProposalValidator(
            valid_states=set(flow_config.states.keys()) if hasattr(flow_config, 'states') else None,
            strict_mode=strict_validation,
        )

        # Initialize conflict resolver
        # FIX: Use continue_current_goal as default action (has template in prompts.yaml)
        self._resolver = ConflictResolver(default_action="continue_current_goal")

        # Config-driven priority assignment (FlowConfig.priorities)
        self._priority_assigner = PriorityAssigner(self._flow_config)

        # Initialize Knowledge Sources via Registry (Plugin System)
        # Sources are created in priority_order from SourceRegistry
        # Configuration can enable/disable individual sources
        _sm_resolver = getattr(state_machine, '_resolver', None)
        _expr_parser = getattr(_sm_resolver, 'expression_parser', None) if _sm_resolver else None

        source_configs = {
            "IntentProcessorSource": {"rule_resolver": _sm_resolver} if _sm_resolver else {},
            "TransitionResolverSource": {"expression_parser": _expr_parser} if _expr_parser else {},
            "ObjectionGuardSource": {"persona_limits": persona_limits},
            "ConversationGuardSource": {
                "guard": self._guard,
                "fallback_handler": self._fallback_handler,
            },
            "AutonomousDecisionSource": {"llm": llm},
        }

        self._sources: List[KnowledgeSource] = SourceRegistry.create_sources(
            config=self._get_sources_config(),
            source_configs=source_configs,
        )

        logger.info(
            f"DialogueOrchestrator initialized with {len(self._sources)} sources: "
            f"{[s.name for s in self._sources]}"
        )

    def _get_sources_config(self) -> Dict[str, Any]:
        """
        Get sources configuration from flow_config or constants.

        Returns:
            Dict with 'sources' key containing per-source enabled flags
        """
        # Try to get from flow_config
        if hasattr(self._flow_config, 'constants'):
            return self._flow_config.constants.get('blackboard', {})
        return {}

    @property
    def blackboard(self) -> DialogueBlackboard:
        """Get the blackboard instance."""
        return self._blackboard

    @property
    def event_bus(self) -> DialogueEventBus:
        """Get the event bus instance."""
        return self._event_bus

    @property
    def sources(self) -> List[KnowledgeSource]:
        """Get list of Knowledge Sources."""
        return list(self._sources)

    def add_source(self, source: KnowledgeSource) -> None:
        """
        Add a new Knowledge Source.

        Args:
            source: Knowledge Source to add
        """
        self._sources.append(source)
        logger.info(f"Added Knowledge Source: {source.name}")

    def remove_source(self, source_name: str) -> bool:
        """
        Remove a Knowledge Source by name.

        Args:
            source_name: Name of source to remove

        Returns:
            True if source was removed, False if not found
        """
        for source in self._sources:
            if source.name == source_name:
                self._sources.remove(source)
                logger.info(f"Removed Knowledge Source: {source_name}")
                return True
        return False

    def get_source(self, source_name: str) -> Optional[KnowledgeSource]:
        """
        Get a Knowledge Source by name.

        Args:
            source_name: Name of source to get

        Returns:
            KnowledgeSource if found, None otherwise
        """
        for source in self._sources:
            if source.name == source_name:
                return source
        return None

    def process_turn(
        self,
        intent: str,
        extracted_data: Dict[str, Any],
        context_envelope: Optional[Any] = None,
        user_message: str = "",
        frustration_level: int = 0,
    ) -> ResolvedDecision:
        """
        Process a dialogue turn through the Blackboard system.

        This is the main entry point, replacing StateMachine.apply_rules().

        Args:
            intent: Classified intent for this turn
            extracted_data: Data extracted from user message
            context_envelope: Full context envelope (Phase 5)

        Returns:
            ResolvedDecision with action, next_state, and metadata
        """
        turn_start_time = time.time()
        turn_number = self._blackboard._intent_tracker.turn_number + 1
        current_state = self._state_machine.state

        try:
            # === STEP 1: Begin Turn ===
            self._blackboard.begin_turn(
                intent=intent,
                extracted_data=extracted_data,
                context_envelope=context_envelope,
                user_message=user_message,
                frustration_level=frustration_level,
            )

            self._event_bus.emit(TurnStartedEvent(
                turn_number=turn_number,
                intent=intent,
                state=current_state,
            ))

            logger.debug(
                f"Turn {turn_number} started: intent={intent}, state={current_state}"
            )

            # === STEP 2: Knowledge Sources Contribute ===
            for source in self._sources:
                source_start_time = time.time()

                # Check if source should contribute
                if not source.should_contribute(self._blackboard):
                    logger.debug(f"Source {source.name} skipped (should_contribute=False)")
                    continue

                # Let source contribute
                try:
                    source.contribute(self._blackboard)
                except Exception as e:
                    logger.error(f"Error in source {source.name}: {e}")
                    self._event_bus.emit(ErrorOccurredEvent(
                        turn_number=turn_number,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        component=source.name,
                    ))
                    continue

                source_time_ms = (time.time() - source_start_time) * 1000

                # Get proposals from this source
                proposals_summary = [
                    str(p) for p in self._blackboard.get_proposals()
                    if p.source_name == source.name
                ]

                self._event_bus.emit(SourceContributedEvent(
                    turn_number=turn_number,
                    source_name=source.name,
                    proposals_count=len(proposals_summary),
                    proposals_summary=proposals_summary,
                    execution_time_ms=source_time_ms,
                ))

            # === STEP 3: Apply Priority Ordering (config-driven) ===
            proposals = self._blackboard.get_proposals()
            self._priority_assigner.assign(proposals, self._blackboard.get_context())

            # === STEP 4: Validate Proposals ===
            validation_errors: List[ValidationError] = []

            if self._enable_validation:
                validation_errors = self._validator.validate(proposals)

                error_count = len(self._validator.get_errors_only(validation_errors))
                warning_count = len(self._validator.get_warnings_only(validation_errors))

                self._event_bus.emit(ProposalValidatedEvent(
                    turn_number=turn_number,
                    valid_count=len(proposals) - error_count,
                    error_count=error_count,
                    warning_count=warning_count,
                    errors=[str(e) for e in validation_errors],
                ))

                # Handle blocking validation errors
                if self._validator.has_blocking_errors(validation_errors):
                    logger.error(
                        f"Blocking validation errors: {validation_errors}"
                    )
                    # Return safe fallback decision
                    return self._create_fallback_decision(
                        current_state=current_state,
                        reason="validation_error",
                        turn_number=turn_number,
                    )

            # === STEP 4: Resolve Conflicts ===
            resolve_start_time = time.time()

            # Get fallback transition (from "any" trigger)
            fallback_transition = self._get_fallback_transition()

            decision = self._resolver.resolve_with_fallback(
                proposals=proposals,
                current_state=current_state,
                fallback_transition=fallback_transition,
                data_updates=self._blackboard.get_data_updates(),
                flags_to_set=self._blackboard.get_flags_to_set(),
            )

            resolve_time_ms = (time.time() - resolve_start_time) * 1000

            self._event_bus.emit(ConflictResolvedEvent(
                turn_number=turn_number,
                winning_action=decision.action,
                winning_transition=decision.next_state if decision.next_state != current_state else None,
                rejected_count=len(decision.rejected_proposals),
                merge_decision=decision.resolution_trace.get("merge_decision", "unknown"),
                resolution_time_ms=resolve_time_ms,
            ))

            # === STEP 5: Commit Decision ===
            self._blackboard.commit_decision(decision)

            self._event_bus.emit(DecisionCommittedEvent(
                turn_number=turn_number,
                action=decision.action,
                next_state=decision.next_state,
                reason_codes=decision.reason_codes,
            ))

            # Emit state transition event if state changed
            state_changed = decision.next_state != current_state
            if state_changed:
                self._event_bus.emit(StateTransitionedEvent(
                    turn_number=turn_number,
                    from_state=current_state,
                    to_state=decision.next_state,
                    trigger_reason=", ".join(decision.reason_codes),
                ))

            # === STEP 6: Apply Side Effects (CRITICAL for bot.py compatibility) ===
            # These side effects were previously performed in state_machine.process()
            # and are REQUIRED for correct bot.py operation
            self._apply_side_effects(decision, current_state, state_changed)

            # === STEP 7: Fill Compatibility Fields ===
            # bot.py expects full sm_result dict with these fields
            self._fill_compatibility_fields(decision, current_state)

            turn_time_ms = (time.time() - turn_start_time) * 1000

            logger.info(
                f"Turn {turn_number} completed in {turn_time_ms:.1f}ms: "
                f"action={decision.action}, next_state={decision.next_state}"
            )

            return decision

        except Exception as e:
            logger.exception(f"Error processing turn {turn_number}: {e}")

            self._event_bus.emit(ErrorOccurredEvent(
                turn_number=turn_number,
                error_type=type(e).__name__,
                error_message=str(e),
                component="DialogueOrchestrator",
            ))

            # Return safe fallback
            return self._create_fallback_decision(
                current_state=current_state,
                reason="processing_error",
                turn_number=turn_number,
            )

    def _get_fallback_transition(self) -> Optional[str]:
        """
        Get fallback transition from "any" trigger in current state.

        Returns:
            Target state for "any" transition, or None
        """
        ctx = self._blackboard.get_context()
        return ctx.get_transition("any")

    def _create_fallback_decision(
        self,
        current_state: str,
        reason: str,
        turn_number: int,
    ) -> ResolvedDecision:
        """
        Create a safe fallback decision when processing fails.

        Args:
            current_state: Current dialogue state
            reason: Reason for fallback
            turn_number: Current turn number

        Returns:
            Safe ResolvedDecision that continues conversation
        """
        logger.warning(
            f"Creating fallback decision: reason={reason}, state={current_state}"
        )

        fallback = ResolvedDecision(
            action="continue_current_goal",
            next_state=current_state,  # Stay in current state
            reason_codes=[f"fallback_{reason}"],
            rejected_proposals=[],
            resolution_trace={"fallback": True, "reason": reason},
        )
        # Fill compatibility fields even for fallback
        self._fill_compatibility_fields(fallback, current_state)
        return fallback

    # =========================================================================
    # COMPATIBILITY METHODS (for integration with bot.py)
    # =========================================================================

    def _apply_side_effects(
        self,
        decision: ResolvedDecision,
        prev_state: str,
        state_changed: bool,
    ) -> None:
        """
        Apply side effects that were previously in state_machine.process().

        CRITICALLY IMPORTANT: These side effects are necessary for correct operation:
        1. IntentTracker.record() - intent history for conditions
        2. state update - state transition (via transition_to for atomicity)
        3. last_action update - for contextual classification
        4. current_phase update - for SPIN phase
        5. on_enter flags - flags when entering state

        OUT OF SCOPE (called directly from bot.py):
        - increment_turn() - called by bot.py line 637 BEFORE process_turn()
                             for tracking disambiguation cooldown
        - disambiguation methods - enter/exit/resolve called directly
        - reset() - called for new conversation

        ORDER OF CALLS in bot.py:
        1. state_machine.increment_turn()           # bot.py line 637
        2. state_machine.transition_to(skip_next_state, source="fallback_skip")
        3. collected_data["competitor"] = ...       # bot.py lines 773-776
        4. orchestrator.process_turn()              # bot.py -> HERE WE ARE
        5. state_machine.transition_to(policy_next_state, source="policy_override")

        FIX (Distributed State Mutation bug):
        Previously, this method directly assigned state, last_action, and current_phase
        separately, which could lead to inconsistencies when bot.py also directly
        modified state. Now we use transition_to() for atomic updates.

        Args:
            decision: The resolved decision
            prev_state: State before this turn
            state_changed: Whether state transition occurred
        """
        # Get state configuration for on_enter logic
        next_config = self._flow_config.states.get(decision.next_state, {})

        # Compute final action (considering on_enter override)
        final_action = decision.action
        if state_changed:
            on_enter = next_config.get("on_enter")
            if on_enter:
                on_enter_action = (
                    on_enter.get("action") if isinstance(on_enter, dict) else on_enter
                )
                if on_enter_action:
                    final_action = on_enter_action
                    decision.action = on_enter_action  # Update decision for consistency
                    logger.debug(f"on_enter action override: {on_enter_action}")

        # 1. ATOMIC STATE TRANSITION via transition_to()
        # This ensures state, current_phase, and last_action are always consistent
        # FUNDAMENTAL FIX: Use FlowConfig.get_phase_for_state() for all flows
        phase = self._flow_config.get_phase_for_state(decision.next_state)
        self._state_machine.transition_to(
            next_state=decision.next_state,
            action=final_action,
            phase=phase,
            source="orchestrator",
            validate=False,  # Already validated by ProposalValidator
        )

        # 2. Apply data_updates to collected_data
        if decision.data_updates:
            self._state_machine.update_data(decision.data_updates)

        # 3. Apply on_enter flags when state changes
        if state_changed:
            on_enter_flags = self._flow_config.get_state_on_enter_flags(decision.next_state)
            for flag_name, flag_value in on_enter_flags.items():
                self._state_machine.collected_data[flag_name] = flag_value

        # 4. Apply flags_to_set from decision
        if decision.flags_to_set:
            for flag_name, flag_value in decision.flags_to_set.items():
                self._state_machine.collected_data[flag_name] = flag_value

        # 5. DEFERRED GOBACK INCREMENT (BUGFIX for GoBackGuardSource)
        # GoBackGuardSource no longer increments goback_count directly in contribute().
        # Instead, it adds pending_goback_increment=True to the proposal metadata.
        # We increment the counter here ONLY IF:
        # 1. The action "acknowledge_go_back" won the conflict resolution
        # 2. The state actually changed (transition happened)
        # 3. The transition went to the expected prev_state
        #
        # This prevents incorrect counter increment when another source
        # (e.g., ObjectionGuardSource with CRITICAL priority) blocks the go_back.
        self._apply_deferred_goback_increment(
            decision=decision,
            prev_state=prev_state,
            state_changed=state_changed,
        )

        # 6. Track state before objection series (FIX: _state_before_objection tracking)
        # This enables returning to the correct state after handling objections.
        #
        # Logic:
        # - When entering handle_objection from a non-objection state: save prev_state
        # - When a positive intent resets the objection streak: clear _state_before_objection
        # - When leaving handle_objection normally: clear _state_before_objection
        self._update_state_before_objection(
            decision=decision,
            prev_state=prev_state,
            state_changed=state_changed,
        )

    def _apply_deferred_goback_increment(
        self,
        decision: ResolvedDecision,
        prev_state: str,
        state_changed: bool,
    ) -> None:
        """
        Apply deferred goback_count increment after conflict resolution.

        BUGFIX: GoBackGuardSource no longer increments goback_count directly.
        Instead, it adds pending_goback_increment metadata to the proposal.
        We increment the counter here ONLY IF:
        1. The winning action is "acknowledge_go_back"
        2. The state actually changed (transition happened)
        3. The transition went to the expected target state

        This prevents incorrect counter increment when another source with higher
        priority (e.g., ObjectionGuardSource with CRITICAL) blocks the go_back.

        Args:
            decision: The resolved decision
            prev_state: State before this turn
            state_changed: Whether state transition occurred
        """
        # Only process if the winning action is acknowledge_go_back
        if decision.action != "acknowledge_go_back":
            return

        # Only process if state actually changed (transition happened)
        if not state_changed:
            logger.debug(
                "Deferred goback increment SKIPPED: state did not change "
                f"(blocked by higher priority action/transition)"
            )
            return

        # Get winning action metadata from resolution trace
        winning_metadata = decision.resolution_trace.get("winning_action_metadata", {})

        # Check if this was a pending goback increment
        if not winning_metadata.get("pending_goback_increment"):
            return

        # Get expected target state from metadata
        expected_to_state = winning_metadata.get("to_state")
        actual_next_state = decision.next_state

        # Verify the transition went to the expected state
        # (handles edge case where a different transition won)
        if expected_to_state and actual_next_state != expected_to_state:
            logger.warning(
                f"Deferred goback increment SKIPPED: transition went to "
                f"{actual_next_state} instead of expected {expected_to_state}"
            )
            return

        # Get CircularFlowManager and apply the increment
        circular_flow = getattr(self._state_machine, 'circular_flow', None)
        if circular_flow is None:
            logger.warning("Cannot apply deferred goback increment: CircularFlowManager not available")
            return

        from_state = winning_metadata.get("from_state", prev_state)
        to_state = actual_next_state

        # Use CircularFlowManager.record_go_back() - the canonical method
        # This ensures all go_back recording logic is centralized in CircularFlowManager
        circular_flow.record_go_back(from_state, to_state)

    def _update_state_before_objection(
        self,
        decision: ResolvedDecision,
        prev_state: str,
        state_changed: bool,
    ) -> None:
        """
        Update _state_before_objection based on state transitions and intent patterns.

        This method implements the objection series tracking:
        1. When entering handle_objection from another state, save that state
        2. When the objection streak is broken (positive intent), clear the saved state
        3. When leaving handle_objection normally (not to another objection), clear it

        The saved state is used by get_return_state() to determine where to return
        after successfully handling an objection series.

        Args:
            decision: The resolved decision
            prev_state: State before this turn
            state_changed: Whether state transition occurred
        """
        # Guard: Skip if blackboard not initialized (can happen in tests)
        # Check _current_intent directly to avoid RuntimeError from current_intent property
        if self._blackboard._current_intent is None:
            return

        current_intent = self._blackboard._current_intent
        next_state = decision.next_state

        # Get the intent tracker for streak information
        tracker = self._blackboard._intent_tracker

        # CASE 1: Entering handle_objection from a non-objection handling state
        # Save the state we came from (only once per objection series)
        if (state_changed and
            next_state == "handle_objection" and
            prev_state != "handle_objection" and
            self._state_machine._state_before_objection is None):

            self._state_machine._state_before_objection = prev_state
            logger.debug(
                f"Saved state_before_objection: {prev_state} "
                f"(entering handle_objection)"
            )
            return

        # CASE 2: Positive intent breaks the objection streak
        # IntentTracker automatically resets category_streak when a non-objection intent
        # is recorded. If we have a saved state and the streak is now 0, clear it.
        #
        # ==========================================================================
        # NOT A BUG: _state_before_objection clearing on positive intent
        # ==========================================================================
        #
        # REPORTED CONCERN:
        #   "When client says 'agreement' in handle_objection, _state_before_objection
        #    is cleared prematurely because streak is already 0 from begin_turn()"
        #
        # WHY THIS IS CORRECT (by design):
        #
        # 1. SEMANTIC MEANING: A positive intent (agreement, interest, etc.) in
        #    handle_objection means the objection is RESOLVED. The client accepted
        #    our response. We no longer need to "return" to the previous state.
        #
        # 2. TIMING IS INTENTIONAL:
        #    - begin_turn() → record() → streak resets to 0 for non-objection
        #    - _update_state_before_objection() runs AFTER, sees streak=0
        #    - This is the CORRECT moment to clear: objection series ended
        #
        # 3. WHAT HAPPENS NEXT:
        #    - handle_objection state has its own transitions in YAML
        #    - "agreement" typically transitions to next logical state
        #    - No need to artificially "return" when client is satisfied
        #
        # 4. ALTERNATIVE CONSIDERED:
        #    "Keep _state_before_objection until we LEAVE handle_objection"
        #    This would be wrong because:
        #    - Multiple objections in a row would need the ORIGINAL state
        #    - But after resolution, that state is no longer relevant
        #    - The YAML transitions define the correct next state
        #
        # CALL SEQUENCE:
        #   begin_turn() → record("agreement") → streak=0 → ... → here → clear ✓
        #
        # If different semantics are needed, this is a FEATURE REQUEST, not a bug.
        # ==========================================================================
        if (self._state_machine._state_before_objection is not None and
            current_intent in POSITIVE_INTENTS):

            # Check if objection streak was actually broken
            # (streak is already 0 because record() was called in begin_turn())
            objection_streak = tracker.objection_consecutive() if tracker else 0
            if objection_streak == 0:
                logger.debug(
                    f"Clearing state_before_objection: positive intent '{current_intent}' "
                    f"broke objection streak"
                )
                self._state_machine._state_before_objection = None
                return

        # CASE 3: Leaving handle_objection to a non-objection state
        # (e.g., agreement -> close, or returning to previous state)
        if (state_changed and
            prev_state == "handle_objection" and
            next_state != "handle_objection" and
            self._state_machine._state_before_objection is not None):

            # Only clear if the next state is NOT an objection-related transition
            # (allows returning to saved state)
            if current_intent not in OBJECTION_INTENTS:
                logger.debug(
                    f"Clearing state_before_objection: left handle_objection "
                    f"to {next_state}"
                )
                self._state_machine._state_before_objection = None

    def _fill_compatibility_fields(
        self,
        decision: ResolvedDecision,
        prev_state: str,
    ) -> None:
        """
        Fill compatibility fields in ResolvedDecision for bot.py.

        bot.py expects the following fields in sm_result:
        - prev_state: for metrics and state change detection
        - goal: for generator context
        - collected_data: full dict after applying updates
        - missing_data: list of missing required fields
        - optional_data: list of missing optional fields
        - is_final: whether state is final
        - spin_phase: current SPIN phase
        - circular_flow: CircularFlowManager stats
        - objection_flow: objection stats

        Args:
            decision: ResolvedDecision to fill
            prev_state: State before this turn
        """
        # Get state configuration
        next_config = self._flow_config.states.get(decision.next_state, {})
        required = next_config.get("required_data", [])
        optional = next_config.get("optional_data", [])

        # Fill compatibility fields
        decision.prev_state = prev_state
        decision.goal = next_config.get("goal", "")
        decision.collected_data = self._state_machine.collected_data.copy()
        decision.missing_data = [
            f for f in required
            if not self._state_machine.collected_data.get(f)
        ]
        decision.optional_data = [
            f for f in optional
            if not self._state_machine.collected_data.get(f)
        ]

        # Determine is_final (with objection limit override)
        decision.is_final = next_config.get("is_final", False)
        # Override: soft_close triggered by objection limit is always final
        if (decision.next_state == "soft_close" and
            self._state_machine.collected_data.get("_objection_limit_final")):
            decision.is_final = True

        # Fill phase info
        # FUNDAMENTAL FIX: Use FlowConfig.get_phase_for_state() for all flows
        decision.spin_phase = self._flow_config.get_phase_for_state(decision.next_state)

        # Fill prev_phase for decision_trace phase tracking
        # FUNDAMENTAL FIX: Use FlowConfig.get_phase_for_state() for all flows
        decision.prev_phase = self._flow_config.get_phase_for_state(prev_state)

        # Fill stats
        decision.circular_flow = self._state_machine.circular_flow.get_stats()
        decision.objection_flow = self._get_objection_stats()

        # Disambiguation metadata (for bot.py ask_clarification response path)
        if decision.action == "ask_clarification":
            winning_meta = decision.resolution_trace.get("winning_action_metadata", {})
            decision.disambiguation_options = winning_meta.get("disambiguation_options", [])
            decision.disambiguation_question = winning_meta.get("disambiguation_question", "")

    def _get_objection_stats(self) -> Dict[str, Any]:
        """
        Get objection statistics from IntentTracker.

        Mirrors state_machine._get_objection_stats() for compatibility.
        """
        tracker = self._blackboard._intent_tracker
        return {
            "consecutive_objections": tracker.objection_consecutive(),
            "total_objections": tracker.objection_total(),
            "history": [
                (r.intent, r.state)
                for r in tracker.get_intents_by_category("objection")
            ],
            "return_state": self._state_machine._state_before_objection,
        }

    def get_turn_summary(self) -> Dict[str, Any]:
        """Get summary of the last processed turn."""
        return self._blackboard.get_turn_summary()


# === Factory function for easy setup ===

def create_orchestrator(
    state_machine: 'IStateMachine',
    flow_config: 'IFlowConfig',
    persona_limits: Optional[Dict[str, Dict[str, int]]] = None,
    enable_metrics: bool = True,
    enable_debug_logging: bool = False,
    custom_sources: Optional[List[Type[KnowledgeSource]]] = None,
    tenant_config: Optional['TenantConfig'] = None,  # Multi-tenancy support
    guard: Optional[Any] = None,
    fallback_handler: Optional[Any] = None,
    llm: Optional[Any] = None,
) -> DialogueOrchestrator:
    """
    Factory function to create a fully configured DialogueOrchestrator.

    This is the COMPOSITION ROOT for the Blackboard system (DESIGN_PRINCIPLES.md).
    All dependencies are wired here, not scattered throughout the codebase.

    Hexagonal Architecture:
        - state_machine must implement IStateMachine protocol
        - flow_config must implement IFlowConfig protocol
        - This allows easy testing with mock implementations

    Multi-Tenancy:
        Pass tenant_config to customize behavior per tenant.

    Args:
        state_machine: State machine implementing IStateMachine protocol
        flow_config: Flow config implementing IFlowConfig protocol
        persona_limits: Custom persona limits (uses defaults if None)
        enable_metrics: Whether to enable metrics collection
        enable_debug_logging: Whether to enable debug event logging
        custom_sources: Optional list of custom KnowledgeSource classes to register
        tenant_config: Tenant-specific configuration (optional)

    Returns:
        Configured DialogueOrchestrator instance

    Example:
        # Basic usage (uses all built-in sources)
        orchestrator = create_orchestrator(state_machine, flow_config)

        # With custom source
        class MyCustomSource(KnowledgeSource):
            ...

        orchestrator = create_orchestrator(
            state_machine,
            flow_config,
            custom_sources=[MyCustomSource]
        )

        # With tenant configuration
        tenant = TenantConfig(
            tenant_id="acme_corp",
            bot_name="ACME Sales Assistant",
            tone="friendly",
            features={"escalation": True},
        )
        orchestrator = create_orchestrator(
            state_machine,
            flow_config,
            tenant_config=tenant
        )
    """
    from .event_bus import MetricsCollector, DebugLogger
    from .protocols import DEFAULT_TENANT

    # Use default tenant if not provided
    tenant_config = tenant_config or DEFAULT_TENANT

    # Register custom sources if provided
    if custom_sources:
        for source_class in custom_sources:
            if not SourceRegistry.get_registration(source_class.__name__):
                SourceRegistry.register(
                    source_class,
                    priority_order=200,  # Custom sources run after built-in
                    description=f"Custom source: {source_class.__name__}"
                )
                logger.info(f"Registered custom source: {source_class.__name__}")

    # Create event bus
    event_bus = DialogueEventBus()

    # Add metrics collector
    if enable_metrics:
        metrics_collector = MetricsCollector()
        event_bus.subscribe_all(metrics_collector.handle_event)

    # Add debug logger
    if enable_debug_logging:
        debug_logger = DebugLogger()
        event_bus.subscribe_all(debug_logger.handle_event)

    # Create orchestrator (sources loaded via SourceRegistry)
    orchestrator = DialogueOrchestrator(
        state_machine=state_machine,
        flow_config=flow_config,
        event_bus=event_bus,
        enable_validation=True,
        persona_limits=persona_limits,
        tenant_config=tenant_config,
        guard=guard,
        fallback_handler=fallback_handler,
        llm=llm,
    )

    return orchestrator
