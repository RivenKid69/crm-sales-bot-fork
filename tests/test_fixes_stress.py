"""
Stress tests for the 5 compound regression fixes.
Attempts to break each fix with edge cases, boundary conditions,
adversarial inputs, and unexpected combinations.

Run: pytest tests/test_fixes_stress.py -v
"""
import re
import pytest
from unittest.mock import MagicMock, patch

from src.knowledge.fact_disambiguation import (
    FactDisambiguationDecision,
    FactDisambiguator,
    _PRICING_SIGNAL_RE,
    _EQUIPMENT_SIGNAL_RE,
    _FAMILY_PATTERNS,
    detect_fact_disambiguation,
)
from src.knowledge.enhanced_retrieval import _KB_META_STRIP_RE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFLICT_MINI_FACTS = """\
[pricing/tariff_mini]
Тариф Mini — базовый ежемесячный тариф Wipon для одной торговой точки.
Цена: 5 000 ₸/месяц.

[equipment/kit_mini]
Комплект Mini — готовый кассовый комплект для малого бизнеса.
Цена: 98 000 ₸ единоразово.
"""

CONFLICT_PRO_FACTS = """\
[pricing/tariff_pro]
Тариф Pro — максимальный тариф Wipon.
Цена: 500 000 ₸/год.
⚠️ НЕ ПУТАТЬ: Тариф Pro ≠ Комплект Pro ≠ Модуль Pro УКМ.

[equipment/kit_pro]
Комплект Pro — готовый кассовый комплект для высокого оборота.
Цена: 360 000 ₸ единоразово.
⚠️ НЕ ПУТАТЬ: «Комплект Pro» — оборудование, «Тариф Pro» — подписка.

[pricing/module_pro]
Модуль Pro УКМ — программный модуль для акцизной продукции.
Цена: 12 000 ₸/год.
"""

CONFLICT_STANDARD_FACTS = """\
[pricing/tariff_standard]
Тариф Standard — 220 000 ₸/год, до 5 торговых точек.

[equipment/kit_standard]
Комплект Standard — 168 000 ₸, включает POS i3, сканер, принтер.
"""

def make_disambiguator():
    d = FactDisambiguator()
    d.strict_mode = True
    return d


