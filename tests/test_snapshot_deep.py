"""Deep tests for snapshot system and supporting infrastructure."""

import time
from types import SimpleNamespace

from src.state_machine import StateMachine
from src.conversation_guard import ConversationGuard, GuardConfig
from src.lead_scoring import LeadScorer
from src.fallback_handler import FallbackHandler
from src.objection_handler import ObjectionHandler, ObjectionType
from src.context_window import ContextWindow, TurnContext, EpisodicMemory, EpisodeType
from src.metrics import ConversationMetrics, ConversationOutcome
from src.history_compactor import HistoryCompactor
from src.snapshot_buffer import LocalSnapshotBuffer
from src.session_lock import SessionLockManager
from src.session_manager import SessionManager
from src.bot import SalesBot


class DummyLLM:
    def __init__(self):
        self.model = "dummy-llm"
        self.last_prompt = None

    def generate_structured(self, prompt, schema):
        self.last_prompt = prompt
        # Return dict compatible with HistoryCompactSchema
        return {
            "summary": ["ok"],
            "key_facts": ["fact"],
            "objections": [],
            "decisions": [],
            "open_questions": [],
            "next_steps": ["next"],
        }


def _mk_history(n):
    return [{"user": f"u{i}", "bot": f"b{i}"} for i in range(n)]


def test_state_machine_serialization_includes_disambiguation():
    sm = StateMachine()
    sm.state = "spin_problem"
    sm.current_phase = "problem"
    sm.collected_data = {"company_size": 10}
    sm.in_disambiguation = True
    sm.disambiguation_context = {"options": ["a", "b"]}
    sm.pre_disambiguation_state = "spin_situation"
    sm.turns_since_last_disambiguation = 3

    sm.intent_tracker.record("problem_revealed", sm.state)

    data = sm.to_dict()
    restored = StateMachine.from_dict(data)

    assert restored.state == "spin_problem"
    assert restored.current_phase == "problem"
    assert restored.collected_data == {"company_size": 10}
    assert restored.in_disambiguation is True
    assert restored.disambiguation_context == {"options": ["a", "b"]}
    assert restored.pre_disambiguation_state == "spin_situation"
    assert restored.turns_since_last_disambiguation == 3
    assert restored.intent_tracker.turn_number == sm.intent_tracker.turn_number


def test_conversation_guard_elapsed_time_restore():
    guard = ConversationGuard(GuardConfig(timeout_seconds=10))
    guard.check("greeting", "hi", {})
    time.sleep(0.02)

    data = guard.to_dict()
    restored = ConversationGuard.from_dict(data)
    assert restored.turn_count == guard.turn_count
    assert restored._state.start_time is not None


def test_lead_scorer_internal_fields_restore():
    scorer = LeadScorer()
    scorer.apply_turn_decay()
    scorer.add_signal("explicit_problem")
    scorer.end_turn()
    scorer._turns_without_end_turn = 2

    data = scorer.to_dict()
    restored = LeadScorer.from_dict(data)
    assert restored._raw_score == scorer._raw_score
    assert restored._turn_count == scorer._turn_count
    assert restored._decay_applied_this_turn == scorer._decay_applied_this_turn
    assert restored._turns_without_end_turn == scorer._turns_without_end_turn
    assert restored.signals_history == scorer.signals_history


def test_fallback_handler_stats_and_used_templates_restore():
    handler = FallbackHandler()
    handler._stats.total_count = 2
    handler._stats.tier_counts = {"tier_1": 2}
    handler._stats.state_counts = {"spin_situation": 1}
    handler._stats.last_tier = "tier_1"
    handler._stats.last_state = "spin_situation"
    handler._stats.dynamic_cta_counts = {"cta_demo": 1}
    handler._stats.consecutive_tier_2_count = 1
    handler._stats.consecutive_tier_2_state = "spin_problem"
    handler._used_templates = {"tier_1": ["a", "b"]}

    data = handler.to_dict()
    restored = FallbackHandler.from_dict(data)
    assert restored._stats.total_count == 2
    assert restored._stats.tier_counts["tier_1"] == 2
    assert restored._stats.consecutive_tier_2_state == "spin_problem"
    assert restored._used_templates["tier_1"] == ["a", "b"]


