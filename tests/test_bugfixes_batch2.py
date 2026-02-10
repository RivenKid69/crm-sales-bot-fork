"""
Тесты для исправленных багов (Batch 2).

Покрывает:
1. Потеря trace при fallback к tier_1
2. Перезапись данных в ContextEnvelope
3. Singleton игнорирует параметры
4. Decay без end_turn()
5. DAG majority edge case
6. Засорение истории frustration
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# =============================================================================
# 1. Trace Propagation in Fallback Tests
# =============================================================================

class TestTracePropagationInFallback:
    """Тесты для сохранения trace при fallback к tier_1."""

    def test_get_static_tier_2_options_passes_trace_to_tier_1(self):
        """_get_static_tier_2_options передаёт trace в _tier_1_rephrase."""
        from src.fallback_handler import FallbackHandler
        from src.conditions.trace import EvaluationTrace

        handler = FallbackHandler()
        trace = EvaluationTrace(rule_name="test_rule")

        # Мокаем _tier_1_rephrase чтобы проверить что trace передаётся
        with patch.object(handler, '_tier_1_rephrase') as mock_tier_1:
            mock_tier_1.return_value = MagicMock()

            # Вызываем _get_static_tier_2_options для состояния без шаблона
            handler._get_static_tier_2_options(
                state="nonexistent_state",
                context={},
                trace=trace
            )

            # Проверяем что _tier_1_rephrase вызван с trace
            mock_tier_1.assert_called_once()
            call_kwargs = mock_tier_1.call_args
            assert call_kwargs.kwargs.get('trace') is trace or \
                   (len(call_kwargs.args) >= 3 and call_kwargs.args[2] is trace) or \
                   call_kwargs[1].get('trace') is trace

    def test_trace_not_lost_in_fallback_chain(self):
        """Trace сохраняется через всю цепочку fallback."""
        from src.fallback_handler import FallbackHandler, FallbackResponse
        from src.conditions.trace import EvaluationTrace

        handler = FallbackHandler()
        trace = EvaluationTrace(rule_name="test_rule")

        # Тестируем _get_static_tier_2_options напрямую
        # когда для состояния нет шаблона, должен fallback к tier_1
        response = handler._get_static_tier_2_options(
            state="unknown_state_xyz",
            context={},
            trace=trace
        )

        # Response должен содержать trace
        assert isinstance(response, FallbackResponse)
        assert response.trace is trace

# =============================================================================
# 2. ContextEnvelope Data Priority Tests
# =============================================================================

class TestContextEnvelopeDataPriority:
    """Тесты для приоритета данных в ContextEnvelope."""

    def test_intent_history_from_state_machine_not_overwritten(self):
        """intent_history от IntentTracker не перезаписывается context_window."""
        from src.context_envelope import ContextEnvelopeBuilder, ContextEnvelope
        from unittest.mock import MagicMock

        # Создаём mock state_machine с intent_tracker
        sm = MagicMock()
        sm.state = "spin_situation"
        sm.collected_data = {}

        tracker = MagicMock()
        tracker.last_intent = "greeting"
        tracker.turn_number = 5
        tracker.get_recent_intents.return_value = ["intent_from_tracker_1", "intent_from_tracker_2"]
        tracker.objection_total.return_value = 3
        tracker.objection_consecutive.return_value = 1

        sm.intent_tracker = tracker

        # Создаём mock context_window
        cw = MagicMock()
        cw.get_intent_history.return_value = ["intent_from_cw_1", "intent_from_cw_2"]
        cw.get_objection_count.return_value = 10  # Другое значение
        cw.get_action_history.return_value = []
        cw.get_positive_count.return_value = 0
        cw.get_question_count.return_value = 0
        cw.get_unclear_count.return_value = 0
        cw.detect_oscillation.return_value = False
        cw.detect_stuck_pattern.return_value = False
        cw.detect_repeated_question.return_value = False
        cw.get_confidence_trend.return_value = "stable"
        cw.get_average_confidence.return_value = 0.8
        cw.__len__ = MagicMock(return_value=5)
        cw.get_last_turn.return_value = None
        cw.get_structured_context.return_value = {}
        cw.get_episodic_context.return_value = {"total_objections": 20}
        cw.get_momentum.return_value = 0

        builder = ContextEnvelopeBuilder(
            state_machine=sm,
            context_window=cw,
        )

        envelope = builder.build()

        # Данные от IntentTracker должны иметь приоритет
        assert envelope.intent_history == ["intent_from_tracker_1", "intent_from_tracker_2"]
        assert envelope.objection_count == 1  # От tracker, не от cw
        assert envelope.total_objections == 3  # От tracker, не от cw (20)

    def test_context_window_used_when_no_state_machine(self):
        """context_window используется когда state_machine отсутствует."""
        from src.context_envelope import ContextEnvelopeBuilder
        from unittest.mock import MagicMock

        cw = MagicMock()
        cw.get_intent_history.return_value = ["intent_from_cw"]
        cw.get_objection_count.return_value = 5
        cw.get_action_history.return_value = []
        cw.get_positive_count.return_value = 0
        cw.get_question_count.return_value = 0
        cw.get_unclear_count.return_value = 0
        cw.detect_oscillation.return_value = False
        cw.detect_stuck_pattern.return_value = False
        cw.detect_repeated_question.return_value = False
        cw.get_confidence_trend.return_value = "stable"
        cw.get_average_confidence.return_value = 0.8
        cw.__len__ = MagicMock(return_value=5)
        cw.get_last_turn.return_value = MagicMock(
            next_state="test_state",
            state="prev_state",
            action="test_action",
            intent="test_intent",
            confidence=0.9
        )
        cw.get_structured_context.return_value = {}
        cw.get_episodic_context.return_value = {"total_objections": 10}
        cw.get_momentum.return_value = 0

        builder = ContextEnvelopeBuilder(
            state_machine=None,
            context_window=cw,
        )

        envelope = builder.build()

        # Данные от context_window должны использоваться
        assert envelope.intent_history == ["intent_from_cw"]
        assert envelope.objection_count == 5
        assert envelope.total_objections == 10

# =============================================================================
# 3. Singleton Parameter Warning Tests
# =============================================================================

class TestSingletonParameterWarning:
    """Тесты для предупреждения о параметрах singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        from src.classifier.cascade import reset_cascade_classifier
        reset_cascade_classifier()

    def teardown_method(self):
        """Reset singleton after each test."""
        from src.classifier.cascade import reset_cascade_classifier
        reset_cascade_classifier()

    def test_first_call_creates_with_parameters(self):
        """Первый вызов создаёт экземпляр с переданными параметрами."""
        from src.classifier.cascade import get_cascade_classifier, reset_cascade_classifier

        classifier = get_cascade_classifier(enable_semantic=False)
        assert classifier.enable_semantic is False

    def test_second_call_with_different_params_logs_warning(self):
        """Второй вызов с другими параметрами логирует warning."""
        from src.classifier.cascade import get_cascade_classifier, reset_cascade_classifier

        # Первый вызов
        classifier1 = get_cascade_classifier(enable_semantic=False)

        # Второй вызов с другими параметрами
        with patch('classifier.cascade.logger') as mock_logger:
            classifier2 = get_cascade_classifier(enable_semantic=True)

            # Должен быть warning
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "different parameters" in str(call_args).lower() or \
                   "existing singleton" in str(call_args).lower()

        # Возвращается тот же экземпляр
        assert classifier1 is classifier2
        # С оригинальными параметрами
        assert classifier2.enable_semantic is False

    def test_same_params_no_warning(self):
        """Повторный вызов с теми же параметрами не логирует warning."""
        from src.classifier.cascade import get_cascade_classifier, reset_cascade_classifier

        classifier1 = get_cascade_classifier(enable_semantic=True)

        with patch('classifier.cascade.logger') as mock_logger:
            classifier2 = get_cascade_classifier(enable_semantic=True)

            # Warning не должен быть
            mock_logger.warning.assert_not_called()

        assert classifier1 is classifier2

    def test_reset_allows_new_params(self):
        """После reset можно создать с новыми параметрами."""
        from src.classifier.cascade import get_cascade_classifier, reset_cascade_classifier

        classifier1 = get_cascade_classifier(enable_semantic=False)
        assert classifier1.enable_semantic is False

        reset_cascade_classifier()

        classifier2 = get_cascade_classifier(enable_semantic=True)
        assert classifier2.enable_semantic is True
        assert classifier1 is not classifier2

