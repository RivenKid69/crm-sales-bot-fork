# План обновления Codebase-Analyzer

## Валидированная архитектура (на основе научных исследований)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ФАЗА 1: ИНДЕКСАЦИЯ (без LLM)                              │
│                    Детерминистическая, масштабируемая                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  1.1 AST Parsing      →  1.2 Dependency DAG  →  1.3 Embeddings              │
│  (tree-sitter)           (NetworkX)              (jina-code/voyage)          │
│                                                                              │
│  Результат: entities.json + graph.json + embeddings.qdrant                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ФАЗА 2: АНАЛИЗ (с LLM)                                    │
│                    Итерационная, bottom-up агрегация                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  2.1 Топологическая   →  2.2 Entity         →  2.3 Module      →  2.4 Arch  │
│      сортировка DAG       Summarization          Aggregation       Synthesis │
│                                                                              │
│  Контекст = код сущности + саммари зависимостей (НЕ полный код!)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ФАЗА 3: ГЕНЕРАЦИЯ                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  3.1 Templates  →  3.2 Markdown/HTML Export  →  3.3 Diagrams (optional)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Текущее состояние vs Целевое

| Компонент | Текущий статус | Целевой статус | Приоритет |
|-----------|----------------|----------------|-----------|
| AST Parsers | ⚠️ 60% (PHP ok, Go/TS partial) | ✅ 100% | P0 |
| Dependency Graph | ✅ 100% | ✅ + топологическая сортировка | P0 |
| Call Graph | ⚠️ Частично | ✅ Полный extraction | P1 |
| Embeddings | ❌ Stub | ✅ Jina/Voyage + Qdrant | P1 |
| Topological Sort | ❌ Нет | ✅ DAG ordering | P0 |
| Entity Summarizer | ❌ Нет | ✅ LLM summaries | P0 |
| Bottom-up Aggregation | ❌ Нет | ✅ Hierarchical merge | P0 |
| RAG Retrieval | ❌ Stub | ✅ Hybrid search | P2 |
| Incremental Mode | ❌ Нет | ✅ Hash-based cache | P1 |
| Generator | ❌ Stub | ✅ Markdown/HTML | P2 |

---

## ЭТАП 1: Фундамент (Фаза 1 - без LLM)

### 1.1 Усиление парсеров [P0] — 3-4 дня

**Файлы:** `indexer/parsers/go_parser.py`, `indexer/parsers/typescript_parser.py`

**Задачи:**

```python
# go_parser.py - добавить:
- _parse_struct_fields()      # Поля структур
- _parse_interface_methods()  # Методы интерфейсов
- _parse_function_calls()     # Вызовы функций в теле
- _extract_receiver_methods() # Методы с receiver'ами
- _parse_channel_operations() # Операции с каналами (опционально)

# typescript_parser.py - добавить:
- _parse_class_members()      # Полный парсинг методов/свойств
- _parse_function_body()      # Извлечение вызовов из тела
- _parse_jsx_components()     # React компоненты из JSX
- _parse_hooks_usage()        # Использование хуков
- _parse_type_definitions()   # Type aliases, interfaces полностью
```

**Тесты:** Использовать существующие `tests/codebase_analyzer/test_parsers.py`

---

### 1.2 Топологическая сортировка DAG [P0] — 1 день

**Файл:** `indexer/graph/dependency_graph.py`

**Добавить методы:**

```python
class DependencyGraph:

    def get_topological_order(self) -> list[str]:
        """Возвращает entity_ids в порядке зависимостей (листья первые).

        Использует алгоритм Кана для DAG.
        Циклические зависимости обрабатываются через SCC (Tarjan).
        """

    def get_leaf_entities(self) -> list[str]:
        """Сущности без исходящих зависимостей внутри проекта."""

    def get_processing_levels(self) -> list[list[str]]:
        """Группировка сущностей по уровням для параллельной обработки.

        Уровень 0: листья (нет зависимостей)
        Уровень 1: зависят только от уровня 0
        Уровень N: зависят от уровней 0..N-1
        """

    def break_cycles(self) -> list[tuple[str, str]]:
        """Находит и разрывает циклы, возвращая удалённые рёбра.

        Стратегия: удаляем ребро с минимальным весом в каждом цикле.
        """
```

