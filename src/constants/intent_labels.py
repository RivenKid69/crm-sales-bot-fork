"""
Маппинг интентов на человекочитаемые описания.

Используется для отображения вариантов пользователю
при disambiguation (уточнении намерения).
"""

from typing import Dict


INTENT_LABELS: Dict[str, str] = {
    # Вопросы
    "price_question": "Узнать стоимость",
    "question_features": "Узнать о функциях",
    "question_integrations": "Узнать об интеграциях",
    "pricing_details": "Детали по ценам",
    "comparison": "Сравнить с конкурентами",
    "consultation_request": "Запросить консультацию",

    # Возражения
    "objection_price": "Обсудить цену",
    "objection_no_time": "Обсудить время",
    "objection_think": "Подумать",
    "objection_competitor": "Сравнить с текущим решением",

    # Действия
    "agreement": "Продолжить разговор",
    "demo_request": "Запросить демо",
    "callback_request": "Перезвонить позже",
    "contact_provided": "Контакт предоставлен",
    "rejection": "Отказ",

    # SPIN
    "situation_provided": "Рассказать о ситуации",
    "problem_revealed": "Обсудить проблемы",
    "implication_acknowledged": "Обсудить последствия",
    "need_expressed": "Обсудить ценность",
    "no_problem": "Проблем нет",
    "no_need": "Потребности нет",

    # Прочее
    "greeting": "Поздороваться",
    "small_talk": "Поболтать",
    "gratitude": "Поблагодарить",
    "go_back": "Вернуться назад",
    "correct_info": "Исправить информацию",
    "info_provided": "Информация предоставлена",
    "unclear": "Непонятно",
}


def get_label(intent: str) -> str:
    """
    Получить человекочитаемое название интента.

    Args:
        intent: Системное имя интента

    Returns:
        Человекочитаемое название или само имя интента если нет в маппинге
    """
    return INTENT_LABELS.get(intent, intent)
