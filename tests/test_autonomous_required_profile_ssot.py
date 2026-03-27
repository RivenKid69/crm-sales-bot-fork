from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_autonomous_states_use_new_required_profile_ssot():
    states = _load_yaml(
        ROOT / "src" / "yaml_config" / "flows" / "autonomous" / "states.yaml"
    )["states"]

    assert states["autonomous_discovery"]["required_data"] == ["business_type", "city"]
    assert states["autonomous_qualification"]["required_data"] == ["automation_before"]
    assert states["autonomous_presentation"]["required_data"] == []

    for terminal_name in ("payment_ready", "video_call_scheduled"):
        requirements = states["autonomous_closing"]["terminal_state_requirements"][terminal_name]
        assert requirements["required_any"] == ["contact_name", "client_name"]
        assert requirements["required_all"] == ["business_type", "city", "automation_before"]
        assert "required_if_true" not in requirements


def test_soft_profile_automation_slot_tracks_only_automation_before():
    dedup = _load_yaml(ROOT / "src" / "yaml_config" / "question_dedup.yaml")
    automation_slot = dedup["profile_collection"]["slots"]["automation"]

    assert automation_slot["required_all"] == ["automation_before"]
    assert "required_if_true" not in automation_slot
    assert "раньше автоматизация" in automation_slot["question"].lower()
    assert "чем пользуетесь" not in automation_slot["question"].lower()


def test_shared_spin_phase_questions_remain_unchanged():
    dedup = _load_yaml(ROOT / "src" / "yaml_config" / "question_dedup.yaml")
    situation_phase = dedup["phase_questions"]["situation"]
    problem_phase = dedup["phase_questions"]["problem"]

    assert situation_phase["required_fields"] == ["company_size", "current_tools", "business_type"]
    assert problem_phase["required_fields"] == ["pain_point"]
