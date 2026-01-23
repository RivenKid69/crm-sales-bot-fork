"""
Оркестратор симуляций диалогов.

Запускает множество симуляций параллельно и собирает результаты.
"""

import sys
import os
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Добавляем путь к src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .personas import PERSONAS, get_all_persona_names
from .client_agent import ClientAgent
from .metrics import (
    determine_outcome,
    calculate_spin_coverage,
    extract_phases_from_dialogue
)


@dataclass
class SimulationResult:
    """Результат одной симуляции"""
    simulation_id: int
    persona: str
    outcome: str
    turns: int
    duration_seconds: float
    dialogue: List[Dict[str, Any]]

    # Flow info (for e2e testing)
    flow_name: str = ""

    # SPIN прогресс (works for any phase-based flow)
    phases_reached: List[str] = field(default_factory=list)
    spin_coverage: float = 0.0

    # Качество
    objections_count: int = 0
    objections_handled: int = 0
    fallback_count: int = 0

    # Lead
    final_lead_score: float = 0.0
    collected_data: Dict[str, Any] = field(default_factory=dict)

    # Ошибки
    errors: List[str] = field(default_factory=list)

    # Phase 8: Rule traces for debugging conditional rules
    rule_traces: List[Dict[str, Any]] = field(default_factory=list)

    # Decision Tracing: Full traces for all decision stages
    decision_traces: List[Dict[str, Any]] = field(default_factory=list)
    client_traces: List[Dict[str, Any]] = field(default_factory=list)


