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

from feature_flags import flags
from logger import logger
from settings import settings

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
# Phase 4: RuleResult for StateMachine
# =============================================================================

@dataclass
class RuleResult:
    """
    Result of rule resolution.

    Supports tuple unpacking for backward compatibility:
        action, state = sm.apply_rules(intent)

    Attributes:
        action: The action to take
        next_state: The next state (or current if None returned)
        trace: Optional evaluation trace for debugging
    """
    action: str
    next_state: str
    trace: Optional[EvaluationTrace] = None

    def __iter__(self) -> Iterator[Any]:
        """Support tuple unpacking: action, state = result"""
        yield self.action
        yield self.next_state

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "action": self.action,
            "next_state": self.next_state,
        }
        if self.trace:
            result["trace"] = self.trace.to_dict()
        return result


class CircularFlowManager:
    """
    Управление возвратами назад с защитой от злоупотреблений.

    Позволяет клиенту вернуться к предыдущей фазе,
    но ограничивает количество возвратов для предотвращения зацикливания.

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

    def can_go_back(self, current_state: str) -> bool:
        """
        Проверить можно ли вернуться назад.

        Args:
            current_state: Текущее состояние

        Returns:
            True если возврат возможен
        """
        if self.goback_count >= self.max_gobacks:
            logger.info(
                "Go back limit reached",
                current=current_state,
                count=self.goback_count
            )
            return False

        return current_state in self.allowed_gobacks

    def go_back(self, current_state: str) -> Optional[str]:
        """
        Выполнить возврат назад.

        Args:
            current_state: Текущее состояние

        Returns:
            Предыдущее состояние или None если возврат невозможен
        """
        if not self.can_go_back(current_state):
            return None

        prev_state = self.allowed_gobacks.get(current_state)
        if prev_state:
            self.goback_count += 1
            self.goback_history.append((current_state, prev_state))
            logger.info(
                "Go back executed",
                from_state=current_state,
                to_state=prev_state,
                remaining=self.max_gobacks - self.goback_count
            )

        return prev_state

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

        # Phase 4/Phase 1: RuleResolver with optional expression parser
        if config:
            expression_parser = None
            if config.custom_conditions:
                from src.conditions.expression_parser import ConditionExpressionParser
                expression_parser = ConditionExpressionParser(
                    sm_registry,
                    config.custom_conditions
                )
            self._resolver = RuleResolver(
                sm_registry,
                default_action=config.default_action,
                expression_parser=expression_parser
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
    # Priority-Driven Rule Application (Этап 4)
    # =========================================================================

    def _apply_priority(
        self,
        priority: Dict[str, Any],
        intent: str,
        config: Dict,
        transitions: Dict,
        rules: Dict,
        ctx: Any,
        trace: Optional['EvaluationTrace'] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Apply a single priority and return result if matched.

        Args:
            priority: Priority configuration from YAML
            intent: Current intent
            config: Current state configuration
            transitions: State transitions
            rules: State rules
            ctx: EvaluatorContext for condition evaluation
            trace: Optional trace for debugging

        Returns:
            Tuple[action, next_state] if priority matched, None otherwise
        """
        priority_name = priority.get("name", "unknown")

        # Check if priority applies to this intent
        if not self._priority_matches_intent(priority, intent, config):
            return None

        # Check condition if specified
        condition = priority.get("condition")
        condition_matched = False
        if condition:
            condition_matched = self._evaluate_priority_condition(condition, ctx, config)
            if not condition_matched:
                # Check 'else' clause
                else_action = priority.get("else")
                if else_action == "use_transitions":
                    next_state = self._resolve_transition(intent, transitions, ctx, trace)
                    if next_state:
                        return f"transition_to_{next_state}", next_state
                return None

        # Mark soft_close as final when triggered by objection limit
        if condition == "objection_limit_reached" and condition_matched:
            action = priority.get("action", "")
            if action == "transition_to_soft_close" or action.endswith("soft_close"):
                self.collected_data["_objection_limit_final"] = True

        # Check feature flag if specified
        feature_flag = priority.get("feature_flag")
        if feature_flag and not getattr(flags, feature_flag, False):
            return None

        # Handle the priority
        handler = priority.get("handler")
        if handler:
            return self._call_priority_handler(handler, intent, config, transitions, ctx, trace)

        # Direct action
        action = priority.get("action")
        if action:
            if action == "final":
                return "final", self.state
            elif action.startswith("transition_to_"):
                next_state = action.replace("transition_to_", "")
                return action, next_state
            return action, self.state

        # Use transitions
        if priority.get("use_transitions"):
            trigger = priority.get("trigger")
            if trigger:
                # Use trigger as key (e.g., "data_complete", "any")
                next_state = self._resolve_transition(trigger, transitions, ctx, trace)
            else:
                next_state = self._resolve_transition(intent, transitions, ctx, trace)
            if next_state:
                return f"transition_to_{next_state}", next_state

        # Use resolver for rules
        if priority.get("use_resolver") and priority.get("source") == "rules":
            if intent in rules:
                rule_value = rules[intent]
                if isinstance(rule_value, (list, dict)):
                    action = self._resolver.resolve_action(
                        intent=intent,
                        state_rules=rules,
                        global_rules={},
                        ctx=ctx,
                        state=self.state,
                        trace=trace
                    )
                    return action, self.state
                else:
                    return rule_value, self.state

        # Default action from priority
        default_action = priority.get("default_action")
        if default_action:
            next_state = self._resolve_transition(intent, transitions, ctx, trace) or self.state
            return default_action, next_state

        return None

    def _priority_matches_intent(
        self,
        priority: Dict[str, Any],
        intent: str,
        config: Dict
    ) -> bool:
        """
        Check if a priority matches the current intent.

        Args:
            priority: Priority configuration
            intent: Current intent
            config: State configuration

        Returns:
            True if priority applies to this intent
        """
        # Check specific intents list
        intents = priority.get("intents", [])
        if intents and intent in intents:
            return True

        # Check intent category
        intent_category = priority.get("intent_category")
        if intent_category:
            category_intents = INTENT_CATEGORIES.get(intent_category, [])
            if intent in category_intents:
                return True

        # Check trigger (special keys like "data_complete", "any")
        trigger = priority.get("trigger")
        if trigger:
            return True  # Triggers always apply, actual logic is in handler

        # Check source (e.g., "rules" - applies if intent is in state rules)
        source = priority.get("source")
        if source == "rules":
            return intent in config.get("rules", {})

        # Check condition-only priorities (like final_state)
        if priority.get("condition") and not intents and not intent_category:
            return True

        # Check handler (like phase_progress_handler)
        if priority.get("handler"):
            return True

        # Check use_transitions without specific intents
        if priority.get("use_transitions") and not intents and not intent_category and not trigger:
            return True

        return False

    def _evaluate_priority_condition(
        self,
        condition: str,
        ctx: Any,
        config: Dict
    ) -> bool:
        """
        Evaluate a priority condition.

        Args:
            condition: Condition name
            ctx: EvaluatorContext
            config: State configuration

        Returns:
            True if condition is met
        """
        if condition == "is_final":
            return config.get("is_final", False)
        elif condition == "objection_limit_reached":
            return self._check_objection_limit()
        elif condition == "has_all_required_data":
            return self._check_phase_data_complete(config)
        else:
            # Try to evaluate via condition registry
            try:
                return sm_registry.evaluate(condition, ctx)
            except Exception:
                return False

    def _call_priority_handler(
        self,
        handler: str,
        intent: str,
        config: Dict,
        transitions: Dict,
        ctx: Any,
        trace: Optional['EvaluationTrace'] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Call a priority handler method.

        Args:
            handler: Handler name
            intent: Current intent
            config: State configuration
            transitions: State transitions
            ctx: EvaluatorContext
            trace: Optional trace

        Returns:
            Tuple[action, next_state] or None
        """
        if handler == "circular_flow_handler":
            prev_state = self.circular_flow.go_back(self.state)
            if prev_state:
                return "go_back", prev_state
            return None

        elif handler == "phase_progress_handler":
            spin_phase = self._get_current_phase()
            if not spin_phase:
                return None

            progress_intents = self.progress_intents
            if intent in progress_intents:
                intent_phase = progress_intents[intent]
                if self._is_phase_progression(intent_phase, spin_phase):
                    next_state = self._resolve_transition(intent, transitions, ctx, trace)
                    if next_state:
                        return f"transition_to_{next_state}", next_state

            # Auto-transition by data_complete within phase
            if intent not in transitions and self._check_phase_data_complete(config):
                next_state = self._resolve_transition("data_complete", transitions, ctx, trace)
                if next_state:
                    # Check if next phase should be skipped
                    next_config = self.states_config.get(next_state, {})
                    next_phase = next_config.get("phase") or next_config.get("spin_phase")
                    if next_phase and self._should_skip_phase(next_phase):
                        skip_transitions = next_config.get("transitions", {})
                        skip_next = self._resolve_transition("data_complete", skip_transitions, ctx, trace)
                        if skip_next:
                            next_state = skip_next
                    return f"transition_to_{next_state}", next_state

            return None

        return None

    def _apply_rules_priority_driven(
        self,
        intent: str,
        config: Dict,
        transitions: Dict,
        rules: Dict,
        ctx: Any,
        trace: Optional['EvaluationTrace'] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Apply rules using priority-driven approach from FlowConfig.

        Iterates through priorities sorted by priority number and applies
        each one until a result is found.

        Args:
            intent: Current intent
            config: State configuration
            transitions: State transitions
            rules: State rules
            ctx: EvaluatorContext
            trace: Optional trace for debugging

        Returns:
            Tuple[action, next_state] if any priority matched, None otherwise
        """
        # Sort priorities by priority number (lower = higher priority)
        sorted_priorities = sorted(
            self.priorities,
            key=lambda p: p.get("priority", 999)
        )

        # Special handling for objection intents - save state before objection
        if intent in OBJECTION_INTENTS:
            if self._state_before_objection is None:
                self._state_before_objection = self.state
            logger.info(
                "Objection recorded",
                type=intent,
                consecutive=self.intent_tracker.objection_consecutive(),
                total=self.intent_tracker.objection_total()
            )

        # Reset state_before_objection on positive intents
        if intent in POSITIVE_INTENTS:
            self._state_before_objection = None

        # =====================================================================
        # PRIORITY OVERRIDE: Price-related questions
        # Price questions have highest priority - ALWAYS return answer_with_pricing
        # This ensures price questions are not deflected regardless of state rules
        # =====================================================================
        if flags.is_enabled("price_question_override"):
            price_related_intents = self._get_intent_category("price_related") or {"price_question", "pricing_details"}
            if intent in price_related_intents:
                logger.debug(
                    "Price-related intent detected (priority-driven), using pricing action",
                    intent=intent,
                    state=self.state
                )
                if trace:
                    trace.set_result("answer_with_pricing", Resolution.CONDITION_MATCHED, "price_related_priority")
                return "answer_with_pricing", self.state

        # Iterate through priorities
        for priority in sorted_priorities:
            result = self._apply_priority(
                priority, intent, config, transitions, rules, ctx, trace
            )
            if result:
                return result

        # No priority matched - return default
        return "continue_current_goal", self.state

    def apply_rules(self, intent: str, context_envelope: Any = None) -> Tuple[str, str]:
        """
        Определяем действие и следующее состояние.

        Phase 4 Pipeline:
        1. Record intent in IntentTracker (BEFORE conditions)
        2. Build EvaluatorContext for condition evaluation
        3. Apply priority-based rule resolution
        4. Return (action, next_state) with optional trace

        Phase 5: Context-aware conditions via context_envelope.

        Порядок приоритетов:
        0. Финальное состояние
        1. Rejection — критический интент
        1.5. Go Back — возврат назад по фазам
        1.7. Возражения с защитой от зацикливания (via IntentTracker)
        2. State-specific rules (с поддержкой conditional rules)
        3. Общий обработчик вопросов (QUESTION_INTENTS)
        4. SPIN-специфичная логика
        5. Переходы по интенту
        6. Автопереход по data_complete
        7. Автопереход по "any"
        8. Default — оставаться в текущем состоянии

        Args:
            intent: The intent to process
            context_envelope: Optional ContextEnvelope with rich context signals

        Returns:
            Tuple[str, str]: (action, next_state)
        """
        # =====================================================================
        # Phase 4 STEP 1: Record intent in IntentTracker FIRST
        # This must happen BEFORE any condition evaluation
        # EXCEPTION: Skip recording objections when limit already reached
        # to prevent counter overflow (3→6) when soft_close continues
        # =====================================================================
        if not self._should_skip_objection_recording(intent):
            self.intent_tracker.record(intent, self.state)

        # =====================================================================
        # DAG STEP: Check if current state is a DAG node
        # If so, process via DAG executor and return early
        # =====================================================================
        if self._dag_enabled and self._flow and self._flow.is_dag_state(self.state):
            dag_result = self._apply_dag_rules(intent, context_envelope)
            if dag_result is not None:
                return dag_result

        # =====================================================================
        # Phase 4 STEP 2: Build EvaluatorContext for conditions
        # Phase 5: Include context_envelope for context-aware conditions
        # =====================================================================
        config = self.states_config.get(self.state, {})
        transitions = config.get("transitions", {})
        rules = config.get("rules", {})
        spin_phase = self._get_current_spin_phase()

        # Build context for condition evaluation (with envelope if provided)
        ctx = EvaluatorContext.from_state_machine(
            self, intent, config, context_envelope=context_envelope
        )

        # Create trace if tracing is enabled
        trace = None
        if self._enable_tracing and self._trace_collector:
            trace = self._trace_collector.create_trace(
                rule_name=intent,
                intent=intent,
                state=self.state,
                domain="state_machine"
            )

        # =====================================================================
        # PRIORITY-DRIVEN APPROACH (Этап 4)
        # When FlowConfig is available with priorities, use configurable logic
        # =====================================================================
        if self._flow and self.priorities:
            result = self._apply_rules_priority_driven(
                intent, config, transitions, rules, ctx, trace
            )
            if result:
                action, next_state = result
                if trace and not trace.final_action:
                    trace.set_result(action, Resolution.SIMPLE)
                self._last_trace = trace
                return action, next_state

        # =====================================================================
        # LEGACY APPROACH: Hardcoded priorities (backward compatibility)
        # Used when no FlowConfig or no priorities defined
        # =====================================================================

        # =====================================================================
        # ПРИОРИТЕТ 0: Финальное состояние
        # =====================================================================
        if config.get("is_final"):
            if trace:
                trace.set_result("final", Resolution.SIMPLE)
            self._last_trace = trace
            return "final", self.state

        # =====================================================================
        # ПРИОРИТЕТ 1: Rejection — всегда обрабатываем немедленно
        # =====================================================================
        if intent == "rejection":
            next_state = self._resolve_transition("rejection", transitions, ctx, trace)
            if next_state:
                if trace and not trace.final_action:
                    trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
                self._last_trace = trace
                return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 1.5: Go Back — возврат назад по фазам
        # Контролируется feature flag circular_flow (по умолчанию выключен)
        # =====================================================================
        if intent in GO_BACK_INTENTS and flags.circular_flow:
            prev_state = self.circular_flow.go_back(self.state)
            if prev_state:
                if trace:
                    trace.set_result("go_back", Resolution.SIMPLE)
                self._last_trace = trace
                return "go_back", prev_state
            # Если возврат невозможен — продолжаем обычную обработку

        # =====================================================================
        # ПРИОРИТЕТ 1.7: Возражения с защитой от зацикливания
        # Phase 4: Now using IntentTracker methods instead of ObjectionFlowManager
        # =====================================================================
        if intent in OBJECTION_INTENTS:
            # Save state before objection for potential return
            if self._state_before_objection is None:
                self._state_before_objection = self.state

            logger.info(
                "Objection recorded",
                type=intent,
                consecutive=self.intent_tracker.objection_consecutive(),
                total=self.intent_tracker.objection_total()
            )

            # Проверяем лимит возражений через IntentTracker
            if self._check_objection_limit():
                if trace:
                    trace.set_result("objection_limit_reached", Resolution.CONDITION_MATCHED, "objection_limit_reached")
                self._last_trace = trace
                # Mark soft_close as final when triggered by objection limit
                self.collected_data["_objection_limit_final"] = True
                return "objection_limit_reached", "soft_close"

            # Иначе обрабатываем через transitions (handle_objection или soft_close)
            next_state = self._resolve_transition(intent, transitions, ctx, trace)
            if next_state:
                if trace and not trace.final_action:
                    trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
                self._last_trace = trace
                return f"transition_to_{next_state}", next_state

        # Phase 4: Reset state_before_objection on positive intents
        if intent in POSITIVE_INTENTS:
            self._state_before_objection = None

        # =====================================================================
        # ПРИОРИТЕТ 1.9: Price-related questions (НОВОЕ)
        # Вопросы о цене имеют ВЫСШИЙ ПРИОРИТЕТ над state rules
        # ВСЕГДА возвращаем answer_with_pricing, независимо от того что
        # написано в rules для этого intent
        # =====================================================================
        if flags.is_enabled("price_question_override"):
            # Получаем категорию price_related из конфига
            price_related_intents = self._get_intent_category("price_related") or {"price_question", "pricing_details"}

            if intent in price_related_intents:
                logger.debug(
                    "Price-related intent detected, using pricing action (priority 1.9)",
                    intent=intent,
                    state=self.state
                )
                if trace:
                    trace.set_result("answer_with_pricing", Resolution.CONDITION_MATCHED, "price_related_priority")
                self._last_trace = trace
                return "answer_with_pricing", self.state

        # =====================================================================
        # ПРИОРИТЕТ 2: State-specific rules (с поддержкой conditional rules)
        # Phase 4: Now supports conditional rules via RuleResolver
        # =====================================================================
        if intent in rules:
            rule_value = rules[intent]

            # Check if this is a conditional rule (list or dict) or simple string
            if isinstance(rule_value, (list, dict)):
                # Phase 4: Use RuleResolver for conditional rules
                action = self._resolver.resolve_action(
                    intent=intent,
                    state_rules=rules,
                    global_rules={},
                    ctx=ctx,
                    state=self.state,
                    trace=trace
                )
                self._last_trace = trace
                return action, self.state
            else:
                # Simple string rule - apply price_question fix
                rule_action = rule_value

                # =============================================================
                # Phase 4: Price question fix via has_pricing_data condition
                # Now using the registered condition instead of hardcoded check
                # =============================================================
                if intent == "price_question" and rule_action == "deflect_and_continue":
                    # Use the registered condition from sm_registry
                    try:
                        has_pricing_data = sm_registry.evaluate("has_pricing_data", ctx, trace)
                        if has_pricing_data:
                            if trace:
                                trace.set_result("answer_with_facts", Resolution.CONDITION_MATCHED, "has_pricing_data")
                            self._last_trace = trace
                            return "answer_with_facts", self.state
                    except Exception as e:
                        # Fallback to direct check if condition fails
                        logger.warning("Condition evaluation failed, using fallback", error=str(e))
                        if self.collected_data.get("company_size") or self.collected_data.get("users_count"):
                            if trace:
                                trace.set_result("answer_with_facts", Resolution.CONDITION_MATCHED, "has_pricing_data_fallback")
                            self._last_trace = trace
                            return "answer_with_facts", self.state

                if trace:
                    trace.set_result(rule_action, Resolution.SIMPLE)
                self._last_trace = trace
                return rule_action, self.state

        # =====================================================================
        # ПРИОРИТЕТ 3: Общий обработчик вопросов
        # Если клиент задаёт вопрос — сначала отвечаем, потом продолжаем
        # =====================================================================
        if intent in QUESTION_INTENTS:
            next_state = self._resolve_transition(intent, transitions, ctx, trace) or self.state
            if trace and not trace.final_action:
                trace.set_result("answer_question", Resolution.SIMPLE)
            self._last_trace = trace
            return "answer_question", next_state

        # =====================================================================
        # ПРИОРИТЕТ 4: SPIN-специфичная логика
        # =====================================================================
        if spin_phase:
            progress_intents = self.spin_progress_intents
            if intent in progress_intents:
                intent_phase = progress_intents[intent]
                if self._is_spin_phase_progression(intent_phase, spin_phase):
                    next_state = self._resolve_transition(intent, transitions, ctx, trace)
                    if next_state:
                        if trace and not trace.final_action:
                            trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
                        self._last_trace = trace
                        return f"transition_to_{next_state}", next_state

            # Автопереход по data_complete только если:
            # 1. Данные собраны
            # 2. Интент НЕ определён явно в transitions (no_need, no_problem и т.д.)
            # Это позволяет явным интентам иметь приоритет над автопереходом
            if intent not in transitions and self._check_spin_data_complete(config):
                next_state = self._resolve_transition("data_complete", transitions, ctx, trace)
                if next_state:
                    next_config = self.states_config.get(next_state, {})
                    next_phase = next_config.get("spin_phase")
                    if next_phase and self._should_skip_spin_phase(next_phase):
                        skip_transitions = next_config.get("transitions", {})
                        skip_next = self._resolve_transition("data_complete", skip_transitions, ctx, trace)
                        if skip_next:
                            next_state = skip_next
                    if trace and not trace.final_action:
                        trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
                    self._last_trace = trace
                    return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 5: Переходы по интенту
        # =====================================================================
        next_state = self._resolve_transition(intent, transitions, ctx, trace)
        if next_state:
            if trace and not trace.final_action:
                trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
            self._last_trace = trace
            return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 6: Проверка data_complete для non-SPIN состояний
        # =====================================================================
        required = config.get("required_data", [])
        if required:
            missing = [f for f in required if not self.collected_data.get(f)]
            if not missing:
                next_state = self._resolve_transition("data_complete", transitions, ctx, trace)
                if next_state:
                    if trace and not trace.final_action:
                        trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
                    self._last_trace = trace
                    return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 7: Автопереход (для greeting)
        # =====================================================================
        next_state = self._resolve_transition("any", transitions, ctx, trace)
        if next_state:
            if trace and not trace.final_action:
                trace.set_result(f"transition_to_{next_state}", Resolution.SIMPLE)
            self._last_trace = trace
            return f"transition_to_{next_state}", next_state

        # =====================================================================
        # ПРИОРИТЕТ 8: Default — остаёмся в текущем состоянии
        # =====================================================================
        # Всегда возвращаем валидный action, а не имя состояния
        # generator.py использует spin_phase из контекста для выбора нужного шаблона
        if trace:
            trace.set_result("continue_current_goal", Resolution.DEFAULT)
        self._last_trace = trace
        return "continue_current_goal", self.state

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
        Обработать интент, вернуть результат.

        Phase 4: Uses IntentTracker for history and stats.
        Phase 5: Uses context_envelope for context-aware conditions.

        Args:
            intent: The intent to process
            extracted_data: Optional extracted data to update
            context_envelope: Optional ContextEnvelope with rich context signals
        """
        prev_state = self.state

        if extracted_data:
            self.update_data(extracted_data)

        action, next_state = self.apply_rules(intent, context_envelope=context_envelope)
        self.state = next_state

        # Store last_action for context
        self.last_action = action

        # Update current phase from state config
        self.current_phase = self._get_current_phase()

        # Check if state changed
        state_changed = prev_state != next_state

        # =====================================================================
        # ON_ENTER: Set flags when entering a new state (generic mechanism)
        # =====================================================================
        # Replaces hardcoded checks like:
        #   if next_state == "spin_implication": self.collected_data["implication_probed"] = True
        # Now configured via YAML:
        #   spin_implication:
        #     on_enter:
        #       set_flags:
        #         implication_probed: true
        if state_changed and self._flow:
            on_enter_flags = self._flow.get_state_on_enter_flags(next_state)
            for flag_name, flag_value in on_enter_flags.items():
                self.collected_data[flag_name] = flag_value

        config = self.states_config.get(self.state, {})

        # =====================================================================
        # ON_ENTER: Execute action when entering a new state
        # =====================================================================
        # If state changed AND new state has on_enter config, use on_enter action.
        # This allows states to show prompts/options immediately upon entry,
        # regardless of what intent triggered the transition.
        on_enter = config.get("on_enter")
        if state_changed and on_enter:
            on_enter_action = on_enter.get("action") if isinstance(on_enter, dict) else on_enter
            if on_enter_action:
                action = on_enter_action

        required = config.get("required_data", [])
        missing = [f for f in required if not self.collected_data.get(f)]

        # Собираем optional данные для SPIN
        optional = config.get("optional_data", [])
        optional_missing = [f for f in optional if not self.collected_data.get(f)]

        # Determine is_final
        is_final = config.get("is_final", False)
        # Override for objection limit triggered soft_close
        # When soft_close is reached via objection_limit, force it to be final
        # This prevents dialog from continuing and objection counter overflow
        if self.state == "soft_close" and self.collected_data.get("_objection_limit_final"):
            is_final = True

        result = {
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
            # Phase 4: Use IntentTracker-based stats (backward compat)
            "objection_flow": self._get_objection_stats(),
        }

        # Phase 4: Add trace if enabled
        if self._enable_tracing and self._last_trace:
            result["trace"] = self._last_trace.to_dict()

        return result

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