**Алгоритм:**
1. Найти SCC (Strongly Connected Components) — `nx.strongly_connected_components()`
2. Для каждого SCC > 1 узла: разорвать цикл (минимальное ребро)
3. Топологическая сортировка результирующего DAG — `nx.topological_sort()`
4. Группировка по уровням для параллелизма

---

### 1.3 Модуль Embeddings [P1] — 2 дня

**Новый файл:** `indexer/embeddings/embedder.py`

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class CodeEmbedder:
    """Генерация embeddings для кода с использованием code-специфичных моделей."""

    def __init__(self, model_name: str = "jinaai/jina-embeddings-v2-base-code"):
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def embed_entity(self, entity: CodeEntity) -> np.ndarray:
        """Embedding для одной сущности.

        Контент = docstring + signature + первые N строк кода.
        """

    def embed_batch(self, entities: list[CodeEntity]) -> np.ndarray:
        """Batch embedding для эффективности."""

    def embed_text(self, text: str) -> np.ndarray:
        """Embedding для произвольного текста (для поиска)."""


class EmbeddingStore:
    """Хранение embeddings в Qdrant."""

    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)

    def create_collection(self, name: str, dimension: int):
        """Создание коллекции с HNSW индексом."""

    def upsert(self, collection: str, ids: list[str],
               vectors: np.ndarray, payloads: list[dict]):
        """Добавление/обновление embeddings."""

    def search(self, collection: str, query_vector: np.ndarray,
               top_k: int = 10, filter: dict = None) -> list[ScoredPoint]:
        """Поиск ближайших соседей."""
```

**Зависимости:**
```bash
pip install sentence-transformers qdrant-client
```

---

### 1.4 Обновление Indexer Pipeline [P0] — 1 день

**Файл:** `indexer/indexer.py`

**Изменения:**

```python
class CodebaseIndexer:

    def index(self, project_root: Path) -> IndexResult:
        """Полный pipeline индексации.

        1. discover_files()
        2. parse_files() → FileEntity[]
        3. build_graph() → DependencyGraph
        4. compute_topological_order() → ordered entity_ids  # NEW
        5. generate_embeddings() → store in Qdrant           # NEW
        6. compute_stats()
        7. save_index()
        """

    def compute_topological_order(self) -> list[list[str]]:
        """Вычисление порядка обработки для Фазы 2."""
        return self._dependency_graph.get_processing_levels()

    def generate_embeddings(self):
        """Генерация и сохранение embeddings."""
        embedder = CodeEmbedder(self.config.embedding.model_name)
        store = EmbeddingStore(
            self.config.rag.qdrant_host,
            self.config.rag.qdrant_port
        )
        # Batch processing всех сущностей

    def save_index(self, output_dir: Path) -> Path:
        """Сохранение индекса.

        Добавить:
        - processing_order.json  # Топологический порядок
        - embeddings_meta.json   # Метаданные Qdrant коллекции
        """
```

---

## ЭТАП 2: LLM Анализ (Фаза 2)

### 2.1 Entity Summarizer [P0] — 2 дня

**Новый файл:** `analyzer/summarizer.py`

```python
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class EntitySummary:
    """Результат суммаризации одной сущности."""
    entity_id: str
    summary: str           # 2-3 предложения
    purpose: str           # Одно предложение: зачем нужен
    domain: str            # Бизнес-домен (auth, payments, etc.)
    key_behaviors: list[str]  # Ключевые действия
    dependencies_used: list[str]  # Какие зависимости важны

    # Метаданные
    input_tokens: int
    output_tokens: int
    model: str

    def to_context_string(self) -> str:
        """Краткое представление для использования как контекст."""
        return f"{self.entity_id}: {self.purpose}"


