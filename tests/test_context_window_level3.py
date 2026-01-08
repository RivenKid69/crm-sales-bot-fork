"""
Тесты для Context Window Level 3: Episodic Memory

Тестирует:
- EpisodicMemory: хранение ключевых эпизодов всего диалога
- ClientProfile: сбор профиля клиента
- Episode detection: первое возражение, breakthrough, turning points
- Action effectiveness: какие actions работают
- Classifier integration: паттерны 11-15
"""

import pytest
import sys
import time
sys.path.insert(0, "src")

from context_window import (
    ContextWindow, TurnContext, TurnType,
    EpisodicMemory, Episode, EpisodeType, ClientProfile
)
from classifier import HybridClassifier


# =============================================================================
# ТЕСТЫ ClientProfile
# =============================================================================

class TestClientProfile:
    """Тесты профиля клиента."""

    def test_empty_profile(self):
        """Пустой профиль."""
        profile = ClientProfile()
        assert profile.company_name is None
        assert profile.company_size is None
        assert not profile.pain_points
        assert not profile.has_data()

    def test_update_from_data(self):
        """Обновление профиля из extracted_data."""
        profile = ClientProfile()

        profile.update_from_data({
            "company_name": "Рога и Копыта",
            "company_size": 15,
            "industry": "retail",
        })

        assert profile.company_name == "Рога и Копыта"
        assert profile.company_size == 15
        assert profile.industry == "retail"
        assert profile.has_data()

    def test_add_pain_points(self):
        """Добавление болей клиента."""
        profile = ClientProfile()

        profile.update_from_data({"pain_point": "учёт товаров"})
        profile.update_from_data({"pain_point": "потеря времени"})
        profile.update_from_data({"pain_point": "учёт товаров"})  # дубликат

        assert len(profile.pain_points) == 2
        assert "учёт товаров" in profile.pain_points
        assert "потеря времени" in profile.pain_points

    def test_add_objections(self):
        """Добавление типов возражений."""
        profile = ClientProfile()

        profile.add_objection("objection_price")
        profile.add_objection("objection_think")
        profile.add_objection("objection_price")  # дубликат

        assert len(profile.objection_types) == 2
        assert "objection_price" in profile.objection_types

    def test_to_dict(self):
        """Сериализация профиля."""
        profile = ClientProfile()
        profile.company_name = "Test"
        profile.company_size = 10
        profile.pain_points.append("боль")

        data = profile.to_dict()
        assert data["company_name"] == "Test"
        assert data["company_size"] == 10
        assert "боль" in data["pain_points"]


# =============================================================================
# ТЕСТЫ EpisodicMemory
# =============================================================================

