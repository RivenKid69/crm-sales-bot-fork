from scripts.beauty_salon_autonomous_e2e import evaluate_scenario
from scripts.beauty_salon_autonomous_e2e import evaluate_turn_check


def test_evaluate_turn_check_passes_for_positive_first_answer():
    result = evaluate_turn_check(
        "Да, Wipon подходит для салона: можно вести услуги, продажи товаров и смотреть аналитику.",
        {
            "must_contain_any": ["услуг", "товар", "аналит"],
            "must_not_contain_any": ["расписан", "мастер"],
            "must_not_start_with_any": ["но", "однако"],
        },
    )

    assert result["passed"] is True
    assert result["forbidden_markers"] == []
    assert result["forbidden_openers"] == []
    assert result["missing_any_group"] is False


def test_evaluate_turn_check_detects_unasked_limitation_leak():
    result = evaluate_turn_check(
        "Но встроенного расписания мастеров нет, хотя услуги и товары вести можно.",
        {
            "must_contain_any": ["услуг", "товар"],
            "must_not_contain_any": ["расписан", "мастер", "нет встроенного"],
            "must_not_start_with_any": ["но", "однако"],
        },
    )

    assert result["passed"] is False
    assert result["forbidden_markers"]
    assert result["forbidden_openers"] == ["но"]


def test_evaluate_scenario_marks_missing_turn_as_failure():
    scenario = {
        "checks": [
            {"turn": 3, "must_contain_any": ["расписан"]},
        ]
    }
    result = {"turns": [{"turn": 1, "bot": "Здравствуйте"}, {"turn": 2, "bot": "Да, подходит"}]}

    evaluation = evaluate_scenario(result, scenario)

    assert evaluation["passed"] is False
    assert evaluation["checks"][0]["error"] == "missing_turn"
