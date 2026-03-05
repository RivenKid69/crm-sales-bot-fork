from src.knowledge.pain_loader import PAIN_FILE_TO_CATEGORY, load_pain_knowledge_base


def test_load_pain_knowledge_base_counts_and_categories():
    kb = load_pain_knowledge_base()

    assert kb.company_name == "Wipon"
    assert kb.company_description == "БД решений по болям клиентов"
    assert len(kb.sections) == 129

    categories = {section.category for section in kb.sections}
    assert categories == set(PAIN_FILE_TO_CATEGORY.values())
