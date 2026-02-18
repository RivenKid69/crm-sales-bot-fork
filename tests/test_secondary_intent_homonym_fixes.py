"""
Тесты на исправление омонимов в secondary_intent_detection.py

Проверяем два свойства для каждого исправленного интента:
  1. FALSE POSITIVE устранён  — омоним больше не триггерит ложный secondary intent
  2. TRUE POSITIVE сохранён   — реальные случаи по-прежнему детектируются

Тестируем через реальный SecondaryIntentDetectionLayer._do_refine(),
а не через ручной keyword scan (который проверял только часть логики).
"""

import pytest
from src.classifier.secondary_intent_detection import SecondaryIntentDetectionLayer
from src.classifier.refinement_pipeline import RefinementContext


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def layer():
    return SecondaryIntentDetectionLayer()


def get_signals(layer, message: str, primary_intent: str = "objection_trust") -> list[str]:
    """Прогоняет сообщение через layer._do_refine и возвращает secondary_signals."""
    ctx = RefinementContext(
        message=message,
        intent=primary_intent,
        confidence=0.85,
    )
    result_dict = {"intent": primary_intent, "confidence": 0.85, "extracted_data": {}}
    ref = layer._do_refine(message, result_dict, ctx)
    return ref.secondary_signals


# ===========================================================================
# price_question  (keywords=frozenset() — patterns always run)
# ===========================================================================

class TestPriceQuestion:

    # --- FALSE POSITIVES устранены ---

    def test_stoit_valueworthit_no_price(self, layer):
        """'не стоит тратить время' — сомнение, не вопрос о цене."""
        signals = get_signals(layer, "не стоит тратить время на это")
        assert "price_question" not in signals, f"Ложное срабатывание: {signals}"

    def test_stoit_risk_no_price(self, layer):
        """'стоит ли рисковать' — оценка, не вопрос о цене."""
        signals = get_signals(layer, "стоит ли рисковать и переходить?")
        assert "price_question" not in signals, f"Ложное срабатывание: {signals}"

    def test_davajte_greeting_no_price(self, layer):
        """'давайте познакомимся' — предложение начать диалог, не цена."""
        signals = get_signals(layer, "давайте познакомимся, я Алексей")
        assert "price_question" not in signals, f"Ложное срабатывание: {signals}"

    def test_davajte_discuss_no_price(self, layer):
        """'давайте обсудим задачи' — переход к теме, не цена."""
        signals = get_signals(layer, "давайте обсудим наши задачи сначала")
        assert "price_question" not in signals, f"Ложное срабатывание: {signals}"

    def test_sim11_full_message_no_price(self, layer):
        """SIM #11 Turn 4 — полное сообщение с 'стоит' как омонимом."""
        msg = "вручную в основном. а это точно работает? не уверен, что стоит тратить время на это"
        signals = get_signals(layer, msg, primary_intent="question_features")
        assert "price_question" not in signals, (
            f"SIM #11 регрессия: 'стоит' в смысле 'worth it' снова детектируется как price_question. "
            f"Signals: {signals}"
        )

    # --- TRUE POSITIVES сохранены ---

    def test_skolko_stoit_is_price(self, layer):
        """'сколько стоит' — настоящий вопрос о цене."""
        signals = get_signals(layer, "сколько стоит ваш продукт?", primary_intent="info_provided")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_stoimost_is_price(self, layer):
        """'стоимость' — явный ценовой сигнал."""
        signals = get_signals(layer, "какая стоимость подключения?", primary_intent="info_provided")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_composite_size_and_price(self, layer):
        """'100 человек, сколько стоит' — составное сообщение: основной кейс для secondary."""
        signals = get_signals(layer, "нас 100 человек, сколько стоит тариф?", primary_intent="situation_provided")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_tsena_is_price(self, layer):
        """'цену скажите' — прямой запрос цены."""
        signals = get_signals(layer, "цену скажите пожалуйста", primary_intent="info_provided")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_prays_is_price(self, layer):
        """'прайс' — ценовой сигнал."""
        signals = get_signals(layer, "пришлите прайс", primary_intent="callback_request")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_tarif_is_price(self, layer):
        """'тариф' — ценовой сигнал."""
        signals = get_signals(layer, "какой тариф минимальный?", primary_intent="question_features")
        assert "price_question" in signals, f"True positive потерян: {signals}"

    def test_davajte_po_tsene_is_price(self, layer):
        """'давайте по цене' — контекстный паттерн для цены (не омоним)."""
        signals = get_signals(layer, "ну давайте уже по цене поговорим", primary_intent="info_provided")
        assert "price_question" in signals, f"True positive потерян: {signals}"


