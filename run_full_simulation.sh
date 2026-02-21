#!/bin/bash
# =============================================================================
# ПОЛНАЯ СИМУЛЯЦИЯ CRM SALES BOT (AUTONOMOUS FLOW)
# =============================================================================
# Параметры:
#   - 150 диалогов через AUTONOMOUS LLM-driven flow
#   - 21 уникальная персона
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
TOTAL_DIALOGS=150
PARALLEL_THREADS=8
FLOW="autonomous"

echo -e "${BLUE}=============================================="
echo -e "CRM SALES BOT - AUTONOMOUS FLOW SIMULATION"
echo -e "==============================================${NC}"
echo ""
echo -e "${GREEN}Параметры симуляции:${NC}"
echo "  • Дата и время: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  • Модель: Qwen3 14B (Ollama)"
echo "  • Всего диалогов: ${TOTAL_DIALOGS}"
echo "  • Персон: 21"
echo "  • Flow: ${FLOW} (LLM-driven)"
echo "  • Параллельных потоков: ${PARALLEL_THREADS} (GPU + CPU)"
echo ""

# ============================================================================
# ШАГ 1: Проверка Ollama
# ============================================================================
echo -e "${YELLOW}[1/3] Проверка Ollama...${NC}"

if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama уже запущен${NC}"
else
    echo -e "${YELLOW}Запускаем Ollama...${NC}"
    ./scripts/start_ollama.sh 2>&1

    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}✗ Ошибка запуска Ollama${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Ollama запущен${NC}"
fi

if ollama list 2>/dev/null | grep -q "qwen3:14b"; then
    echo -e "${GREEN}✓ Модель qwen3:14b установлена${NC}"
else
    echo -e "${RED}✗ Модель qwen3:14b не найдена! Скачайте: ollama pull qwen3:14b${NC}"
    exit 1
fi

# ============================================================================
# ШАГ 2: Настройка окружения
# ============================================================================
echo ""
echo -e "${YELLOW}[2/3] Настройка окружения...${NC}"

export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS=${PARALLEL_THREADS}
export MKL_NUM_THREADS=${PARALLEL_THREADS}
export OPENBLAS_NUM_THREADS=${PARALLEL_THREADS}
export NUMEXPR_NUM_THREADS=${PARALLEL_THREADS}
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
export SENTENCE_TRANSFORMERS_HOME="${HOME}/.cache/sentence_transformers"

echo -e "${GREEN}✓ Переменные окружения настроены${NC}"

# ============================================================================
# ШАГ 3: Запуск симуляции (AUTONOMOUS FLOW)
# ============================================================================
echo ""
echo -e "${YELLOW}[3/3] Запуск симуляции (${TOTAL_DIALOGS} диалогов, ${FLOW} flow)...${NC}"
echo -e "${BLUE}=============================================="
echo -e "НАЧАЛО СИМУЛЯЦИИ (AUTONOMOUS FLOW)"
echo -e "==============================================${NC}"
echo ""

START_TIME=$(date +%s)

python3 scripts/run_full_simulation_100.py 2>&1

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo -e "${BLUE}=============================================="
echo -e "СИМУЛЯЦИЯ ЗАВЕРШЕНА"
echo -e "==============================================${NC}"
echo ""
echo -e "${GREEN}Результаты:${NC}"
echo "  • Время выполнения: ${DURATION} секунд ($((DURATION / 60)) минут)"
echo "  • Всего диалогов: ${TOTAL_DIALOGS}"
echo "  • Flow: ${FLOW}"
echo "  • Параллельных потоков: ${PARALLEL_THREADS}"
echo ""
echo -e "${GREEN}✓ Симуляция успешно завершена!${NC}"
echo ""
