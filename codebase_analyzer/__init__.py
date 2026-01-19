"""Codebase Analyzer - Automated code analysis and documentation generation."""

__version__ = "0.1.0"
__author__ = "Codebase Analyzer Team"

from .config import AppConfig, get_config, load_config
from .indexer.indexer import CodebaseIndexer, create_indexer

__all__ = [
    "AppConfig",
    "get_config",
    "load_config",
    "CodebaseIndexer",
    "create_indexer",
    "__version__",
]
