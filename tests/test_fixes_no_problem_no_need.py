"""
Тесты для исправлений:
1. Интенты no_problem и no_need в INTENT_ROOTS и INTENT_PHRASES
2. Удаление дублирования паттернов objection_competitor
3. Синхронизация размеров категорий

Проблемы:
- no_problem/no_need отсутствовали в INTENT_ROOTS/INTENT_PHRASES,
  хотя использовались в hybrid.py, config.py (SALES_STATES), retriever.py
- Дублирование паттернов objection_competitor в patterns.py
- Несоответствие размеров категорий между _meta.yaml и CATEGORY_ROUTER_PROMPT
"""

import pytest
import sys
import re
import yaml
sys.path.insert(0, 'src')

from config import (
    INTENT_ROOTS,
    INTENT_PHRASES,
    SALES_STATES,
    CATEGORY_ROUTER_PROMPT,
)
from classifier import HybridClassifier
from classifier.intents import RootClassifier, LemmaClassifier, COMPILED_PRIORITY_PATTERNS


class TestNoProblemNoNeedInIntentRoots:
    """Тесты для наличия no_problem и no_need в INTENT_ROOTS"""

    def test_no_problem_exists_in_intent_roots(self):
        """no_problem должен быть в INTENT_ROOTS"""
        assert "no_problem" in INTENT_ROOTS, \
            "Intent 'no_problem' должен быть в INTENT_ROOTS"

    def test_no_need_exists_in_intent_roots(self):
        """no_need должен быть в INTENT_ROOTS"""
        assert "no_need" in INTENT_ROOTS, \
            "Intent 'no_need' должен быть в INTENT_ROOTS"

    def test_no_problem_has_roots(self):
        """no_problem должен иметь непустой список корней"""
        roots = INTENT_ROOTS.get("no_problem", [])
        assert len(roots) > 0, \
            "no_problem должен иметь корни слов для классификации"

    def test_no_need_has_roots(self):
        """no_need должен иметь непустой список корней"""
        roots = INTENT_ROOTS.get("no_need", [])
        assert len(roots) > 0, \
            "no_need должен иметь корни слов для классификации"

    def test_no_problem_roots_contain_expected_words(self):
        """no_problem должен содержать ключевые корни"""
        roots = INTENT_ROOTS.get("no_problem", [])
        expected_patterns = ["нет проблем", "все хорошо", "справляемся", "устраивает"]
        found = sum(1 for pattern in expected_patterns
                    if any(pattern in root for root in roots))
        assert found >= 2, \
            f"no_problem должен содержать минимум 2 из {expected_patterns}"

    def test_no_need_roots_contain_expected_words(self):
        """no_need должен содержать ключевые корни"""
        roots = INTENT_ROOTS.get("no_need", [])
        expected_patterns = ["не нужно", "обойдёмся", "справляемся", "не требуется"]
        found = sum(1 for pattern in expected_patterns
                    if any(pattern in root for root in roots))
        assert found >= 2, \
            f"no_need должен содержать минимум 2 из {expected_patterns}"


class TestNoProblemNoNeedInIntentPhrases:
    """Тесты для наличия no_problem и no_need в INTENT_PHRASES"""

    def test_no_problem_exists_in_intent_phrases(self):
        """no_problem должен быть в INTENT_PHRASES"""
        assert "no_problem" in INTENT_PHRASES, \
            "Intent 'no_problem' должен быть в INTENT_PHRASES"

    def test_no_need_exists_in_intent_phrases(self):
        """no_need должен быть в INTENT_PHRASES"""
        assert "no_need" in INTENT_PHRASES, \
            "Intent 'no_need' должен быть в INTENT_PHRASES"

    def test_no_problem_has_phrases(self):
        """no_problem должен иметь непустой список фраз"""
        phrases = INTENT_PHRASES.get("no_problem", [])
        assert len(phrases) > 0, \
            "no_problem должен иметь фразы для LemmaClassifier"

    def test_no_need_has_phrases(self):
        """no_need должен иметь непустой список фраз"""
        phrases = INTENT_PHRASES.get("no_need", [])
        assert len(phrases) > 0, \
            "no_need должен иметь фразы для LemmaClassifier"


