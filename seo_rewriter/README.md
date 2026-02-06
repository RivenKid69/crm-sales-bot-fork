# SEO Rewriter

Инструмент для рерайта текста с проверкой уникальности.

## Что есть в коде

- CLI: `seo-rewriter` (`seo_rewriter/src/seo_rewriter/cli.py`)
- REST API: FastAPI (`seo_rewriter/src/seo_rewriter/api.py`)
- Проверка уникальности: n-gram, Jaccard, SimHash, Winnowing
- LLM backend: Ollama (`qwen3:14b` по умолчанию)

## Установка

```bash
cd seo_rewriter
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## CLI

### Рерайт

```bash
seo-rewriter rewrite "Ваш текст..."
seo-rewriter rewrite --file input.txt --output output.txt
seo-rewriter rewrite "Текст" --style news --keywords "crm,продажи"
```

### Проверка двух текстов

```bash
seo-rewriter check "оригинал" "рерайт"
```

### Сервисные команды

```bash
seo-rewriter models
seo-rewriter config
```

## REST API

Запуск:

```bash
python3 -m seo_rewriter.api
```

Эндпоинты:
- `GET /health`
- `POST /rewrite`
- `POST /check`
- `GET /styles`

Документация OpenAPI доступна по `/docs`.

## Конфиг

Параметры в `seo_rewriter/src/seo_rewriter/config.py`.

Environment prefix: `SEO_`.
Примеры:
- `SEO_OLLAMA_BASE_URL`
- `SEO_OLLAMA_MODEL`
- `SEO_TARGET_UNIQUENESS`