class EntitySummarizer:
    """Bottom-up суммаризация сущностей кода."""

    def __init__(self, llm_client: VLLMClient, config: AnalyzerConfig):
        self.llm = llm_client
        self.config = config
        self._summaries: dict[str, EntitySummary] = {}

    async def summarize_entity(
        self,
        entity: CodeEntity,
        dependency_summaries: list[EntitySummary]
    ) -> EntitySummary:
        """Суммаризация одной сущности.

        Args:
            entity: Сущность для анализа
            dependency_summaries: Саммари зависимостей (НЕ их код!)
        """
        context = self._build_context(entity, dependency_summaries)
        prompt = self._build_prompt(entity, context)

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            max_tokens=500,
            temperature=0.1
        )

        return self._parse_response(entity.id, response)

    def _build_context(
        self,
        entity: CodeEntity,
        dep_summaries: list[EntitySummary]
    ) -> str:
        """Построение контекста из саммари зависимостей.

        Ключевая оптимизация: используем summary, не полный код!

        Пример:
        Dependencies:
        - src/auth/base.py::AuthProvider: "Базовый класс для провайдеров аутентификации"
        - src/config.py::Settings: "Pydantic настройки из ENV"
        """
        if not dep_summaries:
            return "No internal dependencies."

        lines = ["Dependencies:"]
        for s in dep_summaries[:10]:  # Ограничение контекста
            lines.append(f"- {s.entity_id}: {s.purpose}")
        return "\n".join(lines)

    def _build_prompt(self, entity: CodeEntity, context: str) -> str:
        """Промпт для суммаризации."""
        return f"""Analyze this {entity.entity_type.value} and provide a structured summary.

{context}

Code:
```{entity.language.value}
{entity.source_code}
```

Respond in JSON format:
{{
  "summary": "2-3 sentences describing what this code does",
  "purpose": "One sentence: why this exists",
  "domain": "business domain (e.g., auth, payments, logging)",
  "key_behaviors": ["behavior1", "behavior2"],
  "dependencies_used": ["dep1", "dep2"]
}}"""

    async def summarize_level(
        self,
        entity_ids: list[str],
        graph: DependencyGraph
    ) -> list[EntitySummary]:
        """Параллельная суммаризация одного уровня DAG."""
        tasks = []
        for eid in entity_ids:
            entity = graph.get_entity(eid)
            dep_ids = graph.get_dependencies(eid)
            dep_summaries = [self._summaries[d] for d in dep_ids if d in self._summaries]
            tasks.append(self.summarize_entity(entity, dep_summaries))

        results = await asyncio.gather(*tasks)
        for summary in results:
            self._summaries[summary.entity_id] = summary
        return results
