"""Entity summarization using LLM for bottom-up code analysis."""

import asyncio
import hashlib
import json
import re
from typing import Any

from ..config import AppConfig, get_config
from ..indexer.models.entities import CodeEntity, EntityType
from ..indexer.graph.dependency_graph import DependencyGraph
from ..utils.logging import get_logger
from .models import EntitySummary

logger = get_logger("summarizer")


# System prompt for entity summarization
SUMMARIZER_SYSTEM_PROMPT = """Ты - дружелюбный наставник, который объясняет код начинающим разработчикам.
Пиши понятно и просто, как будто объясняешь джуну за чашкой кофе.

Правила:
1. Объясняй ЧТО делает код простыми словами, избегай сложных терминов
2. Используй аналогии из реальной жизни где уместно
3. Будь дружелюбным: 2-3 предложения для описания, одно для цели
4. Укажи область применения (например: авторизация, платежи, логирование, настройки, api, база данных, утилиты)
5. Перечисли главные возможности понятным языком (максимум 5)
6. Отвечай ТОЛЬКО валидным JSON без дополнительного текста

Формат ответа:
{
  "summary": "2-3 предложения что делает этот код, понятно для новичка",
  "purpose": "Одно предложение: зачем это нужно в проекте",
  "domain": "область применения",
  "key_behaviors": ["возможность1", "возможность2"],
  "dependencies_used": ["зависимость1", "зависимость2"]
}"""


