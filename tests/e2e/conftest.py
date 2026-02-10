"""
Pytest fixtures for E2E sales technique tests.

Provides fixtures for:
- Mock LLM clients for testing
- Real LLM client (when available)
- Flow configuration helpers
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock
from typing import List, Optional
import os

# =============================================================================
# LLM Fixtures
# =============================================================================

@pytest.fixture
def mock_e2e_llm():
    """
    Mock LLM for e2e tests that simulates client responses.

    Returns deterministic responses based on the conversation state.
    """
    llm = MagicMock()

    # Default bot responses
    bot_responses = [
        "Здравствуйте! Расскажите о вашем бизнесе.",
        "Какие сложности вы испытываете сейчас?",
        "Понимаю. Это действительно важная проблема.",
        "Наше решение поможет вам с этим.",
        "Давайте запланируем демонстрацию?",
    ]

    call_count = [0]

    def generate_side_effect(prompt, **kwargs):
        idx = call_count[0] % len(bot_responses)
        call_count[0] += 1
        return bot_responses[idx]

    llm.generate.side_effect = generate_side_effect
    llm.health_check.return_value = True
    llm.model = "mock-e2e-model"

    return llm

@pytest.fixture
def mock_client_llm():
    """
    Mock LLM for simulating client responses.

    Simulates a cooperative client going through sales flow.
    """
    llm = MagicMock()

    # Client responses simulating happy path
    client_responses = [
        "Здравствуйте, расскажите что у вас есть",
        "У нас небольшой магазин, 5 сотрудников",
        "Да, есть проблемы с учётом товаров",
        "Это стоит нам около 50 тысяч в месяц",
        "Да, хотел бы увидеть демо",
        "Отлично, давайте созвонимся завтра",
    ]

    call_count = [0]

    def generate_side_effect(prompt, **kwargs):
        idx = call_count[0] % len(client_responses)
        call_count[0] += 1
        return client_responses[idx]

    llm.generate.side_effect = generate_side_effect
    llm.health_check.return_value = True
    llm.model = "mock-client-model"

    return llm

@pytest.fixture(scope="session")
def real_llm():
    """
    Real LLM client for integration tests.

    Returns None if vLLM is not available.
    Skip tests using this fixture when LLM unavailable.
    """
    try:
        from src.llm import VLLMClient

        # Try to connect to vLLM
        client = VLLMClient(
            model="Qwen/Qwen3-1.8B-AWQ",
            base_url=os.environ.get("VLLM_URL", "http://localhost:8000/v1")
        )

        if client.health_check():
            return client
        return None
    except Exception:
        return None

@pytest.fixture
def skip_without_llm(real_llm):
    """Skip test if real LLM is not available."""
    if real_llm is None:
        pytest.skip("Real LLM not available")
    return real_llm

# =============================================================================
# Scenario Fixtures
# =============================================================================

@pytest.fixture
def all_scenarios():
    """Get all 20 e2e scenarios."""
    from src.simulator.e2e_scenarios import ALL_SCENARIOS
    return ALL_SCENARIOS

@pytest.fixture
def scenario_by_flow():
    """Get scenario by flow name."""
    from src.simulator.e2e_scenarios import get_scenario_by_flow
    return get_scenario_by_flow

@pytest.fixture
def scenarios_by_persona():
    """Get scenarios filtered by persona."""
    from src.simulator.e2e_scenarios import get_scenarios_by_persona
    return get_scenarios_by_persona

# =============================================================================
# Runner Fixtures
# =============================================================================

@pytest.fixture
def simulation_runner(mock_e2e_llm, mock_client_llm):
    """Create SimulationRunner with mock LLMs."""
    from src.simulator.runner import SimulationRunner

    return SimulationRunner(
        bot_llm=mock_e2e_llm,
        client_llm=mock_client_llm,
        verbose=False
    )

@pytest.fixture
def e2e_evaluator():
    """Create E2EEvaluator instance."""
    from src.simulator.e2e_evaluator import E2EEvaluator
    return E2EEvaluator()

# =============================================================================
# Flow Configuration Fixtures
# =============================================================================

@pytest.fixture
def flow_configs_path():
    """Path to flow configurations."""
    return Path(__file__).parent.parent.parent / "src" / "yaml_config" / "flows"

@pytest.fixture
def available_flows(flow_configs_path):
    """List of available flow names."""
    flows = []
    for item in flow_configs_path.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            flow_yaml = item / "flow.yaml"
            if flow_yaml.exists():
                flows.append(item.name)
    return sorted(flows)

# =============================================================================
# Results Directory Fixture
# =============================================================================

@pytest.fixture
def e2e_results_dir(tmp_path):
    """Create temporary directory for e2e results."""
    results_dir = tmp_path / "e2e_results"
    results_dir.mkdir()
    return results_dir
