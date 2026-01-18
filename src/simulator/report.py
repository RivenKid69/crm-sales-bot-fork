"""
Генерация отчётов по симуляциям.

Создаёт полные отчёты с:
- Общей статистикой
- Статистикой по персонам
- SPIN прогрессом
- Полными диалогами
"""

from typing import List
from datetime import datetime

from .runner import SimulationResult
from .metrics import MetricsCollector, AggregatedMetrics


class ReportGenerator:
    """Генератор отчётов по симуляциям"""

    def __init__(self):
        self.metrics_collector = MetricsCollector()

    def generate_full_report(
        self,
        results: List[SimulationResult],
        include_dialogues: bool = True
    ) -> str:
        """
        Генерирует полный отчёт по всем симуляциям.

        Args:
            results: Список результатов симуляций
            include_dialogues: Включать ли полные диалоги

        Returns:
            Текст отчёта
        """
        if not results:
            return "Нет результатов для отчёта"

        # Агрегируем метрики
        metrics = self.metrics_collector.aggregate(results)

        report = []

        # Заголовок
        report.append("=" * 80)
        report.append("ОТЧЁТ ПО СИМУЛЯЦИЯМ ДИАЛОГОВ")
        report.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")

        # Общая статистика
        report.append(self._section_general_stats(metrics))

        # Конверсия
        report.append(self._section_conversion(metrics))

        # По персонам
        report.append(self._section_persona_stats(metrics))

        # SPIN прогресс
        report.append(self._section_spin_progress(metrics))

        # Возражения
        report.append(self._section_objections(metrics))

        # Fallback статистика
        report.append(self._section_fallback(metrics))

        # Lead scoring
        report.append(self._section_lead_scoring(metrics))

        # Проблемные диалоги
        report.append(self._section_problems(results))

        # Phase 8: Статистика условных правил
        report.append(self._section_rule_traces(results))

        # Полные диалоги (если включено)
        if include_dialogues:
            report.append(self._section_full_dialogues(results))

        # Финал
        report.append("")
        report.append("=" * 80)
        report.append("КОНЕЦ ОТЧЁТА")
        report.append("=" * 80)

        return "\n".join(report)

    def generate_console_summary(self, results: List[SimulationResult]) -> str:
        """
        Генерирует краткую сводку для консоли.

        Args:
            results: Список результатов

        Returns:
            Текст сводки
        """
        if not results:
            return "Нет результатов"

        metrics = self.metrics_collector.aggregate(results)

        lines = []
        lines.append("")
        lines.append("=" * 60)
        lines.append("СВОДКА")
        lines.append("=" * 60)
        lines.append(f"Всего симуляций: {metrics.total_simulations}")
        lines.append(f"Успешных: {metrics.success_count} ({metrics.success_rate:.1f}%)")
        lines.append(f"Soft close: {metrics.soft_close_count} ({metrics.soft_close_rate:.1f}%)")
        lines.append(f"Отказов: {metrics.rejection_count} ({metrics.rejection_rate:.1f}%)")
        lines.append(f"Ср. SPIN coverage: {metrics.avg_spin_coverage * 100:.0f}%")
        lines.append(f"Ср. lead score: {metrics.avg_lead_score:.2f}")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _section_general_stats(self, metrics: AggregatedMetrics) -> str:
        """Секция общей статистики"""
        lines = []
        lines.append("## ОБЩАЯ СТАТИСТИКА")
        lines.append("-" * 50)
        lines.append(f"Всего симуляций: {metrics.total_simulations}")
        lines.append(f"Всего ходов: {metrics.total_turns}")
        lines.append(f"Общее время: {metrics.total_duration_seconds:.1f} сек")
        lines.append(f"Среднее время на симуляцию: {metrics.total_duration_seconds / max(metrics.total_simulations, 1):.1f} сек")
        lines.append("")
        return "\n".join(lines)

    def _section_conversion(self, metrics: AggregatedMetrics) -> str:
        """Секция конверсии"""
        lines = []
        lines.append("## КОНВЕРСИЯ")
        lines.append("-" * 50)
        lines.append(f"Успешных (контакт/демо): {metrics.success_count} ({metrics.success_rate:.1f}%)")
        lines.append(f"Soft close: {metrics.soft_close_count} ({metrics.soft_close_rate:.1f}%)")
        lines.append(f"Отказов: {metrics.rejection_count} ({metrics.rejection_rate:.1f}%)")
        lines.append(f"Abandoned/Timeout: {metrics.abandoned_count}")
        lines.append("")
        lines.append(f"Конверсия в успех: {metrics.success_rate:.1f}%")
        lines.append(f"Конверсия в soft close+: {metrics.success_rate + metrics.soft_close_rate:.1f}%")
        lines.append("")
        return "\n".join(lines)

    def _section_persona_stats(self, metrics: AggregatedMetrics) -> str:
        """Секция статистики по персонам"""
        lines = []
        lines.append("## СТАТИСТИКА ПО ПЕРСОНАМ")
        lines.append("-" * 50)

        for persona, stats in sorted(metrics.persona_stats.items()):
            lines.append(f"\n{persona}:")
            lines.append(f"  Диалогов: {stats['count']}")
            lines.append(f"  Успех: {stats['success_rate']:.0f}%")
            lines.append(f"  Ср. ходов: {stats['avg_turns']:.1f}")
            lines.append(f"  SPIN coverage: {stats['avg_spin_coverage']:.0f}%")
            lines.append(f"  Ср. lead score: {stats['avg_lead_score']:.2f}")

        lines.append("")
        return "\n".join(lines)

    def _section_spin_progress(self, metrics: AggregatedMetrics) -> str:
        """Секция SPIN прогресса"""
        lines = []
        lines.append("## SPIN ПРОГРЕСС")
        lines.append("-" * 50)
        lines.append(f"Среднее SPIN coverage: {metrics.avg_spin_coverage * 100:.0f}%")
        lines.append("")
        lines.append("Достижение фаз:")

        phase_names = {
            "situation": "Situation (ситуация)",
            "problem": "Problem (проблема)",
            "implication": "Implication (последствия)",
            "need_payoff": "Need-payoff (потребность)",
            "presentation": "Presentation (презентация)"
        }

        for phase, name in phase_names.items():
            rate = metrics.phase_reach_rates.get(phase, 0)
            bar = "█" * int(rate / 5) + "░" * (20 - int(rate / 5))
            lines.append(f"  {name}: {bar} {rate:.0f}%")

        lines.append("")
        return "\n".join(lines)

    def _section_objections(self, metrics: AggregatedMetrics) -> str:
        """Секция возражений"""
        lines = []
        lines.append("## ОБРАБОТКА ВОЗРАЖЕНИЙ")
        lines.append("-" * 50)
        lines.append(f"Всего возражений: {metrics.total_objections}")
        lines.append(f"Обработано успешно: {metrics.total_objections_handled}")
        lines.append(f"Успешность обработки: {metrics.objection_success_rate:.0f}%")
        lines.append("")
        return "\n".join(lines)

    def _section_fallback(self, metrics: AggregatedMetrics) -> str:
        """Секция fallback статистики"""
        lines = []
        lines.append("## FALLBACK СТАТИСТИКА")
        lines.append("-" * 50)
        lines.append(f"Всего ходов: {metrics.total_turns}")
        lines.append(f"Fallback использован: {metrics.total_fallbacks} раз")
        lines.append(f"Fallback rate: {metrics.fallback_rate:.1f}%")
        lines.append("")
        return "\n".join(lines)

    def _section_lead_scoring(self, metrics: AggregatedMetrics) -> str:
        """Секция lead scoring"""
        lines = []
        lines.append("## LEAD SCORING")
        lines.append("-" * 50)
        lines.append(f"Средний lead score: {metrics.avg_lead_score:.2f}")
        lines.append(f"Hot leads (>=0.7): {metrics.hot_leads_count}")
        lines.append(f"Warm leads (0.4-0.7): {metrics.warm_leads_count}")
        lines.append(f"Cold leads (<0.4): {metrics.cold_leads_count}")
        lines.append("")
        return "\n".join(lines)

    def _section_problems(self, results: List[SimulationResult]) -> str:
        """Секция проблемных диалогов"""
        lines = []
        lines.append("## ПРОБЛЕМНЫЕ ДИАЛОГИ")
        lines.append("-" * 50)

        problems = [r for r in results if r.errors or r.fallback_count > 3]

        if not problems:
            lines.append("Критических проблем не обнаружено")
        else:
            lines.append(f"Найдено проблемных диалогов: {len(problems)}")
            lines.append("")

            for r in problems[:10]:  # Показываем максимум 10
                lines.append(f"Симуляция #{r.simulation_id} ({r.persona}):")
                if r.errors:
                    lines.append(f"  Ошибки: {'; '.join(r.errors[:3])}")
                if r.fallback_count > 3:
                    lines.append(f"  Много fallback: {r.fallback_count}")
                lines.append("")

        lines.append("")
        return "\n".join(lines)

    def _section_rule_traces(self, results: List[SimulationResult]) -> str:
        """
        Phase 8: Секция статистики условных правил.

        Показывает:
        - Общую статистику по типам разрешения правил
        - Топ сработавших условий
        - Примеры условных правил с детализацией
        """
        lines = []
        lines.append("## УСЛОВНЫЕ ПРАВИЛА (ТРАССИРОВКА)")
        lines.append("-" * 50)

        # Собираем все трассировки
        all_traces = []
        for r in results:
            all_traces.extend(r.rule_traces)

        if not all_traces:
            lines.append("Трассировка условных правил не собрана")
            lines.append("(Возможно, трассировка отключена или правила не применялись)")
            lines.append("")
            return "\n".join(lines)

        # Статистика по типам разрешения
        resolution_counts = {}
        matched_conditions = {}
        total_conditions_checked = 0

        for trace_info in all_traces:
            trace = trace_info.get("trace", {})
            resolution = trace.get("resolution", "unknown")
            resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1

            matched = trace.get("matched_condition")
            if matched:
                matched_conditions[matched] = matched_conditions.get(matched, 0) + 1

            total_conditions_checked += trace.get("conditions_checked", 0)

        lines.append(f"Всего трассировок: {len(all_traces)}")
        lines.append(f"Всего проверок условий: {total_conditions_checked}")
        lines.append("")

        # Статистика по типам разрешения
        lines.append("Типы разрешения правил:")
        resolution_labels = {
            "simple": "Простое правило",
            "condition_matched": "Условие сработало",
            "default": "По умолчанию",
            "fallback": "Fallback",
            "none": "Без изменений"
        }
        for res, count in sorted(resolution_counts.items(), key=lambda x: -x[1]):
            label = resolution_labels.get(res, res)
            pct = count / len(all_traces) * 100
            lines.append(f"  {label}: {count} ({pct:.1f}%)")
        lines.append("")

        # Топ сработавших условий
        if matched_conditions:
            lines.append("Топ сработавших условий:")
            for condition, count in sorted(matched_conditions.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"  {condition}: {count}")
            lines.append("")

        # Примеры условных правил (первые 5 с condition_matched)
        conditional_traces = [
            t for t in all_traces
            if t.get("trace", {}).get("resolution") == "condition_matched"
        ]

        if conditional_traces:
            lines.append("Примеры сработавших условных правил:")
            for trace_info in conditional_traces[:5]:
                trace = trace_info.get("trace", {})
                turn = trace_info.get("turn", "?")
                rule = trace.get("rule_name", "?")
                action = trace.get("final_action", "?")
                matched = trace.get("matched_condition", "?")
                lines.append(f"  [Ход {turn}] {rule} -> {action} via {matched}")
            lines.append("")

        return "\n".join(lines)

    def _section_full_dialogues(self, results: List[SimulationResult]) -> str:
        """Секция с полными диалогами"""
        lines = []
        lines.append("")
        lines.append("=" * 80)
        lines.append("ПОЛНЫЕ ДИАЛОГИ")
        lines.append("=" * 80)

        for r in results:
            lines.append("")
            lines.append("-" * 80)
            lines.append(f"СИМУЛЯЦИЯ #{r.simulation_id}")
            lines.append(f"Персона: {r.persona}")
            lines.append(f"Исход: {r.outcome}")
            lines.append(f"Ходов: {r.turns}")
            lines.append(f"SPIN coverage: {r.spin_coverage * 100:.0f}%")
            lines.append(f"Lead score: {r.final_lead_score:.2f}")
            if r.collected_data:
                lines.append(f"Собранные данные: {r.collected_data}")
            if r.errors:
                lines.append(f"Ошибки: {r.errors}")
            lines.append("-" * 40)
            lines.append("ДИАЛОГ:")
            lines.append("")

            for turn in r.dialogue:
                lines.append(f"[Ход {turn['turn']}]")
                lines.append(f"Клиент: {turn['client']}")
                lines.append(f"Бот: {turn['bot']}")
                lines.append(f"  (state={turn['state']}, intent={turn['intent']}, action={turn.get('action', '')})")

                # Phase 8: Show [RULE] trace for conditional rules
                rule_trace = turn.get("rule_trace")
                if rule_trace:
                    resolution = rule_trace.get("resolution", "")
                    final_action = rule_trace.get("final_action", "")
                    matched = rule_trace.get("matched_condition")

                    if matched:
                        lines.append(f"  [RULE] {rule_trace.get('rule_name', '')} -> {final_action} ({resolution} via {matched})")
                    else:
                        lines.append(f"  [RULE] {rule_trace.get('rule_name', '')} -> {final_action} ({resolution})")

                    # Show condition entries if any
                    entries = rule_trace.get("entries", [])
                    for entry in entries:
                        result_str = "PASS" if entry.get("result") else "FAIL"
                        lines.append(f"    {entry.get('condition', '')}: {result_str}")

                lines.append("")

            # Итоговые метрики диалога
            lines.append("-" * 40)
            lines.append("МЕТРИКИ ДИАЛОГА:")
            lines.append(f"  Фазы: {', '.join(r.phases_reached) if r.phases_reached else 'нет'}")
            lines.append(f"  Возражения: {r.objections_count}")
            lines.append(f"  Fallback: {r.fallback_count}")
            lines.append("")

        return "\n".join(lines)

    def save_report(self, results: List[SimulationResult], filepath: str, include_dialogues: bool = True):
        """
        Сохраняет отчёт в файл.

        Args:
            results: Результаты симуляций
            filepath: Путь к файлу
            include_dialogues: Включать ли полные диалоги
        """
        report = self.generate_full_report(results, include_dialogues=include_dialogues)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)


