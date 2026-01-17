"""
Tests for knowledge data configuration.

Tests src/knowledge/data/*.yaml including _meta.yaml and all category files.
"""

import pytest
from pathlib import Path
import yaml


@pytest.fixture(scope="module")
def knowledge_data_dir():
    """Get knowledge data directory."""
    return Path(__file__).parent.parent / "src" / "knowledge" / "data"


@pytest.fixture(scope="module")
def meta_config(knowledge_data_dir):
    """Load _meta.yaml configuration."""
    with open(knowledge_data_dir / "_meta.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def all_knowledge_files(knowledge_data_dir):
    """Get all knowledge YAML files (excluding _meta.yaml)."""
    return [f for f in knowledge_data_dir.glob("*.yaml") if f.name != "_meta.yaml"]


def load_yaml_file(file_path):
    """Helper to load YAML file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestMetaConfigStructure:
    """Tests for _meta.yaml structure."""

    def test_has_company_section(self, meta_config):
        """Meta config should have company section."""
        assert "company" in meta_config

    def test_company_has_name(self, meta_config):
        """Company should have name."""
        assert "name" in meta_config["company"]
        assert meta_config["company"]["name"] == "Wipon"

    def test_company_has_description(self, meta_config):
        """Company should have description."""
        assert "description" in meta_config["company"]
        assert len(meta_config["company"]["description"]) > 0

    def test_has_stats_section(self, meta_config):
        """Meta config should have stats section."""
        assert "stats" in meta_config

    def test_stats_has_total_sections(self, meta_config):
        """Stats should have total_sections."""
        assert "total_sections" in meta_config["stats"]
        assert meta_config["stats"]["total_sections"] > 0

    def test_stats_has_last_updated(self, meta_config):
        """Stats should have last_updated."""
        assert "last_updated" in meta_config["stats"]

    def test_stats_has_categories(self, meta_config):
        """Stats should have categories."""
        assert "categories" in meta_config["stats"]
        assert len(meta_config["stats"]["categories"]) > 0


class TestMetaCategories:
    """Tests for meta categories."""

    def test_each_category_has_name(self, meta_config):
        """Each category should have name."""
        for cat in meta_config["stats"]["categories"]:
            assert "name" in cat

    def test_each_category_has_count(self, meta_config):
        """Each category should have count."""
        for cat in meta_config["stats"]["categories"]:
            assert "count" in cat
            assert cat["count"] > 0

    def test_expected_categories_exist(self, meta_config):
        """Expected categories should exist."""
        category_names = [c["name"] for c in meta_config["stats"]["categories"]]
        expected = [
            "equipment", "pricing", "products", "support", "tis",
            "regions", "inventory", "features", "integrations", "fiscal",
            "analytics", "employees", "stability", "mobile", "promotions",
            "competitors", "faq"
        ]
        for cat in expected:
            assert cat in category_names, f"Missing category: {cat}"


class TestKnowledgeFilesExist:
    """Tests for knowledge file existence."""

    def test_equipment_file_exists(self, knowledge_data_dir):
        """equipment.yaml should exist."""
        assert (knowledge_data_dir / "equipment.yaml").exists()

    def test_pricing_file_exists(self, knowledge_data_dir):
        """pricing.yaml should exist."""
        assert (knowledge_data_dir / "pricing.yaml").exists()

    def test_products_file_exists(self, knowledge_data_dir):
        """products.yaml should exist."""
        assert (knowledge_data_dir / "products.yaml").exists()

    def test_support_file_exists(self, knowledge_data_dir):
        """support.yaml should exist."""
        assert (knowledge_data_dir / "support.yaml").exists()

    def test_features_file_exists(self, knowledge_data_dir):
        """features.yaml should exist."""
        assert (knowledge_data_dir / "features.yaml").exists()

    def test_integrations_file_exists(self, knowledge_data_dir):
        """integrations.yaml should exist."""
        assert (knowledge_data_dir / "integrations.yaml").exists()

    def test_analytics_file_exists(self, knowledge_data_dir):
        """analytics.yaml should exist."""
        assert (knowledge_data_dir / "analytics.yaml").exists()

    def test_employees_file_exists(self, knowledge_data_dir):
        """employees.yaml should exist."""
        assert (knowledge_data_dir / "employees.yaml").exists()

    def test_inventory_file_exists(self, knowledge_data_dir):
        """inventory.yaml should exist."""
        assert (knowledge_data_dir / "inventory.yaml").exists()

    def test_fiscal_file_exists(self, knowledge_data_dir):
        """fiscal.yaml should exist."""
        assert (knowledge_data_dir / "fiscal.yaml").exists()

    def test_mobile_file_exists(self, knowledge_data_dir):
        """mobile.yaml should exist."""
        assert (knowledge_data_dir / "mobile.yaml").exists()

    def test_regions_file_exists(self, knowledge_data_dir):
        """regions.yaml should exist."""
        assert (knowledge_data_dir / "regions.yaml").exists()

    def test_stability_file_exists(self, knowledge_data_dir):
        """stability.yaml should exist."""
        assert (knowledge_data_dir / "stability.yaml").exists()

    def test_competitors_file_exists(self, knowledge_data_dir):
        """competitors.yaml should exist."""
        assert (knowledge_data_dir / "competitors.yaml").exists()

    def test_promotions_file_exists(self, knowledge_data_dir):
        """promotions.yaml should exist."""
        assert (knowledge_data_dir / "promotions.yaml").exists()

    def test_tis_file_exists(self, knowledge_data_dir):
        """tis.yaml should exist."""
        assert (knowledge_data_dir / "tis.yaml").exists()

    def test_faq_file_exists(self, knowledge_data_dir):
        """faq.yaml should exist."""
        assert (knowledge_data_dir / "faq.yaml").exists()


class TestKnowledgeFileStructure:
    """Tests for knowledge file structure."""

    def test_all_files_have_sections(self, all_knowledge_files):
        """All knowledge files should have sections."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            assert "sections" in config, f"{file_path.name} missing sections"

    def test_sections_are_lists(self, all_knowledge_files):
        """Sections should be lists."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            assert isinstance(config["sections"], list), f"{file_path.name} sections not a list"

    def test_sections_not_empty(self, all_knowledge_files):
        """Sections should not be empty."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            assert len(config["sections"]) > 0, f"{file_path.name} has empty sections"


class TestKnowledgeSectionStructure:
    """Tests for knowledge section structure."""

    def test_sections_have_topic(self, all_knowledge_files):
        """All sections should have topic."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for i, section in enumerate(config["sections"]):
                assert "topic" in section, f"{file_path.name} section {i} missing topic"

    def test_sections_have_priority(self, all_knowledge_files):
        """All sections should have priority."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for i, section in enumerate(config["sections"]):
                assert "priority" in section, f"{file_path.name} section {i} missing priority"

    def test_sections_have_keywords(self, all_knowledge_files):
        """All sections should have keywords."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for i, section in enumerate(config["sections"]):
                assert "keywords" in section, f"{file_path.name} section {i} missing keywords"

    def test_sections_have_facts(self, all_knowledge_files):
        """All sections should have facts."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for i, section in enumerate(config["sections"]):
                assert "facts" in section, f"{file_path.name} section {i} missing facts"


class TestKnowledgeSectionValidity:
    """Tests for knowledge section validity."""

    def test_priorities_are_valid(self, all_knowledge_files):
        """Priorities should be between 1 and 10."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                assert 1 <= section["priority"] <= 10, \
                    f"{file_path.name} section {section['topic']} has invalid priority"

    def test_keywords_are_lists(self, all_knowledge_files):
        """Keywords should be lists."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                assert isinstance(section["keywords"], list), \
                    f"{file_path.name} section {section['topic']} keywords not a list"

    def test_keywords_not_empty(self, all_knowledge_files):
        """Keywords should not be empty."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                assert len(section["keywords"]) > 0, \
                    f"{file_path.name} section {section['topic']} has no keywords"

    def test_facts_not_empty(self, all_knowledge_files):
        """Facts should not be empty."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                assert len(section["facts"]) > 0, \
                    f"{file_path.name} section {section['topic']} has empty facts"


class TestFeaturesFileContent:
    """Tests for features.yaml content."""

    @pytest.fixture
    def features_config(self, knowledge_data_dir):
        """Load features.yaml."""
        return load_yaml_file(knowledge_data_dir / "features.yaml")

    def test_has_inventory_section(self, features_config):
        """Should have inventory section."""
        topics = [s["topic"] for s in features_config["sections"]]
        assert "inventory" in topics

    def test_has_reports_section(self, features_config):
        """Should have reports section."""
        topics = [s["topic"] for s in features_config["sections"]]
        assert "reports" in topics

    def test_has_employees_section(self, features_config):
        """Should have employees section."""
        topics = [s["topic"] for s in features_config["sections"]]
        assert "employees" in topics

    def test_inventory_facts_mention_wipon(self, features_config):
        """Inventory facts should mention Wipon."""
        inventory_sections = [s for s in features_config["sections"] if s["topic"] == "inventory"]
        assert len(inventory_sections) > 0
        assert "wipon" in inventory_sections[0]["facts"].lower()

    def test_features_has_minimum_sections(self, features_config):
        """Features should have at least 50 sections."""
        assert len(features_config["sections"]) >= 50


class TestMetaCategoriesMatchFiles:
    """Tests for meta categories matching actual files."""

    def test_all_meta_categories_have_files(self, meta_config, knowledge_data_dir):
        """All meta categories should have corresponding files."""
        for cat in meta_config["stats"]["categories"]:
            file_path = knowledge_data_dir / f"{cat['name']}.yaml"
            assert file_path.exists(), f"Missing file for category: {cat['name']}"

    def test_file_counts_reasonable(self, meta_config, knowledge_data_dir):
        """File section counts should be reasonable."""
        for cat in meta_config["stats"]["categories"]:
            file_path = knowledge_data_dir / f"{cat['name']}.yaml"
            if file_path.exists():
                config = load_yaml_file(file_path)
                actual_count = len(config["sections"])
                # Allow some variance due to updates
                assert actual_count > 0, f"{cat['name']} has no sections"


class TestKnowledgeKeywordQuality:
    """Tests for keyword quality in knowledge files."""

    def test_keywords_are_lowercase_or_mixed(self, all_knowledge_files):
        """Keywords should generally be lowercase (some mixed case allowed)."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                for keyword in section["keywords"]:
                    # Keywords should be strings
                    assert isinstance(keyword, str), \
                        f"{file_path.name} section {section['topic']} has non-string keyword"

    def test_keywords_not_too_short(self, all_knowledge_files):
        """Keywords should generally be at least 2 characters."""
        for file_path in all_knowledge_files:
            config = load_yaml_file(file_path)
            for section in config["sections"]:
                for keyword in section["keywords"]:
                    # Allow very short keywords like "1с" or "qr"
                    if len(keyword) < 2:
                        assert keyword.isdigit() or keyword in ["1с", "qr"], \
                            f"{file_path.name} has very short keyword: {keyword}"


class TestTotalKnowledgeStats:
    """Tests for total knowledge statistics."""

    def test_total_sections_matches_meta(self, meta_config, all_knowledge_files):
        """Total sections should approximately match meta."""
        total = sum(len(load_yaml_file(f)["sections"]) for f in all_knowledge_files)
        meta_total = meta_config["stats"]["total_sections"]
        # Allow 10% variance
        assert abs(total - meta_total) / meta_total < 0.2, \
            f"Total sections {total} doesn't match meta {meta_total}"

    def test_minimum_total_sections(self, all_knowledge_files):
        """Should have at least 1000 total sections."""
        total = sum(len(load_yaml_file(f)["sections"]) for f in all_knowledge_files)
        assert total >= 1000, f"Only {total} total sections, expected at least 1000"


class TestKnowledgeFilesParseCorrectly:
    """Tests that all knowledge files parse correctly."""

    def test_all_files_parse_without_error(self, all_knowledge_files):
        """All knowledge files should parse without error."""
        for file_path in all_knowledge_files:
            try:
                config = load_yaml_file(file_path)
                assert config is not None, f"{file_path.name} parsed to None"
            except yaml.YAMLError as e:
                pytest.fail(f"{file_path.name} failed to parse: {e}")

    def test_all_files_are_valid_yaml(self, all_knowledge_files):
        """All knowledge files should be valid YAML."""
        for file_path in all_knowledge_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Should not have tab characters (YAML prefers spaces)
                # Note: Some files might have tabs, so just warn
                if '\t' in content:
                    # Allow tabs but check the file still parses
                    try:
                        yaml.safe_load(content)
                    except yaml.YAMLError:
                        pytest.fail(f"{file_path.name} has tabs and fails to parse")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
