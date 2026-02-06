# Knowledge Extractor

CLI для извлечения знаний из документов в YAML-формат, совместимый с `crm_sales_bot`.

## Возможности

- Парсинг: PDF, DOCX, TXT/MD, XLSX/CSV/TSV/JSON
- Chunking: semantic / qa / table
- LLM extraction
- Semantic deduplication
- Category routing и генерация `*_meta.yaml`

## Установка

```bash
cd knowledge_extractor
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Запуск

```bash
python3 -m knowledge_extractor --input docs/ --output kb/
python3 -m knowledge_extractor -i manual.pdf -o kb/
python3 -m knowledge_extractor -i docs/ -o kb/ --dry-run
```

Дополнительные параметры:
- `--llm-url`
- `--llm-model`
- `--max-tokens`
- `--min-keywords`
- `--max-keywords`
- `--dedup-threshold`
- `--company-name`
- `--company-description`
- `--verbose`

## Выход

В директорию `--output` записываются category-файлы YAML + `_meta.yaml`.

Категории согласованы с `src/knowledge/data/` основного проекта.
