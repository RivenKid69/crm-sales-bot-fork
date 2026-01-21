#!/usr/bin/env python3
"""
CLI для запуска симуляций диалогов.

Использование:
    python -m src.simulator -n 50 -o report.txt
    python -m src.simulator --count 10 --persona skeptic
    python -m src.simulator -n 100 --parallel 4

E2E тестирование 20 техник продаж:
    python -m src.simulator --e2e                    # 20 техник × 5 персон = 100 тестов
    python -m src.simulator --e2e --personas 3       # 20 техник × 3 персоны = 60 тестов
    python -m src.simulator --e2e-flow challenger    # 1 техника × 5 персон = 5 тестов
    python -m src.simulator --e2e -o e2e_report.json # С сохранением отчёта
"""

import argparse
import sys
import os
from datetime import datetime

# Принудительно используем CPU для sentence-transformers чтобы освободить VRAM для Ollama
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# Также устанавливаем device через torch
os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.path.expanduser("~/.cache/sentence_transformers")

# Добавляем путь к src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.runner import SimulationRunner
from simulator.report import ReportGenerator
from simulator.personas import get_all_persona_names


def create_parser():
    """Create and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="Симулятор диалогов для тестирования CRM Sales Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python -m src.simulator -n 50                    # 50 симуляций
  python -m src.simulator -n 50 -o report.txt      # С сохранением в файл
  python -m src.simulator -n 20 --persona skeptic  # Только скептики
  python -m src.simulator -n 100 -p 4              # 4 параллельных потока
  python -m src.simulator --e2e                    # 20 техник × 5 персон = 100 тестов
  python -m src.simulator --e2e --personas 3       # 20 техник × 3 персоны = 60 тестов
  python -m src.simulator --e2e-flow challenger    # 1 техника × 5 персон = 5 тестов
  python -m src.simulator --e2e --seed 42          # Воспроизводимый выбор персон
        """
    )

    parser.add_argument(
        "--count", "-n",
        type=int,
        default=50,
        help="Количество симуляций (по умолчанию: 50)"
    )

    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=8,
        help="Количество параллельных потоков (по умолчанию: 8)"
    )

    parser.add_argument(
        "--persona",
        choices=get_all_persona_names() + ["all"],
        default="all",
        help="Фильтр по персоне (по умолчанию: all)"
    )

    parser.add_argument(
        "--output", "-o",
        help="Файл для сохранения полного отчёта"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод"
    )

    parser.add_argument(
        "--no-dialogues",
        action="store_true",
        help="Не включать полные диалоги в отчёт"
    )

    # E2E Testing arguments
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Запустить e2e тесты всех 20 техник продаж"
    )

    parser.add_argument(
        "--e2e-flow",
        type=str,
        metavar="FLOW",
        help="Запустить e2e тест для конкретного flow (например: challenger)"
    )

    parser.add_argument(
        "--flow",
        type=str,
        metavar="FLOW",
        help="Использовать конкретный flow для обычных симуляций"
    )

    parser.add_argument(
        "--personas",
        type=int,
        default=5,
        metavar="N",
        help="Количество рандомных персон на каждую технику в e2e режиме (по умолчанию: 5)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="SEED",
        help="Random seed для воспроизводимости выбора персон"
    )

    return parser


