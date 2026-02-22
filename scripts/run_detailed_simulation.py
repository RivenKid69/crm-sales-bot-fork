#!/usr/bin/env python3
"""
РАСШИРЕННАЯ СИМУЛЯЦИЯ CRM SALES BOT

Запускает полную симуляцию с детальным логированием:
- 100 диалогов (20 флоу × 5 персон)
- 8 параллельных потоков
- Qwen3 14B через Ollama
- Детальные метрики и трейсинг
- JSON и TXT отчеты с датой/временем

Использование:
    python scripts/run_detailed_simulation.py
"""

import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

# Добавляем путь к src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import psutil
import requests
from colorama import init, Fore, Style

# Инициализация colorama
init(autoreset=True)


def print_header(text: str):
    """Красивый заголовок"""
    print()
    print(Fore.CYAN + "=" * 80)
    print(Fore.CYAN + text.center(80))
    print(Fore.CYAN + "=" * 80)
    print()


def print_section(text: str):
    """Заголовок секции"""
    print()
    print(Fore.YELLOW + f"[{text}]")
    print(Fore.YELLOW + "-" * 80)


def print_success(text: str):
    """Успешное сообщение"""
    print(Fore.GREEN + f"✓ {text}")


def print_error(text: str):
    """Сообщение об ошибке"""
    print(Fore.RED + f"✗ {text}")


def print_info(text: str):
    """Информационное сообщение"""
    print(Fore.BLUE + f"ℹ {text}")


def check_ollama() -> bool:
    """Проверка доступности Ollama"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_qwen3_model() -> bool:
    """Проверка наличия модели Qwen3 14B"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any("ministral-3:14b-instruct-2512-q8_0" in m for m in models)
    except Exception:
        return False
    return False


def get_system_info() -> dict:
    """Получить информацию о системе"""
    info = {
        "timestamp": datetime.now().isoformat(),
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "memory_available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 2),
        "memory_percent": psutil.virtual_memory().percent,
    }

    # Попытка получить информацию о GPU
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=gpu_name,memory.total,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            gpu_data = result.stdout.strip().split(", ")
            if len(gpu_data) >= 4:
                info["gpu_name"] = gpu_data[0]
                info["gpu_memory_total_mb"] = int(gpu_data[1])
                info["gpu_memory_free_mb"] = int(gpu_data[2])
                info["gpu_utilization_percent"] = int(gpu_data[3])
    except Exception:
        pass

    return info


