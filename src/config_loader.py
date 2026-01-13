"""
Configuration Loader for State Machine and Dialogue Systems.

This module loads and validates YAML configuration files for the
state machine, SPIN phases, conditions, and related subsystems.

Part of Phase 1: State Machine Parameterization
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Union
from dataclasses import dataclass, field
import yaml
import logging

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


class ConfigLoader:
    """
    Loads and validates YAML configuration files.

    Provides:
    - Loading of all config files from src/config/
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


# Export all public components
__all__ = [
    "ConfigLoader",
    "LoadedConfig",
    "ConfigLoadError",
    "ConfigValidationError",
    "get_config",
    "init_config",
]
