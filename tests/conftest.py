"""
Shared pytest fixtures for CRM Sales Bot tests.

Provides fixtures for:
- Mock LLM clients
- Temporary config directories with custom parameters
- Feature flag overrides
- Bot factory with custom configs
"""

import pytest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock, patch
from typing import Any, Dict, Optional, Callable
import yaml
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# Mock LLM Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Basic mock LLM client."""
    llm = MagicMock()
    llm.generate.return_value = "Здравствуйте! Чем могу помочь?"
    llm.health_check.return_value = True
    llm.model = "mock-model"
    return llm


@pytest.fixture
def mock_llm_with_responses():
    """Mock LLM client with configurable responses."""
    def _create(responses: Dict[str, str] = None, default: str = "Ответ"):
        llm = MagicMock()
        responses = responses or {}

        def generate_side_effect(prompt, **kwargs):
            for key, response in responses.items():
                if key in prompt:
                    return response
            return default

        llm.generate.side_effect = generate_side_effect
        llm.health_check.return_value = True
        llm.model = "mock-model"
        return llm
    return _create


@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client for classifier tests."""
    client = Mock()
    client.health_check.return_value = True
    return client


# Alias for backward compatibility
@pytest.fixture
def mock_vllm_client(mock_ollama_client):
    """Alias for mock_ollama_client (backward compatibility)."""
    return mock_ollama_client


# =============================================================================
# Config Directory Fixtures
# =============================================================================

def _create_minimal_config(tmp_path: Path, overrides: Dict[str, Any] = None) -> Path:
    """Helper to create minimal config directory with overrides."""
    overrides = overrides or {}

    (tmp_path / "states").mkdir(exist_ok=True)
    (tmp_path / "spin").mkdir(exist_ok=True)
    (tmp_path / "conditions").mkdir(exist_ok=True)

    # Base constants
    constants = {
        "spin": {
            "phases": ["situation", "problem", "implication", "need_payoff"],
            "states": {
                "situation": "spin_situation",
                "problem": "spin_problem",
                "implication": "spin_implication",
                "need_payoff": "spin_need_payoff",
            },
            "progress_intents": {
                "situation_provided": "situation",
                "problem_revealed": "problem",
                "implication_acknowledged": "implication",
                "need_expressed": "need_payoff",
            },
        },
        "limits": {
            "max_consecutive_objections": 3,
            "max_total_objections": 5,
            "max_gobacks": 2,
        },
        "intents": {
            "go_back": ["go_back", "correct_info"],
            "categories": {
                "objection": ["objection_price", "objection_no_time", "objection_competitor", "objection_think"],
                "positive": ["agreement", "demo_request", "callback_request", "contact_provided"],
                "question": ["price_question", "question_features"],
                "spin_progress": ["situation_provided", "problem_revealed", "implication_acknowledged", "need_expressed"],
                "negative": ["rejection", "farewell"],
            }
        },
        "policy": {
            "overlay_allowed_states": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff", "presentation"],
            "protected_states": ["greeting", "close", "success"],
            "aggressive_actions": ["ask_for_demo", "ask_for_contact"],
            "repair_actions": {
                "stuck": "clarify_one_question",
                "oscillation": "summarize_and_clarify",
            },
        },
        "lead_scoring": {
            "positive_weights": {
                "demo_request": 30,
                "contact_provided": 35,
                "callback_request": 25,
                "price_with_size": 25,
                "explicit_problem": 15,
            },
            "negative_weights": {
                "objection_price": -15,
                "objection_no_time": -20,
                "objection_no_need": -25,
                "rejection_soft": -25,
            },
            "thresholds": {
                "cold": [0, 29],
                "warm": [30, 49],
                "hot": [50, 69],
                "very_hot": [70, 100],
            },
            "skip_phases": {
                "cold": [],
                "warm": ["spin_implication", "spin_need_payoff"],
                "hot": ["spin_problem", "spin_implication", "spin_need_payoff"],
                "very_hot": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"],
            },
            "paths": {
                "cold": "full_spin",
                "warm": "short_spin",
                "hot": "direct_present",
                "very_hot": "direct_close",
            },
        },
        "guard": {
            "max_turns": 25,
            "max_phase_attempts": 3,
            "max_same_state": 4,
            "max_same_message": 2,
            "timeout_seconds": 1800,
            "progress_check_interval": 5,
            "min_unique_states_for_progress": 2,
            "high_frustration_threshold": 7,
            "profiles": {
                "strict": {
                    "max_turns": 15,
                    "max_phase_attempts": 2,
                    "max_same_state": 3,
                    "timeout_seconds": 900,
                },
                "relaxed": {
                    "max_turns": 40,
                    "max_phase_attempts": 5,
                    "max_same_state": 6,
                    "timeout_seconds": 3600,
                },
            },
        },
        "frustration": {
            "max_level": 10,
            "weights": {
                "frustrated": 3,
                "skeptical": 1,
                "rushed": 1,
                "confused": 1,
            },
            "decay": {
                "neutral": 1,
                "positive": 2,
                "interested": 2,
            },
            "thresholds": {
                "warning": 4,
                "high": 7,
                "critical": 9,
            },
        },
        "circular_flow": {
            "allowed_gobacks": {
                "spin_problem": "spin_situation",
                "spin_implication": "spin_problem",
                "spin_need_payoff": "spin_implication",
                "presentation": "spin_need_payoff",
                "close": "presentation",
                "handle_objection": "presentation",
                "soft_close": "greeting",
            },
        },
        "context": {
            "state_order": {
                "greeting": 0,
                "spin_situation": 1,
                "spin_problem": 2,
                "spin_implication": 3,
                "spin_need_payoff": 4,
                "presentation": 5,
                "handle_objection": 5,
                "close": 6,
                "success": 7,
                "soft_close": -1,
            },
            "phase_order": {
                "greeting": 0,
                "situation": 1,
                "problem": 2,
                "implication": 3,
                "need_payoff": 4,
                "presentation": 5,
                "close": 6,
            },
        },
        "fallback": {
            "rephrase_templates": {
                "spin_situation": [
                    "Расскажите подробнее о вашей компании?",
                    "Сколько у вас сотрудников?",
                ],
                "spin_problem": [
                    "С какими сложностями вы сталкиваетесь?",
                    "Что вас больше всего беспокоит?",
                ],
            },
            "options_templates": {
                "spin_situation": {
                    "question": "Расскажите о себе:",
                    "options": ["Малый бизнес", "Средний бизнес", "Крупная компания"],
                },
            },
            "default_rephrase": "Давайте попробую спросить иначе...",
            "default_options": {
                "question": "Что вас интересует?",
                "options": ["Узнать больше", "Посмотреть демо", "Узнать цены"],
            },
        },
        "cta": {
            "early_states": ["greeting", "spin_situation", "spin_problem"],
            "templates": {
                "spin_implication": ["Хотите узнать, как мы решаем эту проблему?"],
                "spin_need_payoff": ["Готовы посмотреть демо?"],
                "presentation": ["Записаться на демо?", "Оставить контакты?"],
                "close": ["Оставьте номер, мы перезвоним"],
            },
            "by_action": {
                "demo": ["Записаться на демо?"],
                "contact": ["Оставить контакты?"],
                "trial": ["Попробовать бесплатно?"],
            },
        },
    }

    # Apply overrides using deep merge
    def deep_merge(base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    constants = deep_merge(constants, overrides)

    with open(tmp_path / "constants.yaml", 'w', encoding='utf-8') as f:
        yaml.dump(constants, f, allow_unicode=True)

    # States
    states = {
        "meta": {"version": "1.0"},
        "defaults": {"default_action": "continue_current_goal"},
        "states": {
            "greeting": {
                "goal": "Приветствие клиента",
                "transitions": {
                    "agreement": "spin_situation",
                    "demo_request": "close",
                    "price_question": "spin_situation",
                },
                "rules": {
                    "greeting": "greet_back",
                },
            },
            "spin_situation": {
                "goal": "Понять ситуацию клиента",
                "phase": "situation",
                "transitions": {
                    "data_complete": "spin_problem",
                    "situation_provided": "spin_problem",
                },
            },
            "spin_problem": {
                "goal": "Выявить проблемы",
                "phase": "problem",
                "transitions": {
                    "data_complete": "spin_implication",
                    "problem_revealed": "spin_implication",
                },
            },
            "spin_implication": {
                "goal": "Показать последствия",
                "phase": "implication",
                "transitions": {
                    "data_complete": "spin_need_payoff",
                    "implication_acknowledged": "spin_need_payoff",
                },
            },
            "spin_need_payoff": {
                "goal": "Сформировать потребность",
                "phase": "need_payoff",
                "transitions": {
                    "data_complete": "presentation",
                    "need_expressed": "presentation",
                },
            },
            "presentation": {
                "goal": "Презентация продукта",
                "transitions": {
                    "agreement": "close",
                    "demo_request": "close",
                    "callback_request": "close",
                },
            },
            "handle_objection": {
                "goal": "Обработка возражения",
                "transitions": {
                    "agreement": "presentation",
                },
            },
            "close": {
                "goal": "Закрытие сделки",
                "transitions": {
                    "contact_provided": "success",
                    "data_complete": "success",
                },
            },
            "success": {
                "goal": "Успешное завершение",
                "is_final": True,
            },
            "soft_close": {
                "goal": "Мягкое завершение",
                "is_final": False,
                "transitions": {
                    "agreement": "spin_situation",
                    "demo_request": "close",
                },
            },
        },
    }

    with open(tmp_path / "states" / "sales_flow.yaml", 'w', encoding='utf-8') as f:
        yaml.dump(states, f, allow_unicode=True)

    # SPIN phases
    spin = {
        "phase_order": ["situation", "problem", "implication", "need_payoff"],
        "phases": {
            "situation": {"state": "spin_situation", "skippable": False},
            "problem": {"state": "spin_problem", "skippable": True},
            "implication": {"state": "spin_implication", "skippable": True},
            "need_payoff": {"state": "spin_need_payoff", "skippable": True},
        },
    }

    with open(tmp_path / "spin" / "phases.yaml", 'w', encoding='utf-8') as f:
        yaml.dump(spin, f, allow_unicode=True)

    # Custom conditions
    custom = {
        "conditions": {
            "ready_for_demo": {
                "description": "Client ready for demo",
                "expression": {
                    "and": ["has_contact", {"or": ["has_pain", "has_interest"]}],
                },
            },
        },
        "aliases": {},
    }

    with open(tmp_path / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
        yaml.dump(custom, f, allow_unicode=True)

    return tmp_path


@pytest.fixture
def config_dir(tmp_path):
    """Create a minimal config directory."""
    return _create_minimal_config(tmp_path)


@pytest.fixture
def config_factory(tmp_path):
    """Factory to create config directories with custom overrides."""
    created_dirs = []

    def _create(**overrides) -> Path:
        # Create unique subdir for each call
        subdir = tmp_path / f"config_{len(created_dirs)}"
        subdir.mkdir(exist_ok=True)
        created_dirs.append(subdir)
        return _create_minimal_config(subdir, overrides)

    return _create


@pytest.fixture
def config_with_custom_limits(tmp_path):
    """Config with custom limits for testing."""
    return _create_minimal_config(tmp_path, {
        "limits": {
            "max_consecutive_objections": 2,
            "max_total_objections": 4,
            "max_gobacks": 1,
        },
    })


@pytest.fixture
def config_with_strict_guard(tmp_path):
    """Config with strict guard profile values."""
    return _create_minimal_config(tmp_path, {
        "guard": {
            "max_turns": 10,
            "max_phase_attempts": 2,
            "max_same_state": 3,
            "max_same_message": 1,
            "timeout_seconds": 60,
            "high_frustration_threshold": 5,
        },
        "frustration": {
            "thresholds": {
                "warning": 3,
                "high": 5,
                "critical": 8,
            },
        },
    })


@pytest.fixture
def config_with_hot_lead_settings(tmp_path):
    """Config for hot lead phase skipping tests."""
    return _create_minimal_config(tmp_path, {
        "lead_scoring": {
            "thresholds": {
                "cold": [0, 20],
                "warm": [21, 40],
                "hot": [41, 60],
                "very_hot": [61, 100],
            },
            "skip_phases": {
                "cold": [],
                "warm": ["spin_implication"],
                "hot": ["spin_problem", "spin_implication"],
                "very_hot": ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"],
            },
        },
    })


# =============================================================================
# Feature Flags Fixtures
# =============================================================================

@pytest.fixture
def feature_flags_override():
    """Context manager for temporary feature flag overrides."""
    from src.feature_flags import flags

    @contextmanager
    def _override(**kwargs):
        original = {}
        for flag, value in kwargs.items():
            try:
                original[flag] = flags.is_enabled(flag)
            except:
                original[flag] = None
            flags.set_override(flag, value)
        try:
            yield flags
        finally:
            for flag in kwargs:
                flags.clear_override(flag)

    return _override


@pytest.fixture(autouse=False)
def clean_feature_flags():
    """Cleanup feature flags after test."""
    from src.feature_flags import flags
    yield
    flags.clear_all_overrides()


# =============================================================================
# Mock Context Fixtures
# =============================================================================

class MockContext:
    """Mock context for condition evaluation."""
    def __init__(self, **kwargs):
        self.collected_data = kwargs.pop('collected_data', {})
        self.state = kwargs.pop('state', 'greeting')
        self.turn_number = kwargs.pop('turn_number', 0)
        self.intent = kwargs.pop('intent', None)
        self.frustration_level = kwargs.pop('frustration_level', 0)
        self.lead_score = kwargs.pop('lead_score', 0)
        self.consecutive_objections = kwargs.pop('consecutive_objections', 0)
        self.total_objections = kwargs.pop('total_objections', 0)
        self.goback_count = kwargs.pop('goback_count', 0)
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_context():
    """Factory for mock context objects."""
    def _create(**kwargs):
        return MockContext(**kwargs)
    return _create


class MockRegistry:
    """Mock registry that returns predefined values."""
    def __init__(self, conditions: dict = None):
        self._conditions = conditions or {}
        self.name = "mock_registry"

    def has(self, name: str) -> bool:
        return name in self._conditions

    def evaluate(self, name: str, ctx, trace=None) -> bool:
        if name not in self._conditions:
            return False
        value = self._conditions[name]
        if callable(value):
            return value(ctx)
        return value

    def list_all(self):
        return list(self._conditions.keys())


@pytest.fixture
def mock_registry():
    """Factory for mock registry objects."""
    def _create(conditions: dict = None):
        return MockRegistry(conditions)
    return _create


# =============================================================================
# Bot Factory Fixtures
# =============================================================================

@pytest.fixture
def bot_factory(mock_llm, config_factory, feature_flags_override):
    """Factory to create SalesBot with custom config and flags."""
    from src.feature_flags import flags

    def _create(
        config_overrides: Dict[str, Any] = None,
        flag_overrides: Dict[str, bool] = None,
        llm=None,
    ):
        # Enable required feature groups
        flags.enable_group("phase_0")
        flags.enable_group("phase_1")

        # Apply flag overrides
        if flag_overrides:
            for flag, value in flag_overrides.items():
                flags.set_override(flag, value)

        # Create config
        config_dir = config_factory(**(config_overrides or {}))

        # Import and create bot
        from src.bot import SalesBot
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        bot = SalesBot(llm or mock_llm, config=config)
        return bot

    return _create


# =============================================================================
# Component Fixtures
# =============================================================================

@pytest.fixture
def conversation_guard_factory():
    """Factory to create ConversationGuard with custom config."""
    def _create(
        max_turns: int = 25,
        max_phase_attempts: int = 3,
        max_same_state: int = 4,
        max_same_message: int = 2,
        timeout_seconds: int = 1800,
        high_frustration_threshold: int = 7,
    ):
        from src.conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(
            max_turns=max_turns,
            max_phase_attempts=max_phase_attempts,
            max_same_state=max_same_state,
            max_same_message=max_same_message,
            timeout_seconds=timeout_seconds,
            high_frustration_threshold=high_frustration_threshold,
        )
        return ConversationGuard(config)

    return _create


@pytest.fixture
def lead_scorer_factory():
    """Factory to create LeadScorer with custom config."""
    def _create(
        positive_weights: Dict[str, int] = None,
        negative_weights: Dict[str, int] = None,
        thresholds: Dict[str, list] = None,
        skip_phases: Dict[str, list] = None,
    ):
        from src.lead_scoring import LeadScorer

        config = {}
        if positive_weights:
            config['positive_weights'] = positive_weights
        if negative_weights:
            config['negative_weights'] = negative_weights
        if thresholds:
            config['thresholds'] = thresholds
        if skip_phases:
            config['skip_phases'] = skip_phases

        return LeadScorer(config=config if config else None)

    return _create


@pytest.fixture
def frustration_tracker_factory():
    """Factory to create FrustrationTracker with custom config."""
    def _create(
        max_level: int = 10,
        weights: Dict[str, int] = None,
        decay: Dict[str, int] = None,
        thresholds: Dict[str, int] = None,
    ):
        from src.tone_analyzer.frustration_tracker import FrustrationTracker

        tracker = FrustrationTracker()

        # Override config if provided
        if max_level:
            tracker.max_level = max_level
        if weights:
            tracker.weights = weights
        if decay:
            tracker.decay = decay
        if thresholds:
            tracker.thresholds = thresholds

        return tracker

    return _create


# =============================================================================
# Real Config Fixtures (for integration tests)
# =============================================================================

@pytest.fixture
def real_config():
    """Load the actual config from src/yaml_config/."""
    from src.config_loader import ConfigLoader
    loader = ConfigLoader()
    return loader.load()


@pytest.fixture
def real_constants():
    """Load the actual constants.yaml."""
    constants_path = Path(__file__).parent.parent / "src" / "yaml_config" / "constants.yaml"
    with open(constants_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture
def real_settings():
    """Load the actual settings.yaml."""
    settings_path = Path(__file__).parent.parent / "src" / "settings.yaml"
    with open(settings_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
