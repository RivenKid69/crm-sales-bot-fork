#!/bin/bash
# =============================================================================
# Запуск Ollama для CRM Sales Bot
# =============================================================================
# Использование: ./scripts/start_ollama.sh
#
# Требования:
#   - Ollama установлен (curl -fsSL https://ollama.ai/install.sh | sh)
#   - ~9 GB свободной VRAM для qwen3:14b
# =============================================================================

set -e

MODEL="qwen3:14b"
HOST="0.0.0.0"
PORT="11434"

echo "=============================================="
echo "CRM Sales Bot - Ollama Launcher"
echo "=============================================="
echo ""
echo "Model: $MODEL"
echo "Host: $HOST:$PORT"
echo ""

# Проверяем установлен ли Ollama
if ! command -v ollama &> /dev/null; then
    echo "ERROR: Ollama не найден!"
    echo ""
    echo "Установите Ollama:"
    echo "  curl -fsSL https://ollama.ai/install.sh | sh"
    echo ""
    exit 1
fi

echo "[1/3] Проверка модели..."

# Проверяем скачана ли модель
if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "Модель $MODEL не найдена. Скачиваем..."
    echo ""
    ollama pull "$MODEL"
    echo ""
    echo "Модель успешно скачана!"
else
    echo "Модель $MODEL уже установлена"
fi

echo ""
echo "[2/3] Проверка сервера Ollama..."

# Проверяем запущен ли сервер
if curl -s "http://localhost:$PORT/api/tags" > /dev/null 2>&1; then
    echo "Ollama сервер уже запущен на порту $PORT"
else
    echo "Запускаем Ollama сервер..."

    # Запускаем в фоне
    OLLAMA_HOST="$HOST:$PORT" ollama serve &
    OLLAMA_PID=$!

    # Ждём запуска
    echo "Ожидание запуска сервера..."
    for i in {1..30}; do
        if curl -s "http://localhost:$PORT/api/tags" > /dev/null 2>&1; then
            echo "Сервер запущен (PID: $OLLAMA_PID)"
            break
        fi
        sleep 1
    done

    if ! curl -s "http://localhost:$PORT/api/tags" > /dev/null 2>&1; then
        echo "ERROR: Не удалось запустить сервер за 30 секунд"
        exit 1
    fi
fi

echo ""
echo "[3/3] Проверка доступности модели..."

# Тест загрузки модели (первый запрос прогревает модель)
echo "Прогрев модели (может занять время при первом запуске)..."
RESPONSE=$(curl -s -X POST "http://localhost:$PORT/api/chat" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"Привет\"}], \"stream\": false}" \
    --max-time 120 2>&1) || true

if echo "$RESPONSE" | grep -q '"message"'; then
    echo "Модель успешно загружена и отвечает!"
else
    echo "WARNING: Модель может ещё загружаться. Первый запрос может быть медленным."
fi

echo ""
echo "=============================================="
echo "Ollama готов к работе!"
echo "=============================================="
echo ""
echo "API: http://localhost:$PORT/api/chat"
echo "Model: $MODEL"
echo ""
echo "Тест (structured output):"
echo "  curl -X POST http://localhost:$PORT/api/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\": \"$MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"Сколько будет 2+2?\"}], \"stream\": false, \"format\": {\"type\": \"object\", \"properties\": {\"answer\": {\"type\": \"integer\"}}, \"required\": [\"answer\"]}}'"
echo ""
echo "Для остановки: killall ollama"
echo ""