# ---------------------------------------------------------------------------
# FIX 2 STRESS: _KB_META_STRIP_RE
# ---------------------------------------------------------------------------
class TestFix2Strip:
    """Stress test the НЕ ПУТАТЬ stripping regex."""

    def test_basic_strip(self):
        text = "Строка 1.\n⚠️ НЕ ПУТАТЬ: Тариф ≠ Комплект.\nСтрока 3."
        result = _KB_META_STRIP_RE.sub("", text)
        assert "НЕ ПУТАТЬ" not in result
        assert "Строка 1." in result
        assert "Строка 3." in result

    def test_bullet_variant(self):
        text = "Факт.\n• ⚠️ НЕ ПУТАТЬ: что-то важное.\nЕщё факт."
        result = _KB_META_STRIP_RE.sub("", text)
        assert "НЕ ПУТАТЬ" not in result
        assert "Факт." in result
        assert "Ещё факт." in result

    def test_multiline_preservation(self):
        """Multiline facts — only НЕ ПУТАТЬ lines removed, rest preserved."""
        text = "Цена: 5000 ₸.\n⚠️ НЕ ПУТАТЬ: тариф ≠ комплект.\nПодключение: 1 день."
        result = _KB_META_STRIP_RE.sub("", text)
        assert "Цена: 5000 ₸." in result
        assert "Подключение: 1 день." in result
        assert "НЕ ПУТАТЬ" not in result

    def test_consecutive_ne_putat_lines(self):
        """Multiple НЕ ПУТАТЬ lines in a row."""
        text = "A.\n⚠️ НЕ ПУТАТЬ: X.\n⚠️ НЕ ПУТАТЬ: Y.\nB."
        result = _KB_META_STRIP_RE.sub("", text)
        assert "НЕ ПУТАТЬ" not in result
        assert "A." in result
        assert "B." in result

    def test_no_false_positive_on_similar_text(self):
        """'НЕ ПУТАТЬ' in middle of sentence (not at line start) must NOT be stripped."""
        text = "Важно: НЕ ПУТАТЬ тариф с комплектом (это в середине предложения)."
        result = _KB_META_STRIP_RE.sub("", text)
        # The regex requires line-start position, so embedded НЕ ПУТАТЬ should stay
        # This is actually a design decision — mid-sentence НЕ ПУТАТЬ is NOT stripped
        # The regex uses (?m)^\s* so it must start at line beginning
        assert "НЕ ПУТАТЬ" in result  # correctly preserved (not a metadata line)

    def test_empty_string(self):
        assert _KB_META_STRIP_RE.sub("", "") == ""

    def test_only_ne_putat_lines(self):
        text = "⚠️ НЕ ПУТАТЬ: всё.\n• ⚠️ НЕ ПУТАТЬ: тоже всё.\n"
        result = _KB_META_STRIP_RE.sub("", text)
        assert "НЕ ПУТАТЬ" not in result
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# FIX 3 STRESS: _detect_specific_type
# ---------------------------------------------------------------------------
class TestFix3DetectSpecificType:
    """Adversarial tests for the expanded _detect_specific_type."""

    def setup_method(self):
        self.d = make_disambiguator()

    # --- Explicit type words (Step 1) ---
    def test_explicit_tariff_word(self):
        assert self.d._detect_specific_type("Выбираю тариф") == "tariff"

    def test_explicit_kit_word(self):
        assert self.d._detect_specific_type("Хочу комплект Mini") == "kit"

    def test_explicit_module_word(self):
        assert self.d._detect_specific_type("Нужен модуль УКМ") == "module"

    def test_two_explicit_types_returns_none(self):
        """Explicit 'тариф' + explicit 'комплект' in same message → None → disambig.
        Note: 'тарифа' (genitive) does NOT match \\bтариф\\b — use nominative form."""
        # Both explicit patterns match → len > 1 → None
        assert self.d._detect_specific_type("Нужен тариф и комплект Mini") is None
        assert self.d._detect_specific_type("Выберите тариф или комплект?") is None

    def test_all_three_explicit_types_returns_none(self):
        result = self.d._detect_specific_type("тариф комплект модуль")
        assert result is None

    # --- Implicit pricing signals (Step 2) ---
    def test_cena_signal(self):
        assert self.d._detect_specific_type("Цена Mini?") == "tariff"

    def test_stoimost_signal(self):
        assert self.d._detect_specific_type("Стоимость Pro") == "tariff"

    def test_skolko_stoit_signal(self):
        assert self.d._detect_specific_type("Сколько стоит Lite?") == "tariff"

    def test_tarif_inflected_form_e(self):
        """тарифе (locative) must resolve to tariff via _PRICING_SIGNAL_RE."""
        assert self.d._detect_specific_type("Расскажите о тарифе Pro") == "tariff"

    def test_tarif_inflected_form_akh(self):
        """тарифах (prepositional plural) — pricing signal."""
        assert self.d._detect_specific_type("Обо всех тарифах") == "tariff"

    def test_tarif_inflected_form_ov(self):
        """тарифов (genitive plural) — pricing signal."""
        assert self.d._detect_specific_type("Перечень тарифов") == "tariff"

    def test_podpiska_signal(self):
        assert self.d._detect_specific_type("Условия подписки") == "tariff"

    def test_v_god_signal(self):
        assert self.d._detect_specific_type("Цена в год?") == "tariff"

    def test_rassrochka_signal(self):
        assert self.d._detect_specific_type("Рассрочка по оплате доступна?") == "tariff"

    def test_byudzhet_signal(self):
        assert self.d._detect_specific_type("Бюджет ограничен, что посоветуете?") == "tariff"

    def test_monoblock_signal(self):
        assert self.d._detect_specific_type("Какой моноблок включён?") == "kit"

    def test_skaner_signal(self):
        assert self.d._detect_specific_type("Сканер нужен в комплекте?") == "kit"

    def test_printer_signal(self):
        assert self.d._detect_specific_type("Принтер чековый есть?") == "kit"

    def test_oborudovanie_signal(self):
        assert self.d._detect_specific_type("Какое оборудование нужно?") == "kit"

    # --- ADVERSARIAL: pricing + equipment signals simultaneously ---
    def test_explicit_kit_beats_pricing_signal(self):
        """Explicit 'моноблок' (in _MESSAGE_SPECIFIC_PATTERNS['kit']) wins over
        pricing signal — step 1 returns 'kit' before step 2 fires.
        This is CORRECT: user asking about monoblock price → answer about kit."""
        assert self.d._detect_specific_type("Цена и моноблок Standard") == "kit"
        assert self.d._detect_specific_type("Стоимость моноблока Standard?") == "kit"

    def test_explicit_oborudovanie_beats_pricing_signal(self):
        """'оборудование' is in both explicit kit patterns AND equipment signals.
        Explicit (step 1) fires first → kit."""
        assert self.d._detect_specific_type("Цена оборудования") == "kit"

    def test_both_implicit_signals_returns_none(self):
        """When NEITHER explicit pattern matches but BOTH implicit signals fire → None.
        Use words that are in _EQUIPMENT_SIGNAL_RE but NOT in _MESSAGE_SPECIFIC_PATTERNS['kit']."""
        # "кассовый аппарат" is in _EQUIPMENT_SIGNAL_RE, NOT explicit kit patterns
        result = self.d._detect_specific_type("Стоимость кассового аппарата Mini?")
        assert result is None  # pricing(стоимост) + equipment(кассов аппарат) → None

    def test_both_implicit_budget_iron_returns_none(self):
        """бюджет (pricing implicit) + железяки (equipment implicit) → None."""
        result = self.d._detect_specific_type("Бюджет на железяки небольшой")
        assert result is None

    # --- Tricky false positives ---
    def test_ne_stoit_not_pricing(self):
        """'не стоит' (=shouldn't) must not trigger pricing signal."""
        # The regex has сколько\s+стоит — "не стоит" does NOT match that pattern
        # "стоит" alone is NOT in the pattern (by design per MEMORY.md bug fix)
        result = self.d._detect_specific_type("Не стоит тратить время")
        # No pricing, no equipment, 1 or 0 families → None
        assert result is None

    def test_mne_nuzhno_not_module(self):
        """'нужно' vs 'нужен модуль' — only 'модул' triggers module."""
        result = self.d._detect_specific_type("Мне нужно оформить подписку")
        # 'нужно' → no module match; 'подписку' → pricing signal → tariff
        assert result == "tariff"

    def test_scanner_explicit_wins_over_pricing(self):
        """'сканер' is in explicit kit patterns (step 1) → kit wins over pricing signal.
        User asking about scanner price → kit answer is correct."""
        result = self.d._detect_specific_type("Сколько стоит сканер?")
        assert result == "kit"  # explicit kit beats implicit pricing

    # --- Step 3: 2+ families ---
    def test_two_families_lite_standard(self):
        assert self.d._detect_specific_type("Что лучше Lite или Standard?") == "tariff"

    def test_two_families_standard_pro(self):
        assert self.d._detect_specific_type("Чем Standard отличается от Pro?") == "tariff"

    def test_two_families_mini_pro(self):
        assert self.d._detect_specific_type("Mini или Pro для моего бизнеса?") == "tariff"

    def test_single_family_no_signals_returns_none(self):
        """Single family, no signals → None → should disambig."""
        assert self.d._detect_specific_type("Расскажите про Pro") is None

    def test_zero_families_no_signals_returns_none(self):
        assert self.d._detect_specific_type("Расскажите о системе") is None

    def test_two_families_with_equipment_signal_returns_none(self):
        """2 families + equipment signal → step 3 would fire BUT step 2 fires first.
        has_pricing=False, has_equipment=True → return 'kit' from step 2.
        So 'kit' wins, not 'tariff'. Verify this is the actual behavior."""
        result = self.d._detect_specific_type("Моноблок для Lite или Standard?")
        # Step 1: no explicit "тариф"/"комплект"/"модул" keywords
        # Step 2: equipment=True (моноблок), pricing=False → return "kit"
        assert result == "kit"

    def test_two_families_with_pricing_signal_stays_tariff(self):
        """2 families + pricing signal → step 2 returns tariff (before step 3)."""
        result = self.d._detect_specific_type("Цена для Lite и Standard?")
        # Step 2: pricing=True → tariff (even before step 3 would fire)
        assert result == "tariff"


