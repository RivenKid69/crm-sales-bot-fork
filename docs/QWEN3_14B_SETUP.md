# Qwen3-14B-AWQ Setup Guide

## Характеристики модели

- **Модель**: Qwen/Qwen3-14B-AWQ
- **Квантизация**: 4-bit AWQ (99%+ качества от FP16)
- **VRAM**: ~8.4GB + 4-8GB для KV-cache = ~12-16GB
- **Скорость на RTX 5090**: 120-150 tokens/sec
- **Размер на диске**: ~8-9 GB

## Преимущества над Qwen3-4B

| Параметр | Qwen3-4B | Qwen3-14B | Улучшение |
|----------|----------|-----------|-----------|
| Параметры | 4B | 14B | **3.5x** |
| Качество рассуждений | Базовое | Продвинутое | **~40%** |
| Понимание контекста | Хорошее | Отличное | **~35%** |
| Генерация диалогов | Хорошая | Превосходная | **~30%** |
| Скорость | ~280 t/s | ~140 t/s | 2x медленнее |
| VRAM | ~3-4GB | ~12-16GB | 4x больше |

## Установка

### 1. Установить vLLM

```bash
cd /home/corta/crm_sales_bot
source .venv/bin/activate
pip install vllm
```

### 2. Скачать модель

```bash
python scripts/download_qwen3_14b.py
```

Модель будет загружена в `~/.cache/huggingface/hub/`

### 3. Запустить vLLM сервер

```bash
./scripts/start_vllm_qwen3_14b.sh
```

Сервер запустится на `http://localhost:8000`

### 4. Проверить работу

```bash
curl http://localhost:8000/v1/models
```

Должен вернуть список доступных моделей.

## Конфигурация

Настройки в [src/settings.yaml](../src/settings.yaml):

```yaml
llm:
  model: "Qwen/Qwen3-14B-AWQ"
  base_url: "http://localhost:8000/v1"
  timeout: 60
```

## Оптимизация для RTX 5090

Скрипт запуска уже оптимизирован:

- **GPU Memory Utilization**: 90% (оставляем 10% для KV-cache)
- **Max Context Length**: 32K tokens
- **Attention Backend**: FLASHINFER (быстрее на RTX 5090)
- **Quantization**: AWQ

## Мониторинг

### Проверить использование GPU:

```bash
watch -n 1 nvidia-smi
```

### Проверить статус сервера:

```bash
curl http://localhost:8000/health
```

## Остановка сервера

```bash
# Найти процесс
ps aux | grep vllm

# Остановить
kill <PID>

# Или через pkill
pkill -f "vllm.entrypoints.openai.api_server"
```

## Troubleshooting

### Ошибка "CUDA out of memory"

Уменьшите `gpu-memory-utilization` в скрипте:

```bash
GPU_MEMORY_UTILIZATION="0.85"  # Было 0.90
```

### Медленная генерация

Проверьте:
1. Используется ли GPU: `nvidia-smi` должен показывать загрузку
2. Не запущены ли другие процессы на GPU
3. Включен ли FLASHINFER backend

### Модель не загружается

Проверьте наличие модели:

```bash
ls -lh ~/.cache/huggingface/hub/ | grep Qwen3-14B
```

Если модели нет, запустите снова:

```bash
python scripts/download_qwen3_14b.py
```

## Дополнительные команды

### Тест производительности:

```bash
# Запустить бенчмарк
python -m vllm.entrypoints.openai.run_batch \
    --model Qwen/Qwen3-14B-AWQ \
    --input-len 512 \
    --output-len 128 \
    --num-prompts 10
```

### Логи vLLM:

```bash
# Просмотр логов (если запущен через systemd)
journalctl -u vllm -f

# Или прямо в консоли
./scripts/start_vllm_qwen3_14b.sh
```

## Переход обратно на Qwen3-4B

Если нужно вернуться:

1. Остановить vLLM сервер
2. Изменить в `src/settings.yaml`:
   ```yaml
   model: "Qwen/Qwen3-4B-AWQ"
   ```
3. Перезапустить с 4B моделью

## Production deployment

Для production рекомендуется запускать через systemd:

```bash
sudo nano /etc/systemd/system/vllm.service
```

```ini
[Unit]
Description=vLLM Server - Qwen3-14B-AWQ
After=network.target

[Service]
Type=simple
User=corta
WorkingDirectory=/home/corta/crm_sales_bot
ExecStart=/home/corta/crm_sales_bot/scripts/start_vllm_qwen3_14b.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запустить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable vllm
sudo systemctl start vllm
sudo systemctl status vllm
```
