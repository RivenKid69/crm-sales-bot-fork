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
