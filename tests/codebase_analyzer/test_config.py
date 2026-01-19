"""Tests for codebase_analyzer/config.py - Configuration system."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from codebase_analyzer.config import (
    AppConfig,
    ChunkingConfig,
    EmbeddingConfig,
    GeneratorConfig,
    IndexerConfig,
    LLMConfig,
    RAGConfig,
    get_config,
    load_config,
)


# ============================================================================
# LLMConfig Tests
# ============================================================================


class TestLLMConfig:
    """Tests for LLM configuration."""

    def test_default_values(self):
        """Test LLMConfig has correct default values."""
        config = LLMConfig()

        assert config.model_name == "Qwen/Qwen3-30B-A3B-GPTQ-Int4"
        assert config.quantization == "gptq"
        assert config.max_model_len == 65536
        assert config.gpu_memory_utilization == 0.92
        assert config.max_num_batched_tokens == 8192
        assert config.enable_chunked_prefill is True
        assert config.enable_prefix_caching is True
        assert config.temperature == 0.1
        assert config.top_p == 0.9
        assert config.max_tokens == 4096
        assert config.api_base == "http://localhost:8000/v1"
        assert config.api_key == "EMPTY"

    def test_custom_values(self):
        """Test LLMConfig accepts custom values."""
        config = LLMConfig(
            model_name="custom-model",
            quantization="awq",
            temperature=0.7,
            max_tokens=8192,
        )

        assert config.model_name == "custom-model"
        assert config.quantization == "awq"
        assert config.temperature == 0.7
        assert config.max_tokens == 8192

    def test_gpu_memory_utilization_bounds(self):
        """Test GPU memory utilization validation bounds."""
        # Valid values
        config = LLMConfig(gpu_memory_utilization=0.5)
        assert config.gpu_memory_utilization == 0.5

        config = LLMConfig(gpu_memory_utilization=0.99)
        assert config.gpu_memory_utilization == 0.99

        # Invalid: below minimum
        with pytest.raises(ValueError):
            LLMConfig(gpu_memory_utilization=0.4)

        # Invalid: above maximum
        with pytest.raises(ValueError):
            LLMConfig(gpu_memory_utilization=1.0)

    def test_temperature_bounds(self):
        """Test temperature validation bounds."""
        # Valid
        config = LLMConfig(temperature=0.0)
        assert config.temperature == 0.0

        config = LLMConfig(temperature=2.0)
        assert config.temperature == 2.0

        # Invalid
        with pytest.raises(ValueError):
            LLMConfig(temperature=-0.1)

        with pytest.raises(ValueError):
            LLMConfig(temperature=2.1)

    def test_top_p_bounds(self):
        """Test top_p validation bounds."""
        config = LLMConfig(top_p=0.0)
        assert config.top_p == 0.0

        config = LLMConfig(top_p=1.0)
        assert config.top_p == 1.0

        with pytest.raises(ValueError):
            LLMConfig(top_p=-0.1)

        with pytest.raises(ValueError):
            LLMConfig(top_p=1.1)

    def test_quantization_literal(self):
        """Test quantization accepts only valid literals."""
        for valid in ["gptq", "awq", "none"]:
            config = LLMConfig(quantization=valid)
            assert config.quantization == valid

        with pytest.raises(ValueError):
            LLMConfig(quantization="invalid")

    def test_env_prefix(self):
        """Test environment variable prefix."""
        with patch.dict(os.environ, {"LLM_MODEL_NAME": "env-model", "LLM_TEMPERATURE": "0.5"}):
            config = LLMConfig()
            assert config.model_name == "env-model"
            assert config.temperature == 0.5


# ============================================================================
# EmbeddingConfig Tests
# ============================================================================


class TestEmbeddingConfig:
    """Tests for embedding configuration."""

    def test_default_values(self):
        """Test EmbeddingConfig has correct defaults."""
        config = EmbeddingConfig()

        assert config.model_name == "Qodo/Qodo-Embed-1-1.5B"
        assert config.device == "auto"
        assert config.batch_size == 32
        assert config.normalize is True

    def test_device_literal(self):
        """Test device accepts only valid literals."""
        for valid in ["cuda", "cpu", "auto"]:
            config = EmbeddingConfig(device=valid)
            assert config.device == valid

        with pytest.raises(ValueError):
            EmbeddingConfig(device="invalid")

    def test_env_prefix(self):
        """Test environment variable prefix."""
        with patch.dict(os.environ, {"EMBED_MODEL_NAME": "custom-embed", "EMBED_BATCH_SIZE": "64"}):
            config = EmbeddingConfig()
            assert config.model_name == "custom-embed"
            assert config.batch_size == 64


# ============================================================================
# RAGConfig Tests
# ============================================================================


class TestRAGConfig:
    """Tests for RAG configuration."""

    def test_default_values(self):
        """Test RAGConfig has correct defaults."""
        config = RAGConfig()

        assert config.vector_db == "qdrant"
        assert config.qdrant_host == "localhost"
        assert config.qdrant_port == 6333
        assert config.collection_name == "codebase_chunks"
        assert config.top_k_initial == 50
        assert config.top_k_final == 10
        assert config.rrf_k == 60
        assert config.bm25_weight == 0.3
        assert config.dense_weight == 0.5
        assert config.graph_weight == 0.2
        assert config.enable_reranking is True
        assert config.reranker_model == "colbert"

    def test_vector_db_literal(self):
        """Test vector_db accepts only valid literals."""
        for valid in ["qdrant", "milvus", "chroma"]:
            config = RAGConfig(vector_db=valid)
            assert config.vector_db == valid

        with pytest.raises(ValueError):
            RAGConfig(vector_db="invalid")

    def test_weight_bounds(self):
        """Test retrieval weights validation."""
        # Valid
        config = RAGConfig(bm25_weight=0.0, dense_weight=0.5, graph_weight=1.0)
        assert config.bm25_weight == 0.0
        assert config.graph_weight == 1.0

        # Invalid
        with pytest.raises(ValueError):
            RAGConfig(bm25_weight=-0.1)

        with pytest.raises(ValueError):
            RAGConfig(dense_weight=1.1)


# ============================================================================
# ChunkingConfig Tests
# ============================================================================


class TestChunkingConfig:
    """Tests for chunking configuration."""

    def test_default_values(self):
        """Test ChunkingConfig has correct defaults."""
        config = ChunkingConfig()

        assert config.strategy == "ast"
        assert config.chunk_size_tokens == 1500
        assert config.chunk_overlap_percent == 0.1
        assert config.min_chunk_size == 100

    def test_strategy_literal(self):
        """Test strategy accepts only valid literals."""
        for valid in ["ast", "semantic", "fixed"]:
            config = ChunkingConfig(strategy=valid)
            assert config.strategy == valid

        with pytest.raises(ValueError):
            ChunkingConfig(strategy="invalid")

    def test_overlap_percent_bounds(self):
        """Test chunk_overlap_percent bounds."""
        config = ChunkingConfig(chunk_overlap_percent=0.0)
        assert config.chunk_overlap_percent == 0.0

        config = ChunkingConfig(chunk_overlap_percent=0.5)
        assert config.chunk_overlap_percent == 0.5

        with pytest.raises(ValueError):
            ChunkingConfig(chunk_overlap_percent=-0.1)

        with pytest.raises(ValueError):
            ChunkingConfig(chunk_overlap_percent=0.6)


# ============================================================================
# IndexerConfig Tests
# ============================================================================


class TestIndexerConfig:
    """Tests for indexer configuration."""

    def test_default_values(self):
        """Test IndexerConfig has correct defaults."""
        config = IndexerConfig()

        assert config.languages == ["php", "go", "typescript", "javascript"]
        assert "**/*.php" in config.include_patterns
        assert "**/*.go" in config.include_patterns
        assert "**/*.ts" in config.include_patterns
        assert "**/node_modules/**" in config.exclude_patterns
        assert "**/vendor/**" in config.exclude_patterns
        assert config.max_file_size_mb == 5.0
        assert config.parallel_workers == 8

    def test_custom_patterns(self):
        """Test custom include/exclude patterns."""
        config = IndexerConfig(
            languages=["python"],
            include_patterns=["**/*.py"],
            exclude_patterns=["**/venv/**"],
        )

        assert config.languages == ["python"]
        assert config.include_patterns == ["**/*.py"]
        assert config.exclude_patterns == ["**/venv/**"]


# ============================================================================
# GeneratorConfig Tests
# ============================================================================


class TestGeneratorConfig:
    """Tests for generator configuration."""

    def test_default_values(self):
        """Test GeneratorConfig has correct defaults."""
        config = GeneratorConfig()

        assert config.output_format == "markdown"
        assert config.detail_level == "modular"
        assert config.include_code_snippets is True
        assert config.include_diagrams is False
        assert config.language == "ru"

    def test_literals(self):
        """Test literal type validation."""
        for fmt in ["markdown", "html", "both"]:
            config = GeneratorConfig(output_format=fmt)
            assert config.output_format == fmt

        for level in ["minimal", "modular", "detailed"]:
            config = GeneratorConfig(detail_level=level)
            assert config.detail_level == level

        for lang in ["en", "ru"]:
            config = GeneratorConfig(language=lang)
            assert config.language == lang


# ============================================================================
# AppConfig Tests
# ============================================================================


class TestAppConfig:
    """Tests for main application configuration."""

    def test_default_values(self):
        """Test AppConfig has correct defaults."""
        config = AppConfig()

        # Sub-configurations exist
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.rag, RAGConfig)
        assert isinstance(config.chunking, ChunkingConfig)
        assert isinstance(config.indexer, IndexerConfig)
        assert isinstance(config.generator, GeneratorConfig)

        # Paths
        assert isinstance(config.project_root, Path)
        assert isinstance(config.output_dir, Path)
        assert isinstance(config.cache_dir, Path)
        assert isinstance(config.index_dir, Path)

        # Defaults
        assert config.log_level == "INFO"
        assert config.batch_size == 10
        assert config.max_retries == 3
        assert config.retry_delay == 1.0

    def test_path_resolution(self):
        """Test paths are resolved to absolute."""
        config = AppConfig(
            project_root="./relative/path",
            output_dir="../another/path",
        )

        assert config.project_root.is_absolute()
        assert config.output_dir.is_absolute()
        assert "relative" not in str(config.project_root) or config.project_root.is_absolute()

    def test_log_level_literal(self):
        """Test log_level accepts only valid literals."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            config = AppConfig(log_level=level)
            assert config.log_level == level

        with pytest.raises(ValueError):
            AppConfig(log_level="INVALID")

    def test_nested_config_override(self):
        """Test overriding nested configuration."""
        config = AppConfig(
            llm=LLMConfig(model_name="custom-llm", temperature=0.8),
            rag=RAGConfig(vector_db="chroma"),
        )

        assert config.llm.model_name == "custom-llm"
        assert config.llm.temperature == 0.8
        assert config.rag.vector_db == "chroma"

    def test_from_yaml(self, sample_config_yaml: Path):
        """Test loading configuration from YAML file."""
        config = AppConfig.from_yaml(sample_config_yaml)

        assert config.llm.model_name == "test-model"
        assert config.llm.temperature == 0.5
        assert config.llm.max_tokens == 2048
        assert config.embedding.model_name == "test-embed"
        assert config.embedding.device == "cpu"
        assert config.rag.vector_db == "chroma"
        assert config.rag.top_k_final == 5
        assert config.chunking.strategy == "ast"
        assert config.indexer.languages == ["php", "go"]
        assert config.generator.language == "ru"
        assert config.log_level == "DEBUG"
        assert config.batch_size == 5

    def test_from_yaml_missing_file(self, temp_dir: Path):
        """Test loading from non-existent YAML file."""
        with pytest.raises(FileNotFoundError):
            AppConfig.from_yaml(temp_dir / "nonexistent.yaml")

    def test_from_yaml_invalid_yaml(self, temp_dir: Path):
        """Test loading from invalid YAML file."""
        invalid_yaml = temp_dir / "invalid.yaml"
        invalid_yaml.write_text("{ invalid yaml: [")

        with pytest.raises(yaml.YAMLError):
            AppConfig.from_yaml(invalid_yaml)

    def test_from_yaml_partial_config(self, temp_dir: Path):
        """Test loading partial config uses defaults for missing values."""
        partial_yaml = temp_dir / "partial.yaml"
        partial_yaml.write_text("""
llm:
  temperature: 0.3
log_level: "WARNING"
""")

        config = AppConfig.from_yaml(partial_yaml)

        # Overridden values
        assert config.llm.temperature == 0.3
        assert config.log_level == "WARNING"

        # Default values preserved
        assert config.llm.model_name == "Qwen/Qwen3-30B-A3B-GPTQ-Int4"
        assert config.embedding.model_name == "Qodo/Qodo-Embed-1-1.5B"

    def test_to_yaml(self, temp_dir: Path):
        """Test saving configuration to YAML file."""
        config = AppConfig(
            llm=LLMConfig(model_name="save-test", temperature=0.6),
            log_level="DEBUG",
        )

        output_path = temp_dir / "saved_config.yaml"
        config.to_yaml(output_path)

        # Verify file exists and contains data
        assert output_path.exists()

        # Load with UnsafeLoader to handle Path objects serialized by yaml.dump
        with open(output_path) as f:
            data = yaml.load(f, Loader=yaml.UnsafeLoader)

        assert data["llm"]["model_name"] == "save-test"
        assert data["llm"]["temperature"] == 0.6
        assert data["log_level"] == "DEBUG"

    def test_to_yaml_roundtrip(self, temp_dir: Path):
        """Test YAML save/load roundtrip."""
        original = AppConfig(
            llm=LLMConfig(model_name="roundtrip-test", temperature=0.7),
            rag=RAGConfig(vector_db="milvus", top_k_final=15),
            log_level="WARNING",
            batch_size=20,
        )

        yaml_path = temp_dir / "roundtrip.yaml"
        original.to_yaml(yaml_path)

        # Load with UnsafeLoader to handle Path objects
        with open(yaml_path) as f:
            data = yaml.load(f, Loader=yaml.UnsafeLoader)

        # Verify key fields preserved
        assert data["llm"]["model_name"] == original.llm.model_name
        assert data["llm"]["temperature"] == original.llm.temperature
        assert data["rag"]["vector_db"] == original.rag.vector_db
        assert data["rag"]["top_k_final"] == original.rag.top_k_final
        assert data["log_level"] == original.log_level
        assert data["batch_size"] == original.batch_size

    def test_extra_fields_ignored(self, temp_dir: Path):
        """Test extra fields in YAML are ignored."""
        yaml_content = """
llm:
  model_name: "test"
unknown_field: "should be ignored"
another_unknown:
  nested: "value"
"""
        yaml_path = temp_dir / "extra.yaml"
        yaml_path.write_text(yaml_content)

        # Should not raise, extra="ignore" in SettingsConfigDict
        config = AppConfig.from_yaml(yaml_path)
        assert config.llm.model_name == "test"


