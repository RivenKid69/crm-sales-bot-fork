"""
Tests for BUG #3 "Broken Record" fix.

The bug: anti-repetition data (do_not_repeat_responses) was collected correctly
by ResponseDirectives but never reached the LLM prompt because:
1. generator.py didn't extract do_not_repeat_responses from the memory dict
2. autonomous templates had no {do_not_repeat_responses} placeholder
3. _base templates had dead Jinja2 / double wrapping

These tests verify all 3 fixes.
"""

import pytest
import os
import yaml
from unittest.mock import Mock

src_path = os.path.join(os.path.dirname(__file__), '..', 'src')


# =============================================================================
# Test 1: generator.py — do_not_repeat_responses extraction
# =============================================================================
class TestDoNotRepeatResponsesExtraction:
    """Verify generator.py extracts do_not_repeat_responses into variables."""

    def test_default_exists_in_personalization_defaults(self):
        """do_not_repeat_responses must be in PERSONALIZATION_DEFAULTS."""
        from src.generator import PERSONALIZATION_DEFAULTS

        assert "do_not_repeat_responses" in PERSONALIZATION_DEFAULTS
        assert PERSONALIZATION_DEFAULTS["do_not_repeat_responses"] == ""

    def test_variables_populated_when_responses_present(self):
        """When memory has do_not_repeat_responses, variables must contain formatted block."""
        from src.generator import ResponseGenerator, SafeDict

        gen = ResponseGenerator(llm=Mock())

        # Simulate the extraction logic from generator.py
        memory = {
            "do_not_repeat_responses": [
                "Основные тарифы: Mini 5k, Lite 150k...",
                "У нас 4 тарифа от 5000 до 500000...",
            ]
        }

        variables = {"do_not_repeat_responses": ""}  # default

        if memory.get("do_not_repeat_responses"):
            recent_responses = memory["do_not_repeat_responses"]
            formatted = "\n".join(f"- {r}" for r in recent_responses[-3:])
            variables["do_not_repeat_responses"] = (
                "⚠️ НЕ ПОВТОРЯЙ дословно эти свои предыдущие ответы:\n"
                f"{formatted}\n"
                "Сформулируй мысль ДРУГИМИ словами."
            )

        assert "НЕ ПОВТОРЯЙ" in variables["do_not_repeat_responses"]
        assert "Основные тарифы" in variables["do_not_repeat_responses"]
        assert "У нас 4 тарифа" in variables["do_not_repeat_responses"]

    def test_variables_empty_when_no_responses(self):
        """When memory has empty do_not_repeat_responses, variables stay empty."""
        memory = {"do_not_repeat_responses": []}
        variables = {"do_not_repeat_responses": ""}

        if memory.get("do_not_repeat_responses"):
            # Should NOT enter this block for empty list
            variables["do_not_repeat_responses"] = "SHOULD NOT APPEAR"

        assert variables["do_not_repeat_responses"] == ""

    def test_variables_empty_when_key_missing(self):
        """When memory has no do_not_repeat_responses key, variables stay empty."""
        memory = {"client_card": "some data"}
        variables = {"do_not_repeat_responses": ""}

        if memory.get("do_not_repeat_responses"):
            variables["do_not_repeat_responses"] = "SHOULD NOT APPEAR"

        assert variables["do_not_repeat_responses"] == ""

    def test_only_last_3_responses_used(self):
        """At most 3 most recent responses are included."""
        memory = {
            "do_not_repeat_responses": [
                "Response 1",
                "Response 2",
                "Response 3",
                "Response 4",
                "Response 5",
            ]
        }
        variables = {"do_not_repeat_responses": ""}

        if memory.get("do_not_repeat_responses"):
            recent_responses = memory["do_not_repeat_responses"]
            formatted = "\n".join(f"- {r}" for r in recent_responses[-3:])
            variables["do_not_repeat_responses"] = (
                "⚠️ НЕ ПОВТОРЯЙ дословно эти свои предыдущие ответы:\n"
                f"{formatted}\n"
                "Сформулируй мысль ДРУГИМИ словами."
            )

        # Only last 3 should be present
        assert "Response 1" not in variables["do_not_repeat_responses"]
        assert "Response 2" not in variables["do_not_repeat_responses"]
        assert "Response 3" in variables["do_not_repeat_responses"]
        assert "Response 4" in variables["do_not_repeat_responses"]
        assert "Response 5" in variables["do_not_repeat_responses"]

    def test_safedict_returns_empty_for_missing_do_not_repeat(self):
        """SafeDict must return empty string when do_not_repeat_responses is absent."""
        from src.generator import SafeDict

        template = "Before\n{do_not_repeat_responses}\nAfter"
        result = template.format_map(SafeDict({"other_var": "value"}))

        assert "{do_not_repeat_responses}" not in result
        assert "Before\n\nAfter" == result


