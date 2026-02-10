"""E2E: multiple sessions with different flow/config and external profile source."""

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

def test_multi_session_flow_config_restore(tmp_path):
    llm = _get_real_llm()

    external_profiles = {
        "sess-a": {"client_id": "client-a", "flow_name": "spin_selling", "config_name": "tenant_alpha"},
        "sess-b": {"client_id": "client-b", "flow_name": "bant", "config_name": "tenant_beta"},
        "sess-c": {"client_id": "client-c", "flow_name": "meddic", "config_name": "tenant_gamma"},
    }

    external_snapshots = {}
    external_history = {sid: [] for sid in external_profiles}

    def get_profile(session_id: str):
        return external_profiles[session_id]

    def save_snapshot(sid, snapshot):
        external_snapshots[sid] = snapshot

    def load_snapshot(sid):
        return external_snapshots.get(sid)

    def load_history_tail(sid, n):
        return external_history.get(sid, [])[-n:]

    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "snapshot_buffer.sqlite"))
    manager = SessionManager(
        save_snapshot=save_snapshot,
        load_snapshot=load_snapshot,
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
    )

    # Simulate dialog activity for each session
    for sid in external_profiles.keys():
        profile = get_profile(sid)
        bot = manager.get_or_create(
            sid,
            llm=llm,
            client_id=profile["client_id"],
            flow_name=profile["flow_name"],
            config_name=profile["config_name"],
        )
        for msg in [
            "Привет",
            "У нас небольшой бизнес",
            "Есть проблемы с продажами",
        ]:
            bot.process(msg)
            external_history[sid].append(bot.history[-1])

    # Server signals each dialog has ended
    for sid, profile in external_profiles.items():
        closed = manager.close_session(sid, client_id=profile["client_id"])
        assert closed is True
    assert buffer.count() == len(external_profiles)

    # Validate snapshots in buffer are not mixed
    for sid, profile in external_profiles.items():
        snap = buffer.get(sid)
        assert snap["client_id"] == profile["client_id"]
        assert snap["flow_name"] == profile["flow_name"]
        assert snap["config_name"] == profile["config_name"]

    # Restore from buffer (new manager simulating new process)
    manager2 = SessionManager(
        save_snapshot=save_snapshot,
        load_snapshot=load_snapshot,
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
    )

    for sid, profile in external_profiles.items():
        restored = manager2.get_or_create(
            sid,
            llm=llm,
            client_id=profile["client_id"],
            flow_name=profile["flow_name"],
            config_name=profile["config_name"],
        )

        # Ensure correct flow/config restored and client_id preserved
        assert restored._flow.name == profile["flow_name"]
        assert restored._config.name == profile["config_name"]
        assert restored.client_id == profile["client_id"]

        # Ensure history tail is from correct session
        assert restored.history == external_history[sid][-4:]
