# Self-Contained Docker Stack

Отдельный self-contained стек для `crm-sales-bot`:
- `ollama`
- `ollama-model-init`
- `tei-model-init`
- `tei-embed`
- `tei-rerank`
- `bot`

Использование:

```bash
cd infra/docker-selfcontained
cp .env.example .env
cp config/settings.yaml.example config/settings.yaml
docker compose up -d --build
curl -s http://localhost:8000/ready
```

Замечания:
- `config/settings.yaml` заменяет встроенный `src/settings.yaml` внутри контейнера `bot`.
- `.env` содержит infrastructure/runtime overrides и секреты.
- По умолчанию модель: `qwen3.5:27b`; если локально рабочая другая, меняйте `OLLAMA_MODEL` в `.env`.
