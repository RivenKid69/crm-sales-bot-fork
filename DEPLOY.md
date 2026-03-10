# Деплой CRM Sales Bot

## Что разворачивается

Текущая поставка self-contained и поднимается одним `docker compose`:
- `ollama` - LLM runtime
- `ollama-model-init` - первый `pull` LLM-модели в volume
- `tei-model-init` - первый preload TEI-моделей в HF cache
- `tei-embed` - embeddings service
- `tei-rerank` - reranker service
- `bot` - FastAPI API бота

Бэку не нужно вручную запускать отдельные systemd-сервисы для TEI или руками править URL внутри контейнеров.

## Требования к серверу

- Ubuntu 22.04+ или другой Linux с Docker
- NVIDIA GPU
- Docker Engine + Docker Compose plugin
- NVIDIA Container Toolkit
- исходящий доступ контейнеров в интернет на первом запуске
- минимум 32 GB RAM
- желательно 32 GB VRAM для связки `qwen3.5:27b` + TEI
- минимум 80 GB свободного места

Почему нужен интернет на первом запуске:
- `ollama-model-init` скачивает Ollama-модель
- `tei-model-init` скачивает `Qwen/Qwen3-Embedding-4B` и `Qwen/Qwen3-Reranker-4B`

После первой инициализации модели сохраняются в volumes.

## Шаг 1. Установить Docker и NVIDIA Container Toolkit

```bash
curl -fsSL https://get.docker.com | sh

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Проверка GPU в Docker:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

## Шаг 2. Скопировать проект

```bash
git clone <repo-url> /opt/crm-sales-bot
cd /opt/crm-sales-bot
```

или:

```bash
scp -r crm-sales-bot-fork/ user@server:/opt/crm-sales-bot/
cd /opt/crm-sales-bot
```

## Шаг 3. Создать `.env`

Минимально нужен production `API_KEY`.

```bash
cat > .env <<'EOF'
API_KEY=replace-with-long-random-secret
OLLAMA_MODEL=qwen3.5:27b
EOF
```

Сгенерировать ключ можно так:

```bash
openssl rand -hex 32
```

Если модель нужно поменять, достаточно заменить `OLLAMA_MODEL` в `.env`. Ту же модель автоматически подтянет `ollama-model-init`.

## Шаг 4. Запустить стек

```bash
docker compose up -d --build
```

На первом запуске ожидаемо долго:
- собирается image бота
- собирается image TEI runtime
- скачивается Ollama-модель
- скачиваются TEI-модели

Проверка статуса:

```bash
docker compose ps -a
```

Ожидаемое состояние:
- `ollama` - `healthy`
- `tei-embed` - `healthy`
- `tei-rerank` - `healthy`
- `ollama-model-init` - `Exited (0)`
- `tei-model-init` - `Exited (0)`
- `bot` - `Up`

## Шаг 5. Проверить API

```bash
curl -s http://localhost:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok","model":"qwen3.5:27b"}
```

Тестовый запрос:

```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H "Authorization: Bearer $(grep '^API_KEY=' .env | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-1",
    "user_id": "user-1",
    "channel": "api",
    "message": {
      "text": "Здравствуйте"
    }
  }'
```

## Полезные команды

Логи:

```bash
docker compose logs -f bot
docker compose logs -f ollama
docker compose logs -f tei-embed
docker compose logs -f tei-rerank
```

Перезапуск после обновления:

```bash
git pull
docker compose up -d --build
```

Полная остановка:

```bash
docker compose down
```

## Данные в volumes

- `ollama_data` - Ollama-модели
- `hf_cache` - TEI-модели Hugging Face
- `bot_data` - SQLite и embedding cache

Не удалять эти volumes без необходимости, иначе первый запуск придётся повторять с полной загрузкой моделей.

## Что проброшено наружу

- `8000:8000` - API бота

`ollama`, `tei-embed` и `tei-rerank` наружу не публикуются и живут только во внутренней docker-сети.

## Troubleshooting

**`bot` не стартует**

Проверьте:

```bash
docker compose ps -a
docker compose logs ollama-model-init
docker compose logs tei-model-init
```

Обычно причина одна из двух:
- у контейнеров нет исходящего интернета
- GPU runtime в Docker не настроен

**TEI или Ollama не могут скачать модели**

Проверьте DNS и исходящий доступ из Docker. На первом запуске это обязательно.

**`401 Unauthorized`**

Используется неверный `Authorization: Bearer <API_KEY>`.

**Медленный ответ**

Проверьте загрузку GPU:

```bash
nvidia-smi
```

**`CUDA out of memory`**

Текущая рекомендованная связка рассчитана на GPU-класс уровня RTX 5090 / 32 GB VRAM. На более слабой карте придётся менять модель и повторно валидировать compose-конфигурацию.
