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

        # Decision Analysis: Full decision traces
        report.append(self._section_decision_analysis(results))

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

    def _section_decision_analysis(self, results: List[SimulationResult]) -> str:
        """
        Секция анализа решений (Decision Tracing).

        Показывает:
        - Общую статистику по классификации
        - Статистику по state machine transitions
        - Информацию о policy overrides
        - Тайминги
        """
        lines = []
        lines.append("## DECISION ANALYSIS")
        lines.append("-" * 50)

        # Collect all decision traces
        all_traces = []
        for r in results:
            all_traces.extend(r.decision_traces)

        if not all_traces:
            lines.append("Decision traces не собраны")
            lines.append("(enable_tracing=True для сбора)")
            lines.append("")
            return "\n".join(lines)

        lines.append(f"Всего traces: {len(all_traces)}")
        lines.append("")

        # Classification stats
        confidences = []
        methods = {}
        intents = {}

        for trace in all_traces:
            classification = trace.get("classification", {})
            if classification:
                conf = classification.get("confidence", 0)
                if conf:
                    confidences.append(conf)
                method = classification.get("method_used", "unknown")
                methods[method] = methods.get(method, 0) + 1
                intent = classification.get("top_intent", "unknown")
                intents[intent] = intents.get(intent, 0) + 1

        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            high_conf = len([c for c in confidences if c > 0.8])
            lines.append("Classification:")
            lines.append(f"  Avg confidence: {avg_conf:.2f}")
            lines.append(f"  High confidence (>0.8): {high_conf}/{len(confidences)} ({high_conf/len(confidences)*100:.0f}%)")
            lines.append(f"  Methods: {methods}")
            lines.append(f"  Top intents: {dict(sorted(intents.items(), key=lambda x: -x[1])[:5])}")
            lines.append("")

        # Dialogue confidence sanity-check (runner-level turn_data coverage).
        dialogue_confidences = []
        for r in results:
            for turn in getattr(r, "dialogue", []) or []:
                conf = turn.get("confidence")
                if isinstance(conf, (int, float)):
                    dialogue_confidences.append(float(conf))

        if dialogue_confidences:
            non_zero = len([c for c in dialogue_confidences if c > 0.0])
            coverage = non_zero / len(dialogue_confidences) * 100
            if non_zero == 0:
                lines.append("SANITY CHECK:")
                lines.append("  WARNING: dialogue confidence coverage is 0% (all turns are 0.0)")
                lines.append("")
            else:
                lines.append("SANITY CHECK:")
                lines.append(f"  Dialogue confidence non-zero coverage: {non_zero}/{len(dialogue_confidences)} ({coverage:.0f}%)")
                lines.append("")
        else:
            lines.append("SANITY CHECK:")
            lines.append("  WARNING: dialogue confidence values are missing")
            lines.append("")

        # State machine stats
        transitions = {}
        states_visited = {}

        for trace in all_traces:
            sm = trace.get("state_machine", {})
            if sm:
                prev_state = sm.get("prev_state", "?")
                next_state = sm.get("next_state", "?")
                trans_key = f"{prev_state}->{next_state}"
                transitions[trans_key] = transitions.get(trans_key, 0) + 1
                states_visited[next_state] = states_visited.get(next_state, 0) + 1

        if transitions:
            lines.append("State Machine:")
            lines.append(f"  Top transitions: {dict(sorted(transitions.items(), key=lambda x: -x[1])[:5])}")
            lines.append(f"  States visited: {dict(sorted(states_visited.items(), key=lambda x: -x[1])[:5])}")
            lines.append("")

        # Policy override stats
        override_count = 0
        override_decisions = {}

        for trace in all_traces:
            policy = trace.get("policy_override", {})
            if policy and policy.get("was_overridden"):
                override_count += 1
                decision = policy.get("decision", "unknown")
                override_decisions[decision] = override_decisions.get(decision, 0) + 1

        if override_count > 0:
            lines.append("Policy Overrides:")
            lines.append(f"  Total: {override_count} ({override_count/len(all_traces)*100:.1f}%)")
            lines.append(f"  Decisions: {override_decisions}")
            lines.append("")

        # Timing stats
        turn_times = []
        bottlenecks = {}

        for trace in all_traces:
            timing = trace.get("timing", {})
            if timing:
                total_ms = timing.get("total_turn_ms", 0)
                if total_ms:
                    turn_times.append(total_ms)
                bottleneck = timing.get("bottleneck", "unknown")
                bottlenecks[bottleneck] = bottlenecks.get(bottleneck, 0) + 1

        if turn_times:
            avg_time = sum(turn_times) / len(turn_times)
            lines.append("Timing:")
            lines.append(f"  Avg turn time: {avg_time:.0f}ms")
            lines.append(f"  Max turn time: {max(turn_times):.0f}ms")
            lines.append(f"  Bottlenecks: {bottlenecks}")
            lines.append("")

        # Per-simulation breakdown (first 3 simulations)
        lines.append("Per-Simulation Breakdown (first 3):")
        for r in results[:3]:
            if not r.decision_traces:
                continue
            lines.append(f"\n  Simulation #{r.simulation_id} ({r.persona}, {r.outcome}):")
            for i, trace in enumerate(r.decision_traces[:5], 1):
                meta = trace.get("metadata", {})
                turn = meta.get("turn_number", i)
                classification = trace.get("classification", {})
                intent = classification.get("top_intent", "?")
                conf = classification.get("confidence", 0)
                sm = trace.get("state_machine", {})
                prev_state = sm.get("prev_state", "?")
                next_state = sm.get("next_state", "?")
                action = sm.get("action", "?")
                timing = trace.get("timing", {})
                ms = timing.get("total_turn_ms", 0)

                lines.append(f"    Turn {turn}: {intent}({conf:.2f}) | {prev_state}->{next_state} | {action} | {ms:.0f}ms")

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
    Generate E2E test report with grouping by technique.

    Args:
        results: List of E2EResult objects
        output_path: Optional path to save JSON report

    Returns:
        Report data as dict
    """
    import json
    from datetime import datetime
    from collections import defaultdict

    # Calculate summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    # Group results by flow (technique)
    results_by_flow = defaultdict(list)
    for r in results:
        results_by_flow[r.flow_name].append(r)

    # Calculate per-technique stats
    techniques_summary = []
    for flow_name, flow_results in sorted(results_by_flow.items()):
        tech_total = len(flow_results)
        tech_passed = sum(1 for r in flow_results if r.passed)
        tech_avg_score = sum(r.score for r in flow_results) / tech_total
        tech_pass_rate = (tech_passed / tech_total * 100) if tech_total > 0 else 0.0

        techniques_summary.append({
            "flow": flow_name,
            "total": tech_total,
            "passed": tech_passed,
            "pass_rate": round(tech_pass_rate, 2),
            "avg_score": round(tech_avg_score, 4),
            "personas": [r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"
                        for r in flow_results]
        })

    # Count unique techniques and personas
    unique_techniques = len(results_by_flow)
    personas_per_technique = len(next(iter(results_by_flow.values()))) if results_by_flow else 0

    # Build report structure
    report_data = {
        "run_id": f"e2e_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "total_tests": total,
            "techniques": unique_techniques,
            "personas_per_technique": personas_per_technique,
        },
        "summary": {
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 2),
            "avg_score": round(avg_score, 4),
        },
        "by_technique": techniques_summary,
        "all_results": []
    }

    # Add individual test results
    for r in results:
        # Extract persona from scenario_id
        persona = r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"

        result_data = {
            "id": r.scenario_id,
            "name": r.scenario_name,
            "flow": r.flow_name,
            "persona": persona,
            "passed": r.passed,
            "score": round(r.score, 4),
            "outcome": r.outcome,
            "expected_outcome": r.expected_outcome,
            "phases_reached": r.phases_reached,
            "expected_phases": r.expected_phases,
            "turns": r.turns,
            "duration_seconds": round(r.duration_seconds, 2),
            "errors": r.errors,
            "details": r.details,
            # Full dialogue history
            "dialogue": getattr(r, 'dialogue', []) if hasattr(r, 'dialogue') else [],
            # Decision Tracing: Include full traces
            "decision_traces": getattr(r, 'decision_traces', []) if hasattr(r, 'decision_traces') else [],
            "client_traces": getattr(r, 'client_traces', []) if hasattr(r, 'client_traces') else [],
            "rule_traces": getattr(r, 'rule_traces', []) if hasattr(r, 'rule_traces') else [],
        }
        report_data["all_results"].append(result_data)

    # Save to file if path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

    return report_data


def generate_e2e_text_report(results: List, output_path: str = None) -> str:
    """
    Generate human-readable E2E test report with grouping by technique.

    Args:
        results: List of E2EResult objects
        output_path: Optional path to save text report

    Returns:
        Report text
    """
    from datetime import datetime
    from collections import defaultdict

    lines = []

    # Header
    lines.append("=" * 80)
    lines.append("E2E TEST REPORT - SALES TECHNIQUES")
    lines.append("=" * 80)
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Group by flow
    results_by_flow = defaultdict(list)
    for r in results:
        results_by_flow[r.flow_name].append(r)

    unique_techniques = len(results_by_flow)
    personas_per_technique = len(next(iter(results_by_flow.values()))) if results_by_flow else 0

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Techniques: {unique_techniques}")
    lines.append(f"Personas per technique: {personas_per_technique}")
    lines.append(f"Total tests: {total}")
    lines.append(f"Passed: {passed}/{total} ({pass_rate:.1f}%)")
    lines.append(f"Average Score: {avg_score:.2f}")
    lines.append("")

    # Results grouped by technique
    lines.append("RESULTS BY TECHNIQUE")
    lines.append("-" * 80)

    for flow_name in sorted(results_by_flow.keys()):
        flow_results = results_by_flow[flow_name]
        flow_passed = sum(1 for r in flow_results if r.passed)
        flow_total = len(flow_results)
        flow_avg_score = sum(r.score for r in flow_results) / flow_total

        # Technique header
        flow_status = "✓" if flow_passed == flow_total else "○" if flow_passed > 0 else "✗"
        lines.append(f"\n{flow_status} {flow_name.upper()} ({flow_passed}/{flow_total}, avg: {flow_avg_score:.2f})")

        # Details per persona
        for r in flow_results:
            status = "PASS" if r.passed else "FAIL"
            persona = r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"
            expected_note = f" (exp: {r.expected_outcome})" if r.outcome != r.expected_outcome else ""
            lines.append(f"    {status} {persona:18s} → {r.outcome:12s} score={r.score:.2f}{expected_note}")

    lines.append("")

    # Failed tests details
    failed_results = [r for r in results if not r.passed]
    if failed_results:
        lines.append("FAILED TESTS DETAILS")
        lines.append("-" * 80)
        for r in failed_results:
            persona = r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"
            lines.append(f"\n{r.flow_name} + {persona}:")
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