class TestNoProblemNoNeedClassification:
    """Тесты для классификации no_problem и no_need"""

    def setup_method(self):
        self.classifier = HybridClassifier()
        self.root_classifier = RootClassifier()
        self.lemma_classifier = LemmaClassifier()

    def test_root_classifier_detects_no_problem(self):
        """RootClassifier должен обнаруживать no_problem"""
        test_phrases = [
            "нет у нас таких проблем",
            "у нас всё хорошо",
            "мы справляемся",
            "нас всё устраивает",
        ]
        detected = 0
        for phrase in test_phrases:
            intent, conf, _ = self.root_classifier.classify(phrase)
            if intent == "no_problem" and conf > 0.3:
                detected += 1

        assert detected >= 2, \
            f"RootClassifier должен обнаруживать no_problem минимум в 2 из {len(test_phrases)} фраз"

    def test_root_classifier_detects_no_need(self):
        """RootClassifier должен обнаруживать no_need"""
        test_phrases = [
            "нам это не нужно",
            "мы обойдёмся",
            "и так справляемся",
            "в этом нет необходимости",
            "нет необходимости в этом",
            "не требуется нам такое",
        ]
        detected = 0
        for phrase in test_phrases:
            intent, conf, _ = self.root_classifier.classify(phrase)
            if intent == "no_need" and conf > 0.3:
                detected += 1

        assert detected >= 1, \
            f"RootClassifier должен обнаруживать no_need минимум в 1 из {len(test_phrases)} фраз"

    def test_lemma_classifier_detects_no_problem(self):
        """LemmaClassifier должен обнаруживать no_problem"""
        test_phrases = [
            "нет у нас таких проблем",
            "всё хорошо с этим",
            "проблем не испытываем",
        ]
        detected = 0
        for phrase in test_phrases:
            intent, conf, _ = self.lemma_classifier.classify(phrase)
            if intent == "no_problem" and conf > 0.3:
                detected += 1

        assert detected >= 1, \
            "LemmaClassifier должен обнаруживать no_problem"

    def test_lemma_classifier_detects_no_need(self):
        """LemmaClassifier должен обнаруживать no_need"""
        test_phrases = [
            "нам это не нужно",
            "обходимся без этого",
            "нет в этом необходимости",
        ]
        detected = 0
        for phrase in test_phrases:
            intent, conf, _ = self.lemma_classifier.classify(phrase)
            if intent == "no_need" and conf > 0.3:
                detected += 1

        assert detected >= 1, \
            "LemmaClassifier должен обнаруживать no_need"


class TestNoProblemNoNeedInSalesStates:
    """Тесты для использования no_problem и no_need в SALES_STATES"""

    def test_no_problem_in_spin_problem_transitions(self):
        """no_problem должен быть в переходах spin_problem"""
        spin_problem_config = SALES_STATES.get("spin_problem", {})
        transitions = spin_problem_config.get("transitions", {})
        assert "no_problem" in transitions, \
            "no_problem должен быть в переходах состояния spin_problem"

    def test_no_problem_in_spin_implication_transitions(self):
        """no_problem должен быть в переходах spin_implication"""
        spin_implication_config = SALES_STATES.get("spin_implication", {})
        transitions = spin_implication_config.get("transitions", {})
        assert "no_problem" in transitions, \
            "no_problem должен быть в переходах состояния spin_implication"

    def test_no_need_in_spin_need_payoff_transitions(self):
        """no_need должен быть в переходах spin_need_payoff"""
        spin_need_payoff_config = SALES_STATES.get("spin_need_payoff", {})
        transitions = spin_need_payoff_config.get("transitions", {})
        assert "no_need" in transitions, \
            "no_need должен быть в переходах состояния spin_need_payoff"