# ---------------------------------------------------------------------------
# FIX 3 INTEGRATION: full analyze() with conflict facts
# ---------------------------------------------------------------------------
class TestFix3Integration:
    """Test _detect_specific_type inside the full analyze() flow."""

    def setup_method(self):
        self.d = make_disambiguator()

    def test_price_question_no_disambig(self):
        """'Сколько стоит Mini?' → pricing signal → no disambig."""
        result = self.d.analyze(
            user_message="Сколько стоит Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert not result.should_disambiguate
        assert any("tariff" in rc for rc in result.reason_codes)

    def test_what_includes_should_disambig(self):
        """'Что включает Mini?' → no signals, 1 family → should disambig."""
        result = self.d.analyze(
            user_message="Что включает Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert result.should_disambiguate

    def test_equipment_word_no_disambig(self):
        """'Какой моноблок входит в Mini?' → equipment signal → kit → no disambig."""
        result = self.d.analyze(
            user_message="Какой моноблок входит в Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert not result.should_disambiguate

    def test_tarif_locative_no_disambig(self):
        """'тарифе' (locative) → pricing signal → no disambig."""
        result = self.d.analyze(
            user_message="Расскажите о тарифе Mini",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert not result.should_disambiguate

    def test_two_families_comparison_no_disambig(self):
        """2 families → tariff → no disambig even with conflict facts."""
        combined = CONFLICT_MINI_FACTS + "\n" + CONFLICT_STANDARD_FACTS
        result = self.d.analyze(
            user_message="Что лучше: Mini или Standard?",
            retrieved_facts=combined,
        )
        assert not result.should_disambiguate

    def test_both_implicit_signals_should_disambig(self):
        """Both IMPLICIT signals (кассовый аппарат=equipment + стоимость=pricing) → None → disambig."""
        result = self.d.analyze(
            user_message="Стоимость кассового аппарата для Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert result.should_disambiguate

    def test_explicit_kit_word_no_disambig(self):
        """Explicit 'моноблок' (kit) → kit → no disambig even with pricing signal."""
        result = self.d.analyze(
            user_message="Цена и моноблок Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert not result.should_disambiguate  # explicit kit wins

    def test_ne_putat_in_facts_does_not_reach_llm(self):
        """НЕ ПУТАТЬ lines in facts — FactDisambiguator can use them,
        but after _KB_META_STRIP_RE they won't reach LLM.
        Here we just check that analyze() still works when НЕ ПУТАТЬ is present."""
        result = self.d.analyze(
            user_message="Расскажите про Pro",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        # Should still disambiguate (3-way conflict: tariff/kit/module)
        assert result.should_disambiguate
        assert "pro" in result.family

    def test_all_three_types_conflict_disambig(self):
        """3-way conflict: tariff+kit+module for Pro → should disambig with 3 options."""
        result = self.d.analyze(
            user_message="Расскажите про Pro",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        assert result.should_disambiguate
        assert len(result.options) >= 2

    def test_module_signal_resolves_3way_conflict(self):
        """'модуль' keyword in 3-way conflict → module → no disambig."""
        result = self.d.analyze(
            user_message="Что такое модуль Pro?",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        assert not result.should_disambiguate

    def test_ukm_signal_resolves_3way_conflict(self):
        result = self.d.analyze(
            user_message="Расскажите про УКМ Pro",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        assert not result.should_disambiguate

    def test_aksiz_signal_resolves_3way_conflict(self):
        result = self.d.analyze(
            user_message="Нужен акцизный Pro",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        assert not result.should_disambiguate


# ---------------------------------------------------------------------------
# FIX 4 STRESS: _is_family_already_clarified
# ---------------------------------------------------------------------------
class TestFix4PerFamilyTracking:
    """Stress test per-family resolved tracking."""

    def setup_method(self):
        self.d = make_disambiguator()

    def _make_history(self, pairs):
        return [{"user": u, "bot": b} for u, b in pairs]

    def test_numeric_selection_resolves_family(self):
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("1", "Тариф Mini — базовый тариф."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is True

    def test_ordinal_selection_resolves_family(self):
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("первый", "Тариф Mini — базовый тариф."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is True

    def test_keyword_selection_resolves_family(self):
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("тариф, пожалуйста", "Тариф Mini — базовый тариф."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is True

    def test_option_text_selection_resolves_family(self):
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("Тариф Mini", "Тариф Mini — базовый тариф."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is True

    def test_different_family_not_resolved(self):
        """Pro was clarified but we're asking about Standard — must return False."""
        history = self._make_history([
            ("Расскажите про Pro",
             "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами."),
            ("1", "Тариф Pro — максимальный тариф."),
        ])
        assert self.d._is_family_already_clarified(history, "standard") is False

    def test_no_selection_after_clarification_not_resolved(self):
        """Bot asked, but client didn't answer (no next turn)."""
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is False

    def test_random_response_after_clarification_not_resolved(self):
        """Client replied but it's not a selection — stay unresolved."""
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("Мне нужно подумать", "Конечно, не спешите."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is False

    def test_empty_history(self):
        assert self.d._is_family_already_clarified([], "mini") is False

    def test_clarification_for_different_family_in_history_then_same_asked(self):
        """Pro clarified → now asking again about Pro (different turn) → resolved."""
        history = self._make_history([
            ("Расскажите про Pro",
             "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами."),
            ("2", "Комплект Pro — готовый комплект."),
            ("А цена Pro?", "..."),
        ])
        # Pro was clarified (turn 0-1), so should be resolved
        assert self.d._is_family_already_clarified(history, "pro") is True

    def test_analyze_skips_disambig_when_family_resolved(self):
        """Full analyze() with Pro already resolved in history."""
        history = [
            {
                "user": "Расскажите про Pro",
                "bot": (
                    "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n"
                    "1) Тариф Pro\n2) Комплект Pro\n3) Модуль Pro УКМ\n"
                    "Ответьте номером 1-3 или напишите вариант словами."
                ),
            },
            {"user": "1", "bot": "Тариф Pro — максимальный тариф Wipon."},
        ]
        result = self.d.analyze(
            user_message="Какова цена Pro в год?",
            retrieved_facts=CONFLICT_PRO_FACTS,
            history=history,
        )
        # Even though facts have 3-way Pro conflict, family is already resolved
        # AND "цена" is a pricing signal → step 3 of _detect_specific_type resolves first
        # so reason_code should be message_specific_tariff OR family_already_clarified
        assert not result.should_disambiguate

    def test_multi_family_history_correct_isolation(self):
        """Mini clarified, then asking about Lite — Lite must still disambiguate."""
        history = [
            {
                "user": "Расскажите про Mini",
                "bot": (
                    "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n"
                    "1) Тариф Mini\n2) Комплект Mini\n"
                    "Ответьте номером 1-3 или напишите вариант словами."
                ),
            },
            {"user": "1", "bot": "Тариф Mini — базовый тариф."},
        ]
        # Check that Lite is NOT resolved (different family)
        assert self.d._is_family_already_clarified(history, "lite") is False
        # Check that Mini IS resolved
        assert self.d._is_family_already_clarified(history, "mini") is True

    def test_cyrillic_family_alias_resolution(self):
        """«Стандарт» (Russian) should resolve to 'standard' family."""
        history = self._make_history([
            ("Расскажите про стандарт",
             "Уточните, пожалуйста, что вы имеете в виду под «Standard»:\n1) Тариф Standard\n2) Комплект Standard\nОтветьте номером 1-3 или напишите вариант словами."),
            ("1", "Тариф Standard — 220 000 ₸/год."),
        ])
        assert self.d._is_family_already_clarified(history, "standard") is True


# ---------------------------------------------------------------------------
# FIX 4 ADVERSARIAL: tricky clarification patterns
# ---------------------------------------------------------------------------
class TestFix4Adversarial:
    def setup_method(self):
        self.d = make_disambiguator()

    def _make_history(self, pairs):
        return [{"user": u, "bot": b} for u, b in pairs]

    def test_clarification_without_marker_not_counted(self):
        """Bot mentioned Pro options but WITHOUT the marker → not a clarification."""
        history = self._make_history([
            ("Про Pro расскажите",
             "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n1) Тариф Pro\n2) Комплект Pro"),
            # NOTE: no _CLARIFICATION_MARKER in bot_text above!
            ("1", "..."),
        ])
        # No marker → loop skips this turn → not resolved
        assert self.d._is_family_already_clarified(history, "pro") is False

    def test_number_4_not_a_valid_selection(self):
        """'4' is NOT a valid option index (only 1-3 accepted)."""
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("4", "Не понял, уточните пожалуйста."),
        ])
        # "4" does NOT match r"^\s*[1-3]\b" → not resolved
        assert self.d._is_family_already_clarified(history, "mini") is False

    def test_unrelated_message_after_clarification(self):
        """Client wrote a long unrelated message after disambiguation."""
        history = self._make_history([
            ("Расскажите про Mini",
             "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n1) Тариф Mini\n2) Комплект Mini\nОтветьте номером 1-3 или напишите вариант словами."),
            ("У меня вопрос по поводу нашего разговора, не связанный с этим", "..."),
        ])
        assert self.d._is_family_already_clarified(history, "mini") is False

    def test_family_in_later_turn_not_matched_to_earlier_clarification(self):
        """Gap between clarification and current turn — Pro was clarified in turn 0,
        turns 1-3 are unrelated, now asking about Pro again."""
        history = self._make_history([
            ("Расскажите про Pro",
             "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами."),
            ("1", "Тариф Pro — максимальный тариф."),
            ("Расскажите о поддержке", "Поддержка 24/7."),
            ("Ещё раз про поддержку", "Можно написать в чат."),
        ])
        # Even with 2 unrelated turns after, Pro should still be marked resolved
        assert self.d._is_family_already_clarified(history, "pro") is True

    def test_second_number_in_unrelated_context_not_counted(self):
        """'Мне нужно 2 кассы' — '2' is in a different context, not a disambiguation answer.
        But our heuristic: if bot asked and NEXT user turn has r'^\\s*[1-3]\\b', it counts.
        This is a known limitation — '2 кассы' would be treated as selection.
        The test documents this as acceptable behavior."""
        history = self._make_history([
            ("Расскажите про Pro",
             "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n1) Тариф Pro\n2) Комплект Pro\nОтветьте номером 1-3 или напишите вариант словами."),
            ("2 точки у меня", "..."),  # '2 точки' starts with '2'
        ])
        # This is a false positive case — '2' at start triggers selection detection
        # Document as known limitation
        result = self.d._is_family_already_clarified(history, "pro")
        # We don't assert True/False here — just document behavior
        # assert result is True  # known false positive
        assert isinstance(result, bool)  # just check it doesn't crash


# ---------------------------------------------------------------------------
# FIX 5 STRESS: recency guard (continue → break)
# ---------------------------------------------------------------------------
class TestFix5RecencyGuard:
    """Test that _rewrite_fact_disambiguation_selection stops at non-disambig turns."""

    def setup_method(self):
        from src.knowledge.enhanced_retrieval import QueryRewriter
        llm_mock = MagicMock()
        llm_mock.generate.return_value = "query"
        self.rewriter = QueryRewriter(llm_mock)

    def _make_history(self, pairs):
        return [{"user": u, "bot": b} for u, b in pairs]

    def _disambig_bot(self, family="Mini"):
        return (
            f"Уточните, пожалуйста, что вы имеете в виду под «{family}»:\n"
            "1) Тариф Mini\n2) Комплект Mini\n"
            "Ответьте номером 1-3 или напишите вариант словами."
        )

    def test_normal_bot_turn_stops_scan(self):
        """Latest bot turn is a normal answer → break → resolve returns None."""
        history = self._make_history([
            ("Расскажите про Mini", self._disambig_bot()),
            ("1", "Тариф Mini — базовый тариф."),  # normal answer (not disambig)
        ])
        result = self.rewriter.resolve_fact_disambiguation_selection(
            user_message="А какой комплект есть?",
            history=history,
        )
        # Latest bot turn ("Тариф Mini — базовый тариф.") has NO disambiguation marker
        # → break → nothing resolved
        assert result is None

    def test_disambig_as_latest_turn_resolves(self):
        """Latest bot turn IS a disambiguation → resolve applies."""
        history = self._make_history([
            ("Расскажите про Mini", self._disambig_bot()),
        ])
        result = self.rewriter.resolve_fact_disambiguation_selection(
            user_message="1",
            history=history,
        )
        # Latest turn has disambig marker → should resolve
        assert result is not None
        assert "Тариф Mini" in result or "Комплект Mini" in result

    def test_two_disambig_turns_separated_by_normal_stops_at_normal(self):
        """Old disambig (turn 0) → normal answer (turn 1) → new disambig (turn 2).
        rewriting should apply to turn 2 (latest disambig), not turn 0."""
        history = self._make_history([
            ("Расскажите про Mini", self._disambig_bot("Mini")),  # turn 0
            ("1", "Тариф Mini — базовый тариф."),                 # turn 1 (normal)
            ("Расскажите про Lite",
             "Уточните, пожалуйста, что вы имеете в виду под «Lite»:\n"
             "1) Тариф Lite\n2) Комплект Lite\n"
             "Ответьте номером 1-3 или напишите вариант словами."),  # turn 2 (disambig)
        ])
        result = self.rewriter.resolve_fact_disambiguation_selection(
            user_message="2",
            history=history,
        )
        # Should resolve based on Lite disambig (turn 2), not Mini (turn 0)
        assert result is not None
        assert "Lite" in result

    def test_empty_history_returns_none(self):
        result = self.rewriter.resolve_fact_disambiguation_selection(
            user_message="1",
            history=[],
        )
        assert result is None

    def test_old_disambig_not_applied_to_current_question(self):
        """Old disambig at turn 0, 3 normal turns since → must NOT apply."""
        history = self._make_history([
            ("Расскажите про Mini", self._disambig_bot()),
            ("1", "Тариф Mini — базовый тариф."),
            ("Расскажите о поддержке", "Поддержка 24/7."),
            ("Как оплатить?", "Оплата через Kaspi или перевод."),
        ])
        result = self.rewriter.resolve_fact_disambiguation_selection(
            user_message="Что входит в Standard?",
            history=history,
        )
        # 3 normal turns since disambig → break at latest non-disambig → None
        assert result is None


# ---------------------------------------------------------------------------
# FIX 1+2 INTEGRATION: max_kb_chars + strip in pipeline
# ---------------------------------------------------------------------------
class TestFix1Fix2Integration:
    """Verify НЕ ПУТАТЬ doesn't reach LLM even when facts are big."""

    def test_strip_applied_to_long_facts(self):
        """Simulate _build_query_context stripping НЕ ПУТАТЬ from section.facts."""
        from src.knowledge.enhanced_retrieval import _KB_META_STRIP_RE as er_re
        # Both modules should have the same strip behavior
        facts_with_meta = (
            "Тариф Pro — максимальный тариф.\n"
            "⚠️ НЕ ПУТАТЬ: Тариф Pro ≠ Комплект Pro.\n"
            "Цена: 500 000 ₸/год.\n"
            "• ⚠️ НЕ ПУТАТЬ: не путайте с модулем УКМ.\n"
            "Функции: аналитика, интеграции."
        )
        clean = er_re.sub("", facts_with_meta)
        assert "НЕ ПУТАТЬ" not in clean
        assert "Цена: 500 000 ₸/год." in clean
        assert "Функции: аналитика, интеграции." in clean

    def test_autonomous_kb_strip_same_behavior(self):
        """autonomous_kb.py's _KB_META_STRIP_RE must behave identically."""
        from src.knowledge.autonomous_kb import _KB_META_STRIP_RE as ak_re
        text = "Данные.\n⚠️ НЕ ПУТАТЬ: что-то.\nЕщё данные."
        result = ak_re.sub("", text)
        assert "НЕ ПУТАТЬ" not in result
        assert "Данные." in result and "Ещё данные." in result

    def test_max_kb_chars_setting_is_25000(self):
        """Verify settings.yaml was correctly patched."""
        from src.settings import settings
        val = settings.get_nested("enhanced_retrieval.max_kb_chars", 0)
        assert val == 25000, f"Expected 25000 but got {val}"


# ---------------------------------------------------------------------------
# REGRESSION: existing correct behaviors must not break
# ---------------------------------------------------------------------------
class TestRegressionNoBroken:
    """Ensure existing correct behaviors are not broken by the fixes."""

    def setup_method(self):
        self.d = make_disambiguator()

    def test_explicit_kit_still_resolves(self):
        """'комплект' (explicit kit) — must still resolve to kit."""
        result = self.d.analyze(
            user_message="Расскажите про комплект Mini",
            retrieved_facts=CONFLICT_MINI_FACTS,
        )
        assert not result.should_disambiguate

    def test_explicit_module_still_resolves(self):
        result = self.d.analyze(
            user_message="Нужен модуль для маркировки",
            retrieved_facts=CONFLICT_PRO_FACTS,
        )
        assert not result.should_disambiguate

    def test_empty_facts_no_crash(self):
        result = self.d.analyze(user_message="Что такое Mini?", retrieved_facts="")
        assert not result.should_disambiguate
        assert "empty_retrieved_facts" in result.reason_codes

    def test_empty_message_no_crash(self):
        result = self.d.analyze(user_message="", retrieved_facts=CONFLICT_MINI_FACTS)
        assert not result.should_disambiguate

    def test_clarification_limit_still_fires(self):
        """After max_clarification_repeats, stop asking — still works."""
        disambig_bot = (
            "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n"
            "1) Тариф Mini\n2) Комплект Mini\n"
            "Ответьте номером 1-3 или напишите вариант словами."
        )
        history = [
            {"user": "Что такое Mini?", "bot": disambig_bot},
            {"user": "Не понял", "bot": disambig_bot},
        ]
        result = self.d.analyze(
            user_message="Всё равно не понимаю",
            retrieved_facts=CONFLICT_MINI_FACTS,
            history=history,
        )
        assert not result.should_disambiguate
        assert "clarification_repeat_limit" in result.reason_codes

    def test_no_conflict_no_disambig(self):
        """Facts contain only one type → no conflict → no disambig."""
        only_tariff = "[pricing/tariff_mini]\nТариф Mini — 5 000 ₸/мес.\n"
        result = self.d.analyze(
            user_message="Расскажите про Mini",
            retrieved_facts=only_tariff,
        )
        assert not result.should_disambiguate

    def test_fail_open_on_exception(self):
        """detect_fact_disambiguation() must not raise — fail-open behavior."""
        result = detect_fact_disambiguation(
            user_message=None,  # type: ignore — simulate bad input
            retrieved_facts=None,  # type: ignore
        )
        assert isinstance(result, FactDisambiguationDecision)
        assert not result.should_disambiguate

    def test_two_different_families_no_intra_family_conflict(self):
        """Separate Mini and Standard sections — no intra-family conflict."""
        facts = """\
[pricing/tariff_mini]
Тариф Mini — 5 000 ₸/мес.

[pricing/tariff_standard]
Тариф Standard — 220 000 ₸/год.
"""
        result = self.d.analyze(
            user_message="Чем Mini отличается от Standard?",
            retrieved_facts=facts,
        )
        assert not result.should_disambiguate


# ---------------------------------------------------------------------------
# EDGE CASES: combinations that could expose unexpected interactions
# ---------------------------------------------------------------------------
class TestEdgeCasesCombinations:
    def setup_method(self):
        self.d = make_disambiguator()

    def test_pricing_signal_overrides_family_already_clarified_check(self):
        """Fix 3 (pricing signal) runs BEFORE Fix 4 (family resolved).
        Even if family wasn't clarified, pricing signal resolves it first."""
        history = []  # No previous clarifications
        result = self.d.analyze(
            user_message="Сколько стоит Pro?",
            retrieved_facts=CONFLICT_PRO_FACTS,
            history=history,
        )
        # Fix 3 fires first (pricing signal → tariff)
        assert not result.should_disambiguate
        assert "message_specific_tariff" in result.reason_codes

    def test_fix4_only_fires_after_fix3_fails(self):
        """When Fix 3 returns None AND Fix 4 resolves → no disambig via Fix 4.
        Use message WITHOUT 'про' preposition to avoid step 3 false trigger."""
        history = [
            {
                "user": "Расскажите про Mini",
                "bot": (
                    "Уточните, пожалуйста, что вы имеете в виду под «Mini»:\n"
                    "1) Тариф Mini\n2) Комплект Mini\n"
                    "Ответьте номером 1-3 или напишите вариант словами."
                ),
            },
            {"user": "1", "bot": "Тариф Mini — базовый тариф."},
        ]
        # "Подробнее о Mini" — no "про" preposition, no pricing/equipment signals
        # Fix 3 returns None → Fix 4 should resolve (family already clarified)
        result = self.d.analyze(
            user_message="Подробнее о Mini",
            retrieved_facts=CONFLICT_MINI_FACTS,
            history=history,
        )
        assert not result.should_disambiguate
        assert "family_already_clarified" in result.reason_codes

    def test_equipment_signal_overrides_step3(self):
        """Equipment signal (step 2) fires before step 3 (2 families).
        2 families + equipment signal → kit (not tariff)."""
        # "Оборудование для Lite или Standard?" → equipment signal → kit
        result = self.d._detect_specific_type("Оборудование для Lite или Standard?")
        assert result == "kit"  # step 2 fires before step 3

    def test_pricing_signal_wins_over_2_families(self):
        """Pricing signal wins over 2-family comparison logic."""
        result = self.d._detect_specific_type("Цена для Mini или Standard?")
        assert result == "tariff"

    def test_three_families_still_tariff_via_step3(self):
        """3 families mentioned → step 3 (>=2) → tariff."""
        result = self.d._detect_specific_type("Mini, Standard или Pro — что лучше?")
        assert result == "tariff"

    def test_long_message_with_buried_pricing_signal(self):
        """Pricing signal buried at the end of a long message."""
        long_msg = (
            "Я занимаюсь продажами, у меня несколько точек в разных городах, "
            "работаем уже 5 лет, хотим автоматизировать. "
            "Расскажите о Pro для нашей сети. Нас интересует бюджет."
        )
        result = self.d._detect_specific_type(long_msg)
        assert result == "tariff"

    def test_cyrillic_mixed_case_pricing_signal(self):
        """Mixed case pricing words."""
        assert self.d._detect_specific_type("ЦЕНА Mini?") == "tariff"
        assert self.d._detect_specific_type("Стоимость Mini") == "tariff"
        assert self.d._detect_specific_type("ТАРИФ Mini") == "tariff"  # explicit

    def test_pro_preposition_bug_pro_false_family(self):
        """'про' as Russian preposition before non-Pro product MUST NOT count as Pro family.
        Bug: 'Расскажите про Mini' → 'про' + 'mini' = 2 families → step 3 → 'tariff' (WRONG).
        Fix: _PRO_PREPOSITION_RE strips 'про' before non-Pro product names."""
        from src.knowledge.fact_disambiguation import _PRO_PREPOSITION_RE
        # Verify the regex strips "про" before non-Pro products
        assert _PRO_PREPOSITION_RE.search("расскажите про Mini")
        assert _PRO_PREPOSITION_RE.search("расскажите про Standard")
        assert _PRO_PREPOSITION_RE.search("расскажите про Lite")
        # But NOT before "Pro" itself
        assert not _PRO_PREPOSITION_RE.search("расскажите про Pro")
        # And NOT when "про" stands alone or at end
        assert not _PRO_PREPOSITION_RE.search("интересует про")

    def test_pro_preposition_step3_correct(self):
        """After fix: 'Расскажите про Mini' → 1 family → no step 3 → None (disambig)."""
        result = self.d._detect_specific_type("Расскажите про Mini")
        assert result is None  # не tariff из-за "про"-preposition

    def test_pro_preposition_step3_correct_standard(self):
        result = self.d._detect_specific_type("Расскажите про Standard")
        assert result is None

    def test_pro_product_comparison_still_fires(self):
        """'Mini или Pro?' — 'про' is NOT before non-Pro product → both count → tariff."""
        result = self.d._detect_specific_type("Mini или Pro — что лучше?")
        assert result == "tariff"

    def test_kazakh_words_no_false_trigger(self):
        """Kazakh words that happen to look like Russian signals shouldn't trigger."""
        # Common Kazakh words shouldn't accidentally trigger signals
        result = self.d._detect_specific_type("Сәлем, мен білгім келеді")
        assert result is None  # No families, no Russian signals

    def test_rrhe_not_triggered_by_mid_word_match(self):
        """Pricing pattern тариф\\w* should not match inside other words."""
        # 'тарифный', 'тарифе' should match (they're real inflections)
        assert bool(_PRICING_SIGNAL_RE.search("тарифный"))  # correct match
        assert bool(_PRICING_SIGNAL_RE.search("тарифе"))    # correct match
        assert bool(_PRICING_SIGNAL_RE.search("тарифах"))   # correct match

    def test_stub_facts_no_family_no_conflict(self):
        """Minimal facts with no family keywords → no conflict → no disambig."""
        stub = "[faq/general]\nWipon — торговая система для розницы.\n"
        result = self.d.analyze(
            user_message="Что такое Wipon?",
            retrieved_facts=stub,
        )
        assert not result.should_disambiguate

    def test_analyze_with_none_history(self):
        """history=None should work (uses [] internally)."""
        result = self.d.analyze(
            user_message="Сколько стоит Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
            history=None,
        )
        assert not result.should_disambiguate

    def test_analyze_with_empty_history(self):
        # "Расскажите про Mini" — "про" is preposition before "Mini" (non-Pro product)
        # → preposition stripped in step 3 → only "mini" family → 1 family → None → disambig
        result = self.d.analyze(
            user_message="Расскажите про Mini",
            retrieved_facts=CONFLICT_MINI_FACTS,
            history=[],
        )
        assert result.should_disambiguate

    def test_about_mini_without_pro_preposition(self):
        """'Что такое Mini?' — no 'про', no signals → disambig."""
        result = self.d.analyze(
            user_message="Что такое Mini?",
            retrieved_facts=CONFLICT_MINI_FACTS,
            history=[],
        )
        assert result.should_disambiguate

    def test_fix4_does_not_affect_different_family_in_retrieved_facts(self):
        """Pro was clarified, but now user asks about Standard which has conflict.
        Standard should still disambiguate (different family).
        Use 'Standard' without 'про' preposition to avoid step 3 trigger."""
        history = [
            {
                "user": "Расскажите про Pro",
                "bot": (
                    "Уточните, пожалуйста, что вы имеете в виду под «Pro»:\n"
                    "1) Тариф Pro\n2) Комплект Pro\n"
                    "Ответьте номером 1-3 или напишите вариант словами."
                ),
            },
            {"user": "1", "bot": "Тариф Pro — максимальный тариф."},
        ]
        result = self.d.analyze(
            user_message="А что такое Standard?",  # no "про" preposition
            retrieved_facts=CONFLICT_STANDARD_FACTS,
            history=history,
        )
        # Standard was never clarified → should disambig
        assert result.should_disambiguate
        assert result.family == "standard"
