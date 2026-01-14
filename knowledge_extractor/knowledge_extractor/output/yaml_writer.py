"""YAML output writer."""

import logging
from pathlib import Path
from typing import Dict, List

import yaml

from ..extraction.schemas import ExtractedSection

logger = logging.getLogger(__name__)


class YAMLWriter:
    """Write sections to YAML files."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_category_file(
        self,
        filename: str,
        sections: List[ExtractedSection],
        category: str,
    ) -> Path:
        """Write sections to a category YAML file."""
        filepath = self.output_dir / filename

        # Convert sections to dict format
        data = {
            "sections": [self._section_to_dict(s) for s in sections],
        }

        # Write with custom YAML formatting
        with open(filepath, "w", encoding="utf-8") as f:
            # Add header comment
            f.write(f"# База знаний: {category}\n")
            f.write(f"# Категория: {category}\n")
            f.write(f"# Секций: {len(sections)}\n\n")

            # Write YAML
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=100,
                indent=2,
            )

        logger.info(f"Written {len(sections)} sections to {filepath}")
        return filepath

    def write_all(
        self,
        sections_by_category: Dict[str, List[ExtractedSection]],
    ) -> List[Path]:
        """Write all sections grouped by category."""
        written_files = []

        for category, sections in sections_by_category.items():
            if not sections:
                continue

            filename = f"{category}.yaml"
            filepath = self.write_category_file(filename, sections, category)
            written_files.append(filepath)

        return written_files

    def _section_to_dict(self, section: ExtractedSection) -> dict:
        """Convert ExtractedSection to YAML-compatible dict."""
        return {
            "topic": section.topic,
            "priority": section.priority,
            "keywords": section.keywords,
            "facts": self._format_facts(section.facts),
        }

    def _format_facts(self, facts: str) -> str:
        """Format facts for YAML (preserve multiline)."""
        # Clean up whitespace
        facts = facts.strip()

        # If multiline, use literal block scalar
        if "\n" in facts:
            return facts

        return facts


class YAMLDumper(yaml.SafeDumper):
    """Custom YAML dumper for better formatting."""

    pass


def str_representer(dumper, data):
    """Represent strings with proper multiline handling."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


YAMLDumper.add_representer(str, str_representer)