class EntitySummarizer:
    """Bottom-up summarization of code entities using LLM.

    Key principle: When summarizing an entity, use SUMMARIES of its dependencies
    as context, not the full code. This keeps context size manageable for large
    codebases while preserving semantic information.
    """

    # JSON schema for entity summary (used with Ollama format parameter)
    ENTITY_SUMMARY_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "purpose": {"type": "string"},
            "domain": {"type": "string"},
            "key_behaviors": {"type": "array", "items": {"type": "string"}},
            "dependencies_used": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "purpose", "domain", "key_behaviors", "dependencies_used"],
    }

    def __init__(
        self,
        api_base: str = "http://localhost:11434",
        model: str = "ministral-3:14b-instruct-2512-q8_0",
        config: AppConfig | None = None,
    ):
        """Initialize summarizer.

        Args:
            api_base: Ollama API base URL (e.g. http://localhost:11434)
            model: Model name to use
            config: Optional app configuration
        """
        # Normalize base URL: strip /v1 suffix if present
        self.api_base = api_base.rstrip("/")
        if self.api_base.endswith("/v1"):
            self.api_base = self.api_base[:-3]
        self.model = model
        self.config = config or get_config()
        self._summaries: dict[str, EntitySummary] = {}
        self._http_client = None

    async def _get_client(self):
        """Get or create async HTTP client."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                base_url=self.api_base,
                timeout=120.0,
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def get_code_hash(self, entity: CodeEntity) -> str:
        """Compute hash of entity's source code for caching."""
        content = entity.source_code or ""
        # Normalize whitespace for consistent hashing
        normalized = " ".join(content.split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get_cached_summary(self, entity_id: str) -> EntitySummary | None:
        """Get previously computed summary."""
        return self._summaries.get(entity_id)

    async def summarize_entity(
        self,
        entity: CodeEntity,
        dependency_summaries: list[EntitySummary] | None = None,
    ) -> EntitySummary:
        """Summarize a single code entity.

        Args:
            entity: The code entity to summarize
            dependency_summaries: Summaries of entities this entity depends on
                                 (NOT their full code!)

        Returns:
            EntitySummary with LLM-generated summary
        """
        # Check cache first
        cached = self.get_cached_summary(entity.id)
        if cached:
            return cached

        # Build context from dependency summaries
        context = self._build_context(dependency_summaries or [])

        # Build prompt
        prompt = self._build_prompt(entity, context)

        # Call LLM
        response = await self._call_llm(prompt)

        # Parse response
        summary = self._parse_response(entity.id, response, entity)

        # Cache result
        self._summaries[entity.id] = summary

        return summary

    def _build_context(self, dep_summaries: list[EntitySummary]) -> str:
        """Build context string from dependency summaries.

        This is the KEY OPTIMIZATION: we use short summaries instead of
        full source code, keeping context size O(deps * summary_length)
        instead of O(deps * code_length).

        Example output:
        Dependencies:
        - src/auth/base.py::AuthProvider: Base class for authentication providers
        - src/config.py::Settings: Pydantic settings loaded from environment
        """
        if not dep_summaries:
            return "No internal dependencies."

        lines = ["Dependencies:"]
        for s in dep_summaries[:15]:  # Limit to 15 most important
            # Use purpose (shorter) instead of full summary
            lines.append(f"- {s.entity_id}: {s.purpose}")

        return "\n".join(lines)

    def _build_prompt(self, entity: CodeEntity, context: str) -> str:
        """Build prompt for entity summarization."""
        entity_type = entity.entity_type.value
        language = entity.language.value if hasattr(entity, 'language') else "code"

        # Limit source code length
        source = entity.source_code or ""
        if len(source) > 4000:
            source = source[:4000] + "\n... (truncated)"

        return f"""Analyze this {entity_type} and provide a structured summary.

{context}

Code:
```{language}
{source}
```

Entity name: {entity.name}
Entity type: {entity_type}

Respond in JSON format as specified."""

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        """Call Ollama native API with two-step approach.

        Step 1: LLM thinks freely (think=true, no format constraint)
        Step 2: Feed reasoning back, request structured JSON (think=false, format=schema)

        This preserves Qwen3 reasoning quality while ensuring reliable JSON output.
        """
        client = await self._get_client()
        total_in = 0
        total_out = 0

        try:
            # Step 1: Think freely
            resp1 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "think": True,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 512,
                    },
                },
            )
            resp1.raise_for_status()
            data1 = resp1.json()
            msg1 = data1.get("message", {})
            reasoning = msg1.get("content", "")
            total_in += data1.get("prompt_eval_count", 0)
            total_out += data1.get("eval_count", 0)

            # Step 2: Format as structured JSON using the reasoning
            resp2 = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": reasoning},
                        {"role": "user", "content": "Теперь оформи свой анализ в JSON формате как указано в инструкции."},
                    ],
                    "stream": False,
                    "think": False,
                    "format": self.ENTITY_SUMMARY_SCHEMA,
                    "options": {
                        "temperature": 0,
                        "num_predict": 512,
                    },
                },
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            msg2 = data2.get("message", {})
            content = msg2.get("content", "")
            total_in += data2.get("prompt_eval_count", 0)
            total_out += data2.get("eval_count", 0)

            return {
                "content": content,
                "input_tokens": total_in,
                "output_tokens": total_out,
            }
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "content": "{}",
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            }

    def _parse_response(
        self,
        entity_id: str,
        response: dict[str, Any],
        entity: CodeEntity,
    ) -> EntitySummary:
        """Parse LLM response into EntitySummary."""
        content = response.get("content", "{}")

        # Try to extract JSON from response
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
                # Find JSON object pattern
                match = re.search(r"\{[\s\S]*\}", content)
                if match:
                    content = match.group(0)

            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response for {entity_id}")
            logger.debug(f"Parse error: {e}")
            logger.debug(f"Raw content (first 500 chars): {content[:500]}")
            # Create fallback summary
            parsed = {
                "summary": f"Code entity: {entity.name}",
                "purpose": f"Implements {entity.entity_type.value} functionality",
                "domain": "unknown",
                "key_behaviors": [],
                "dependencies_used": [],
            }

        return EntitySummary(
            entity_id=entity_id,
            summary=parsed.get("summary", ""),
            purpose=parsed.get("purpose", ""),
            domain=parsed.get("domain", "unknown"),
            key_behaviors=parsed.get("key_behaviors", [])[:5],
            dependencies_used=parsed.get("dependencies_used", [])[:10],
            input_tokens=response.get("input_tokens", 0),
            output_tokens=response.get("output_tokens", 0),
            model=self.model,
            code_hash=self.get_code_hash(entity),
        )

    async def summarize_level(
        self,
        entity_ids: list[str],
        graph: DependencyGraph,
        max_concurrent: int = 5,
    ) -> list[EntitySummary]:
        """Summarize all entities at a processing level in parallel.

        Args:
            entity_ids: IDs of entities to summarize (all at same DAG level)
            graph: Dependency graph for looking up entities and dependencies
            max_concurrent: Maximum concurrent LLM calls

        Returns:
            List of summaries for all entities in this level
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def summarize_one(entity_id: str) -> EntitySummary | None:
            async with semaphore:
                entity = graph.get_entity(entity_id)
                if not entity:
                    logger.warning(f"Entity not found: {entity_id}")
                    return None

                # Get dependency summaries (already computed in previous levels)
                dep_ids = graph.get_dependency_ids(entity_id)
                dep_summaries = [
                    self._summaries[d]
                    for d in dep_ids
                    if d in self._summaries
                ]

                try:
                    return await self.summarize_entity(entity, dep_summaries)
                except Exception as e:
                    logger.error(f"Failed to summarize {entity_id}: {e}")
                    return None

        tasks = [summarize_one(eid) for eid in entity_ids]
        results = await asyncio.gather(*tasks)

        # Filter None results
        summaries = [s for s in results if s is not None]

        logger.info(f"Summarized {len(summaries)}/{len(entity_ids)} entities at level")
        return summaries

    async def summarize_all(
        self,
        graph: DependencyGraph,
        max_concurrent: int = 5,
    ) -> dict[str, EntitySummary]:
        """Summarize all entities in the graph using bottom-up order.

        This is the main entry point for full codebase summarization.

        Args:
            graph: Dependency graph with all entities
            max_concurrent: Maximum concurrent LLM calls per level

        Returns:
            Dictionary mapping entity IDs to their summaries
        """
        # Get processing levels (topological order)
        levels = graph.get_processing_levels()

        total_entities = sum(len(level) for level in levels)
        processed = 0

        logger.info(f"Starting bottom-up summarization: {total_entities} entities in {len(levels)} levels")

        for level_idx, entity_ids in enumerate(levels):
            logger.info(f"Processing level {level_idx + 1}/{len(levels)}: {len(entity_ids)} entities")

            await self.summarize_level(entity_ids, graph, max_concurrent)

            processed += len(entity_ids)
            logger.info(f"Progress: {processed}/{total_entities} ({100 * processed // total_entities}%)")

        return self._summaries

    @property
    def summaries(self) -> dict[str, EntitySummary]:
        """Get all computed summaries."""
        return self._summaries

    def clear_cache(self):
        """Clear all cached summaries."""
        self._summaries.clear()
