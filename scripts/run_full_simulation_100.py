#!/usr/bin/env python3
"""
ПОЛНАЯ ДЕТАЛЬНАЯ СИМУЛЯЦИЯ CRM SALES BOT - 100 ДИАЛОГОВ

Параметры:
- 100 диалогов (случайная выборка из 20 флоу × 8 персон)
- 8 параллельных потоков (GPU + CPU)
- Qwen3 14B через Ollama
- Полное логирование всех метрик
- Отчеты с точной датой и временем

Использование:
    python scripts/run_full_simulation_100.py
"""

import sys
import os
import json
import time
import random
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Добавляем путь к src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import psutil
import requests
from colorama import init, Fore, Style

# Инициализация colorama
init(autoreset=True)

# =============================================================================
# ПАРАМЕТРЫ СИМУЛЯЦИИ
# =============================================================================
TOTAL_DIALOGS = 100
TOTAL_FLOWS = 20
TOTAL_PERSONAS = 8
PARALLEL_THREADS = 8  # GPU и CPU потоки
MODEL_NAME = "qwen3:14b"
OLLAMA_URL = "http://localhost:11434"

# =============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# =============================================================================
def setup_logging(log_file: Path) -> logging.Logger:
    """Настройка детального логирования"""
    logger = logging.getLogger('simulation')
    logger.setLevel(logging.DEBUG)

    # Форматтер с детальной информацией
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(threadName)-12s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Файловый handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    # Консольный handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


# =============================================================================
# УТИЛИТЫ ВЫВОДА
# =============================================================================
def print_header(text: str):
    """Красивый заголовок"""
    print()
    print(Fore.CYAN + "=" * 100)
    print(Fore.CYAN + Style.BRIGHT + text.center(100))
    print(Fore.CYAN + "=" * 100)
    print()


def print_section(text: str):
    """Заголовок секции"""
    print()
    print(Fore.YELLOW + Style.BRIGHT + f"[{text}]")
    print(Fore.YELLOW + "-" * 100)


def print_success(text: str):
    print(Fore.GREEN + f"[OK] {text}")


def print_error(text: str):
    print(Fore.RED + f"[ERROR] {text}")


def print_info(text: str):
    print(Fore.BLUE + f"[INFO] {text}")


def print_metric(name: str, value: Any, unit: str = ""):
    print(f"  {Fore.CYAN}{name:.<40} {Fore.WHITE}{value} {unit}")


