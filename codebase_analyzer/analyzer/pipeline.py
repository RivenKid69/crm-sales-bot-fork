"""Bottom-up analysis pipeline for codebase documentation."""

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import AppConfig, get_config
from ..indexer.graph.dependency_graph import DependencyGraph
from ..indexer.models.entities import CodeEntity, EntityType
from ..utils.logging import get_logger
from .cache import AnalysisCache
from .models import (
    AnalysisResult,
    ArchitectureSummary,
    EntitySummary,
    ModuleSummary,
)
from .summarizer import EntitySummarizer

logger = get_logger("pipeline")


# System prompt for module summarization
MODULE_SUMMARY_PROMPT = """Ты - дружелюбный наставник для начинающих разработчиков.
Объясни что делает этот модуль простым языком, как будто рассказываешь коллеге за чашкой кофе.

Важно:
- Опиши подробно, какую роль модуль играет в системе
- Объясни КАК модуль взаимодействует с другими модулями (кто его вызывает, кого вызывает он)
- Используй аналогии из реальной жизни

Отвечай ТОЛЬКО валидным JSON:
{
  "summary": "3-5 предложений подробно описывающих модуль и его роль в системе",
  "role_in_system": "Одно предложение: какую роль играет модуль в общей архитектуре",
  "responsibilities": ["что делает 1", "что делает 2", "что делает 3"],
  "uses_modules": ["какие модули использует этот модуль и зачем"],
  "used_by_modules": ["какие модули используют этот модуль и зачем"],
  "dependencies": ["внешние зависимости (библиотеки, интерфейсы)"],
  "exports": ["главные классы/функции которые экспортирует модуль"]
}"""


# System prompt for architecture synthesis
ARCHITECTURE_PROMPT = """Ты - опытный разработчик, который объясняет архитектуру проекта новичку.
Опиши как устроена система простым языком, используя аналогии из реальной жизни.

Важно:
- Покажи КАК модули связаны между собой
- Опиши путь данных через систему
- Используй понятные аналогии

Отвечай ТОЛЬКО валидным JSON:
{
  "overview": "5-7 предложений подробно описывающих систему и её архитектуру",
  "main_idea": "Одно предложение: главная идея/цель системы",
  "patterns_detected": ["паттерн 1 и где он используется", "паттерн 2 и где он используется"],
  "tech_stack": ["технология 1", "технология 2"],
  "data_flow": "Подробное описание как данные проходят через систему: откуда приходят, как обрабатываются, куда уходят",
  "module_relationships": ["Модуль A -> использует -> Модуль B для чего", "Модуль C -> зависит от -> Модуль D потому что"],
  "key_components": ["ключевой компонент 1 и его роль", "ключевой компонент 2 и его роль"],
  "entry_points": ["точка входа 1", "точка входа 2"]
}"""