def test_objection_handler_restore_attempts():
    handler = ObjectionHandler()
    handler.objection_attempts = {ObjectionType.PRICE: 2}
    data = handler.to_dict()
    restored = ObjectionHandler.from_dict(data)
    assert restored.objection_attempts.get(ObjectionType.PRICE) == 2


def test_context_window_full_restore():
    cw = ContextWindow(max_size=3)
    turn = TurnContext(
        user_message="hi",
        bot_response="hello",
        intent="greeting",
        confidence=0.9,
        action="ask",
        state="greeting",
        next_state="spin_situation",
        extracted_data={},
    )
    cw.add_turn(turn)
    cw.episodic_memory.record_successful_close(turn, 1, action_before="ask")

    data = cw.to_dict()
    restored = ContextWindow.from_dict(data)
    assert len(restored.turns) == 1
    assert restored.turns[0].user_message == "hi"
    assert len(restored.episodic_memory.episodes) == 1
    assert restored.episodic_memory.episodes[0].episode_type == EpisodeType.SUCCESSFUL_CLOSE


def test_context_window_accepts_list_format():
    cw = ContextWindow(max_size=2)
    cw.add_turn_from_dict(
        user_message="u",
        bot_response="b",
        intent="greeting",
        confidence=0.5,
        action="ask",
        state="greeting",
        next_state="spin_situation",
    )
    compact = cw.to_dict()["context_window"]

    restored = ContextWindow.from_dict(compact)
    assert len(restored.turns) == 1
    assert restored.turns[0].bot_response == "b"


def test_metrics_roundtrip_with_timestamps():
    metrics = ConversationMetrics("conv-1")
    metrics.record_turn("spin_situation", "greeting")
    metrics.record_lead_score(10, "cold", "signal")
    metrics.record_objection("price", resolved=False, attempts=1)
    metrics.set_outcome(ConversationOutcome.SOFT_CLOSE)

    data = metrics.to_dict()
    restored = ConversationMetrics.from_dict(data)
    assert restored.turns == metrics.turns
    assert restored.outcome == ConversationOutcome.SOFT_CLOSE
    assert restored.lead_score_history[0]["score"] == 10


def test_history_compactor_incremental_llm():
    history = _mk_history(6)
    llm = DummyLLM()
    prev_compact = {"summary": ["old"]}
    prev_meta = {"compacted_turns": 1}

    compact, meta = HistoryCompactor.compact(
        history_full=history,
        history_tail_size=4,
        previous_compact=prev_compact,
        previous_meta=prev_meta,
        llm=llm,
    )
    assert compact["summary"] == ["ok"]
    assert meta["compacted_turns"] == 2  # 6 total, tail 4 => 2 compacted
    assert "Previous compact" in llm.last_prompt


def test_history_compactor_fallback():
    history = _mk_history(5)
    compact, meta = HistoryCompactor.compact(
        history_full=history,
        history_tail_size=4,
        previous_compact=None,
        llm=None,
        fallback_context={"collected_data": {"company": "acme"}},
    )
    assert "company: acme" in compact["key_facts"]
    assert meta["compacted_turns"] == 1


def test_local_snapshot_buffer_persistence(tmp_path):
    path = tmp_path / "buffer.sqlite"
    buffer1 = LocalSnapshotBuffer(db_path=str(path))
    buffer1.enqueue("s1", {"a": 1})

    buffer2 = LocalSnapshotBuffer(db_path=str(path))
    assert buffer2.get("s1") == {"a": 1}
    buffer2.enqueue("s1", {"a": 2})
    assert buffer1.get("s1") == {"a": 2}
    assert buffer2.count() == 1