```

**Системный промпт:**

```python
SUMMARIZER_SYSTEM_PROMPT = """You are a code documentation expert.
Analyze code and produce concise, accurate summaries.

Rules:
1. Focus on WHAT the code does, not HOW
2. Use domain terminology when appropriate
3. Be concise: 2-3 sentences for summary
4. Identify the business domain accurately
5. List only the most important behaviors (max 5)

Respond ONLY in valid JSON."""
```

---

### 2.2 Bottom-up Aggregation Pipeline [P0] — 2 дня

**Новый файл:** `analyzer/pipeline.py`

```python
class AnalysisPipeline:
    """Orchestrator для bottom-up анализа всей кодовой базы."""

    def __init__(
        self,
        graph: DependencyGraph,
        llm_client: VLLMClient,
        config: AppConfig
    ):
        self.graph = graph
        self.summarizer = EntitySummarizer(llm_client, config)
        self.config = config

    async def analyze(self) -> AnalysisResult:
        """Полный pipeline анализа.

        1. Получить уровни обработки (топологический порядок)
        2. Для каждого уровня: параллельная суммаризация
        3. Агрегация по модулям
        4. Генерация архитектурного обзора
        """
        levels = self.graph.get_processing_levels()

        # Прогресс
        total_entities = sum(len(level) for level in levels)
        processed = 0

        # Bottom-up обработка
        for level_idx, entity_ids in enumerate(levels):
            logger.info(f"Processing level {level_idx}: {len(entity_ids)} entities")

            summaries = await self.summarizer.summarize_level(
                entity_ids, self.graph
            )

            processed += len(entity_ids)
            logger.info(f"Progress: {processed}/{total_entities}")

        # Агрегация по модулям
        module_summaries = await self._aggregate_modules()

        # Архитектурный обзор
        architecture = await self._generate_architecture(module_summaries)

        return AnalysisResult(
            entity_summaries=self.summarizer._summaries,
            module_summaries=module_summaries,
            architecture=architecture
        )

    async def _aggregate_modules(self) -> dict[str, ModuleSummary]:
        """Агрегация саммари по директориям/модулям.

        Группировка по:
        - Директориям (src/auth/, src/payments/)
        - Detected clusters (Louvain)
        """
        modules = {}

        # Группировка по директориям
        by_directory = defaultdict(list)
        for eid, summary in self.summarizer._summaries.items():
            entity = self.graph.get_entity(eid)
            if entity:
                dir_path = entity.location.file_path.parent
                by_directory[dir_path].append(summary)

        # Суммаризация каждого модуля
        for dir_path, summaries in by_directory.items():
            if len(summaries) < 2:
                continue

            module_summary = await self._summarize_module(
                dir_path, summaries
            )
            modules[str(dir_path)] = module_summary

        return modules

    async def _summarize_module(
        self,
        path: Path,
        entity_summaries: list[EntitySummary]
    ) -> ModuleSummary:
        """Суммаризация одного модуля из его сущностей."""

        # Контекст = все саммари сущностей модуля
        context_lines = [f"Module: {path}"]
        for s in entity_summaries:
            context_lines.append(f"- {s.entity_id}: {s.purpose}")

        prompt = f"""Summarize this code module based on its components.

{chr(10).join(context_lines)}

Provide:
1. Module purpose (1-2 sentences)
2. Key responsibilities (bullet points)
3. Main entities and their roles
4. Dependencies on other modules"""

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="You are a software architect. Summarize modules concisely.",
            max_tokens=800
        )

        return ModuleSummary(
            path=path,
            summary=response.text,
            entities=[s.entity_id for s in entity_summaries],
            domains=list(set(s.domain for s in entity_summaries))
        )

    async def _generate_architecture(
        self,
        module_summaries: dict[str, ModuleSummary]
    ) -> ArchitectureSummary:
        """Генерация высокоуровневого архитектурного обзора."""

        context_lines = ["System modules:"]
        for path, ms in module_summaries.items():
            context_lines.append(f"\n## {path}")
            context_lines.append(ms.summary[:500])  # Ограничение

        prompt = f"""Based on these module summaries, provide a high-level architecture overview.

{chr(10).join(context_lines)}

Describe:
1. System purpose and main functionality
2. Architecture pattern (MVC, microservices, monolith, etc.)
3. Key modules and their interactions
4. Data flow between components
5. External dependencies and integrations"""

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt="You are a senior software architect.",
            max_tokens=2000
        )

        return ArchitectureSummary(
            overview=response.text,
            modules=list(module_summaries.keys()),
            patterns_detected=[],  # TODO: pattern detection
            diagram_suggestion=""   # TODO: Mermaid diagram
        )
```

---

### 2.3 Модели результатов анализа [P0] — 0.5 дня

**Новый файл:** `analyzer/models.py`

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class EntitySummary:
    entity_id: str
    summary: str
    purpose: str
    domain: str
    key_behaviors: list[str] = field(default_factory=list)
    dependencies_used: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    def to_context_string(self) -> str:
        return f"{self.entity_id}: {self.purpose}"


@dataclass
class ModuleSummary:
    path: Path
    summary: str
    entities: list[str]
    domains: list[str]
    responsibilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ArchitectureSummary:
    overview: str
    modules: list[str]
    patterns_detected: list[str]
    diagram_suggestion: str
    tech_stack: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    entity_summaries: dict[str, EntitySummary]
    module_summaries: dict[str, ModuleSummary]
    architecture: ArchitectureSummary

    # Метаданные
    total_entities: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    processing_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Сериализация для JSON."""

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisResult":
        """Десериализация из JSON."""
```

---