class AnalysisPipeline:
    """Orchestrator for bottom-up codebase analysis.

    Pipeline stages:
    1. Entity summarization (bottom-up by DAG levels)
    2. Module aggregation (group summaries by directory)
    3. Architecture synthesis (high-level overview)
    """

    # JSON schema for module summary (Ollama format parameter)
    MODULE_SUMMARY_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "role_in_system": {"type": "string"},
            "responsibilities": {"type": "array", "items": {"type": "string"}},
            "uses_modules": {"type": "array", "items": {"type": "string"}},
            "used_by_modules": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "exports": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "role_in_system", "responsibilities", "uses_modules",
                      "used_by_modules", "dependencies", "exports"],
    }

    # JSON schema for architecture summary (Ollama format parameter)
    ARCHITECTURE_SCHEMA = {
        "type": "object",
        "properties": {
            "overview": {"type": "string"},
            "main_idea": {"type": "string"},
            "patterns_detected": {"type": "array", "items": {"type": "string"}},
            "tech_stack": {"type": "array", "items": {"type": "string"}},
            "data_flow": {"type": "string"},
            "module_relationships": {"type": "array", "items": {"type": "string"}},
            "key_components": {"type": "array", "items": {"type": "string"}},
            "entry_points": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["overview", "main_idea", "patterns_detected", "tech_stack",
                      "data_flow", "module_relationships", "key_components", "entry_points"],
    }

    def __init__(
        self,
        graph: DependencyGraph,
        api_base: str = "http://localhost:11434",
        model: str = "ministral-3:14b-instruct-2512-q8_0",
        config: AppConfig | None = None,
        cache: AnalysisCache | None = None,
    ):
        """Initialize pipeline.

        Args:
            graph: Populated dependency graph from indexer
            api_base: Ollama API base URL (e.g. http://localhost:11434)
            model: Model name to use
            config: Optional app configuration
            cache: Optional analysis cache for incremental analysis
        """
        self.graph = graph
        # Normalize base URL: strip /v1 suffix if present
        self.api_base = api_base.rstrip("/")
        if self.api_base.endswith("/v1"):
            self.api_base = self.api_base[:-3]
        self.model = model
        self.config = config or get_config()
        self.cache = cache

        self.summarizer = EntitySummarizer(
            api_base=self.api_base,
            model=model,
            config=config,
        )

        self._http_client = None

    async def _get_client(self):
        """Get or create async HTTP client."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=180.0,  # Longer timeout for aggregation
            )
        return self._http_client

    async def close(self):
        """Close all clients."""
        await self.summarizer.close()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def analyze(
        self,
        max_concurrent: int = 5,
        skip_architecture: bool = False,
    ) -> AnalysisResult:
        """Run full analysis pipeline.

        Args:
            max_concurrent: Maximum concurrent LLM calls
            skip_architecture: Skip architecture synthesis (faster)

        Returns:
            Complete analysis result
        """
        start_time = time.time()

        logger.info("Starting bottom-up analysis pipeline")

        # Get processing levels for reporting
        levels = self.graph.get_processing_levels()

        # Stage 1: Entity summarization
        logger.info("Stage 1: Entity summarization")
        entity_summaries = await self.summarizer.summarize_all(
            self.graph,
            max_concurrent=max_concurrent,
        )

        # Stage 2: Module aggregation
        logger.info("Stage 2: Module aggregation")
        module_summaries = await self._aggregate_modules(entity_summaries)

        # Stage 3: Architecture synthesis
        architecture = None
        if not skip_architecture and module_summaries:
            logger.info("Stage 3: Architecture synthesis")
            architecture = await self._synthesize_architecture(module_summaries)

        # Build result
        total_in = sum(s.input_tokens for s in entity_summaries.values())
        total_out = sum(s.output_tokens for s in entity_summaries.values())

        result = AnalysisResult(
            entity_summaries=entity_summaries,
            module_summaries=module_summaries,
            architecture=architecture,
            total_entities=len(entity_summaries),
            total_modules=len(module_summaries),
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            processing_time_seconds=time.time() - start_time,
            model_used=self.model,
            analysis_timestamp=datetime.now().isoformat(),
            processing_levels=[list(level) for level in levels],
        )

        logger.info(
            f"Analysis complete: {result.total_entities} entities, "
            f"{result.total_modules} modules, "
            f"{result.processing_time_seconds:.1f}s"
        )

        return result

    async def analyze_incremental(
        self,
        max_concurrent: int = 5,
        skip_architecture: bool = False,
    ) -> AnalysisResult:
        """Run incremental analysis using cache.

        Only analyzes entities that have changed since the last run.
        Unchanged entities are loaded from cache.

        Args:
            max_concurrent: Maximum concurrent LLM calls
            skip_architecture: Skip architecture synthesis (faster)

        Returns:
            Complete analysis result (mix of cached and fresh)
        """
        if not self.cache:
            logger.warning("No cache configured, falling back to full analysis")
            return await self.analyze(max_concurrent, skip_architecture)

        start_time = time.time()
        logger.info("Starting incremental analysis pipeline")

        # Phase 1: Determine what changed
        changed_entity_ids: list[str] = []
        cached_summaries: dict[str, EntitySummary] = {}

        all_entity_ids = self.graph.get_all_entity_ids()
        logger.info(f"Checking {len(all_entity_ids)} entities for changes")

        for entity_id in all_entity_ids:
            entity = self.graph.get_entity(entity_id)
            if not entity:
                continue

            code_hash = self.cache.get_code_hash(entity)

            # Try to get from cache
            cached = self.cache.get_cached_summary(entity_id, code_hash)
            if cached:
                cached_summaries[entity_id] = cached
            else:
                changed_entity_ids.append(entity_id)
                # Invalidate dependents (entities that depend on this one)
                self.cache.invalidate_dependents(
                    entity_id,
                    lambda eid: self.graph.get_dependent_ids(eid),
                )

        logger.info(
            f"Incremental status: {len(changed_entity_ids)} changed, "
            f"{len(cached_summaries)} cached"
        )

        # Phase 2: Analyze changed entities (respecting topological order)
        if changed_entity_ids:
            fresh_summaries = await self._analyze_entities_incremental(
                changed_entity_ids,
                cached_summaries,
                max_concurrent,
            )
            # Merge fresh summaries
            all_summaries = {**cached_summaries, **fresh_summaries}
        else:
            logger.info("No changes detected, using fully cached results")
            all_summaries = cached_summaries

        # Phase 3: Module aggregation
        logger.info("Stage 2: Module aggregation")
        module_summaries = await self._aggregate_modules(all_summaries)

        # Phase 4: Architecture synthesis
        architecture = None
        if not skip_architecture and module_summaries:
            logger.info("Stage 3: Architecture synthesis")
            architecture = await self._synthesize_architecture(module_summaries)

        # Build result
        levels = self.graph.get_processing_levels()
        total_in = sum(s.input_tokens for s in all_summaries.values())
        total_out = sum(s.output_tokens for s in all_summaries.values())

        result = AnalysisResult(
            entity_summaries=all_summaries,
            module_summaries=module_summaries,
            architecture=architecture,
            total_entities=len(all_summaries),
            total_modules=len(module_summaries),
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            processing_time_seconds=time.time() - start_time,
            model_used=self.model,
            analysis_timestamp=datetime.now().isoformat(),
            processing_levels=[list(level) for level in levels],
        )

        logger.info(
            f"Incremental analysis complete: {result.total_entities} entities "
            f"({len(changed_entity_ids)} analyzed, {len(cached_summaries)} cached), "
            f"{result.processing_time_seconds:.1f}s"
        )

        return result

    async def _analyze_entities_incremental(
        self,
        entity_ids: list[str],
        cached_summaries: dict[str, EntitySummary],
        max_concurrent: int,
    ) -> dict[str, EntitySummary]:
        """Analyze a subset of entities, using cached summaries as context.

        Processes entities in topological order to ensure dependencies
        (whether cached or fresh) are available as context.
        """
        # Get topological order to process dependencies first
        topo_order = self.graph.get_topological_order(break_cycles_if_needed=False)

        # Filter to only entities we need to analyze, but maintain order
        ordered_ids = [eid for eid in topo_order if eid in entity_ids]

        # If some IDs aren't in topo order, add them at the end
        remaining = set(entity_ids) - set(ordered_ids)
        ordered_ids.extend(remaining)

        logger.info(f"Analyzing {len(ordered_ids)} changed entities")

        fresh_summaries: dict[str, EntitySummary] = {}

        # Process in batches respecting dependencies
        # For simplicity, we process one at a time ensuring dependencies are ready
        # A more sophisticated approach would group by processing level
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_entity(entity_id: str) -> tuple[str, EntitySummary | None]:
            async with semaphore:
                entity = self.graph.get_entity(entity_id)
                if not entity:
                    return entity_id, None

                # Build context from dependencies (cached + fresh)
                all_available = {**cached_summaries, **fresh_summaries}
                dep_ids = self.graph.get_dependency_ids(entity_id)
                dep_summaries = [
                    all_available[did]
                    for did in dep_ids
                    if did in all_available
                ]

                # Create context string
                context = ""
                if dep_summaries:
                    context_lines = ["Dependencies:"]
                    for ds in dep_summaries[:10]:  # Limit context size
                        context_lines.append(f"- {ds.to_context_string()}")
                    context = "\n".join(context_lines)

                # Summarize the entity
                summary = await self.summarizer.summarize_entity(entity, context)

                # Cache the new summary
                if summary and self.cache:
                    code_hash = self.cache.get_code_hash(entity)
                    self.cache.cache_summary(summary, code_hash)

                return entity_id, summary

        # Process entities
        # For proper dependency ordering, process level by level
        processing_levels = self.graph.get_processing_levels(break_cycles_if_needed=False)

        for level_idx, level in enumerate(processing_levels):
            level_entities = [eid for eid in level if eid in entity_ids]
            if not level_entities:
                continue

            logger.debug(f"Processing level {level_idx}: {len(level_entities)} entities")

            tasks = [process_entity(eid) for eid in level_entities]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Entity processing failed: {result}")
                    continue
                entity_id, summary = result
                if summary:
                    fresh_summaries[entity_id] = summary

        return fresh_summaries

    async def _aggregate_modules(
        self,
        entity_summaries: dict[str, EntitySummary],
    ) -> dict[str, ModuleSummary]:
        """Aggregate entity summaries into module summaries.

        Groups entities by directory and generates module-level summaries.
        """
        # Group entities by directory
        by_directory: dict[str, list[EntitySummary]] = defaultdict(list)

        for entity_id, summary in entity_summaries.items():
            entity = self.graph.get_entity(entity_id)
            if entity:
                dir_path = str(entity.location.file_path.parent)
                by_directory[dir_path].append(summary)

        # Filter to directories with multiple entities
        significant_dirs = {
            path: summaries
            for path, summaries in by_directory.items()
            if len(summaries) >= 2  # At least 2 entities
        }

        logger.info(f"Aggregating {len(significant_dirs)} modules")

        # Generate module summaries
        module_summaries: dict[str, ModuleSummary] = {}

        for dir_path, summaries in significant_dirs.items():
            try:
                module_summary = await self._summarize_module(dir_path, summaries)
                module_summaries[dir_path] = module_summary
            except Exception as e:
                logger.error(f"Failed to summarize module {dir_path}: {e}")

        return module_summaries

    async def _summarize_module(
        self,
        dir_path: str,
        entity_summaries: list[EntitySummary],
    ) -> ModuleSummary:
        """Generate summary for a single module."""
        # Build context from entity summaries
        context_lines = [f"Module: {dir_path}", "Components:"]
        for s in entity_summaries[:20]:  # Limit for context size
            context_lines.append(f"- {s.entity_id.split('::')[-1]}: {s.purpose}")

        # Get unique domains
        domains = list(set(s.domain for s in entity_summaries if s.domain != "unknown"))

        prompt = f"""{chr(10).join(context_lines)}

Domains covered: {', '.join(domains) if domains else 'general'}

Summarize this module."""

        # Call LLM with two-step approach (think + structured output)
        client = await self._get_client()
        total_in = 0
        total_out = 0
        try:
            messages = [
                {"role": "system", "content": MODULE_SUMMARY_PROMPT},
                {"role": "user", "content": prompt},
            ]

            # Step 1: Think freely
            resp1 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 600,
                    },
                },
            )
            resp1.raise_for_status()
            data1 = resp1.json()
            reasoning = data1.get("message", {}).get("content", "")
            total_in += data1.get("prompt_eval_count", 0)
            total_out += data1.get("eval_count", 0)

            # Step 2: Format as structured JSON
            resp2 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages + [
                        {"role": "assistant", "content": reasoning},
                        {"role": "user", "content": "Теперь оформи свой анализ в JSON формате как указано в инструкции."},
                    ],
                    "stream": False,
                    "think": False,
                    "format": self.MODULE_SUMMARY_SCHEMA,
                    "options": {
                        "temperature": 0,
                        "num_predict": 600,
                    },
                },
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            content = data2.get("message", {}).get("content", "")
            total_in += data2.get("prompt_eval_count", 0)
            total_out += data2.get("eval_count", 0)

            # Parse JSON response
            parsed = self._parse_json_response(content)

            return ModuleSummary(
                path=dir_path,
                name=Path(dir_path).name,
                summary=parsed.get("summary", ""),
                entities=[s.entity_id for s in entity_summaries],
                domains=domains,
                responsibilities=parsed.get("responsibilities", []),
                dependencies=parsed.get("dependencies", []),
                exports=parsed.get("exports", []),
                role_in_system=parsed.get("role_in_system", ""),
                uses_modules=parsed.get("uses_modules", []),
                used_by_modules=parsed.get("used_by_modules", []),
                entity_count=len(entity_summaries),
                input_tokens=total_in,
                output_tokens=total_out,
            )

        except Exception as e:
            logger.error(f"Module summarization failed: {e}")
            return ModuleSummary(
                path=dir_path,
                name=Path(dir_path).name,
                summary=f"Module containing {len(entity_summaries)} components",
                entities=[s.entity_id for s in entity_summaries],
                domains=domains,
                entity_count=len(entity_summaries),
            )

    async def _synthesize_architecture(
        self,
        module_summaries: dict[str, ModuleSummary],
    ) -> ArchitectureSummary:
        """Synthesize high-level architecture from module summaries."""
        # Build context from module summaries
        context_lines = ["System modules:"]
        for path, module in list(module_summaries.items())[:30]:  # Limit modules
            context_lines.append(f"\n## {module.name}")
            if module.summary:
                context_lines.append(module.summary[:300])
            if module.responsibilities:
                context_lines.append(f"Responsibilities: {', '.join(module.responsibilities[:3])}")

        prompt = f"""{chr(10).join(context_lines)}

Total modules: {len(module_summaries)}

Provide a high-level architecture overview."""

        # Call LLM with two-step approach (think + structured output)
        client = await self._get_client()
        total_in = 0
        total_out = 0
        try:
            messages = [
                {"role": "system", "content": ARCHITECTURE_PROMPT},
                {"role": "user", "content": prompt},
            ]

            # Step 1: Think freely
            resp1 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1500,
                    },
                },
            )
            resp1.raise_for_status()
            data1 = resp1.json()
            reasoning = data1.get("message", {}).get("content", "")
            total_in += data1.get("prompt_eval_count", 0)
            total_out += data1.get("eval_count", 0)

            # Step 2: Format as structured JSON
            resp2 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages + [
                        {"role": "assistant", "content": reasoning},
                        {"role": "user", "content": "Теперь оформи свой анализ в JSON формате как указано в инструкции."},
                    ],
                    "stream": False,
                    "think": False,
                    "format": self.ARCHITECTURE_SCHEMA,
                    "options": {
                        "temperature": 0,
                        "num_predict": 1500,
                    },
                },
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            content = data2.get("message", {}).get("content", "")
            total_in += data2.get("prompt_eval_count", 0)
            total_out += data2.get("eval_count", 0)

            # Parse JSON response
            parsed = self._parse_json_response(content)

            return ArchitectureSummary(
                overview=parsed.get("overview", ""),
                modules=list(module_summaries.keys()),
                patterns_detected=parsed.get("patterns_detected", []),
                tech_stack=parsed.get("tech_stack", []),
                data_flow=parsed.get("data_flow", ""),
                key_components=parsed.get("key_components", []),
                main_idea=parsed.get("main_idea", ""),
                module_relationships=parsed.get("module_relationships", []),
                entry_points=parsed.get("entry_points", []),
                input_tokens=total_in,
                output_tokens=total_out,
            )

        except Exception as e:
            logger.error(f"Architecture synthesis failed: {e}")
            return ArchitectureSummary(
                overview=f"System with {len(module_summaries)} modules",
                modules=list(module_summaries.keys()),
            )

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks and think tags."""
        import json
        import re

        try:
            # Strip <think>...</think> tags (Qwen3 adds these)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            content = content.strip()

            # Handle markdown code blocks
            if "```json" in content:
                match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)
            elif "```" in content:
                match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            # Try to find raw JSON object if content doesn't start with {
            content = content.strip()
            if not content.startswith("{"):
                match = re.search(r"\{[\s\S]*\}", content)
                if match:
                    content = match.group(0)

            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON response")
            return {}


