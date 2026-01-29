#!/bin/bash
# =============================================================================
# ПОЛНАЯ СИМУЛЯЦИЯ CRM SALES BOT
# =============================================================================
# Параметры:
#   - 100 диалогов (20 флоу × 5 персон каждый)
#   - 8 параллельных потоков (CPU + GPU)
#   - Qwen3 14B через Ollama
#   - Полное логирование с метриками
#   - Отчеты с датой и временем
# =============================================================================

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Параметры симуляции
PARALLEL_THREADS=8
PERSONAS_PER_FLOW=5
TOTAL_SIMULATIONS=$((20 * PERSONAS_PER_FLOW))  # 20 флоу × 8 персон = 160

# Генерация имени файла с датой и временем
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
REPORT_DIR="./reports/simulation_${TIMESTAMP}"
LOG_FILE="${REPORT_DIR}/simulation_${TIMESTAMP}.log"
METRICS_FILE="${REPORT_DIR}/metrics_${TIMESTAMP}.json"
FULL_REPORT="${REPORT_DIR}/full_report_${TIMESTAMP}.txt"

# Создаем директорию для отчетов
mkdir -p "${REPORT_DIR}"

echo -e "${BLUE}=============================================="
echo -e "CRM SALES BOT - ПОЛНАЯ СИМУЛЯЦИЯ"
echo -e "==============================================${NC}"
echo ""
echo -e "${GREEN}Параметры симуляции:${NC}"
echo "  • Дата и время: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  • Модель: Qwen3 14B (Ollama)"
echo "  • Всего диалогов: ${TOTAL_SIMULATIONS}"
echo "  • Количество флоу: 20"
echo "  • Персон на флоу: ${PERSONAS_PER_FLOW}"
echo "  • Параллельных потоков: ${PARALLEL_THREADS} (GPU + CPU)"
echo "  • GPU потоки: 8"
echo "  • CPU потоки: 8"
echo ""
echo -e "${GREEN}Файлы вывода:${NC}"
echo "  • Директория: ${REPORT_DIR}"
echo "  • Лог: ${LOG_FILE}"
echo "  • Метрики: ${METRICS_FILE}"
echo "  • Отчет: ${FULL_REPORT}"
echo ""

# ============================================================================
# ШАГ 1: Запуск Ollama
# ============================================================================
echo -e "${YELLOW}[1/4] Проверка и запуск Ollama...${NC}"

