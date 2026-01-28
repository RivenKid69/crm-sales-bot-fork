"""Intent Taxonomy Registry for intelligent fallback.

This module implements a hierarchical intent taxonomy system that provides
intelligent fallback resolution when exact intent mappings are not found.

The taxonomy provides a 5-level fallback chain:
1. Exact match (handled by resolver)
2. Category fallback (e.g., price_question → question → answer_with_pricing)
3. Super-category fallback (e.g., question → user_input → acknowledge_and_continue)
4. Domain fallback (e.g., pricing domain → answer_with_pricing)
5. DEFAULT_ACTION (continue_current_goal)

This eliminates the systemic classification catastrophe where unmapped intents
silently fall back to generic continue_current_goal without intelligent resolution.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class IntentTaxonomy:
    """Taxonomy metadata for a single intent.

    Attributes:
        intent: The intent name
        category: Primary category (e.g., question, positive, objection)
        super_category: Higher-level grouping (e.g., user_input, user_action)
        semantic_domain: Semantic domain (e.g., pricing, product, purchase)
        fallback_action: Action to use if no exact mapping found
        fallback_transition: Optional state transition for fallback
        priority: Priority level (critical, high, medium, low)
    """
    intent: str
    category: str
    super_category: str
    semantic_domain: str
    fallback_action: str
    fallback_transition: Optional[str] = None
    priority: str = "medium"


class IntentTaxonomyRegistry:
    """Registry for taxonomy-based intelligent fallback resolution.

    This registry provides multi-level fallback chains for intents based on
    their taxonomic classification. When an exact intent mapping is not found,
    the resolver can query this registry for intelligent fallback options based
    on the intent's category, super-category, and semantic domain.

    Example:
        >>> registry = IntentTaxonomyRegistry(taxonomy_config)
        >>> chain = registry.get_fallback_chain("price_question")
        >>> # Returns:
        >>> # [
        >>> #   {"level": "exact", "intent": "price_question"},
        >>> #   {"level": "category", "action": "answer_with_pricing"},
        >>> #   {"level": "super_category", "action": "acknowledge_and_continue"},
        >>> #   {"level": "domain", "action": "answer_with_pricing"},
        >>> #   {"level": "default", "action": "continue_current_goal"}
        >>> # ]
    """

    def __init__(self, taxonomy_config: Dict):
        """Initialize registry from taxonomy configuration.

        Args:
            taxonomy_config: Configuration dict containing:
                - intent_taxonomy: Dict of intent -> taxonomy metadata
                - taxonomy_category_defaults: Category-level defaults
                - taxonomy_super_category_defaults: Super-category defaults
                - taxonomy_domain_defaults: Domain-level defaults
        """
        self.taxonomy: Dict[str, IntentTaxonomy] = {}
        self.category_defaults = taxonomy_config.get("taxonomy_category_defaults", {})
        self.super_category_defaults = taxonomy_config.get("taxonomy_super_category_defaults", {})
        self.domain_defaults = taxonomy_config.get("taxonomy_domain_defaults", {})

        # Build taxonomy registry from config
        intent_taxonomy_config = taxonomy_config.get("intent_taxonomy", {})
        for intent, meta in intent_taxonomy_config.items():
            try:
                self.taxonomy[intent] = IntentTaxonomy(
                    intent=intent,
                    category=meta["category"],
                    super_category=meta["super_category"],
                    semantic_domain=meta["semantic_domain"],
                    fallback_action=meta["fallback_action"],
                    fallback_transition=meta.get("fallback_transition"),
                    priority=meta.get("priority", "medium")
                )
            except KeyError as e:
                logger.error(
                    "Invalid taxonomy entry",
                    intent=intent,
                    missing_field=str(e),
                    meta=meta
                )
                # Skip invalid entries
                continue

        logger.info(
            "Intent taxonomy registry initialized",
            total_intents=len(self.taxonomy),
            categories=len(self.category_defaults),
            super_categories=len(self.super_category_defaults),
            domains=len(self.domain_defaults)
        )

    def get_fallback_chain(self, intent: str) -> List[Dict[str, Any]]:
        """Get 5-level fallback chain for an intent.

        Returns a list of fallback options in priority order:
        1. Exact match (placeholder, actual match handled by resolver)
        2. Category fallback (based on intent's category)
        3. Super-category fallback (based on intent's super_category)
        4. Domain fallback (based on intent's semantic_domain)
        5. Default fallback (continue_current_goal)

        Args:
            intent: The intent name to get fallback chain for

        Returns:
            List of fallback options, each containing:
                - level: The fallback level (exact, category, super_category, domain, default)
                - action: The fallback action (if applicable)
                - transition: Optional state transition (if applicable)
                - intent: The original intent (for exact level only)

        Example:
            >>> chain = registry.get_fallback_chain("price_question")
            >>> # Returns 5-level chain with taxonomy-based fallbacks
        """
        chain = [{"level": "exact", "intent": intent}]

        # If intent not in taxonomy, return default fallback only
        if intent not in self.taxonomy:
            logger.warning(
                "Intent not in taxonomy",
                intent=intent,
                fallback="default_only"
            )
            chain.append({"level": "default", "action": "continue_current_goal"})
            return chain

        tax = self.taxonomy[intent]

        # Level 2: Category fallback
        if tax.category in self.category_defaults:
            cat_defaults = self.category_defaults[tax.category]
            chain.append({
                "level": "category",
                "category": tax.category,
                "action": cat_defaults.get("fallback_action"),
                "transition": cat_defaults.get("fallback_transition")
            })

        # Level 3: Super-category fallback
        if tax.super_category in self.super_category_defaults:
            super_defaults = self.super_category_defaults[tax.super_category]
            chain.append({
                "level": "super_category",
                "super_category": tax.super_category,
                "action": super_defaults.get("fallback_action"),
                "transition": super_defaults.get("fallback_transition")
            })

        # Level 4: Domain fallback (strongest semantic signal)
        if tax.semantic_domain in self.domain_defaults:
            domain_defaults = self.domain_defaults[tax.semantic_domain]
            chain.append({
                "level": "domain",
                "domain": tax.semantic_domain,
                "action": domain_defaults.get("fallback_action"),
                "transition": domain_defaults.get("fallback_transition")
            })

        # Level 5: Default fallback (should never reach with proper taxonomy)
        chain.append({"level": "default", "action": "continue_current_goal"})

        return chain

    def get_taxonomy(self, intent: str) -> Optional[IntentTaxonomy]:
        """Get taxonomy metadata for an intent.

        Args:
            intent: The intent name

        Returns:
            IntentTaxonomy object if found, None otherwise
        """
        return self.taxonomy.get(intent)

    def has_intent(self, intent: str) -> bool:
        """Check if an intent is in the taxonomy.

        Args:
            intent: The intent name

        Returns:
            True if intent is in taxonomy, False otherwise
        """
        return intent in self.taxonomy

    def get_intents_by_category(self, category: str) -> List[str]:
        """Get all intents in a category.

        Args:
            category: The category name

        Returns:
            List of intent names in the category
        """
        return [
            intent for intent, tax in self.taxonomy.items()
            if tax.category == category
        ]

    def get_intents_by_domain(self, domain: str) -> List[str]:
        """Get all intents in a semantic domain.

        Args:
            domain: The semantic domain name

        Returns:
            List of intent names in the domain
        """
        return [
            intent for intent, tax in self.taxonomy.items()
            if tax.semantic_domain == domain
        ]

    def get_critical_intents(self) -> List[str]:
        """Get all intents marked as critical priority.

        Returns:
            List of critical intent names
        """
        return [
            intent for intent, tax in self.taxonomy.items()
            if tax.priority == "critical"
        ]

    def validate_completeness(self, all_intents: List[str]) -> Dict[str, List[str]]:
        """Validate taxonomy completeness against a list of all intents.

        Args:
            all_intents: List of all intent names that should be in taxonomy

        Returns:
            Dict with validation results:
                - missing: Intents in all_intents but not in taxonomy
                - extra: Intents in taxonomy but not in all_intents
                - total_coverage: Percentage of coverage
        """
        taxonomy_intents = set(self.taxonomy.keys())
        all_intents_set = set(all_intents)

        missing = list(all_intents_set - taxonomy_intents)
        extra = list(taxonomy_intents - all_intents_set)

        coverage = 0.0
        if len(all_intents_set) > 0:
            coverage = len(taxonomy_intents & all_intents_set) / len(all_intents_set) * 100

        return {
            "missing": missing,
            "extra": extra,
            "total_coverage": coverage,
            "missing_count": len(missing),
            "extra_count": len(extra)
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get taxonomy statistics.

        Returns:
            Dict with taxonomy statistics:
                - total_intents: Total number of intents
                - by_category: Count of intents per category
                - by_super_category: Count of intents per super-category
                - by_domain: Count of intents per domain
                - by_priority: Count of intents per priority
        """
        by_category = {}
        by_super_category = {}
        by_domain = {}
        by_priority = {}

        for tax in self.taxonomy.values():
            by_category[tax.category] = by_category.get(tax.category, 0) + 1
            by_super_category[tax.super_category] = by_super_category.get(tax.super_category, 0) + 1
            by_domain[tax.semantic_domain] = by_domain.get(tax.semantic_domain, 0) + 1
            by_priority[tax.priority] = by_priority.get(tax.priority, 0) + 1

        return {
            "total_intents": len(self.taxonomy),
            "by_category": by_category,
            "by_super_category": by_super_category,
            "by_domain": by_domain,
            "by_priority": by_priority
        }