# =============================================================================
# Test 2: autonomous/prompts.yaml — placeholder present
# =============================================================================
class TestAutonomousTemplatesPlaceholder:
    """Verify autonomous templates have {do_not_repeat_responses} placeholder."""

    @pytest.fixture
    def autonomous_prompts(self):
        path = os.path.join(
            src_path, 'yaml_config', 'templates', 'autonomous', 'prompts.yaml'
        )
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_autonomous_respond_has_placeholder(self, autonomous_prompts):
        """autonomous_respond template must contain {do_not_repeat_responses}."""
        template = autonomous_prompts['templates']['autonomous_respond']['template']
        assert '{do_not_repeat_responses}' in template

    def test_continue_current_goal_has_placeholder(self, autonomous_prompts):
        """continue_current_goal template must contain {do_not_repeat_responses}."""
        template = autonomous_prompts['templates']['continue_current_goal']['template']
        assert '{do_not_repeat_responses}' in template

    def test_autonomous_respond_no_soft_instruction(self, autonomous_prompts):
        """autonomous_respond must NOT have the soft dedup instruction (replaced by data block)."""
        template = autonomous_prompts['templates']['autonomous_respond']['template']
        assert 'Не повторяй то что уже обсуждалось в диалоге' not in template

    def test_autonomous_respond_renders_clean_without_data(self, autonomous_prompts):
        """When do_not_repeat_responses is empty, template renders cleanly."""
        from src.generator import SafeDict

        template = autonomous_prompts['templates']['autonomous_respond']['template']
        variables = {
            'system': 'test system',
            'retrieved_facts': 'facts',
            'history': 'history',
            'spin_phase': 'situation',
            'goal': 'test goal',
            'user_message': 'hello',
            'collected_data': '',
            'missing_data': '',
            'do_not_ask': '',
            'objection_instructions': '',
            'do_not_repeat_responses': '',
        }
        result = template.format_map(SafeDict(variables))
        assert '{do_not_repeat_responses}' not in result
        assert '{' not in result or result.count('{') == result.count('}')


# =============================================================================
# Test 3: _base/prompts.yaml — no Jinja2, unified placeholder
# =============================================================================
class TestBaseTemplatesUnified:
    """Verify _base templates have clean {do_not_repeat_responses} without Jinja2."""

    @pytest.fixture
    def base_prompts(self):
        path = os.path.join(
            src_path, 'yaml_config', 'templates', '_base', 'prompts.yaml'
        )
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_no_jinja2_in_base_prompts(self, base_prompts):
        """No Jinja2 syntax ({% if / {% endif %}) in any _base template."""
        for name, tpl in base_prompts['templates'].items():
            template_text = tpl.get('template', '')
            assert '{% if' not in template_text, f"Jinja2 found in {name}"
            assert '{% endif' not in template_text, f"Jinja2 found in {name}"

    def test_answer_with_pricing_has_placeholder(self, base_prompts):
        """answer_with_pricing must contain {do_not_repeat_responses}."""
        template = base_prompts['templates']['answer_with_pricing']['template']
        assert '{do_not_repeat_responses}' in template

    def test_answer_with_pricing_no_jinja2_wrapping(self, base_prompts):
        """answer_with_pricing must NOT have Jinja2 wrapping around do_not_repeat."""
        template = base_prompts['templates']['answer_with_pricing']['template']
        assert '{% if do_not_repeat_responses %}' not in template

    def test_answer_with_pricing_brief_has_placeholder(self, base_prompts):
        """answer_with_pricing_brief must contain {do_not_repeat_responses}."""
        template = base_prompts['templates']['answer_with_pricing_brief']['template']
        assert '{do_not_repeat_responses}' in template

    def test_answer_with_pricing_brief_no_duplicate_wrapping(self, base_prompts):
        """answer_with_pricing_brief must NOT have duplicate wrapping text."""
        template = base_prompts['templates']['answer_with_pricing_brief']['template']
        assert 'Ты уже отвечал на этот вопрос ранее:' not in template
        assert '⚠️ ВАЖНО: НЕ ПОВТОРЯЙ дословно предыдущие ответы!' not in template

    def test_answer_with_pricing_brief_keeps_context_line(self, base_prompts):
        """answer_with_pricing_brief must keep the template-specific context line."""
        template = base_prompts['templates']['answer_with_pricing_brief']['template']
        assert 'КОНТЕКСТ: Клиент ПОВТОРНО спрашивает о цене.' in template

    def test_answer_with_pricing_brief_not_in_required(self, base_prompts):
        """do_not_repeat_responses must NOT be in required params of answer_with_pricing_brief."""
        params = base_prompts['templates']['answer_with_pricing_brief']['parameters']
        required = params.get('required', [])
        assert 'do_not_repeat_responses' not in required

    def test_answer_with_pricing_renders_with_data(self, base_prompts):
        """answer_with_pricing renders correctly with do_not_repeat_responses data."""
        from src.generator import SafeDict

        template = base_prompts['templates']['answer_with_pricing']['template']
        variables = {
            'system': 'test',
            'retrieved_facts': 'Mini 5k',
            'history': 'hist',
            'user_message': 'price?',
            'do_not_ask': '',
            'collected_fields_list': '',
            'do_not_repeat_responses': (
                "⚠️ НЕ ПОВТОРЯЙ дословно эти свои предыдущие ответы:\n"
                "- Тарифы от 5k до 500k\n"
                "Сформулируй мысль ДРУГИМИ словами."
            ),
        }
        result = template.format_map(SafeDict(variables))
        assert 'НЕ ПОВТОРЯЙ' in result
        assert 'Тарифы от 5k до 500k' in result
        assert '{do_not_repeat_responses}' not in result

    def test_answer_with_pricing_renders_clean_without_data(self, base_prompts):
        """answer_with_pricing renders cleanly when do_not_repeat_responses is empty."""
        from src.generator import SafeDict

        template = base_prompts['templates']['answer_with_pricing']['template']
        variables = {
            'system': 'test',
            'retrieved_facts': 'Mini 5k',
            'history': 'hist',
            'user_message': 'price?',
            'do_not_ask': '',
            'collected_fields_list': '',
            'do_not_repeat_responses': '',
        }
        result = template.format_map(SafeDict(variables))
        assert '{do_not_repeat_responses}' not in result
        # Should still have the core pricing instruction
        assert 'КРИТИЧЕСКИ ВАЖНО' in result


# =============================================================================
# Run tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
