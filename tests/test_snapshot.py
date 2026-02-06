"""Tests for snapshot serialization/deserialization."""

import time

from src.state_machine import StateMachine, CircularFlowManager
from src.conversation_guard import ConversationGuard
from src.lead_scoring import LeadScorer
from src.bot import SalesBot
from src.session_manager import SessionManager
from src.snapshot_buffer import LocalSnapshotBuffer


class TestCircularFlowManagerSnapshot:
    def test_roundtrip(self):
        cfm = CircularFlowManager()
        cfm.record_go_back("spin", "greeting")
        cfm.record_go_back("presentation", "spin")

        data = cfm.to_dict()
        restored = CircularFlowManager.from_dict(data)

        assert restored.goback_count == cfm.goback_count
        assert restored.goback_history == cfm.goback_history


class TestStateMachineSnapshot:
    def test_roundtrip(self):
        sm = StateMachine()
        sm.state = "spin_situation"
        sm.current_phase = "spin"
        sm.collected_data = {"company_size": 10}

        data = sm.to_dict()
        restored = StateMachine.from_dict(data)

        assert restored.state == "spin_situation"
        assert restored.current_phase == "spin"
        assert restored.collected_data == {"company_size": 10}


class TestConversationGuardSnapshot:
    def test_roundtrip_with_elapsed_time(self):
        guard = ConversationGuard()
        guard.check("greeting", "hello", {})
        guard.check("spin_situation", "10 people", {})

        time.sleep(0.05)

        data = guard.to_dict()
        restored = ConversationGuard.from_dict(data)

        assert restored.turn_count == 2
        assert len(restored.state_history) == 2


class TestLeadScorerSnapshot:
    def test_roundtrip_with_signals(self):
        scorer = LeadScorer()
        scorer.add_signal("general_interest")
        scorer.add_signal("explicit_problem")

        data = scorer.to_dict()
        restored = LeadScorer.from_dict(data)

        assert restored.current_score == scorer.current_score
        assert len(restored.signals_history) == len(scorer.signals_history)


class TestSalesBotSnapshot:
    def test_full_roundtrip(self, mock_llm):
        bot = SalesBot(llm=mock_llm, flow_name="bant", client_id="client-1")
        bot.conversation_id = "test-123"

        bot.state_machine.state = "spin_problem"
        bot.state_machine.collected_data = {"company_size": 50}
        bot.guard.check("spin_problem", "test", {})
        bot.lead_scorer.add_signal("explicit_problem")

        snapshot = bot.to_snapshot()
        restored = SalesBot.from_snapshot(snapshot, llm=mock_llm, history_tail=[])

        assert restored.conversation_id == "test-123"
        assert restored.client_id == "client-1"
        assert restored._flow.name == "bant"
        assert restored.state_machine.state == "spin_problem"
        assert restored.state_machine.collected_data == {"company_size": 50}
        assert restored.guard.turn_count == bot.guard.turn_count

    def test_snapshot_format_matches_integration_spec(self, mock_llm):
        bot = SalesBot(llm=mock_llm)
        snapshot = bot.to_snapshot()

        assert "version" in snapshot
        assert "conversation_id" in snapshot
        assert "flow_name" in snapshot
        assert "state_machine" in snapshot
        assert "context_window" in snapshot

        assert isinstance(snapshot["context_window"], list)
        assert "remaining" in snapshot["state_machine"]["circular_flow"]

        signals = snapshot["lead_scorer"]["signals_history"]
        assert isinstance(signals, list)
        if signals:
            assert isinstance(signals[0], str)

    def test_compaction_snapshot_has_no_tail(self, mock_llm):
        bot = SalesBot(llm=mock_llm)
        bot.history = [
            {"user": "u1", "bot": "b1"},
            {"user": "u2", "bot": "b2"},
            {"user": "u3", "bot": "b3"},
            {"user": "u4", "bot": "b4"},
            {"user": "u5", "bot": "b5"},
        ]

        snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
        assert "history_compact" in snapshot
        assert snapshot["history"] == []


class TestSessionManager:
    def test_cache_hit(self, mock_llm, tmp_path):
        buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
        manager = SessionManager(snapshot_buffer=buffer)
        bot1 = manager.get_or_create("sess-1", llm=mock_llm, client_id="client-1")
        bot2 = manager.get_or_create("sess-1", llm=mock_llm, client_id="client-1")

        assert bot1 is bot2

    def test_restore_from_snapshot_with_tail(self, mock_llm, tmp_path):
        bot = SalesBot(llm=mock_llm, client_id="client-2")
        bot.conversation_id = "sess-2"
        bot.state_machine.state = "presentation"
        snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)

        storage = {"client-2::sess-2": snapshot}
        tail = [{"user": "uX", "bot": "bX"}]

        buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
        manager = SessionManager(
            load_snapshot=lambda sid: storage.get(sid),
            load_history_tail=lambda sid, n: tail,
            snapshot_buffer=buffer,
        )

        restored = manager.get_or_create("sess-2", llm=mock_llm, client_id="client-2")
        assert restored.state_machine.state == "presentation"
        assert restored.history == tail

    def test_batch_flush_after_23(self, mock_llm, tmp_path):
        buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
        saved = {}

        def save_snapshot(sid, snapshot):
            saved[sid] = snapshot

        fake_time = time.struct_time((2026, 2, 5, 23, 5, 0, 0, 0, -1))

        manager = SessionManager(
            save_snapshot=save_snapshot,
            snapshot_buffer=buffer,
            flush_hour=23,
            time_provider=lambda: fake_time,
        )

        buffer.enqueue("s1", {"conversation_id": "s1"})
        buffer.enqueue("s2", {"conversation_id": "s2"})

        manager._maybe_flush_batch()
        assert "s1" in saved and "s2" in saved
        assert buffer.count() == 0

    def test_restore_from_local_buffer_consumes_snapshot(self, mock_llm, tmp_path):
        buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))

        bot = SalesBot(llm=mock_llm, client_id="client-3")
        bot.conversation_id = "s1"
        snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
        buffer.enqueue("s1", snapshot, client_id="client-3")

        manager = SessionManager(
            snapshot_buffer=buffer,
            load_history_tail=lambda sid, n: [],
        )

        _ = manager.get_or_create("s1", llm=mock_llm, client_id="client-3")
        assert buffer.get("s1", client_id="client-3") is None

    def test_named_config_applies_on_new_session_creation(self, mock_llm, tmp_path):
        buffer = LocalSnapshotBuffer(db_path=str(tmp_path / "buffer.sqlite"))
        manager = SessionManager(snapshot_buffer=buffer)

        bot = manager.get_or_create(
            "sess-config",
            llm=mock_llm,
            client_id="client-4",
            flow_name="spin_selling",
            config_name="tenant_alpha",
        )

        assert bot._config.name == "tenant_alpha"
        assert bot.state_machine._config.name == "tenant_alpha"
