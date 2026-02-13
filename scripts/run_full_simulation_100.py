#!/usr/bin/env python3
"""
ПОЛНАЯ ДЕТАЛЬНАЯ СИМУЛЯЦИЯ CRM SALES BOT - 100 ДИАЛОГОВ (AUTONOMOUS FLOW)

Параметры:
- 100 диалогов через AUTONOMOUS LLM-driven flow
- 16 уникальных персон (8 оригинальных + 8 новых)
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
TOTAL_FLOWS = 1          # Только autonomous flow
TOTAL_PERSONAS = 16      # 16 персон (8 оригинальных + 8 новых)
AUTONOMOUS_FLOW = "autonomous"  # Все прогоны через LLM-driven flow
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
    print_metric("Flow", f"{AUTONOMOUS_FLOW} (LLM-driven)")
    print_metric("Количество персон", TOTAL_PERSONAS)
    print_metric("Параллельных потоков", PARALLEL_THREADS)
    print_metric("Модель", MODEL_NAME)
    print_metric("Ollama URL", OLLAMA_URL)
    print_metric("Директория отчетов", str(report_dir))

    logger.info(f"Параметры: диалогов={TOTAL_DIALOGS}, flow={AUTONOMOUS_FLOW}, "
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
        from src.llm import OllamaClient
        from src.simulator.runner import SimulationRunner
        from src.simulator.report import ReportGenerator
        from src.simulator.personas import PERSONAS, get_all_persona_names
        from src.simulator.kb_questions import load_kb_question_pool

        print_success("Модули симулятора импортированы")
        print_success(f"Доступно персон: {len(PERSONAS)} ({', '.join(get_all_persona_names())})")
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
        from src.tone_analyzer.semantic_analyzer import get_semantic_tone_analyzer
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
        from src.knowledge.reranker import get_reranker
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
    # ПОДГОТОВКА ПЕРСОН
    # ==========================================================================
    print_section("ПОДГОТОВКА ПЕРСОН")

    all_persona_names = get_all_persona_names()
    print_info(f"Flow: {AUTONOMOUS_FLOW} (все {TOTAL_DIALOGS} прогонов через LLM-driven autonomous)")
    print_info(f"Доступно персон: {len(all_persona_names)}")
    for name in all_persona_names:
        persona = PERSONAS[name]
        print(f"  {Fore.CYAN}{name:.<30} {Fore.WHITE}{persona.name} (max_turns={persona.max_turns})")

    logger.info(f"Flow: {AUTONOMOUS_FLOW}, Персон: {len(all_persona_names)}")
    logger.info(f"Персоны: {', '.join(all_persona_names)}")

    # ==========================================================================
    # ЗАГРУЗКА KB QUESTION POOL (3000+ ВОПРОСОВ)
    # ==========================================================================
    print_section("ЗАГРУЗКА KB QUESTION POOL")

    kb_pool = load_kb_question_pool()
    if kb_pool:
        print_success(f"KB question pool загружен: {kb_pool.total_questions} вопросов")
        print_info(f"Категории: {', '.join(kb_pool.categories[:10])}...")
        logger.info(f"KB pool: {kb_pool.total_questions} вопросов, {len(kb_pool.categories)} категорий")
    else:
        print_error("KB question pool не загружен! Файл kb_questions.json отсутствует")
        logger.error("KB question pool не загружен")
        print_info("Симуляция продолжится без KB вопросов")

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
        verbose=True,
        flow_name=AUTONOMOUS_FLOW,
        kb_question_pool=kb_pool,
    )

    print_success(f"SimulationRunner инициализирован: flow={AUTONOMOUS_FLOW}, KB question pool")
    logger.info(f"SimulationRunner готов: flow={AUTONOMOUS_FLOW}")

    # ==========================================================================
    # ЗАПУСК СИМУЛЯЦИИ
    # ==========================================================================
    print_header(f"ЗАПУСК СИМУЛЯЦИИ: {TOTAL_DIALOGS} ДИАЛОГОВ (AUTONOMOUS FLOW)")

    print(Fore.CYAN + f"Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(Fore.CYAN + f"Flow: {AUTONOMOUS_FLOW} (LLM-driven)")
    print(Fore.CYAN + f"Персон: {len(all_persona_names)}")
    print(Fore.CYAN + f"Параллельность: {PARALLEL_THREADS} потоков")
    print(Fore.CYAN + f"Модель: {MODEL_NAME}")
    print()
    print(Fore.YELLOW + "-" * 100)

    logger.info("=" * 60)
    logger.info("НАЧАЛО СИМУЛЯЦИИ (AUTONOMOUS FLOW)")
    logger.info("=" * 60)

    # Запуск мониторинга ресурсов
    monitor = ResourceMonitor(interval=5.0)
    monitor.start()

    start_time = time.time()
    completed_count = [0]
    detailed_results = []
    lock = threading.Lock()

    def progress_callback(result):
        """Callback для отслеживания прогресса"""
        with lock:
            completed_count[0] += 1

            is_positive = result.outcome in ("success", "soft_close")
            if is_positive:
                status = Fore.GREEN + "OK"
            else:
                status = Fore.RED + "XX"

            # Детальная информация о результате
            result_info = {
                "index": completed_count[0],
                "timestamp": datetime.now().isoformat(),
                "flow": AUTONOMOUS_FLOW,
                "persona": result.persona,
                "outcome": result.outcome,
                "turns": result.turns,
                "phases_reached": result.phases_reached,
                "spin_coverage": result.spin_coverage,
                "lead_score": result.final_lead_score,
                "fallback_count": result.fallback_count,
                "objections_count": result.objections_count,
                "kb_questions_used": result.kb_questions_used,
                "duration_seconds": result.duration_seconds,
                "errors": result.errors,
            }
            detailed_results.append(result_info)

            # Вывод в консоль
            progress = completed_count[0] / TOTAL_DIALOGS * 100
            phases_str = "→".join(result.phases_reached[:4]) if result.phases_reached else "none"
            print(f"  [{completed_count[0]:3d}/{TOTAL_DIALOGS}] ({progress:5.1f}%) "
                  f"{status}{Style.RESET_ALL} "
                  f"{result.persona:25s} "
                  f"| {result.outcome:12s} "
                  f"| turns: {result.turns:2d} "
                  f"| phases: {phases_str}")

            # Логирование
            logger.info(f"[{completed_count[0]}/{TOTAL_DIALOGS}] "
                       f"{result.outcome:12s} "
                       f"persona={result.persona} "
                       f"turns={result.turns} "
                       f"phases={result.phases_reached}")

    # Запуск batch симуляции (все 100 через autonomous flow)
    try:
        results = runner.run_batch(
            count=TOTAL_DIALOGS,
            parallel=PARALLEL_THREADS,
            progress_callback=progress_callback
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
    positive_outcomes = ("success", "soft_close")
    success_count = sum(1 for r in results if r.outcome in positive_outcomes)
    success_rate = (success_count / total * 100) if total > 0 else 0.0
    avg_turns = sum(r.turns for r in results) / total if total > 0 else 0.0
    avg_coverage = sum(r.spin_coverage for r in results) / total if total > 0 else 0.0
    error_count = sum(1 for r in results if r.outcome == "error")

    # Метрики по outcome
    outcomes = {}
    for r in results:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1

    # Метрики по персонам
    persona_stats = {}
    for r in results:
        if r.persona not in persona_stats:
            persona_stats[r.persona] = {"outcomes": [], "turns": [], "coverage": []}
        persona_stats[r.persona]["outcomes"].append(r.outcome)
        persona_stats[r.persona]["turns"].append(r.turns)
        persona_stats[r.persona]["coverage"].append(r.spin_coverage)

    # ==========================================================================
    # ВЫВОД ИТОГОВ
    # ==========================================================================
    print_section("ОБЩИЕ РЕЗУЛЬТАТЫ")
    print_metric("Flow", f"{AUTONOMOUS_FLOW} (LLM-driven)")
    print_metric("Всего диалогов", total)
    print_metric("Успешно (success+soft_close)", f"{success_count} ({success_rate:.1f}%)")
    print_metric("Ошибки", error_count)
    print_metric("Средние ходы", f"{avg_turns:.1f}")
    print_metric("Средний phase coverage", f"{avg_coverage:.2f}")
    print_metric("Время выполнения", f"{duration:.1f} сек ({duration/60:.1f} мин)")
    print_metric("Среднее время на диалог", f"{duration/total:.2f} сек")
    print_metric("Производительность", f"{total/duration*60:.1f} диалогов/мин")

    print_section("РЕЗУЛЬТАТЫ ПО OUTCOME")
    for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        percent = count / total * 100
        color = Fore.GREEN if outcome in positive_outcomes else Fore.RED
        print(f"  {color}{outcome:.<40} {Fore.WHITE}{count} ({percent:.1f}%)")

    print_section("РЕЗУЛЬТАТЫ ПО ПЕРСОНАМ")
    sorted_personas = sorted(
        persona_stats.items(),
        key=lambda x: sum(1 for o in x[1]["outcomes"] if o in positive_outcomes) / len(x[1]["outcomes"]),
        reverse=True
    )
    for persona, stats in sorted_personas:
        n = len(stats["outcomes"])
        p_success = sum(1 for o in stats["outcomes"] if o in positive_outcomes)
        p_rate = p_success / n * 100
        avg_t = sum(stats["turns"]) / n
        avg_c = sum(stats["coverage"]) / n
        color = Fore.GREEN if p_rate >= 50 else Fore.YELLOW if p_rate >= 25 else Fore.RED
        print(f"  {color}{persona:.<25}{Style.RESET_ALL} "
              f"success: {p_success}/{n} ({p_rate:.0f}%) "
              f"| avg_turns: {avg_t:.1f} "
              f"| coverage: {avg_c:.2f}")

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
    reporter = ReportGenerator()
    reporter.save_report(results, str(full_report), include_dialogues=True)
    print_success(f"Полный отчет: {full_report.name}")

    # 2. JSON метрики
    metrics_data = {
        "metadata": {
            "timestamp": timestamp_readable,
            "timestamp_iso": datetime.now().isoformat(),
            "version": "2.0",
            "model": MODEL_NAME,
            "flow": AUTONOMOUS_FLOW,
        },
        "parameters": {
            "total_dialogs": TOTAL_DIALOGS,
            "flow": AUTONOMOUS_FLOW,
            "total_personas": TOTAL_PERSONAS,
            "parallel_threads": PARALLEL_THREADS,
        },
        "summary": {
            "total": total,
            "success_count": success_count,
            "success_rate_percent": success_rate,
            "error_count": error_count,
            "avg_turns": avg_turns,
            "avg_phase_coverage": avg_coverage,
        },
        "performance": {
            "duration_seconds": duration,
            "duration_minutes": duration / 60,
            "avg_time_per_dialog_seconds": duration / total if total > 0 else 0,
            "dialogs_per_minute": total / duration * 60 if duration > 0 else 0,
        },
        "outcomes": outcomes,
        "persona_stats": {
            persona: {
                "count": len(stats["outcomes"]),
                "success_rate": sum(1 for o in stats["outcomes"] if o in positive_outcomes) / len(stats["outcomes"]),
                "avg_turns": sum(stats["turns"]) / len(stats["turns"]),
                "avg_coverage": sum(stats["coverage"]) / len(stats["coverage"]),
            }
            for persona, stats in persona_stats.items()
        },
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
    logger.info(f"Результат: {success_count}/{total} success ({success_rate:.1f}%)")
    logger.info(f"Средние ходы: {avg_turns:.1f}, coverage: {avg_coverage:.2f}")
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
    if success_rate < 30:
        print(Fore.RED + f"WARNING: Success rate {success_rate:.1f}% ниже порога 30%")
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
