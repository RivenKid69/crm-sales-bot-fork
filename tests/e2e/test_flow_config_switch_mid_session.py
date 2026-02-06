"""E2E: switch flow/config mid-session (client changed plan/settings)."""

import os
import pytest

from src.llm import OllamaClient
from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer


def _get_real_llm():
    model = os.getenv("E2E_LLM_MODEL", "qwen3:14b")
    base_url = os.getenv("OLLAMA_BASE_URL")
    llm = OllamaClient(model=model, base_url=base_url)
    if not llm.health_check():
        pytest.skip(
            f"Ollama model '{model}' not available at {llm.base_url}. "
            "Start ollama and pull the model to run this test."
        )
    return llm


def test_switch_flow_config_mid_session(tmp_path):
    llm = _get_real_llm()
    session_id = "sess-switch-flow"
    client_id = "client-switch-1"

    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "snapshot_buffer.sqlite"))
    manager = SessionManager(snapshot_buffer=buffer)

    # Initial profile
    flow_a = "spin_selling"
    config_a = "tenant_alpha"
    bot = manager.get_or_create(
        session_id,
        llm=llm,
        client_id=client_id,
        flow_name=flow_a,
        config_name=config_a,
    )
    bot.process("Привет")
    bot.process("У нас небольшой бизнес")

    assert bot._flow.name == flow_a
    assert bot._config.name == config_a

    # Client changes plan/settings: new flow/config
    flow_b = "bant"
    config_b = "tenant_beta"

    bot_switched = manager.get_or_create(
        session_id,
        llm=llm,
        client_id=client_id,
        flow_name=flow_b,
        config_name=config_b,
    )

    assert bot_switched._flow.name == flow_b
    assert bot_switched._config.name == config_b
    assert bot_switched.client_id == client_id
    # Ensure bot can continue without crash
    result = bot_switched.process("Давайте продолжим")
    assert "response" in result