def main():
    """Основная функция"""
    print_header("CRM SALES BOT - ПОЛНАЯ ДЕТАЛЬНАЯ СИМУЛЯЦИЯ")

    # Параметры
    PARALLEL_THREADS = 8
    PERSONAS_PER_FLOW = 8
    TOTAL_FLOWS = 20
    TOTAL_SIMULATIONS = TOTAL_FLOWS * PERSONAS_PER_FLOW

    # Создаем директорию для отчетов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path(f"./reports/simulation_{timestamp}")
    report_dir.mkdir(parents=True, exist_ok=True)

    log_file = report_dir / f"simulation_{timestamp}.log"
    metrics_file = report_dir / f"metrics_{timestamp}.json"
    full_report = report_dir / f"full_report_{timestamp}.txt"
    system_info_file = report_dir / f"system_info_{timestamp}.json"

    print_info(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info(f"Директория отчетов: {report_dir}")
    print()

    print(Fore.CYAN + "Параметры симуляции:")
    print(f"  • Модель: Qwen3 14B (Ollama)")
    print(f"  • Всего диалогов: {TOTAL_SIMULATIONS}")
    print(f"  • Количество флоу: {TOTAL_FLOWS}")
    print(f"  • Персон на флоу: {PERSONAS_PER_FLOW}")
    print(f"  • Параллельных потоков: {PARALLEL_THREADS}")

    # Информация о системе
    print_section("Информация о системе")
    system_info = get_system_info()

    print(f"  • CPU: {system_info['cpu_count']} ядер")
    print(f"  • RAM: {system_info['memory_available_gb']} GB / {system_info['memory_total_gb']} GB свободно")

    if "gpu_name" in system_info:
        print(f"  • GPU: {system_info['gpu_name']}")
        print(f"  • VRAM: {system_info['gpu_memory_free_mb']} MB / {system_info['gpu_memory_total_mb']} MB свободно")

    # Сохраняем system info
    with open(system_info_file, "w", encoding="utf-8") as f:
        json.dump(system_info, f, indent=2, ensure_ascii=False)

    print_success(f"Информация о системе сохранена: {system_info_file}")

    # Проверка Ollama
    print_section("Проверка Ollama")

    if check_ollama():
        print_success("Ollama запущен и доступен")
    else:
        print_error("Ollama не запущен!")
        print_info("Запустите: ./scripts/start_ollama.sh")
        sys.exit(1)

    # Проверка модели
    print_section("Проверка модели Qwen3 14B")

    if check_qwen3_model():
        print_success("Модель ministral-3:14b-instruct-2512-q8_0 установлена")
    else:
        print_error("Модель ministral-3:14b-instruct-2512-q8_0 не найдена!")
        print_info("Скачайте: ollama pull ministral-3:14b-instruct-2512-q8_0")
        sys.exit(1)

    # Настройка окружения
    print_section("Настройка окружения")

    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["OMP_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["OPENBLAS_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["NUMEXPR_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"

    print_success("Переменные окружения настроены")
    print(f"  • CUDA_VISIBLE_DEVICES: {os.environ['CUDA_VISIBLE_DEVICES']}")
    print(f"  • OMP_NUM_THREADS: {os.environ['OMP_NUM_THREADS']}")

    # Запуск симуляции
    print_header("ЗАПУСК СИМУЛЯЦИИ")
    print(f"Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Всего диалогов: {TOTAL_SIMULATIONS}")
    print(f"Параллельность: {PARALLEL_THREADS}")
    print()

    start_time = time.time()

    try:
        # Импорт модулей
        from src.llm import OllamaClient
        from src.simulator.runner import SimulationRunner
        from src.simulator.e2e_scenarios import ALL_SCENARIOS, expand_scenarios_with_personas
        from src.simulator.report import generate_e2e_report

        # Инициализация LLM
        print_info("Инициализация Ollama client...")
        llm = OllamaClient()

        # Прогрев модели
        print_info("Прогрев модели (загрузка в VRAM)...")
        warmup_response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "ministral-3:14b-instruct-2512-q8_0",
                "messages": [{"role": "user", "content": "Привет"}],
                "stream": False,
                "options": {"num_predict": 10}
            },
            timeout=120
        )

        if warmup_response.status_code == 200:
            print_success("Модель загружена в VRAM")
        else:
            print_error("Ошибка прогрева модели")
            sys.exit(1)

        # Сброс circuit breaker
        if hasattr(llm, 'reset_circuit_breaker'):
            llm.reset_circuit_breaker()

        # Прогрев embedding моделей
        print_info("Прогрев embedding моделей...")
        try:
            from src.tone_analyzer.semantic_analyzer import get_semantic_tone_analyzer
            analyzer = get_semantic_tone_analyzer()
            if analyzer.is_available:
                print_success("Semantic tone analyzer: готов")
            else:
                print_info("Semantic tone analyzer: недоступен")
        except Exception as e:
            print_info(f"Semantic tone analyzer: ошибка - {e}")

        try:
            from src.knowledge.reranker import get_reranker
            reranker = get_reranker()
            if reranker.is_available():
                print_success("Reranker: готов")
            else:
                print_info("Reranker: недоступен")
        except Exception as e:
            print_info(f"Reranker: ошибка - {e}")

        # Генерация сценариев
        print_info(f"Генерация {TOTAL_SIMULATIONS} сценариев...")
        scenarios = expand_scenarios_with_personas(
            scenarios=ALL_SCENARIOS,
            personas_per_scenario=PERSONAS_PER_FLOW,
            seed=None
        )
        print_success(f"Сгенерировано {len(scenarios)} сценариев")

        # Создание runner
        runner = SimulationRunner(
            bot_llm=llm,
            client_llm=llm,
            verbose=True
        )

        # Запуск симуляций
        print()
        print(Fore.GREEN + Style.BRIGHT + f"Запуск {len(scenarios)} симуляций...")
        print(Fore.CYAN + "-" * 80)

        completed = [0]
        passed_count = [0]

        def progress_callback(result):
            completed[0] += 1
            if result.passed:
                passed_count[0] += 1

            status = Fore.GREEN + "PASS" if result.passed else Fore.RED + "FAIL"
            print(f"  [{completed[0]:3d}/{len(scenarios)}] {status} {Style.RESET_ALL}"
                  f"{result.scenario_name:30s} → {result.outcome:12s} (score: {result.score:.2f})")

        results = runner.run_e2e_batch(
            scenarios,
            progress_callback=progress_callback,
            parallel=PARALLEL_THREADS
        )

        print(Fore.CYAN + "-" * 80)
        print()

        # Итоги
        end_time = time.time()
        duration = end_time - start_time

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        avg_score = sum(r.score for r in results) / total if total > 0 else 0.0
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        print_header("ИТОГИ СИМУЛЯЦИИ")

        print(Fore.CYAN + "Результаты:")
        print(f"  • Всего: {total}")
        print(f"  • Успешно: {Fore.GREEN}{passed}{Style.RESET_ALL} ({pass_rate:.1f}%)")
        print(f"  • Провалено: {Fore.RED}{failed}{Style.RESET_ALL}")
        print(f"  • Средний score: {avg_score:.2f}")
        print(f"  • Время выполнения: {duration:.1f} сек ({duration / 60:.1f} мин)")
        print(f"  • Среднее время на диалог: {duration / total:.1f} сек")

        # Сохранение отчетов
        print_section("Сохранение отчетов")

        # Детальный TXT отчет
        report_data = generate_e2e_report(results, str(full_report))
        print_success(f"Полный отчет: {full_report}")

        # JSON метрики
        metrics_data = {
            "timestamp": datetime.now().isoformat(),
            "parameters": {
                "total_simulations": TOTAL_SIMULATIONS,
                "total_flows": TOTAL_FLOWS,
                "personas_per_flow": PERSONAS_PER_FLOW,
                "parallel_threads": PARALLEL_THREADS,
                "model": "ministral-3:14b-instruct-2512-q8_0",
            },
            "results": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": pass_rate,
                "avg_score": avg_score,
            },
            "performance": {
                "duration_seconds": duration,
                "duration_minutes": duration / 60,
                "avg_time_per_dialog": duration / total if total > 0 else 0,
            },
            "system_info": system_info,
            "detailed_results": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_name": r.scenario_name,
                    "flow": r.flow_name,
                    "persona": r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown",
                    "passed": r.passed,
                    "outcome": r.outcome,
                    "score": r.score,
                    "phases_reached": r.phases_reached,
                    "coverage": r.details.get("phases", {}).get("coverage", 0.0),
                }
                for r in results
            ]
        }

        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2, ensure_ascii=False)

        print_success(f"Метрики (JSON): {metrics_file}")

        # Размеры файлов
        print()
        print(Fore.CYAN + "Размеры файлов:")
        for file_path in [full_report, metrics_file, log_file, system_info_file]:
            if file_path.exists():
                size = file_path.stat().st_size
                if size > 1024 * 1024:
                    size_str = f"{size / 1024 / 1024:.2f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.2f} KB"
                else:
                    size_str = f"{size} bytes"
                print(f"  • {file_path.name}: {size_str}")

        # Финальная информация о системе
        print_section("Использование ресурсов")
        final_system_info = get_system_info()

        print(f"  • CPU: {final_system_info['cpu_percent']}%")
        print(f"  • RAM: {final_system_info['memory_percent']}% "
              f"({final_system_info['memory_available_gb']} GB свободно)")

        if "gpu_utilization_percent" in final_system_info:
            print(f"  • GPU: {final_system_info['gpu_utilization_percent']}%")
            print(f"  • VRAM: {final_system_info['gpu_memory_free_mb']} MB свободно")

        print()
        print_success("Симуляция успешно завершена!")
        print()
        print(Fore.YELLOW + "Просмотр отчетов:")
        print(f"  less {full_report}")
        print(f"  cat {metrics_file} | jq")
        print()

        # Exit code based on pass rate
        if pass_rate < 70:
            print(Fore.RED + f"WARNING: Pass rate {pass_rate:.1f}% ниже порога 70%")
            sys.exit(1)

    except KeyboardInterrupt:
        print()
        print_error("Симуляция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print()
        print_error(f"Ошибка симуляции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