# Проверяем запущен ли Ollama
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama уже запущен${NC}"
else
    echo -e "${YELLOW}Запускаем Ollama...${NC}"
    ./scripts/start_ollama.sh 2>&1 | tee -a "${LOG_FILE}"

    # Проверяем успешность запуска
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}✗ Ошибка запуска Ollama${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Ollama запущен${NC}"
fi

# ============================================================================
# ШАГ 2: Проверка модели Qwen3 14B
# ============================================================================
echo ""
echo -e "${YELLOW}[2/4] Проверка модели Qwen3 14B...${NC}"

if ollama list 2>/dev/null | grep -q "qwen3:14b"; then
    echo -e "${GREEN}✓ Модель qwen3:14b установлена${NC}"
else
    echo -e "${YELLOW}Скачиваем модель qwen3:14b (~9GB)...${NC}"
    ollama pull qwen3:14b 2>&1 | tee -a "${LOG_FILE}"
    echo -e "${GREEN}✓ Модель скачана${NC}"
fi

# ============================================================================
# ШАГ 3: Настройка окружения
# ============================================================================
echo ""
echo -e "${YELLOW}[3/4] Настройка окружения...${NC}"

# Настраиваем переменные окружения для оптимизации GPU/CPU
export CUDA_VISIBLE_DEVICES=0  # Используем первую GPU
export OMP_NUM_THREADS=8        # 8 потоков для OpenMP (CPU)
export MKL_NUM_THREADS=8        # 8 потоков для Intel MKL
export OPENBLAS_NUM_THREADS=8   # 8 потоков для OpenBLAS
export NUMEXPR_NUM_THREADS=8    # 8 потоков для NumExpr

# Настройки для PyTorch (если используются embeddings)
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# Кэш для sentence transformers
export SENTENCE_TRANSFORMERS_HOME="${HOME}/.cache/sentence_transformers"

echo -e "${GREEN}✓ Переменные окружения настроены${NC}"
echo "  • CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES}"
echo "  • OMP_NUM_THREADS: ${OMP_NUM_THREADS}"
echo "  • Параллельность: ${PARALLEL_THREADS}"

# ============================================================================
# ШАГ 4: Запуск симуляции
# ============================================================================
echo ""
echo -e "${YELLOW}[4/4] Запуск симуляции (${TOTAL_SIMULATIONS} диалогов)...${NC}"
echo -e "${BLUE}=============================================="
echo -e "НАЧАЛО СИМУЛЯЦИИ"
echo -e "==============================================${NC}"
echo ""

# Запускаем E2E режим (20 техник × 5 персон = 100 тестов)
# --e2e: режим тестирования всех 20 техник продаж
# --personas 5: по 5 случайных персон на каждую технику
# --parallel 8: 8 параллельных потоков
# -o: полный отчет с диалогами

START_TIME=$(date +%s)

python3 -m src.simulator \
    --e2e \
    --personas ${PERSONAS_PER_FLOW} \
    --parallel ${PARALLEL_THREADS} \
    -o "${FULL_REPORT}" \
    -v 2>&1 | tee -a "${LOG_FILE}"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# ============================================================================
# ИТОГИ
# ============================================================================
echo ""
echo -e "${BLUE}=============================================="
echo -e "СИМУЛЯЦИЯ ЗАВЕРШЕНА"
echo -e "==============================================${NC}"
echo ""
echo -e "${GREEN}Результаты:${NC}"
echo "  • Время выполнения: ${DURATION} секунд ($((DURATION / 60)) минут)"
echo "  • Всего диалогов: ${TOTAL_SIMULATIONS}"
echo "  • Параллельных потоков: ${PARALLEL_THREADS}"
echo ""
echo -e "${GREEN}Файлы с результатами:${NC}"
echo "  • Директория: ${REPORT_DIR}"
echo "  • Лог симуляции: ${LOG_FILE}"
echo "  • Полный отчет: ${FULL_REPORT}"

# Показываем размеры файлов
if [ -f "${LOG_FILE}" ]; then
    LOG_SIZE=$(du -h "${LOG_FILE}" | cut -f1)
    echo "    └─ Размер лога: ${LOG_SIZE}"
fi

if [ -f "${FULL_REPORT}" ]; then
    REPORT_SIZE=$(du -h "${FULL_REPORT}" | cut -f1)
    echo "    └─ Размер отчета: ${REPORT_SIZE}"
fi

echo ""
echo -e "${GREEN}Просмотр отчета:${NC}"
echo "  less ${FULL_REPORT}"
echo ""
echo -e "${GREEN}Просмотр лога:${NC}"
echo "  less ${LOG_FILE}"
echo ""

# Извлекаем основные метрики из отчета
if [ -f "${FULL_REPORT}" ]; then
    echo -e "${YELLOW}Краткие метрики:${NC}"

    # Ищем секцию SUMMARY в отчете
    grep -A 10 "SUMMARY" "${FULL_REPORT}" 2>/dev/null || echo "  (метрики не найдены в отчете)"

    echo ""
fi

# Информация о системе
echo -e "${YELLOW}Использование ресурсов:${NC}"
echo "  GPU:"
nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | \
    awk -F, '{printf "    └─ Загрузка: %s%%, VRAM: %sMB / %sMB (использовано)\n", $1, $3, $4}' || \
    echo "    └─ (информация недоступна)"

echo "  CPU:"
echo "    └─ Потоков: ${PARALLEL_THREADS} из $(nproc)"

echo ""
echo -e "${GREEN}✓ Симуляция успешно завершена!${NC}"
echo ""
