"""
Comprehensive tests for knowledge_extractor configuration.

Tests 100% coverage of:
- LLMConfig
- ChunkingConfig
- ExtractionConfig
- DeduplicationConfig
- OutputConfig
- Config (main)
- CATEGORIES
- CATEGORY_KEYWORDS
- COMMON_TYPOS
- KEYBOARD_NEIGHBORS_RU
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge_extractor"))

from knowledge_extractor.config import (
    LLMConfig,
    ChunkingConfig,
    ExtractionConfig,
    DeduplicationConfig,
    OutputConfig,
    Config,
    CATEGORIES,
    CATEGORY_FILES,
    CATEGORY_KEYWORDS,
    COMMON_TYPOS,
    KEYBOARD_NEIGHBORS_RU,
)


# =============================================================================
# LLM CONFIG TESTS
# =============================================================================

class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_base_url(self):
        """Test default base_url."""
        config = LLMConfig()
        assert config.base_url == "http://localhost:8000/v1"

    def test_default_model(self):
        """Test default model."""
        config = LLMConfig()
        assert config.model == "Qwen/Qwen3-14B"

    def test_default_timeout(self):
        """Test default timeout."""
        config = LLMConfig()
        assert config.timeout == 120

    def test_default_max_retries(self):
        """Test default max_retries."""
        config = LLMConfig()
        assert config.max_retries == 3

    def test_default_temperature(self):
        """Test default temperature."""
        config = LLMConfig()
        assert config.temperature == 0.3

    def test_default_max_tokens(self):
        """Test default max_tokens."""
        config = LLMConfig()
        assert config.max_tokens == 1024

    def test_custom_base_url(self):
        """Test custom base_url."""
        config = LLMConfig(base_url="http://custom:9000/v1")
        assert config.base_url == "http://custom:9000/v1"

    def test_custom_model(self):
        """Test custom model."""
        config = LLMConfig(model="CustomModel/test")
        assert config.model == "CustomModel/test"

    def test_custom_timeout(self):
        """Test custom timeout."""
        config = LLMConfig(timeout=60)
        assert config.timeout == 60

    def test_custom_max_retries(self):
        """Test custom max_retries."""
        config = LLMConfig(max_retries=5)
        assert config.max_retries == 5

    def test_custom_temperature(self):
        """Test custom temperature."""
        config = LLMConfig(temperature=0.7)
        assert config.temperature == 0.7

    def test_custom_max_tokens(self):
        """Test custom max_tokens."""
        config = LLMConfig(max_tokens=2048)
        assert config.max_tokens == 2048


# =============================================================================
# CHUNKING CONFIG TESTS
# =============================================================================

class TestChunkingConfig:
    """Tests for ChunkingConfig dataclass."""

    def test_default_min_chunk_size(self):
        """Test default min_chunk_size."""
        config = ChunkingConfig()
        assert config.min_chunk_size == 200

    def test_default_max_chunk_size(self):
        """Test default max_chunk_size."""
        config = ChunkingConfig()
        assert config.max_chunk_size == 1500

    def test_default_overlap_sentences(self):
        """Test default overlap_sentences."""
        config = ChunkingConfig()
        assert config.overlap_sentences == 2

    def test_default_table_rows_per_chunk(self):
        """Test default table_rows_per_chunk."""
        config = ChunkingConfig()
        assert config.table_rows_per_chunk == 20

    def test_default_message_gap_minutes(self):
        """Test default message_gap_minutes."""
        config = ChunkingConfig()
        assert config.message_gap_minutes == 60

    def test_custom_min_chunk_size(self):
        """Test custom min_chunk_size."""
        config = ChunkingConfig(min_chunk_size=100)
        assert config.min_chunk_size == 100

    def test_custom_max_chunk_size(self):
        """Test custom max_chunk_size."""
        config = ChunkingConfig(max_chunk_size=2000)
        assert config.max_chunk_size == 2000

    def test_custom_overlap_sentences(self):
        """Test custom overlap_sentences."""
        config = ChunkingConfig(overlap_sentences=3)
        assert config.overlap_sentences == 3

    def test_custom_table_rows_per_chunk(self):
        """Test custom table_rows_per_chunk."""
        config = ChunkingConfig(table_rows_per_chunk=30)
        assert config.table_rows_per_chunk == 30

    def test_custom_message_gap_minutes(self):
        """Test custom message_gap_minutes."""
        config = ChunkingConfig(message_gap_minutes=120)
        assert config.message_gap_minutes == 120


# =============================================================================
# EXTRACTION CONFIG TESTS
# =============================================================================

class TestExtractionConfig:
    """Tests for ExtractionConfig dataclass."""

    def test_default_min_keywords(self):
        """Test default min_keywords."""
        config = ExtractionConfig()
        assert config.min_keywords == 20

    def test_default_max_keywords(self):
        """Test default max_keywords."""
        config = ExtractionConfig()
        assert config.max_keywords == 50

    def test_default_min_facts_length(self):
        """Test default min_facts_length."""
        config = ExtractionConfig()
        assert config.min_facts_length == 50

    def test_default_priority(self):
        """Test default default_priority."""
        config = ExtractionConfig()
        assert config.default_priority == 8

    def test_custom_min_keywords(self):
        """Test custom min_keywords."""
        config = ExtractionConfig(min_keywords=10)
        assert config.min_keywords == 10

    def test_custom_max_keywords(self):
        """Test custom max_keywords."""
        config = ExtractionConfig(max_keywords=100)
        assert config.max_keywords == 100

    def test_custom_min_facts_length(self):
        """Test custom min_facts_length."""
        config = ExtractionConfig(min_facts_length=100)
        assert config.min_facts_length == 100

    def test_custom_default_priority(self):
        """Test custom default_priority."""
        config = ExtractionConfig(default_priority=5)
        assert config.default_priority == 5


# =============================================================================
# DEDUPLICATION CONFIG TESTS
# =============================================================================

class TestDeduplicationConfig:
    """Tests for DeduplicationConfig dataclass."""

    def test_default_similarity_threshold(self):
        """Test default similarity_threshold."""
        config = DeduplicationConfig()
        assert config.similarity_threshold == 0.85

    def test_default_embedder_model(self):
        """Test default embedder_model."""
        config = DeduplicationConfig()
        assert config.embedder_model == "ai-forever/ru-en-RoSBERTa"

    def test_custom_similarity_threshold(self):
        """Test custom similarity_threshold."""
        config = DeduplicationConfig(similarity_threshold=0.9)
        assert config.similarity_threshold == 0.9

    def test_custom_embedder_model(self):
        """Test custom embedder_model."""
        config = DeduplicationConfig(embedder_model="custom/model")
        assert config.embedder_model == "custom/model"


# =============================================================================
# OUTPUT CONFIG TESTS
# =============================================================================

class TestOutputConfig:
    """Tests for OutputConfig dataclass."""

    def test_default_company_name_none(self):
        """Test default company_name is None."""
        config = OutputConfig()
        assert config.company_name is None

    def test_default_company_description_none(self):
        """Test default company_description is None."""
        config = OutputConfig()
        assert config.company_description is None

    def test_custom_company_name(self):
        """Test custom company_name."""
        config = OutputConfig(company_name="Poster")
        assert config.company_name == "Poster"

    def test_custom_company_description(self):
        """Test custom company_description."""
        config = OutputConfig(company_description="CRM система")
        assert config.company_description == "CRM система"


# =============================================================================
# MAIN CONFIG TESTS
# =============================================================================

class TestMainConfig:
    """Tests for main Config dataclass."""

    def test_default_llm_config(self):
        """Test default llm config is created."""
        config = Config()
        assert isinstance(config.llm, LLMConfig)

    def test_default_chunking_config(self):
        """Test default chunking config is created."""
        config = Config()
        assert isinstance(config.chunking, ChunkingConfig)

    def test_default_extraction_config(self):
        """Test default extraction config is created."""
        config = Config()
        assert isinstance(config.extraction, ExtractionConfig)

    def test_default_deduplication_config(self):
        """Test default deduplication config is created."""
        config = Config()
        assert isinstance(config.deduplication, DeduplicationConfig)

    def test_default_output_config(self):
        """Test default output config is created."""
        config = Config()
        assert isinstance(config.output, OutputConfig)

    def test_default_input_path_none(self):
        """Test default input_path is None."""
        config = Config()
        assert config.input_path is None

    def test_default_output_path_none(self):
        """Test default output_path is None."""
        config = Config()
        assert config.output_path is None

    def test_default_verbose_false(self):
        """Test default verbose is False."""
        config = Config()
        assert config.verbose is False

    def test_default_dry_run_false(self):
        """Test default dry_run is False."""
        config = Config()
        assert config.dry_run is False

    def test_default_parallel_workers(self):
        """Test default parallel_workers."""
        config = Config()
        assert config.parallel_workers == 1

    def test_custom_input_path(self):
        """Test custom input_path."""
        config = Config(input_path=Path("/custom/input"))
        assert config.input_path == Path("/custom/input")

    def test_custom_output_path(self):
        """Test custom output_path."""
        config = Config(output_path=Path("/custom/output"))
        assert config.output_path == Path("/custom/output")

    def test_custom_verbose(self):
        """Test custom verbose."""
        config = Config(verbose=True)
        assert config.verbose is True

    def test_custom_dry_run(self):
        """Test custom dry_run."""
        config = Config(dry_run=True)
        assert config.dry_run is True

    def test_custom_parallel_workers(self):
        """Test custom parallel_workers."""
        config = Config(parallel_workers=4)
        assert config.parallel_workers == 4


# =============================================================================
# CATEGORIES TESTS
# =============================================================================

class TestCategories:
    """Tests for CATEGORIES list."""

    EXPECTED_CATEGORIES = [
        "analytics",
        "competitors",
        "employees",
        "equipment",
        "faq",
        "features",
        "fiscal",
        "integrations",
        "inventory",
        "mobile",
        "pricing",
        "products",
        "promotions",
        "regions",
        "stability",
        "support",
        "tis",
    ]

    def test_categories_is_list(self):
        """Test CATEGORIES is a list."""
        assert isinstance(CATEGORIES, list)

    def test_categories_count(self):
        """Test CATEGORIES has expected count."""
        assert len(CATEGORIES) == 17

    def test_all_expected_categories_present(self):
        """Test all expected categories are present."""
        for cat in self.EXPECTED_CATEGORIES:
            assert cat in CATEGORIES, f"Category {cat} not found"

    def test_categories_are_strings(self):
        """Test all categories are strings."""
        for cat in CATEGORIES:
            assert isinstance(cat, str)

    def test_categories_are_lowercase(self):
        """Test all categories are lowercase."""
        for cat in CATEGORIES:
            assert cat == cat.lower()


class TestCategoryFiles:
    """Tests for CATEGORY_FILES mapping."""

    def test_category_files_is_dict(self):
        """Test CATEGORY_FILES is a dict."""
        assert isinstance(CATEGORY_FILES, dict)

    def test_category_files_matches_categories(self):
        """Test CATEGORY_FILES has entry for each category."""
        for cat in CATEGORIES:
            assert cat in CATEGORY_FILES

    def test_category_files_format(self):
        """Test CATEGORY_FILES values have .yaml extension."""
        for cat, filename in CATEGORY_FILES.items():
            assert filename == f"{cat}.yaml"


# =============================================================================
# CATEGORY KEYWORDS TESTS
# =============================================================================

class TestCategoryKeywords:
    """Tests for CATEGORY_KEYWORDS mapping."""

    def test_category_keywords_is_dict(self):
        """Test CATEGORY_KEYWORDS is a dict."""
        assert isinstance(CATEGORY_KEYWORDS, dict)

    def test_all_categories_have_keywords(self):
        """Test all categories have keywords."""
        for cat in CATEGORIES:
            assert cat in CATEGORY_KEYWORDS, f"Category {cat} has no keywords"

    def test_keywords_are_lists(self):
        """Test all keyword values are lists."""
        for cat, keywords in CATEGORY_KEYWORDS.items():
            assert isinstance(keywords, list), f"Keywords for {cat} is not a list"

    def test_keywords_are_strings(self):
        """Test all keywords are strings."""
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                assert isinstance(kw, str), f"Keyword in {cat} is not a string"

    def test_keywords_not_empty(self):
        """Test no category has empty keywords."""
        for cat, keywords in CATEGORY_KEYWORDS.items():
            assert len(keywords) > 0, f"Category {cat} has empty keywords"


class TestCategoryKeywordsPricing:
    """Tests for pricing category keywords."""

    def test_pricing_has_price_words(self):
        """Test pricing has price-related words."""
        keywords = CATEGORY_KEYWORDS["pricing"]
        assert any("цена" in kw or "стоимость" in kw or "тариф" in kw for kw in keywords)

    def test_pricing_has_payment_words(self):
        """Test pricing has payment-related words."""
        keywords = CATEGORY_KEYWORDS["pricing"]
        assert any("оплата" in kw or "подписка" in kw for kw in keywords)


class TestCategoryKeywordsFeatures:
    """Tests for features category keywords."""

    def test_features_has_function_words(self):
        """Test features has function-related words."""
        keywords = CATEGORY_KEYWORDS["features"]
        assert any("функция" in kw or "возможность" in kw for kw in keywords)


class TestCategoryKeywordsIntegrations:
    """Tests for integrations category keywords."""

    def test_integrations_has_integration_word(self):
        """Test integrations has 'integration' word."""
        keywords = CATEGORY_KEYWORDS["integrations"]
        assert any("интеграция" in kw or "api" in kw.lower() for kw in keywords)

    def test_integrations_has_services(self):
        """Test integrations has specific service names."""
        keywords = CATEGORY_KEYWORDS["integrations"]
        assert any("1с" in kw.lower() or "kaspi" in kw.lower() for kw in keywords)


class TestCategoryKeywordsSupport:
    """Tests for support category keywords."""

    def test_support_has_support_words(self):
        """Test support has support-related words."""
        keywords = CATEGORY_KEYWORDS["support"]
        assert any("поддержка" in kw or "помощь" in kw for kw in keywords)


class TestCategoryKeywordsEquipment:
    """Tests for equipment category keywords."""

    def test_equipment_has_device_words(self):
        """Test equipment has device-related words."""
        keywords = CATEGORY_KEYWORDS["equipment"]
        assert any("оборудование" in kw or "касса" in kw or "терминал" in kw for kw in keywords)


class TestCategoryKeywordsMobile:
    """Tests for mobile category keywords."""

    def test_mobile_has_mobile_words(self):
        """Test mobile has mobile-related words."""
        keywords = CATEGORY_KEYWORDS["mobile"]
        assert any("мобильн" in kw or "приложение" in kw for kw in keywords)


class TestCategoryKeywordsAnalytics:
    """Tests for analytics category keywords."""

    def test_analytics_has_analytics_words(self):
        """Test analytics has analytics-related words."""
        keywords = CATEGORY_KEYWORDS["analytics"]
        assert any("аналитика" in kw or "отчёт" in kw or "статистика" in kw for kw in keywords)


class TestCategoryKeywordsInventory:
    """Tests for inventory category keywords."""

    def test_inventory_has_stock_words(self):
        """Test inventory has stock-related words."""
        keywords = CATEGORY_KEYWORDS["inventory"]
        assert any("склад" in kw or "товар" in kw or "остаток" in kw for kw in keywords)


class TestCategoryKeywordsEmployees:
    """Tests for employees category keywords."""

    def test_employees_has_staff_words(self):
        """Test employees has staff-related words."""
        keywords = CATEGORY_KEYWORDS["employees"]
        assert any("сотрудник" in kw or "персонал" in kw for kw in keywords)


class TestCategoryKeywordsFaq:
    """Tests for faq category keywords."""

    def test_faq_has_question_words(self):
        """Test faq has question-related words."""
        keywords = CATEGORY_KEYWORDS["faq"]
        assert any("вопрос" in kw or "faq" in kw.lower() for kw in keywords)


class TestCategoryKeywordsStability:
    """Tests for stability category keywords."""

    def test_stability_has_security_words(self):
        """Test stability has security-related words."""
        keywords = CATEGORY_KEYWORDS["stability"]
        assert any("безопасность" in kw or "защита" in kw or "бэкап" in kw for kw in keywords)


class TestCategoryKeywordsCompetitors:
    """Tests for competitors category keywords."""

    def test_competitors_has_comparison_words(self):
        """Test competitors has comparison-related words."""
        keywords = CATEGORY_KEYWORDS["competitors"]
        assert any("конкурент" in kw or "сравнение" in kw for kw in keywords)


class TestCategoryKeywordsFiscal:
    """Tests for fiscal category keywords."""

    def test_fiscal_has_tax_words(self):
        """Test fiscal has tax-related words."""
        keywords = CATEGORY_KEYWORDS["fiscal"]
        assert any("фискальный" in kw or "чек" in kw or "налог" in kw for kw in keywords)


class TestCategoryKeywordsRegions:
    """Tests for regions category keywords."""

    def test_regions_has_location_words(self):
        """Test regions has location-related words."""
        keywords = CATEGORY_KEYWORDS["regions"]
        assert any("регион" in kw or "город" in kw for kw in keywords)


class TestCategoryKeywordsPromotions:
    """Tests for promotions category keywords."""

    def test_promotions_has_promo_words(self):
        """Test promotions has promo-related words."""
        keywords = CATEGORY_KEYWORDS["promotions"]
        assert any("акция" in kw or "скидка" in kw or "бонус" in kw for kw in keywords)


class TestCategoryKeywordsTis:
    """Tests for tis category keywords."""

    def test_tis_has_tax_integration_words(self):
        """Test tis has tax integration words."""
        keywords = CATEGORY_KEYWORDS["tis"]
        assert any("тис" in kw.lower() or "910" in kw or "913" in kw for kw in keywords)


# =============================================================================
# COMMON TYPOS TESTS
# =============================================================================

class TestCommonTypos:
    """Tests for COMMON_TYPOS dictionary."""

    def test_common_typos_is_dict(self):
        """Test COMMON_TYPOS is a dict."""
        assert isinstance(COMMON_TYPOS, dict)

    def test_common_typos_not_empty(self):
        """Test COMMON_TYPOS is not empty."""
        assert len(COMMON_TYPOS) > 0

    def test_typos_are_lists(self):
        """Test all typo values are lists."""
        for word, typos in COMMON_TYPOS.items():
            assert isinstance(typos, list), f"Typos for {word} is not a list"

    def test_typos_are_strings(self):
        """Test all typos are strings."""
        for word, typos in COMMON_TYPOS.items():
            for typo in typos:
                assert isinstance(typo, str)

    def test_has_price_typos(self):
        """Test has price-related word typos."""
        assert "стоимость" in COMMON_TYPOS or "цена" in COMMON_TYPOS

    def test_has_integration_typos(self):
        """Test has integration word typos."""
        assert "интеграция" in COMMON_TYPOS

    def test_has_function_typos(self):
        """Test has function word typos."""
        assert "функция" in COMMON_TYPOS

    def test_typos_differ_from_correct(self):
        """Test typos are different from correct word."""
        for word, typos in COMMON_TYPOS.items():
            for typo in typos:
                assert typo != word, f"Typo {typo} equals correct word {word}"


# =============================================================================
# KEYBOARD NEIGHBORS TESTS
# =============================================================================

class TestKeyboardNeighborsRu:
    """Tests for KEYBOARD_NEIGHBORS_RU dictionary."""

    def test_keyboard_neighbors_is_dict(self):
        """Test KEYBOARD_NEIGHBORS_RU is a dict."""
        assert isinstance(KEYBOARD_NEIGHBORS_RU, dict)

    def test_keyboard_neighbors_not_empty(self):
        """Test KEYBOARD_NEIGHBORS_RU is not empty."""
        assert len(KEYBOARD_NEIGHBORS_RU) > 0

    def test_keys_are_russian_letters(self):
        """Test keys are Russian letters."""
        russian_lower = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
        for key in KEYBOARD_NEIGHBORS_RU.keys():
            assert key in russian_lower, f"Key {key} is not a Russian letter"

    def test_values_are_strings(self):
        """Test values are strings of neighbor letters."""
        for key, neighbors in KEYBOARD_NEIGHBORS_RU.items():
            assert isinstance(neighbors, str)

    def test_has_common_letters(self):
        """Test has common Russian letters."""
        common_letters = ['а', 'о', 'е', 'и', 'н', 'т']
        for letter in common_letters:
            assert letter in KEYBOARD_NEIGHBORS_RU, f"Letter {letter} not in neighbors"

    def test_neighbors_are_valid_letters(self):
        """Test neighbor values are valid Russian letters."""
        russian_lower = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя|'
        for key, neighbors in KEYBOARD_NEIGHBORS_RU.items():
            for char in neighbors:
                if char != '|':  # | is separator
                    assert char in russian_lower, \
                        f"Neighbor {char} for {key} is not Russian"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