# ===========================================================================
# request_brevity
# ===========================================================================

class TestRequestBrevity:

    # --- FALSE POSITIVES устранены ---

    def test_davajte_greeting_no_brevity(self, layer):
        """'давайте познакомимся' — не запрос краткости."""
        signals = get_signals(layer, "давайте познакомимся, расскажите о системе")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    def test_davaj_start_no_brevity(self, layer):
        """'давай начнём' — предложение начать, не краткость."""
        signals = get_signals(layer, "давай начнём с вопроса о функциях")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    def test_bystree_delivery_no_brevity(self, layer):
        """'побыстрее доставите' — вопрос о сроках, не краткость."""
        signals = get_signals(layer, "побыстрее доставите оборудование?")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    def test_bystree_competitor_no_brevity(self, layer):
        """'работает быстрее конкурентов' — сравнение скорости, не краткость."""
        signals = get_signals(layer, "ваша система работает быстрее конкурентов?")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    def test_srazu_understood_no_brevity(self, layer):
        """'сразу понял' — подтверждение, не просьба о краткости."""
        signals = get_signals(layer, "сразу понял, спасибо за объяснение")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    def test_srazu_tell_no_brevity(self, layer):
        """'сразу скажу' — вводное слово, не краткость."""
        signals = get_signals(layer, "сразу скажу что нас интересует аналитика")
        assert "request_brevity" not in signals, f"Ложное срабатывание: {signals}"

    # --- TRUE POSITIVES сохранены ---

    def test_koroche_is_brevity(self, layer):
        """'короче' — явный сигнал краткости."""
        signals = get_signals(layer, "короче, скажите главное", primary_intent="info_provided")
        assert "request_brevity" in signals, f"True positive потерян: {signals}"

    def test_konkretno_is_brevity(self, layer):
        """'конкретно' — явный сигнал краткости."""
        signals = get_signals(layer, "скажите конкретно сколько стоит", primary_intent="price_question")
        assert "request_brevity" in signals, f"True positive потерян: {signals}"

    def test_po_delu_with_koroche_is_brevity(self, layer):
        """'короче, давайте по делу' — комбинация: keyword 'короче' гейтит паттерн."""
        signals = get_signals(layer, "короче, давайте уже по делу", primary_intent="info_provided")
        assert "request_brevity" in signals, f"True positive потерян: {signals}"


# ===========================================================================
# question_features
# ===========================================================================

