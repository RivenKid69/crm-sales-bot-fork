"""
Тесты для исправленных багов.

Покрывает:
1. Circuit breaker half-open состояние
2. Frustration tracker - единственный экземпляр
3. Disambiguation path - фазы защиты
4. Fork stack - LIFO порядок
5. Lead scoring - turn-based decay
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm import VLLMClient, CircuitBreakerState, CircuitBreakerStatus, LLMStats


# =============================================================================
# 1. Circuit Breaker Half-Open Tests
# =============================================================================

class TestCircuitBreakerHalfOpen:
    """Тесты для half-open состояния circuit breaker."""

    def test_circuit_breaker_status_enum(self):
        """CircuitBreakerStatus содержит все состояния."""
        assert CircuitBreakerStatus.CLOSED == "closed"
        assert CircuitBreakerStatus.OPEN == "open"
        assert CircuitBreakerStatus.HALF_OPEN == "half_open"

    def test_initial_state_is_closed(self):
        """Начальное состояние - CLOSED."""
        state = CircuitBreakerState()
        assert state.status == CircuitBreakerStatus.CLOSED
        assert state.is_open is False
        assert state.half_open_request_in_flight is False

    def test_is_open_property_backward_compatibility(self):
        """is_open property работает для обратной совместимости."""
        state = CircuitBreakerState(status=CircuitBreakerStatus.OPEN)
        assert state.is_open is True

        state.status = CircuitBreakerStatus.CLOSED
        assert state.is_open is False

        state.status = CircuitBreakerStatus.HALF_OPEN
        assert state.is_open is False  # half-open != open

    def test_transition_to_open_after_threshold(self):
        """Circuit переходит в OPEN после достижения порога ошибок."""
        llm = VLLMClient(enable_retry=False)

        # Симулируем ошибки до порога
        for _ in range(llm.CIRCUIT_BREAKER_THRESHOLD):
            llm._record_failure()

        assert llm._circuit_breaker.status == CircuitBreakerStatus.OPEN

    def test_transition_to_half_open_after_timeout(self):
        """Circuit переходит в HALF_OPEN после истечения timeout."""
        llm = VLLMClient(enable_retry=False)

        # Открываем circuit
        for _ in range(llm.CIRCUIT_BREAKER_THRESHOLD):
            llm._record_failure()

        assert llm._circuit_breaker.status == CircuitBreakerStatus.OPEN

        # Устанавливаем timeout в прошлое
        llm._circuit_breaker.open_until = time.time() - 1

        # Проверяем - должен перейти в half-open
        result = llm._is_circuit_open()
        assert result is False  # Пропускаем probe request
        assert llm._circuit_breaker.status == CircuitBreakerStatus.HALF_OPEN
        assert llm._circuit_breaker.half_open_request_in_flight is True

    def test_half_open_blocks_subsequent_requests(self):
        """В HALF_OPEN блокируются все запросы кроме первого."""
        llm = VLLMClient(enable_retry=False)

        # Переводим в half-open
        llm._circuit_breaker.status = CircuitBreakerStatus.HALF_OPEN
        llm._circuit_breaker.half_open_request_in_flight = False

        # Первый запрос проходит
        assert llm._is_circuit_open() is False
        assert llm._circuit_breaker.half_open_request_in_flight is True

        # Второй запрос блокируется
        assert llm._is_circuit_open() is True

    def test_half_open_success_closes_circuit(self):
        """Успешный probe request закрывает circuit."""
        llm = VLLMClient(enable_retry=False)

        # Переводим в half-open
        llm._circuit_breaker.status = CircuitBreakerStatus.HALF_OPEN
        llm._circuit_breaker.half_open_request_in_flight = True
        llm._circuit_breaker.failures = 5

        # Успешный запрос
        llm._reset_failures()

        assert llm._circuit_breaker.status == CircuitBreakerStatus.CLOSED
        assert llm._circuit_breaker.failures == 0
        assert llm._circuit_breaker.half_open_request_in_flight is False

    def test_half_open_failure_reopens_circuit(self):
        """Неудачный probe request возвращает в OPEN."""
        llm = VLLMClient(enable_retry=False)

        # Переводим в half-open
        llm._circuit_breaker.status = CircuitBreakerStatus.HALF_OPEN
        llm._circuit_breaker.half_open_request_in_flight = True

        # Неудачный probe request
        llm._record_failure()

        assert llm._circuit_breaker.status == CircuitBreakerStatus.OPEN
        assert llm._circuit_breaker.half_open_request_in_flight is False
        assert llm._circuit_breaker.open_until > time.time()

    def test_stats_dict_includes_status(self):
        """get_stats_dict включает circuit_breaker_status."""
        llm = VLLMClient()

        stats = llm.get_stats_dict()
        assert "circuit_breaker_status" in stats
        assert stats["circuit_breaker_status"] == CircuitBreakerStatus.CLOSED
        assert "circuit_breaker_open" in stats  # backward compatibility


# =============================================================================
# 2. Frustration Tracker - Single Instance Tests
# =============================================================================

class TestFrustrationTrackerSingleInstance:
    """Тесты для единственного экземпляра frustration tracker."""

    def test_cascade_and_regex_share_tracker(self):
        """CascadeToneAnalyzer и RegexToneAnalyzer используют один tracker."""
        from tone_analyzer.cascade_analyzer import CascadeToneAnalyzer
        from tone_analyzer.frustration_tracker import FrustrationTracker

        analyzer = CascadeToneAnalyzer()

        # Оба должны ссылаться на один и тот же объект
        assert analyzer._frustration is analyzer._regex._frustration_tracker

    def test_regex_does_not_own_shared_tracker(self):
        """RegexToneAnalyzer не владеет внешним tracker."""
        from tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from tone_analyzer.frustration_tracker import FrustrationTracker

        shared_tracker = FrustrationTracker()
        analyzer = RegexToneAnalyzer(frustration_tracker=shared_tracker)

        assert analyzer._owns_frustration_tracker is False
        assert analyzer._frustration_tracker is shared_tracker

    def test_regex_owns_internal_tracker(self):
        """RegexToneAnalyzer владеет собственным tracker."""
        from tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()

        assert analyzer._owns_frustration_tracker is True

    def test_reset_does_not_reset_shared_tracker(self):
        """reset() не сбрасывает shared tracker."""
        from tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from tone_analyzer.frustration_tracker import FrustrationTracker

        shared_tracker = FrustrationTracker()
        shared_tracker._level = 5  # Устанавливаем значение

        analyzer = RegexToneAnalyzer(frustration_tracker=shared_tracker)
        analyzer.reset()

        # Tracker не должен быть сброшен
        assert shared_tracker._level == 5

    def test_reset_resets_owned_tracker(self):
        """reset() сбрасывает собственный tracker."""
        from tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        analyzer._frustration_tracker._level = 5

        analyzer.reset()

        assert analyzer._frustration_tracker._level == 0

    def test_no_double_frustration_update(self):
        """Frustration обновляется только один раз за analyze()."""
        from tone_analyzer.cascade_analyzer import CascadeToneAnalyzer
        from tone_analyzer.models import Tone

        analyzer = CascadeToneAnalyzer()
        analyzer.reset()

        # Проверяем что frustration level одинаков в трекере и результате
        initial_level = analyzer._frustration.level
        assert initial_level == 0

        # Анализируем frustrated сообщение
        result = analyzer.analyze("Это ужасно! Вы меня бесите!")

        # Frustration level в результате должен совпадать с трекером
        # (раньше они расходились из-за двух независимых трекеров)
        assert result.frustration_level == analyzer._frustration.level
        # И он должен быть больше начального
        assert result.frustration_level > initial_level


# =============================================================================
# 3. Fork Stack LIFO Tests
# =============================================================================

class TestForkStackLIFO:
    """Тесты для LIFO порядка fork stack."""

    def test_complete_fork_removes_last_occurrence(self):
        """complete_fork удаляет последнее вхождение fork_id."""
        from dag.models import DAGExecutionContext, DAGBranch

        ctx = DAGExecutionContext(primary_state="greeting")

        # Добавляем fork_A дважды (вложенный fork)
        ctx.fork_stack = ["fork_A", "fork_B", "fork_A"]

        ctx.complete_fork("fork_A")

        # Должно удалить ПОСЛЕДНИЙ fork_A
        assert ctx.fork_stack == ["fork_A", "fork_B"]

    def test_complete_fork_lifo_order(self):
        """complete_fork соблюдает LIFO порядок."""
        from dag.models import DAGExecutionContext

        ctx = DAGExecutionContext(primary_state="greeting")

        # Стандартный LIFO сценарий
        ctx.fork_stack = ["fork_A", "fork_B", "fork_C"]

        # Завершаем в обратном порядке
        ctx.complete_fork("fork_C")
        assert ctx.fork_stack == ["fork_A", "fork_B"]

        ctx.complete_fork("fork_B")
        assert ctx.fork_stack == ["fork_A"]

        ctx.complete_fork("fork_A")
        assert ctx.fork_stack == []

    def test_complete_fork_top_of_stack(self):
        """complete_fork для элемента на вершине стека."""
        from dag.models import DAGExecutionContext

        ctx = DAGExecutionContext(primary_state="greeting")
        ctx.fork_stack = ["fork_A", "fork_B"]

        ctx.complete_fork("fork_B")  # На вершине стека

        assert ctx.fork_stack == ["fork_A"]

    def test_complete_fork_not_on_top(self):
        """complete_fork для элемента НЕ на вершине стека."""
        from dag.models import DAGExecutionContext

        ctx = DAGExecutionContext(primary_state="greeting")
        ctx.fork_stack = ["fork_A", "fork_B", "fork_C"]

        # Завершаем fork_A (не на вершине)
        ctx.complete_fork("fork_A")

        # Должен удалить fork_A
        assert ctx.fork_stack == ["fork_B", "fork_C"]

    def test_complete_fork_nonexistent(self):
        """complete_fork для несуществующего fork_id."""
        from dag.models import DAGExecutionContext

        ctx = DAGExecutionContext(primary_state="greeting")
        ctx.fork_stack = ["fork_A", "fork_B"]

        # Не должно вызвать ошибку
        ctx.complete_fork("fork_X")

        assert ctx.fork_stack == ["fork_A", "fork_B"]


# =============================================================================
# 4. Lead Scoring Turn-Based Decay Tests
# =============================================================================

class TestLeadScoringTurnBasedDecay:
    """Тесты для turn-based decay в lead scoring."""

    def test_reset_initializes_turn_count(self):
        """reset() инициализирует счётчик ходов."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer()
        assert scorer._turn_count == 0
        assert scorer._decay_applied_this_turn is False

    def test_apply_turn_decay_increments_counter(self):
        """apply_turn_decay увеличивает счётчик ходов."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer.add_signal("demo_request")  # Score > 0

        scorer.end_turn()
        scorer.apply_turn_decay()

        assert scorer._turn_count == 2  # 1 from add_signal, 1 from apply_turn_decay

    def test_apply_turn_decay_applies_decay(self):
        """apply_turn_decay применяет decay к score."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer(decay_factor=0.9)
        scorer.add_signal("demo_request")  # +30
        initial_score = scorer._raw_score

        scorer.end_turn()
        scorer.apply_turn_decay()

        # Score должен уменьшиться
        assert scorer._raw_score < initial_score
        assert scorer._raw_score == pytest.approx(initial_score * 0.9, rel=0.01)

    def test_decay_not_applied_twice_in_same_turn(self):
        """Decay не применяется дважды в одном ходу."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer(decay_factor=0.9)
        scorer.add_signal("demo_request")  # +30
        score_after_first = scorer._raw_score

        # Попытка применить decay снова в том же ходу
        scorer.apply_turn_decay()
        scorer.apply_turn_decay()
        scorer.apply_turn_decay()

        # Score не должен измениться
        assert scorer._raw_score == score_after_first

    def test_end_turn_resets_decay_flag(self):
        """end_turn сбрасывает флаг decay."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer()
        scorer.apply_turn_decay()

        assert scorer._decay_applied_this_turn is True

        scorer.end_turn()

        assert scorer._decay_applied_this_turn is False

    def test_decay_applied_even_without_signals(self):
        """Decay применяется даже без новых сигналов."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer(decay_factor=0.9)

        # Ход 1: добавляем сигнал
        scorer.add_signal("demo_request")  # +30
        score_turn1 = scorer._raw_score

        # Ход 2: только decay, без сигналов
        scorer.end_turn()
        scorer.apply_turn_decay()
        score_turn2 = scorer._raw_score

        # Ход 3: только decay
        scorer.end_turn()
        scorer.apply_turn_decay()
        score_turn3 = scorer._raw_score

        # Score должен уменьшаться каждый ход
        assert score_turn2 < score_turn1
        assert score_turn3 < score_turn2

    def test_add_signal_triggers_decay_if_not_applied(self):
        """add_signal вызывает decay если он ещё не применён."""
        from lead_scoring import LeadScorer

        scorer = LeadScorer(decay_factor=0.9)
        scorer.add_signal("demo_request")  # Ход 1: +30

        scorer.end_turn()

        # Ход 2: add_signal должен сначала применить decay
        scorer.add_signal("features_question")  # decay + (+5)

        # Decay должен был примениться
        assert scorer._decay_applied_this_turn is True
        # Score: 30 * 0.9 + 5 = 32
        expected = 30 * 0.9 + 5
        assert scorer._raw_score == pytest.approx(expected, rel=0.01)


# =============================================================================
# 5. Disambiguation Path Protection Phases Tests
# =============================================================================

class TestDisambiguationPathProtection:
    """Тесты для фаз защиты в disambiguation path."""

    @pytest.fixture
    def mock_llm(self):
        """Мок для LLM."""
        llm = MagicMock()
        llm.generate.return_value = "Test response"
        return llm

    @pytest.fixture
    def feature_flags_enabled(self):
        """Включаем все feature flags для тестов."""
        from feature_flags import flags

        original_values = {}
        flags_to_enable = [
            'tone_analysis',
            'conversation_guard',
            'objection_handler',
            'context_policy_overlays',
            'context_full_envelope',
        ]

        for flag in flags_to_enable:
            original_values[flag] = getattr(flags, flag, False)
            flags.set_override(flag, True)

        yield

        # Восстанавливаем
        for flag, value in original_values.items():
            flags.set_override(flag, value)

    def test_continue_with_classification_calls_tone_analysis(
        self, mock_llm, feature_flags_enabled
    ):
        """_continue_with_classification вызывает tone analysis."""
        from bot import SalesBot
        from unittest.mock import patch

        bot = SalesBot(mock_llm)

        with patch.object(bot, '_analyze_tone') as mock_tone:
            mock_tone.return_value = {
                "tone_instruction": "",
                "frustration_level": 0,
                "should_apologize": False,
                "should_offer_exit": False,
            }
            with patch.object(bot, '_check_guard', return_value=None):
                with patch.object(bot, '_check_objection', return_value=None):
                    with patch.object(bot.generator, 'generate', return_value="Response"):
                        bot._continue_with_classification(
                            classification={"intent": "test", "confidence": 0.9},
                            user_message="Test message"
                        )

            mock_tone.assert_called_once_with("Test message")

    def test_continue_with_classification_calls_guard_check(
        self, mock_llm, feature_flags_enabled
    ):
        """_continue_with_classification вызывает guard check."""
        from bot import SalesBot

        bot = SalesBot(mock_llm)

        with patch.object(bot, '_analyze_tone') as mock_tone:
            mock_tone.return_value = {
                "tone_instruction": "",
                "frustration_level": 3,
                "should_apologize": False,
                "should_offer_exit": False,
            }
            with patch.object(bot, '_check_guard') as mock_guard:
                mock_guard.return_value = None
                with patch.object(bot, '_check_objection', return_value=None):
                    with patch.object(bot.generator, 'generate', return_value="Response"):
                        bot._continue_with_classification(
                            classification={"intent": "test", "confidence": 0.9},
                            user_message="Test message"
                        )

                mock_guard.assert_called_once()
                # Проверяем что frustration_level передан
                call_kwargs = mock_guard.call_args[1]
                assert call_kwargs['frustration_level'] == 3

    def test_continue_with_classification_calls_objection_check(
        self, mock_llm, feature_flags_enabled
    ):
        """_continue_with_classification вызывает objection check."""
        from bot import SalesBot

        bot = SalesBot(mock_llm)

        with patch.object(bot, '_analyze_tone') as mock_tone:
            mock_tone.return_value = {
                "tone_instruction": "",
                "frustration_level": 0,
                "should_apologize": False,
                "should_offer_exit": False,
            }
            with patch.object(bot, '_check_guard', return_value=None):
                with patch.object(bot, '_check_objection') as mock_objection:
                    mock_objection.return_value = None
                    with patch.object(bot.generator, 'generate', return_value="Response"):
                        bot._continue_with_classification(
                            classification={"intent": "test", "confidence": 0.9},
                            user_message="Это слишком дорого"
                        )

                    mock_objection.assert_called_once()

    def test_continue_with_classification_handles_guard_intervention(
        self, mock_llm, feature_flags_enabled
    ):
        """_continue_with_classification обрабатывает guard intervention."""
        from bot import SalesBot

        bot = SalesBot(mock_llm)

        with patch.object(bot, '_analyze_tone') as mock_tone:
            mock_tone.return_value = {
                "tone_instruction": "",
                "frustration_level": 5,
                "should_apologize": True,
                "should_offer_exit": True,
                "tone": "frustrated",
            }
            with patch.object(bot, '_check_guard', return_value="soft_close"):
                with patch.object(bot, '_apply_fallback') as mock_fallback:
                    mock_fallback.return_value = {
                        "response": "Извините за неудобства...",
                        "action": "close",
                        "next_state": "soft_close",
                    }

                    result = bot._continue_with_classification(
                        classification={"intent": "test", "confidence": 0.9},
                        user_message="Test message"
                    )

                    # Должен вернуть fallback response
                    assert result["is_final"] is True
                    assert result["fallback_used"] is True
