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
from .models import (
    AnalysisResult,
    ArchitectureSummary,
    EntitySummary,
    ModuleSummary,
)
from .summarizer import EntitySummarizer

logger = get_logger("pipeline")


# System prompt for module summarization
MODULE_SUMMARY_PROMPT = """You are a software architect analyzing a code module.
Based on the summaries of its components, provide a module-level summary.

Respond in JSON format:
{
  "summary": "2-3 sentences describing the module's overall purpose",
  "responsibilities": ["responsibility1", "responsibility2"],
  "dependencies": ["module1", "module2"],
  "exports": ["main_class1", "main_function1"]
}"""


# System prompt for architecture synthesis
ARCHITECTURE_PROMPT = """You are a senior software architect.
Based on the module summaries, provide a high-level architecture overview.

Respond in JSON format:
{
  "overview": "3-5 sentences describing the system's purpose and architecture",
  "patterns_detected": ["pattern1", "pattern2"],
  "tech_stack": ["technology1", "technology2"],
  "data_flow": "Description of how data flows through the system",
  "key_components": ["component1", "component2"]
}"""


class AnalysisPipeline:
    """Orchestrator for bottom-up codebase analysis.

    Pipeline stages:
    1. Entity summarization (bottom-up by DAG levels)
    2. Module aggregation (group summaries by directory)
    3. Architecture synthesis (high-level overview)
    """

    def __init__(
        self,
        graph: DependencyGraph,
        api_base: str = "http://localhost:11434/v1",
        model: str = "qwen3:14b",
        config: AppConfig | None = None,
    ):
        """Initialize pipeline.

        Args:
            graph: Populated dependency graph from indexer
            api_base: LLM API base URL
            model: Model name to use
            config: Optional app configuration
        """
        self.graph = graph
        self.api_base = api_base
        self.model = model
        self.config = config or get_config()

        self.summarizer = EntitySummarizer(
            api_base=api_base,
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

        # Call LLM
        client = await self._get_client()
        try:
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": MODULE_SUMMARY_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 600,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

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
                entity_count=len(entity_summaries),
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
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

        # Call LLM
        client = await self._get_client()
        try:
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": ARCHITECTURE_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            # Parse JSON response
            parsed = self._parse_json_response(content)

            return ArchitectureSummary(
                overview=parsed.get("overview", ""),
                modules=list(module_summaries.keys()),
                patterns_detected=parsed.get("patterns_detected", []),
                tech_stack=parsed.get("tech_stack", []),
                data_flow=parsed.get("data_flow", ""),
                key_components=parsed.get("key_components", []),
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

        except Exception as e:
            logger.error(f"Architecture synthesis failed: {e}")
            return ArchitectureSummary(
                overview=f"System with {len(module_summaries)} modules",
                modules=list(module_summaries.keys()),
            )

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        import json
        import re

        try:
            # Handle markdown code blocks
            if "```json" in content:
                match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)
            elif "```" in content:
                match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON response")
            return {}


async def analyze_codebase(
    graph: DependencyGraph,
    api_base: str = "http://localhost:11434/v1",
    model: str = "qwen3:14b",
    output_path: Path | None = None,
    max_concurrent: int = 5,
) -> AnalysisResult:
    """Convenience function for running full analysis.

    Args:
        graph: Populated dependency graph
        api_base: LLM API base URL
        model: Model name
        output_path: Optional path to save results
        max_concurrent: Maximum concurrent LLM calls

    Returns:
        Analysis result
    """
    pipeline = AnalysisPipeline(
        graph=graph,
        api_base=api_base,
        model=model,
    )

    try:
        result = await pipeline.analyze(max_concurrent=max_concurrent)

        if output_path:
            result.save(output_path)
            logger.info(f"Results saved to {output_path}")

        return result
    finally:
        await pipeline.close()