def generate_e2e_report(results: List, output_path: str = None) -> dict:
    """
    Generate E2E test report.

    Args:
        results: List of E2EResult objects
        output_path: Optional path to save JSON report

    Returns:
        Report data as dict
    """
    import json
    from datetime import datetime

    # Calculate summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # Build report structure
    report_data = {
        "run_id": f"e2e_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "total_flows": total,
        },
        "summary": {
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 2),
            "avg_score": round(avg_score, 4),
        },
        "flows": []
    }

    # Add individual flow results
    for r in results:
        flow_data = {
            "id": r.scenario_id,
            "name": r.scenario_name,
            "flow": r.flow_name,
            "passed": r.passed,
            "score": round(r.score, 4),
            "outcome": r.outcome,
            "expected_outcome": r.expected_outcome,
            "phases_reached": r.phases_reached,
            "expected_phases": r.expected_phases,
            "turns": r.turns,
            "duration_seconds": round(r.duration_seconds, 2),
            "errors": r.errors,
            "details": r.details
        }
        report_data["flows"].append(flow_data)

    # Save to file if path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

    return report_data


def generate_e2e_text_report(results: List, output_path: str = None) -> str:
    """
    Generate human-readable E2E test report.

    Args:
        results: List of E2EResult objects
        output_path: Optional path to save text report

    Returns:
        Report text
    """
    from datetime import datetime

    lines = []

    # Header
    lines.append("=" * 80)
    lines.append("E2E TEST REPORT - SALES TECHNIQUES")
    lines.append("=" * 80)
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Passed: {passed}/{total} ({pass_rate:.1f}%)")
    lines.append(f"Average Score: {avg_score:.2f}")
    lines.append("")

    # Results by technique
    lines.append("RESULTS BY TECHNIQUE")
    lines.append("-" * 80)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        expected_note = f" (expected: {r.expected_outcome})" if r.outcome != r.expected_outcome else ""
        lines.append(
            f"{status} {r.scenario_id:>2}. {r.scenario_name:<25} "
            f"-> {r.outcome:<12} score={r.score:.2f}{expected_note}"
        )

    lines.append("")

    # Failed tests details
    failed_results = [r for r in results if not r.passed]
    if failed_results:
        lines.append("FAILED TESTS DETAILS")
        lines.append("-" * 80)
        for r in failed_results:
            lines.append(f"\n{r.scenario_id}. {r.scenario_name}:")
            lines.append(f"  Flow: {r.flow_name}")
            lines.append(f"  Expected: {r.expected_outcome}, Got: {r.outcome}")
            lines.append(f"  Phases reached: {r.phases_reached}")
            lines.append(f"  Expected phases: {r.expected_phases}")
            if r.errors:
                lines.append(f"  Errors: {r.errors[:3]}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    report_text = "\n".join(lines)

    # Save to file if path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

    return report_text
