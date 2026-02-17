# Knowledge Base

## 1. Хранилище

Данные знаний: `src/knowledge/data/*.yaml`

Категории:
- `analytics`
- `competitors`
- `employees`
- `equipment`
- `faq`
- `features`
- `fiscal`
- `integrations`
- `inventory`
- `mobile`
- `pricing`
- `products`
- `promotions`
- `regions`
- `stability`
- `support`
- `tis`

## 2. Retrieval pipeline

Класс: `CascadeRetriever` (`src/knowledge/retriever.py`).

Этапы поиска:
1. `exact`
2. `lemma`
3. `semantic` (если включены embeddings)

После поиска возможен rerank (`src/knowledge/reranker.py`) по порогам из `settings.yaml`.

## 3. Routing

- Базовый intent->category mapping: `INTENT_TO_CATEGORY` в `src/knowledge/retriever.py`.
- Дополнительный LLM category routing: `src/knowledge/category_router.py` (включается настройкой `category_router.enabled`).

## 4. Конфигурация

`src/settings.yaml`:
- `retriever.use_embeddings`
- `retriever.embedder_model`
- `retriever.thresholds.*`
- `retriever.default_top_k`
- `reranker.enabled`
- `reranker.threshold`
- `reranker.candidates_count`

## 5. Публичные методы retriever

- `retrieve(...) -> str`
- `retrieve_with_urls(...) -> tuple[str, list[dict]]`
- `search(...) -> list[SearchResult]`
- `search_with_stats(...) -> tuple[list[SearchResult], dict]`

## 6. Enhanced Autonomous Retrieval

Feature flag: `enhanced_autonomous_retrieval` (OFF по умолчанию).

Используется **только** автономным flow (`--flow autonomous`). Стандартные flow (spin_selling, aida и др.) не используют этот pipeline.

### Зачем

В базовом автономном режиме факты грузятся по категориям из YAML-конфига состояния (`autonomous_kb.py`). Это значит: одни и те же факты для любого вопроса в рамках фазы, без адаптации к запросу клиента.

Enhanced Retrieval делает поиск **query-driven** — факты подбираются под конкретный вопрос клиента с помощью LLM (Qwen).

### Pipeline (8 этапов)

```
User message
    │
    ▼
[0] Fast path ──── greeting/farewell → fallback на load_facts_for_state()
    │
    ▼
[1] Query Rewrite (LLM) ── раскрытие местоимений, follow-up → standalone запрос
    │
    ▼
[2] Category Routing (LLM, опционально) ── определение категорий KB
    │
    ▼
[3] Base Retrieval ── CascadeRetriever.search() по переписанному запросу
    │
    ▼
[4] Complexity Detection (rule-based) ── сложный запрос?
    │ нет                          │ да
    ▼                              ▼
    │                    [5] Query Decomposition (LLM)
    │                         ↓
    │                    Multi-query retrieval по подзапросам
    │                         ↓
    ├─────────────────── [6] RRF Fusion (слияние результатов)
    │
    ▼
[7] Long-Context Reorder ── zigzag (важное по краям контекстного окна)
    │
    ▼
[8] State Backfill ── дополнение фактами фазы (оставшийся бюджет)
    │
    ▼
facts_text + urls → ResponseGenerator
```

### Компоненты

| Компонент | Файл | LLM? | Описание |
|-----------|------|------|----------|
| `QueryRewriter` | `enhanced_retrieval.py` | Да | Переписывает follow-up в standalone запрос |
| `CategoryRouter` | `category_router.py` | Да | Определяет категории KB для поиска |
| `ComplexityDetector` | `enhanced_retrieval.py` | Нет | Rule-based: `?` count, маркеры сравнения, паттерны |
| `QueryDecomposer` | `enhanced_retrieval.py` | Да | Разбивает сложный запрос на подзапросы (до 4) |
| `MultiQueryRetriever` | `enhanced_retrieval.py` | Нет | Параллельный поиск + RRF merge |
| `LongContextReorder` | `enhanced_retrieval.py` | Нет | Zigzag для lost-in-the-middle |
| `load_facts_for_state` | `autonomous_kb.py` | Нет | Статическая загрузка по kb_categories |

### Бюджет контекста

- `max_kb_chars` (default: 40 000, ~10K tokens) — общий бюджет
- Query-driven факты получают приоритет
- State-context заполняет оставшийся бюджет
- Разделитель: `=== КОНТЕКСТ ЭТАПА ===`

### Fact rotation

Секции, показанные в недавних тёрнах (`recently_used_keys`), деприоритизируются. Свежие секции идут первыми в token window.

### Конфигурация (`settings.yaml`)

```yaml
enhanced_retrieval:
  max_kb_chars: 40000
  top_k_per_sub_query: 3
  max_sub_queries: 4
  rrf_k: 60
  rewrite_min_words: 4
  min_complexity_length: 30
```

### Интеграция с генератором

`ResponseGenerator.generate()` (`src/generator.py`) выбирает путь:

```
if autonomous + enhanced_autonomous_retrieval:
    → EnhancedRetrievalPipeline.retrieve()
elif autonomous:
    → load_facts_for_state()
else:
    → CascadeRetriever.retrieve()
```