class TestHybridClassifierShortAnswerContext:
    """Тесты для контекстной классификации коротких ответов с no_problem/no_need"""

    def setup_method(self):
        self.classifier = HybridClassifier()

    def test_short_no_in_problem_phase_returns_no_problem(self):
        """'Нет' в фазе problem должен возвращать no_problem"""
        context = {"spin_phase": "problem", "last_action": "spin_problem"}
        result = self.classifier.classify("нет", context)
        assert result["intent"] == "no_problem", \
            f"Ожидался no_problem, получили {result['intent']}"

    def test_short_no_in_need_payoff_phase_returns_no_need(self):
        """'Нет' в фазе need_payoff должен возвращать no_need"""
        context = {"spin_phase": "need_payoff", "last_action": "spin_need_payoff"}
        result = self.classifier.classify("нет", context)
        assert result["intent"] == "no_need", \
            f"Ожидался no_need, получили {result['intent']}"

    def test_elaborate_no_problem_detected(self):
        """Развёрнутый ответ 'нет, у нас всё хорошо' должен классифицироваться"""
        # Без контекста, но с явным указанием что проблем нет
        result = self.classifier.classify("нет, у нас всё хорошо с этим")
        # Может быть no_problem или rejection, главное не unclear
        assert result["intent"] in ["no_problem", "rejection", "agreement"], \
            f"Ожидался no_problem/rejection/agreement, получили {result['intent']}"

    def test_elaborate_no_need_detected(self):
        """Развёрнутый ответ 'нам это точно не нужно' должен классифицироваться"""
        result = self.classifier.classify("нам это точно не нужно")
        # Может быть no_need или rejection
        assert result["intent"] in ["no_need", "rejection"], \
            f"Ожидался no_need/rejection, получили {result['intent']}"


class TestObjectionCompetitorPatternsDuplication:
    """Тесты на отсутствие дублирования паттернов objection_competitor"""

    def test_no_duplicate_competitor_patterns(self):
        """Проверка отсутствия дублирующих паттернов objection_competitor"""
        competitor_patterns = []
        for pattern, intent, conf in COMPILED_PRIORITY_PATTERNS:
            if intent == "objection_competitor":
                competitor_patterns.append((pattern.pattern, conf))

        # Проверяем что нет точных дублей с разным confidence
        seen_patterns = {}
        duplicates = []
        for pattern, conf in competitor_patterns:
            if pattern in seen_patterns:
                duplicates.append((pattern, seen_patterns[pattern], conf))
            else:
                seen_patterns[pattern] = conf

        assert len(duplicates) == 0, \
            f"Найдены дублирующие паттерны: {duplicates}"

    def test_critical_competitor_patterns_have_iko(self):
        """Критические паттерны конкурентов должны включать нормализованное 'iko'"""
        critical_patterns = []
        for pattern, intent, conf in COMPILED_PRIORITY_PATTERNS:
            if intent == "objection_competitor" and conf >= 0.99:
                critical_patterns.append(pattern.pattern)

        assert len(critical_patterns) > 0, \
            "Должны быть критические паттерны objection_competitor (conf >= 0.99)"

        # Проверяем что хотя бы один паттерн содержит 'iko'
        has_iko = any("iko" in p for p in critical_patterns)
        assert has_iko, \
            "Критические паттерны должны содержать 'iko' (нормализованная форма iiko)"

    def test_competitor_patterns_match_normalized_iiko(self):
        """Паттерны должны матчить нормализованную форму 'iko' (из 'iiko')"""
        test_phrases = [
            "чем вы лучше iko",  # нормализованная форма iiko
            "чем лучше iko",
        ]
        for phrase in test_phrases:
            matched = False
            for pattern, intent, conf in COMPILED_PRIORITY_PATTERNS:
                if intent == "objection_competitor" and pattern.search(phrase):
                    matched = True
                    break
            assert matched, \
                f"Паттерны objection_competitor должны матчить: '{phrase}'"