def test_local_snapshot_buffer_last_flush_date(tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    assert buffer.last_flush_date is None
    buffer.last_flush_date = (2026, 2, 5)
    assert buffer.last_flush_date == (2026, 2, 5)


def test_local_snapshot_buffer_flush_lock(tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    assert buffer.try_flush_lock() is True
    assert buffer.try_flush_lock() is False
    buffer.release_flush_lock()
    assert buffer.try_flush_lock() is True


def test_session_lock_manager_exclusive(tmp_path):
    lock_dir = tmp_path / "locks"
    mgr = SessionLockManager(lock_dir=str(lock_dir))
    session_id = "sess-1"

    lock_path = mgr._lock_path(session_id)
    with mgr.lock(session_id):
        handle = open(lock_path, "a", encoding="utf-8")
        try:
            try:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                locked = False
        finally:
            handle.close()
        assert locked is False


def test_session_manager_cleanup_expired_enqueues_snapshot(mock_llm, tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    manager = SessionManager(ttl_seconds=0, snapshot_buffer=buffer)
    _ = manager.get_or_create("sess-expired", llm=mock_llm, client_id="client-expired")

    removed = manager.cleanup_expired()
    assert removed == 1
    assert buffer.count() == 1


def test_session_manager_flush_not_before_hour(mock_llm, tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    saved = {}

    def save_snapshot(sid, snapshot):
        saved[sid] = snapshot

    fake_time = time.struct_time((2026, 2, 5, 22, 59, 0, 0, 0, -1))
    manager = SessionManager(
        save_snapshot=save_snapshot,
        snapshot_buffer=buffer,
        flush_hour=23,
        time_provider=lambda: fake_time,
    )

    buffer.enqueue("s1", {"conversation_id": "s1"})
    manager._maybe_flush_batch()
    assert saved == {}
    assert buffer.count() == 1


def test_salesbot_snapshot_restores_compact_and_tail(mock_llm, tmp_path):
    bot = SalesBot(llm=mock_llm, client_id="client-xyz")
    bot.history = _mk_history(6)
    snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)

    tail = _mk_history(4)
    restored = SalesBot.from_snapshot(snapshot, llm=mock_llm, history_tail=tail)
    assert restored.history == tail
    assert restored.history_compact is not None
    assert restored.history_compact_meta is not None
    assert restored.client_id == "client-xyz"


def test_snapshot_buffer_no_mix_between_sessions(tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    buffer.enqueue("s1", {"conversation_id": "s1", "client_id": "c1"})
    buffer.enqueue("s2", {"conversation_id": "s2", "client_id": "c2"})

    s1 = buffer.get("s1")
    s2 = buffer.get("s2")
    assert s1["client_id"] == "c1"
    assert s2["client_id"] == "c2"
    assert s1["conversation_id"] != s2["conversation_id"]


def test_snapshot_buffer_allows_same_session_for_different_clients(tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    buffer.enqueue("same", {"conversation_id": "same", "client_id": "c1", "v": 1})
    buffer.enqueue("same", {"conversation_id": "same", "client_id": "c2", "v": 2})

    assert buffer.count() == 2
    assert buffer.get("same", client_id="c1")["v"] == 1
    assert buffer.get("same", client_id="c2")["v"] == 2
    assert buffer.get("same") is None  # Ambiguous without client_id


def test_session_manager_cache_isolated_by_client_id(mock_llm, tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    manager = SessionManager(snapshot_buffer=buffer)

    bot_c1 = manager.get_or_create("shared-sid", llm=mock_llm, client_id="c1")
    bot_c2 = manager.get_or_create("shared-sid", llm=mock_llm, client_id="c2")

    assert bot_c1 is not bot_c2
    assert bot_c1.client_id == "c1"
    assert bot_c2.client_id == "c2"


def test_session_manager_flush_uses_tenant_aware_storage_key(tmp_path):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    saved = {}

    def save_snapshot(sid, snapshot):
        saved[sid] = snapshot

    fake_time = time.struct_time((2026, 2, 5, 23, 1, 0, 0, 0, -1))
    manager = SessionManager(
        save_snapshot=save_snapshot,
        snapshot_buffer=buffer,
        flush_hour=23,
        time_provider=lambda: fake_time,
    )

    buffer.enqueue("same", {"conversation_id": "same", "client_id": "c1"})
    buffer.enqueue("same", {"conversation_id": "same", "client_id": "c2"})

    manager._maybe_flush_batch()
    assert "c1::same" in saved
    assert "c2::same" in saved
    assert buffer.count() == 0


def test_session_manager_client_id_mismatch_skips_restore(tmp_path, mock_llm):
    buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
    snapshot = {"conversation_id": "s1", "client_id": "c1", "history": []}
    buffer.enqueue("s1", snapshot, client_id="c1")

    manager = SessionManager(snapshot_buffer=buffer)
    bot = manager.get_or_create("s1", llm=mock_llm, client_id="c2")

    assert bot.client_id == "c2"
    assert buffer.get("s1", client_id="c1") is not None