class SimulationRunner:
    """Оркестратор массовых симуляций"""

    def __init__(
        self,
        bot_llm,
        client_llm=None,
        verbose: bool = False,
        flow_name: Optional[str] = None
    ):
        """
        Инициализация runner'а.

        Args:
            bot_llm: LLM для бота
            client_llm: LLM для клиента (если None, используется bot_llm)
            verbose: Выводить подробную информацию
            flow_name: Имя flow для использования (None = default из settings)
        """
        self.bot_llm = bot_llm
        self.client_llm = client_llm or bot_llm
        self.verbose = verbose
        self.flow_name = flow_name

    def run_batch(
        self,
        count: int = 50,
        parallel: int = 1,
        persona_filter: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> List[SimulationResult]:
        """
        Запуск batch симуляций.

        Args:
            count: Количество симуляций
            parallel: Количество параллельных потоков
            persona_filter: Фильтр по персоне (или None для всех)
            progress_callback: Callback для отображения прогресса

        Returns:
            Список результатов симуляций
        """
        # Сбрасываем circuit breaker перед началом batch
        if hasattr(self.bot_llm, 'reset_circuit_breaker'):
            self.bot_llm.reset_circuit_breaker()

        results = []

        # Формируем очередь персон
        if persona_filter and persona_filter != "all":
            persona_queue = [persona_filter] * count
        else:
            all_personas = get_all_persona_names()
            persona_queue = []
            for i in range(count):
                persona_queue.append(all_personas[i % len(all_personas)])
            random.shuffle(persona_queue)

        # Запускаем симуляции
        if parallel <= 1:
            # Последовательный запуск
            for i in range(count):
                result = self._run_single(i, persona_queue[i])
                results.append(result)

                if progress_callback:
                    progress_callback(result)
                elif self.verbose:
                    print(f"  [{i+1}/{count}] {result.persona}: {result.outcome} ({result.turns} ходов)")
        else:
            # Параллельный запуск
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(self._run_single, i, persona_queue[i]): i
                    for i in range(count)
                }

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)

                        if progress_callback:
                            progress_callback(result)
                        elif self.verbose:
                            idx = len(results)
                            print(f"  [{idx}/{count}] {result.persona}: {result.outcome} ({result.turns} ходов)")
                    except Exception as e:
                        print(f"  [ERROR] Симуляция провалилась: {e}")

        return sorted(results, key=lambda r: r.simulation_id)

    def run_single(self, persona_name: str = "happy_path") -> SimulationResult:
        """
        Запуск одной симуляции.

        Args:
            persona_name: Имя персоны

        Returns:
            Результат симуляции
        """
        return self._run_single(0, persona_name)

    def _run_single(
        self,
        sim_id: int,
        persona_name: str,
        flow_name: Optional[str] = None
    ) -> SimulationResult:
        """
        Внутренняя реализация одной симуляции.

        Args:
            sim_id: ID симуляции
            persona_name: Имя персоны
            flow_name: Имя flow (если None, используется self.flow_name)

        Returns:
            Результат симуляции
        """
        start_time = time.time()
        errors = []
        dialogue = []
        active_flow = flow_name or self.flow_name

        rule_traces = []  # Phase 8: Collect rule traces
        decision_traces = []  # Decision Tracing: Full traces
        client_traces = []  # Client agent traces

        try:
            # Импортируем SalesBot здесь чтобы избежать circular import
            from bot import SalesBot

            # Создаём агентов
            persona = PERSONAS[persona_name]
            client = ClientAgent(self.client_llm, persona)
            # Phase 8: Enable tracing for conditional rules debugging
            # Pass flow_name to SalesBot (SalesBot already supports this!)
            bot = SalesBot(self.bot_llm, enable_tracing=True, flow_name=active_flow)

            # Первое сообщение клиента
            client_message = client.start_conversation()

            # Цикл диалога
            max_turns = 25
            fallback_count = 0

            for turn in range(max_turns):
                try:
                    # Бот отвечает
                    bot_result = bot.process(client_message)

                    # Записываем ход
                    turn_data = {
                        "turn": turn + 1,
                        "client": client_message,
                        "bot": bot_result.get("response", ""),
                        "state": bot_result.get("state", ""),
                        "intent": bot_result.get("intent", ""),
                        "action": bot_result.get("action", ""),
                        "confidence": bot_result.get("confidence", 0),
                        # FIX: Include all visited states for accurate phase coverage
                        # This is critical for fallback skip scenarios where bot transitions
                        # through intermediate states in a single turn
                        "visited_states": bot_result.get("visited_states", []),
                        "initial_state": bot_result.get("initial_state", ""),
                    }

                    # Phase 8: Collect rule trace if available
                    if "trace" in bot_result:
                        trace_data = bot_result["trace"]
                        turn_data["rule_trace"] = trace_data
                        rule_traces.append({
                            "turn": turn + 1,
                            "trace": trace_data
                        })

                    # Decision Tracing: Collect decision trace if available
                    if "decision_trace" in bot_result and bot_result["decision_trace"]:
                        decision_traces.append(bot_result["decision_trace"])
                        turn_data["decision_trace"] = bot_result["decision_trace"]

                    dialogue.append(turn_data)

                    # Считаем fallback
                    if bot_result.get("fallback_used", False):
                        fallback_count += 1

                    # Проверяем завершение
                    if bot_result.get("is_final", False):
                        break

                    # Клиент решает продолжать ли
                    if not client.should_continue():
                        break

                    # Клиент отвечает
                    client_message = client.respond(bot_result.get("response", ""))

                    # Collect client agent trace if available
                    client_trace = client.get_last_trace()
                    if client_trace:
                        client_traces.append(client_trace.to_dict())

                except Exception as e:
                    errors.append(f"Turn {turn + 1}: {str(e)}")
                    if self.verbose:
                        traceback.print_exc()
                    break

            # Собираем результат
            duration = time.time() - start_time

            # Get flow_config from bot for dynamic phase extraction
            flow_config = getattr(bot, '_flow', None)
            expected_phases = flow_config.phase_order if flow_config else None

            # Извлекаем фазы и рассчитываем coverage с учётом flow
            phases = extract_phases_from_dialogue(dialogue, flow_config=flow_config)
            spin_coverage = calculate_spin_coverage(phases, expected_phases=expected_phases)

            # Определяем исход
            final_state = dialogue[-1]["state"] if dialogue else ""
            is_final = len(dialogue) > 0
            collected_data = {}

            if hasattr(bot, 'state_machine') and hasattr(bot.state_machine, 'collected_data'):
                collected_data = dict(bot.state_machine.collected_data)

            outcome = determine_outcome(final_state, is_final, collected_data)

            # Получаем lead score
            lead_score = 0.0
            if hasattr(bot, 'get_lead_score'):
                try:
                    lead_info = bot.get_lead_score()
                    lead_score = lead_info.get("score", 0.0) if isinstance(lead_info, dict) else 0.0
                except Exception:
                    pass

            # Получаем информацию о возражениях из клиента
            client_summary = client.get_summary()

            return SimulationResult(
                simulation_id=sim_id,
                persona=persona_name,
                outcome=outcome,
                turns=len(dialogue),
                duration_seconds=duration,
                dialogue=dialogue,
                flow_name=active_flow or "",
                phases_reached=phases,
                spin_coverage=spin_coverage,
                objections_count=client_summary.get("objections", 0),
                objections_handled=0,  # TODO: track from bot
                fallback_count=fallback_count,
                final_lead_score=lead_score,
                collected_data=collected_data,
                errors=errors,
                rule_traces=rule_traces,  # Phase 8: Include rule traces
                decision_traces=decision_traces,  # Decision Tracing
                client_traces=client_traces,  # Client agent traces
            )

        except Exception as e:
            duration = time.time() - start_time
            errors.append(f"Fatal: {str(e)}")
            if self.verbose:
                traceback.print_exc()

            return SimulationResult(
                simulation_id=sim_id,
                persona=persona_name,
                outcome="error",
                turns=len(dialogue),
                duration_seconds=duration,
                dialogue=dialogue,
                flow_name=active_flow or "",
                errors=errors
            )

    def run_e2e_batch(
        self,
        scenarios: List[Any],
        progress_callback: Optional[callable] = None,
        parallel: int = 1
    ) -> List[Any]:
        """
        Запуск batch e2e сценариев с разными flows.

        Args:
            scenarios: Список E2EScenario
            progress_callback: Callback для отображения прогресса
            parallel: Количество параллельных потоков (по умолчанию: 1)

        Returns:
            Список E2EResult
        """
        from .e2e_scenarios import E2EScenario
        from .e2e_evaluator import E2EEvaluator, E2EResult

        # Сбрасываем circuit breaker перед началом batch
        if hasattr(self.bot_llm, 'reset_circuit_breaker'):
            self.bot_llm.reset_circuit_breaker()

        evaluator = E2EEvaluator()
        results: List[E2EResult] = []

        def _evaluate_scenario(idx: int, scenario) -> E2EResult:
            """Выполняет симуляцию и оценку одного сценария."""
            sim_result = self._run_single(
                sim_id=int(scenario.id) if scenario.id.isdigit() else idx,
                persona_name=scenario.persona,
                flow_name=scenario.flow
            )
            return evaluator.evaluate(sim_result, scenario)

        if parallel <= 1:
            # Последовательный запуск
            for idx, scenario in enumerate(scenarios):
                evaluation = _evaluate_scenario(idx, scenario)
                results.append(evaluation)

                if progress_callback:
                    progress_callback(evaluation)
                elif self.verbose:
                    status = "PASS" if evaluation.passed else "FAIL"
                    print(f"  [{idx+1}/{len(scenarios)}] {status} {scenario.name}: "
                          f"{evaluation.outcome} (score: {evaluation.score:.2f})")
        else:
            # Параллельный запуск
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_evaluate_scenario, idx, scenario): (idx, scenario)
                    for idx, scenario in enumerate(scenarios)
                }

                for future in as_completed(futures):
                    try:
                        evaluation = future.result()
                        results.append(evaluation)

                        if progress_callback:
                            progress_callback(evaluation)
                        elif self.verbose:
                            status = "PASS" if evaluation.passed else "FAIL"
                            print(f"  [{len(results)}/{len(scenarios)}] {status} {evaluation.scenario_name}: "
                                  f"{evaluation.outcome} (score: {evaluation.score:.2f})")
                    except Exception as e:
                        idx, scenario = futures[future]
                        print(f"  [ERROR] Сценарий {scenario.name} провалился: {e}")

        # Сортируем по scenario_id для стабильного порядка
        return sorted(results, key=lambda r: r.scenario_id)


def create_runner(verbose: bool = False) -> SimulationRunner:
    """
    Создаёт runner с дефолтным LLM.

    Args:
        verbose: Подробный вывод

    Returns:
        Настроенный SimulationRunner
    """
    from llm import OllamaLLM

    llm = OllamaLLM()
    return SimulationRunner(bot_llm=llm, client_llm=llm, verbose=verbose)
