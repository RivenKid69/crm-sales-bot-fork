"""Data models for code entities extracted from AST parsing."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EntityType(str, Enum):
    """Types of code entities."""

    FILE = "file"
    CLASS = "class"
    INTERFACE = "interface"
    TRAIT = "trait"  # PHP
    STRUCT = "struct"  # Go
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    CONSTANT = "constant"
    VARIABLE = "variable"
    IMPORT = "import"
    NAMESPACE = "namespace"
    PACKAGE = "package"  # Go
    MODULE = "module"
    COMPONENT = "component"  # React
    HOOK = "hook"  # React hooks
    ROUTE = "route"  # API endpoints


class Visibility(str, Enum):
    """Visibility modifiers."""

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"  # Go


class Language(str, Enum):
    """Supported programming languages."""

    PHP = "php"
    GO = "go"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    TSX = "tsx"
    JSX = "jsx"


@dataclass
class SourceLocation:
    """Location in source code."""

    file_path: Path
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def __str__(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


@dataclass
class Parameter:
    """Function/method parameter."""

    name: str
    type_hint: str | None = None
    default_value: str | None = None
    is_variadic: bool = False
    is_reference: bool = False  # PHP &$param


@dataclass
class TypeInfo:
    """Type information for variables, return types, etc."""

    name: str
    is_nullable: bool = False
    is_array: bool = False
    is_generic: bool = False
    generic_params: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        result = self.name
        if self.generic_params:
            result += f"<{', '.join(self.generic_params)}>"
        if self.is_array:
            result += "[]"
        if self.is_nullable:
            result = f"?{result}"
        return result


@dataclass
class CodeEntity:
    """Base class for all code entities."""

    id: str  # Unique identifier (e.g., "file:class:method")
    name: str
    entity_type: EntityType
    language: Language
    location: SourceLocation

    # Documentation
    docstring: str | None = None
    comments: list[str] = field(default_factory=list)

    # Raw source code
    source_code: str = ""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Get fully qualified name."""
        return self.id


@dataclass
class FunctionEntity(CodeEntity):
    """Function or method entity."""

    parameters: list[Parameter] = field(default_factory=list)
    return_type: TypeInfo | None = None
    is_async: bool = False
    is_static: bool = False
    is_abstract: bool = False
    visibility: Visibility = Visibility.PUBLIC

    # Extracted information
    calls: list[str] = field(default_factory=list)  # Functions/methods called
    sql_queries: list[str] = field(default_factory=list)  # SQL queries found
    api_calls: list[str] = field(default_factory=list)  # External API calls
    exceptions_thrown: list[str] = field(default_factory=list)
    exceptions_caught: list[str] = field(default_factory=list)

    @property
    def signature(self) -> str:
        """Get function signature."""
        params = ", ".join(
            f"{p.type_hint + ' ' if p.type_hint else ''}{p.name}"
            + (f" = {p.default_value}" if p.default_value else "")
            for p in self.parameters
        )
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"{self.name}({params}){ret}"


@dataclass
class ClassEntity(CodeEntity):
    """Class, interface, trait, or struct entity."""

    # Inheritance
    extends: str | None = None
    implements: list[str] = field(default_factory=list)
    uses_traits: list[str] = field(default_factory=list)  # PHP traits

    # Members
    methods: list[FunctionEntity] = field(default_factory=list)
    properties: list["PropertyEntity"] = field(default_factory=list)
    constants: list["ConstantEntity"] = field(default_factory=list)

    # Class characteristics
    is_abstract: bool = False
    is_final: bool = False
    is_interface: bool = False
    is_trait: bool = False

    visibility: Visibility = Visibility.PUBLIC

    @property
    def public_methods(self) -> list[FunctionEntity]:
        return [m for m in self.methods if m.visibility == Visibility.PUBLIC]

    @property
    def public_properties(self) -> list["PropertyEntity"]:
        return [p for p in self.properties if p.visibility == Visibility.PUBLIC]


@dataclass
class PropertyEntity(CodeEntity):
    """Class property or instance variable."""

    type_hint: TypeInfo | None = None
    default_value: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    is_static: bool = False
    is_readonly: bool = False


@dataclass
class ConstantEntity(CodeEntity):
    """Constant definition."""

    value: str | None = None
    type_hint: TypeInfo | None = None


@dataclass
class ImportEntity(CodeEntity):
    """Import or use statement."""

    module_path: str = ""
    imported_names: list[str] = field(default_factory=list)
    alias: str | None = None
    is_type_only: bool = False  # TypeScript "import type"


@dataclass
class FileEntity(CodeEntity):
    """Represents a source file."""

    # File info
    file_path: Path = field(default_factory=Path)
    file_size: int = 0
    line_count: int = 0

    # Namespace/package
    namespace: str | None = None
    package: str | None = None

    # Contents
    imports: list[ImportEntity] = field(default_factory=list)
    classes: list[ClassEntity] = field(default_factory=list)
    functions: list[FunctionEntity] = field(default_factory=list)
    constants: list[ConstantEntity] = field(default_factory=list)

    # React specific
    components: list["ComponentEntity"] = field(default_factory=list)

    @property
    def all_entities(self) -> list[CodeEntity]:
        """Get all entities in the file."""
        entities: list[CodeEntity] = [self]
        entities.extend(self.imports)
        entities.extend(self.classes)
        for cls in self.classes:
            entities.extend(cls.methods)
            entities.extend(cls.properties)
            entities.extend(cls.constants)
        entities.extend(self.functions)
        entities.extend(self.constants)
        entities.extend(self.components)
        return entities


@dataclass
class ComponentEntity(CodeEntity):
    """React component entity."""

    is_functional: bool = True
    props_type: str | None = None
    hooks_used: list[str] = field(default_factory=list)
    child_components: list[str] = field(default_factory=list)
    state_variables: list[str] = field(default_factory=list)


@dataclass
class RouteEntity(CodeEntity):
    """API route/endpoint entity."""

    http_method: str = "GET"
    path: str = ""
    handler: str = ""
    middleware: list[str] = field(default_factory=list)
    request_params: list[Parameter] = field(default_factory=list)
    response_type: TypeInfo | None = None


def create_entity_id(
    file_path: Path,
    entity_type: EntityType,
    *name_parts: str,
) -> str:
    """Create a unique entity ID.

    Format: file_path:type:name1:name2...
    Example: src/User.php:class:User:method:getName
    """
    parts = [str(file_path), entity_type.value]
    parts.extend(name_parts)
    return ":".join(parts)
