"""
Сбор и агрегация метрик симуляций.

Supports dynamic flow configurations - not just SPIN.
Phase extraction and coverage calculation now work with any sales technique.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from collections import Counter
import logging

from src.yaml_config.constants import SPIN_PHASES, SPIN_STATES

if TYPE_CHECKING:
    from .runner import SimulationResult
    from src.config_loader import FlowConfig

logger = logging.getLogger(__name__)


@dataclass
class SimulationMetrics:
    """Метрики одной симуляции"""
    # Идентификация
    simulation_id: int
    persona: str

    # Результат
    outcome: str  # "success", "rejection", "soft_close", "abandoned", "timeout"
    turns: int
    duration_seconds: float

    # SPIN прогресс
    phases_reached: List[str] = field(default_factory=list)
    spin_coverage: float = 0.0

    # Качество
    objections_count: int = 0
    objections_handled: int = 0
    fallback_count: int = 0

    # Lead scoring
    final_lead_score: float = 0.0

    # Данные
    collected_data: Dict[str, Any] = field(default_factory=dict)

    # Ошибки
    errors: List[str] = field(default_factory=list)


@dataclass
class AggregatedMetrics:
    """Агрегированные метрики по всем симуляциям"""
    # Общие
    total_simulations: int = 0
    total_turns: int = 0
    total_duration_seconds: float = 0.0

    # По исходам
    success_count: int = 0
    soft_close_count: int = 0
    rejection_count: int = 0
    abandoned_count: int = 0

    # Конверсия
    success_rate: float = 0.0
    soft_close_rate: float = 0.0
    rejection_rate: float = 0.0

    # SPIN
    avg_spin_coverage: float = 0.0
    phase_reach_rates: Dict[str, float] = field(default_factory=dict)

    # Возражения
    total_objections: int = 0
    total_objections_handled: int = 0
    objection_success_rate: float = 0.0

    # Fallback
    total_fallbacks: int = 0
    fallback_rate: float = 0.0

    # Lead scoring
    avg_lead_score: float = 0.0
    hot_leads_count: int = 0
    warm_leads_count: int = 0
    cold_leads_count: int = 0

    # По персонам
    persona_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Ошибки
    error_count: int = 0


class MetricsCollector:
    """Сборщик и агрегатор метрик.

    Note: This class uses SPIN_PHASES as default for backward compatibility.
    For multi-flow support, consider passing expected_phases to individual results.
    """

    # FIX Defect 4: Removed hardcoded "presentation" injection.
    # Phases should come from flow_config, not hardcoded here.
    METRICS_PHASES = list(SPIN_PHASES)

    # Alias for backward compatibility
    SPIN_PHASES = METRICS_PHASES

    def collect_from_result(self, result: 'SimulationResult') -> SimulationMetrics:
        """
        Собирает метрики из результата симуляции.

        Args:
            result: Результат симуляции

        Returns:
            Метрики симуляции
        """
        return SimulationMetrics(
            simulation_id=result.simulation_id,
            persona=result.persona,
            outcome=result.outcome,
            turns=result.turns,
            duration_seconds=result.duration_seconds,
            phases_reached=result.phases_reached,
            spin_coverage=result.spin_coverage,
            objections_count=result.objections_count,
            objections_handled=result.objections_handled,
            fallback_count=result.fallback_count,
            final_lead_score=result.final_lead_score,
            collected_data=result.collected_data,
            errors=result.errors
        )

    def aggregate(self, results: List['SimulationResult']) -> AggregatedMetrics:
        """
        Агрегирует метрики по всем симуляциям.

        Args:
            results: Список результатов симуляций

        Returns:
            Агрегированные метрики
        """
        if not results:
            return AggregatedMetrics()

        n = len(results)

        # Подсчёт по исходам
        outcomes = Counter(r.outcome for r in results)
        success_count = outcomes.get("success", 0)
        soft_close_count = outcomes.get("soft_close", 0)
        rejection_count = outcomes.get("rejection", 0)
        abandoned_count = outcomes.get("abandoned", 0) + outcomes.get("timeout", 0)

        # Общие суммы
        total_turns = sum(r.turns for r in results)
        total_duration = sum(r.duration_seconds for r in results)

        # SPIN coverage
        avg_spin = sum(r.spin_coverage for r in results) / n

        # Подсчёт фаз
        phase_counts = Counter()
        for r in results:
            for phase in r.phases_reached:
                phase_counts[phase] += 1

        phase_rates = {
            phase: phase_counts.get(phase, 0) / n * 100
            for phase in self.SPIN_PHASES
        }

        # Возражения
        total_objections = sum(r.objections_count for r in results)
        total_handled = sum(r.objections_handled for r in results)
        obj_rate = (total_handled / total_objections * 100) if total_objections > 0 else 0

        # Fallback
        total_fallbacks = sum(r.fallback_count for r in results)
        fallback_rate = (total_fallbacks / total_turns * 100) if total_turns > 0 else 0

        # Lead scoring
        avg_lead = sum(r.final_lead_score for r in results) / n
        hot = len([r for r in results if r.final_lead_score >= 0.7])
        warm = len([r for r in results if 0.4 <= r.final_lead_score < 0.7])
        cold = len([r for r in results if r.final_lead_score < 0.4])

        # Статистика по персонам
        persona_stats = self._calc_persona_stats(results)

        # Ошибки
        error_count = len([r for r in results if r.errors])

        return AggregatedMetrics(
            total_simulations=n,
            total_turns=total_turns,
            total_duration_seconds=total_duration,
            success_count=success_count,
            soft_close_count=soft_close_count,
            rejection_count=rejection_count,
            abandoned_count=abandoned_count,
            success_rate=success_count / n * 100,
            soft_close_rate=soft_close_count / n * 100,
            rejection_rate=rejection_count / n * 100,
            avg_spin_coverage=avg_spin,
            phase_reach_rates=phase_rates,
            total_objections=total_objections,
            total_objections_handled=total_handled,
            objection_success_rate=obj_rate,
            total_fallbacks=total_fallbacks,
            fallback_rate=fallback_rate,
            avg_lead_score=avg_lead,
            hot_leads_count=hot,
            warm_leads_count=warm,
            cold_leads_count=cold,
            persona_stats=persona_stats,
            error_count=error_count
        )

    def _calc_persona_stats(self, results: List['SimulationResult']) -> Dict[str, Dict[str, Any]]:
        """Рассчитывает статистику по персонам"""
        persona_groups: Dict[str, List] = {}

        for r in results:
            if r.persona not in persona_groups:
                persona_groups[r.persona] = []
            persona_groups[r.persona].append(r)

        stats = {}
        for persona, group in persona_groups.items():
            n = len(group)
            success = len([r for r in group if r.outcome == "success"])

            stats[persona] = {
                "count": n,
                "success_count": success,
                "success_rate": success / n * 100 if n > 0 else 0,
                "avg_turns": sum(r.turns for r in group) / n if n > 0 else 0,
                "avg_spin_coverage": sum(r.spin_coverage for r in group) / n * 100 if n > 0 else 0,
                "avg_lead_score": sum(r.final_lead_score for r in group) / n if n > 0 else 0,
            }

        return stats


def determine_outcome(state: str, is_final: bool, collected_data: Dict) -> str:
    """
    Определяет исход диалога.

    Args:
        state: Финальное состояние
        is_final: Завершён ли диалог
        collected_data: Собранные данные

    Returns:
        Строка исхода
    """
    # Успех - получили валидный контакт или запланировали демо
    try:
        from src.conditions.state_machine.contact_validator import has_valid_contact
        if has_valid_contact(collected_data):
            return "success"
    except Exception:
        # Fallback: lenient check if validator is unavailable
        if (
            "contact_info" in collected_data or
            "contact" in collected_data or
            "phone" in collected_data or
            "email" in collected_data
        ):
            return "success"

    if state in ["success", "demo_scheduled"]:
        return "success"

    # Явный отказ
    if state in ["rejection", "rejected"]:
        return "rejection"

    # Эскалация на оператора
    if state in ["escalated"]:
        return "soft_close"

    # Мягкое закрытие
    if state in ["soft_close"]:
        return "soft_close"

    # Если диалог завершён но нет контакта
    if is_final:
        return "soft_close"

    # По умолчанию - abandoned
    return "abandoned"


def calculate_spin_coverage(
    phases_reached: List[str],
    expected_phases: Optional[List[str]] = None
) -> float:
    """
    Рассчитывает покрытие фаз продаж.

    Supports any sales technique, not just SPIN.

    Args:
        phases_reached: Список достигнутых фаз
        expected_phases: Ожидаемые фазы для данной техники.
                        If None, falls back to legacy SPIN phases.

    Returns:
        Покрытие от 0.0 до 1.0
    """
    # FIX Defect 4: Use provided expected_phases or fall back to SPIN.
    # No more hardcoded "presentation" injection — flow config controls phases.
    if expected_phases is None:
        all_phases = list(SPIN_PHASES)
    else:
        all_phases = list(expected_phases)

    if not phases_reached or not all_phases:
        return 0.0

    reached_set = set(phases_reached)
    covered = len(reached_set.intersection(all_phases))

    return covered / len(all_phases)


def build_phase_mapping_from_flow(flow_config: 'FlowConfig') -> Dict[str, str]:
    """
    Build state->phase mapping from FlowConfig.

    Args:
        flow_config: The FlowConfig object containing phase_mapping

    Returns:
        Dict mapping state names to phase names.
        Example: {"bant_budget": "budget", "bant_authority": "authority", ...}
    """
    # FlowConfig.phase_mapping is {phase: state}, we need {state: phase}
    phase_mapping = {state: phase for phase, state in flow_config.phase_mapping.items()}

    # FIX Defect 4: Add post_phases_state from flow config instead of hardcoding
    post_phases_state = flow_config.post_phases_state
    if post_phases_state:
        phase_mapping[post_phases_state] = post_phases_state
    # Map 'close' to itself (distinct state, not alias for presentation)
    if "close" not in phase_mapping:
        phase_mapping["close"] = "close"

    return phase_mapping


def extract_phases_from_dialogue(
    dialogue: List[Dict],
    flow_config: Optional['FlowConfig'] = None,
    phase_mapping: Optional[Dict[str, str]] = None
) -> List[str]:
    """
    Извлекает достигнутые фазы из диалога.

    Supports dynamic flow configurations - not just SPIN.

    FIX: Now extracts phases from BOTH prev_state and next_state in decision_trace
    to correctly capture phases that were visited briefly (e.g., after fallback skip).

    Args:
        dialogue: История диалога
        flow_config: FlowConfig object for dynamic phase mapping.
                    Takes precedence over phase_mapping if provided.
        phase_mapping: Direct state->phase mapping dict.
                      Used if flow_config is not provided.
                      Falls back to legacy SPIN mapping if neither provided.

    Returns:
        Список достигнутых фаз
    """
    phases = dict()

    # Build phase mapping from flow_config, direct mapping, or legacy SPIN
    if flow_config is not None:
        mapping = build_phase_mapping_from_flow(flow_config)
        logger.debug(
            "Using flow_config for phase extraction",
            flow_name=flow_config.name,
            phase_mapping=mapping
        )
    elif phase_mapping is not None:
        mapping = phase_mapping.copy()
        # Ensure presentation mappings exist
        mapping.setdefault("presentation", "presentation")
        mapping.setdefault("close", "presentation")
    else:
        # Legacy fallback: SPIN phases only
        # SPIN_STATES: {"situation": "spin_situation", ...}
        # Инвертируем: {"spin_situation": "situation", ...}
        mapping = {state: phase for phase, state in SPIN_STATES.items()}
        mapping["presentation"] = "presentation"
        mapping["close"] = "presentation"
        logger.debug("Using legacy SPIN phase mapping (no flow_config provided)")

    for turn in dialogue:
        # FIX: Extract phases from ALL sources to ensure complete phase coverage
        # Priority order:
        # 1. visited_states (most reliable - explicit list of all states visited in this turn)
        # 2. state field (legacy - only contains final state)
        # 3. decision_trace (fallback for older data without visited_states)

        # 1. PRIMARY: Use visited_states if available (most reliable)
        # This explicitly tracks ALL states visited during a turn, including
        # intermediate states from fallback skip scenarios
        visited_states = turn.get("visited_states", [])
        if visited_states:
            for visited_state in visited_states:
                if visited_state in mapping:
                    phases[mapping[visited_state]] = True
            # If we have visited_states, we can skip other sources as they're redundant
            continue

        # 2. FALLBACK: Use "state" field (which is next_state in bot.py)
        # Only reached if visited_states is not available (legacy data)
        state = turn.get("state", "")
        if state in mapping:
            phases[mapping[state]] = True

        # 3. FALLBACK: Check decision_trace for prev_state and next_state
        # This captures states that were visited but not recorded in "state" field
        # Only reached if visited_states is not available (legacy data)
        decision_trace = turn.get("decision_trace")
        if decision_trace:
            state_machine = decision_trace.get("state_machine", {})

            # Extract prev_state (state bot was IN when processing message)
            prev_state = state_machine.get("prev_state", "")
            if prev_state and prev_state in mapping:
                phases[mapping[prev_state]] = True

            # Extract next_state (state bot transitioned TO)
            next_state = state_machine.get("next_state", "")
            if next_state and next_state in mapping:
                phases[mapping[next_state]] = True

            # Also use explicit phase fields if available (more reliable)
            prev_phase = state_machine.get("prev_phase")
            if prev_phase:
                phases[prev_phase] = True

            next_phase = state_machine.get("next_phase")
            if next_phase:
                phases[next_phase] = True

    return list(phases.keys())