class TestQuestionFeatures:

    # --- FALSE POSITIVES устранены ---

    def test_mozhet_byt_no_features(self, layer):
        """'может быть не нужно' — сомнение, не вопрос о функциях."""
        signals = get_signals(layer, "может быть нам это и не нужно")
        assert "question_features" not in signals, f"Ложное срабатывание: {signals}"

    def test_mozhet_pomoch_no_features(self, layer):
        """'может поможете' — просьба, не вопрос о функциях."""
        signals = get_signals(layer, "может поможете разобраться с ценами?")
        assert "question_features" not in signals, f"Ложное срабатывание: {signals}"

    def test_kakie_clienty_no_features(self, layer):
        """'какие у вас клиенты' — вопрос о компании, не о функциях."""
        signals = get_signals(layer, "какие у вас клиенты обычно?")
        assert "question_features" not in signals, f"Ложное срабатывание: {signals}"

    # --- TRUE POSITIVES сохранены ---

    def test_funktsii_is_features(self, layer):
        """'какие функции' — прямой вопрос о функциях."""
        signals = get_signals(layer, "нас 5 человек, какие функции есть?", primary_intent="situation_provided")
        assert "question_features" in signals, f"True positive потерян: {signals}"

    def test_funktsional_is_features(self, layer):
        """'функционал' — явный сигнал."""
        signals = get_signals(layer, "расскажите про функционал системы", primary_intent="info_provided")
        assert "question_features" in signals, f"True positive потерян: {signals}"

    def test_vozmozhnosti_is_features(self, layer):
        """'возможности' — сигнал о функциях."""
        signals = get_signals(layer, "какие возможности у системы?", primary_intent="info_provided")
        assert "question_features" in signals, f"True positive потерян: {signals}"

    def test_rabotaet_is_features(self, layer):
        """'как работает' — feature вопрос (keyword 'работает' сохранён)."""
        signals = get_signals(layer, "расскажите как работает учёт?", primary_intent="situation_provided")
        assert "question_features" in signals, f"True positive потерян: {signals}"


# ===========================================================================
# question_integrations
# ===========================================================================

class TestQuestionIntegrations:

    # --- FALSE POSITIVES устранены ---

    def test_import_tovarov_no_integration(self, layer):
        """'импортом товаров' — торговый импорт в retail, не интеграция данных."""
        signals = get_signals(layer, "мы занимаемся импортом товаров из Китая")
        assert "question_integrations" not in signals, f"Ложное срабатывание: {signals}"

    def test_eksport_tovarov_no_integration(self, layer):
        """'экспорт продукции' — торговый экспорт, не интеграция."""
        signals = get_signals(layer, "у нас экспорт продукции в Россию")
        assert "question_integrations" not in signals, f"Ложное срабатывание: {signals}"

    def test_obmen_tovarov_no_integration(self, layer):
        """'обмен товара' — возврат/обмен в магазине, не интеграция."""
        signals = get_signals(layer, "как оформить обмен товара?")
        assert "question_integrations" not in signals, f"Ложное срабатывание: {signals}"

    def test_obmen_valyuty_no_integration(self, layer):
        """'обмен валюты' — не интеграция."""
        signals = get_signals(layer, "работаете ли вы с обменом валюты?")
        assert "question_integrations" not in signals, f"Ложное срабатывание: {signals}"

    # --- TRUE POSITIVES сохранены ---

    def test_api_is_integration(self, layer):
        """'api' — явный сигнал интеграции."""
        signals = get_signals(layer, "есть ли api для интеграции?", primary_intent="info_provided")
        assert "question_integrations" in signals, f"True positive потерян: {signals}"

    def test_kaspi_is_integration(self, layer):
        """'каспи' — специфичная интеграция."""
        signals = get_signals(layer, "работает ли с каспи?", primary_intent="info_provided")
        assert "question_integrations" in signals, f"True positive потерян: {signals}"

    def test_1c_is_integration(self, layer):
        """'1с' — интеграция с 1С."""
        signals = get_signals(layer, "есть интеграция с 1с?", primary_intent="question_features")
        assert "question_integrations" in signals, f"True positive потерян: {signals}"

    def test_webhook_is_integration(self, layer):
        """'webhook' — технический сигнал интеграции."""
        signals = get_signals(layer, "поддерживаете webhook?", primary_intent="question_technical")
        assert "question_integrations" in signals, f"True positive потерян: {signals}"


# ===========================================================================
# question_technical
# ===========================================================================