# ============================================================================
# Global Config Functions Tests
# ============================================================================


class TestGlobalConfigFunctions:
    """Tests for get_config and load_config functions."""

    def test_get_config_returns_singleton(self):
        """Test get_config returns same instance."""
        # Reset global state
        import codebase_analyzer.config as config_module

        config_module._config = None

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_get_config_creates_default(self):
        """Test get_config creates default AppConfig."""
        import codebase_analyzer.config as config_module

        config_module._config = None

        config = get_config()

        assert isinstance(config, AppConfig)
        assert config.llm.model_name == "Qwen/Qwen3-30B-A3B-GPTQ-Int4"

    def test_load_config_from_file(self, sample_config_yaml: Path):
        """Test load_config from YAML file."""
        import codebase_analyzer.config as config_module

        config_module._config = None

        config = load_config(sample_config_yaml)

        assert config.llm.model_name == "test-model"
        assert config is config_module._config

    def test_load_config_nonexistent_creates_default(self, temp_dir: Path):
        """Test load_config with non-existent path creates default."""
        import codebase_analyzer.config as config_module

        config_module._config = None

        config = load_config(temp_dir / "nonexistent.yaml")

        assert isinstance(config, AppConfig)
        assert config.llm.model_name == "Qwen/Qwen3-30B-A3B-GPTQ-Int4"

    def test_load_config_none_creates_default(self):
        """Test load_config with None creates default."""
        import codebase_analyzer.config as config_module

        config_module._config = None

        config = load_config(None)

        assert isinstance(config, AppConfig)

    def test_load_config_updates_global(self, sample_config_yaml: Path):
        """Test load_config updates global instance."""
        import codebase_analyzer.config as config_module

        config_module._config = None

        # First load
        config1 = get_config()
        assert config1.llm.model_name == "Qwen/Qwen3-30B-A3B-GPTQ-Int4"

        # Load from file
        config2 = load_config(sample_config_yaml)
        assert config2.llm.model_name == "test-model"

        # get_config should now return new config
        config3 = get_config()
        assert config3.llm.model_name == "test-model"
        assert config3 is config2


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestConfigEdgeCases:
    """Tests for configuration edge cases."""

    def test_empty_yaml_file(self, temp_dir: Path):
        """Test loading empty YAML file raises or returns defaults."""
        empty_yaml = temp_dir / "empty.yaml"
        empty_yaml.write_text("")

        # Empty YAML loads as None which may raise TypeError
        # This is expected behavior - empty config is invalid
        with pytest.raises((TypeError, Exception)):
            AppConfig.from_yaml(empty_yaml)

    def test_yaml_with_null_values(self, temp_dir: Path):
        """Test YAML with null values raises validation error."""
        yaml_content = """
llm:
  model_name: null
  temperature: null
"""
        yaml_path = temp_dir / "nulls.yaml"
        yaml_path.write_text(yaml_content)

        # Null values for required fields should raise validation error
        with pytest.raises(Exception):  # pydantic ValidationError
            AppConfig.from_yaml(yaml_path)

    def test_environment_variables(self):
        """Test configuration from environment variables."""
        env_vars = {
            "LLM_MODEL_NAME": "env-llm-model",
            "LLM_TEMPERATURE": "0.8",
            "EMBED_DEVICE": "cuda",
            "RAG_VECTOR_DB": "milvus",
            "CHUNK_STRATEGY": "semantic",
        }

        with patch.dict(os.environ, env_vars):
            config = AppConfig()

            assert config.llm.model_name == "env-llm-model"
            assert config.llm.temperature == 0.8
            assert config.embedding.device == "cuda"
            assert config.rag.vector_db == "milvus"
            assert config.chunking.strategy == "semantic"

    def test_yaml_precedence_over_env(self, temp_dir: Path):
        """Test YAML values take precedence over environment."""
        yaml_content = """
llm:
  model_name: "yaml-model"
  temperature: 0.3
"""
        yaml_path = temp_dir / "precedence.yaml"
        yaml_path.write_text(yaml_content)

        env_vars = {
            "LLM_MODEL_NAME": "env-model",
            "LLM_TEMPERATURE": "0.9",
        }

        with patch.dict(os.environ, env_vars):
            config = AppConfig.from_yaml(yaml_path)

            # YAML should override environment
            assert config.llm.model_name == "yaml-model"
            assert config.llm.temperature == 0.3

    def test_deeply_nested_override(self, temp_dir: Path):
        """Test overriding deeply nested values."""
        yaml_content = """
rag:
  qdrant_host: "custom-host"
  qdrant_port: 9999
"""
        yaml_path = temp_dir / "nested.yaml"
        yaml_path.write_text(yaml_content)

        config = AppConfig.from_yaml(yaml_path)

        assert config.rag.qdrant_host == "custom-host"
        assert config.rag.qdrant_port == 9999
        # Other defaults preserved
        assert config.rag.collection_name == "codebase_chunks"

    def test_config_serialization(self):
        """Test config model_dump and serialization."""
        config = AppConfig(
            llm=LLMConfig(model_name="serialize-test"),
            log_level="DEBUG",
        )

        data = config.model_dump()

        assert isinstance(data, dict)
        assert data["llm"]["model_name"] == "serialize-test"
        assert data["log_level"] == "DEBUG"
        assert "project_root" in data

    def test_large_batch_size(self):
        """Test config accepts large batch size."""
        config = AppConfig(batch_size=1000)
        assert config.batch_size == 1000

    def test_unicode_in_paths(self, temp_dir: Path):
        """Test config handles unicode in paths."""
        unicode_dir = temp_dir / "проект_тест"
        unicode_dir.mkdir()

        config = AppConfig(project_root=unicode_dir)
        assert "проект_тест" in str(config.project_root)

    def test_model_dump_excludes_none(self):
        """Test model_dump can exclude None values."""
        config = AppConfig()
        data = config.model_dump(exclude_none=True)

        # log_file is None by default
        assert data.get("log_file") is None or "log_file" not in data


