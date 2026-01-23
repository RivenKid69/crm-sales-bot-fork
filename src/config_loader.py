"""
Configuration Loader for State Machine and Dialogue Systems.

This module loads and validates YAML configuration files for the
state machine, SPIN phases, conditions, and related subsystems.

Part of Phase 1: State Machine Parameterization
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Union, TYPE_CHECKING
from dataclasses import dataclass, field
import yaml
import logging
import re

if TYPE_CHECKING:
    from src.conditions.registry import ConditionRegistry
    from src.dag.models import DAGNodeConfig

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        message = f"Configuration validation failed with {len(errors)} error(s):\n"
        message += "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


class ConfigLoadError(Exception):
    """Raised when configuration file loading fails."""

    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        message = f"Failed to load '{file_path}': {reason}"
        super().__init__(message)


@dataclass
class LoadedConfig:
    """
    Result of loading configuration.

    Contains all loaded and validated configuration data from YAML files.
    """
    # States configuration
    states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    states_meta: Dict[str, Any] = field(default_factory=dict)
    default_action: str = "continue_current_goal"

    # SPIN configuration
    spin_phases: List[str] = field(default_factory=list)
    spin_config: Dict[str, Any] = field(default_factory=dict)

    # Constants (single source of truth)
    constants: Dict[str, Any] = field(default_factory=dict)

    # Custom conditions
    custom_conditions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    condition_aliases: Dict[str, str] = field(default_factory=dict)

    # Convenience accessors for frequently used constants
    @property
    def limits(self) -> Dict[str, int]:
        """Get limits configuration."""
        return self.constants.get("limits", {})

    @property
    def intents(self) -> Dict[str, Any]:
        """Get intents configuration."""
        return self.constants.get("intents", {})

    @property
    def policy(self) -> Dict[str, Any]:
        """Get dialogue policy configuration."""
        return self.constants.get("policy", {})

    @property
    def lead_scoring(self) -> Dict[str, Any]:
        """Get lead scoring configuration."""
        return self.constants.get("lead_scoring", {})

    @property
    def guard(self) -> Dict[str, Any]:
        """Get conversation guard configuration."""
        return self.constants.get("guard", {})

    @property
    def frustration(self) -> Dict[str, Any]:
        """Get frustration tracker configuration."""
        return self.constants.get("frustration", {})

    @property
    def circular_flow(self) -> Dict[str, Any]:
        """Get circular flow (go back) configuration."""
        return self.constants.get("circular_flow", {})

    @property
    def context(self) -> Dict[str, Any]:
        """Get context window configuration (state_order, phase_order)."""
        return self.constants.get("context", {})

    @property
    def fallback(self) -> Dict[str, Any]:
        """Get fallback templates configuration."""
        return self.constants.get("fallback", {})

    @property
    def cta(self) -> Dict[str, Any]:
        """Get CTA (call-to-action) configuration."""
        return self.constants.get("cta", {})

    @property
    def response_directives(self) -> Dict[str, Any]:
        """Get response directives configuration."""
        return self.constants.get("response_directives", {})

    # SPIN convenience methods
    def get_spin_state(self, phase: str) -> Optional[str]:
        """Get state name for a SPIN phase."""
        phases = self.spin_config.get("phases", {})
        phase_config = phases.get(phase, {})
        return phase_config.get("state")

    def get_spin_skip_conditions(self, phase: str) -> List[str]:
        """Get skip conditions for a SPIN phase."""
        phases = self.spin_config.get("phases", {})
        phase_config = phases.get(phase, {})
        return phase_config.get("skip_conditions", [])

    def is_phase_skippable(self, phase: str) -> bool:
        """Check if a SPIN phase can be skipped."""
        phases = self.spin_config.get("phases", {})
        phase_config = phases.get(phase, {})
        return phase_config.get("skippable", False)

    # Lead scoring convenience methods
    def get_skip_phases_for_temperature(self, temperature: str) -> List[str]:
        """Get SPIN phases to skip for a lead temperature."""
        skip_phases = self.lead_scoring.get("skip_phases", {})
        return skip_phases.get(temperature.lower(), [])

    # State convenience methods
    def get_state_config(self, state_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a state."""
        return self.states.get(state_name)

    def get_state_transitions(self, state_name: str) -> Dict[str, Any]:
        """Get transitions for a state."""
        state = self.states.get(state_name, {})
        return state.get("transitions", {})

    def get_state_rules(self, state_name: str) -> Dict[str, Any]:
        """Get rules for a state."""
        state = self.states.get(state_name, {})
        return state.get("rules", {})

    def is_final_state(self, state_name: str) -> bool:
        """Check if a state is final."""
        state = self.states.get(state_name, {})
        return state.get("is_final", False)

    def get_state_on_enter(self, state_name: str) -> Optional[Dict[str, Any]]:
        """
        Get on_enter configuration for a state.

        on_enter defines an action to execute when entering the state,
        regardless of which intent triggered the transition.

        Example YAML:
            ask_activity:
              on_enter:
                action: show_activity_options

        Returns:
            Dict with 'action' key, or None if not defined
        """
        state = self.states.get(state_name, {})
        on_enter = state.get("on_enter")
        if on_enter is None:
            return None
        # Support both dict format and shorthand string format
        if isinstance(on_enter, str):
            return {"action": on_enter}
        return on_enter

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        """
        Get flags to set when entering a state.

        Allows generic flag setting without hardcoding state names.

        Example YAML:
            spin_implication:
              on_enter:
                action: probe_implication
                set_flags:
                  implication_probed: true

        Returns:
            Dict of flag_name -> value to set in collected_data
        """
        on_enter = self.get_state_on_enter(state_name)
        if on_enter and isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}