class TestQuestionTechnical:

    # --- FALSE POSITIVES устранены ---

    def test_protokol_vstrechi_no_technical(self, layer):
        """'протокол встречи' — встреча/документ, не техвопрос."""
        signals = get_signals(layer, "пришлите протокол встречи пожалуйста")
        assert "question_technical" not in signals, f"Ложное срабатывание: {signals}"

    def test_parametry_biznesa_no_technical(self, layer):
        """'параметры бизнеса' — бизнес-термин, не техвопрос."""
        signals = get_signals(layer, "эти параметры важны для нашего бизнеса")
        assert "question_technical" not in signals, f"Ложное срабатывание: {signals}"

    def test_harakteristiki_clientov_no_technical(self, layer):
        """'характеристики клиентов' — маркетинг, не техвопрос."""
        signals = get_signals(layer, "какие характеристики у ваших клиентов?")
        assert "question_technical" not in signals, f"Ложное срабатывание: {signals}"

    # --- TRUE POSITIVES сохранены ---

    def test_ssl_is_technical(self, layer):
        """'ssl' — технический сигнал."""
        signals = get_signals(layer, "используете ssl шифрование?", primary_intent="question_security")
        assert "question_technical" in signals, f"True positive потерян: {signals}"

    def test_api_is_technical(self, layer):
        """'api' в техническом контексте."""
        signals = get_signals(layer, "есть документация по api?", primary_intent="info_provided")
        assert "question_technical" in signals, f"True positive потерян: {signals}"

    def test_nastrojka_is_technical(self, layer):
        """'настройка' — технический вопрос."""
        signals = get_signals(layer, "как настройка происходит?", primary_intent="question_implementation")
        assert "question_technical" in signals, f"True positive потерян: {signals}"

    def test_tekhnicheskiy_is_technical(self, layer):
        """'технический' — явный маркер."""
        signals = get_signals(layer, "есть технический специалист?", primary_intent="request_human")
        assert "question_technical" in signals, f"True positive потерян: {signals}"


# ===========================================================================
# question_security
# ===========================================================================

class TestQuestionSecurity:

    # --- FALSE POSITIVES устранены ---

    def test_avtorizatsiya_platezha_no_security(self, layer):
        """'авторизация платежа' — POS payment auth, не вопрос безопасности."""
        signals = get_signals(layer, "авторизация платежа прошла успешно")
        assert "question_security" not in signals, f"Ложное срабатывание: {signals}"

    def test_net_dostupa_internet_no_security(self, layer):
        """'нет доступа к интернету' — connectivity issue, не security."""
        signals = get_signals(layer, "у нас нет доступа к интернету на точке")
        assert "question_security" not in signals, f"Ложное срабатывание: {signals}"

    # --- TRUE POSITIVES сохранены ---

    def test_bezopasnost_is_security(self, layer):
        """'безопасность' — явный сигнал."""
        signals = get_signals(layer, "как обеспечивается безопасность данных?", primary_intent="info_provided")
        assert "question_security" in signals, f"True positive потерян: {signals}"

    def test_shifrovanie_is_security(self, layer):
        """'шифрование' — явный сигнал."""
        signals = get_signals(layer, "есть шифрование при передаче?", primary_intent="info_provided")
        assert "question_security" in signals, f"True positive потерян: {signals}"

    def test_gdpr_is_security(self, layer):
        """'gdpr' — явный сигнал."""
        signals = get_signals(layer, "соответствуете ли gdpr?", primary_intent="question_technical")
        assert "question_security" in signals, f"True positive потерян: {signals}"

    def test_kontrol_dostupa_is_security(self, layer):
        """'контроль доступа' — контекстный паттерн (не bare 'доступа')."""
        signals = get_signals(layer, "есть ли контроль доступа по ролям?", primary_intent="info_provided")
        assert "question_security" in signals, f"True positive потерян: {signals}"

    def test_backup_is_security(self, layer):
        """'бэкап' — сигнал безопасности/надёжности."""
        signals = get_signals(layer, "делаете ли бэкап данных?", primary_intent="info_provided")
        assert "question_security" in signals, f"True positive потерян: {signals}"
