"""Base parser class for AST parsing."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import tree_sitter_go
import tree_sitter_php
import tree_sitter_typescript
from tree_sitter import Language, Parser, Node

from ..models.entities import (
    CodeEntity,
    EntityType,
    FileEntity,
    Language as CodeLanguage,
    SourceLocation,
    create_entity_id,
)
from ..models.relations import Relation


class BaseParser(ABC):
    """Abstract base class for language-specific AST parsers."""

    def __init__(self):
        self._parser: Parser | None = None
        self._language: Language | None = None

    @property
    @abstractmethod
    def language(self) -> CodeLanguage:
        """Get the language this parser handles."""
        ...

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Get file extensions this parser handles."""
        ...

    @abstractmethod
    def _init_language(self) -> Language:
        """Initialize the tree-sitter language."""
        ...

    def get_parser(self) -> Parser:
        """Get or create the tree-sitter parser."""
        if self._parser is None:
            self._parser = Parser()
            self._language = self._init_language()
            self._parser.language = self._language
        return self._parser

    def parse_file(self, file_path: Path) -> FileEntity | None:
        """Parse a source file and extract entities.

        Args:
            file_path: Path to the source file

        Returns:
            FileEntity with all extracted information, or None if parsing failed
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return self.parse_content(content, file_path)
        except Exception as e:
            # Log error but don't crash
            return None

    def parse_content(self, content: str, file_path: Path) -> FileEntity | None:
        """Parse source code content and extract entities.

        Args:
            content: Source code content
            file_path: Path for identification

        Returns:
            FileEntity with all extracted information
        """
        parser = self.get_parser()
        tree = parser.parse(content.encode("utf-8"))

        if tree.root_node.has_error:
            # Tree has syntax errors, but we can still try to extract what we can
            pass

        # Create file entity
        file_entity = FileEntity(
            id=create_entity_id(file_path, EntityType.FILE),
            name=file_path.name,
            entity_type=EntityType.FILE,
            language=self.language,
            location=SourceLocation(
                file_path=file_path,
                start_line=1,
                end_line=content.count("\n") + 1,
            ),
            file_path=file_path,
            file_size=len(content),
            line_count=content.count("\n") + 1,
            source_code=content,
        )

        # Extract entities from AST
        self._extract_entities(tree.root_node, content, file_entity)

        return file_entity

    @abstractmethod
    def _extract_entities(
        self,
        root_node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Extract entities from the AST.

        This method should populate the file_entity with:
        - imports
        - classes
        - functions
        - constants
        - etc.
        """
        ...

    def _get_node_text(self, node: Node, content: str) -> str:
        """Get the text content of a node."""
        return content[node.start_byte:node.end_byte]

    def _get_node_location(self, node: Node, file_path: Path) -> SourceLocation:
        """Get the source location of a node."""
        return SourceLocation(
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
        )

    def _find_nodes(self, node: Node, node_types: list[str]) -> list[Node]:
        """Find all child nodes of given types (non-recursive)."""
        return [child for child in node.children if child.type in node_types]

    def _find_nodes_recursive(self, node: Node, node_types: list[str]) -> list[Node]:
        """Find all descendant nodes of given types (recursive)."""
        results: list[Node] = []

        def traverse(n: Node) -> None:
            if n.type in node_types:
                results.append(n)
            for child in n.children:
                traverse(child)

        traverse(node)
        return results

    def _find_first_child(self, node: Node, node_type: str) -> Node | None:
        """Find the first child node of a given type."""
        for child in node.children:
            if child.type == node_type:
                return child
        return None

    def _get_docstring(self, node: Node, content: str) -> str | None:
        """Extract docstring/comment preceding a node."""
        # Look for comment nodes before the current node
        prev = node.prev_sibling
        comments: list[str] = []

        while prev and prev.type in ("comment", "doc_comment"):
            comment_text = self._get_node_text(prev, content).strip()
            comments.insert(0, comment_text)
            prev = prev.prev_sibling

        if comments:
            return "\n".join(comments)
        return None


# Parser registry
_parsers: dict[CodeLanguage, type[BaseParser]] = {}


def register_parser(language: CodeLanguage):
    """Decorator to register a parser for a language."""

    def decorator(cls: type[BaseParser]) -> type[BaseParser]:
        _parsers[language] = cls
        return cls

    return decorator


def get_parser_for_file(file_path: Path) -> BaseParser | None:
    """Get the appropriate parser for a file based on its extension."""
    ext = file_path.suffix.lower()

    for parser_cls in _parsers.values():
        instance = parser_cls()
        if ext in instance.file_extensions:
            return instance

    return None


def get_parser_for_language(language: CodeLanguage) -> BaseParser | None:
    """Get the parser for a specific language."""
    parser_cls = _parsers.get(language)
    if parser_cls:
        return parser_cls()
    return None
