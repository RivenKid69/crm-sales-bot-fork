"""Documentation generation module."""

from .markdown import (
    GeneratorConfig,
    MarkdownGenerator,
    generate_documentation,
    slugify,
)

__all__ = [
    "GeneratorConfig",
    "MarkdownGenerator",
    "generate_documentation",
    "slugify",
]
