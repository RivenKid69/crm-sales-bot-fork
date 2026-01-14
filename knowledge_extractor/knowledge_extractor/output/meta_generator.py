"""Generate _meta.yaml file."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ..extraction.schemas import ExtractedSection


class MetaGenerator:
    """Generate _meta.yaml with database statistics."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def generate(
        self,
        sections: List[ExtractedSection],
        company_name: Optional[str] = None,
        company_description: Optional[str] = None,
    ) -> Path:
        """Generate _meta.yaml file."""
        # Calculate stats
        category_counts = {}
        for section in sections:
            cat = section.category
            category_counts[cat] = category_counts.get(cat, 0) + 1

        categories_list = [
            {"name": name, "count": count}
            for name, count in sorted(category_counts.items())
        ]

        meta = {
            "company": {
                "name": company_name or "Unknown",
                "description": company_description or "Knowledge base",
            },
            "stats": {
                "total_sections": len(sections),
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "categories": categories_list,
            },
        }

        # Write file
        filepath = self.output_dir / "_meta.yaml"
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(
                meta,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        return filepath

    def update_stats(
        self,
        sections_by_file: Dict[str, List[ExtractedSection]],
    ) -> Dict:
        """Calculate statistics from sections."""
        total = sum(len(sects) for sects in sections_by_file.values())

        category_stats = {}
        for filename, sections in sections_by_file.items():
            # Extract category from filename (remove .yaml)
            category = filename.replace(".yaml", "")
            category_stats[category] = len(sections)

        return {
            "total_sections": total,
            "categories": category_stats,
        }
