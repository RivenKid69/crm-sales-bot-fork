"""Tests for markdown documentation generator."""

from pathlib import Path

import pytest

from codebase_analyzer.analyzer.models import (
    AnalysisResult,
    ArchitectureSummary,
    EntitySummary,
    ModuleSummary,
)
from codebase_analyzer.generator import (
    GeneratorConfig,
    MarkdownGenerator,
    generate_documentation,
    slugify,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_entity_summaries():
    """Create sample entity summaries."""
    return {
        "auth::UserService::login": EntitySummary(
            entity_id="auth::UserService::login",
            summary="Handles user authentication by validating credentials.",
            purpose="Authenticate users",
            domain="auth",
            key_behaviors=["validate credentials", "create session"],
            dependencies_used=["DatabaseService", "TokenGenerator"],
        ),
        "auth::UserService::logout": EntitySummary(
            entity_id="auth::UserService::logout",
            summary="Terminates user session and clears tokens.",
            purpose="End user session",
            domain="auth",
            key_behaviors=["invalidate session", "clear tokens"],
            dependencies_used=["SessionStore"],
        ),
        "api::UserController::handleLogin": EntitySummary(
            entity_id="api::UserController::handleLogin",
            summary="HTTP endpoint handler for login requests.",
            purpose="Process login API requests",
            domain="api",
            key_behaviors=["parse request", "call service", "return response"],
            dependencies_used=["UserService"],
        ),
        "db::DatabaseService::query": EntitySummary(
            entity_id="db::DatabaseService::query",
            summary="Executes database queries with connection pooling.",
            purpose="Execute SQL queries",
            domain="database",
            key_behaviors=["pool connections", "execute query"],
            dependencies_used=[],
        ),
    }

@pytest.fixture
def sample_module_summaries():
    """Create sample module summaries."""
    return {
        "src/auth": ModuleSummary(
            path="src/auth",
            name="auth",
            summary="Authentication and authorization module handling user identity.",
            entities=["auth::UserService::login", "auth::UserService::logout"],
            domains=["auth"],
            responsibilities=["User authentication", "Session management"],
            dependencies=["db"],
            exports=["UserService", "AuthMiddleware"],
            entity_count=2,
            total_lines=500,
        ),
        "src/api": ModuleSummary(
            path="src/api",
            name="api",
            summary="REST API layer providing HTTP endpoints.",
            entities=["api::UserController::handleLogin"],
            domains=["api"],
            responsibilities=["HTTP routing", "Request handling"],
            dependencies=["auth"],
            exports=["UserController"],
            entity_count=1,
            total_lines=300,
        ),
        "src/db": ModuleSummary(
            path="src/db",
            name="db",
            summary="Database access layer with connection pooling.",
            entities=["db::DatabaseService::query"],
            domains=["database"],
            responsibilities=["Database connections", "Query execution"],
            dependencies=[],
            exports=["DatabaseService"],
            entity_count=1,
            total_lines=200,
        ),
    }

@pytest.fixture
def sample_architecture():
    """Create sample architecture summary."""
    return ArchitectureSummary(
        overview="A microservices-based authentication system with REST API.",
        modules=["src/auth", "src/api", "src/db"],
        patterns_detected=["MVC", "Repository Pattern", "Dependency Injection"],
        tech_stack=["Go", "PostgreSQL", "Redis"],
        data_flow="API -> Auth -> Database",
        key_components=["UserService", "DatabaseService", "AuthMiddleware"],
        diagram_mermaid="""graph TD
    A[API] --> B[Auth]
    B --> C[Database]""",
    )

@pytest.fixture
def sample_analysis_result(sample_entity_summaries, sample_module_summaries, sample_architecture):
    """Create a complete analysis result."""
    return AnalysisResult(
        entity_summaries=sample_entity_summaries,
        module_summaries=sample_module_summaries,
        architecture=sample_architecture,
        total_entities=4,
        total_modules=3,
        total_tokens_in=1000,
        total_tokens_out=500,
        processing_time_seconds=10.5,
        model_used="ministral-3:14b-instruct-2512-q8_0",
        analysis_timestamp="2024-01-20T10:00:00",
        processing_levels=[
            ["db::DatabaseService::query"],
            ["auth::UserService::login", "auth::UserService::logout"],
            ["api::UserController::handleLogin"],
        ],
    )

@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "docs"
    output_dir.mkdir()
    return output_dir

@pytest.fixture
def generator():
    """Create a markdown generator instance."""
    return MarkdownGenerator()

@pytest.fixture
def generator_with_config():
    """Create a generator with custom config."""
    config = GeneratorConfig(
        title="Test Project",
        create_module_docs=True,
        create_api_docs=True,
        create_structure=True,
    )
    return MarkdownGenerator(config=config)

# =============================================================================
# Slugify Tests
# =============================================================================

class TestSlugify:
    """Tests for the slugify function."""

    def test_basic_slugify(self):
        """Test basic text slugification."""
        assert slugify("Hello World") == "hello-world"

    def test_slugify_special_chars(self):
        """Test slugify removes special characters."""
        assert slugify("Hello! World?") == "hello-world"

    def test_slugify_multiple_spaces(self):
        """Test slugify collapses multiple spaces."""
        assert slugify("hello   world") == "hello-world"

    def test_slugify_underscores(self):
        """Test slugify converts underscores to hyphens."""
        assert slugify("hello_world") == "hello-world"

    def test_slugify_empty(self):
        """Test slugify handles empty string."""
        assert slugify("") == "unnamed"

    def test_slugify_only_special(self):
        """Test slugify handles only special chars."""
        assert slugify("!!!") == "unnamed"

    def test_slugify_unicode(self):
        """Test slugify with unicode characters."""
        result = slugify("hello-мир")
        assert result  # Should produce something

# =============================================================================
# GeneratorConfig Tests
# =============================================================================

class TestGeneratorConfig:
    """Tests for GeneratorConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GeneratorConfig()
        assert config.create_module_docs is True
        assert config.create_api_docs is True
        assert config.create_structure is True
        assert config.title == "Project Documentation"

    def test_custom_config(self):
        """Test custom configuration."""
        config = GeneratorConfig(
            title="My Project",
            create_api_docs=False,
            max_entities_per_module=10,
        )
        assert config.title == "My Project"
        assert config.create_api_docs is False
        assert config.max_entities_per_module == 10

# =============================================================================
# MarkdownGenerator Initialization Tests
# =============================================================================

class TestMarkdownGeneratorInit:
    """Tests for MarkdownGenerator initialization."""

    def test_create_generator_default(self):
        """Test creating generator with defaults."""
        gen = MarkdownGenerator()
        assert gen.config is not None
        assert gen.template_env is not None

    def test_create_generator_with_config(self):
        """Test creating generator with custom config."""
        config = GeneratorConfig(title="Custom Title")
        gen = MarkdownGenerator(config=config)
        assert gen.config.title == "Custom Title"

    def test_create_generator_with_custom_templates(self):
        """Test creating generator with custom templates."""
        custom_templates = {
            "readme.md.jinja": "# Custom {{ title }}",
        }
        gen = MarkdownGenerator(custom_templates=custom_templates)

        # Verify custom template is used
        template = gen.template_env.get_template("readme.md.jinja")
        rendered = template.render(title="Test")
        assert "Custom Test" in rendered

# =============================================================================
# README Generation Tests
# =============================================================================

class TestReadmeGeneration:
    """Tests for README.md generation."""

    def test_generate_readme(self, generator, sample_analysis_result, temp_output_dir):
        """Test README generation."""
        readme_path = generator._generate_readme(sample_analysis_result, temp_output_dir)

        assert readme_path.exists()
        content = readme_path.read_text()

        assert "Project Documentation" in content
        assert "microservices-based authentication" in content

    def test_readme_contains_architecture(self, generator, sample_analysis_result, temp_output_dir):
        """Test README includes architecture details."""
        generator._generate_readme(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "README.md").read_text()

        assert "Architecture Patterns" in content
        assert "MVC" in content
        assert "Repository Pattern" in content

    def test_readme_contains_modules(self, generator, sample_analysis_result, temp_output_dir):
        """Test README lists modules."""
        generator._generate_readme(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "README.md").read_text()

        assert "Modules" in content
        assert "auth" in content.lower()
        assert "api" in content.lower()

    def test_readme_contains_tech_stack(self, generator, sample_analysis_result, temp_output_dir):
        """Test README includes tech stack."""
        generator._generate_readme(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "README.md").read_text()

        assert "Tech Stack" in content
        assert "Go" in content
        assert "PostgreSQL" in content

    def test_readme_contains_mermaid_diagram(self, generator, sample_analysis_result, temp_output_dir):
        """Test README includes mermaid diagram."""
        generator._generate_readme(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "README.md").read_text()

        assert "```mermaid" in content
        assert "graph TD" in content

    def test_readme_no_architecture(self, generator, temp_output_dir):
        """Test README generation without architecture."""
        result = AnalysisResult(
            entity_summaries={},
            module_summaries={},
            architecture=None,
        )
        generator._generate_readme(result, temp_output_dir)
        content = (temp_output_dir / "README.md").read_text()

        assert "No architecture overview available" in content

# =============================================================================
# Module Documentation Tests
# =============================================================================

class TestModuleDocGeneration:
    """Tests for module documentation generation."""

    def test_generate_module_doc(self, generator, sample_module_summaries, sample_entity_summaries, temp_output_dir):
        """Test module documentation generation."""
        module = sample_module_summaries["src/auth"]
        module_path = generator._generate_module_doc(
            module, sample_entity_summaries, temp_output_dir
        )

        assert module_path.exists()
        assert module_path.name == "auth.md"

    def test_module_doc_content(self, generator, sample_module_summaries, sample_entity_summaries, temp_output_dir):
        """Test module doc contains expected content."""
        module = sample_module_summaries["src/auth"]
        generator._generate_module_doc(module, sample_entity_summaries, temp_output_dir)

        content = (temp_output_dir / "auth.md").read_text()

        assert "# auth" in content
        assert "Authentication and authorization" in content
        assert "Responsibilities" in content
        assert "User authentication" in content

    def test_module_doc_contains_entities(self, generator, sample_module_summaries, sample_entity_summaries, temp_output_dir):
        """Test module doc includes entity summaries."""
        module = sample_module_summaries["src/auth"]
        generator._generate_module_doc(module, sample_entity_summaries, temp_output_dir)

        content = (temp_output_dir / "auth.md").read_text()

        assert "Components" in content
        assert "login" in content
        assert "Authenticate users" in content

    def test_module_doc_dependencies(self, generator, sample_module_summaries, sample_entity_summaries, temp_output_dir):
        """Test module doc shows dependencies."""
        module = sample_module_summaries["src/auth"]
        generator._generate_module_doc(module, sample_entity_summaries, temp_output_dir)

        content = (temp_output_dir / "auth.md").read_text()

        assert "Dependencies" in content
        assert "db" in content

# =============================================================================
# API Documentation Tests
# =============================================================================

class TestApiDocGeneration:
    """Tests for API documentation generation."""

    def test_generate_api_docs(self, generator, sample_analysis_result, temp_output_dir):
        """Test API documentation generation."""
        api_path = generator._generate_api_docs(sample_analysis_result, temp_output_dir)

        assert api_path.exists()
        assert api_path.name == "API.md"

    def test_api_docs_detects_api_entities(self, generator, sample_analysis_result, temp_output_dir):
        """Test API docs includes detected API entities."""
        generator._generate_api_docs(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "API.md").read_text()

        # Should detect api-related entities
        assert "API Documentation" in content
        # api::UserController::handleLogin should be detected
        assert "handleLogin" in content

    def test_api_docs_no_api_entities(self, generator, temp_output_dir):
        """Test API docs with no API entities."""
        result = AnalysisResult(
            entity_summaries={
                "util::helper": EntitySummary(
                    entity_id="util::helper",
                    summary="A utility function",
                    purpose="Help",
                    domain="util",
                ),
            },
            module_summaries={},
        )
        generator._generate_api_docs(result, temp_output_dir)
        content = (temp_output_dir / "API.md").read_text()

        assert "No API endpoints" in content

# =============================================================================
# Structure Documentation Tests
# =============================================================================

class TestStructureDocGeneration:
    """Tests for structure documentation generation."""

    def test_generate_structure(self, generator, sample_analysis_result, temp_output_dir):
        """Test structure documentation generation."""
        structure_path = generator._generate_structure(sample_analysis_result, temp_output_dir)

        assert structure_path.exists()
        assert structure_path.name == "STRUCTURE.md"

    def test_structure_contains_stats(self, generator, sample_analysis_result, temp_output_dir):
        """Test structure doc contains statistics."""
        generator._generate_structure(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "STRUCTURE.md").read_text()

        assert "Total Entities" in content
        assert "Total Modules" in content
        assert "ministral-3:14b-instruct-2512-q8_0" in content

    def test_structure_contains_modules_by_size(self, generator, sample_analysis_result, temp_output_dir):
        """Test structure doc lists modules by size."""
        generator._generate_structure(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "STRUCTURE.md").read_text()

        assert "Modules by Size" in content
        assert "auth" in content

    def test_structure_contains_domains(self, generator, sample_analysis_result, temp_output_dir):
        """Test structure doc lists business domains."""
        generator._generate_structure(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "STRUCTURE.md").read_text()

        assert "Business Domains" in content
        assert "auth" in content
        assert "database" in content

    def test_structure_contains_levels(self, generator, sample_analysis_result, temp_output_dir):
        """Test structure doc shows dependency levels."""
        generator._generate_structure(sample_analysis_result, temp_output_dir)
        content = (temp_output_dir / "STRUCTURE.md").read_text()

        assert "Dependency Levels" in content
        assert "Level 0" in content

# =============================================================================
# Full Generation Tests
# =============================================================================

class TestFullGeneration:
    """Tests for full documentation generation."""

    def test_generate_all(self, generator, sample_analysis_result, temp_output_dir):
        """Test generating all documentation."""
        files = generator.generate(sample_analysis_result, temp_output_dir)

        # Should generate README, modules, API, and structure
        assert len(files) > 0
        assert (temp_output_dir / "README.md").exists()
        assert (temp_output_dir / "API.md").exists()
        assert (temp_output_dir / "STRUCTURE.md").exists()

    def test_generate_creates_module_dir(self, generator, sample_analysis_result, temp_output_dir):
        """Test that modules directory is created."""
        generator.generate(sample_analysis_result, temp_output_dir)

        modules_dir = temp_output_dir / "modules"
        assert modules_dir.exists()
        assert (modules_dir / "auth.md").exists()

    def test_generate_with_disabled_options(self, temp_output_dir, sample_analysis_result):
        """Test generation with disabled options."""
        config = GeneratorConfig(
            create_module_docs=False,
            create_api_docs=False,
            create_structure=False,
        )
        gen = MarkdownGenerator(config=config)

        files = gen.generate(sample_analysis_result, temp_output_dir)

        # Should only generate README
        assert len(files) == 1
        assert files[0].name == "README.md"

    def test_generate_convenience_function(self, sample_analysis_result, temp_output_dir):
        """Test the convenience function."""
        files = generate_documentation(sample_analysis_result, temp_output_dir)

        assert len(files) > 0
        assert (temp_output_dir / "README.md").exists()

# =============================================================================
# Content Generation Tests (Without Writing Files)
# =============================================================================

class TestContentGeneration:
    """Tests for generating content without file writes."""

    def test_generate_readme_content(self, generator, sample_analysis_result):
        """Test generating README content only."""
        content = generator.generate_readme_content(sample_analysis_result)

        assert "Project Documentation" in content
        assert "microservices-based" in content

    def test_generate_single_module(self, generator, sample_module_summaries, sample_entity_summaries):
        """Test generating single module content."""
        module = sample_module_summaries["src/auth"]
        content = generator.generate_single_module(module, sample_entity_summaries)

        assert "# auth" in content
        assert "Authentication" in content

# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_result(self, generator, temp_output_dir):
        """Test generating docs from empty result."""
        result = AnalysisResult()

        files = generator.generate(result, temp_output_dir)

        assert len(files) >= 1  # At least README
        assert (temp_output_dir / "README.md").exists()

    def test_special_chars_in_module_name(self, generator, sample_entity_summaries, temp_output_dir):
        """Test handling special characters in module names."""
        module = ModuleSummary(
            path="src/my-special_module!@#",
            name="my-special_module!@#",
            summary="A module with special chars",
            entities=[],
            entity_count=0,
            total_lines=0,
        )

        module_path = generator._generate_module_doc(
            module, sample_entity_summaries, temp_output_dir
        )

        assert module_path.exists()
        # Filename should be slugified
        assert "my-special-module" in module_path.name

    def test_unicode_content(self, generator, temp_output_dir):
        """Test handling unicode content."""
        result = AnalysisResult(
            entity_summaries={
                "test::unicode": EntitySummary(
                    entity_id="test::unicode",
                    summary="Обработка данных 数据处理",
                    purpose="Процессинг",
                    domain="интернационализация",
                ),
            },
            module_summaries={
                "src/i18n": ModuleSummary(
                    path="src/i18n",
                    name="i18n",
                    summary="Модуль интернационализации",
                    entities=["test::unicode"],
                    entity_count=1,
                    total_lines=100,
                ),
            },
        )

        files = generator.generate(result, temp_output_dir)

        # Should handle unicode without errors
        readme_content = (temp_output_dir / "README.md").read_text()
        assert "интернационализации" in readme_content or len(readme_content) > 0

    def test_large_entity_list(self, generator, temp_output_dir):
        """Test handling large number of entities."""
        # Create many entities
        entity_summaries = {}
        entity_ids = []
        for i in range(100):
            eid = f"test::entity_{i}"
            entity_ids.append(eid)
            entity_summaries[eid] = EntitySummary(
                entity_id=eid,
                summary=f"Entity {i} summary",
                purpose=f"Purpose {i}",
                domain="test",
            )

        module = ModuleSummary(
            path="src/large",
            name="large",
            summary="Large module",
            entities=entity_ids,
            entity_count=100,
            total_lines=10000,
        )

        # Should limit entities per config
        gen = MarkdownGenerator(config=GeneratorConfig(max_entities_per_module=10))
        content = gen.generate_single_module(module, entity_summaries)

        # Should not include all 100 entities
        entity_count = content.count("### entity_")
        assert entity_count <= 10

    def test_output_dir_creation(self, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        new_dir = tmp_path / "new" / "nested" / "dir"
        assert not new_dir.exists()

        result = AnalysisResult()
        gen = MarkdownGenerator()
        gen.generate(result, new_dir)

        assert new_dir.exists()