async def analyze_codebase(
    graph: DependencyGraph,
    api_base: str = "http://localhost:11434",
    model: str = "ministral-3:14b-instruct-2512-q8_0",
    output_path: Path | None = None,
    max_concurrent: int = 5,
    cache_dir: Path | None = None,
    incremental: bool = False,
) -> AnalysisResult:
    """Convenience function for running full or incremental analysis.

    Args:
        graph: Populated dependency graph
        api_base: LLM API base URL
        model: Model name
        output_path: Optional path to save results
        max_concurrent: Maximum concurrent LLM calls
        cache_dir: Optional directory for analysis cache
        incremental: Whether to use incremental analysis

    Returns:
        Analysis result
    """
    # Setup cache if incremental mode is enabled
    cache = None
    if incremental and cache_dir:
        cache = AnalysisCache(cache_dir=cache_dir, model=model)
        logger.info(f"Using incremental analysis with cache at {cache_dir}")

    pipeline = AnalysisPipeline(
        graph=graph,
        api_base=api_base,
        model=model,
        cache=cache,
    )

    try:
        if incremental and cache:
            result = await pipeline.analyze_incremental(max_concurrent=max_concurrent)
        else:
            result = await pipeline.analyze(max_concurrent=max_concurrent)

        if output_path:
            result.save(output_path)
            logger.info(f"Results saved to {output_path}")

        return result
    finally:
        await pipeline.close()
