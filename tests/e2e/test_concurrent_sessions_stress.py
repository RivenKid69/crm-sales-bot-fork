"""E2E stress test: concurrent dialogues with Qwen3 14B via simulator ClientAgent."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from src.llm import OllamaClient
from src.simulator.personas import PERSONAS, get_all_persona_names
from src.simulator.client_agent import ClientAgent
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

def _run_dialog(session_id, client_id, persona_key, manager, llm, turns, token):
    persona = PERSONAS[persona_key]
    client = ClientAgent(llm, persona, persona_key=persona_key)

    client_message = client.start_conversation()
    client_message = f"{token} {client_message}"

    for _ in range(turns):
        bot = manager.get_or_create(session_id, llm=llm, client_id=client_id)
        result = bot.process(client_message)
        if result.get("is_final"):
            break
        bot_message = result.get("response", "")
        client_message = client.respond(bot_message)
        client_message = f"{token} {client_message}"

    # Save snapshot to exercise buffer path
    manager.save(session_id, client_id=client_id)
    bot = manager.get_or_create(session_id, llm=llm, client_id=client_id)
    return {
        "session_id": session_id,
        "client_id": client_id,
        "token": token,
        "history": list(bot.history),
        "collected_data": dict(bot.state_machine.collected_data),
    }

def test_concurrent_sessions_no_leakage(tmp_path):
    llm = _get_real_llm()

    sessions = int(os.getenv("E2E_STRESS_SESSIONS", "4"))
    turns = int(os.getenv("E2E_STRESS_TURNS", "4"))
    parallel = int(os.getenv("E2E_STRESS_PARALLEL", "2"))

    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "snapshot_buffer.sqlite"))
    manager = SessionManager(
        snapshot_buffer=buffer,
    )

    persona_keys = get_all_persona_names()
    results = []

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = []
        for i in range(sessions):
            sid = f"stress-{i}-{uuid.uuid4().hex[:6]}"
            client_id = f"client-{i}-{uuid.uuid4().hex[:6]}"
            token = f"[SID{i}]"
            persona_key = persona_keys[i % len(persona_keys)]
            futures.append(
                executor.submit(
                    _run_dialog,
                    sid,
                    client_id,
                    persona_key,
                    manager,
                    llm,
                    turns,
                    token,
                )
            )

        for future in as_completed(futures):
            results.append(future.result())

    tokens = {r["token"] for r in results}
    assert buffer.count() == sessions

    if os.getenv("E2E_STRESS_LOGS") == "1":
        for result in results:
            history_users = " | ".join([h.get("user", "") for h in result["history"][-3:]])
            print(f"[SESSION] {result['session_id']} {result['token']} users: {history_users}")

    for result in results:
        history_text = " ".join([h.get("user", "") for h in result["history"]])
        assert result["token"] in history_text
        for other in tokens - {result["token"]}:
            assert other not in history_text
