"""E2E test: snapshot after real dialog stop and restore continuation."""

import os
import time

import pytest

from src.llm import OllamaClient
from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer

def _get_real_llm():
    model = os.getenv("E2E_LLM_MODEL", "ministral-3:14b-instruct-2512-q8_0")
    base_url = os.getenv("OLLAMA_BASE_URL")
    llm = OllamaClient(model=model, base_url=base_url)
    if not llm.health_check():
        pytest.skip(
            f"Ollama model '{model}' not available at {llm.base_url}. "
            "Start ollama and pull the model to run this test."
        )
    return llm

def test_snapshot_restore_real_dialog(tmp_path):
    llm = _get_real_llm()
    session_id = "sess-real-restore"
    client_id = "client-real-1"
    external_history = {session_id: []}

    def load_history_tail(sid, n):
        return external_history.get(sid, [])[-n:]

    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "snapshot_buffer.sqlite"))
    manager = SessionManager(
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
    )

    bot = manager.get_or_create(session_id, llm=llm, client_id=client_id)
    user_messages = [
        "Привет",
        "У нас магазин, 10 сотрудников",
        "Есть проблемы с учетом продаж",
    ]

    for msg in user_messages:
        bot.process(msg)
        external_history[session_id].append(bot.history[-1])

    # Simulate dialog end -> snapshot via explicit close
    closed = manager.close_session(session_id, client_id=client_id)
    assert closed is True
    assert buffer.count() == 1

    # Restore from local snapshot buffer
    manager2 = SessionManager(
        load_history_tail=load_history_tail,
        snapshot_buffer=buffer,
    )
    restored = manager2.get_or_create(session_id, llm=llm, client_id=client_id)

    # Snapshot should have been consumed
    assert buffer.count() == 0
    assert restored.history == external_history[session_id][-4:]
    assert restored.last_action is not None
    assert restored.client_id == client_id

    # Continue dialog from same place
    result = restored.process("Давайте продолжим")
    assert "response" in result
    assert restored.history[-1]["user"] == "Давайте продолжим"