## ЭТАП 3: Инкрементальный режим

### 3.1 Hash-based кэширование [P1] — 1.5 дня

**Новый файл:** `analyzer/cache.py`

```python
import hashlib
import json
from pathlib import Path

class AnalysisCache:
    """Кэш результатов анализа на основе хэшей кода."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, CacheEntry] = {}
        self._load_index()

    def get_code_hash(self, entity: CodeEntity) -> str:
        """Вычисление хэша кода сущности."""
        content = entity.source_code or ""
        # Нормализация: убираем whitespace variations
        normalized = " ".join(content.split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get_cached_summary(self, entity_id: str, code_hash: str) -> EntitySummary | None:
        """Получение закэшированного саммари если хэш совпадает."""
        entry = self._index.get(entity_id)
        if entry and entry.code_hash == code_hash:
            return self._load_summary(entity_id)
        return None

    def cache_summary(self, summary: EntitySummary, code_hash: str):
        """Сохранение саммари в кэш."""
        self._index[summary.entity_id] = CacheEntry(
            entity_id=summary.entity_id,
            code_hash=code_hash,
            timestamp=time.time()
        )
        self._save_summary(summary)
        self._save_index()

    def invalidate_dependents(self, entity_id: str, graph: DependencyGraph):
        """Инвалидация кэша для всех зависимых сущностей.

        Если A зависит от B, и B изменился → инвалидировать A.
        """
        dependents = graph.get_dependents(entity_id)
        for dep_id in dependents:
            if dep_id in self._index:
                del self._index[dep_id]
        self._save_index()


@dataclass
class CacheEntry:
    entity_id: str
    code_hash: str
    timestamp: float
```

**Интеграция с pipeline:**

```python
class AnalysisPipeline:

    async def analyze_incremental(self) -> AnalysisResult:
        """Инкрементальный анализ с кэшированием."""

        # 1. Определить что изменилось
        changed_entities = []
        cached_summaries = {}

        for eid in self.graph.get_all_entity_ids():
            entity = self.graph.get_entity(eid)
            code_hash = self.cache.get_code_hash(entity)

            cached = self.cache.get_cached_summary(eid, code_hash)
            if cached:
                cached_summaries[eid] = cached
            else:
                changed_entities.append(eid)
                # Инвалидировать зависимых
                self.cache.invalidate_dependents(eid, self.graph)

        logger.info(f"Changed: {len(changed_entities)}, Cached: {len(cached_summaries)}")

        # 2. Пересчитать только изменённые (в топологическом порядке!)
        # ...
```

---

## ЭТАП 4: Генерация документации

### 4.1 Генератор Markdown [P2] — 1.5 дня

**Новый файл:** `generator/markdown.py`

```python
class MarkdownGenerator:
    """Генерация Markdown документации из результатов анализа."""

    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.template_env = self._setup_jinja()

    def generate(self, result: AnalysisResult, output_dir: Path):
        """Генерация полной документации."""

        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. README.md - архитектурный обзор
        self._generate_readme(result.architecture, output_dir)

        # 2. modules/ - документация по модулям
        for path, module in result.module_summaries.items():
            self._generate_module_doc(module, output_dir)

        # 3. api/ - API документация (если есть endpoints)
        self._generate_api_docs(result, output_dir)

        # 4. STRUCTURE.md - структура проекта
        self._generate_structure(result, output_dir)

    def _generate_readme(self, arch: ArchitectureSummary, output_dir: Path):
        """Генерация главного README."""
        template = self.template_env.get_template("readme.md.jinja")
        content = template.render(architecture=arch)
        (output_dir / "README.md").write_text(content)
```

**Шаблон `templates/readme.md.jinja`:**

```jinja
# {{ architecture.title or "Project Documentation" }}

## Overview

{{ architecture.overview }}

## Architecture

{{ architecture.patterns_detected | join(", ") if architecture.patterns_detected else "Not detected" }}

## Modules

{% for module in architecture.modules %}
- [{{ module | basename }}](modules/{{ module | slugify }}.md)
{% endfor %}

## Tech Stack

{% for tech in architecture.tech_stack %}
- {{ tech }}
{% endfor %}

---
*Generated by Codebase-Analyzer*
```

