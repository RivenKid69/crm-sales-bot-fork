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


class TestSerializationContract:
    """
    CI guard: ensures StateMachine serialization contract is complete.
    If you add a new field to __init__ and this test fails, you MUST
    add the field to _SNAPSHOT_FIELDS, _SNAPSHOT_NESTED, or _TRANSIENT_FIELDS.
    """

    def test_all_init_fields_declared(self):
        """Every instance var must be in exactly one field registry."""
        sm = StateMachine()
        all_instance_vars = set(vars(sm).keys())
        declared = (
            StateMachine._SNAPSHOT_FIELDS
            | StateMachine._SNAPSHOT_NESTED
            | StateMachine._TRANSIENT_FIELDS
        )
        undeclared = all_instance_vars - declared
        assert not undeclared, (
            f"Undeclared fields in StateMachine.__init__: {undeclared}. "
            f"Add to _SNAPSHOT_FIELDS (stateful), _SNAPSHOT_NESTED (has own to_dict), "
            f"or _TRANSIENT_FIELDS (reconstructed/transient)."
        )

    def test_to_dict_covers_all_snapshot_fields(self):
        """to_dict() output must include every declared snapshot field."""
        sm = StateMachine()
        serialized_keys = set(sm.to_dict().keys())
        expected = StateMachine._SNAPSHOT_FIELDS | StateMachine._SNAPSHOT_NESTED
        missing = expected - serialized_keys
        assert not missing, (
            f"to_dict() missing declared snapshot fields: {missing}. "
            f"Add these to the return dict in to_dict()."
        )

    def test_no_field_in_multiple_registries(self):
        """Each field must be in exactly one registry, not multiple."""
        overlap_sn = StateMachine._SNAPSHOT_FIELDS & StateMachine._SNAPSHOT_NESTED
        overlap_st = StateMachine._SNAPSHOT_FIELDS & StateMachine._TRANSIENT_FIELDS
        overlap_nt = StateMachine._SNAPSHOT_NESTED & StateMachine._TRANSIENT_FIELDS
        assert not (overlap_sn | overlap_st | overlap_nt), (
            f"Fields in multiple registries: {overlap_sn | overlap_st | overlap_nt}"
        )

    def test_from_dict_restores_all_snapshot_fields(self):
        """
        from_dict() must restore every _SNAPSHOT_FIELDS value to match to_dict().
        Catches the case where a field is in _SNAPSHOT_FIELDS and to_dict()
        but missing from from_dict() restoration logic.
        """
        sm = StateMachine()
        # Set every snapshot field to a non-default value
        sm.state = "presentation"
        sm.current_phase = "closing"
        sm.collected_data = {"key": "val"}
        sm.last_action = "test_action"
        sm._state_before_objection = "spin_problem"
        sm.in_disambiguation = True
        sm.disambiguation_context = {"opts": [1]}
        sm.pre_disambiguation_state = "greeting"
        sm.turns_since_last_disambiguation = 5

        data = sm.to_dict()
        restored = StateMachine.from_dict(data)

        for field in StateMachine._SNAPSHOT_FIELDS:
            assert getattr(restored, field) == getattr(sm, field), (
                f"from_dict() did not restore field '{field}': "
                f"expected {getattr(sm, field)!r}, got {getattr(restored, field)!r}"
            )


class TestStateMachineSnapshotRoundtrip:
    """Additional roundtrip tests for newly serialized fields."""

    def test_roundtrip_last_action(self):
        """last_action survives roundtrip."""
        sm = StateMachine()
        sm.last_action = "handle_objection_price"

        data = sm.to_dict()
        restored = StateMachine.from_dict(data)

        assert restored.last_action == "handle_objection_price"

    def test_roundtrip_state_before_objection(self):
        """_state_before_objection survives roundtrip."""
        sm = StateMachine()
        sm._state_before_objection = "spin_problem"

        data = sm.to_dict()
        restored = StateMachine.from_dict(data)

        assert restored._state_before_objection == "spin_problem"

    def test_backward_compat_old_snapshot(self):
        """Old snapshot (missing new keys) loads, fields default to None."""
        old_data = {
            "state": "greeting",
            "current_phase": None,
            "collected_data": {},
            "in_disambiguation": False,
            "disambiguation_context": None,
            "pre_disambiguation_state": None,
            "turns_since_last_disambiguation": 999,
        }
        restored = StateMachine.from_dict(old_data)

        assert restored.last_action is None
        assert restored._state_before_objection is None
        assert restored.state == "greeting"


class TestSalesBotSnapshotSync:
    """Tests for bot.last_action sync with state_machine.last_action."""

    def test_last_action_synced_after_restore(self, mock_llm):
        """bot.last_action == bot.state_machine.last_action after restore."""
        bot = SalesBot(llm=mock_llm, flow_name="bant")
        bot.last_action = "answer_with_pricing"
        bot.state_machine.last_action = "answer_with_pricing"

        snapshot = bot.to_snapshot()
        restored = SalesBot.from_snapshot(snapshot, llm=mock_llm, history_tail=[])

        assert restored.last_action == "answer_with_pricing"
        assert restored.state_machine.last_action == "answer_with_pricing"

    def test_state_before_objection_full_roundtrip(self, mock_llm):
        """Objection state survives full bot snapshot cycle."""
        bot = SalesBot(llm=mock_llm, flow_name="bant")
        bot.state_machine._state_before_objection = "spin_problem"
        bot.state_machine.state = "handle_objection"

        snapshot = bot.to_snapshot()
        restored = SalesBot.from_snapshot(snapshot, llm=mock_llm, history_tail=[])

        assert restored.state_machine._state_before_objection == "spin_problem"
        assert restored.state_machine.state == "handle_objection"


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