@dataclass
class FlowConfig:
    """
    Configuration for a modular flow (SPIN, BANT, Support, etc.).

    FlowConfig represents a complete flow definition loaded from
    flows/{flow_name}/ directory, with all inheritance resolved.
    """
    name: str
    version: str = "1.0"
    description: str = ""

    # Resolved states (after extends/mixins)
    states: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Phase configuration (optional - some flows don't have phases)
    phases: Optional[Dict[str, Any]] = None

    # Processing priorities
    priorities: List[Dict[str, Any]] = field(default_factory=list)

    # Flow variables (substituted in templates)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Entry points for different scenarios
    entry_points: Dict[str, str] = field(default_factory=dict)

    # Prompt templates
    templates: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # DAG nodes (parsed from states with type != simple)
    _dag_nodes: Dict[str, "DAGNodeConfig"] = field(default_factory=dict)

    def __post_init__(self):
        """Parse DAG nodes from states after initialization."""
        self._parse_dag_nodes()

    def _parse_dag_nodes(self):
        """Extract DAG nodes from states configuration."""
        from src.dag.models import DAGNodeConfig, NodeType

        for state_id, state_config in self.states.items():
            type_str = state_config.get("type", "simple")
            if type_str != "simple":
                try:
                    self._dag_nodes[state_id] = DAGNodeConfig.from_state_config(
                        state_id, state_config
                    )
                except Exception:
                    # If parsing fails, skip this node
                    pass

    # Computed properties
    @property
    def post_phases_state(self) -> Optional[str]:
        """State to transition to after all phases complete."""
        if self.phases:
            return self.phases.get("post_phases_state", "presentation")
        return None

    @property
    def phase_order(self) -> List[str]:
        """Ordered list of phase names."""
        if self.phases:
            return self.phases.get("order", [])
        return []

    @property
    def phase_mapping(self) -> Dict[str, str]:
        """Mapping from phase name to state name."""
        if self.phases:
            return self.phases.get("mapping", {})
        return {}

    @property
    def progress_intents(self) -> Dict[str, str]:
        """Intents that indicate progress through phases."""
        if self.phases:
            return self.phases.get("progress_intents", {})
        return {}

    @property
    def skip_conditions(self) -> Dict[str, List[str]]:
        """Conditions for skipping phases."""
        if self.phases:
            return self.phases.get("skip_conditions", {})
        return {}

    @property
    def state_to_phase(self) -> Dict[str, str]:
        """
        Reverse mapping from state name to phase name.

        Built automatically from phase_mapping. This is the FUNDAMENTAL
        solution for phase resolution in custom flows.

        Example:
            # flow.yaml has:
            # phases:
            #   mapping:
            #     budget: bant_budget
            #     authority: bant_authority

            flow.state_to_phase
            # Returns: {"bant_budget": "budget", "bant_authority": "authority"}
        """
        return {v: k for k, v in self.phase_mapping.items()}

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """
        Get phase name for a state.

        This is the CANONICAL method for resolving state -> phase mapping.
        All components should use this method instead of hardcoded mappings.

        Resolution order:
        1. state_config.phase (explicit in state definition, e.g., SPIN states)
        2. state_to_phase reverse mapping (from flow.phases.mapping)
        3. None (not a phase state)

        Args:
            state_name: Name of the state to look up

        Returns:
            Phase name or None if state is not a phase state

        Example:
            # SPIN flow (explicit phase in state config)
            flow.get_phase_for_state("spin_situation")  # "situation"

            # BANT flow (uses reverse mapping)
            flow.get_phase_for_state("bant_budget")  # "budget"

            # Non-phase state
            flow.get_phase_for_state("greeting")  # None
        """
        # 1. Check explicit phase in state config (highest priority)
        state_config = self.states.get(state_name, {})
        explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
        if explicit_phase:
            return explicit_phase

        # 2. Use reverse mapping from phase_mapping
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        """
        Check if a state is a phase state.

        Args:
            state_name: Name of the state to check

        Returns:
            True if state has an associated phase, False otherwise
        """
        return self.get_phase_for_state(state_name) is not None

    def get_state_for_phase(self, phase: str) -> Optional[str]:
        """Get state name for a phase."""
        return self.phase_mapping.get(phase)

    def get_entry_point(self, scenario: str = "default") -> str:
        """Get entry state for a scenario."""
        return self.entry_points.get(scenario, self.entry_points.get("default", "greeting"))

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a flow variable."""
        return self.variables.get(name, default)

    def get_template(self, action: str) -> Optional[str]:
        """
        Get prompt template string for an action.

        Args:
            action: Action name (e.g., 'spin_situation', 'deflect_and_continue')

        Returns:
            Template string or None if not found
        """
        template_config = self.templates.get(action)
        if template_config:
            return template_config.get("template")
        return None

    def get_template_config(self, action: str) -> Optional[Dict[str, Any]]:
        """
        Get full template configuration for an action.

        Args:
            action: Action name

        Returns:
            Dict with template, description, parameters, etc.
        """
        return self.templates.get(action)

    # =========================================================================
    # State Configuration Methods
    # =========================================================================

    def get_state_on_enter(self, state_name: str) -> Optional[Dict[str, Any]]:
        """
        Get on_enter configuration for a state.

        Returns:
            Dict with 'action', 'set_flags', etc. or None
        """
        state = self.states.get(state_name, {})
        on_enter = state.get("on_enter")
        if on_enter is None:
            return None
        if isinstance(on_enter, str):
            return {"action": on_enter}
        return on_enter

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        """
        Get flags to set when entering a state.

        Allows generic flag setting without hardcoding state names.

        Example YAML:
            spin_implication:
              on_enter:
                set_flags:
                  implication_probed: true

        Returns:
            Dict of flag_name -> value to set in collected_data
        """
        on_enter = self.get_state_on_enter(state_name)
        if on_enter and isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}

    @property
    def skip_map(self) -> Dict[str, str]:
        """
        Build skip map from state transitions.

        Returns a mapping of state -> next_state for fallback skip logic.
        Built automatically from 'data_complete' transitions in states.

        Returns:
            Dict mapping state_name -> skip_target_state
        """
        result = {}
        for state_name, state_config in self.states.items():
            if state_name.startswith("_"):  # Skip abstract states
                continue
            transitions = state_config.get("transitions", {})
            # Use 'data_complete' transition as skip target
            if "data_complete" in transitions:
                result[state_name] = transitions["data_complete"]
        return result

    @property
    def goback_map(self) -> Dict[str, str]:
        """
        Build goback map from state transitions.

        Returns a mapping of state -> previous_state for go_back logic.
        Built automatically from 'go_back' transitions or inverse of skip_map.

        Returns:
            Dict mapping state_name -> goback_target_state
        """
        result = {}
        for state_name, state_config in self.states.items():
            if state_name.startswith("_"):
                continue
            transitions = state_config.get("transitions", {})
            # Explicit go_back transition takes priority
            if "go_back" in transitions:
                result[state_name] = transitions["go_back"]
        # If no explicit go_back, build from skip_map inverse
        if not result:
            skip = self.skip_map
            for from_state, to_state in skip.items():
                result[to_state] = from_state
        return result

    # =========================================================================
    # DAG Support Methods
    # =========================================================================

    @property
    def dag_nodes(self) -> Dict[str, "DAGNodeConfig"]:
        """Get all DAG nodes in this flow."""
        return self._dag_nodes

    def is_dag_state(self, state_id: str) -> bool:
        """
        Check if a state is a DAG node (choice, fork, join, parallel).

        Args:
            state_id: State identifier

        Returns:
            True if state is a DAG node, False otherwise
        """
        return state_id in self._dag_nodes

    def get_dag_node(self, state_id: str) -> Optional["DAGNodeConfig"]:
        """
        Get DAG node configuration for a state.

        Args:
            state_id: State identifier

        Returns:
            DAGNodeConfig or None if not a DAG node
        """
        return self._dag_nodes.get(state_id)

    def get_dag_node_type(self, state_id: str) -> Optional[str]:
        """
        Get the type of DAG node (choice, fork, join, parallel).

        Args:
            state_id: State identifier

        Returns:
            Node type string or None if not a DAG node
        """
        node = self._dag_nodes.get(state_id)
        if node:
            return node.node_type.value
        return None

    def get_fork_branches(self, state_id: str) -> List[Dict[str, Any]]:
        """
        Get branches for a FORK node.

        Args:
            state_id: FORK state identifier

        Returns:
            List of branch configurations
        """
        node = self._dag_nodes.get(state_id)
        if node:
            return node.branches
        return []

    def get_choice_options(self, state_id: str) -> List[Dict[str, Any]]:
        """
        Get choices for a CHOICE node.

        Args:
            state_id: CHOICE state identifier

        Returns:
            List of choice configurations
        """
        node = self._dag_nodes.get(state_id)
        if node:
            return node.choices
        return []

    def get_join_config(self, state_id: str) -> Optional[Dict[str, Any]]:
        """
        Get JOIN node configuration.

        Args:
            state_id: JOIN state identifier

        Returns:
            Dict with expects_branches, join_condition, on_join
        """
        node = self._dag_nodes.get(state_id)
        if node:
            return {
                "expects_branches": node.expects_branches,
                "join_condition": node.join_condition.value,
                "on_join_action": node.on_join_action,
            }
        return None

    # =========================================================================
    # Intent Category Support (for price questions, etc.)
    # =========================================================================

    def get_intent_category(self, category_name: str) -> Optional[List[str]]:
        """
        Get intent category from global constants.

        Reads from constants.yaml: intents.{category_name}

        Args:
            category_name: Name of the intent category (e.g., 'price_related')

        Returns:
            List of intent names in the category, or None if not found

        Example:
            price_intents = flow.get_intent_category("price_related")
            # Returns: ["price_question", "pricing_details"]
        """
        try:
            config = get_config()
            return config.intents.get(category_name)
        except Exception:
            # If config not available, return None
            return None

    def get_intent_action_override(self, intent: str) -> Optional[str]:
        """
        Get action override for a specific intent.

        Reads from constants.yaml: intents.intent_action_overrides.{intent}

        Args:
            intent: Intent name to look up

        Returns:
            Action name to use for this intent, or None if no override

        Example:
            action = flow.get_intent_action_override("price_question")
            # Returns: "answer_with_pricing"
        """
        try:
            config = get_config()
            overrides = config.intents.get("intent_action_overrides", {})
            return overrides.get(intent)
        except Exception:
            return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert FlowConfig to dictionary.

        Returns:
            Dict representation of the flow configuration.
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "states": self.states,
            "phases": self.phases,
            "priorities": self.priorities,
            "variables": self.variables,
            "entry_points": self.entry_points,
            "templates": self.templates,
        }


class ConfigLoader:
    """
    Loads and validates YAML configuration files.

    Provides:
    - Loading of all config files from src/config/
    - Loading of modular flows from flows/{flow_name}/
    - Validation of references between files
    - Threshold synchronization checks
    - Fallback to default values
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config loader.

        Args:
            config_dir: Path to config directory (defaults to src/config/)
        """
        if config_dir is None:
            # Default to src/yaml_config/ relative to this file
            config_dir = Path(__file__).parent / "yaml_config"
        self.config_dir = Path(config_dir)

    def load(self, validate: bool = True) -> LoadedConfig:
        """
        Load all configuration files.

        Args:
            validate: Whether to validate configuration (default True)

        Returns:
            LoadedConfig with all data

        Raises:
            ConfigLoadError: If file loading fails
            ConfigValidationError: If validation fails
        """
        # Load individual files
        constants = self._load_yaml("constants.yaml", required=True)
        states_data = self._load_yaml("states/sales_flow.yaml", required=True)
        spin_data = self._load_yaml("spin/phases.yaml", required=True)
        custom_data = self._load_yaml("conditions/custom.yaml", required=False)

        # Extract states
        states = states_data.get("states", {})
        states_meta = states_data.get("meta", {})
        defaults = states_data.get("defaults", {})
        default_action = defaults.get("default_action", "continue_current_goal")

        # Extract SPIN
        spin_phases = spin_data.get("phase_order", [])

        # Extract custom conditions
        custom_conditions = {}
        condition_aliases = {}
        if custom_data:
            custom_conditions = custom_data.get("conditions", {})
            condition_aliases = custom_data.get("aliases", {})

        # Create result
        config = LoadedConfig(
            states=states,
            states_meta=states_meta,
            default_action=default_action,
            spin_phases=spin_phases,
            spin_config=spin_data,
            constants=constants,
            custom_conditions=custom_conditions,
            condition_aliases=condition_aliases,
        )

        # Validate if requested
        if validate:
            self._validate(config)

        return config

    def _load_yaml(
        self,
        relative_path: str,
        required: bool = True
    ) -> Dict[str, Any]:
        """
        Load a YAML file.

        Args:
            relative_path: Path relative to config_dir
            required: Whether file is required to exist

        Returns:
            Parsed YAML as dict (empty dict if not required and missing)

        Raises:
            ConfigLoadError: If required file is missing or parsing fails
        """
        file_path = self.config_dir / relative_path

        if not file_path.exists():
            if required:
                raise ConfigLoadError(
                    str(file_path),
                    "File not found"
                )
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if data else {}
        except yaml.YAMLError as e:
            raise ConfigLoadError(str(file_path), f"YAML parse error: {e}")
        except Exception as e:
            raise ConfigLoadError(str(file_path), str(e))

    def _validate(self, config: LoadedConfig) -> None:
        """
        Validate loaded configuration.

        Checks:
        - All states in transitions exist
        - All SPIN phase states exist
        - Threshold synchronization (guard vs frustration)
        - Intent categories have valid intents

        Args:
            config: LoadedConfig to validate

        Raises:
            ConfigValidationError: If validation fails
        """
        errors = []

        # Get known states
        known_states = set(config.states.keys())

        # 1. Validate state transitions
        errors.extend(self._validate_transitions(config.states, known_states))

        # 2. Validate SPIN phase states
        errors.extend(self._validate_spin_phases(config, known_states))

        # 3. Validate threshold synchronization
        errors.extend(self._validate_thresholds(config))

        # 4. Validate lead_scoring.skip_phases references valid states
        errors.extend(self._validate_skip_phases(config, known_states))

        # 5. Validate circular_flow.allowed_gobacks
        errors.extend(self._validate_gobacks(config, known_states))

        if errors:
            raise ConfigValidationError(errors)

    def _validate_transitions(
        self,
        states: Dict[str, Any],
        known_states: Set[str]
    ) -> List[str]:
        """Validate that all transition targets exist."""
        errors = []

        for state_name, state_config in states.items():
            transitions = state_config.get("transitions", {})
            for intent, target in transitions.items():
                # Target can be:
                # - String (state name)
                # - List of conditional rules
                if isinstance(target, str):
                    if target not in known_states:
                        errors.append(
                            f"Unknown state '{target}' in "
                            f"{state_name}.transitions.{intent}"
                        )
                elif isinstance(target, list):
                    # List of conditional rules
                    for rule in target:
                        if isinstance(rule, dict):
                            then_target = rule.get("then")
                            if then_target and then_target not in known_states:
                                errors.append(
                                    f"Unknown state '{then_target}' in "
                                    f"{state_name}.transitions.{intent} rule"
                                )
                        elif isinstance(rule, str):
                            # Default fallback state
                            if rule not in known_states:
                                errors.append(
                                    f"Unknown state '{rule}' in "
                                    f"{state_name}.transitions.{intent} fallback"
                                )

        return errors

    def _validate_spin_phases(
        self,
        config: LoadedConfig,
        known_states: Set[str]
    ) -> List[str]:
        """Validate SPIN phase configuration."""
        errors = []

        # Check that all phases in phase_order have configuration
        for phase in config.spin_phases:
            phases = config.spin_config.get("phases", {})
            if phase not in phases:
                errors.append(
                    f"SPIN phase '{phase}' in phase_order has no configuration"
                )
            else:
                phase_config = phases[phase]
                state = phase_config.get("state")
                if state and state not in known_states:
                    errors.append(
                        f"Unknown state '{state}' in spin.phases.{phase}"
                    )

        # Check constants.spin.states match
        spin_states = config.constants.get("spin", {}).get("states", {})
        for phase, state in spin_states.items():
            if state not in known_states:
                errors.append(
                    f"Unknown state '{state}' in constants.spin.states.{phase}"
                )

        return errors

    def _validate_thresholds(self, config: LoadedConfig) -> List[str]:
        """Validate threshold synchronization."""
        errors = []

        # CRITICAL: guard.high_frustration_threshold must equal frustration.thresholds.high
        guard_threshold = config.guard.get("high_frustration_threshold")
        frustration_high = config.frustration.get("thresholds", {}).get("high")

        if guard_threshold is not None and frustration_high is not None:
            if guard_threshold != frustration_high:
                errors.append(
                    f"Threshold mismatch: guard.high_frustration_threshold "
                    f"({guard_threshold}) != frustration.thresholds.high "
                    f"({frustration_high}). These MUST be equal!"
                )

        return errors

    def _validate_skip_phases(
        self,
        config: LoadedConfig,
        known_states: Set[str]
    ) -> List[str]:
        """Validate lead_scoring.skip_phases references."""
        errors = []

        skip_phases = config.lead_scoring.get("skip_phases", {})
        for temperature, phases in skip_phases.items():
            if not isinstance(phases, list):
                continue
            for phase in phases:
                # skip_phases contains state names, not phase names
                if phase not in known_states:
                    # Could also be a phase name - check spin states
                    spin_states = config.constants.get("spin", {}).get("states", {})
                    if phase not in spin_states.values():
                        errors.append(
                            f"Unknown state/phase '{phase}' in "
                            f"lead_scoring.skip_phases.{temperature}"
                        )

        return errors

    def _validate_gobacks(
        self,
        config: LoadedConfig,
        known_states: Set[str]
    ) -> List[str]:
        """Validate circular_flow.allowed_gobacks."""
        errors = []

        allowed_gobacks = config.circular_flow.get("allowed_gobacks", {})
        for from_state, to_state in allowed_gobacks.items():
            if from_state not in known_states:
                errors.append(
                    f"Unknown state '{from_state}' in "
                    f"circular_flow.allowed_gobacks (source)"
                )
            if to_state not in known_states:
                errors.append(
                    f"Unknown state '{to_state}' in "
                    f"circular_flow.allowed_gobacks (target)"
                )

        return errors

    def reload(self) -> LoadedConfig:
        """Reload configuration from files."""
        return self.load(validate=True)

    # =========================================================================
    # FLOW LOADING (Modular flows with extends/mixins)
    # =========================================================================

    def load_flow(self, flow_name: str, validate: bool = True) -> FlowConfig:
        """
        Load a modular flow by name.

        Loads flow configuration from flows/{flow_name}/ directory,
        resolving all extends, mixins, and parameter substitutions.

        Args:
            flow_name: Name of the flow (e.g., "spin_selling", "bant")
            validate: Whether to validate the flow configuration

        Returns:
            FlowConfig with all inheritance resolved

        Raises:
            ConfigLoadError: If flow files cannot be loaded
            ConfigValidationError: If validation fails

        Example:
            from settings import settings

            loader = ConfigLoader()
            # Load flow from settings (configurable in settings.yaml)
            flow = loader.load_flow(settings.flow.active)
            print(flow.phase_order)  # e.g., ['situation', 'problem', ...]
        """
        flow_dir = self.config_dir / "flows" / flow_name
        flow_file = flow_dir / "flow.yaml"

        if not flow_file.exists():
            raise ConfigLoadError(
                str(flow_file),
                f"Flow '{flow_name}' not found"
            )

        # Load flow.yaml
        flow_data = self._load_yaml(f"flows/{flow_name}/flow.yaml", required=True)
        flow_config = flow_data.get("flow", {})

        # Load base components
        base_states = self._load_yaml("flows/_base/states.yaml", required=False)
        base_mixins = self._load_yaml("flows/_base/mixins.yaml", required=False)
        base_priorities = self._load_yaml("flows/_base/priorities.yaml", required=False)

        # Load flow-specific states if exists
        flow_states_file = f"flows/{flow_name}/states.yaml"
        flow_states = self._load_yaml(flow_states_file, required=False)

        # Build mixins registry
        mixins_registry = base_mixins.get("mixins", {})

        # Build states with inheritance
        all_states = {}

        # First, add base states (non-abstract)
        for name, state_config in base_states.get("states", {}).items():
            if not state_config.get("abstract", False):
                all_states[name] = state_config.copy()

        # Then, process flow-specific states
        for name, state_config in flow_states.get("states", {}).items():
            if state_config.get("abstract", False):
                continue  # Skip abstract states
            resolved = self._resolve_state(
                state_name=name,
                state_config=state_config,
                all_states={**base_states.get("states", {}), **flow_states.get("states", {})},
                mixins_registry=mixins_registry,
                variables=flow_config.get("variables", {})
            )
            all_states[name] = resolved

        # Resolve variables in all states
        # Merge flow variables with state-level parameters
        variables = flow_config.get("variables", {})
        for name, state_config in all_states.items():
            # State parameters override flow variables
            state_params = state_config.pop("parameters", {})
            merged_params = {**variables, **state_params}
            all_states[name] = self._resolve_parameters(state_config, merged_params)

        # Build priorities
        priorities = base_priorities.get("default_priorities", [])
        if "priorities" in flow_config:
            flow_priorities = flow_config["priorities"]
            if isinstance(flow_priorities, dict) and "overrides" in flow_priorities:
                priorities = self._apply_priority_overrides(
                    priorities,
                    flow_priorities["overrides"]
                )
            elif isinstance(flow_priorities, list):
                priorities = flow_priorities

        # Build FlowConfig
        result = FlowConfig(
            name=flow_config.get("name", flow_name),
            version=flow_config.get("version", "1.0"),
            description=flow_config.get("description", ""),
            states=all_states,
            phases=flow_config.get("phases"),
            priorities=priorities,
            variables=variables,
            entry_points=flow_config.get("entry_points", {"default": "greeting"}),
            templates=self._load_flow_templates(flow_name)
        )

        if validate:
            self._validate_flow(result)

        return result

    def _resolve_state(
        self,
        state_name: str,
        state_config: Dict[str, Any],
        all_states: Dict[str, Dict[str, Any]],
        mixins_registry: Dict[str, Dict[str, Any]],
        variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve a state configuration with extends and mixins.

        Args:
            state_name: Name of the state being resolved
            state_config: Raw state configuration
            all_states: All available states (for extends lookup)
            mixins_registry: Available mixins
            variables: Flow variables for parameter substitution

        Returns:
            Resolved state configuration
        """
        result = {}

        # 1. Apply extends (inheritance)
        if "extends" in state_config:
            base_name = state_config["extends"]
            if base_name in all_states:
                base_config = all_states[base_name]
                # Recursively resolve base
                if "extends" in base_config or "mixins" in base_config:
                    base_config = self._resolve_state(
                        base_name, base_config, all_states, mixins_registry, variables
                    )
                result = self._deep_merge({}, base_config)
            else:
                logger.warning(
                    f"State '{state_name}' extends unknown state '{base_name}'"
                )

        # 2. Apply mixins
        if "mixins" in state_config:
            for mixin_name in state_config["mixins"]:
                if mixin_name in mixins_registry:
                    mixin = mixins_registry[mixin_name]

                    # Handle nested includes
                    if "includes" in mixin:
                        for included_name in mixin["includes"]:
                            if included_name in mixins_registry:
                                included_mixin = mixins_registry[included_name]
                                result = self._apply_mixin(result, included_mixin)

                    result = self._apply_mixin(result, mixin)
                else:
                    logger.warning(
                        f"State '{state_name}' uses unknown mixin '{mixin_name}'"
                    )

        # 3. Apply state's own configuration (overrides base/mixins)
        for key, value in state_config.items():
            if key in ("extends", "mixins", "abstract"):
                continue  # Skip meta keys
            if key in ("rules", "transitions", "parameters"):
                # Deep merge rules/transitions/parameters
                # This ensures parameters from base states (like _base_phase) are inherited
                # and child states can override specific values while keeping others
                if key not in result:
                    result[key] = {}
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_mixin(
        self,
        state_config: Dict[str, Any],
        mixin: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply a mixin to a state configuration."""
        result = state_config.copy()

        # Apply rules from mixin (later mixins override earlier ones)
        if "rules" in mixin:
            if "rules" not in result:
                result["rules"] = {}
            for intent, action in mixin["rules"].items():
                result["rules"][intent] = action

        # Apply transitions from mixin (later mixins override earlier ones)
        if "transitions" in mixin:
            if "transitions" not in result:
                result["transitions"] = {}
            for intent, target in mixin["transitions"].items():
                result["transitions"][intent] = target

        return result

    # Regex pattern for template placeholders
    _TEMPLATE_PATTERN = re.compile(r'\{\{(\w+)\}\}')

    def _resolve_parameters(
        self,
        config: Any,
        params: Dict[str, Any]
    ) -> Any:
        """
        Substitute {{param}} placeholders in configuration.

        Args:
            config: Configuration dict/list/str to process
            params: Parameters to substitute

        Returns:
            Configuration with parameters substituted
        """
        if isinstance(config, dict):
            return {
                key: self._resolve_parameters(value, params)
                for key, value in config.items()
            }
        elif isinstance(config, list):
            return [self._resolve_parameters(item, params) for item in config]
        elif isinstance(config, str):
            # Simple template substitution
            result = config
            for key, value in params.items():
                placeholder = "{{" + key + "}}"
                if placeholder in result:
                    if result == placeholder:
                        # If entire string is placeholder, return value directly
                        return value
                    result = result.replace(placeholder, str(value))
            return result
        return config

    def _find_unresolved_templates(
        self,
        config: Any,
        path: str = ""
    ) -> List[Dict[str, str]]:
        """
        Find all unresolved {{template}} placeholders in configuration.

        This method recursively searches through the configuration to find
        any {{variable}} placeholders that were not resolved during
        parameter substitution.

        Args:
            config: Configuration to search (dict, list, str, or other)
            path: Current path for error messages (e.g., "greeting.transitions.price_question")

        Returns:
            List of dicts with 'path' and 'template' keys for each unresolved template

        Example:
            >>> loader._find_unresolved_templates({"state": "{{entry_state}}"}, "greeting")
            [{"path": "greeting.state", "template": "{{entry_state}}"}]
        """
        unresolved = []

        if isinstance(config, dict):
            for key, value in config.items():
                new_path = f"{path}.{key}" if path else key
                unresolved.extend(self._find_unresolved_templates(value, new_path))
        elif isinstance(config, list):
            for i, item in enumerate(config):
                new_path = f"{path}[{i}]"
                unresolved.extend(self._find_unresolved_templates(item, new_path))
        elif isinstance(config, str):
            matches = self._TEMPLATE_PATTERN.findall(config)
            for match in matches:
                unresolved.append({
                    "path": path,
                    "template": "{{" + match + "}}",
                    "variable": match
                })

        return unresolved

    def _validate_templates_resolved(
        self,
        states: Dict[str, Dict[str, Any]],
        flow_name: str = ""
    ) -> List[str]:
        """
        Validate that all templates in flow states are resolved.

        After parameter substitution, there should be no remaining {{variable}}
        placeholders. This method checks all states and returns errors for any
        unresolved templates.

        Args:
            states: Dict of state_name -> state_config with resolved parameters
            flow_name: Name of the flow for error context

        Returns:
            List of error messages for unresolved templates

        Example errors:
            - "Unresolved template {{entry_state}} in greeting.transitions.price_question.
               Define 'entry_state' in flow.yaml variables or state parameters."
        """
        errors = []
        flow_context = f" in flow '{flow_name}'" if flow_name else ""

        for state_name, state_config in states.items():
            # Skip abstract states (they are templates, not final states)
            if state_config.get("abstract", False):
                continue

            unresolved = self._find_unresolved_templates(state_config, state_name)
            for item in unresolved:
                errors.append(
                    f"Unresolved template {item['template']} at '{item['path']}'{flow_context}. "
                    f"Define '{item['variable']}' in flow.yaml variables or state parameters."
                )

        return errors

    def _get_required_template_variables(self) -> Dict[str, str]:
        """
        Get list of required template variables with their descriptions.

        These are the standard template variables used across flows that
        must be defined for proper flow operation.

        Returns:
            Dict mapping variable name to description
        """
        return {
            "entry_state": "First qualification state after greeting (e.g., 'spin_situation', 'bant_budget')",
            "next_phase_state": "State to transition to when current phase completes",
            "prev_phase_state": "State to return to on go_back intent",
            "default_price_action": "Default action for price questions (e.g., 'deflect_and_continue', 'answer_with_facts')",
            "default_unclear_action": "Default action for unclear intents (e.g., 'continue_current_goal')",
        }

    def _deep_merge(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Override values take precedence. Lists are replaced, not merged.

        Args:
            base: Base dictionary
            override: Dictionary with overriding values

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_priority_overrides(
        self,
        priorities: List[Dict[str, Any]],
        overrides: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply priority overrides from flow config."""
        result = [p.copy() for p in priorities]

        # Build index by name
        index = {p["name"]: i for i, p in enumerate(result)}

        for override in overrides:
            name = override.get("name")
            if name and name in index:
                idx = index[name]
                result[idx] = self._deep_merge(result[idx], override)

        return result

    def _load_flow_templates(self, flow_name: str) -> Dict[str, Dict[str, Any]]:
        """
        Load prompt templates for a flow.

        Loads base templates from templates/_base/ and merges with
        flow-specific templates from templates/{flow_name}/.

        Args:
            flow_name: Name of the flow

        Returns:
            Dict of template_name -> template_config
        """
        templates = {}

        # Load base templates
        base_templates_file = self.config_dir / "templates" / "_base" / "prompts.yaml"
        if base_templates_file.exists():
            base_data = self._load_yaml("templates/_base/prompts.yaml", required=False)
            templates.update(base_data.get("templates", {}))

        # Load flow-specific templates (override base)
        flow_templates_file = self.config_dir / "templates" / flow_name / "prompts.yaml"
        if flow_templates_file.exists():
            flow_data = self._load_yaml(f"templates/{flow_name}/prompts.yaml", required=False)
            templates.update(flow_data.get("templates", {}))

        return templates

    def _validate_flow(self, flow: FlowConfig) -> None:
        """
        Validate a loaded flow configuration.

        Validates:
        1. Phase mapping references valid states
        2. Entry points reference valid states
        3. All transition targets exist
        4. All {{template}} placeholders have been resolved

        Args:
            flow: FlowConfig to validate

        Raises:
            ConfigValidationError: If validation fails
        """
        errors = []
        known_states = set(flow.states.keys())

        # 1. Validate phase mapping
        for phase, state in flow.phase_mapping.items():
            if state not in known_states:
                errors.append(
                    f"Phase '{phase}' maps to unknown state '{state}'"
                )

        # 2. Validate entry points
        for scenario, state in flow.entry_points.items():
            if state not in known_states:
                errors.append(
                    f"Entry point '{scenario}' references unknown state '{state}'"
                )

        # 3. Validate transitions (skip unresolved templates - they'll be caught below)
        for state_name, state_config in flow.states.items():
            transitions = state_config.get("transitions", {})
            for intent, target in transitions.items():
                if isinstance(target, str):
                    # Skip template placeholders - they'll be validated separately
                    if target.startswith("{{") and target.endswith("}}"):
                        continue
                    if target not in known_states:
                        errors.append(
                            f"State '{state_name}' transition to unknown state '{target}'"
                        )
                elif isinstance(target, list):
                    for rule in target:
                        if isinstance(rule, dict):
                            then_target = rule.get("then")
                            if then_target and then_target not in known_states:
                                # Skip template placeholders
                                if isinstance(then_target, str) and then_target.startswith("{{"):
                                    continue
                                errors.append(
                                    f"State '{state_name}' rule transition to unknown state '{then_target}'"
                                )
                        elif isinstance(rule, str):
                            # Skip template placeholders
                            if rule.startswith("{{") and rule.endswith("}}"):
                                continue
                            if rule not in known_states:
                                errors.append(
                                    f"State '{state_name}' fallback to unknown state '{rule}'"
                                )

        # 4. Validate all templates have been resolved
        # This is critical - unresolved templates will cause runtime errors
        template_errors = self._validate_templates_resolved(flow.states, flow.name)
        errors.extend(template_errors)

        if errors:
            raise ConfigValidationError(errors)

    def __repr__(self) -> str:
        return f"ConfigLoader(config_dir={self.config_dir})"


# Singleton instance for global access
_config_instance: Optional[LoadedConfig] = None
_config_loader: Optional[ConfigLoader] = None


def get_config(reload: bool = False) -> LoadedConfig:
    """
    Get the global configuration instance.

    Args:
        reload: Force reload from files

    Returns:
        LoadedConfig instance
    """
    global _config_instance, _config_loader

    if _config_loader is None:
        _config_loader = ConfigLoader()

    if _config_instance is None or reload:
        _config_instance = _config_loader.load()

    return _config_instance


def init_config(config_dir: Optional[Path] = None) -> LoadedConfig:
    """
    Initialize configuration from a specific directory.

    Args:
        config_dir: Path to config directory

    Returns:
        LoadedConfig instance
    """
    global _config_instance, _config_loader

    _config_loader = ConfigLoader(config_dir)
    _config_instance = _config_loader.load()

    return _config_instance


def validate_config_conditions(
    config: LoadedConfig,
    registry: "ConditionRegistry",
    raise_on_error: bool = True
) -> Dict[str, Any]:
    """
    Validate that all 'when:' conditions in config reference existing conditions.

    This function validates:
    - Conditions in state rules (rules.intent.when)
    - Conditions in transitions (transitions.intent.when)
    - Custom conditions expressions

    Args:
        config: LoadedConfig instance to validate
        registry: ConditionRegistry with registered conditions
        raise_on_error: If True, raise ConfigValidationError on errors

    Returns:
        Dict with validation results:
        {
            "is_valid": bool,
            "errors": [...],
            "warnings": [...],
            "checked_rules": int,
            "checked_transitions": int
        }

    Raises:
        ConfigValidationError: If raise_on_error=True and validation fails

    Example:
        from src.config_loader import get_config, validate_config_conditions
        from src.conditions.state_machine.registry import sm_registry

        config = get_config()
        result = validate_config_conditions(config, sm_registry)
        if not result["is_valid"]:
            print("Validation errors:", result["errors"])
    """
    from src.rules.resolver import RuleResolver
    from src.conditions.expression_parser import ConditionExpressionParser

    # Create expression parser for composite conditions
    expression_parser = ConditionExpressionParser(
        registry=registry,
        custom_conditions=config.custom_conditions
    )

    # Create resolver with expression parser
    resolver = RuleResolver(
        registry=registry,
        default_action=config.default_action,
        expression_parser=expression_parser
    )

    # Get known states
    known_states = set(config.states.keys())

    # Validate config
    validation_result = resolver.validate_config(
        states_config=config.states,
        global_rules={},
        known_states=known_states
    )

    # Also validate custom conditions
    custom_errors = expression_parser.validate_custom_conditions()
    for name, errors in custom_errors.items():
        for error in errors:
            validation_result.add_error(
                error_type="custom_condition_error",
                message=f"Custom condition '{name}': {error}",
                condition_name=name
            )

    # Convert to dict
    result = validation_result.to_dict()

    # Log results
    if validation_result.is_valid:
        logger.info(
            f"Config validation passed: "
            f"{validation_result.checked_rules} rules, "
            f"{validation_result.checked_transitions} transitions"
        )
    else:
        logger.warning(
            f"Config validation found {len(validation_result.errors)} error(s)"
        )
        for err in validation_result.errors:
            logger.warning(f"  - {err.message}")

    # Raise if requested
    if raise_on_error and not validation_result.is_valid:
        error_messages = [e.message for e in validation_result.errors]
        raise ConfigValidationError(error_messages)

    return result


def get_config_validated(
    registry: "ConditionRegistry" = None,
    reload: bool = False
) -> LoadedConfig:
    """
    Get configuration with condition validation.

    This is a convenience function that loads config and validates
    all condition references against the registry.

    Args:
        registry: ConditionRegistry to validate against (defaults to sm_registry)
        reload: Force reload from files

    Returns:
        LoadedConfig instance (validated)

    Raises:
        ConfigValidationError: If condition validation fails

    Example:
        from src.config_loader import get_config_validated
        config = get_config_validated()  # Uses sm_registry by default
    """
    config = get_config(reload=reload)

    # Get registry if not provided
    if registry is None:
        from src.conditions.state_machine.registry import sm_registry
        registry = sm_registry

    # Validate conditions
    validate_config_conditions(config, registry, raise_on_error=True)

    return config


# Export all public components
__all__ = [
    "ConfigLoader",
    "LoadedConfig",
    "FlowConfig",
    "ConfigLoadError",
    "ConfigValidationError",
    "get_config",
    "get_config_validated",
    "init_config",
    "validate_config_conditions",
]
