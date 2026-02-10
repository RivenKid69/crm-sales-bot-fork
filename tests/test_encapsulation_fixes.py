# tests/test_encapsulation_fixes.py

"""
Targeted tests for Issues #4-#7 encapsulation fixes.

Covers:
- FrozenDict immutability
- deep_freeze_dict recursion
- GoBackInfo frozen snapshot
- IntentTrackerReadOnly proxy
- TenantConfig frozen
- ContextSnapshot new fields (state_before_objection, valid_states, go_back_info)
- DataUpdateCollisionError (strict mode)
- Blackboard public properties (intent_tracker, is_turn_active, data_update_audit)
- should_skip_objection_recording shared function (SSOT)
- IIntentTrackerReader / IIntentTracker protocol split
"""

import pytest
from unittest.mock import Mock, MagicMock, PropertyMock
from typing import Optional

# =============================================================================
# FrozenDict Tests
# =============================================================================

class TestFrozenDict:
    """Test FrozenDict immutability."""

    def test_read_operations_work(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1, "b": 2, "c": 3})
        assert fd["a"] == 1
        assert fd.get("b") == 2
        assert fd.get("missing", 42) == 42
        assert len(fd) == 3
        assert "a" in fd
        assert "z" not in fd
        assert list(fd.keys()) == ["a", "b", "c"]
        assert list(fd.values()) == [1, 2, 3]
        assert list(fd.items()) == [("a", 1), ("b", 2), ("c", 3)]

    def test_isinstance_dict(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"x": 1})
        assert isinstance(fd, dict)

    def test_setitem_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError, match="FrozenDict does not support mutation"):
            fd["a"] = 2

    def test_delitem_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            del fd["a"]

    def test_update_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd.update({"b": 2})

    def test_pop_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd.pop("a")

    def test_popitem_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd.popitem()

    def test_clear_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd.clear()

    def test_setdefault_existing_key_ok(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        assert fd.setdefault("a", 99) == 1

    def test_setdefault_new_key_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd.setdefault("z", 99)

    def test_ior_blocked(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        with pytest.raises(TypeError):
            fd |= {"b": 2}

    def test_mutable_copy_via_dict(self):
        """dict(frozen) creates a mutable copy."""
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        mutable = dict(fd)
        mutable["b"] = 2
        assert "b" in mutable
        assert "b" not in fd

    def test_repr(self):
        from src.blackboard.models import FrozenDict
        fd = FrozenDict({"a": 1})
        assert "FrozenDict" in repr(fd)

class TestDeepFreezeDict:
    """Test recursive dict freezing."""

    def test_shallow(self):
        from src.blackboard.models import deep_freeze_dict, FrozenDict
        result = deep_freeze_dict({"a": 1, "b": "hello"})
        assert isinstance(result, FrozenDict)
        assert result["a"] == 1

    def test_nested(self):
        from src.blackboard.models import deep_freeze_dict, FrozenDict
        result = deep_freeze_dict({"outer": {"inner": {"deep": 42}}})
        assert isinstance(result, FrozenDict)
        assert isinstance(result["outer"], FrozenDict)
        assert isinstance(result["outer"]["inner"], FrozenDict)
        assert result["outer"]["inner"]["deep"] == 42

    def test_nested_mutation_blocked(self):
        from src.blackboard.models import deep_freeze_dict
        result = deep_freeze_dict({"a": {"b": 1}})
        with pytest.raises(TypeError):
            result["a"]["b"] = 999

    def test_lists_not_frozen(self):
        """Lists inside FrozenDict are NOT frozen (accepted limitation)."""
        from src.blackboard.models import deep_freeze_dict
        result = deep_freeze_dict({"items": [1, 2, 3]})
        result["items"].append(4)  # This should work
        assert 4 in result["items"]

    def test_already_frozen_not_double_wrapped(self):
        from src.blackboard.models import deep_freeze_dict, FrozenDict
        inner = FrozenDict({"x": 1})
        result = deep_freeze_dict({"a": inner})
        assert result["a"] is inner  # Same object, not re-wrapped

# =============================================================================
# GoBackInfo Tests
# =============================================================================

class TestGoBackInfo:
    """Test GoBackInfo frozen dataclass."""

    def test_creation(self):
        from src.blackboard.models import GoBackInfo
        info = GoBackInfo(
            target_state="spin_situation",
            limit_reached=False,
            remaining=2,
            goback_count=1,
            max_gobacks=3,
            history=(("spin_problem", "spin_situation"),),
        )
        assert info.target_state == "spin_situation"
        assert info.limit_reached is False
        assert info.remaining == 2
        assert info.goback_count == 1
        assert info.max_gobacks == 3

    def test_frozen(self):
        from src.blackboard.models import GoBackInfo
        info = GoBackInfo(
            target_state="s1", limit_reached=False,
            remaining=1, goback_count=0, max_gobacks=3,
        )
        with pytest.raises(AttributeError):
            info.target_state = "s2"

# =============================================================================
# IntentTrackerReadOnly Tests
# =============================================================================

class TestIntentTrackerReadOnly:
    """Test read-only proxy for IntentTracker."""

    def _make_tracker_mock(self):
        tracker = Mock()
        tracker.turn_number = 5
        tracker.prev_intent = "greet"
        tracker.last_intent = "ask_price"
        tracker.last_state = "spin_situation"
        tracker.history_length = 10
        tracker.objection_consecutive.return_value = 2
        tracker.objection_total.return_value = 4
        tracker.total_count.return_value = 3
        tracker.category_total.return_value = 7
        tracker.streak_count.return_value = 1
        tracker.category_streak.return_value = 2
        tracker.get_intents_by_category.return_value = ["a", "b"]
        tracker.get_recent_intents.return_value = ["ask_price", "greet"]
        return tracker

    def test_read_properties(self):
        from src.blackboard.models import IntentTrackerReadOnly
        tracker = self._make_tracker_mock()
        ro = IntentTrackerReadOnly(tracker)
        assert ro.turn_number == 5
        assert ro.prev_intent == "greet"
        assert ro.last_intent == "ask_price"
        assert ro.last_state == "spin_situation"
        assert ro.history_length == 10

    def test_read_methods(self):
        from src.blackboard.models import IntentTrackerReadOnly
        tracker = self._make_tracker_mock()
        ro = IntentTrackerReadOnly(tracker)
        assert ro.objection_consecutive() == 2
        assert ro.objection_total() == 4
        assert ro.total_count("greet") == 3
        assert ro.category_total("objection") == 7
        assert ro.streak_count("greet") == 1
        assert ro.category_streak("objection") == 2
        assert ro.get_intents_by_category("x") == ["a", "b"]
        assert ro.get_recent_intents(5) == ["ask_price", "greet"]

    def test_setattr_blocked(self):
        from src.blackboard.models import IntentTrackerReadOnly
        tracker = self._make_tracker_mock()
        ro = IntentTrackerReadOnly(tracker)
        with pytest.raises(AttributeError, match="immutable"):
            ro.turn_number = 99

    def test_no_record_method(self):
        """IntentTrackerReadOnly does NOT expose record()."""
        from src.blackboard.models import IntentTrackerReadOnly
        tracker = self._make_tracker_mock()
        ro = IntentTrackerReadOnly(tracker)
        assert not hasattr(ro, "record")

    def test_no_advance_turn_method(self):
        """IntentTrackerReadOnly does NOT expose advance_turn()."""
        from src.blackboard.models import IntentTrackerReadOnly
        tracker = self._make_tracker_mock()
        ro = IntentTrackerReadOnly(tracker)
        assert not hasattr(ro, "advance_turn")

# =============================================================================
# TenantConfig Frozen Tests
# =============================================================================

class TestTenantConfigFrozen:
    """Test TenantConfig is frozen (immutable)."""

    def test_creation(self):
        from src.blackboard.protocols import TenantConfig
        tc = TenantConfig(tenant_id="acme", bot_name="ACME Bot", tone="friendly")
        assert tc.tenant_id == "acme"
        assert tc.bot_name == "ACME Bot"
        assert tc.tone == "friendly"

    def test_frozen(self):
        from src.blackboard.protocols import TenantConfig
        tc = TenantConfig(tenant_id="acme")
        with pytest.raises(AttributeError):
            tc.tenant_id = "other"

    def test_default_values(self):
        from src.blackboard.protocols import TenantConfig
        tc = TenantConfig(tenant_id="t1")
        assert tc.bot_name == "Assistant"
        assert tc.tone == "professional"
        assert tc.features == {}
        assert tc.persona_limits_override is None

# =============================================================================
# Protocol Split Tests
# =============================================================================

class TestProtocolSplit:
    """Test IIntentTrackerReader / IIntentTracker protocol split."""

    def test_reader_protocol_exists(self):
        from src.blackboard.protocols import IIntentTrackerReader
        assert IIntentTrackerReader is not None

    def test_full_tracker_extends_reader(self):
        """IIntentTracker should extend IIntentTrackerReader (check via MRO)."""
        from src.blackboard.protocols import IIntentTracker, IIntentTrackerReader
        # Protocols with non-method members don't support issubclass();
        # check via __mro__ instead
        assert IIntentTrackerReader in IIntentTracker.__mro__

    def test_state_before_objection_in_protocol(self):
        """IStateMachine protocol should have state_before_objection."""
        from src.blackboard.protocols import IStateMachine
        # Check the protocol has the property defined
        assert hasattr(IStateMachine, 'state_before_objection')

# =============================================================================
# DataUpdateCollisionError Tests
# =============================================================================

class TestDataUpdateCollision:
    """Test strict collision detection in propose_data_update/propose_flag_set."""

    def _make_blackboard(self, strict=True):
        """Create a minimal blackboard for collision testing."""
        from src.blackboard.blackboard import DialogueBlackboard
        sm = Mock()
        sm.state = "greeting"
        sm.collected_data = {}
        sm.current_phase = None
        sm.last_action = None
        sm.state_before_objection = None
        sm.intent_tracker = None

        flow_config = Mock()
        flow_config.states = {"greeting": {}}
        flow_config.to_dict.return_value = {}
        flow_config.state_to_phase = {}

        bb = DialogueBlackboard(sm, flow_config, strict_data_updates=strict)
        return bb

    def test_strict_mode_raises_on_data_collision(self):
        from src.blackboard.blackboard import DataUpdateCollisionError
        bb = self._make_blackboard(strict=True)
        bb.propose_data_update("name", "Alice", source_name="SourceA")
        with pytest.raises(DataUpdateCollisionError, match="name"):
            bb.propose_data_update("name", "Bob", source_name="SourceB")

    def test_strict_mode_raises_on_flag_collision(self):
        from src.blackboard.blackboard import DataUpdateCollisionError
        bb = self._make_blackboard(strict=True)
        bb.propose_flag_set("ready", True, source_name="SourceA")
        with pytest.raises(DataUpdateCollisionError, match="ready"):
            bb.propose_flag_set("ready", False, source_name="SourceB")

    def test_non_strict_mode_allows_overwrite(self):
        bb = self._make_blackboard(strict=False)
        bb.propose_data_update("name", "Alice", source_name="SourceA")
        bb.propose_data_update("name", "Bob", source_name="SourceB")
        assert bb._data_updates["name"] == "Bob"

    def test_audit_trail_tracks_sources(self):
        bb = self._make_blackboard(strict=False)
        bb.propose_data_update("name", "Alice", source_name="DataCollector")
        audit = bb.data_update_audit
        assert audit["name"] == "DataCollector"

# =============================================================================
# Blackboard Public Properties Tests
# =============================================================================

class TestBlackboardPublicAPI:
    """Test new public properties on DialogueBlackboard."""

    def _make_blackboard(self):
        from src.blackboard.blackboard import DialogueBlackboard
        sm = Mock()
        sm.state = "greeting"
        sm.collected_data = {}
        sm.current_phase = None
        sm.last_action = None
        sm.state_before_objection = None

        tracker = Mock()
        tracker.turn_number = 1
        tracker.prev_intent = None
        tracker.last_intent = None
        tracker.last_state = None
        tracker.history_length = 0
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 0

        flow_config = Mock()
        flow_config.states = {"greeting": {}}
        flow_config.to_dict.return_value = {}
        flow_config.state_to_phase = {}

        bb = DialogueBlackboard(sm, flow_config, intent_tracker=tracker)
        return bb, tracker

    def test_intent_tracker_property(self):
        bb, tracker = self._make_blackboard()
        assert bb.intent_tracker is tracker

    def test_is_turn_active_before_begin_turn(self):
        bb, _ = self._make_blackboard()
        assert bb.is_turn_active is False

    def test_data_update_audit_empty_initially(self):
        bb, _ = self._make_blackboard()
        assert bb.data_update_audit == {}

# =============================================================================
# ContextSnapshot New Fields Tests
# =============================================================================

class TestContextSnapshotNewFields:
    """Test new fields added to ContextSnapshot."""

    def _make_snapshot(self, **overrides):
        from src.blackboard.models import ContextSnapshot, GoBackInfo, IntentTrackerReadOnly
        tracker = Mock()
        tracker.prev_intent = None
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 0

        defaults = dict(
            state="greeting",
            collected_data={},
            current_intent="greet",
            intent_tracker=IntentTrackerReadOnly(tracker),
            context_envelope=None,
            turn_number=1,
            persona="default",
            state_config={},
            flow_config={},
            state_to_phase={},
            state_before_objection=None,
            valid_states=frozenset({"greeting", "close"}),
            go_back_info=None,
        )
        defaults.update(overrides)
        return ContextSnapshot(**defaults)

    def test_state_before_objection_field(self):
        ctx = self._make_snapshot(state_before_objection="spin_situation")
        assert ctx.state_before_objection == "spin_situation"

    def test_valid_states_field(self):
        ctx = self._make_snapshot(valid_states=frozenset({"a", "b", "c"}))
        assert "a" in ctx.valid_states
        assert "z" not in ctx.valid_states

    def test_go_back_info_field(self):
        from src.blackboard.models import GoBackInfo
        info = GoBackInfo(
            target_state="s1", limit_reached=False,
            remaining=2, goback_count=0, max_gobacks=3,
        )
        ctx = self._make_snapshot(go_back_info=info)
        assert ctx.go_back_info is info
        assert ctx.go_back_info.target_state == "s1"

    def test_snapshot_is_frozen(self):
        ctx = self._make_snapshot()
        with pytest.raises(AttributeError):
            ctx.state = "other"

# =============================================================================
# Shared should_skip_objection_recording Tests
# =============================================================================

class TestSharedSkipObjectionRecording:
    """Test the SSOT function in intent_tracker.py."""

    def test_non_objection_returns_false(self):
        from src.intent_tracker import should_skip_objection_recording
        tracker = Mock()
        result = should_skip_objection_recording("greet", tracker, {})
        assert result is False

    def test_objection_under_limit_returns_false(self):
        from src.intent_tracker import should_skip_objection_recording
        tracker = Mock()
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 0
        result = should_skip_objection_recording("objection_price", tracker, {})
        assert result is False

    def test_objection_over_consecutive_limit_returns_true(self):
        from src.intent_tracker import should_skip_objection_recording
        tracker = Mock()
        tracker.objection_consecutive.return_value = 999
        tracker.objection_total.return_value = 0
        # Must use an actual objection intent name from YAML constants
        result = should_skip_objection_recording("objection_price", tracker, {})
        assert result is True

    def test_objection_over_total_limit_returns_true(self):
        from src.intent_tracker import should_skip_objection_recording
        tracker = Mock()
        tracker.objection_consecutive.return_value = 0
        tracker.objection_total.return_value = 999
        result = should_skip_objection_recording("objection_price", tracker, {})
        assert result is True