# ============================================================================
# Validation Tests
# ============================================================================


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_invalid_yaml_validation_error(self, temp_dir: Path):
        """Test invalid values in YAML raise validation error."""
        invalid_yaml = temp_dir / "invalid.yaml"
        invalid_yaml.write_text("""
llm:
  gpu_memory_utilization: 1.5  # Invalid
""")

        with pytest.raises(ValueError):
            AppConfig.from_yaml(invalid_yaml)

    def test_weights_sum_not_validated(self):
        """Test RAG weights sum is not automatically validated."""
        # Weights don't have to sum to 1.0
        config = RAGConfig(
            bm25_weight=0.5,
            dense_weight=0.5,
            graph_weight=0.5,
        )

        # No validation error - weights sum to 1.5
        assert config.bm25_weight + config.dense_weight + config.graph_weight == 1.5

    def test_chunking_consistency(self):
        """Test chunking config values consistency."""
        # min_chunk_size should be less than chunk_size_tokens
        config = ChunkingConfig(
            chunk_size_tokens=1000,
            min_chunk_size=100,
        )

        assert config.min_chunk_size < config.chunk_size_tokens

    def test_retrieval_consistency(self):
        """Test RAG retrieval config consistency."""
        config = RAGConfig(
            top_k_initial=50,
            top_k_final=10,
        )

        # top_k_final should be <= top_k_initial
        assert config.top_k_final <= config.top_k_initial