class TestCategoryRouterPromptSync:
    """Тесты синхронизации размеров категорий между _meta.yaml и CATEGORY_ROUTER_PROMPT"""

    @pytest.fixture
    def meta_yaml(self):
        """Загружаем _meta.yaml"""
        with open('src/knowledge/data/_meta.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_category_counts_match_meta_yaml(self, meta_yaml):
        """Размеры категорий в CATEGORY_ROUTER_PROMPT должны соответствовать _meta.yaml"""
        # Извлекаем размеры категорий из _meta.yaml
        meta_categories = {}
        for cat in meta_yaml.get('stats', {}).get('categories', []):
            meta_categories[cat['name']] = cat['count']

        # Извлекаем размеры из CATEGORY_ROUTER_PROMPT
        prompt_categories = {}
        # Паттерн: "category_name (N секций)" или "category_name (N секции/секция)"
        pattern = r'^(\w+)\s+\((\d+)\s+секци[йяеи]'
        for line in CATEGORY_ROUTER_PROMPT.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                cat_name = match.group(1)
                cat_count = int(match.group(2))
                prompt_categories[cat_name] = cat_count

        # Проверяем соответствие
        mismatches = []
        for cat_name, meta_count in meta_categories.items():
            prompt_count = prompt_categories.get(cat_name)
            if prompt_count is None:
                mismatches.append(f"{cat_name}: отсутствует в CATEGORY_ROUTER_PROMPT")
            elif prompt_count != meta_count:
                mismatches.append(
                    f"{cat_name}: _meta.yaml={meta_count}, prompt={prompt_count}"
                )

        assert len(mismatches) == 0, \
            f"Несоответствия размеров категорий:\n" + "\n".join(mismatches)

    def test_all_meta_categories_in_prompt(self, meta_yaml):
        """Все категории из _meta.yaml должны быть в CATEGORY_ROUTER_PROMPT"""
        meta_categories = set()
        for cat in meta_yaml.get('stats', {}).get('categories', []):
            meta_categories.add(cat['name'])

        # Извлекаем категории из CATEGORY_ROUTER_PROMPT
        prompt_categories = set()
        pattern = r'^(\w+)\s+\(\d+\s+секци[йяеи]'
        for line in CATEGORY_ROUTER_PROMPT.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                prompt_categories.add(match.group(1))

        missing = meta_categories - prompt_categories
        assert len(missing) == 0, \
            f"Категории отсутствуют в CATEGORY_ROUTER_PROMPT: {missing}"


class TestIntentConsistency:
    """Тесты на консистентность интентов между разными местами использования"""

    def test_no_problem_used_consistently(self):
        """no_problem должен быть согласован между INTENT_ROOTS, INTENT_PHRASES и SALES_STATES"""
        # Проверяем что интент есть везде где должен
        assert "no_problem" in INTENT_ROOTS, "no_problem должен быть в INTENT_ROOTS"
        assert "no_problem" in INTENT_PHRASES, "no_problem должен быть в INTENT_PHRASES"

        # Проверяем в SALES_STATES
        used_in_states = False
        for state_name, state_config in SALES_STATES.items():
            transitions = state_config.get("transitions", {})
            if "no_problem" in transitions:
                used_in_states = True
                break

        assert used_in_states, "no_problem должен использоваться в SALES_STATES"

    def test_no_need_used_consistently(self):
        """no_need должен быть согласован между INTENT_ROOTS, INTENT_PHRASES и SALES_STATES"""
        assert "no_need" in INTENT_ROOTS, "no_need должен быть в INTENT_ROOTS"
        assert "no_need" in INTENT_PHRASES, "no_need должен быть в INTENT_PHRASES"

        # Проверяем в SALES_STATES
        used_in_states = False
        for state_name, state_config in SALES_STATES.items():
            transitions = state_config.get("transitions", {})
            if "no_need" in transitions:
                used_in_states = True
                break

        assert used_in_states, "no_need должен использоваться в SALES_STATES"
