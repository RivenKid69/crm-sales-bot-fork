from src.question_dedup import QuestionDeduplicationEngine


def _build_engine(tmp_path):
    config_path = tmp_path / "question_dedup_test.yaml"
    config_path.write_text(
        """
data_fields: {}
phase_questions: {}
prompt_instructions: {}
profile_collection:
  enabled: true
  phases:
    - discovery
    - qualification
  slot_order:
    - contact_name
    - business_type
    - city
    - automation
  slots:
    contact_name:
      required_any: [contact_name, client_name]
      question: "Кстати, как к вам лучше обращаться?"
      markers: ["как к вам лучше обращаться", "как вас зовут"]
    business_type:
      required_any: [business_type]
      question: "Чтобы точнее подсказать, в какой сфере вы работаете?"
      markers: ["в какой сфере"]
    city:
      required_any: [city]
      question: "Подскажите, пожалуйста, в каком вы городе?"
      markers: ["в каком вы городе", "из какого города"]
    automation:
      required_all: [automation_before]
      question: "Коротко уточню: раньше автоматизация у вас уже была?"
      markers: ["автоматизац", "раньше была"]
  blockers:
    question_instruction_markers:
      - "не задавай"
    skip_intents:
      - rejection
    skip_intent_prefixes:
      - "objection_"
    max_frustration: 2
    recent_turn_window: 3
  instruction_template: |
    Мягкий сбор профиля: если уместен вопрос, спроси: "{question}".
strategies: {}
metrics: {}
""".strip(),
        encoding="utf-8",
    )
    return QuestionDeduplicationEngine(config_path=config_path)


def test_soft_profile_prefers_first_missing_slot(tmp_path):
    engine = _build_engine(tmp_path)

    instruction = engine.get_soft_profile_instruction(
        phase="discovery",
        intent="info_provided",
        collected_data={},
        history=[],
        question_instruction="Задай один вопрос по цели этапа.",
        frustration_level=0,
    )

    assert "мягкий сбор профиля" in instruction.lower()
    assert "как к вам лучше обращаться" in instruction.lower()


def test_soft_profile_respects_question_blockers(tmp_path):
    engine = _build_engine(tmp_path)

    instruction = engine.get_soft_profile_instruction(
        phase="discovery",
        intent="info_provided",
        collected_data={},
        history=[],
        question_instruction="⚠️ НЕ задавай вопросов в этом ответе.",
        frustration_level=0,
    )

    assert instruction == ""


def test_soft_profile_avoids_recent_duplicate_slot(tmp_path):
    engine = _build_engine(tmp_path)
    history = [{"user": "Привет", "bot": "Кстати, как к вам лучше обращаться?"}]

    instruction = engine.get_soft_profile_instruction(
        phase="discovery",
        intent="info_provided",
        collected_data={},
        history=history,
        question_instruction="",
        frustration_level=0,
    )

    assert "в какой сфере вы работаете" in instruction.lower()
    assert "как к вам лучше обращаться" not in instruction.lower()


def test_soft_profile_automation_slot_is_complete_once_automation_before_is_known(tmp_path):
    engine = _build_engine(tmp_path)
    base = {
        "contact_name": "Алексей",
        "business_type": "ритейл",
        "city": "Алматы",
        "automation_before": False,
    }

    instruction_complete = engine.get_soft_profile_instruction(
        phase="qualification",
        intent="info_provided",
        collected_data=base,
        history=[],
        question_instruction="",
        frustration_level=0,
    )
    assert instruction_complete == ""

    missing_automation = engine.get_soft_profile_instruction(
        phase="qualification",
        intent="info_provided",
        collected_data={
            "contact_name": "Алексей",
            "business_type": "ритейл",
            "city": "Алматы",
        },
        history=[],
        question_instruction="",
        frustration_level=0,
    )
    assert "раньше автоматизация" in missing_automation.lower()


def test_soft_profile_skips_objection_intent_prefix(tmp_path):
    engine = _build_engine(tmp_path)

    instruction = engine.get_soft_profile_instruction(
        phase="discovery",
        intent="objection_price",
        collected_data={},
        history=[],
        question_instruction="",
        frustration_level=0,
    )

    assert instruction == ""
