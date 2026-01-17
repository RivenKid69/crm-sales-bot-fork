"""
CTA Generator для CRM Sales Bot.

Генератор Call-to-Action для завершения сообщений.
Добавляет CTA только когда уместно.

Использование:
    from cta_generator import CTAGenerator

    generator = CTAGenerator()
    response = "Wipon помогает автоматизировать работу."
    context = {"frustration_level": 2, "state": "presentation"}

    final_response = generator.append_cta(response, "presentation", context)
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from random import choice
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.config_loader import LoadedConfig

try:
    from logger import logger
except ImportError:
    from src.logger import logger
from src.conditions.personalization import (
    PersonalizationContext,
    personalization_registry,
)


@dataclass
class CTAResult:
    """
    Результат генерации CTA.

    Attributes:
        original_response: Исходный ответ
        cta: Сгенерированный CTA (или None)
        final_response: Финальный ответ с CTA
        cta_added: Был ли добавлен CTA
        skip_reason: Причина пропуска (если CTA не добавлен)
    """
    original_response: str
    cta: Optional[str]
    final_response: str
    cta_added: bool
    skip_reason: Optional[str] = None


class CTAGenerator:
    """
    Генератор Call-to-Action для завершения сообщений.

    Принципы:
    1. CTA добавляется только в уместных состояниях
    2. Не добавляется если ответ уже содержит вопрос
    3. Не добавляется при высоком frustration
    4. Не добавляется слишком рано в диалоге

    Attributes:
        used_ctas: История использованных CTA для избежания повторов
    """

    # CTA по состояниям (defaults, loaded from config via _load_ctas)
    CTAS: Dict[str, List[str]] = {
        # В ранних состояниях CTA не добавляем
        "greeting": [],

        # В поздних состояниях — прямые CTA (defaults)
        "presentation": [
            "Готовы попробовать?",
            "Запланируем демо?",
            "Хотите тестовый доступ?",
            "Оставите контакт для связи?",
        ],
        "handle_objection": [
            "Может всё-таки глянем демо? Это бесплатно и ни к чему не обязывает.",
            "Давайте просто покажу — 15 минут, и всё станет понятнее.",
        ],
        "close": [
            "Какой контакт для связи удобнее?",
            "На какой email прислать информацию?",
            "Когда удобно созвониться?",
        ],
    }

    # Альтернативные CTA по типу действия
    CTA_BY_ACTION: Dict[str, List[str]] = {
        "demo": [
            "Запланируем демо?",
            "Показать на демо?",
            "Хотите увидеть в действии?",
        ],
        "contact": [
            "Оставите контакт?",
            "Какой контакт для связи?",
            "На какую почту прислать?",
        ],
        "trial": [
            "Хотите тестовый доступ?",
            "Попробуете бесплатно?",
            "Дать пробный период?",
        ],
        "info": [
            "Прислать подробную информацию?",
            "Отправить презентацию?",
            "Скинуть материалы на почту?",
        ],
    }

    # Мягкие CTA (для сомневающихся клиентов)
    SOFT_CTAS: List[str] = [
        "Если интересно — могу рассказать подробнее.",
        "Будут вопросы — пишите.",
        "Если что — я на связи.",
    ]

    # Пороги для пропуска CTA
    FRUSTRATION_THRESHOLD = 5    # Не добавлять при высоком frustration
    MIN_TURNS_FOR_CTA = 3        # Минимум ходов до добавления CTA

    # Early states where CTA should not be added (loaded from config)
    DEFAULT_EARLY_STATES = {"greeting"}

    def __init__(self, config: Optional["LoadedConfig"] = None):
        """
        Инициализация генератора.

        Args:
            config: LoadedConfig for CTA templates and early_states
        """
        self.used_ctas: Dict[str, List[str]] = {}
        self.turn_count = 0

        # Load config-driven templates (fallback to class constants)
        self._ctas = self._load_ctas(config)
        self._cta_by_action = self._load_cta_by_action(config)
        self._early_states = self._load_early_states(config)

    def _load_ctas(self, config: Optional["LoadedConfig"]) -> Dict[str, List[str]]:
        """Load state-specific CTAs from config or use default."""
        if config is None:
            return self.CTAS
        templates = config.cta.get("templates", {})
        return templates if templates else self.CTAS

    def _load_cta_by_action(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, List[str]]:
        """Load action-specific CTAs from config or use default."""
        if config is None:
            return self.CTA_BY_ACTION
        by_action = config.cta.get("by_action", {})
        return by_action if by_action else self.CTA_BY_ACTION

    def _load_early_states(self, config: Optional["LoadedConfig"]) -> set:
        """Load early states from config or use default."""
        if config is None:
            return self.DEFAULT_EARLY_STATES
        early = config.cta.get("early_states", [])
        return set(early) if early else self.DEFAULT_EARLY_STATES

    def reset(self) -> None:
        """Сброс для нового разговора"""
        self.used_ctas.clear()
        self.turn_count = 0

    def increment_turn(self) -> None:
        """Увеличить счётчик ходов"""
        self.turn_count += 1

    def should_add_cta(
        self,
        state: str,
        response: str,
        context: Optional[Dict] = None
    ) -> tuple:
        """
        Проверить нужно ли добавлять CTA.

        Args:
            state: Текущее состояние
            response: Текущий ответ
            context: Контекст (frustration_level, last_action, etc.)

        Returns:
            Tuple[bool, Optional[str]]: (нужно ли добавлять, причина пропуска)
        """
        context = context or {}

        # 1. Проверяем есть ли CTA для этого состояния
        if state not in self._ctas or not self._ctas[state]:
            return False, "no_cta_for_state"

        # 2. Проверяем не заканчивается ли ответ вопросом
        if response.rstrip().endswith("?"):
            return False, "response_ends_with_question"

        # 3. Проверяем frustration level
        frustration = context.get("frustration_level", 0)
        if frustration >= self.FRUSTRATION_THRESHOLD:
            return False, f"high_frustration_{frustration}"

        # 4. Проверяем не слишком ли рано
        if self.turn_count < self.MIN_TURNS_FOR_CTA:
            return False, f"too_early_turn_{self.turn_count}"

        # 5. Проверяем last_action
        last_action = context.get("last_action", "")
        if last_action == "answer_question":
            return False, "just_answered_question"

        # 6. Проверяем состояния где CTA не уместен
        if state in self._early_states:
            return False, "early_state"

        return True, None

    def get_cta(
        self,
        state: str,
        cta_type: Optional[str] = None,
        soft: bool = False
    ) -> Optional[str]:
        """
        Получить подходящий CTA.

        Args:
            state: Текущее состояние
            cta_type: Тип CTA (demo, contact, trial, info)
            soft: Использовать мягкий CTA

        Returns:
            CTA или None
        """
        # Выбираем источник CTA
        if soft:
            ctas = self.SOFT_CTAS
        elif cta_type and cta_type in self._cta_by_action:
            ctas = self._cta_by_action[cta_type]
        else:
            ctas = self._ctas.get(state, [])

        if not ctas:
            return None

        # Фильтруем уже использованные
        used = self.used_ctas.get(state, [])
        available = [cta for cta in ctas if cta not in used]

        if not available:
            # Все использованы — сбрасываем историю
            self.used_ctas[state] = []
            available = ctas

        # Выбираем случайный
        selected = choice(available)

        # Записываем в историю
        if state not in self.used_ctas:
            self.used_ctas[state] = []
        self.used_ctas[state].append(selected)

        return selected

    def append_cta(
        self,
        response: str,
        state: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Добавить CTA к ответу если уместно.

        Args:
            response: Текущий ответ
            state: Текущее состояние
            context: Контекст диалога

        Returns:
            Ответ с CTA или исходный ответ
        """
        should_add, skip_reason = self.should_add_cta(state, response, context)

        if not should_add:
            logger.debug(
                "CTA skipped",
                state=state,
                reason=skip_reason
            )
            return response

        # Определяем тип CTA на основе контекста
        context = context or {}
        cta_type = context.get("preferred_cta_type")
        soft = context.get("frustration_level", 0) >= 3  # Мягкий при среднем frustration

        cta = self.get_cta(state, cta_type=cta_type, soft=soft)
        if not cta:
            return response

        logger.info(
            "CTA added",
            state=state,
            cta=cta[:30]
        )

        # Добавляем CTA с пробелом
        return f"{response.rstrip()} {cta}"

    def generate_cta_result(
        self,
        response: str,
        state: str,
        context: Optional[Dict] = None
    ) -> CTAResult:
        """
        Генерировать полный результат с CTA.

        Args:
            response: Текущий ответ
            state: Текущее состояние
            context: Контекст диалога

        Returns:
            CTAResult с полной информацией
        """
        should_add, skip_reason = self.should_add_cta(state, response, context)

        if not should_add:
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason=skip_reason
            )

        context = context or {}
        cta_type = context.get("preferred_cta_type")
        soft = context.get("frustration_level", 0) >= 3

        cta = self.get_cta(state, cta_type=cta_type, soft=soft)
        if not cta:
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="no_cta_available"
            )

        final_response = f"{response.rstrip()} {cta}"

        return CTAResult(
            original_response=response,
            cta=cta,
            final_response=final_response,
            cta_added=True
        )

    def get_direct_cta(self, cta_type: str) -> Optional[str]:
        """
        Получить CTA напрямую по типу (без проверок).

        Args:
            cta_type: Тип CTA (demo, contact, trial, info)

        Returns:
            CTA или None
        """
        ctas = self.CTA_BY_ACTION.get(cta_type, [])
        if not ctas:
            return None
        return choice(ctas)

    def get_soft_cta(self) -> str:
        """Получить мягкий CTA"""
        return choice(self.SOFT_CTAS)

    def get_usage_stats(self) -> Dict:
        """Получить статистику использования CTA"""
        return {
            "turn_count": self.turn_count,
            "used_ctas_by_state": {
                state: len(ctas) for state, ctas in self.used_ctas.items()
            },
            "total_ctas_used": sum(len(ctas) for ctas in self.used_ctas.values())
        }

    # =========================================================================
    # CONDITION-BASED CTA METHODS (Phase 7 Integration)
    # =========================================================================

    def _get_cta_stats(self) -> Dict[str, Any]:
        """Get CTA statistics for PersonalizationContext."""
        last_cta_turn = None
        cta_count = sum(len(ctas) for ctas in self.used_ctas.values())

        # Find last CTA turn (approximate based on history)
        if cta_count > 0:
            last_cta_turn = max(0, self.turn_count - 1)

        return {
            "last_cta_turn": last_cta_turn,
            "cta_count": cta_count,
        }

    def create_personalization_context(
        self,
        state: str,
        context: Optional[Dict] = None
    ) -> PersonalizationContext:
        """
        Create a PersonalizationContext from state and context.

        Args:
            state: Current dialogue state
            context: Context dictionary

        Returns:
            PersonalizationContext for condition evaluation
        """
        context = context or {}
        cta_stats = self._get_cta_stats()

        # Build collected_data from context if not already there
        collected_data = context.get("collected_data", {})

        return PersonalizationContext.from_context_dict(
            context={
                "collected_data": collected_data,
                "turn_number": self.turn_count,
                "has_breakthrough": context.get("has_breakthrough", False),
                "engagement_level": context.get("engagement_level", "medium"),
                "momentum_direction": context.get("momentum_direction", "neutral"),
                "frustration_level": context.get("frustration_level", 0),
                "objection_type": context.get("objection_type"),
                "total_objections": context.get("total_objections", 0),
                "repeated_objection_types": context.get("repeated_objection_types", []),
                "last_action": context.get("last_action"),
            },
            state=state,
            cta_stats=cta_stats
        )

    def should_add_cta_with_conditions(
        self,
        state: str,
        response: str,
        context: Optional[Dict] = None
    ) -> tuple:
        """
        Check if CTA should be added using condition-based evaluation.

        Uses PersonalizationContext and registered conditions for
        more intelligent CTA decision making.

        Args:
            state: Current dialogue state
            response: Current response text
            context: Context dictionary

        Returns:
            Tuple[bool, Optional[str]]: (should add CTA, skip reason)
        """
        # First check response-based rules (these don't need conditions)
        if response.rstrip().endswith("?"):
            return False, "response_ends_with_question"

        # Create personalization context
        ctx = self.create_personalization_context(state, context)

        # Evaluate conditions
        try:
            should_add = personalization_registry.evaluate("should_add_cta", ctx)

            if not should_add:
                # Determine the specific reason
                if not personalization_registry.evaluate("cta_eligible_state", ctx):
                    return False, "no_cta_for_state"
                if not personalization_registry.evaluate("enough_turns_for_cta", ctx):
                    return False, f"too_early_turn_{ctx.turn_number}"
                if personalization_registry.evaluate("should_skip_cta", ctx):
                    return False, f"high_frustration_{ctx.frustration_level}"
                return False, "condition_not_met"

            return True, None

        except Exception as e:
            logger.warning(f"Error evaluating CTA conditions: {e}")
            # Fall back to legacy method
            return self.should_add_cta(state, response, context)

    def get_optimal_cta_type(
        self,
        state: str,
        context: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Determine the optimal CTA type using conditions.

        Uses PersonalizationContext and registered conditions to
        select the most appropriate CTA type.

        Args:
            state: Current dialogue state
            context: Context dictionary

        Returns:
            CTA type (demo, contact, trial, info) or None for default
        """
        ctx = self.create_personalization_context(state, context)

        try:
            # Check CTA type conditions in order of priority
            if personalization_registry.evaluate("contact_cta_appropriate", ctx):
                return "contact"

            if personalization_registry.evaluate("demo_cta_appropriate", ctx):
                return "demo"

            if personalization_registry.evaluate("trial_cta_appropriate", ctx):
                return "trial"

            if personalization_registry.evaluate("info_cta_appropriate", ctx):
                return "info"

            # No specific type recommended
            return None

        except Exception as e:
            logger.warning(f"Error determining CTA type: {e}")
            return None

    def append_cta_with_conditions(
        self,
        response: str,
        state: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Add CTA to response using condition-based evaluation.

        Enhanced version of append_cta that uses PersonalizationContext
        and registered conditions for smarter CTA selection.

        Args:
            response: Current response text
            state: Current dialogue state
            context: Context dictionary

        Returns:
            Response with CTA or original response
        """
        should_add, skip_reason = self.should_add_cta_with_conditions(
            state, response, context
        )

        if not should_add:
            logger.debug(
                "CTA skipped (conditions)",
                state=state,
                reason=skip_reason
            )
            return response

        # Determine CTA type using conditions
        ctx = self.create_personalization_context(state, context)
        cta_type = self.get_optimal_cta_type(state, context)

        # Check if soft CTA is needed
        try:
            soft = personalization_registry.evaluate("should_use_soft_cta", ctx)
        except Exception:
            soft = context.get("frustration_level", 0) >= 3 if context else False

        cta = self.get_cta(state, cta_type=cta_type, soft=soft)
        if not cta:
            return response

        logger.info(
            "CTA added (conditions)",
            state=state,
            cta_type=cta_type or "default",
            soft=soft,
            cta=cta[:30]
        )

        return f"{response.rstrip()} {cta}"

    def generate_cta_result_with_conditions(
        self,
        response: str,
        state: str,
        context: Optional[Dict] = None
    ) -> CTAResult:
        """
        Generate CTA result using condition-based evaluation.

        Enhanced version of generate_cta_result that uses
        PersonalizationContext and registered conditions.

        Args:
            response: Current response text
            state: Current dialogue state
            context: Context dictionary

        Returns:
            CTAResult with full information
        """
        should_add, skip_reason = self.should_add_cta_with_conditions(
            state, response, context
        )

        if not should_add:
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason=skip_reason
            )

        # Get optimal CTA
        ctx = self.create_personalization_context(state, context)
        cta_type = self.get_optimal_cta_type(state, context)

        try:
            soft = personalization_registry.evaluate("should_use_soft_cta", ctx)
        except Exception:
            soft = context.get("frustration_level", 0) >= 3 if context else False

        cta = self.get_cta(state, cta_type=cta_type, soft=soft)
        if not cta:
            return CTAResult(
                original_response=response,
                cta=None,
                final_response=response,
                cta_added=False,
                skip_reason="no_cta_available"
            )

        final_response = f"{response.rstrip()} {cta}"

        return CTAResult(
            original_response=response,
            cta=cta,
            final_response=final_response,
            cta_added=True
        )


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("CTA GENERATOR DEMO")
    print("=" * 60)

    generator = CTAGenerator()

    # Симуляция диалога
    test_cases = [
        ("greeting", "Здравствуйте! Чем могу помочь?", {}),
        ("presentation", "Wipon решает эту проблему автоматически.", {"frustration_level": 1}),
        ("presentation", "У нас есть интеграция с 1С.", {"frustration_level": 6}),
        ("handle_objection", "Понимаю ваши сомнения.", {"frustration_level": 2}),
        ("close", "Отлично! Давайте обменяемся контактами.", {}),
    ]

    for state, response, context in test_cases:
        generator.increment_turn()
        print(f"\n--- State: {state}, Turn: {generator.turn_count} ---")
        print(f"Original: {response}")
        print(f"Context: {context}")

        result = generator.generate_cta_result(response, state, context)
        print(f"CTA Added: {result.cta_added}")
        if result.cta:
            print(f"CTA: {result.cta}")
        if result.skip_reason:
            print(f"Skip reason: {result.skip_reason}")
        print(f"Final: {result.final_response}")

    print("\n" + "=" * 60)
    print("USAGE STATS")
    print("=" * 60)
    print(generator.get_usage_stats())