# =============================================================================
# ПРОВЕРКА СИСТЕМЫ
# =============================================================================
def check_ollama() -> bool:
    """Проверка доступности Ollama"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_model(model_name: str) -> bool:
    """Проверка наличия модели"""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(model_name in m for m in models)
    except Exception:
        return False
    return False


def get_gpu_info() -> Dict[str, Any]:
    """Детальная информация о GPU"""
    import subprocess
    try:
        result = subprocess.run([
            "nvidia-smi",
            "--query-gpu=gpu_name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu,power.draw,power.limit",
            "--format=csv,noheader,nounits"
        ], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 8:
                return {
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_free_mb": int(parts[2]),
                    "memory_used_mb": int(parts[3]),
                    "utilization_percent": int(parts[4]),
                    "temperature_c": int(parts[5]),
                    "power_draw_w": float(parts[6]) if parts[6] != "[N/A]" else 0,
                    "power_limit_w": float(parts[7]) if parts[7] != "[N/A]" else 0,
                }
    except Exception:
        pass
    return {}


def get_system_info() -> Dict[str, Any]:
    """Полная информация о системе"""
    info = {
        "timestamp": datetime.now().isoformat(),
        "cpu": {
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "percent_total": psutil.cpu_percent(interval=1),
            "percent_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
            "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 2),
            "used_gb": round(psutil.virtual_memory().used / (1024 ** 3), 2),
            "percent": psutil.virtual_memory().percent,
        },
        "gpu": get_gpu_info(),
    }
    return info


def warmup_model(logger: logging.Logger) -> bool:
    """Прогрев модели - загрузка в VRAM"""
    logger.info("Прогрев модели Qwen3 14B (загрузка в VRAM)...")

    try:
        start = time.time()
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": "Привет! Готов к работе?"}],
                "stream": False,
                "options": {
                    "num_predict": 20,
                    "num_ctx": 4096,
                    "num_thread": PARALLEL_THREADS,
                    "num_gpu": 99,  # Использовать все GPU слои
                }
            },
            timeout=180
        )

        elapsed = time.time() - start

        if response.status_code == 200:
            logger.info(f"Модель загружена в VRAM за {elapsed:.1f} сек")
            return True
        else:
            logger.error(f"Ошибка прогрева: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Ошибка прогрева модели: {e}")
        return False


# =============================================================================
# МОНИТОРИНГ В РЕАЛЬНОМ ВРЕМЕНИ
# =============================================================================
class ResourceMonitor:
    """Мониторинг ресурсов во время симуляции"""

    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self.running = False
        self.thread = None
        self.samples: List[Dict] = []

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _monitor_loop(self):
        while self.running:
            sample = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
            }

            gpu_info = get_gpu_info()
            if gpu_info:
                sample["gpu_utilization"] = gpu_info.get("utilization_percent", 0)
                sample["gpu_memory_used_mb"] = gpu_info.get("memory_used_mb", 0)
                sample["gpu_temperature_c"] = gpu_info.get("temperature_c", 0)

            self.samples.append(sample)
            time.sleep(self.interval)

    def get_summary(self) -> Dict[str, Any]:
        if not self.samples:
            return {}

        return {
            "samples_count": len(self.samples),
            "cpu_avg": sum(s["cpu_percent"] for s in self.samples) / len(self.samples),
            "cpu_max": max(s["cpu_percent"] for s in self.samples),
            "memory_avg": sum(s["memory_percent"] for s in self.samples) / len(self.samples),
            "memory_max": max(s["memory_percent"] for s in self.samples),
            "gpu_utilization_avg": sum(s.get("gpu_utilization", 0) for s in self.samples) / len(self.samples),
            "gpu_utilization_max": max(s.get("gpu_utilization", 0) for s in self.samples),
            "gpu_memory_max_mb": max(s.get("gpu_memory_used_mb", 0) for s in self.samples),
            "gpu_temperature_max_c": max(s.get("gpu_temperature_c", 0) for s in self.samples),
        }


# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================
def main():
    """Основная функция симуляции"""

    # Timestamp для файлов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp_readable = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print_header(f"CRM SALES BOT - ПОЛНАЯ СИМУЛЯЦИЯ 100 ДИАЛОГОВ")
    print_info(f"Дата и время запуска: {timestamp_readable}")

    # Создаем директорию для отчетов
    report_dir = Path(f"./reports/simulation_{timestamp}")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Файлы отчетов
    log_file = report_dir / f"simulation_log_{timestamp}.log"
    metrics_file = report_dir / f"metrics_{timestamp}.json"
    full_report = report_dir / f"full_report_{timestamp}.txt"
    system_info_file = report_dir / f"system_info_{timestamp}.json"
    detailed_results_file = report_dir / f"detailed_results_{timestamp}.json"
    resource_monitor_file = report_dir / f"resource_monitoring_{timestamp}.json"

    # Настройка логирования
    logger = setup_logging(log_file)
    logger.info("=" * 80)
    logger.info(f"НАЧАЛО СИМУЛЯЦИИ: {timestamp_readable}")
    logger.info("=" * 80)

    # ==========================================================================
    # ПАРАМЕТРЫ
    # ==========================================================================
    print_section("ПАРАМЕТРЫ СИМУЛЯЦИИ")
    print_metric("Всего диалогов", TOTAL_DIALOGS)
    print_metric("Количество флоу", TOTAL_FLOWS)
    print_metric("Количество персон", TOTAL_PERSONAS)
    print_metric("Параллельных потоков", PARALLEL_THREADS)
    print_metric("Модель", MODEL_NAME)
    print_metric("Ollama URL", OLLAMA_URL)
    print_metric("Директория отчетов", str(report_dir))

    logger.info(f"Параметры: диалогов={TOTAL_DIALOGS}, флоу={TOTAL_FLOWS}, "
                f"персон={TOTAL_PERSONAS}, потоков={PARALLEL_THREADS}")

    # ==========================================================================
    # НАСТРОЙКА ОКРУЖЕНИЯ ДЛЯ GPU/CPU
    # ==========================================================================
    print_section("НАСТРОЙКА ОКРУЖЕНИЯ (8 ПОТОКОВ GPU/CPU)")

    # GPU
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["CUDA_LAUNCH_BLOCKING"] = "0"

    # CPU потоки
    os.environ["OMP_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["OPENBLAS_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["NUMEXPR_NUM_THREADS"] = str(PARALLEL_THREADS)
    os.environ["VECLIB_MAXIMUM_THREADS"] = str(PARALLEL_THREADS)

    # PyTorch оптимизация
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"
    os.environ["TOKENIZERS_PARALLELISM"] = "true"

    print_success("CUDA_VISIBLE_DEVICES=0")
    print_success(f"OMP_NUM_THREADS={PARALLEL_THREADS}")
    print_success(f"MKL_NUM_THREADS={PARALLEL_THREADS}")
    print_success(f"OPENBLAS_NUM_THREADS={PARALLEL_THREADS}")
    print_success(f"NUMEXPR_NUM_THREADS={PARALLEL_THREADS}")
    print_success("PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512")

    logger.info("Переменные окружения настроены для 8 потоков")

    # ==========================================================================
    # ИНФОРМАЦИЯ О СИСТЕМЕ
    # ==========================================================================
    print_section("ИНФОРМАЦИЯ О СИСТЕМЕ")

    system_info = get_system_info()

    print_metric("CPU ядер (физ./лог.)",
                 f"{system_info['cpu']['cores_physical']} / {system_info['cpu']['cores_logical']}")
    print_metric("CPU частота", f"{system_info['cpu']['freq_mhz']:.0f}", "MHz")
    print_metric("RAM всего", system_info['memory']['total_gb'], "GB")
    print_metric("RAM доступно", system_info['memory']['available_gb'], "GB")
    print_metric("RAM использовано", f"{system_info['memory']['percent']}", "%")

    if system_info['gpu']:
        gpu = system_info['gpu']
        print()
        print_metric("GPU", gpu.get('name', 'N/A'))
        print_metric("VRAM всего", gpu.get('memory_total_mb', 0), "MB")
        print_metric("VRAM свободно", gpu.get('memory_free_mb', 0), "MB")
        print_metric("GPU загрузка", gpu.get('utilization_percent', 0), "%")
        print_metric("GPU температура", gpu.get('temperature_c', 0), "C")
        print_metric("GPU мощность", f"{gpu.get('power_draw_w', 0):.1f} / {gpu.get('power_limit_w', 0):.1f}", "W")

    # Сохраняем system info
    with open(system_info_file, "w", encoding="utf-8") as f:
        json.dump(system_info, f, indent=2, ensure_ascii=False)
    print_success(f"Системная информация сохранена: {system_info_file.name}")

    logger.info(f"Система: CPU={system_info['cpu']['cores_logical']} ядер, "
                f"RAM={system_info['memory']['total_gb']}GB, "
                f"GPU={system_info['gpu'].get('name', 'N/A')}")

    # ==========================================================================
    # ПРОВЕРКА OLLAMA
    # ==========================================================================
    print_section("ПРОВЕРКА OLLAMA")

    if check_ollama():
        print_success("Ollama запущен и доступен")
        logger.info("Ollama: OK")
    else:
        print_error("Ollama не запущен!")
        print_info("Запустите: ./scripts/start_ollama.sh")
        logger.error("Ollama не доступен!")
        sys.exit(1)

    if check_model(MODEL_NAME):
        print_success(f"Модель {MODEL_NAME} установлена")
        logger.info(f"Модель {MODEL_NAME}: OK")
    else:
        print_error(f"Модель {MODEL_NAME} не найдена!")
        print_info(f"Скачайте: ollama pull {MODEL_NAME}")
        logger.error(f"Модель {MODEL_NAME} не найдена!")
        sys.exit(1)

    # Прогрев модели
    if not warmup_model(logger):
        print_error("Не удалось загрузить модель в VRAM")
        sys.exit(1)
    print_success("Модель загружена в VRAM и готова к работе")

    # ==========================================================================
    # ИМПОРТ МОДУЛЕЙ СИМУЛЯТОРА
    # ==========================================================================
    print_section("ИНИЦИАЛИЗАЦИЯ СИМУЛЯТОРА")

    try:
        from llm import OllamaClient
        from simulator.runner import SimulationRunner
        from simulator.e2e_scenarios import ALL_SCENARIOS, expand_scenarios_with_personas
        from simulator.report import generate_e2e_report
        from simulator.personas import PERSONAS

        print_success("Модули симулятора импортированы")
        logger.info("Модули симулятора загружены")

    except ImportError as e:
        print_error(f"Ошибка импорта: {e}")
        logger.error(f"Ошибка импорта модулей: {e}")
        sys.exit(1)

    # ==========================================================================
    # ПРОГРЕВ EMBEDDING МОДЕЛЕЙ
    # ==========================================================================
    print_section("ПРОГРЕВ EMBEDDING МОДЕЛЕЙ")

    # Semantic tone analyzer
    try:
        from tone_analyzer.semantic_analyzer import get_semantic_tone_analyzer
        analyzer = get_semantic_tone_analyzer()
        if analyzer.is_available:
            print_success("Semantic Tone Analyzer: готов")
            logger.info("Semantic Tone Analyzer: OK")
        else:
            print_info("Semantic Tone Analyzer: недоступен")
            logger.warning("Semantic Tone Analyzer: недоступен")
    except Exception as e:
        print_info(f"Semantic Tone Analyzer: {e}")
        logger.warning(f"Semantic Tone Analyzer: {e}")

    # Reranker
    try:
        from knowledge.reranker import get_reranker
        reranker = get_reranker()
        if reranker.is_available():
            print_success("Reranker: готов")
            logger.info("Reranker: OK")
        else:
            print_info("Reranker: недоступен")
            logger.warning("Reranker: недоступен")
    except Exception as e:
        print_info(f"Reranker: {e}")
        logger.warning(f"Reranker: {e}")

    # ==========================================================================
    # ГЕНЕРАЦИЯ СЦЕНАРИЕВ
    # ==========================================================================
    print_section("ГЕНЕРАЦИЯ СЦЕНАРИЕВ")

    # Генерируем все возможные сценарии (20 флоу × 8 персон = 160)
    all_scenarios = expand_scenarios_with_personas(
        scenarios=ALL_SCENARIOS,
        personas_per_scenario=TOTAL_PERSONAS,
        seed=42  # Для воспроизводимости
    )

    print_info(f"Всего возможных комбинаций: {len(all_scenarios)}")
    logger.info(f"Сгенерировано {len(all_scenarios)} комбинаций (20×8)")

    # Выбираем случайные 100 сценариев
    if len(all_scenarios) > TOTAL_DIALOGS:
        random.seed(int(time.time()))
        scenarios = random.sample(all_scenarios, TOTAL_DIALOGS)
        print_info(f"Выбрано случайных сценариев: {len(scenarios)}")
    else:
        scenarios = all_scenarios

    # Статистика по флоу и персонам
    flows_used = set()
    personas_used = set()
    for s in scenarios:
        flows_used.add(s.flow)
        if hasattr(s, 'persona'):
            personas_used.add(s.persona)

    print_metric("Уникальных флоу", len(flows_used))
    print_metric("Уникальных персон", len(personas_used))
    print_success(f"Подготовлено {len(scenarios)} сценариев для симуляции")

    logger.info(f"Выбрано {len(scenarios)} сценариев из {len(all_scenarios)}")
    logger.info(f"Флоу: {len(flows_used)}, Персон: {len(personas_used)}")

    # ==========================================================================
    # ИНИЦИАЛИЗАЦИЯ LLM И RUNNER
    # ==========================================================================
    print_section("ИНИЦИАЛИЗАЦИЯ LLM")

    llm = OllamaClient()

    # Сброс circuit breaker если есть
    if hasattr(llm, 'reset_circuit_breaker'):
        llm.reset_circuit_breaker()
        print_success("Circuit breaker сброшен")

    runner = SimulationRunner(
        bot_llm=llm,
        client_llm=llm,
        verbose=True
    )

    print_success("SimulationRunner инициализирован")
    logger.info("SimulationRunner готов")

    # ==========================================================================
    # ЗАПУСК СИМУЛЯЦИИ
    # ==========================================================================
    print_header(f"ЗАПУСК СИМУЛЯЦИИ: {TOTAL_DIALOGS} ДИАЛОГОВ")

    print(Fore.CYAN + f"Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(Fore.CYAN + f"Параллельность: {PARALLEL_THREADS} потоков")
    print(Fore.CYAN + f"Модель: {MODEL_NAME}")
    print()
    print(Fore.YELLOW + "-" * 100)

    logger.info("=" * 60)
    logger.info("НАЧАЛО СИМУЛЯЦИИ")
    logger.info("=" * 60)

    # Запуск мониторинга ресурсов
    monitor = ResourceMonitor(interval=5.0)
    monitor.start()

    start_time = time.time()
    completed_count = [0]
    passed_count = [0]
    failed_count = [0]
    detailed_results = []
    lock = threading.Lock()

    def progress_callback(result):
        """Callback для отслеживания прогресса"""
        with lock:
            completed_count[0] += 1

            if result.passed:
                passed_count[0] += 1
                status = Fore.GREEN + "PASS"
            else:
                failed_count[0] += 1
                status = Fore.RED + "FAIL"

            # Детальная информация о результате
            result_info = {
                "index": completed_count[0],
                "timestamp": datetime.now().isoformat(),
                "scenario_id": result.scenario_id,
                "scenario_name": result.scenario_name,
                "flow": result.flow_name,
                "persona": result.scenario_id.split("_", 1)[1] if "_" in result.scenario_id else "unknown",
                "passed": result.passed,
                "outcome": result.outcome,
                "score": result.score,
                "phases_reached": result.phases_reached,
                "turn_count": result.details.get("turn_count", 0),
                "coverage": result.details.get("phases", {}).get("coverage", 0.0),
            }
            detailed_results.append(result_info)

            # Вывод в консоль
            progress = completed_count[0] / len(scenarios) * 100
            print(f"  [{completed_count[0]:3d}/{len(scenarios)}] ({progress:5.1f}%) "
                  f"{status}{Style.RESET_ALL} "
                  f"{result.scenario_name:35s} "
                  f"| {result.outcome:12s} "
                  f"| score: {result.score:.3f} "
                  f"| phases: {len(result.phases_reached)}")

            # Логирование
            logger.info(f"[{completed_count[0]}/{len(scenarios)}] "
                       f"{'PASS' if result.passed else 'FAIL'} "
                       f"{result.scenario_name} "
                       f"outcome={result.outcome} "
                       f"score={result.score:.3f}")

    # Запуск batch симуляции
    try:
        results = runner.run_e2e_batch(
            scenarios,
            progress_callback=progress_callback,
            parallel=PARALLEL_THREADS
        )
    except Exception as e:
        logger.error(f"Ошибка симуляции: {e}")
        print_error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Остановка мониторинга
    monitor.stop()

    end_time = time.time()
    duration = end_time - start_time

    print(Fore.YELLOW + "-" * 100)
    print()

    # ==========================================================================
    # РАСЧЕТ МЕТРИК
    # ==========================================================================
    print_header("ИТОГИ СИМУЛЯЦИИ")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0.0
    avg_score = sum(r.score for r in results) / total if total > 0 else 0.0

    # Метрики по outcome
    outcomes = {}
    for r in results:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1

    # Метрики по флоу
    flow_scores = {}
    for r in results:
        if r.flow_name not in flow_scores:
            flow_scores[r.flow_name] = []
        flow_scores[r.flow_name].append(r.score)

    flow_avg_scores = {
        flow: sum(scores) / len(scores)
        for flow, scores in flow_scores.items()
    }

    # Метрики по персонам
    persona_scores = {}
    for r in results:
        persona = r.scenario_id.split("_", 1)[1] if "_" in r.scenario_id else "unknown"
        if persona not in persona_scores:
            persona_scores[persona] = []
        persona_scores[persona].append(r.score)

    persona_avg_scores = {
        persona: sum(scores) / len(scores)
        for persona, scores in persona_scores.items()
    }

    # ==========================================================================
    # ВЫВОД ИТОГОВ
    # ==========================================================================
    print_section("ОБЩИЕ РЕЗУЛЬТАТЫ")
    print_metric("Всего диалогов", total)
    print_metric("Успешно (PASS)", f"{passed} ({pass_rate:.1f}%)")
    print_metric("Провалено (FAIL)", failed)
    print_metric("Средний score", f"{avg_score:.4f}")
    print_metric("Время выполнения", f"{duration:.1f} сек ({duration/60:.1f} мин)")
    print_metric("Среднее время на диалог", f"{duration/total:.2f} сек")
    print_metric("Производительность", f"{total/duration*60:.1f} диалогов/мин")

    print_section("РЕЗУЛЬТАТЫ ПО OUTCOME")
    for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        percent = count / total * 100
        print_metric(outcome, f"{count} ({percent:.1f}%)")

    print_section("ТОП-10 ФЛОУ ПО SCORE")
    sorted_flows = sorted(flow_avg_scores.items(), key=lambda x: -x[1])[:10]
    for i, (flow, score) in enumerate(sorted_flows, 1):
        count = len(flow_scores[flow])
        print(f"  {i:2d}. {Fore.CYAN}{flow:30s}{Style.RESET_ALL} "
              f"score: {Fore.GREEN}{score:.3f}{Style.RESET_ALL} "
              f"(n={count})")

    print_section("РЕЗУЛЬТАТЫ ПО ПЕРСОНАМ")
    sorted_personas = sorted(persona_avg_scores.items(), key=lambda x: -x[1])
    for persona, score in sorted_personas:
        count = len(persona_scores[persona])
        print_metric(persona, f"score: {score:.3f} (n={count})")

    # Мониторинг ресурсов
    resource_summary = monitor.get_summary()
    if resource_summary:
        print_section("ИСПОЛЬЗОВАНИЕ РЕСУРСОВ (за время симуляции)")
        print_metric("CPU средняя загрузка", f"{resource_summary['cpu_avg']:.1f}%")
        print_metric("CPU максимальная загрузка", f"{resource_summary['cpu_max']:.1f}%")
        print_metric("RAM средняя загрузка", f"{resource_summary['memory_avg']:.1f}%")
        print_metric("RAM максимальная загрузка", f"{resource_summary['memory_max']:.1f}%")
        print_metric("GPU средняя загрузка", f"{resource_summary['gpu_utilization_avg']:.1f}%")
        print_metric("GPU максимальная загрузка", f"{resource_summary['gpu_utilization_max']:.1f}%")
        print_metric("VRAM максимум", f"{resource_summary['gpu_memory_max_mb']} MB")
        print_metric("GPU температура макс", f"{resource_summary['gpu_temperature_max_c']} C")

    # ==========================================================================
    # СОХРАНЕНИЕ ОТЧЕТОВ
    # ==========================================================================
    print_header("СОХРАНЕНИЕ ОТЧЕТОВ")

    # 1. Полный TXT отчет
    report_data = generate_e2e_report(results, str(full_report))
    print_success(f"Полный отчет: {full_report.name}")

    # 2. JSON метрики
    metrics_data = {
        "metadata": {
            "timestamp": timestamp_readable,
            "timestamp_iso": datetime.now().isoformat(),
            "version": "1.0",
            "model": MODEL_NAME,
        },
        "parameters": {
            "total_dialogs": TOTAL_DIALOGS,
            "total_flows": TOTAL_FLOWS,
            "total_personas": TOTAL_PERSONAS,
            "parallel_threads": PARALLEL_THREADS,
        },
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate_percent": pass_rate,
            "avg_score": avg_score,
            "min_score": min(r.score for r in results) if results else 0,
            "max_score": max(r.score for r in results) if results else 0,
        },
        "performance": {
            "duration_seconds": duration,
            "duration_minutes": duration / 60,
            "avg_time_per_dialog_seconds": duration / total if total > 0 else 0,
            "dialogs_per_minute": total / duration * 60 if duration > 0 else 0,
        },
        "outcomes": outcomes,
        "flow_scores": {k: {"avg": v, "count": len(flow_scores[k])}
                       for k, v in flow_avg_scores.items()},
        "persona_scores": {k: {"avg": v, "count": len(persona_scores[k])}
                         for k, v in persona_avg_scores.items()},
        "system_info": system_info,
        "resource_monitoring": resource_summary,
    }

    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2, ensure_ascii=False)
    print_success(f"Метрики JSON: {metrics_file.name}")

    # 3. Детальные результаты
    with open(detailed_results_file, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "timestamp": timestamp_readable,
                "total_results": len(detailed_results),
            },
            "results": detailed_results
        }, f, indent=2, ensure_ascii=False)
    print_success(f"Детальные результаты: {detailed_results_file.name}")

    # 4. Мониторинг ресурсов
    with open(resource_monitor_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": resource_summary,
            "samples": monitor.samples
        }, f, indent=2, ensure_ascii=False)
    print_success(f"Мониторинг ресурсов: {resource_monitor_file.name}")

    # Размеры файлов
    print()
    print(Fore.CYAN + "Размеры файлов:")
    for file_path in [full_report, metrics_file, detailed_results_file,
                      resource_monitor_file, log_file, system_info_file]:
        if file_path.exists():
            size = file_path.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / 1024 / 1024:.2f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.2f} KB"
            else:
                size_str = f"{size} bytes"
            print(f"  {file_path.name}: {size_str}")

    # ==========================================================================
    # ФИНАЛ
    # ==========================================================================
    logger.info("=" * 60)
    logger.info("СИМУЛЯЦИЯ ЗАВЕРШЕНА")
    logger.info(f"Результат: {passed}/{total} PASS ({pass_rate:.1f}%)")
    logger.info(f"Средний score: {avg_score:.4f}")
    logger.info(f"Время: {duration:.1f} сек")
    logger.info("=" * 60)

    print()
    print_header("СИМУЛЯЦИЯ ЗАВЕРШЕНА")

    # Финальная статистика
    final_info = get_system_info()
    print(Fore.CYAN + "Финальное состояние системы:")
    print_metric("CPU", f"{final_info['cpu']['percent_total']}%")
    print_metric("RAM", f"{final_info['memory']['percent']}%")
    if final_info['gpu']:
        print_metric("GPU", f"{final_info['gpu'].get('utilization_percent', 0)}%")
        print_metric("VRAM используется", f"{final_info['gpu'].get('memory_used_mb', 0)} MB")

    print()
    print(Fore.GREEN + Style.BRIGHT + f"Директория с отчетами: {report_dir}")
    print()
    print(Fore.YELLOW + "Просмотр отчетов:")
    print(f"  less {full_report}")
    print(f"  cat {metrics_file} | python3 -m json.tool")
    print(f"  tail -f {log_file}")
    print()

    # Exit code
    if pass_rate < 70:
        print(Fore.RED + f"WARNING: Pass rate {pass_rate:.1f}% ниже порога 70%")
        sys.exit(1)

    print(Fore.GREEN + Style.BRIGHT + "Симуляция успешно завершена!")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_error("Симуляция прервана пользователем (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print()
        print_error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
