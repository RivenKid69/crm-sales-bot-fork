"""Intent Coverage Validator for ensuring zero unmapped intents.

This validator ensures that:
1. All critical intents have explicit mappings in _universal_base
2. All intents in constants.yaml have taxonomy entries
3. Price intents use answer_with_pricing (not answer_with_facts)
4. Category and domain defaults are defined

This is part of the "Zero Unmapped Intents by Design" architecture.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CoverageIssue:
    """A single coverage validation issue.

    Attributes:
        severity: critical, high, medium, low
        intent: The intent with the issue (if applicable)
        issue_type: Type of issue (unmapped_critical, missing_taxonomy, wrong_action, etc.)
        message: Human-readable description
        location: Where the issue was found (file/mixin/state)
    """
    severity: str
    intent: Optional[str]
    issue_type: str
    message: str
    location: str


class IntentCoverageValidator:
    """Validator for intent coverage and taxonomy completeness.

    This validator performs static validation to catch unmapped intents
    at CI time, before they can cause production failures.

    Example:
        >>> from src.config_loader import ConfigLoader
        >>> from src.validation.intent_coverage import IntentCoverageValidator
        >>>
        >>> loader = ConfigLoader()
        >>> config = loader.load()
        >>> flow = loader.load_flow("spin_selling")
        >>>
        >>> validator = IntentCoverageValidator(config, flow)
        >>> issues = validator.validate_all()
        >>> critical_issues = [i for i in issues if i.severity == "critical"]
        >>> assert len(critical_issues) == 0, "Critical coverage issues found!"
    """

    # Critical intents that MUST have explicit mappings
    CRITICAL_INTENTS = {
        # Price intents (81% failure without explicit mapping)
        "price_question", "pricing_details", "cost_inquiry",
        "discount_request", "payment_terms", "pricing_comparison",
        "budget_question",
        # Purchase progression (81% failure for contact_provided)
        "contact_provided", "demo_request", "callback_request",
        "request_references", "consultation_request",
        # Meta intents (55% failure for request_brevity)
        "request_brevity", "unclear",
        # Exit and escalation
        "rejection", "farewell", "request_human"
    }

    # Price intents must use answer_with_pricing
    PRICE_INTENTS = {
        "price_question", "pricing_details", "cost_inquiry",
        "discount_request", "payment_terms", "pricing_comparison",
        "budget_question"
    }

    # Fact question intents that should be covered by secondary intent patterns
    # These are high-frequency intents for technical/security/integration questions
    FACT_QUESTION_INTENTS = {
        "question_technical", "question_security", "question_integrations",
        "question_features", "question_support", "comparison",
        "question_implementation", "question_equipment_general",
    }

    # Required keywords for specific patterns
    REQUIRED_PATTERN_KEYWORDS = {
        "question_technical": {"ssl", "tls", "api", "webhook", "шифрование"},
        "question_security": {"безопасность", "ssl", "аудит", "gdpr"},
        "question_integrations": {"api", "webhook", "интеграция"},
    }

    def __init__(self, config: "LoadedConfig", flow: "FlowConfig" = None):
        """Initialize validator.

        Args:
            config: LoadedConfig from ConfigLoader
            flow: Optional FlowConfig (for validating specific flow)
        """
        self.config = config
        self.flow = flow
        self.taxonomy_config = config.taxonomy_config
        self.constants = config.constants

    def validate_all(self) -> List[CoverageIssue]:
        """Run all validation checks.

        Returns:
            List of CoverageIssue objects found
        """
        issues = []

        issues.extend(self.validate_taxonomy_completeness())
        issues.extend(self.validate_critical_intent_mappings())
        issues.extend(self.validate_price_intent_actions())
        issues.extend(self.validate_category_defaults())
        issues.extend(self.validate_universal_base_mixin())

        # NEW: Secondary intent pattern coverage validation
        issues.extend(self.validate_fact_question_pattern_coverage())
        issues.extend(self.validate_pattern_keyword_completeness())

        logger.info(
            "Intent coverage validation complete",
            total_issues=len(issues),
            by_severity={
                "critical": len([i for i in issues if i.severity == "critical"]),
                "high": len([i for i in issues if i.severity == "high"]),
                "medium": len([i for i in issues if i.severity == "medium"]),
                "low": len([i for i in issues if i.severity == "low"]),
            }
        )

        return issues

    def validate_taxonomy_completeness(self) -> List[CoverageIssue]:
        """Validate that all intents have taxonomy entries.

        Returns:
            List of CoverageIssue for missing taxonomy entries
        """
        issues = []

        # Get all intents from constants.yaml categories
        all_intents = self._get_all_intents_from_categories()

        # Get intents in taxonomy
        intent_taxonomy = self.taxonomy_config.get("intent_taxonomy", {})
        taxonomy_intents = set(intent_taxonomy.keys())

        # Find missing intents
        missing = all_intents - taxonomy_intents

        for intent in missing:
            issues.append(CoverageIssue(
                severity="high",
                intent=intent,
                issue_type="missing_taxonomy",
                message=f"Intent '{intent}' found in categories but missing from intent_taxonomy",
                location="constants.yaml"
            ))

        return issues

    def validate_critical_intent_mappings(self) -> List[CoverageIssue]:
        """Validate that all critical intents have explicit mappings.

        Returns:
            List of CoverageIssue for unmapped critical intents
        """
        issues = []

        # Check _universal_base mixin has all critical intents
        universal_base = self._get_universal_base_mixin()
        if not universal_base:
            issues.append(CoverageIssue(
                severity="critical",
                intent=None,
                issue_type="missing_universal_base",
                message="_universal_base mixin not found in mixins.yaml",
                location="flows/_base/mixins.yaml"
            ))
            return issues

        rules = universal_base.get("rules", {})
        transitions = universal_base.get("transitions", {})

        # Check each critical intent has mapping
        for intent in self.CRITICAL_INTENTS:
            has_rule = intent in rules
            has_transition = intent in transitions

            if not has_rule and not has_transition:
                issues.append(CoverageIssue(
                    severity="critical",
                    intent=intent,
                    issue_type="unmapped_critical",
                    message=f"Critical intent '{intent}' has no mapping in _universal_base",
                    location="flows/_base/mixins.yaml:_universal_base"
                ))

        return issues

    def validate_price_intent_actions(self) -> List[CoverageIssue]:
        """Validate that price intents use answer_with_pricing.

        Returns:
            List of CoverageIssue for price intents with wrong actions
        """
        issues = []

        # Check _universal_base
        universal_base = self._get_universal_base_mixin()
        if universal_base:
            rules = universal_base.get("rules", {})
            for intent in self.PRICE_INTENTS:
                action = rules.get(intent)
                if action and action != "answer_with_pricing":
                    issues.append(CoverageIssue(
                        severity="high",
                        intent=intent,
                        issue_type="wrong_action",
                        message=f"Price intent '{intent}' uses '{action}' instead of 'answer_with_pricing'",
                        location="flows/_base/mixins.yaml:_universal_base"
                    ))

        # Check price_handling mixin
        price_handling = self._get_price_handling_mixin()
        if price_handling:
            rules = price_handling.get("rules", {})
            for intent in self.PRICE_INTENTS:
                rule = rules.get(intent)
                if isinstance(rule, list):
                    # Conditional rule - check all "then" actions
                    for item in rule:
                        if isinstance(item, dict) and "then" in item:
                            action = item["then"]
                            if action == "answer_with_facts":
                                issues.append(CoverageIssue(
                                    severity="high",
                                    intent=intent,
                                    issue_type="wrong_action",
                                    message=f"Price intent '{intent}' uses 'answer_with_facts' instead of 'answer_with_pricing' in conditional rule",
                                    location="flows/_base/mixins.yaml:price_handling"
                                ))

        return issues

    def validate_category_defaults(self) -> List[CoverageIssue]:
        """Validate that all categories have fallback defaults.

        Returns:
            List of CoverageIssue for categories without defaults
        """
        issues = []

        # Get all categories
        categories = self.constants.get("intents", {}).get("categories", {})
        category_names = set(categories.keys())

        # Get category defaults
        category_defaults = self.taxonomy_config.get("taxonomy_category_defaults", {})
        default_categories = set(category_defaults.keys())

        # Find categories without defaults
        missing = category_names - default_categories - {"negative", "informative", "question_requires_facts", "spin_progress"}  # Exclude composed/special categories

        for category in missing:
            issues.append(CoverageIssue(
                severity="medium",
                intent=None,
                issue_type="missing_category_default",
                message=f"Category '{category}' has no fallback default in taxonomy_category_defaults",
                location="constants.yaml:taxonomy_category_defaults"
            ))

        return issues

    def validate_universal_base_mixin(self) -> List[CoverageIssue]:
        """Validate that _universal_base is included in _base_phase.

        Returns:
            List of CoverageIssue if _universal_base not included
        """
        issues = []

        if not self.flow:
            # Can't validate without flow
            return issues

        # Get _base_phase state
        base_phase = self.flow.states.get("_base_phase")
        if not base_phase:
            issues.append(CoverageIssue(
                severity="critical",
                intent=None,
                issue_type="missing_base_phase",
                message="_base_phase state not found in flow",
                location="flows/_base/states.yaml"
            ))
            return issues

        # Check mixins list
        mixins = base_phase.get("mixins", [])
        if "_universal_base" not in mixins:
            issues.append(CoverageIssue(
                severity="critical",
                intent=None,
                issue_type="missing_universal_base_in_base_phase",
                message="_universal_base not included in _base_phase mixins",
                location="flows/_base/states.yaml:_base_phase"
            ))
        elif mixins[0] != "_universal_base":
            issues.append(CoverageIssue(
                severity="high",
                intent=None,
                issue_type="universal_base_not_first",
                message="_universal_base should be FIRST in _base_phase mixins for guaranteed coverage",
                location="flows/_base/states.yaml:_base_phase"
            ))

        return issues

    def _get_all_intents_from_categories(self) -> Set[str]:
        """Get all intents from constants.yaml categories.

        Returns:
            Set of all intent names
        """
        all_intents = set()
        categories = self.constants.get("intents", {}).get("categories", {})

        for category, intents in categories.items():
            if isinstance(intents, list):
                all_intents.update(intents)

        return all_intents

    def _get_universal_base_mixin(self) -> Optional[Dict[str, Any]]:
        """Get _universal_base mixin definition.

        Returns:
            Mixin dict or None if not found
        """
        # Try to get from flow first
        if self.flow and hasattr(self.flow, "mixins"):
            return self.flow.mixins.get("_universal_base")

        # Fallback: try to load from mixins.yaml directly
        # (This is a simplified version - in practice would use ConfigLoader)
        return None

    def _get_price_handling_mixin(self) -> Optional[Dict[str, Any]]:
        """Get price_handling mixin definition.

        Returns:
            Mixin dict or None if not found
        """
        if self.flow and hasattr(self.flow, "mixins"):
            return self.flow.mixins.get("price_handling")
        return None

    def _get_secondary_intent_patterns(self) -> Dict[str, Any]:
        """Get secondary intent patterns from the classifier.

        Returns:
            Dict of pattern name -> SecondaryIntentPattern
        """
        try:
            from src.classifier.secondary_intent_detection import DEFAULT_SECONDARY_INTENT_PATTERNS
            return DEFAULT_SECONDARY_INTENT_PATTERNS
        except ImportError:
            logger.warning("Could not import secondary intent patterns")
            return {}

    def validate_fact_question_pattern_coverage(self) -> List[CoverageIssue]:
        """Validate that all fact question intents are covered by patterns OR explicit mappings.

        Checks that each fact question intent has either:
        1. A secondary intent pattern for detection, OR
        2. An explicit mapping in _universal_base

        Returns:
            List of CoverageIssue for uncovered fact intents
        """
        issues = []

        # Get secondary intent patterns
        patterns = self._get_secondary_intent_patterns()
        pattern_covered = set(patterns.keys())

        # Get explicit mappings from _universal_base
        universal_base = self._get_universal_base_mixin()
        explicit_mapped = set()
        if universal_base:
            explicit_mapped.update(universal_base.get("rules", {}).keys())
            explicit_mapped.update(universal_base.get("transitions", {}).keys())

        # Combined coverage
        covered = pattern_covered | explicit_mapped

        # Find uncovered fact intents
        uncovered = self.FACT_QUESTION_INTENTS - covered

        for intent in uncovered:
            issues.append(CoverageIssue(
                severity="critical",
                intent=intent,
                issue_type="uncovered_fact_intent",
                message=f"Fact intent '{intent}' has NO secondary pattern AND NO explicit mapping",
                location="secondary_intent_detection.py / mixins.yaml"
            ))

        return issues

    def validate_pattern_keyword_completeness(self) -> List[CoverageIssue]:
        """Validate that secondary intent patterns have sufficient keyword coverage.

        Checks that patterns for critical intents include all required keywords
        for reliable detection.

        Returns:
            List of CoverageIssue for patterns with missing keywords
        """
        issues = []

        patterns = self._get_secondary_intent_patterns()

        for intent, required_keywords in self.REQUIRED_PATTERN_KEYWORDS.items():
            pattern = patterns.get(intent)

            if not pattern:
                issues.append(CoverageIssue(
                    severity="critical",
                    intent=intent,
                    issue_type="missing_pattern",
                    message=f"Secondary intent pattern for '{intent}' does not exist",
                    location="secondary_intent_detection.py"
                ))
                continue

            # Get pattern keywords
            pattern_keywords = set()
            if hasattr(pattern, 'keywords'):
                pattern_keywords = set(pattern.keywords)

            # Check for missing keywords
            missing = required_keywords - pattern_keywords
            if missing:
                issues.append(CoverageIssue(
                    severity="warning",
                    intent=intent,
                    issue_type="missing_keywords",
                    message=f"Pattern '{intent}' missing keywords: {missing}",
                    location="secondary_intent_detection.py"
                ))

        return issues


def validate_intent_coverage(config: "LoadedConfig", flow: "FlowConfig" = None) -> Dict[str, Any]:
    """Convenience function to run full intent coverage validation.

    Args:
        config: LoadedConfig from ConfigLoader
        flow: Optional FlowConfig

    Returns:
        Dict with validation results:
            - is_valid: bool (True if no critical issues)
            - issues: List of CoverageIssue
            - summary: Dict with counts by severity
    """
    validator = IntentCoverageValidator(config, flow)
    issues = validator.validate_all()

    by_severity = {
        "critical": [i for i in issues if i.severity == "critical"],
        "high": [i for i in issues if i.severity == "high"],
        "medium": [i for i in issues if i.severity == "medium"],
        "low": [i for i in issues if i.severity == "low"],
    }

    is_valid = len(by_severity["critical"]) == 0

    return {
        "is_valid": is_valid,
        "issues": issues,
        "summary": {
            "total": len(issues),
            "critical": len(by_severity["critical"]),
            "high": len(by_severity["high"]),
            "medium": len(by_severity["medium"]),
            "low": len(by_severity["low"]),
        }
    }


def validate_template_dedup_coverage(templates: dict) -> List[str]:
    """Ensure all templates with optional do_not_ask actually use {do_not_ask} in body."""
    issues = []
    for name, tmpl in templates.items():
        optional = tmpl.get("parameters", {}).get("optional", [])
        if "do_not_ask" in optional:
            body = tmpl.get("template", "")
            if "{do_not_ask}" not in body:
                issues.append(f"Template '{name}' declares do_not_ask but doesn't use it")
    return issues
