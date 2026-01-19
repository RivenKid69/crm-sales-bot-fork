"""
Personalization v2 — адаптивная персонализация на основе поведенческих сигналов.

Компоненты:
- StyleParameters, PersonalizationResult — результаты персонализации
- AdaptiveStyleSelector — выбор стиля на основе engagement/momentum/frustration
- IndustryDetectorV2 — semantic определение отрасли
- EffectiveActionTracker — session memory для отслеживания эффективных тактик
- PersonalizationEngineV2 — главный движок персонализации

Feature flags:
- personalization: Master switch (legacy)
- personalization_v2: V2 engine
- personalization_adaptive_style: AdaptiveStyleSelector
- personalization_semantic_industry: IndustryDetectorV2 semantic matching
- personalization_session_memory: EffectiveActionTracker

Usage:
    from src.personalization import PersonalizationEngineV2, AdaptiveStyleSelector

    engine = PersonalizationEngineV2()
    result = engine.personalize(envelope, collected_data)
    prompt_vars = result.to_prompt_variables()
"""

from src.personalization.result import (
    StyleParameters,
    IndustryContext,
    BusinessContext,
    PersonalizationResult,
)
from src.personalization.style_selector import (
    AdaptiveStyleSelector,
    BehavioralSignals,
)
from src.personalization.industry_detector import (
    IndustryDetectorV2,
    IndustryDetectionResult,
)
from src.personalization.action_tracker import (
    EffectiveActionTracker,
    ActionOutcome,
)
from src.personalization.engine import PersonalizationEngineV2

__all__ = [
    # Result types
    "StyleParameters",
    "IndustryContext",
    "BusinessContext",
    "PersonalizationResult",
    # Style selector
    "AdaptiveStyleSelector",
    "BehavioralSignals",
    # Industry detector
    "IndustryDetectorV2",
    "IndustryDetectionResult",
    # Action tracker
    "EffectiveActionTracker",
    "ActionOutcome",
    # Main engine
    "PersonalizationEngineV2",
]
