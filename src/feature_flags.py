"""
Feature Flags для CRM Sales Bot.

Контроль постепенного включения фич.
Позволяет откатить любое изменение без деплоя.

Использование:
    from feature_flags import flags

    if flags.tone_analysis:
        # Новая логика анализа тона
        pass

    if flags.is_enabled("custom_flag"):
        # Проверка произвольного флага
        pass
"""

from typing import Any, Dict, List, Set
from settings import settings


class FeatureFlags:
    """
    Система feature flags для постепенного включения фич.

    Особенности:
    - Загрузка из settings.yaml
    - Override через environment variables
    - Типизированные property для основных флагов
    - Метод is_enabled() для произвольных флагов
    - Поддержка групп флагов
    """

    # Дефолтные значения флагов (используются если не указаны в settings)
    DEFAULTS: Dict[str, bool] = {
        # Фаза 2: Естественность диалога
        "tone_analysis": False,           # Анализ тона клиента
        "response_variations": True,      # Вариативность ответов (безопасно)

        # Фаза 3: Оптимизация SPIN Flow
        "lead_scoring": False,            # Скоринг лидов для адаптивного SPIN
        "circular_flow": False,           # Возврат назад по фазам (опасно)

        # Фаза 1: Защита и надёжность
        "multi_tier_fallback": True,      # 4-уровневый fallback (критично)
        "conversation_guard": True,       # Защита от зацикливания

        # Фаза 0: Инфраструктура
        "structured_logging": True,       # JSON логи
        "metrics_tracking": True,         # Трекинг метрик

        # Дополнительные флаги
        "personalization": False,         # Персонализация на основе данных
        "objection_handler": False,       # Продвинутая обработка возражений
        "cta_generator": False,           # Генерация Call-to-Action

        # Фаза 4: Intent Disambiguation
        "intent_disambiguation": False,   # Уточнение намерения при близких scores

        # Фаза 4.5: Cascade Classifier (семантический fallback)
        "cascade_classifier": True,       # Каскадный классификатор с эмбеддингами

        # Фаза 4.6: Semantic Objection Detection
        "semantic_objection_detection": True,  # Semantic fallback для возражений

        # Фаза 5: Dynamic CTA Fallback
        "dynamic_cta_fallback": False,    # Динамические подсказки в fallback tier_2

        # === Context Policy (PLAN_CONTEXT_POLICY.md) ===
        # Phase 0: Инфраструктура контекста
        "context_full_envelope": True,    # Полный ContextEnvelope для всех подсистем
        "context_shadow_mode": False,     # Shadow mode: логируем решения без применения

        # Phase 2: Естественность диалога
        "context_response_directives": False,  # ResponseDirectives для генератора

        # Phase 3: Policy overlays
        "context_policy_overlays": True,   # DialoguePolicy action overrides
        "context_engagement_v2": False,    # Улучшенный расчёт engagement

        # Phase 5: CTA с памятью
        "context_cta_memory": False,       # CTA с учётом episodic memory

        # === Cascade Tone Analyzer (Phase 5) ===
        "cascade_tone_analyzer": True,     # Master switch для каскадного анализатора
        "tone_semantic_tier2": True,       # RoSBERTa semantic (Tier 2)
        "tone_llm_tier3": True,            # LLM fallback (Tier 3)
    }

    # Группы флагов для удобного управления
    GROUPS: Dict[str, List[str]] = {
        "phase_0": ["structured_logging", "metrics_tracking"],
        "phase_1": ["multi_tier_fallback", "conversation_guard"],
        "phase_2": ["tone_analysis", "response_variations", "personalization"],
        "phase_3": ["lead_scoring", "circular_flow", "objection_handler", "cta_generator", "dynamic_cta_fallback"],
        "phase_4": ["intent_disambiguation", "cascade_classifier", "semantic_objection_detection"],
        "safe": ["response_variations", "multi_tier_fallback", "structured_logging", "metrics_tracking", "conversation_guard", "cascade_classifier", "semantic_objection_detection"],
        "risky": ["circular_flow", "lead_scoring"],
        # Context Policy groups (PLAN_CONTEXT_POLICY.md)
        "context_phase_0": ["context_full_envelope", "context_shadow_mode"],
        "context_phase_2": ["context_response_directives"],
        "context_phase_3": ["context_policy_overlays", "context_engagement_v2"],
        "context_phase_5": ["context_cta_memory"],
        "context_all": [
            "context_full_envelope", "context_shadow_mode",
            "context_response_directives", "context_policy_overlays",
            "context_engagement_v2", "context_cta_memory"
        ],
        "context_safe": ["context_full_envelope", "context_response_directives"],
        # Cascade Tone Analyzer groups
        "phase_5_tone": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
        "tone_safe": ["cascade_tone_analyzer"],  # Только улучшенный Tier 1
        "tone_full": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
    }

    def __init__(self):
        self._flags: Dict[str, bool] = {}
        self._overrides: Dict[str, bool] = {}
        self._load_flags()

    def _load_flags(self) -> None:
        """Загрузить флаги из settings и environment"""
        # Начинаем с defaults
        self._flags = self.DEFAULTS.copy()

        # Переопределяем из settings.yaml
        settings_flags = settings.get_nested("feature_flags", {})
        if isinstance(settings_flags, dict):
            for key, value in settings_flags.items():
                if isinstance(value, bool):
                    self._flags[key] = value

        # Переопределяем из environment (высший приоритет)
        import os
        for key in self._flags:
            env_key = f"FF_{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                self._flags[key] = env_value.lower() in ("true", "1", "yes", "on")

    def reload(self) -> None:
        """Перезагрузить флаги из settings"""
        self._overrides.clear()
        self._load_flags()

    def is_enabled(self, flag: str) -> bool:
        """
        Проверить включён ли флаг.

        Args:
            flag: Имя флага

        Returns:
            True если флаг включён, False иначе
        """
        # Сначала проверяем runtime overrides
        if flag in self._overrides:
            return self._overrides[flag]

        # Затем проверяем загруженные флаги
        return self._flags.get(flag, False)

    def set_override(self, flag: str, value: bool) -> None:
        """
        Установить runtime override для флага.
        Используется для тестов и динамического управления.

        Args:
            flag: Имя флага
            value: Значение
        """
        self._overrides[flag] = value

    def clear_override(self, flag: str) -> None:
        """Убрать runtime override для флага"""
        self._overrides.pop(flag, None)

    def clear_all_overrides(self) -> None:
        """Убрать все runtime overrides"""
        self._overrides.clear()

    def get_all_flags(self) -> Dict[str, bool]:
        """Получить все флаги с текущими значениями"""
        result = self._flags.copy()
        result.update(self._overrides)
        return result

    def get_enabled_flags(self) -> Set[str]:
        """Получить набор включённых флагов"""
        all_flags = self.get_all_flags()
        return {k for k, v in all_flags.items() if v}

    def get_disabled_flags(self) -> Set[str]:
        """Получить набор выключенных флагов"""
        all_flags = self.get_all_flags()
        return {k for k, v in all_flags.items() if not v}

    def is_group_enabled(self, group: str, require_all: bool = False) -> bool:
        """
        Проверить включена ли группа флагов.

        Args:
            group: Имя группы
            require_all: True = все флаги должны быть включены,
                        False = хотя бы один

        Returns:
            True если группа включена
        """
        flags_in_group = self.GROUPS.get(group, [])
        if not flags_in_group:
            return False

        if require_all:
            return all(self.is_enabled(f) for f in flags_in_group)
        else:
            return any(self.is_enabled(f) for f in flags_in_group)

    def enable_group(self, group: str) -> None:
        """Включить все флаги в группе (через overrides)"""
        for flag in self.GROUPS.get(group, []):
            self.set_override(flag, True)

    def disable_group(self, group: str) -> None:
        """Выключить все флаги в группе (через overrides)"""
        for flag in self.GROUPS.get(group, []):
            self.set_override(flag, False)

    # =========================================================================
    # Типизированные property для основных флагов
    # =========================================================================

    @property
    def tone_analysis(self) -> bool:
        """Включён ли анализ тона клиента"""
        return self.is_enabled("tone_analysis")

    @property
    def lead_scoring(self) -> bool:
        """Включён ли скоринг лидов для адаптивного SPIN"""
        return self.is_enabled("lead_scoring")

    @property
    def response_variations(self) -> bool:
        """Включена ли вариативность ответов"""
        return self.is_enabled("response_variations")

    @property
    def multi_tier_fallback(self) -> bool:
        """Включён ли 4-уровневый fallback"""
        return self.is_enabled("multi_tier_fallback")

    @property
    def circular_flow(self) -> bool:
        """Включён ли возврат назад по фазам"""
        return self.is_enabled("circular_flow")

    @property
    def conversation_guard(self) -> bool:
        """Включена ли защита от зацикливания"""
        return self.is_enabled("conversation_guard")

    @property
    def structured_logging(self) -> bool:
        """Включены ли структурированные логи"""
        return self.is_enabled("structured_logging")

    @property
    def metrics_tracking(self) -> bool:
        """Включён ли трекинг метрик"""
        return self.is_enabled("metrics_tracking")

    @property
    def personalization(self) -> bool:
        """Включена ли персонализация"""
        return self.is_enabled("personalization")

    @property
    def objection_handler(self) -> bool:
        """Включена ли продвинутая обработка возражений"""
        return self.is_enabled("objection_handler")

    @property
    def cta_generator(self) -> bool:
        """Включена ли генерация Call-to-Action"""
        return self.is_enabled("cta_generator")

    @property
    def intent_disambiguation(self) -> bool:
        """Включено ли уточнение намерения при близких scores"""
        return self.is_enabled("intent_disambiguation")

    @property
    def dynamic_cta_fallback(self) -> bool:
        """Включены ли динамические подсказки в fallback tier_2"""
        return self.is_enabled("dynamic_cta_fallback")

    @property
    def cascade_classifier(self) -> bool:
        """Включён ли каскадный классификатор с семантическим fallback"""
        return self.is_enabled("cascade_classifier")

    @property
    def semantic_objection_detection(self) -> bool:
        """Включён ли семантический fallback для детекции возражений"""
        return self.is_enabled("semantic_objection_detection")

    # =========================================================================
    # Context Policy flags (PLAN_CONTEXT_POLICY.md)
    # =========================================================================

    @property
    def context_full_envelope(self) -> bool:
        """Включён ли полный ContextEnvelope"""
        return self.is_enabled("context_full_envelope")

    @property
    def context_shadow_mode(self) -> bool:
        """Включён ли shadow mode для policy"""
        return self.is_enabled("context_shadow_mode")

    @property
    def context_response_directives(self) -> bool:
        """Включены ли ResponseDirectives"""
        return self.is_enabled("context_response_directives")

    @property
    def context_policy_overlays(self) -> bool:
        """Включены ли policy overlays"""
        return self.is_enabled("context_policy_overlays")

    @property
    def context_engagement_v2(self) -> bool:
        """Включён ли улучшенный расчёт engagement"""
        return self.is_enabled("context_engagement_v2")

    @property
    def context_cta_memory(self) -> bool:
        """Включён ли CTA с учётом episodic memory"""
        return self.is_enabled("context_cta_memory")

    # =========================================================================
    # Cascade Tone Analyzer flags
    # =========================================================================

    @property
    def cascade_tone_analyzer(self) -> bool:
        """Включён ли каскадный анализатор тона"""
        return self.is_enabled("cascade_tone_analyzer")

    @property
    def tone_semantic_tier2(self) -> bool:
        """Включён ли Tier 2 (RoSBERTa semantic) для анализа тона"""
        return self.is_enabled("tone_semantic_tier2")

    @property
    def tone_llm_tier3(self) -> bool:
        """Включён ли Tier 3 (LLM) для анализа тона"""
        return self.is_enabled("tone_llm_tier3")


