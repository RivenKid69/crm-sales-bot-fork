"""
Интеграционные тесты для проверки SSOT принципа для pricing данных.

Проверяет end-to-end поток:
1. Classifier → price_question
2. Generator → get_facts()
3. LLM response → только тенге ₸, нет рублей ₽
"""

import pytest
from src.bot import SalesBot
from src.config_loader import ConfigLoader

@pytest.fixture
def bot():
    """Fixture для создания бота с полной конфигурацией."""
    loader = ConfigLoader()
    flow = loader.load_flow("spin_selling")
    return SalesBot(flow=flow)

class TestPricingSSoT:
    """Интеграционные тесты SSOT для pricing."""

    def test_price_question_only_tenge(self, bot):
        """Вопрос о цене должен вернуть только тенге."""
        response = bot.process_message("Сколько стоит?")

        # Проверка валюты
        assert "₸" in response, "Response must contain tenge symbol"
        assert "₽" not in response, "Response must not contain ruble symbol"
        assert "рубл" not in response.lower(), "Response must not mention rubles"

    def test_pricing_details_only_tenge(self, bot):
        """Детальный вопрос о тарифах должен вернуть только тенге."""
        response = bot.process_message("Расскажите подробнее о тарифах")

        assert "₸" in response, "Response must contain tenge symbol"
        assert "₽" not in response, "Response must not contain ruble symbol"

    def test_price_question_has_real_prices(self, bot):
        """Ответ должен содержать реальные цены из pricing.yaml."""
        response = bot.process_message("Какие у вас тарифы?")

        # Проверяем что есть хотя бы одна реальная цена
        # (используем регулярку для гибкости форматирования)
        import re
        prices = re.findall(r'(\d[\d\s,]*)\s*₸', response)

        assert len(prices) > 0, "Response must contain at least one price"

        # Проверяем что цены реальные (не 590/790/990)
        price_values = [int(p.replace(' ', '').replace(',', '')) for p in prices]
        assert not any(p in [590, 790, 990] for p in price_values), \
            "Response contains old hardcoded prices"

    def test_repeated_price_question_consistency(self, bot):
        """Повторные вопросы о цене должны давать консистентные ответы."""
        response1 = bot.process_message("Цена?")
        response2 = bot.process_message("А сколько стоит?")

        # Оба ответа должны быть в тенге
        for response in [response1, response2]:
            assert "₸" in response
            assert "₽" not in response

    def test_no_calculation_by_company_size(self, bot):
        """Не должно быть расчетов по company_size × price."""
        # Указываем размер компании
        bot.process_message("У нас 10 сотрудников")
        response = bot.process_message("Сколько будет стоить для нас?")

        # Не должно быть формул типа "10 × 790₽ = 7900₽"
        assert "×" not in response, "No multiplication in response"
        assert "*" not in response, "No multiplication in response"

        # Должны быть фиксированные тарифы
        assert "₸" in response