def run_e2e_mode(args):
    """
    Run E2E testing mode for sales techniques.

    Tests all 20 (or a specific) sales technique flows.
    Each technique is tested with N random personas (default: 5).
    """
    from simulator.e2e_scenarios import (
        ALL_SCENARIOS,
        get_scenario_by_flow,
        expand_scenarios_with_personas
    )
    from simulator.report import generate_e2e_report

    # Заголовок
    print()
    print("=" * 60)
    print("E2E TEST: SALES TECHNIQUES")
    print("=" * 60)
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Determine which scenarios to run
    if args.e2e_flow:
        base_scenario = get_scenario_by_flow(args.e2e_flow)
        if not base_scenario:
            print(f"ОШИБКА: Flow '{args.e2e_flow}' не найден")
            print("Доступные flows:")
            for s in ALL_SCENARIOS:
                print(f"  - {s.flow}")
            sys.exit(1)
        # Expand single flow with random personas
        scenarios = expand_scenarios_with_personas(
            scenarios=[base_scenario],
            personas_per_scenario=args.personas,
            seed=args.seed
        )
        print(f"Flow: {args.e2e_flow}")
        print(f"Персон на технику: {args.personas}")
    else:
        # Expand all scenarios with random personas
        scenarios = expand_scenarios_with_personas(
            scenarios=ALL_SCENARIOS,
            personas_per_scenario=args.personas,
            seed=args.seed
        )
        print(f"Техник: {len(ALL_SCENARIOS)}")
        print(f"Персон на технику: {args.personas}")
        print(f"Всего тестов: {len(scenarios)}")

    if args.output:
        print(f"Вывод в: {args.output}")
    print("=" * 60)
    print()

    try:
        # Инициализация Ollama
        print("Инициализация Ollama...")
        from llm import OllamaClient
        llm = OllamaClient()

        # Прогрев Ollama
        print("Прогрев Ollama (загрузка модели в VRAM)...")
        import requests
        from settings import settings

        warmup_success = False
        warmup_url = f"{settings.llm.base_url.rstrip('/')}/api/chat"
        for attempt in range(5):
            try:
                response = requests.post(
                    warmup_url,
                    json={
                        "model": settings.llm.model,
                        "messages": [{"role": "user", "content": "привет"}],
                        "stream": False,
                        "options": {"num_predict": 10}
                    },
                    timeout=120
                )
                if response.status_code == 200:
                    warmup_success = True
                    print(f"  Модель загружена: {settings.llm.model}")
                    break
                else:
                    print(f"  Попытка {attempt + 1}/5: загрузка модели...")
                    import time
                    time.sleep(3)
            except Exception as e:
                print(f"  Попытка {attempt + 1}/5: {e}")
                import time
                time.sleep(3)

        if not warmup_success:
            print("ОШИБКА: Не удалось подключиться к Ollama.")
            print("Запустите: ./scripts/start_ollama.sh")
            sys.exit(1)

        if hasattr(llm, 'reset_circuit_breaker'):
            llm.reset_circuit_breaker()

        print("Ollama готов")
        print()

    except Exception as e:
        print(f"ОШИБКА при инициализации Ollama: {e}")
        print("Запустите: ./scripts/start_ollama.sh")
        sys.exit(1)

    # Создаём runner
    runner = SimulationRunner(bot_llm=llm, client_llm=llm, verbose=args.verbose)

    # Запускаем e2e тесты
    print(f"Запуск {len(scenarios)} e2e тестов...")
    print("-" * 60)

    completed = [0]
    passed_count = [0]

    def progress_callback(result):
        completed[0] += 1
        if result.passed:
            passed_count[0] += 1
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{completed[0]:2d}/{len(scenarios)}] {status} {result.scenario_name:25s} "
              f"→ {result.outcome:12s} (score: {result.score:.2f})")

    results = runner.run_e2e_batch(scenarios, progress_callback=progress_callback, parallel=args.parallel)

    print("-" * 60)
    print()

    # Сводка результатов
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total:     {total}")
    print(f"Passed:    {passed} ({pass_rate:.1f}%)")
    print(f"Failed:    {failed}")
    print(f"Avg Score: {avg_score:.2f}")
    print()

    # Детали по каждому тесту - группируем по техникам
    print("RESULTS BY TECHNIQUE")
    print("-" * 60)

    # Группируем результаты по flow
    from collections import defaultdict
    results_by_flow = defaultdict(list)
    for r in results:
        results_by_flow[r.flow_name].append(r)

    for flow_name in sorted(results_by_flow.keys()):
        flow_results = results_by_flow[flow_name]
        flow_passed = sum(1 for r in flow_results if r.passed)
        flow_total = len(flow_results)
        flow_avg_score = sum(r.score for r in flow_results) / flow_total

        # Заголовок техники
        flow_status = "✓" if flow_passed == flow_total else "○" if flow_passed > 0 else "✗"
        print(f"\n  {flow_status} {flow_name.upper()} ({flow_passed}/{flow_total}, avg: {flow_avg_score:.2f})")

        # Детали по каждой персоне
        for r in flow_results:
            status = "PASS" if r.passed else "FAIL"
            # Извлекаем персону из scenario_id (формат: "01_skeptic")
            persona = r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"
            print(f"      {status} {persona:18s} → {r.outcome:12s} (score: {r.score:.2f})")

    print()

    # Сохранение отчёта
    if args.output:
        report_data = generate_e2e_report(results, args.output)
        print(f"Отчёт сохранён: {args.output}")

        # Показываем размер файла
        size = os.path.getsize(args.output)
        if size > 1024 * 1024:
            print(f"Размер: {size / 1024 / 1024:.1f} MB")
        elif size > 1024:
            print(f"Размер: {size / 1024:.1f} KB")
        else:
            print(f"Размер: {size} bytes")

    print()
    print("Готово!")

    # Exit code based on pass rate
    if pass_rate < 70:
        print(f"\nWARNING: Pass rate {pass_rate:.1f}% is below 70% threshold")
        sys.exit(1)


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Dispatch to e2e mode if requested
    if args.e2e or args.e2e_flow:
        run_e2e_mode(args)
        return

    # Заголовок
    print()
    print("=" * 60)
    print("СИМУЛЯТОР ДИАЛОГОВ CRM SALES BOT")
    print("=" * 60)
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Симуляций: {args.count}")
    print(f"Параллельность: {args.parallel}")
    print(f"Персона: {args.persona}")
    if args.flow:
        print(f"Flow: {args.flow}")
    if args.output:
        print(f"Вывод в: {args.output}")
    print("=" * 60)
    print()

    try:
        # Импортируем Ollama
        print("Инициализация Ollama...")
        from llm import OllamaClient
        llm = OllamaClient()

        # Прогрев Ollama - делаем тестовый запрос чтобы модель загрузилась
        print("Прогрев Ollama (загрузка модели в VRAM)...")
        import requests
        from settings import settings

        warmup_success = False
        warmup_url = f"{settings.llm.base_url.rstrip('/')}/api/chat"
        for attempt in range(5):
            try:
                response = requests.post(
                    warmup_url,
                    json={
                        "model": settings.llm.model,
                        "messages": [{"role": "user", "content": "привет"}],
                        "stream": False,
                        "options": {"num_predict": 10}
                    },
                    timeout=120
                )
                if response.status_code == 200:
                    warmup_success = True
                    print(f"  Модель загружена: {settings.llm.model}")
                    break
                else:
                    print(f"  Попытка {attempt + 1}/5: загрузка модели...")
                    import time
                    time.sleep(3)
            except Exception as e:
                print(f"  Попытка {attempt + 1}/5: {e}")
                import time
                time.sleep(3)

        if not warmup_success:
            print("ОШИБКА: Не удалось подключиться к Ollama.")
            print("Запустите: ./scripts/start_ollama.sh")
            sys.exit(1)

        # Сбрасываем circuit breaker если он есть
        if hasattr(llm, 'reset_circuit_breaker'):
            llm.reset_circuit_breaker()

        print("Ollama готов")
        print()

    except Exception as e:
        print(f"ОШИБКА при инициализации Ollama: {e}")
        print("Запустите: ./scripts/start_ollama.sh")
        sys.exit(1)

    # Создаём runner
    runner = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,
        verbose=args.verbose,
        flow_name=args.flow
    )

    # Запускаем симуляции
    print(f"Запуск {args.count} симуляций...")
    print("-" * 60)

    completed = [0]

    def progress_callback(result):
        completed[0] += 1
        status = "✓" if result.outcome in ["success", "soft_close"] else "✗"
        print(f"  [{completed[0]:3d}/{args.count}] {status} {result.persona:15s} → {result.outcome:12s} ({result.turns} ходов)")

    results = runner.run_batch(
        count=args.count,
        parallel=args.parallel,
        persona_filter=args.persona if args.persona != "all" else None,
        progress_callback=progress_callback
    )

    print("-" * 60)
    print(f"Завершено: {len(results)} симуляций")
    print()

    # Генерируем отчёт
    reporter = ReportGenerator()

    # Краткая сводка в консоль
    console_summary = reporter.generate_console_summary(results)
    print(console_summary)

    # Полный отчёт в файл
    if args.output:
        include_dialogues = not args.no_dialogues
        reporter.save_report(results, args.output, include_dialogues=include_dialogues)
        print(f"\nПолный отчёт сохранён: {args.output}")

        # Показываем размер файла
        size = os.path.getsize(args.output)
        if size > 1024 * 1024:
            print(f"Размер: {size / 1024 / 1024:.1f} MB")
        elif size > 1024:
            print(f"Размер: {size / 1024:.1f} KB")
        else:
            print(f"Размер: {size} bytes")

    print()
    print("Готово!")


if __name__ == "__main__":
    main()