---

## ЭТАП 5: CLI и интеграция

### 5.1 Обновление CLI [P1] — 0.5 дня

**Файл:** `main.py`

```python
@app.command()
def analyze(
    index_path: Path,
    output: Optional[Path] = None,
    incremental: bool = True,
    model: str = "qwen3:14b",
    api_base: str = "http://localhost:11434/v1",  # Ollama по умолчанию
):
    """Анализ кодовой базы с помощью LLM."""

    # Загрузка индекса
    indexer = create_indexer(config)
    indexer.load_index(index_path)

    # Создание LLM клиента
    llm_config = LLMConfig(
        model_name=model,
        api_base=api_base
    )
    llm = VLLMClient(llm_config)

    # Pipeline анализа
    pipeline = AnalysisPipeline(
        graph=indexer.dependency_graph,
        llm_client=llm,
        config=config
    )

    if incremental:
        result = asyncio.run(pipeline.analyze_incremental())
    else:
        result = asyncio.run(pipeline.analyze())

    # Сохранение
    result_path = output or index_path / "analysis"
    save_analysis_result(result, result_path)

    console.print(f"[green]Analysis complete: {result_path}[/green]")


@app.command()
def generate(
    analysis_path: Path,
    output: Optional[Path] = None,
    format: str = "markdown",
):
    """Генерация документации из результатов анализа."""

    result = load_analysis_result(analysis_path)

    generator = MarkdownGenerator(config.generator)
    generator.generate(result, output or Path("./docs"))

    console.print(f"[green]Documentation generated[/green]")
```

---

## Сводка: Порядок реализации

| # | Задача | Приоритет | Время | Зависит от |
|---|--------|-----------|-------|------------|
| 1 | Топологическая сортировка DAG | P0 | 1 день | - |
| 2 | Усиление Go/TS парсеров | P0 | 3 дня | - |
| 3 | Модели результатов анализа | P0 | 0.5 дня | - |
| 4 | Entity Summarizer | P0 | 2 дня | 1, 3 |
| 5 | Bottom-up Pipeline | P0 | 2 дня | 1, 4 |
| 6 | Модуль Embeddings | P1 | 2 дня | - |
| 7 | Hash-based кэширование | P1 | 1.5 дня | 4, 5 |
| 8 | Обновление CLI | P1 | 0.5 дня | 5 |
| 9 | Генератор Markdown | P2 | 1.5 дня | 5 |
| 10 | RAG Retrieval (опционально) | P2 | 2 дня | 6 |

**Общее время: ~16 дней**

---

## Критические решения

### 1. Обработка циклов
```
Стратегия: SCC detection + разрыв минимальных рёбер
Альтернатива: обрабатывать SCC как один "суперузел"
```

### 2. Ограничение контекста
```
Max dependency summaries в контексте: 10-15
При превышении: сортировка по важности (weight в графе)
```

### 3. Параллелизм
```
Один уровень DAG = параллельная обработка (asyncio.gather)
Между уровнями = строго последовательно
```

### 4. Ollama vs vLLM
```
По умолчанию: Ollama (локальный, простой)
Опционально: vLLM (для production, batching)
API совместимы (OpenAI формат)
```

---

## Тестирование

### Unit тесты
- `test_topological_sort.py` - DAG ordering
- `test_summarizer.py` - mock LLM responses
- `test_cache.py` - hash invalidation

### Integration тесты
- `test_pipeline.py` - полный flow на тестовом проекте
- `test_incremental.py` - кэширование между запусками

### E2E тесты
- Реальный проект (crm_sales_bot сам себя)
- Сравнение результатов с ручной документацией

---

## Источники архитектурных решений

1. **RepoAgent (EMNLP 2024)** — DAG + bottom-up generation
2. **CodePlan (Microsoft FSE 2024)** — dependency-aware context
3. **Google FSE 2025** — AST + LLM combination
4. **Aider** — repository map concept
5. **LoCoBench 2025** — context window degradation data
