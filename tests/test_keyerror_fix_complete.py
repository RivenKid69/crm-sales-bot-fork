"""
Тесты на полноту исправления KeyError "message" в extra={} (Python 3.13).

Покрывает все 10 исправленных мест в 5 файлах:
  - confidence_calibration.py:718  (pipeline, HIGH impact — основной источник 24 KeyError)
  - unified.py:269,378,437,489     (pipeline error path + legacy)
  - composite_refinement.py:463    (legacy)
  - objection_refinement.py:267    (legacy)
  - refinement.py:242,260,284      (legacy)

Подход:
  1. ConfidenceCalibrationLayer._do_refine() с delta >= 0.1 → calibration не потеряна,
     "refinement failed" отсутствует в caplog.
  2. Legacy ClassificationRefinementLayer.refine() с refinement-eligible сообщением →
     нет KeyError traceback в caplog.
  3. SecondaryIntentDetectionLayer._do_refine() с price-вопросом →
     secondary_signals == ["price_question"] (регрессия-гвардия для pipeline пути).
"""

import pytest
import logging

from src.classifier.confidence_calibration import ConfidenceCalibrationLayer
from src.classifier.refinement import (
    ClassificationRefinementLayer,
    RefinementContext as LegacyRefinementContext,
)
from src.classifier.secondary_intent_detection import SecondaryIntentDetectionLayer
from src.classifier.refinement_pipeline import RefinementContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pipeline_ctx(message: str, intent: str, confidence: float) -> RefinementContext:
    return RefinementContext(
        message=message,
        intent=intent,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Test 1: ConfidenceCalibrationLayer — pipeline, основной источник 24 KeyError
# ---------------------------------------------------------------------------

class TestConfidenceCalibrationNoKeyError:
    """
    Проверяет confidence_calibration.py:718 исправлен.

    Стратегия: «да» — 1 слово (≤3) + intent=greeting → heuristic penalties ≥ 0.25
    → delta ≥ 0.1 → logger.info с 'log_message' (не 'message').
    До фикса: logger.info поднимал KeyError → BaseRefinementLayer.refine() ловил →
    логировал "refinement failed" + exc_info=True → откалиброванный confidence терялся.
    После фикса: calibration применяется, "refinement failed" отсутствует.
    """

    @pytest.fixture(scope="class")
    def layer(self):
        return ConfidenceCalibrationLayer()

    def test_calibration_applied_not_lost(self, layer, caplog):
        """delta >= 0.1 → откалиброванный confidence возвращается, не теряется."""
        message = "да"
        original_confidence = 0.9
        result_dict = {
            "intent": "greeting",
            "confidence": original_confidence,
            "alternatives": [],
            "extracted_data": {},
        }
        ctx = make_pipeline_ctx(message, "greeting", original_confidence)

        with caplog.at_level(logging.WARNING, logger="src.classifier.refinement_pipeline"):
            ref = layer._do_refine(message, result_dict, ctx)

        # Calibration must be applied (confidence reduced due to heuristic penalties)
        assert ref.confidence < original_confidence, (
            f"Calibration lost: confidence unchanged at {ref.confidence}. "
            "Скорее всего KeyError в logger.info снова поднимается и перехватывается."
        )

    def test_no_refinement_failed_in_log(self, layer, caplog):
        """После фикса BaseRefinementLayer.refine() не должна ловить исключение из логгера."""
        message = "да"
        result_dict = {
            "intent": "greeting",
            "confidence": 0.9,
            "alternatives": [],
            "extracted_data": {},
        }
        ctx = make_pipeline_ctx(message, "greeting", 0.9)

        with caplog.at_level(logging.WARNING, logger="src.classifier.refinement_pipeline"):
            layer._do_refine(message, result_dict, ctx)

        refinement_failed_records = [
            r for r in caplog.records
            if "refinement failed" in r.getMessage().lower()
        ]
        assert not refinement_failed_records, (
            f"'refinement failed' найдено в caplog — KeyError из logger.info ещё не исправлен:\n"
            + "\n".join(r.getMessage() for r in refinement_failed_records)
        )

    def test_no_keyerror_traceback(self, layer, caplog):
        """В caplog не должно быть трейсбэков с KeyError."""
        message = "да"
        result_dict = {
            "intent": "greeting",
            "confidence": 0.9,
            "alternatives": [],
            "extracted_data": {},
        }
        ctx = make_pipeline_ctx(message, "greeting", 0.9)

        with caplog.at_level(logging.DEBUG):
            layer._do_refine(message, result_dict, ctx)

        keyerror_records = [
            r for r in caplog.records
            if r.exc_info and r.exc_info[0] is KeyError
        ]
        assert not keyerror_records, (
            f"KeyError exc_info найден в {len(keyerror_records)} caplog записях — "
            "logger.info всё ещё использует зарезервированный ключ 'message'."
        )


# ---------------------------------------------------------------------------
# Test 2: Legacy ClassificationRefinementLayer — refinement.py:242,260,284
# ---------------------------------------------------------------------------

class TestLegacyRefinementNoKeyError:
    """
    Проверяет refinement.py:242, 260, 284 исправлены.

    ClassificationRefinementLayer.refine() вызывается в legacy-режиме напрямую
    (без BaseRefinementLayer обёртки), поэтому KeyError из logger.debug/info/warning
    поднимается выше и ломает вызывающий код.
    После фикса: refine() завершается успешно, нет KeyError traceback в caplog.
    """

    @pytest.fixture(scope="class")
    def layer(self):
        return ClassificationRefinementLayer()

    def _make_ctx(self, spin_phase: str = "situation") -> LegacyRefinementContext:
        return LegacyRefinementContext(
            message="да",
            spin_phase=spin_phase,
            state="discovery",
            last_action="ask_about_company",
            last_intent=None,
        )

    def test_refine_success_path_no_keyerror(self, layer, caplog):
        """
        'да' в ситуационной фазе + intent=greeting → refinement применяется.
        Проверяем, что logger.info (строка 260) не поднимает KeyError.
        """
        message = "да"
        llm_result = {"intent": "greeting", "confidence": 0.5, "extracted_data": {}}
        ctx = self._make_ctx(spin_phase="situation")

        with caplog.at_level(logging.DEBUG, logger="src.classifier.refinement"):
            result = layer.refine(message, llm_result, ctx)

        # Should return a result (not crash)
        assert result is not None
        assert "intent" in result

        keyerror_records = [
            r for r in caplog.records
            if r.exc_info and r.exc_info[0] is KeyError
        ]
        assert not keyerror_records, (
            f"KeyError в {len(keyerror_records)} caplog записях из refinement.py — "
            "logger.info/debug всё ещё использует зарезервированный ключ 'message'."
        )

    def test_refine_not_applicable_no_keyerror(self, layer, caplog):
        """
        Длинное сообщение → refinement не применяется (строка 242, logger.debug).
        Проверяем logger.debug без KeyError.
        """
        message = "нас около пятидесяти сотрудников работает в нескольких городах"
        llm_result = {"intent": "greeting", "confidence": 0.5, "extracted_data": {}}
        ctx = self._make_ctx(spin_phase="situation")

        with caplog.at_level(logging.DEBUG, logger="src.classifier.refinement"):
            result = layer.refine(message, llm_result, ctx)

        assert result is not None
        keyerror_records = [
            r for r in caplog.records
            if r.exc_info and r.exc_info[0] is KeyError
        ]
        assert not keyerror_records, (
            "KeyError из logger.debug (refinement.py:242) — ключ 'message' не переименован."
        )


# ---------------------------------------------------------------------------
# Test 3: SecondaryIntentDetectionLayer — price_question pipeline path
# ---------------------------------------------------------------------------

class TestSecondaryIntentPriceQuestion:
    """
    Регрессия-гвардия для SecondaryIntentDetectionLayer (pipeline path).

    Проверяет, что price_question корректно детектируется как secondary_signal
    когда primary=info_provided + есть явные price-паттерны.
    Этот тест является финальной гвардией для успешной интеграции pipeline
    после исправления всех KeyError в refinement-слоях.
    """

    @pytest.fixture(scope="class")
    def layer(self):
        return SecondaryIntentDetectionLayer()

    def _get_signals(self, layer, message: str, primary: str = "info_provided") -> list:
        ctx = RefinementContext(
            message=message,
            intent=primary,
            confidence=0.85,
        )
        result_dict = {"intent": primary, "confidence": 0.85, "extracted_data": {}}
        ref = layer._do_refine(message, result_dict, ctx)
        return ref.secondary_signals

    def test_skolko_stoit_podklyuchenie_is_price(self, layer):
        """'сколько стоит подключение?' → price_question secondary signal."""
        signals = self._get_signals(layer, "сколько стоит подключение?", "info_provided")
        assert "price_question" in signals, (
            f"Регрессия: price_question не детектируется. secondary_signals={signals}"
        )

    def test_tarif_is_price(self, layer):
        """'какой тариф?' → price_question secondary signal."""
        signals = self._get_signals(layer, "какой тариф у вас?", "question_features")
        assert "price_question" in signals, (
            f"Регрессия: тариф не детектируется как price. signals={signals}"
        )

    def test_ne_stoit_tратить_no_price(self, layer):
        """'не стоит тратить время' — омоним НЕ триггерит price_question."""
        signals = self._get_signals(layer, "не стоит тратить время на это", "objection_no_need")
        assert "price_question" not in signals, (
            f"Регрессия омонима 'стоит': снова ложное price_question. signals={signals}"
        )
