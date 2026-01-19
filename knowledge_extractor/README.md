# Knowledge Extractor

CLI-инструмент для автоматической генерации баз знаний в YAML формате из неструктурированных данных.

## Установка

```bash
cd /home/sultan/projects/knowledge_extractor
pip install -e .
```

## Использование

```bash
# Обработать директорию с документами
python -m knowledge_extractor --input docs/ --output kb/

# Обработать один PDF файл
python -m knowledge_extractor -i manual.pdf -o knowledge/

# Использовать кастомный Ollama endpoint
python -m knowledge_extractor -i docs/ -o kb/ --llm-url http://localhost:11434

# Dry run (без LLM, только парсинг и chunking)
python -m knowledge_extractor -i docs/ -o kb/ --dry-run
```

## Поддерживаемые форматы

- **PDF** (.pdf) - через PyMuPDF
- **Word** (.docx) - через python-docx
- **Text** (.txt, .md)
- **Excel** (.xlsx, .xls, .csv) - через pandas/openpyxl
- **Q&A пары** (.tsv, .csv, .json с Q&A структурой)
- **Мессенджеры** (WhatsApp/Telegram экспорты)

## Формат выходных данных

```yaml
sections:
  - topic: tariffs
    priority: 10
    keywords:
      - тариф
      - цена
      - стоимость
      - скока          # опечатка
      - сколько стоит  # вопрос
    facts: |
      **Тарифы:**
      • Mini - 1 точка
      • Lite - 1-2 точки
      • Standard - до 3 точек
```

## Архитектура

```
INPUT (PDF/DOCX/TXT/Excel/Chat)
         │
         ▼
┌─────────────────┐
│  1. PARSERS     │  → ParsedDocument
└────────┬────────┘
         ▼
┌─────────────────┐
│  2. CHUNKING    │  → List[Chunk]
└────────┬────────┘
         ▼
┌─────────────────┐
│  3. EXTRACTION  │  → ExtractedSection (via Ollama + Qwen3 14B)
└────────┬────────┘
         ▼
┌─────────────────┐
│  4. KEYWORDS    │  → Морфология + опечатки + синонимы
└────────┬────────┘
         ▼
┌─────────────────┐
│  5. DEDUP       │  → Semantic deduplication (cosine > 0.85)
└────────┬────────┘
         ▼
┌─────────────────┐
│  6. VALIDATION  │  → Quality check (>90% pass rate)
└────────┬────────┘
         ▼
┌─────────────────┐
│  7. OUTPUT      │  → YAML files по категориям + _meta.yaml
└─────────────────┘
```

## Параметры CLI

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--input, -i` | обязателен | Входной файл или директория |
| `--output, -o` | обязателен | Директория для YAML файлов |
| `--llm-url` | http://localhost:11434 | Ollama API endpoint |
| `--llm-model` | qwen3:14b | Модель Ollama |
| `--company-name` | - | Название компании для _meta.yaml |
| `--min-keywords` | 20 | Минимум keywords на секцию |
| `--max-keywords` | 50 | Максимум keywords на секцию |
| `--dedup-threshold` | 0.85 | Порог дедупликации |
| `--verbose, -v` | false | Подробный вывод |
| `--dry-run` | false | Без LLM извлечения |

## Зависимости

- Python 3.10+
- Ollama с моделью qwen3:14b
- PyMuPDF, python-docx, pandas
- pymorphy3, sentence-transformers
- rich, pyyaml

## Требования к Ollama

Установите и запустите Ollama перед использованием:

```bash
# Установка
curl -fsSL https://ollama.ai/install.sh | sh

# Скачать модель
ollama pull qwen3:14b

# Запуск
ollama serve
```

**Требования:** ~12-16 GB VRAM для Qwen3 14B
