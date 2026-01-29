"""
State Machine — управление состояниями диалога

v2.0: Modular YAML Configuration (domain-independent)

Поддерживает:
- Modular Flow System: FlowConfig с extends/mixins
- DAG State Machine: параллельные потоки и условные ветвления
- Configurable phases: порядок фаз определяется в flow.yaml
- Обработка возражений: handle_objection
- Финальные состояния: success, soft_close
- Circular Flow: возврат назад по фазам (с защитой от злоупотреблений)
- Conditional Rules: условные правила через RuleResolver

Configuration:
- ConfigLoader: загрузка из YAML (src/yaml_config/)
- FlowConfig: модульные flows с наследованием (flows/{flow_name}/)
- DAGNodeConfig: поддержка CHOICE/FORK/JOIN/PARALLEL нод
- ConditionExpressionParser: AND/OR/NOT условия в rules
"""

from typing import Tuple, Dict, Optional, List, Any, Iterator, TYPE_CHECKING
from dataclasses import dataclass

from src.feature_flags import flags
from src.logger import logger
from src.settings import settings

# Phase 4: Conditional Rules imports
from src.intent_tracker import IntentTracker
from src.conditions.state_machine.context import EvaluatorContext
from src.conditions.state_machine.registry import sm_registry
from src.rules.resolver import RuleResolver
from src.conditions.trace import EvaluationTrace, TraceCollector, Resolution

# YAML config constants (single source of truth)
from src.yaml_config.constants import (
    GO_BACK_INTENTS,
    OBJECTION_INTENTS,
    POSITIVE_INTENTS,
    QUESTION_INTENTS,
    INTENT_CATEGORIES,
    ALLOWED_GOBACKS,
    MAX_CONSECUTIVE_OBJECTIONS,
    MAX_TOTAL_OBJECTIONS,
)

if TYPE_CHECKING:
    from src.config_loader import LoadedConfig, FlowConfig
    from src.dag.models import DAGExecutionContext


# =============================================================================
# Stage 14: RuleResult REMOVED - use src.rules.resolver.RuleResult instead
# The Blackboard system now handles all rule resolution logic.
# =============================================================================


