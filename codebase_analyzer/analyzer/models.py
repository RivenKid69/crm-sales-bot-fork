"""Data models for analysis results."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass
class EntitySummary:
    """Result of summarizing a single code entity."""

    entity_id: str
    summary: str  # 2-3 sentences describing what this code does
    purpose: str  # One sentence: why this exists
    domain: str  # Business domain (e.g., auth, payments, logging)
    key_behaviors: list[str] = field(default_factory=list)  # Key actions/behaviors
    dependencies_used: list[str] = field(default_factory=list)  # Important dependencies

    # Metadata
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    code_hash: str = ""  # For caching

    def to_context_string(self) -> str:
        """Short representation for use as context in other summaries."""
        return f"{self.entity_id}: {self.purpose}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entity_id": self.entity_id,
            "summary": self.summary,
            "purpose": self.purpose,
            "domain": self.domain,
            "key_behaviors": self.key_behaviors,
            "dependencies_used": self.dependencies_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "code_hash": self.code_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntitySummary":
        """Deserialize from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            summary=data["summary"],
            purpose=data["purpose"],
            domain=data.get("domain", "unknown"),
            key_behaviors=data.get("key_behaviors", []),
            dependencies_used=data.get("dependencies_used", []),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            model=data.get("model", ""),
            code_hash=data.get("code_hash", ""),
        )


@dataclass
class ModuleSummary:
    """Summary of a code module (directory/package)."""

    path: str  # Module path (e.g., "src/auth")
    name: str  # Module name (e.g., "auth")
    summary: str  # Overall module description
    entities: list[str] = field(default_factory=list)  # Entity IDs in this module
    domains: list[str] = field(default_factory=list)  # Business domains covered
    responsibilities: list[str] = field(default_factory=list)  # Key responsibilities
    dependencies: list[str] = field(default_factory=list)  # Dependencies on other modules
    exports: list[str] = field(default_factory=list)  # Main exported entities

    # Metrics
    entity_count: int = 0
    total_lines: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "name": self.name,
            "summary": self.summary,
            "entities": self.entities,
            "domains": self.domains,
            "responsibilities": self.responsibilities,
            "dependencies": self.dependencies,
            "exports": self.exports,
            "entity_count": self.entity_count,
            "total_lines": self.total_lines,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleSummary":
        """Deserialize from dictionary."""
        return cls(
            path=data["path"],
            name=data.get("name", Path(data["path"]).name),
            summary=data["summary"],
            entities=data.get("entities", []),
            domains=data.get("domains", []),
            responsibilities=data.get("responsibilities", []),
            dependencies=data.get("dependencies", []),
            exports=data.get("exports", []),
            entity_count=data.get("entity_count", 0),
            total_lines=data.get("total_lines", 0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


@dataclass
class ArchitectureSummary:
    """High-level architecture overview of the codebase."""

    overview: str  # Overall system description
    modules: list[str] = field(default_factory=list)  # List of module paths
    patterns_detected: list[str] = field(default_factory=list)  # Architecture patterns
    tech_stack: list[str] = field(default_factory=list)  # Technologies used
    data_flow: str = ""  # Description of data flow
    key_components: list[str] = field(default_factory=list)  # Most important components
    external_dependencies: list[str] = field(default_factory=list)  # External libs/services
    diagram_mermaid: str = ""  # Mermaid diagram code

    # Metrics
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "overview": self.overview,
            "modules": self.modules,
            "patterns_detected": self.patterns_detected,
            "tech_stack": self.tech_stack,
            "data_flow": self.data_flow,
            "key_components": self.key_components,
            "external_dependencies": self.external_dependencies,
            "diagram_mermaid": self.diagram_mermaid,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArchitectureSummary":
        """Deserialize from dictionary."""
        return cls(
            overview=data["overview"],
            modules=data.get("modules", []),
            patterns_detected=data.get("patterns_detected", []),
            tech_stack=data.get("tech_stack", []),
            data_flow=data.get("data_flow", ""),
            key_components=data.get("key_components", []),
            external_dependencies=data.get("external_dependencies", []),
            diagram_mermaid=data.get("diagram_mermaid", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


@dataclass
class AnalysisResult:
    """Complete result of codebase analysis."""

    entity_summaries: dict[str, EntitySummary] = field(default_factory=dict)
    module_summaries: dict[str, ModuleSummary] = field(default_factory=dict)
    architecture: ArchitectureSummary | None = None

    # Metadata
    total_entities: int = 0
    total_modules: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    processing_time_seconds: float = 0.0
    model_used: str = ""
    analysis_timestamp: str = ""

    # Processing info
    processing_levels: list[list[str]] = field(default_factory=list)
    cycles_broken: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entity_summaries": {
                eid: s.to_dict() for eid, s in self.entity_summaries.items()
            },
            "module_summaries": {
                path: m.to_dict() for path, m in self.module_summaries.items()
            },
            "architecture": self.architecture.to_dict() if self.architecture else None,
            "total_entities": self.total_entities,
            "total_modules": self.total_modules,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "processing_time_seconds": self.processing_time_seconds,
            "model_used": self.model_used,
            "analysis_timestamp": self.analysis_timestamp,
            "processing_levels": self.processing_levels,
            "cycles_broken": self.cycles_broken,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisResult":
        """Deserialize from dictionary."""
        return cls(
            entity_summaries={
                eid: EntitySummary.from_dict(s)
                for eid, s in data.get("entity_summaries", {}).items()
            },
            module_summaries={
                path: ModuleSummary.from_dict(m)
                for path, m in data.get("module_summaries", {}).items()
            },
            architecture=(
                ArchitectureSummary.from_dict(data["architecture"])
                if data.get("architecture")
                else None
            ),
            total_entities=data.get("total_entities", 0),
            total_modules=data.get("total_modules", 0),
            total_tokens_in=data.get("total_tokens_in", 0),
            total_tokens_out=data.get("total_tokens_out", 0),
            processing_time_seconds=data.get("processing_time_seconds", 0.0),
            model_used=data.get("model_used", ""),
            analysis_timestamp=data.get("analysis_timestamp", ""),
            processing_levels=data.get("processing_levels", []),
            cycles_broken=data.get("cycles_broken", []),
        )

    def save(self, path: Path) -> None:
        """Save analysis result to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path) -> "AnalysisResult":
        """Load analysis result from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_summary_for_entity(self, entity_id: str) -> EntitySummary | None:
        """Get summary for a specific entity."""
        return self.entity_summaries.get(entity_id)

    def get_summaries_for_module(self, module_path: str) -> list[EntitySummary]:
        """Get all entity summaries for a module."""
        module = self.module_summaries.get(module_path)
        if not module:
            return []
        return [
            self.entity_summaries[eid]
            for eid in module.entities
            if eid in self.entity_summaries
        ]