# =============================================================================
# 4. Lead Scoring Decay Contract Tests
# =============================================================================

class TestLeadScoringDecayContract:
    """Тесты для контракта end_turn() в LeadScorer."""

    def test_decay_applied_once_per_turn(self):
        """Decay применяется только один раз за ход."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer._raw_score = 100.0
        scorer.current_score = 100

        # Первый вызов apply_turn_decay
        scorer.apply_turn_decay()
        score_after_first = scorer.current_score

        # Второй вызов без end_turn - decay НЕ должен применяться
        scorer.apply_turn_decay()
        score_after_second = scorer.current_score

        assert score_after_first == score_after_second

    def test_end_turn_enables_next_decay(self):
        """end_turn() позволяет применить decay в следующем ходу."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer._raw_score = 100.0
        scorer.current_score = 100

        # Первый ход
        scorer.apply_turn_decay()
        score_after_first = scorer.current_score

        # Завершаем ход
        scorer.end_turn()

        # Второй ход - decay должен применяться
        scorer.apply_turn_decay()
        score_after_second = scorer.current_score

        assert score_after_second < score_after_first

    def test_warning_logged_without_end_turn(self):
        """Warning логируется при множественных вызовах без end_turn."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer._raw_score = 50.0
        scorer.current_score = 50

        # Первый вызов
        scorer.apply_turn_decay()

        # Второй и третий вызовы без end_turn
        with patch('lead_scoring.logger') as mock_logger:
            scorer.apply_turn_decay()  # _turns_without_end_turn = 1
            scorer.apply_turn_decay()  # _turns_without_end_turn = 2, should warn

            # Warning должен быть вызван после 2+ пропущенных end_turn
            assert mock_logger.warning.called

    def test_end_turn_resets_warning_counter(self):
        """end_turn() сбрасывает счётчик предупреждений."""
        from src.lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer._turns_without_end_turn = 5

        scorer.end_turn()

        assert scorer._turns_without_end_turn == 0

# =============================================================================
# 5. DAG Majority Edge Case Tests
# =============================================================================

class TestDAGMajorityEdgeCase:
    """Тесты для edge cases в DAG majority стратегии."""

    def test_majority_with_2_branches_warns(self):
        """MAJORITY с 2 ветками логирует warning."""
        from src.dag.sync_points import SyncPointManager, SyncStrategy

        manager = SyncPointManager()

        with patch('dag.sync_points.logger') as mock_logger:
            manager.register(
                sync_id="test_sync",
                expected_branches=["branch_a", "branch_b"],
                strategy=SyncStrategy.MAJORITY
            )

            # Warning должен быть о том что MAJORITY = ALL_COMPLETE для 2 веток
            assert mock_logger.warning.called
            call_args = str(mock_logger.warning.call_args)
            assert "2 branches" in call_args or "ALL_COMPLETE" in call_args

    def test_majority_with_3_branches_no_warning(self):
        """MAJORITY с 3+ ветками не логирует warning."""
        from src.dag.sync_points import SyncPointManager, SyncStrategy

        manager = SyncPointManager()

        with patch('dag.sync_points.logger') as mock_logger:
            manager.register(
                sync_id="test_sync",
                expected_branches=["a", "b", "c"],
                strategy=SyncStrategy.MAJORITY
            )

            # Warning НЕ должен быть для 3 веток
            # (debug может быть, но warning - нет)
            warning_calls = [c for c in mock_logger.method_calls if 'warning' in str(c)]
            assert len(warning_calls) == 0

    def test_majority_requires_more_than_half(self):
        """MAJORITY требует строго больше половины."""
        from src.dag.sync_points import SyncPointManager, SyncStrategy
        from src.dag.models import DAGExecutionContext

        manager = SyncPointManager()
        ctx = DAGExecutionContext(primary_state="test")

        manager.register(
            sync_id="test_sync",
            expected_branches=["a", "b", "c", "d"],  # 4 ветки
            strategy=SyncStrategy.MAJORITY
        )

        # 2 из 4 = 50% - НЕ majority
        manager.arrive("test_sync", "a", ctx)
        result = manager.arrive("test_sync", "b", ctx)
        assert result.is_synced is False

        # 3 из 4 = 75% - majority
        result = manager.arrive("test_sync", "c", ctx)
        assert result.is_synced is True

# =============================================================================
# 6. Frustration History Cleanup Tests
# =============================================================================

class TestFrustrationHistoryCleanup:
    """Тесты для очистки истории frustration от нулевых записей."""

    def test_neutral_tone_at_zero_level_no_history_entry(self):
        """Нейтральный тон при нулевом уровне не создаёт запись в истории."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()
        assert tracker.level == 0

        # NEUTRAL есть в FRUSTRATION_DECAY с весом 1
        # Но при level=0 снижение на 1 даёт max(0, 0-1) = 0
        # delta = 0, поэтому запись не создаётся
        tracker.update(Tone.NEUTRAL)

        # История должна быть пустой (delta = 0)
        assert len(tracker.history) == 0

    def test_frustration_tone_creates_history_entry(self):
        """Тон влияющий на frustration создаёт запись."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Тон который увеличивает frustration
        tracker.update(Tone.FRUSTRATED)

        # Должна быть одна запись с delta > 0
        assert len(tracker.history) == 1
        assert tracker.history[0]["delta"] > 0

    def test_decay_tone_creates_history_entry(self):
        """Тон вызывающий decay создаёт запись если level меняется."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Сначала повышаем frustration
        tracker.update(Tone.FRUSTRATED)
        initial_history_len = len(tracker.history)

        # Теперь decay
        tracker.update(Tone.POSITIVE)

        # Должна быть новая запись
        assert len(tracker.history) == initial_history_len + 1
        assert tracker.history[-1]["delta"] < 0

    def test_decay_at_zero_no_history_entry(self):
        """Decay при нулевом уровне не создаёт запись."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()
        assert tracker.level == 0

        # Decay при нулевом уровне - ничего не меняется
        tracker.update(Tone.POSITIVE)

        # История должна быть пустой
        assert len(tracker.history) == 0

    def test_history_only_contains_meaningful_changes(self):
        """История содержит только значимые изменения (delta != 0)."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Серия тонов (учитывая что NEUTRAL в FRUSTRATION_DECAY с весом 1):
        # 1. NEUTRAL при level=0: max(0, 0-1)=0, delta=0 -> NO entry
        # 2. FRUSTRATED: 0+3=3, delta=3 -> entry
        # 3. NEUTRAL при level=3: max(0, 3-1)=2, delta=-1 -> entry (decay!)
        # 4. POSITIVE при level=2: max(0, 2-2)=0, delta=-2 -> entry
        # 5. NEUTRAL при level=0: max(0, 0-1)=0, delta=0 -> NO entry

        tracker.update(Tone.NEUTRAL)      # delta = 0 at level 0, no entry
        tracker.update(Tone.FRUSTRATED)   # delta = +3, entry
        tracker.update(Tone.NEUTRAL)      # delta = -1 (decay), entry
        tracker.update(Tone.POSITIVE)     # delta = -2 (decay), entry
        tracker.update(Tone.NEUTRAL)      # delta = 0 at level 0, no entry

        # Должно быть 3 записи (все с delta != 0)
        assert len(tracker.history) == 3
        assert all(entry["delta"] != 0 for entry in tracker.history)

        # Проверяем структуру записей
        assert tracker.history[0]["delta"] == 3    # FRUSTRATED
        assert tracker.history[1]["delta"] == -1   # NEUTRAL decay
        assert tracker.history[2]["delta"] == -2   # POSITIVE decay
