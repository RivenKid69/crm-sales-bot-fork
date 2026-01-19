"""Configuration system for Codebase Analyzer using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM inference configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    # Model settings
    model_name: str = Field(
        default="Qwen/Qwen3-30B-A3B-GPTQ-Int4",
        description="Model name or path for vLLM",
    )
    quantization: Literal["gptq", "awq", "none"] = Field(
        default="gptq",
        description="Quantization method",
    )
    max_model_len: int = Field(
        default=65536,
        description="Maximum context length",
    )

    # vLLM settings
    gpu_memory_utilization: float = Field(
        default=0.92,
        ge=0.5,
        le=0.99,
        description="GPU memory utilization (0.5-0.99)",
    )
    max_num_batched_tokens: int = Field(
        default=8192,
        description="Maximum number of batched tokens for throughput",
    )
    enable_chunked_prefill: bool = Field(
        default=True,
        description="Enable chunked prefill for better latency",
    )
    enable_prefix_caching: bool = Field(
        default=True,
        description="Enable prefix caching for repeated prompts",
    )

    # Generation settings
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, description="Max tokens per generation")

    # API settings (for vLLM server mode)
    api_base: str = Field(
        default="http://localhost:8000/v1",
        description="vLLM API base URL",
    )
    api_key: str = Field(default="EMPTY", description="API key (EMPTY for local)")


class EmbeddingConfig(BaseSettings):
    """Embedding model configuration."""

    model_config = SettingsConfigDict(env_prefix="EMBED_")

    model_name: str = Field(
        default="Qodo/Qodo-Embed-1-1.5B",
        description="Embedding model (Qodo-Embed recommended for code)",
    )
    device: Literal["cuda", "cpu", "auto"] = Field(
        default="auto",
        description="Device for embedding model",
    )
    batch_size: int = Field(
        default=32,
        description="Batch size for embedding generation",
    )
    normalize: bool = Field(
        default=True,
        description="Normalize embeddings for cosine similarity",
    )


class RAGConfig(BaseSettings):
    """RAG retrieval configuration."""

    model_config = SettingsConfigDict(env_prefix="RAG_")

    # Vector DB
    vector_db: Literal["qdrant", "milvus", "chroma"] = Field(
        default="qdrant",
        description="Vector database to use",
    )
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    collection_name: str = Field(default="codebase_chunks")

    # Retrieval settings
    top_k_initial: int = Field(
        default=50,
        description="Initial retrieval count before reranking",
    )
    top_k_final: int = Field(
        default=10,
        description="Final context chunks after reranking",
    )
    rrf_k: int = Field(
        default=60,
        description="RRF (Reciprocal Rank Fusion) k parameter",
    )

    # Hybrid retrieval weights
    bm25_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    dense_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    graph_weight: float = Field(default=0.2, ge=0.0, le=1.0)

    # Reranking
    enable_reranking: bool = Field(default=True)
    reranker_model: str = Field(
        default="colbert",
        description="Reranker: colbert or cross-encoder",
    )


class ChunkingConfig(BaseSettings):
    """Code chunking configuration."""

    model_config = SettingsConfigDict(env_prefix="CHUNK_")

    strategy: Literal["ast", "semantic", "fixed"] = Field(
        default="ast",
        description="Chunking strategy (ast recommended)",
    )
    chunk_size_tokens: int = Field(
        default=1500,
        description="Target chunk size in tokens (1000-1500 recommended)",
    )
    chunk_overlap_percent: float = Field(
        default=0.1,
        ge=0.0,
        le=0.5,
        description="Overlap between chunks (10-15% recommended)",
    )
    min_chunk_size: int = Field(
        default=100,
        description="Minimum chunk size to avoid tiny fragments",
    )


class IndexerConfig(BaseSettings):
    """Code indexing configuration."""

    model_config = SettingsConfigDict(env_prefix="INDEX_")

    # Languages to parse
    languages: list[str] = Field(
        default=["php", "go", "typescript", "javascript"],
        description="Programming languages to index",
    )

    # File patterns
    include_patterns: list[str] = Field(
        default=["**/*.php", "**/*.go", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"],
    )
    exclude_patterns: list[str] = Field(
        default=[
            "**/node_modules/**",
            "**/vendor/**",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
            "**/__pycache__/**",
            "**/test/**",
            "**/tests/**",
        ],
    )

    # Processing
    max_file_size_mb: float = Field(
        default=5.0,
        description="Skip files larger than this",
    )
    parallel_workers: int = Field(
        default=8,
        description="Number of parallel workers for indexing",
    )


class GeneratorConfig(BaseSettings):
    """Documentation generator configuration."""

    model_config = SettingsConfigDict(env_prefix="GEN_")

    output_format: Literal["markdown", "html", "both"] = Field(
        default="markdown",
    )
    detail_level: Literal["minimal", "modular", "detailed"] = Field(
        default="modular",
        description="Documentation detail level",
    )
    include_code_snippets: bool = Field(default=True)
    include_diagrams: bool = Field(default=False)
    language: Literal["en", "ru"] = Field(
        default="ru",
        description="Documentation language",
    )


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Sub-configurations
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    indexer: IndexerConfig = Field(default_factory=IndexerConfig)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)

    # Paths
    project_root: Path = Field(
        default=Path.cwd(),
        description="Root directory of the codebase to analyze",
    )
    output_dir: Path = Field(
        default=Path("./docs"),
        description="Output directory for documentation",
    )
    cache_dir: Path = Field(
        default=Path("./.codebase-analyzer-cache"),
        description="Cache directory for intermediate results",
    )
    index_dir: Path = Field(
        default=Path("./.codebase-analyzer-index"),
        description="Directory for code index",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_file: Path | None = Field(default=None)

    # Processing
    batch_size: int = Field(
        default=10,
        description="Batch size for LLM analysis",
    )
    max_retries: int = Field(default=3)
    retry_delay: float = Field(default=1.0)

    @field_validator("project_root", "output_dir", "cache_dir", "index_dir", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve paths to absolute."""
        return Path(v).resolve()

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        """Load configuration from YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        import yaml

        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, allow_unicode=True)


# Global config instance (lazy-loaded)
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from file or create default."""
    global _config
    if path and path.exists():
        _config = AppConfig.from_yaml(path)
    else:
        _config = AppConfig()
    return _config
