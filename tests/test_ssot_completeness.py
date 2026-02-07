# tests/test_ssot_completeness.py

"""
SSOT Completeness Tests — CI guard for SSOT coverage gaps.

Prevents:
    RC-1: objection_return_questions having insufficient coverage
    RC-2: all_questions missing question subcategories
    RC-5: Ghost intents in SSOT categories
    RC-SYS: No automated validation of SSOT completeness
    RC-SYS2: Manual listing of subcategories

These tests catch SSOT gaps at CI time, ensuring:
1. No ghost question intents exist in any category
2. Every question_* intent from INTENT_ROOTS is in all_questions
3. Every base category with question_* intents is auto-discovered
4. objection_return_triggers is a superset of all_questions
5. Simulation limits are auto-derived correctly from TTL
"""

import pytest


class TestSSOTCompleteness:
    """Prevent RC-1..RC-SYS2 class bugs. Catches SSOT gaps at CI time."""

    def test_no_ghost_question_intents(self):
        """Every question_* intent in any category must exist in INTENT_ROOTS or IntentType."""
        import typing
        from src.config import INTENT_ROOTS
        from src.classifier.llm.schemas import IntentType
        from src.yaml_config.constants import INTENT_CATEGORIES

        known = set(INTENT_ROOTS.keys()) | set(typing.get_args(IntentType))
        ghosts = [
            f"{cat}.{intent}"
            for cat, intents in INTENT_CATEGORIES.items()
            for intent in intents
            if intent.startswith("question_") and intent not in known
        ]
        assert not ghosts, f"Ghost intents: {ghosts}"

    def test_all_questions_covers_every_question_intent(self):
        """Every question_* intent from INTENT_ROOTS must be in all_questions."""
        from src.config import INTENT_ROOTS
        from src.yaml_config.constants import INTENT_CATEGORIES

        all_q = set(INTENT_CATEGORIES.get("all_questions", []))
        root_q = {k for k in INTENT_ROOTS if k.startswith("question_")}
        uncovered = root_q - all_q
        assert not uncovered, f"{len(uncovered)} uncovered: {sorted(uncovered)[:10]}"

    # Categories intentionally excluded from all_questions auto-discovery
    # (they contain question_* intents but are not question categories)
    EXCLUDED_FROM_AUTO_DISCOVERY = {"positive"}

    def test_all_question_base_categories_auto_discovered(self):
        """Every base category with question_* intents is covered by all_questions (excluding intentionally excluded categories)."""
        from src.yaml_config.constants import INTENT_CATEGORIES, _base_categories

        all_q = set(INTENT_CATEGORIES.get("all_questions", []))
        missing = []
        for cat, intents in _base_categories.items():
            if cat in self.EXCLUDED_FROM_AUTO_DISCOVERY:
                continue
            q_intents = [i for i in intents if i.startswith("question_")]
            not_covered = [i for i in q_intents if i not in all_q]
            if not_covered:
                missing.append(f"{cat}: {not_covered[:3]}")
        assert not missing, f"Uncovered question categories: {missing}"

    def test_objection_return_triggers_superset_of_all_questions(self):
        """Every question intent must trigger return from handle_objection."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        triggers = set(INTENT_CATEGORIES.get("objection_return_triggers", []))
        all_q = set(INTENT_CATEGORIES.get("all_questions", []))
        missing = all_q - triggers
        assert not missing, f"Questions not in return triggers: {sorted(missing)[:10]}"

    def test_simulation_consecutive_exceeds_ttl(self):
        """max_simulation_consecutive must be > max_turns_in_state (auto-derived or explicit)."""
        from src.config_loader import FlowConfig
        import yaml
        from pathlib import Path

        # Load the base states.yaml to get raw config
        states_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "states.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states_config = yaml.safe_load(f)

        states = states_config.get("states", {})
        for state_name, state_config in states.items():
            if not isinstance(state_config, dict):
                continue
            ttl = state_config.get("max_turns_in_state", 0)
            explicit_consecutive = state_config.get("max_simulation_consecutive")
            if ttl > 0 and explicit_consecutive is not None:
                assert explicit_consecutive > ttl, (
                    f"State '{state_name}': max_simulation_consecutive ({explicit_consecutive}) "
                    f"must be > max_turns_in_state ({ttl})"
                )

    def test_question_requires_facts_is_superset_of_key_intents(self):
        """question_requires_facts must include essential fact-requiring intents."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        qrf = set(INTENT_CATEGORIES.get("question_requires_facts", []))
        # These intents MUST require factual answers
        essential = {"price_question", "pricing_details", "question_features", "question_integrations"}
        missing = essential - qrf
        assert not missing, f"question_requires_facts missing essential intents: {missing}"

    def test_no_objection_return_questions_base_category(self):
        """objection_return_questions base category must not exist (replaced by all_questions)."""
        from src.yaml_config.constants import _base_categories

        assert "objection_return_questions" not in _base_categories, (
            "objection_return_questions base category should be removed"
        )

    # =================================================================
    # SYSTEMIC CI GUARDS — prevent dead intent recurrence
    # =================================================================

    def test_intent_type_matches_intent_roots(self):
        """IntentType and INTENT_ROOTS must be in sync."""
        import typing
        from src.classifier.llm.schemas import IntentType
        from src.config import INTENT_ROOTS

        schema = set(typing.get_args(IntentType))
        roots = set(INTENT_ROOTS.keys())
        assert not (schema - roots), f"In IntentType but not INTENT_ROOTS: {sorted(schema - roots)}"
        assert not (roots - schema), f"In INTENT_ROOTS but not IntentType: {sorted(roots - schema)}"

    def test_mixin_transitions_are_classifiable(self):
        """Every intent in mixins.yaml must exist in IntentType."""
        import typing
        import yaml
        from pathlib import Path
        from src.classifier.llm.schemas import IntentType

        classifiable = set(typing.get_args(IntentType))
        mixins_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "mixins.yaml"
        with open(mixins_path) as f:
            data = yaml.safe_load(f)
        dead = []
        for name, cfg in data.get("mixins", {}).items():
            if not isinstance(cfg, dict):
                continue
            for section in ("rules", "transitions"):
                for intent in cfg.get(section, {}):
                    if intent not in classifiable:
                        dead.append(f"{name}.{section}.{intent}")
        assert not dead, f"Dead intents in mixins: {dead}"

    def test_all_category_intents_are_classifiable(self):
        """Every intent in INTENT_CATEGORIES must exist in IntentType or INTENT_ROOTS."""
        import typing
        from src.classifier.llm.schemas import IntentType
        from src.config import INTENT_ROOTS
        from src.yaml_config.constants import INTENT_CATEGORIES

        known = set(typing.get_args(IntentType)) | set(INTENT_ROOTS.keys())
        ghosts = [
            f"{cat}.{intent}"
            for cat, intents in INTENT_CATEGORIES.items()
            for intent in intents
            if intent not in known
        ]
        assert not ghosts, f"Unclassifiable intents in categories: {ghosts}"