class CircularFlowManager:
    """
    Управление возвратами назад с защитой от злоупотреблений.

    Позволяет клиенту вернуться к предыдущей фазе,
    но ограничивает количество возвратов для предотвращения зацикливания.

    UNIFIED GO_BACK LOGIC:
        This class is the SINGLE SOURCE OF TRUTH for go_back logic.
        It handles both:
        1. allowed_gobacks map (legacy SPIN states from constants.yaml)
        2. YAML transitions (go_back: "{{prev_phase_state}}" in any flow)

        GoBackGuardSource should use methods from this class instead of
        duplicating the logic.

    Attributes:
        goback_count: Количество совершённых возвратов
        goback_history: История возвратов (from_state, to_state)
        max_gobacks: Максимально допустимое количество возвратов
        allowed_gobacks: Разрешённые переходы назад (из YAML конфига)
    """

    # Default values (used when no config provided)
    MAX_GOBACKS = 2  # Максимум возвратов за диалог

    def __init__(
        self,
        allowed_gobacks: Dict[str, str] = None,
        max_gobacks: int = None
    ):
        """
        Инициализация менеджера.

        Args:
            allowed_gobacks: Разрешённые переходы (из YAML конфига).
                             Если не передан, берётся из constants.yaml.
            max_gobacks: Максимум возвратов (из YAML конфига)
        """
        # Use ALLOWED_GOBACKS from constants.yaml if not provided
        if allowed_gobacks is None:
            self.allowed_gobacks = ALLOWED_GOBACKS.copy() if ALLOWED_GOBACKS else {}
        else:
            self.allowed_gobacks = allowed_gobacks
        self.max_gobacks = max_gobacks if max_gobacks is not None else self.MAX_GOBACKS
        self.reset()

    def reset(self) -> None:
        """Сброс для нового разговора"""
        self.goback_count: int = 0
        self.goback_history: List[tuple] = []

    def is_limit_reached(self) -> bool:
        """Check if go_back limit is reached."""
        return self.goback_count >= self.max_gobacks

    def can_go_back(
        self,
        current_state: str,
        yaml_transitions: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Проверить можно ли вернуться назад.

        UNIFIED CHECK: This method checks both limit AND transition availability.
        It's the CANONICAL way to check if go_back is allowed.

        Priority:
        1. Check limit first (count < max)
        2. Check YAML transitions (if provided)
        3. Fall back to allowed_gobacks map

        Args:
            current_state: Текущее состояние
            yaml_transitions: Optional YAML transitions dict from state_config.
                             If provided, checks yaml_transitions["go_back"] first.

        Returns:
            True если возврат возможен (limit not reached AND target exists)
        """
        # Check limit first
        if self.is_limit_reached():
            logger.debug(
                f"Go back limit reached: count={self.goback_count}, max={self.max_gobacks}"
            )
            return False

        # Check if target exists
        target = self.get_go_back_target(current_state, yaml_transitions)
        return target is not None

    def get_go_back_target(
        self,
        current_state: str,
        yaml_transitions: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Get the target state for go_back transition.

        UNIFIED LOOKUP: This method is the CANONICAL way to get go_back target.

        Priority:
        1. YAML transitions (if provided and has go_back key)
        2. allowed_gobacks map (legacy support)

        Args:
            current_state: Текущее состояние
            yaml_transitions: Optional YAML transitions dict from state_config

        Returns:
            Target state name, or None if no go_back transition defined
        """
        # Priority 1: YAML transitions
        if yaml_transitions:
            yaml_target = yaml_transitions.get("go_back")
            if yaml_target:
                return yaml_target

        # Priority 2: allowed_gobacks map (legacy)
        return self.allowed_gobacks.get(current_state)

    def go_back(self, current_state: str) -> Optional[str]:
        """
        Выполнить возврат назад (LEGACY METHOD).

        DEPRECATED: Use can_go_back() + record_go_back() instead.
        This method is kept for backward compatibility with code that
        directly calls go_back() without the Blackboard pipeline.

        Args:
            current_state: Текущее состояние

        Returns:
            Предыдущее состояние или None если возврат невозможен
        """
        if not self.can_go_back(current_state):
            return None

        prev_state = self.allowed_gobacks.get(current_state)
        if prev_state:
            self.record_go_back(current_state, prev_state)

        return prev_state

    def record_go_back(self, from_state: str, to_state: str) -> None:
        """
        Record a successful go_back transition.

        This method is called by Orchestrator._apply_deferred_goback_increment()
        AFTER the conflict resolution confirms that go_back actually happened.

        This is part of the DEFERRED INCREMENT mechanism that prevents
        incorrect counter increment when higher-priority sources block go_back.

        Args:
            from_state: State before go_back
            to_state: State after go_back
        """
        self.goback_count += 1
        self.goback_history.append((from_state, to_state))
        logger.info(
            f"Go back recorded: {from_state} -> {to_state}, "
            f"count={self.goback_count}, remaining={self.get_remaining_gobacks()}"
        )

    def get_remaining_gobacks(self) -> int:
        """Получить оставшееся количество возвратов"""
        return max(0, self.max_gobacks - self.goback_count)

    def get_history(self) -> List[tuple]:
        """Получить историю возвратов"""
        return self.goback_history.copy()

    def get_stats(self) -> Dict:
        """Получить статистику для аналитики"""
        return {
            "goback_count": self.goback_count,
            "remaining": self.get_remaining_gobacks(),
            "history": self.goback_history,
        }


class StateMachine:
    """
    State Machine for managing dialogue states.

    v2.0: Modular YAML Configuration (legacy Python constants deprecated)

    Configuration (auto-loaded if not provided):
    - LoadedConfig: YAML constants and states from ConfigLoader
    - FlowConfig: Modular flow with extends/mixins from flows/spin_selling/

    Features:
    - IntentTracker: unified intent history
    - RuleResolver: conditional rules with AND/OR/NOT expressions
    - EvaluatorContext: typed context for condition evaluation
    - DAGExecutor: parallel branches and conditional routing (when DAG nodes defined)
    """

    def __init__(
        self,
        enable_tracing: bool = False,
        config: "LoadedConfig" = None,
        flow: "FlowConfig" = None
    ):
        """
        Initialize StateMachine.

        Args:
            enable_tracing: If True, collect EvaluationTrace for debugging
            config: LoadedConfig from ConfigLoader (auto-loaded if not provided)
            flow: FlowConfig for modular flow (auto-loaded if not provided)

        Since v2.0: config and flow are always loaded from YAML.
        Legacy Python constants are deprecated.
        """
        self.state = "greeting"
        self.collected_data = {}
        self.current_phase = None  # Current phase name from flow

        # Auto-load config and flow if not provided (v2.0: YAML is the source of truth)
        if config is None or flow is None:
            from src.config_loader import ConfigLoader
            loader = ConfigLoader()
            if config is None:
                config = loader.load()
            if flow is None:
                # Load flow from settings (configurable, not hardcoded)
                flow = loader.load_flow(settings.flow.active)

        # Store config for parameterization (always set since v2.0)
        self._config = config
        self._flow = flow

        # Initialize circular flow with config if available
        if config:
            allowed_gobacks = config.circular_flow.get("allowed_gobacks", {})
            max_gobacks = config.limits.get("max_gobacks", CircularFlowManager.MAX_GOBACKS)
            self.circular_flow = CircularFlowManager(
                allowed_gobacks=allowed_gobacks,
                max_gobacks=max_gobacks
            )
        else:
            self.circular_flow = CircularFlowManager()

        # Phase 4: IntentTracker replaces ObjectionFlowManager
        self.intent_tracker = IntentTracker()

        # Phase 4/Phase 1: RuleResolver with optional expression parser and taxonomy
        if config:
            expression_parser = None
            if config.custom_conditions:
                from src.conditions.expression_parser import ConditionExpressionParser
                expression_parser = ConditionExpressionParser(
                    sm_registry,
                    config.custom_conditions
                )

            # Create taxonomy registry for intelligent fallback
            from src.rules.intent_taxonomy import IntentTaxonomyRegistry
            taxonomy_registry = IntentTaxonomyRegistry(config.taxonomy_config)

            self._resolver = RuleResolver(
                sm_registry,
                default_action=config.default_action,
                expression_parser=expression_parser,
                taxonomy_registry=taxonomy_registry
            )
        else:
            self._resolver = RuleResolver(sm_registry)

        self._enable_tracing = enable_tracing
        self._trace_collector = TraceCollector() if enable_tracing else None
        self._last_trace: Optional[EvaluationTrace] = None

        # Disambiguation state
        self.in_disambiguation: bool = False
        self.disambiguation_context: Optional[Dict] = None
        self.pre_disambiguation_state: Optional[str] = None
        self.turns_since_last_disambiguation: int = 999  # Большое число = давно не было

        # Для контекстной классификации (backward compat - also accessible via intent_tracker)
        self.last_action: Optional[str] = None

        # State before objection (for returning after handling)
        self._state_before_objection: Optional[str] = None

        # DAG Support (Phase DAG)
        self._dag_enabled = True  # DAG mode enabled by default (backward compat)
        self._dag_context: Optional["DAGExecutionContext"] = None
        self._dag_executor = None  # Lazy initialized

    # =========================================================================
    # Configuration Properties (from YAML - legacy Python constants deprecated)
    # =========================================================================

    @property
    def max_consecutive_objections(self) -> int:
        """Get max consecutive objections limit from YAML config."""
        return self._config.limits.get("max_consecutive_objections", 3)

    @property
    def max_total_objections(self) -> int:
        """Get max total objections limit from YAML config."""
        return self._config.limits.get("max_total_objections", 5)

    @property
    def phase_order(self) -> List[str]:
        """Get phase order from FlowConfig."""
        return self._flow.phase_order

    # Alias for backward compatibility
    @property
    def spin_phases(self) -> List[str]:
        """Get SPIN phases order (legacy alias for phase_order)."""
        return self.phase_order

    @property
    def phase_states(self) -> Dict[str, str]:
        """Get phase to state mapping from FlowConfig."""
        return self._flow.phase_mapping

    # Alias for backward compatibility
    @property
    def spin_states(self) -> Dict[str, str]:
        """Get SPIN phase to state mapping (legacy alias for phase_states)."""
        return self.phase_states

    @property
    def progress_intents(self) -> Dict[str, str]:
        """Get progress intents mapping from FlowConfig."""
        return self._flow.progress_intents

    # Alias for backward compatibility
    @property
    def spin_progress_intents(self) -> Dict[str, str]:
        """Get SPIN progress intents mapping (legacy alias for progress_intents)."""
        return self.progress_intents

    @property
    def spin_phase(self) -> Optional[str]:
        """Legacy alias for current_phase."""
        return self.current_phase

    @spin_phase.setter
    def spin_phase(self, value: Optional[str]) -> None:
        """Legacy setter for current_phase."""
        self.current_phase = value

    @property
    def states_config(self) -> Dict[str, Any]:
        """Get states configuration from FlowConfig."""
        return self._flow.states

    @property
    def priorities(self) -> List[Dict[str, Any]]:
        """
        Get processing priorities configuration.

        Returns list of priority definitions from FlowConfig.
        These define the order of processing in apply_rules().

        Note: Currently used for introspection. Full priority-driven
        apply_rules() is planned for future enhancement.
        """
        if self._flow:
            return self._flow.priorities
        return []

    @property
    def last_intent(self) -> Optional[str]:
        """Get last intent from tracker (backward compat property)."""
        return self.intent_tracker.last_intent

    @last_intent.setter
    def last_intent(self, value: Optional[str]) -> None:
        """Setter exists for backward compat but does nothing.
        Use intent_tracker.record() instead."""
        pass  # Intent is set via intent_tracker.record()

    @property
    def turn_number(self) -> int:
        """Get current turn number from tracker."""
        return self.intent_tracker.turn_number

    # =========================================================================
    # DAG Properties and Methods
    # =========================================================================

    @property
    def dag_context(self) -> Optional["DAGExecutionContext"]:
        """
        Get DAG execution context.

        Returns None if DAG mode is not active.
        Context is lazily initialized when first DAG node is encountered.
        """
        return self._dag_context

    @property
    def is_dag_mode(self) -> bool:
        """
        Check if currently in DAG mode.

        DAG mode is active when:
        - There are active parallel branches
        - We are inside a fork
        """
        return (
            self._dag_context is not None and
            self._dag_context.is_dag_mode
        )

    @property
    def active_branches(self) -> List[str]:
        """Get list of active branch IDs (empty if not in DAG mode)."""
        if self._dag_context:
            return self._dag_context.active_branch_ids
        return []

    @property
    def dag_events(self) -> List[Dict]:
        """Get DAG events log for debugging/analytics."""
        if self._dag_context:
            return [e.to_dict() for e in self._dag_context.events]
        return []

    def _init_dag_context(self) -> "DAGExecutionContext":
        """Initialize DAG context lazily."""
        if self._dag_context is None:
            from src.dag.models import DAGExecutionContext
            self._dag_context = DAGExecutionContext(primary_state=self.state)
        return self._dag_context

    def _get_dag_executor(self):
        """Get or create DAG executor lazily."""
        if self._dag_executor is None and self._flow:
            from src.dag.executor import DAGExecutor
            self._dag_executor = DAGExecutor(
                flow_config=self._flow,
                condition_registry=sm_registry,
            )
        return self._dag_executor

    def is_dag_state(self, state_id: str) -> bool:
        """Check if a state is a DAG node (choice, fork, join, parallel)."""
        if self._flow:
            return self._flow.is_dag_state(state_id)
        return False

    def _apply_dag_rules(
        self,
        intent: str,
        context_envelope: Any = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Apply DAG rules for current state.

        Called when current state is a DAG node (choice, fork, join, parallel).

        Args:
            intent: Current intent
            context_envelope: Optional context envelope

        Returns:
            Tuple[action, next_state] or None if DAG processing failed
        """
        # Initialize DAG context if needed
        dag_ctx = self._init_dag_context()

        # Get or create executor
        executor = self._get_dag_executor()
        if not executor:
            logger.warning("DAG executor not available")
            return None

        # Build evaluator context
        config = self.states_config.get(self.state, {})
        ctx = EvaluatorContext.from_state_machine(
            self, intent, config, context_envelope=context_envelope
        )

        # Execute DAG node
        result = executor.execute_node(
            node_id=self.state,
            intent=intent,
            ctx=ctx,
            dag_ctx=dag_ctx,
        )

        if not result.is_dag:
            # Not a DAG node, let normal processing handle it
            return None

        # Handle DAG result
        logger.debug(
            f"DAG result for state '{self.state}': "
            f"action='{result.action}', primary_state='{result.primary_state}'"
        )

        # Update state if changed
        if result.primary_state and result.primary_state != self.state:
            old_state = self.state
            self.state = result.primary_state
            logger.debug(f"DAG transition: {old_state} -> {self.state}")

        # Merge aggregated data from completed branches
        if result.aggregated_data:
            self.collected_data["_dag_results"] = result.aggregated_data
            # Also merge individual branch data into collected_data
            for branch_id, branch_data in result.aggregated_data.items():
                for key, value in branch_data.items():
                    if key not in self.collected_data:
                        self.collected_data[key] = value

        # Update DAG context primary state
        dag_ctx.primary_state = self.state

        return result.action, result.primary_state

    def reset(self):
        """Reset for new conversation."""
        self.state = "greeting"
        self.collected_data = {}
        self.current_phase = None
        self.circular_flow.reset()

        # Phase 4: Reset IntentTracker
        self.intent_tracker.reset()

        # Reset tracing
        if self._trace_collector:
            self._trace_collector.clear()
        self._last_trace = None

        # Reset DAG context
        if self._dag_context:
            self._dag_context.reset()

        # Reset disambiguation state
        self.in_disambiguation = False
        self.disambiguation_context = None
        self.pre_disambiguation_state = None
        self.turns_since_last_disambiguation = 999

        self.last_action = None
        self._state_before_objection = None

        # Clear objection limit flag (also cleared by collected_data = {} above,
        # but explicit clear for documentation)
        self.collected_data.pop("_objection_limit_final", None)

    # =========================================================================
    # Atomic State Transition (FIX: Distributed State Mutation)
    # =========================================================================

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "unknown",
        validate: bool = True,
    ) -> bool:
        """
        Atomically transition to a new state with consistent updates.

        This method is the SINGLE POINT OF CONTROL for state changes,
        ensuring that state, current_phase, and last_action are always
        consistent with each other.

        DESIGN RATIONALE (FIX for Distributed State Mutation bug):
        Previously, orchestrator and bot.py both directly modified
        state_machine.state, leading to inconsistencies where:
        - state = "spin_implication" (from bot.py)
        - current_phase = "problem" (from orchestrator for different state)

        This method ensures atomicity by:
        1. Validating the target state exists (if validate=True)
        2. Computing phase from flow config if not provided
        3. Updating state, current_phase, last_action together
        4. Logging the transition for debugging

        Args:
            next_state: Target state to transition to
            action: Action that triggered this transition (optional)
            phase: Phase for the new state (computed from config if not provided)
            source: Identifier for debugging (e.g., "orchestrator", "policy_override")
            validate: If True, validate that next_state exists in flow config

        Returns:
            True if transition was successful, False if validation failed

        Example:
            # Instead of:
            #   state_machine.state = "spin_problem"
            #   state_machine.current_phase = "problem"  # might forget this!
            #
            # Use:
            state_machine.transition_to(
                next_state="spin_problem",
                action="ask_problem_questions",
                source="orchestrator"
            )
        """
        prev_state = self.state

        # Validation: check if target state exists in flow config
        if validate and self._flow:
            if next_state not in self._flow.states:
                logger.warning(
                    f"transition_to: Invalid state '{next_state}' - not in flow config",
                    source=source,
                    current_state=prev_state,
                )
                return False

        # Compute phase from flow config if not provided
        # FUNDAMENTAL FIX: Use FlowConfig.get_phase_for_state() for all flows
        if phase is None and self._flow:
            phase = self._flow.get_phase_for_state(next_state)

        # ATOMIC UPDATE: All three attributes are updated together
        self.state = next_state
        self.current_phase = phase
        if action is not None:
            self.last_action = action

        # Log transition for debugging
        if prev_state != next_state:
            logger.debug(
                f"State transition: {prev_state} -> {next_state}",
                phase=phase,
                action=action,
                source=source,
            )

        return True

    def sync_phase_from_state(self) -> None:
        """
        Synchronize current_phase with the current state.

        Call this after external code directly modifies state_machine.state
        to ensure current_phase is consistent.

        This is a SAFETY NET for backward compatibility with code that
        still directly assigns to state_machine.state.

        FUNDAMENTAL FIX: Uses FlowConfig.get_phase_for_state() which handles
        both explicit phase fields (SPIN) and reverse mapping from phase_mapping
        (BANT, MEDDIC, etc.).
        """
        if self._flow:
            # Use FlowConfig's canonical phase resolution
            # This handles ALL flows correctly:
            # - SPIN: uses explicit state_config.phase
            # - BANT, MEDDIC, etc.: uses reverse mapping from phases.mapping
            self.current_phase = self._flow.get_phase_for_state(self.state)

    # =========================================================================
    # Phase 4: Objection tracking via IntentTracker
    # =========================================================================

    def _get_objection_stats(self) -> Dict:
        """
        Get objection statistics from IntentTracker.

        Replaces ObjectionFlowManager.get_stats().
        """
        return {
            "consecutive_objections": self.intent_tracker.objection_consecutive(),
            "total_objections": self.intent_tracker.objection_total(),
            "history": [
                (r.intent, r.state)
                for r in self.intent_tracker.get_intents_by_category("objection")
            ],
            "return_state": self._state_before_objection,
        }

    def _check_objection_limit(self) -> bool:
        """
        Check if objection limit has been reached.

        Replaces ObjectionFlowManager.should_soft_close().
        Uses configurable limits from YAML or falls back to constants.
        """
        consecutive = self.intent_tracker.objection_consecutive()
        total = self.intent_tracker.objection_total()

        if consecutive >= self.max_consecutive_objections:
            logger.info(
                "Consecutive objection limit reached",
                count=consecutive,
                limit=self.max_consecutive_objections
            )
            return True

        if total >= self.max_total_objections:
            logger.info(
                "Total objection limit reached",
                total=total,
                limit=self.max_total_objections
            )
            return True

        return False

    def _should_skip_objection_recording(self, intent: str) -> bool:
        """
        Check if objection recording should be skipped.

        Prevents counter from growing beyond limit when soft_close
        continues the dialog (e.g., when is_final=false).

        Args:
            intent: The intent to check

        Returns:
            True if recording should be skipped (limit already reached)
        """
        if intent not in OBJECTION_INTENTS:
            return False

        # Check if limit already reached
        consecutive = self.intent_tracker.objection_consecutive()
        total = self.intent_tracker.objection_total()

        if consecutive >= self.max_consecutive_objections or total >= self.max_total_objections:
            logger.debug(
                "Skipping objection recording - limit already reached",
                intent=intent,
                consecutive=consecutive,
                total=total
            )
            return True
        return False

    # Backward compatibility property for objection_flow
    @property
    def objection_flow(self) -> 'ObjectionFlowAdapter':
        """
        Backward compatibility adapter for objection_flow access.

        Returns an adapter that delegates to IntentTracker methods.
        """
        return ObjectionFlowAdapter(self)

    def update_data(self, data: Dict):
        """Сохраняем извлечённые данные"""
        for key, value in data.items():
            if value:
                self.collected_data[key] = value

    def is_final(self) -> bool:
        """
        Check if current state is a final state.

        Returns:
            True if current state is marked as final in config.
        """
        config = self._flow.states.get(self.state, {})
        is_final_flag = config.get("is_final", False)

        # ======================================================================
        # NOT A BUG: _objection_limit_final prevents infinite soft_close loop
        # ======================================================================
        #
        # REPORTED CONCERN:
        #   "If soft_close.is_final=false in YAML, and user continues objecting,
        #    ObjectionGuard keeps proposing soft_close → infinite loop"
        #
        # WHY THIS CANNOT HAPPEN:
        #
        # 1. THIS OVERRIDE (below):
        #    When soft_close is reached via objection limit, ObjectionGuardSource
        #    sets _objection_limit_final=True flag (objection_guard.py:178-183).
        #    This flag OVERRIDES the YAML is_final setting.
        #
        # 2. _should_skip_objection_recording() in blackboard.py:208-248:
        #    Before recording objection intent, checks if limit already reached.
        #    If so, skips recording → counter stays at limit (doesn't grow 3→6→9).
        #
        # 3. BOT TERMINATION:
        #    is_final=True → bot ends conversation → no more turns → no loop.
        #
        # EVEN IF YAML says is_final=false, the flag makes it True.
        # This is defense in depth against configuration errors.
        # ======================================================================
        if self.state == "soft_close" and self.collected_data.get("_objection_limit_final"):
            is_final_flag = True

        return is_final_flag

    # =========================================================================
    # Disambiguation Methods
    # =========================================================================

    def increment_turn(self) -> None:
        """
        Вызывать в начале каждого process() для отслеживания cooldown.
        """
        if self.turns_since_last_disambiguation < 999:
            self.turns_since_last_disambiguation += 1

    def enter_disambiguation(
        self,
        options: List[Dict],
        extracted_data: Optional[Dict] = None
    ) -> None:
        """
        Войти в режим disambiguation.

        Args:
            options: Список вариантов для пользователя
            extracted_data: Извлечённые данные для сохранения
        """
        self.pre_disambiguation_state = self.state
        self.in_disambiguation = True
        self.disambiguation_context = {
            "options": options,
            "original_state": self.state,
            "extracted_data": extracted_data or {},
            "attempt": 1,
        }

    def resolve_disambiguation(self, resolved_intent: str) -> Tuple[str, str]:
        """
        Разрешить disambiguation с выбранным интентом.

        Args:
            resolved_intent: Выбранный пользователем интент

        Returns:
            Tuple[current_state, resolved_intent]
        """
        current_state = self.state
        self._exit_disambiguation_internal()
        return current_state, resolved_intent

    def exit_disambiguation(self) -> None:
        """Выйти из режима disambiguation без разрешения."""
        self._exit_disambiguation_internal()

    def _exit_disambiguation_internal(self) -> None:
        """Внутренний метод для выхода из disambiguation."""
        self.in_disambiguation = False
        self.disambiguation_context = None
        self.pre_disambiguation_state = None
        self.turns_since_last_disambiguation = 0

    def get_context(self) -> Dict:
        """
        Получить контекст для классификатора.

        Returns:
            Dict с текущим контекстом состояния
        """
        context = {
            "state": self.state,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "spin_phase": self.spin_phase,
            "missing_data": self._get_missing_data(),
            "turns_since_last_disambiguation": self.turns_since_last_disambiguation,
        }

        if self.in_disambiguation:
            context["in_disambiguation"] = True

        return context

    def _get_missing_data(self) -> List[str]:
        """Получить список недостающих обязательных данных."""
        config = self.states_config.get(self.state, {})
        required = config.get("required_data", [])
        return [f for f in required if not self.collected_data.get(f)]

    # =========================================================================
    # Phase Methods (abstracted from SPIN)
    # =========================================================================

    def _get_current_phase(self) -> Optional[str]:
        """
        Get current phase from state configuration.

        Supports both 'phase' (new) and 'spin_phase' (legacy) field names.
        """
        config = self.states_config.get(self.state, {})
        # Try 'phase' first, then fall back to 'spin_phase' for backward compatibility
        return config.get("phase") or config.get("spin_phase")

    # Alias for backward compatibility
    _get_current_spin_phase = _get_current_phase

    def _get_intent_category(self, category_name: str) -> Optional[set]:
        """
        Get intent category from YAML config (constants.yaml).

        Args:
            category_name: Name of the category (e.g., "price_related", "question_requires_facts")

        Returns:
            Set of intents in the category, or None if not found
        """
        # Try FlowConfig first (Phase 4)
        if self._flow:
            category = self._flow.get_intent_category(category_name)
            if category:
                return set(category)

        # Fallback 1: Try self._constants.intents.{category_name}
        if hasattr(self, '_constants') and self._constants:
            intents_config = self._constants.get("intents", {})
            # Check directly under intents (e.g., intents.price_related)
            if category_name in intents_config:
                category = intents_config[category_name]
                if isinstance(category, list):
                    return set(category)
            # Legacy path: intents.categories.{category_name}
            categories = intents_config.get("categories", {})
            if category_name in categories:
                return set(categories[category_name])

        # Fallback 2: Try global config
        try:
            from src.config_loader import get_config
            config = get_config()
            category = config.intents.get(category_name)
            if category:
                return set(category)
        except Exception:
            pass

        return None

    def _get_next_phase_state(self, current_phase: str) -> Optional[str]:
        """
        Get next state in the phase progression.

        Uses FlowConfig.post_phases_state if available, otherwise falls back
        to "presentation" for backward compatibility with SPIN flow.
        """
        phases = self.phase_order
        states = self.phase_states

        if current_phase not in phases:
            return None

        current_idx = phases.index(current_phase)
        if current_idx < len(phases) - 1:
            next_phase = phases[current_idx + 1]
            return states.get(next_phase)

        # After last phase - use configured post_phases_state or default
        return self._post_phases_state

    # Alias for backward compatibility
    _get_next_spin_state = _get_next_phase_state

    @property
    def _post_phases_state(self) -> str:
        """State to transition to after all phases complete."""
        if self._flow and self._flow.post_phases_state:
            return self._flow.post_phases_state
        # Fallback for backward compatibility
        return "presentation"

    def _check_phase_data_complete(self, config: Dict) -> bool:
        """Check if required data for current phase is collected."""
        required = config.get("required_data", [])
        if not required:
            return True  # No required data = complete

        for field in required:
            if not self.collected_data.get(field):
                return False
        return True

    # Alias for backward compatibility
    _check_spin_data_complete = _check_phase_data_complete

    def _should_skip_phase(self, phase: str) -> bool:
        """
        Determine if a phase can be skipped.

        Checks skip_conditions from FlowConfig.
        """
        if not self._flow or not self._flow.skip_conditions:
            return False

        skip_conditions = self._flow.skip_conditions.get(phase, [])
        for condition in skip_conditions:
            if self._evaluate_skip_condition(condition):
                return True
        return False

    # Alias for backward compatibility
    _should_skip_spin_phase = _should_skip_phase

    def _evaluate_skip_condition(self, condition: str) -> bool:
        """Evaluate a skip condition by name."""
        # Check collected_data for the condition
        if condition == "has_high_interest":
            return bool(self.collected_data.get("high_interest"))
        elif condition == "has_desired_outcome":
            return bool(self.collected_data.get("desired_outcome"))
        elif condition == "lead_is_hot":
            return self.collected_data.get("lead_temperature") in ["hot", "very_hot"]
        # Default: try to evaluate via condition registry
        return False

    def _is_phase_progression(self, intent_phase: str, current_phase: str) -> bool:
        """
        Check if intent_phase represents progress from current_phase.

        Args:
            intent_phase: Phase indicated by the intent
            current_phase: Current phase

        Returns:
            True if intent_phase is at or after current_phase
        """
        phases = self.phase_order

        if intent_phase not in phases or current_phase not in phases:
            return False

        intent_idx = phases.index(intent_phase)
        current_idx = phases.index(current_phase)

        return intent_idx >= current_idx

    # Alias for backward compatibility
    _is_spin_phase_progression = _is_phase_progression

    def _resolve_transition(
        self,
        intent_or_key: str,
        transitions: Dict,
        ctx: Any,
        trace: Optional['EvaluationTrace'] = None
    ) -> Optional[str]:
        """
        Resolve a transition, handling both simple strings and conditional rules.

        Args:
            intent_or_key: The intent or key to look up in transitions (e.g., "rejection", "data_complete")
            transitions: Transition dictionary from state config
            ctx: EvaluatorContext for condition evaluation
            trace: Optional trace for debugging

        Returns:
            Next state name, or None if intent not in transitions
        """
        if intent_or_key not in transitions:
            return None

        value = transitions[intent_or_key]

        # Simple string - return directly
        if isinstance(value, str):
            return value

        # Conditional rule - use resolver
        if isinstance(value, (list, dict)):
            return self._resolver.resolve_transition(
                intent=intent_or_key,
                transitions=transitions,
                ctx=ctx,
                state=self.state,
                trace=trace
            )

        return None

    # =========================================================================
    # Stage 14: LEGACY METHODS REMOVED
    # =========================================================================
    # The following methods have been REMOVED as part of Stage 14 migration:
    #   - _apply_priority()
    #   - _priority_matches_intent()
    #   - _evaluate_priority_condition()
    #   - _call_priority_handler()
    #   - _apply_rules_priority_driven()
    #   - apply_rules()
    #
    # All dialogue management logic is now handled by the Blackboard system:
    #   from src.blackboard import create_orchestrator
    #   orchestrator = create_orchestrator(state_machine, flow_config)
    #   decision = orchestrator.process_turn(intent, extracted_data, context_envelope)
    #
    # See: src/blackboard/orchestrator.py for the new implementation.
    # =========================================================================

    def apply_rules(self, intent: str, context_envelope: Any = None) -> Tuple[str, str]:
        """
        DEPRECATED: This method is deprecated in Stage 14.

        All dialogue management logic is now handled by the Blackboard system.
        Use DialogueOrchestrator.process_turn() instead:

            from src.blackboard import create_orchestrator
            orchestrator = create_orchestrator(state_machine, flow_config)
            decision = orchestrator.process_turn(intent, extracted_data, context_envelope)
            sm_result = decision.to_sm_result()

        This stub is kept for backward compatibility with tests.
        It raises DeprecationWarning and returns a default action.

        Args:
            intent: The intent to process
            context_envelope: Optional ContextEnvelope (ignored)

        Returns:
            Tuple[str, str]: ("continue_current_goal", current_state)
        """
        import warnings
        warnings.warn(
            "StateMachine.apply_rules() is deprecated. "
            "Use DialogueOrchestrator.process_turn() from src.blackboard instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Record intent for tracking (still needed for compatibility)
        if not self._should_skip_objection_recording(intent):
            self.intent_tracker.record(intent, self.state)

        # FIX: Track state_before_objection for compatibility with tests
        # This logic mirrors orchestrator._update_state_before_objection()
        self._update_state_before_objection_legacy(intent)

        # Return default - tests and legacy code may still call this
        return "continue_current_goal", self.state

    def _update_state_before_objection_legacy(self, intent: str) -> None:
        """
        Update _state_before_objection for legacy apply_rules() compatibility.

        This method mirrors the logic in orchestrator._update_state_before_objection()
        but works in the context of the deprecated apply_rules() method.

        Used by tests that still call apply_rules() directly.

        Args:
            intent: The intent that was just recorded
        """
        # CASE 1: Objection intent - save current state if not already saved
        if intent in OBJECTION_INTENTS:
            if self._state_before_objection is None and self.state != "handle_objection":
                self._state_before_objection = self.state
                logger.debug(
                    f"[legacy] Saved state_before_objection: {self.state} "
                    f"(objection intent: {intent})"
                )
            return

        # CASE 2: Positive intent - clear saved state if streak is broken
        if intent in POSITIVE_INTENTS:
            if self._state_before_objection is not None:
                # IntentTracker already recorded the intent and reset the streak
                objection_streak = self.intent_tracker.objection_consecutive()
                if objection_streak == 0:
                    logger.debug(
                        f"[legacy] Clearing state_before_objection: "
                        f"positive intent '{intent}' broke objection streak"
                    )
                    self._state_before_objection = None

    def get_last_trace(self) -> Optional[EvaluationTrace]:
        """Get the last evaluation trace (if tracing is enabled)."""
        return self._last_trace

    def get_trace_summary(self) -> Optional[Dict]:
        """Get summary of all traces (if tracing is enabled)."""
        if self._trace_collector:
            return self._trace_collector.get_summary().to_dict()
        return None

    def process(
        self,
        intent: str,
        extracted_data: Dict = None,
        context_envelope: Any = None
    ) -> Dict:
        """
        DEPRECATED: This method is deprecated in Stage 14.

        All dialogue management logic is now handled by the Blackboard system.
        Use DialogueOrchestrator.process_turn() instead:

            from src.blackboard import create_orchestrator
            orchestrator = create_orchestrator(state_machine, flow_config)
            decision = orchestrator.process_turn(intent, extracted_data, context_envelope)
            sm_result = decision.to_sm_result()

        This stub is kept for backward compatibility with tests.
        It performs minimal processing and returns a default result.

        Args:
            intent: The intent to process
            extracted_data: Optional extracted data to update
            context_envelope: Optional ContextEnvelope (ignored)

        Returns:
            Dict with action, next_state, and compatibility fields
        """
        import warnings
        warnings.warn(
            "StateMachine.process() is deprecated. "
            "Use DialogueOrchestrator.process_turn() from src.blackboard instead.",
            DeprecationWarning,
            stacklevel=2
        )

        prev_state = self.state

        if extracted_data:
            self.update_data(extracted_data)

        # Use deprecated apply_rules (which also warns)
        # Suppress the nested warning to avoid double-warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            action, next_state = self.apply_rules(intent, context_envelope=context_envelope)

        self.state = next_state
        self.last_action = action
        self.current_phase = self._get_current_phase()

        config = self.states_config.get(self.state, {})
        required = config.get("required_data", [])
        missing = [f for f in required if not self.collected_data.get(f)]
        optional = config.get("optional_data", [])
        optional_missing = [f for f in optional if not self.collected_data.get(f)]

        is_final = config.get("is_final", False)
        if self.state == "soft_close" and self.collected_data.get("_objection_limit_final"):
            is_final = True

        return {
            "action": action,
            "prev_state": prev_state,
            "next_state": next_state,
            "goal": config.get("goal", ""),
            "collected_data": self.collected_data.copy(),
            "missing_data": missing,
            "optional_data": optional_missing,
            "is_final": is_final,
            "spin_phase": self.spin_phase,
            "circular_flow": self.circular_flow.get_stats(),
            "objection_flow": self._get_objection_stats(),
        }

    # =========================================================================
    # Phase 4: Context building for external systems
    # =========================================================================

    def build_evaluator_context(self, intent: str) -> EvaluatorContext:
        """
        Build an EvaluatorContext for condition evaluation.

        Useful for external systems that need to evaluate conditions
        against the current StateMachine state.

        Args:
            intent: Current intent being processed

        Returns:
            EvaluatorContext with current state data
        """
        config = self.states_config.get(self.state, {})
        return EvaluatorContext.from_state_machine(self, intent, config)


# =============================================================================
# Phase 4: ObjectionFlowAdapter for backward compatibility
# =============================================================================

class ObjectionFlowAdapter:
    """
    Adapter for backward compatibility with ObjectionFlowManager API.

    Delegates all calls to IntentTracker methods.
    This allows existing code that uses sm.objection_flow to continue working.
    """

    def __init__(self, state_machine: StateMachine):
        """Initialize with reference to StateMachine."""
        self._sm = state_machine

    @property
    def MAX_CONSECUTIVE_OBJECTIONS(self) -> int:
        """Get from YAML config via StateMachine."""
        return self._sm.max_consecutive_objections

    @property
    def MAX_TOTAL_OBJECTIONS(self) -> int:
        """Get from YAML config via StateMachine."""
        return self._sm.max_total_objections

    @property
    def objection_count(self) -> int:
        """Consecutive objections count."""
        return self._sm.intent_tracker.objection_consecutive()

    @property
    def total_objections(self) -> int:
        """Total objections in conversation."""
        return self._sm.intent_tracker.objection_total()

    @property
    def objection_history(self) -> List[tuple]:
        """History of objections as (type, state) tuples."""
        return [
            (r.intent, r.state)
            for r in self._sm.intent_tracker.get_intents_by_category("objection")
        ]

    @property
    def last_state_before_objection(self) -> Optional[str]:
        """State before first objection in current series."""
        return self._sm._state_before_objection

    def reset(self) -> None:
        """Reset objection tracking (for new conversation)."""
        self._sm.intent_tracker.reset()
        self._sm._state_before_objection = None

    def record_objection(self, objection_type: str, state: str) -> None:
        """
        Record an objection.

        Note: In Phase 4, recording happens automatically in apply_rules()
        via intent_tracker.record(). This method exists for backward compat.
        """
        # Save state before objection if not already saved
        if self._sm._state_before_objection is None:
            self._sm._state_before_objection = state
        # The actual recording is done in apply_rules via intent_tracker.record()

    def reset_consecutive(self) -> None:
        """
        Reset consecutive objections counter.

        Note: In Phase 4, this happens automatically when a positive intent
        is recorded. This method exists for backward compat.
        """
        # Reset the state_before_objection to signal series end
        self._sm._state_before_objection = None

    def should_soft_close(self) -> bool:
        """Check if objection limit reached."""
        return self._sm._check_objection_limit()

    def get_return_state(self) -> Optional[str]:
        """Get state to return to after handling objection."""
        return self._sm._state_before_objection

    def get_stats(self) -> Dict:
        """Get objection statistics."""
        return self._sm._get_objection_stats()


if __name__ == "__main__":
    sm = StateMachine()
    
    # Тест
    print("=== Тест State Machine ===\n")
    
    tests = [
        ("greeting", {}),
        ("price_question", {}),
        ("info_provided", {"company_size": 15}),
        ("info_provided", {"pain_point": "теряем клиентов"}),
        ("agreement", {}),
    ]
    
    for intent, data in tests:
        result = sm.process(intent, data)
        print(f"Intent: {intent}")
        print(f"  {result['prev_state']} → {result['next_state']}")
        print(f"  Action: {result['action']}")
        print(f"  Data: {result['collected_data']}\n")