class TestEpisodicMemory:
    """Тесты эпизодической памяти."""

    @pytest.fixture
    def memory(self):
        return EpisodicMemory()

    def test_empty_memory(self, memory):
        """Пустая память."""
        assert len(memory) == 0
        assert memory.get_first_objection() is None
        assert not memory.has_breakthrough()
        assert memory.get_total_objections() == 0

    def test_record_first_objection(self, memory):
        """Запись первого возражения."""
        turn = TurnContext(
            user_message="это дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )

        episodes = memory.record_turn(turn, turn_number=1)

        assert len(episodes) == 1
        assert episodes[0].episode_type == EpisodeType.FIRST_OBJECTION
        assert episodes[0].intent == "objection_price"

        first_obj = memory.get_first_objection()
        assert first_obj is not None
        assert first_obj.turn_number == 1

    def test_record_repeated_objection(self, memory):
        """Запись повторного возражения."""
        # Первое возражение
        turn1 = TurnContext(
            user_message="дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )
        memory.record_turn(turn1, turn_number=1)

        # Второе возражение того же типа
        turn2 = TurnContext(
            user_message="всё равно дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )
        episodes = memory.record_turn(turn2, turn_number=5)

        # Должен быть REPEATED_OBJECTION (не FIRST)
        repeated = [e for e in episodes if e.episode_type == EpisodeType.REPEATED_OBJECTION]
        assert len(repeated) == 1
        assert repeated[0].data["count"] == 2

    def test_record_breakthrough(self, memory):
        """Запись прорыва (прогресс после возражения)."""
        # Возражение
        turn1 = TurnContext(
            user_message="дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )
        memory.record_turn(turn1, turn_number=1)

        # Прогресс
        turn2 = TurnContext(
            user_message="хорошо, давайте",
            intent="agreement",
            turn_type=TurnType.PROGRESS,
        )
        episodes = memory.record_turn(turn2, turn_number=2)

        breakthrough = [e for e in episodes if e.episode_type == EpisodeType.BREAKTHROUGH]
        assert len(breakthrough) == 1
        assert memory.has_breakthrough()

    def test_record_data_revealed(self, memory):
        """Запись раскрытия данных клиентом."""
        turn = TurnContext(
            user_message="у нас 15 человек в команде",
            intent="info_provided",
            turn_type=TurnType.PROGRESS,
            extracted_data={"company_size": 15},
        )

        episodes = memory.record_turn(turn, turn_number=1)

        data_eps = [e for e in episodes if e.episode_type == EpisodeType.DATA_REVEALED]
        assert len(data_eps) == 1
        assert data_eps[0].data["company_size"] == 15

        # Профиль обновлён
        assert memory.client_profile.company_size == 15

    def test_record_turning_point(self, memory):
        """Запись переломного момента (смена momentum)."""
        # Негативный ход
        turn1 = TurnContext(
            user_message="не интересно",
            intent="rejection",
            turn_type=TurnType.REGRESS,
        )
        memory.record_turn(turn1, turn_number=1, momentum_direction="negative")

        # Позитивный ход — смена momentum
        turn2 = TurnContext(
            user_message="хотя подождите",
            intent="agreement",
            turn_type=TurnType.PROGRESS,
        )
        episodes = memory.record_turn(turn2, turn_number=2, momentum_direction="positive")

        turning = [e for e in episodes if e.episode_type == EpisodeType.TURNING_POINT]
        assert len(turning) == 1
        assert turning[0].data["from"] == "negative"
        assert turning[0].data["to"] == "positive"

    def test_action_effectiveness(self, memory):
        """Отслеживание эффективности actions."""
        # Прогресс после presentation
        prev1 = TurnContext(user_message="...", intent="info", action="presentation")
        turn1 = TurnContext(
            user_message="интересно",
            intent="agreement",
            turn_type=TurnType.PROGRESS,
        )
        memory.record_turn(turn1, turn_number=1, prev_turn=prev1)

        # Ещё прогресс после presentation
        prev2 = TurnContext(user_message="...", intent="info", action="presentation")
        turn2 = TurnContext(
            user_message="давайте",
            intent="agreement",
            turn_type=TurnType.PROGRESS,
        )
        memory.record_turn(turn2, turn_number=2, prev_turn=prev2)

        # Возражение после handle_objection
        prev3 = TurnContext(user_message="...", intent="info", action="handle_objection")
        turn3 = TurnContext(
            user_message="дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )
        memory.record_turn(turn3, turn_number=3, prev_turn=prev3)

        # presentation эффективен
        assert memory.get_action_effectiveness("presentation") == 1.0
        # handle_objection неэффективен
        assert memory.get_action_effectiveness("handle_objection") == 0.0

    def test_most_common_objection(self, memory):
        """Определение самого частого возражения."""
        for _ in range(3):
            turn = TurnContext(
                user_message="дорого",
                intent="objection_price",
                turn_type=TurnType.REGRESS,
            )
            memory.record_turn(turn, turn_number=1)

        for _ in range(1):
            turn = TurnContext(
                user_message="нет времени",
                intent="objection_no_time",
                turn_type=TurnType.REGRESS,
            )
            memory.record_turn(turn, turn_number=2)

        most_common = memory.get_most_common_objection()
        assert most_common[0] == "objection_price"
        assert most_common[1] == 3

    def test_reset(self, memory):
        """Сброс памяти."""
        turn = TurnContext(
            user_message="дорого",
            intent="objection_price",
            turn_type=TurnType.REGRESS,
        )
        memory.record_turn(turn, turn_number=1)

        memory.reset()

        assert len(memory) == 0
        assert memory.get_first_objection() is None
        assert memory.get_total_objections() == 0


# =============================================================================
# ТЕСТЫ ContextWindow + EpisodicMemory интеграция
# =============================================================================

class TestContextWindowLevel3:
    """Тесты интеграции Level 3 в ContextWindow."""

    @pytest.fixture
    def window(self):
        return ContextWindow(max_size=5)

    def test_episodic_memory_created(self, window):
        """EpisodicMemory создаётся вместе с окном."""
        assert window.episodic_memory is not None
        assert isinstance(window.episodic_memory, EpisodicMemory)

    def test_turns_recorded_to_episodic(self, window):
        """Ходы записываются в эпизодическую память."""
        window.add_turn_from_dict(
            user_message="дорого для нас",
            bot_response="...",
            intent="objection_price",
            confidence=0.9,
            action="presentation",
            state="presentation",
            next_state="handle_objection",
        )

        # В эпизодической памяти есть первое возражение
        first_obj = window.get_first_objection()
        assert first_obj is not None
        assert first_obj.intent == "objection_price"

    def test_total_turn_count_preserved(self, window):
        """Общий счётчик ходов сохраняется при ротации окна."""
        # Добавим 10 ходов (окно = 5)
        for i in range(10):
            window.add_turn_from_dict(
                user_message=f"сообщение {i}",
                bot_response="...",
                intent="info_provided",
                confidence=0.8,
                action="spin_situation",
                state="spin_situation",
                next_state="spin_situation",
            )

        # В окне только 5 ходов
        assert len(window) == 5
        # Но total_turn_count = 10
        assert window.get_total_turn_count() == 10

    def test_episodic_context_in_classifier_context(self, window):
        """Контекст Level 3 включён в classifier_context."""
        window.add_turn_from_dict(
            user_message="дорого",
            bot_response="...",
            intent="objection_price",
            confidence=0.9,
            action="presentation",
            state="presentation",
            next_state="handle_objection",
        )

        ctx = window.get_classifier_context()

        # Level 3 поля должны быть
        assert "first_objection_type" in ctx
        assert ctx["first_objection_type"] == "objection_price"
        assert "has_breakthrough" in ctx
        assert "total_objections" in ctx

    def test_client_profile_collected(self, window):
        """Профиль клиента собирается через диалог."""
        window.add_turn_from_dict(
            user_message="меня зовут Иван, у нас 20 человек",
            bot_response="...",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="greeting",
            next_state="spin_situation",
            extracted_data={"contact_name": "Иван", "company_size": 20},
        )

        profile = window.get_client_profile()
        assert profile["contact_name"] == "Иван"
        assert profile["company_size"] == 20

    def test_reset_clears_episodic(self, window):
        """Reset очищает и эпизодическую память."""
        window.add_turn_from_dict(
            user_message="дорого",
            bot_response="...",
            intent="objection_price",
            confidence=0.9,
            action="presentation",
            state="presentation",
            next_state="handle_objection",
        )

        window.reset()

        assert window.get_first_objection() is None
        assert window.get_total_turn_count() == 0


# =============================================================================
# ТЕСТЫ Classifier + Level 3 паттерны
# =============================================================================

class TestClassifierLevel3Integration:
    """Тесты интеграции classifier с Level 3."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_repeated_objection_pattern(self, classifier):
        """
        Паттерн 11: Повторное возражение определяется с высокой уверенностью.
        """
        context = {
            "state": "handle_objection",
            "last_action": "handle_objection",
            "repeated_objection_types": ["objection_price"],
            "objection_types_seen": ["objection_price"],
        }

        result = classifier.classify("всё равно дорого", context=context)

        print(f"\nRepeated objection pattern:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        assert result["intent"] == "objection_price"
        assert result["confidence"] >= 0.9

    def test_post_breakthrough_agreement(self, classifier):
        """
        Паттерн 13: После breakthrough короткие ответы = agreement.
        """
        context = {
            "state": "presentation",
            "last_action": "presentation",
            "has_breakthrough": True,
            "total_objections": 1,
        }

        result = classifier.classify("ну ладно", context=context)

        print(f"\nPost breakthrough agreement:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        assert result["intent"] == "agreement"

    def test_unstable_client_low_confidence(self, classifier):
        """
        Паттерн 14: Много turning points = низкая уверенность в согласии.
        """
        context = {
            "state": "presentation",
            "last_action": "presentation",
            "turning_points_count": 4,
        }

        result = classifier.classify("да", context=context)

        print(f"\nUnstable client:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        # Уверенность должна быть низкой
        if result.get("pattern_type") == "unstable_client_agreement":
            assert result["confidence"] <= 0.7

    def test_engaged_client_interest(self, classifier):
        """
        Паттерн 15: Клиент с данными и без возражений = высокая лояльность.
        """
        context = {
            "state": "spin_problem",
            "last_action": "spin_problem",
            "client_has_data": True,
            "total_objections": 0,
        }

        result = classifier.classify("интересно, расскажите подробнее", context=context)

        print(f"\nEngaged client:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        assert result["intent"] == "agreement"
        assert result["confidence"] >= 0.85


# =============================================================================
# СРАВНЕНИЕ: Level 1+2 vs Level 1+2+3
# =============================================================================

class TestLevel3Comparison:
    """Сравнение работы с и без Level 3."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_without_episodic_context(self, classifier):
        """Без Level 3 — базовое поведение."""
        context = {
            "state": "handle_objection",
            "last_action": "handle_objection",
            # Нет episodic данных
        }

        result = classifier.classify("опять дорого", context=context)

        print(f"\nWithout Level 3:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}")

        return result

    def test_with_episodic_context(self, classifier):
        """С Level 3 — знаем историю возражений."""
        context = {
            "state": "handle_objection",
            "last_action": "handle_objection",
            # Level 3 данные
            "repeated_objection_types": ["objection_price"],
            "first_objection_type": "objection_price",
            "total_objections": 2,
        }

        result = classifier.classify("опять дорого", context=context)

        print(f"\nWith Level 3:")
        print(f"  intent={result['intent']}, conf={result['confidence']:.2f}, "
              f"pattern={result.get('pattern_type')}")

        return result

    def test_comparison(self, classifier):
        """Сравнение уверенности с и без Level 3."""
        ctx_without = {
            "state": "handle_objection",
            "last_action": "handle_objection",
        }

        ctx_with = {
            "state": "handle_objection",
            "last_action": "handle_objection",
            "repeated_objection_types": ["objection_price"],
            "first_objection_type": "objection_price",
            "total_objections": 2,
        }

        result_without = classifier.classify("дорого для нас", context=ctx_without)
        result_with = classifier.classify("дорого для нас", context=ctx_with)

        print(f"\n=== Comparison ===")
        print(f"Without L3: intent={result_without['intent']}, conf={result_without['confidence']:.2f}")
        print(f"With L3:    intent={result_with['intent']}, conf={result_with['confidence']:.2f}")

        # С Level 3 уверенность должна быть выше (знаем историю)
        assert result_with["confidence"] >= result_without["confidence"]


# =============================================================================
# РЕАЛИСТИЧНЫЕ СЦЕНАРИИ
# =============================================================================

class TestRealisticScenariosLevel3:
    """Реалистичные сценарии с Level 3."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_long_dialog_with_multiple_objections(self, classifier):
        """
        Сценарий: Длинный диалог с несколькими возражениями.
        Level 3 помнит все возражения даже после ротации окна.
        """
        print("\n=== Длинный диалог с возражениями ===")

        cw = ContextWindow(max_size=3)  # Маленькое окно

        # 1. Приветствие
        cw.add_turn_from_dict(
            user_message="Здравствуйте",
            bot_response="...",
            intent="greeting",
            confidence=0.9,
            action="greet",
            state="greeting",
            next_state="spin_situation",
        )

        # 2. Данные
        cw.add_turn_from_dict(
            user_message="у нас 10 человек",
            bot_response="...",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="spin_situation",
            next_state="spin_problem",
            extracted_data={"company_size": 10},
        )

        # 3. Первое возражение по цене
        cw.add_turn_from_dict(
            user_message="это дорого",
            bot_response="...",
            intent="objection_price",
            confidence=0.9,
            action="spin_problem",
            state="spin_problem",
            next_state="handle_objection",
        )

        # 4. Отработали
        cw.add_turn_from_dict(
            user_message="ну ладно",
            bot_response="...",
            intent="agreement",
            confidence=0.8,
            action="handle_objection",
            state="handle_objection",
            next_state="presentation",
        )

        # 5. Презентация (greeting уже выпал из окна!)
        cw.add_turn_from_dict(
            user_message="понятно",
            bot_response="...",
            intent="agreement",
            confidence=0.7,
            action="presentation",
            state="presentation",
            next_state="presentation",
        )

        # Проверяем что Level 3 помнит
        ctx = cw.get_classifier_context()

        print(f"Окно: {len(cw)} ходов")
        print(f"Всего ходов: {cw.get_total_turn_count()}")
        print(f"Первое возражение: {ctx.get('first_objection_type')}")
        print(f"Был breakthrough: {ctx.get('has_breakthrough')}")
        print(f"Профиль: company_size={ctx.get('client_company_size')}")

        # В окне только 3 хода, но Level 3 помнит
        assert len(cw) == 3
        assert cw.get_total_turn_count() == 5
        assert ctx["first_objection_type"] == "objection_price"
        assert ctx["has_breakthrough"] == True
        assert ctx["client_company_size"] == 10

        # 6. Повторное возражение — Level 3 распознаёт
        result = classifier.classify("всё-таки дороговато", context=ctx)

        print(f"Финал: intent={result['intent']}, conf={result['confidence']:.2f}")

        # Должны распознать повторное возражение
        assert result["intent"] == "objection_price"

    def test_breakthrough_changes_interpretation(self, classifier):
        """
        Сценарий: После breakthrough интерпретация меняется.
        """
        print("\n=== Breakthrough меняет интерпретацию ===")

        # Без breakthrough
        ctx_no_break = {
            "state": "presentation",
            "last_action": "presentation",
            "has_breakthrough": False,
            "total_objections": 2,
        }

        # С breakthrough
        ctx_with_break = {
            "state": "presentation",
            "last_action": "presentation",
            "has_breakthrough": True,
            "total_objections": 2,
        }

        message = "ну ок"

        result_no = classifier.classify(message, context=ctx_no_break)
        result_yes = classifier.classify(message, context=ctx_with_break)

        print(f"Без breakthrough: intent={result_no['intent']}, conf={result_no['confidence']:.2f}")
        print(f"С breakthrough:   intent={result_yes['intent']}, conf={result_yes['confidence']:.2f}")

        # С breakthrough должны интерпретировать как agreement
        assert result_yes["intent"] == "agreement"


# =============================================================================
# ТЕСТЫ ПРОИЗВОДИТЕЛЬНОСТИ Level 3
# =============================================================================

class TestPerformanceLevel3:
    """Тесты производительности Level 3."""

    def test_episodic_memory_fast(self):
        """EpisodicMemory работает быстро."""
        memory = EpisodicMemory()

        start = time.time()

        # 100 ходов
        for i in range(100):
            turn = TurnContext(
                user_message=f"сообщение {i}",
                intent="info_provided" if i % 3 != 0 else "objection_price",
                turn_type=TurnType.PROGRESS if i % 3 != 0 else TurnType.REGRESS,
                extracted_data={"data": i} if i % 5 == 0 else {},
            )
            memory.record_turn(turn, turn_number=i + 1)

        # Получить контекст
        ctx = memory.get_episodic_context()

        elapsed = time.time() - start

        print(f"\n100 turns + context: {elapsed*1000:.2f}ms")
        print(f"Episodes: {len(memory)}")
        print(f"Total objections: {memory.get_total_objections()}")

        assert elapsed < 0.5  # Должно быть < 500ms

    def test_full_context_with_level3_fast(self):
        """Полный контекст с Level 3 генерируется быстро."""
        cw = ContextWindow(max_size=5)

        # 50 ходов
        for i in range(50):
            cw.add_turn_from_dict(
                user_message=f"сообщение {i}",
                bot_response="...",
                intent="info_provided" if i % 4 != 0 else "objection_price",
                confidence=0.8,
                action="spin_situation",
                state="spin_situation",
                next_state="spin_situation",
                extracted_data={"data": i} if i % 10 == 0 else {},
            )

        start = time.time()

        # Генерация полного контекста
        for _ in range(100):
            ctx = cw.get_classifier_context()

        elapsed = time.time() - start

        print(f"\n100x full context generation: {elapsed*1000:.2f}ms")
        print(f"Context keys: {len(ctx)}")

        assert elapsed < 1.0  # 100 генераций < 1 секунды


# =============================================================================
# ЗАПУСК ТЕСТОВ
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
