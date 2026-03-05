# Деплой CRM Sales Bot

## Требования к серверу
- Ubuntu 22.04+ (или любой Linux с Docker)
- GPU с 24+ GB VRAM (NVIDIA)
- 32+ GB RAM
- 50+ GB свободного места на диске (модели ~20GB)

## Шаг 1: Установить Docker + NVIDIA toolkit

```bash
# Docker
curl -fsSL https://get.docker.com | sh

# NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Проверить что GPU видна:
```bash
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

## Шаг 2: Скопировать проект на сервер

```bash
scp -r crm-sales-bot-fork/ user@server:/opt/crm-sales-bot/
# или через git clone
```

## Шаг 3: Настроить переменные

```bash
cd /opt/crm-sales-bot
echo "API_KEY=$(openssl rand -hex 32)" > .env
```

## Шаг 4: Запустить

```bash
docker compose up -d
```

Первый запуск:
1. Docker соберёт образ бота (~3-5 мин)
2. Ollama стартанёт, но модель ещё не загружена

## Шаг 5: Загрузить модель Qwen 3.5 27B

```bash
docker exec -it ollama ollama pull qwen3.5:27b
```

Скачивание ~17GB, займёт время в зависимости от канала.

## Шаг 6: Проверить

```bash
# Статус контейнеров
docker compose ps

# Логи бота
docker compose logs -f bot

# Логи ollama
docker compose logs -f ollama

# Тест API
curl -s http://localhost:8000/docs
```

Тест диалога:
```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H "Authorization: Bearer $(cat .env | grep API_KEY | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-1",
    "user_id": "user-1",
    "message": {"text": "Здравствуйте", "timestamp_ms": 0},
    "context": {}
  }'
```

## Порты

| Сервис | Внутренний | Внешний |
|--------|-----------|---------|
| Bot API | 8000 | 8000 |
| Ollama | 11434 | 8080 |

## Перезапуск / обновление

```bash
cd /opt/crm-sales-bot
git pull
docker compose up -d --build
```

## Данные (persistent volumes)

- `ollama_data` — модели Ollama (~17GB). Не удалять!
- `bot_data` — SQLite БД с диалогами
- `hf_cache` — модели эмбеддингов FRIDA + reranker (~2GB). Не удалять!

## Troubleshooting

**Бот не стартует, пишет "connection refused"**
- Ollama ещё не готова. Подождать healthcheck (до 2 мин).

**"CUDA out of memory"**
- Qwen 3.5 27B = ~17GB VRAM. Эмбеддинги (FRIDA) = ~2GB.
- Если VRAM мало, переключить эмбеддинги на CPU: поменять `EMBEDDER_DEVICE=cpu` в docker-compose.yaml.

**Модель отвечает медленно**
- Проверить `nvidia-smi` — GPU должна быть загружена. Если нет, Ollama запустила модель на CPU.
