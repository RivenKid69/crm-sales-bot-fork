"""
Tone Analyzer Module.

Каскадный анализатор тона с 3-уровневой архитектурой:
- Tier 1: Regex (быстрый, явные сигналы)
- Tier 2: Semantic (TEI, неявные сигналы)
- Tier 3: LLM (сарказм, ирония)

Использование:
    from tone_analyzer import CascadeToneAnalyzer, Tone, Style, ToneAnalysis

    # Или через singleton
    from tone_analyzer import get_cascade_tone_analyzer

    analyzer = get_cascade_tone_analyzer()
    result = analyzer.analyze("Сколько можно уже!")
    print(result.tone)  # Tone.FRUSTRATED

Для обратной совместимости также доступны:
    from tone_analyzer import ToneAnalyzer  # Alias для CascadeToneAnalyzer

Enhanced with Intensity-based Frustration Calculation:
    - Multiple signals = higher weight (intensity multipliers)
    - Consecutive negative turns = faster escalation
    - Pre-intervention for RUSHED users with high signal count
    - "быстрее, не тяни, некогда" (3 RUSHED signals) now properly handled
"""

from src.tone_analyzer.models import Tone, Style, ToneAnalysis
from src.tone_analyzer.markers import (
    TONE_MARKERS,
    INFORMAL_MARKERS,
    FRUSTRATION_WEIGHTS,
    FRUSTRATION_DECAY,
    FRUSTRATION_THRESHOLDS,
    MAX_FRUSTRATION,
)
from src.tone_analyzer.frustration_tracker import FrustrationTracker
from src.tone_analyzer.frustration_intensity import (
    FrustrationIntensityCalculator,
    FrustrationIntensityRegistry,
    IFrustrationIntensityCalculator,
    IntensityConfig,
    calculate_frustration_delta,
    should_pre_intervene,
    get_intervention_urgency,
)
from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
from src.tone_analyzer.semantic_analyzer import (
    SemanticToneAnalyzer,
    get_semantic_tone_analyzer,
    reset_semantic_tone_analyzer,
)
from src.tone_analyzer.llm_analyzer import LLMToneAnalyzer
from src.tone_analyzer.cascade_analyzer import (
    CascadeToneAnalyzer,
    CascadeToneConfig,
    get_cascade_tone_analyzer,
    reset_cascade_tone_analyzer,
)
from src.tone_analyzer.examples import TONE_EXAMPLES

# Обратная совместимость: ToneAnalyzer = CascadeToneAnalyzer
ToneAnalyzer = CascadeToneAnalyzer

__all__ = [
    # Models
    "Tone",
    "Style",
    "ToneAnalysis",

    # Markers
    "TONE_MARKERS",
    "INFORMAL_MARKERS",
    "FRUSTRATION_WEIGHTS",
    "FRUSTRATION_DECAY",
    "FRUSTRATION_THRESHOLDS",
    "MAX_FRUSTRATION",

    # Trackers
    "FrustrationTracker",

    # Intensity-based frustration calculation (NEW)
    "FrustrationIntensityCalculator",
    "FrustrationIntensityRegistry",
    "IFrustrationIntensityCalculator",
    "IntensityConfig",
    "calculate_frustration_delta",
    "should_pre_intervene",
    "get_intervention_urgency",

    # Analyzers
    "RegexToneAnalyzer",
    "SemanticToneAnalyzer",
    "LLMToneAnalyzer",
    "CascadeToneAnalyzer",
    "CascadeToneConfig",

    # Singletons
    "get_cascade_tone_analyzer",
    "reset_cascade_tone_analyzer",
    "get_semantic_tone_analyzer",
    "reset_semantic_tone_analyzer",

    # Examples
    "TONE_EXAMPLES",

    # Backward compatibility
    "ToneAnalyzer",
]


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("CASCADE TONE ANALYZER DEMO")
    print("=" * 60)

    # Включаем все tier'ы для демо
    from src.feature_flags import flags
    flags.set_override("cascade_tone_analyzer", True)
    flags.set_override("tone_semantic_tier2", True)
    flags.set_override("tone_llm_tier3", False)  # LLM отключен для быстрого демо

    analyzer = CascadeToneAnalyzer()

    test_messages = [
        # Tier 1: Regex должен ловить
        "Сколько можно уже! 😡",
        "Отлично! Супер! 👍",
        "Короче, давайте к делу",
        "Не понял, что это значит???",

        # Tier 2: Semantic должен ловить
        "Мне это не подходит",
        "Звучит неубедительно",
        "Хотелось бы побыстрее закончить",

        # Нейтральные
        "У нас 10 человек в команде",
        "Сколько стоит?",
    ]

    for msg in test_messages:
        print(f"\n--- '{msg[:40]}...' ---" if len(msg) > 40 else f"\n--- '{msg}' ---")
        result = analyzer.analyze(msg)
        print(f"  Тон: {result.tone.value}")
        print(f"  Tier: {result.tier_used}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Frustration: {result.frustration_level}")
        print(f"  Latency: {result.latency_ms:.1f}ms")
        if result.signals:
            print(f"  Signals: {result.signals[:2]}")

    print("\n" + "=" * 60)
    print(f"Final frustration level: {analyzer.get_frustration_level()}")
    print("=" * 60)

    # Cleanup
    flags.clear_all_overrides()
