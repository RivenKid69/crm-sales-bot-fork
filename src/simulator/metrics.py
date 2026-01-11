"""
Сбор и агрегация метрик симуляций.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, TYPE_CHECKING
from collections import Counter

if TYPE_CHECKING:
    from .runner import SimulationResult


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
    """Сборщик и агрегатор метрик"""

    SPIN_PHASES = ["situation", "problem", "implication", "need_payoff", "presentation"]

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
    # Успех - получили контакт или запланировали демо
    if "contact" in collected_data or "phone" in collected_data or "email" in collected_data:
        return "success"

    if state in ["success", "demo_scheduled"]:
        return "success"

    # Явный отказ
    if state in ["rejection", "rejected"]:
        return "rejection"

    # Мягкое закрытие
    if state in ["soft_close"]:
        return "soft_close"

    # Если диалог завершён но нет контакта
    if is_final:
        return "soft_close"

    # По умолчанию - abandoned
    return "abandoned"


def calculate_spin_coverage(phases_reached: List[str]) -> float:
    """
    Рассчитывает покрытие SPIN фаз.

    Args:
        phases_reached: Список достигнутых фаз

    Returns:
        Покрытие от 0.0 до 1.0
    """
    all_phases = ["situation", "problem", "implication", "need_payoff", "presentation"]

    if not phases_reached:
        return 0.0

    reached_set = set(phases_reached)
    covered = len(reached_set.intersection(all_phases))

    return covered / len(all_phases)


def extract_phases_from_dialogue(dialogue: List[Dict]) -> List[str]:
    """
    Извлекает достигнутые фазы из диалога.

    Args:
        dialogue: История диалога

    Returns:
        Список достигнутых фаз
    """
    phases = set()

    phase_mapping = {
        "spin_situation": "situation",
        "spin_problem": "problem",
        "spin_implication": "implication",
        "spin_need_payoff": "need_payoff",
        "presentation": "presentation",
        "close": "presentation",
    }

    for turn in dialogue:
        state = turn.get("state", "")
        if state in phase_mapping:
            phases.add(phase_mapping[state])

    return list(phases)
