"""Quality validation for generated knowledge base."""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from ..extraction.schemas import ExtractedSection

logger = logging.getLogger(__name__)


class QualityIssue(Enum):
    """Types of quality issues."""

    TOO_FEW_KEYWORDS = "too_few_keywords"
    DUPLICATE_TOPIC = "duplicate_topic"
    SELF_REFERENCE = "self_reference"
    TOO_SHORT_FACTS = "too_short_facts"
    MISSING_CATEGORY = "missing_category"
    INVALID_TOPIC_FORMAT = "invalid_topic_format"
    LOW_KEYWORD_DIVERSITY = "low_keyword_diversity"
    FACTS_NOT_SELF_CONTAINED = "facts_not_self_contained"
    MISSING_TYPOS = "missing_typos"
    MISSING_QUESTIONS = "missing_questions"


@dataclass
class QualityReport:
    """Quality check report."""

    total_sections: int
    passed_sections: int
    issues: List[Tuple[ExtractedSection, QualityIssue, str]] = field(default_factory=list)
    warnings: List[Tuple[ExtractedSection, str]] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_sections == 0:
            return 0.0
        return self.passed_sections / self.total_sections

    @property
    def is_acceptable(self) -> bool:
        """Check if quality meets minimum requirements."""
        # No duplicate topics allowed
        has_duplicates = any(
            issue[1] == QualityIssue.DUPLICATE_TOPIC for issue in self.issues
        )
        return self.pass_rate >= 0.90 and not has_duplicates

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Total sections: {self.total_sections}",
            f"Passed: {self.passed_sections} ({self.pass_rate:.1%})",
            f"Issues: {len(self.issues)}",
            f"Warnings: {len(self.warnings)}",
        ]

        if self.issues:
            lines.append("\nTop issues:")
            issue_counts = {}
            for _, issue_type, _ in self.issues:
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
            for issue_type, count in sorted(
                issue_counts.items(), key=lambda x: -x[1]
            )[:5]:
                lines.append(f"  - {issue_type.value}: {count}")

        return "\n".join(lines)


class QualityChecker:
    """Check quality of generated sections."""

    MIN_KEYWORDS = 20
    MAX_KEYWORDS = 50
    MIN_FACTS_LENGTH = 50

    # Patterns indicating references to other sections
    SELF_REFERENCE_PATTERNS = [
        r"см\.\s*(выше|ниже|раздел)",
        r"как\s+указано\s+(выше|ранее)",
        r"в\s+предыдущ",
        r"в\s+следующ",
        r"смотри\s+секцию",
        r"подробнее\s+в\s+разделе",
    ]

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def check(self, sections: List[ExtractedSection]) -> QualityReport:
        """Run full quality check."""
        issues = []
        warnings = []
        passed = 0

        # Check for duplicate topics
        topic_counts = {}
        for section in sections:
            topic_counts[section.topic] = topic_counts.get(section.topic, 0) + 1

        for section in sections:
            section_issues = []
            section_warnings = []

            # 1. Topic format
            if not self._is_valid_topic(section.topic):
                section_issues.append((
                    section,
                    QualityIssue.INVALID_TOPIC_FORMAT,
                    f"Topic '{section.topic}' не соответствует формату snake_case",
                ))

            # 2. Topic uniqueness
            if topic_counts.get(section.topic, 0) > 1:
                section_issues.append((
                    section,
                    QualityIssue.DUPLICATE_TOPIC,
                    f"Topic '{section.topic}' дублируется",
                ))

            # 3. Keywords count
            if len(section.keywords) < self.MIN_KEYWORDS:
                section_issues.append((
                    section,
                    QualityIssue.TOO_FEW_KEYWORDS,
                    f"Keywords: {len(section.keywords)}, минимум {self.MIN_KEYWORDS}",
                ))

            # 4. Facts length
            if len(section.facts) < self.MIN_FACTS_LENGTH:
                section_issues.append((
                    section,
                    QualityIssue.TOO_SHORT_FACTS,
                    f"Facts: {len(section.facts)} символов, минимум {self.MIN_FACTS_LENGTH}",
                ))

            # 5. Self-references
            if self._has_self_reference(section.facts):
                section_issues.append((
                    section,
                    QualityIssue.FACTS_NOT_SELF_CONTAINED,
                    "Facts содержат ссылки на другие секции",
                ))

            # 6. Keyword diversity (warning)
            diversity = self._calculate_keyword_diversity(section.keywords)
            if diversity < 0.3:
                section_warnings.append((
                    section,
                    f"Низкое разнообразие keywords: {diversity:.2f}",
                ))

            # 7. Check for typos in keywords (warning in non-strict)
            if not self._has_typos(section.keywords):
                if self.strict_mode:
                    section_issues.append((
                        section,
                        QualityIssue.MISSING_TYPOS,
                        "Keywords не содержат опечаток",
                    ))
                else:
                    section_warnings.append((
                        section,
                        "Keywords не содержат опечаток",
                    ))

            # 8. Check for question phrases (warning)
            if not self._has_question_phrases(section.keywords):
                section_warnings.append((
                    section,
                    "Keywords не содержат вопросительных фраз",
                ))

            # Aggregate
            issues.extend(section_issues)
            warnings.extend(section_warnings)

            if not section_issues:
                passed += 1

        return QualityReport(
            total_sections=len(sections),
            passed_sections=passed,
            issues=issues,
            warnings=warnings,
        )

    def _is_valid_topic(self, topic: str) -> bool:
        """Check topic format (snake_case, latin + digits)."""
        return bool(re.match(r"^[a-z][a-z0-9_]{2,59}$", topic))

    def _has_self_reference(self, facts: str) -> bool:
        """Check for references to other sections."""
        facts_lower = facts.lower()
        for pattern in self.SELF_REFERENCE_PATTERNS:
            if re.search(pattern, facts_lower):
                return True
        return False

    def _calculate_keyword_diversity(self, keywords: List[str]) -> float:
        """Calculate keyword diversity (0-1)."""
        if len(keywords) <= 1:
            return 0.0

        # Count unique prefixes (first 3 chars)
        prefixes = set(kw[:3].lower() for kw in keywords if len(kw) >= 3)
        return len(prefixes) / len(keywords)

    def _has_typos(self, keywords: List[str]) -> bool:
        """Check if keywords contain common typos."""
        typo_markers = [
            "скока", "сколко", "скоко", "ценна", "цна", "безплатно",
            "беслатно", "праис", "прас", "работат", "стоет", "функцыя",
        ]
        keywords_lower = [k.lower() for k in keywords]
        return any(typo in keywords_lower for typo in typo_markers)

    def _has_question_phrases(self, keywords: List[str]) -> bool:
        """Check if keywords contain question phrases."""
        question_markers = [
            "как", "сколько", "что такое", "можно ли", "есть ли",
            "работает ли", "почему", "зачем", "какой", "какая",
        ]
        keywords_text = " ".join(keywords).lower()
        return any(q in keywords_text for q in question_markers)


def validate_sections(sections: List[ExtractedSection]) -> Tuple[bool, str]:
    """Quick validation helper."""
    checker = QualityChecker()
    report = checker.check(sections)
    return report.is_acceptable, report.get_summary()