# Singleton экземпляр
flags = FeatureFlags()


# =============================================================================
# Декоратор для условного выполнения
# =============================================================================

def feature_flag(flag_name: str, default_return: Any = None):
    """
    Декоратор для условного выполнения функции на основе feature flag.

    Args:
        flag_name: Имя флага
        default_return: Что возвращать если флаг выключен

    Example:
        @feature_flag("tone_analysis")
        def analyze_tone(message: str):
            # Выполняется только если tone_analysis включён
            return {"tone": "neutral"}
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if flags.is_enabled(flag_name):
                return func(*args, **kwargs)
            return default_return
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# =============================================================================
# CLI для проверки флагов
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("FEATURE FLAGS STATUS")
    print("=" * 60)

    print("\n--- All Flags ---")
    for flag, value in sorted(flags.get_all_flags().items()):
        status = "ON" if value else "OFF"
        print(f"  {flag}: {status}")

    print("\n--- Enabled Flags ---")
    enabled = flags.get_enabled_flags()
    if enabled:
        for flag in sorted(enabled):
            print(f"  + {flag}")
    else:
        print("  (none)")

    print("\n--- Disabled Flags ---")
    disabled = flags.get_disabled_flags()
    if disabled:
        for flag in sorted(disabled):
            print(f"  - {flag}")
    else:
        print("  (none)")

    print("\n--- Groups ---")
    for group, group_flags in FeatureFlags.GROUPS.items():
        all_enabled = flags.is_group_enabled(group, require_all=True)
        any_enabled = flags.is_group_enabled(group, require_all=False)
        status = "ALL ON" if all_enabled else ("PARTIAL" if any_enabled else "OFF")
        print(f"  {group}: {status}")

    print("\n" + "=" * 60)
