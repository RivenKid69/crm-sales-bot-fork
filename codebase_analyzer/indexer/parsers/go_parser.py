"""Go AST parser using tree-sitter."""

import re
from pathlib import Path

import tree_sitter_go
from tree_sitter import Language, Node

from ..models.entities import (
    ClassEntity,
    ConstantEntity,
    EntityType,
    FileEntity,
    FunctionEntity,
    ImportEntity,
    Language as CodeLanguage,
    Parameter,
    PropertyEntity,
    TypeInfo,
    Visibility,
    create_entity_id,
)
from .base import BaseParser, register_parser


@register_parser(CodeLanguage.GO)
class GoParser(BaseParser):
    """Parser for Go source code."""

    @property
    def language(self) -> CodeLanguage:
        return CodeLanguage.GO

    @property
    def file_extensions(self) -> list[str]:
        return [".go"]

    def _init_language(self) -> Language:
        return Language(tree_sitter_go.language())

    def _extract_entities(
        self,
        root_node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Extract Go entities from AST."""
        # Extract package name
        package_nodes = self._find_nodes(root_node, ["package_clause"])
        if package_nodes:
            pkg_node = package_nodes[0]
            name_node = self._find_first_child(pkg_node, "package_identifier")
            if name_node:
                file_entity.package = self._get_node_text(name_node, content)

        # Extract imports
        import_nodes = self._find_nodes_recursive(root_node, ["import_declaration"])
        for import_node in import_nodes:
            imports = self._parse_imports(import_node, content, file_entity)
            file_entity.imports.extend(imports)

        # Extract type declarations (structs, interfaces)
        type_nodes = self._find_nodes_recursive(root_node, ["type_declaration"])
        for type_node in type_nodes:
            entity = self._parse_type_declaration(type_node, content, file_entity)
            if entity:
                file_entity.classes.append(entity)

        # Extract functions
        func_nodes = self._find_nodes(root_node, ["function_declaration"])
        for func_node in func_nodes:
            func_entity = self._parse_function(func_node, content, file_entity)
            if func_entity:
                file_entity.functions.append(func_entity)

        # Extract methods (function with receiver)
        method_nodes = self._find_nodes(root_node, ["method_declaration"])
        for method_node in method_nodes:
            method_entity = self._parse_method(method_node, content, file_entity)
            if method_entity:
                # Associate method with its struct
                receiver_type = self._get_receiver_type(method_node, content)
                if receiver_type:
                    # Find the struct and add the method
                    for cls in file_entity.classes:
                        if cls.name == receiver_type:
                            cls.methods.append(method_entity)
                            break
                    else:
                        # Struct not in this file, add as standalone
                        file_entity.functions.append(method_entity)

        # Extract constants
        const_nodes = self._find_nodes_recursive(root_node, ["const_declaration"])
        for const_node in const_nodes:
            consts = self._parse_constants(const_node, content, file_entity)
            file_entity.constants.extend(consts)

    def _parse_imports(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> list[ImportEntity]:
        """Parse Go import declarations."""
        imports: list[ImportEntity] = []

        # Single import
        import_specs = self._find_nodes_recursive(node, ["import_spec"])
        for spec in import_specs:
            path_node = self._find_first_child(spec, "interpreted_string_literal")
            if path_node:
                path = self._get_node_text(path_node, content).strip('"')

                # Check for alias
                alias: str | None = None
                name_node = self._find_first_child(spec, "package_identifier")
                if name_node:
                    alias = self._get_node_text(name_node, content)

                # Check for dot import or blank import
                dot_node = self._find_first_child(spec, "dot")
                blank_node = self._find_first_child(spec, "blank_identifier")

                import_name = path.split("/")[-1]
                if alias == "_":
                    alias = "_"  # Blank import for side effects
                elif dot_node:
                    alias = "."  # Dot import

                imports.append(
                    ImportEntity(
                        id=create_entity_id(file_entity.file_path, EntityType.IMPORT, path),
                        name=import_name,
                        entity_type=EntityType.IMPORT,
                        language=self.language,
                        location=self._get_node_location(spec, file_entity.file_path),
                        module_path=path,
                        imported_names=[import_name],
                        alias=alias,
                    )
                )

        return imports

    def _parse_type_declaration(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse Go type declarations (structs, interfaces)."""
        type_specs = self._find_nodes_recursive(node, ["type_spec"])
        if not type_specs:
            return None

        spec = type_specs[0]
        name_node = self._find_first_child(spec, "type_identifier")
        if not name_node:
            return None

        type_name = self._get_node_text(name_node, content)

        # Determine if struct or interface
        struct_node = self._find_first_child(spec, "struct_type")
        interface_node = self._find_first_child(spec, "interface_type")

        if struct_node:
            return self._parse_struct(spec, struct_node, type_name, content, file_entity)
        elif interface_node:
            return self._parse_interface(spec, interface_node, type_name, content, file_entity)

        return None

    def _parse_struct(
        self,
        spec_node: Node,
        struct_node: Node,
        name: str,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity:
        """Parse a Go struct."""
        # Determine visibility (exported if starts with uppercase)
        visibility = Visibility.PUBLIC if name[0].isupper() else Visibility.PRIVATE

        entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.STRUCT, name),
            name=name,
            entity_type=EntityType.STRUCT,
            language=self.language,
            location=self._get_node_location(spec_node, file_entity.file_path),
            source_code=self._get_node_text(spec_node, content),
            docstring=self._get_docstring(spec_node, content),
            visibility=visibility,
        )

        # Parse struct fields
        field_list = self._find_first_child(struct_node, "field_declaration_list")
        if field_list:
            for field in self._find_nodes(field_list, ["field_declaration"]):
                props = self._parse_struct_field(field, content, file_entity, entity)
                entity.properties.extend(props)

        return entity

    def _parse_struct_field(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        struct_entity: ClassEntity,
    ) -> list[PropertyEntity]:
        """Parse struct field declarations."""
        properties: list[PropertyEntity] = []

        # Get field names
        names: list[str] = []
        for child in node.children:
            if child.type == "field_identifier":
                names.append(self._get_node_text(child, content))

        # Get type
        type_node = None
        for child in node.children:
            if child.type in [
                "type_identifier",
                "pointer_type",
                "slice_type",
                "array_type",
                "map_type",
                "channel_type",
                "qualified_type",
            ]:
                type_node = child
                break

        type_hint: TypeInfo | None = None
        if type_node:
            type_hint = TypeInfo(name=self._get_node_text(type_node, content))

        # Get tag
        tag: str | None = None
        tag_node = self._find_first_child(node, "raw_string_literal")
        if tag_node:
            tag = self._get_node_text(tag_node, content)

        for field_name in names:
            visibility = Visibility.PUBLIC if field_name[0].isupper() else Visibility.PRIVATE

            prop = PropertyEntity(
                id=create_entity_id(
                    file_entity.file_path,
                    EntityType.PROPERTY,
                    struct_entity.name,
                    field_name,
                ),
                name=field_name,
                entity_type=EntityType.PROPERTY,
                language=self.language,
                location=self._get_node_location(node, file_entity.file_path),
                source_code=self._get_node_text(node, content),
                type_hint=type_hint,
                visibility=visibility,
                metadata={"tag": tag} if tag else {},
            )
            properties.append(prop)

        return properties

    def _parse_interface(
        self,
        spec_node: Node,
        interface_node: Node,
        name: str,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity:
        """Parse a Go interface."""
        visibility = Visibility.PUBLIC if name[0].isupper() else Visibility.PRIVATE

        entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.INTERFACE, name),
            name=name,
            entity_type=EntityType.INTERFACE,
            language=self.language,
            location=self._get_node_location(spec_node, file_entity.file_path),
            source_code=self._get_node_text(spec_node, content),
            docstring=self._get_docstring(spec_node, content),
            visibility=visibility,
            is_interface=True,
        )

        # Parse interface methods
        for child in interface_node.children:
            if child.type == "method_spec":
                method = self._parse_interface_method(child, content, file_entity, entity)
                if method:
                    entity.methods.append(method)
            elif child.type == "type_identifier":
                # Embedded interface
                embedded = self._get_node_text(child, content)
                entity.implements.append(embedded)

        return entity

    def _parse_interface_method(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        interface_entity: ClassEntity,
    ) -> FunctionEntity | None:
        """Parse an interface method specification."""
        name_node = self._find_first_child(node, "field_identifier")
        if not name_node:
            return None

        method_name = self._get_node_text(name_node, content)

        # Get parameters
        params_node = self._find_first_child(node, "parameter_list")
        parameters = self._parse_parameters(params_node, content) if params_node else []

        # Get return type
        return_type = self._parse_return_type(node, content)

        return FunctionEntity(
            id=create_entity_id(
                file_entity.file_path,
                EntityType.METHOD,
                interface_entity.name,
                method_name,
            ),
            name=method_name,
            entity_type=EntityType.METHOD,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            parameters=parameters,
            return_type=return_type,
            is_abstract=True,  # Interface methods are abstract
        )

    def _parse_function(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> FunctionEntity | None:
        """Parse a Go function declaration."""
        name_node = self._find_first_child(node, "identifier")
        if not name_node:
            return None

        func_name = self._get_node_text(name_node, content)
        visibility = Visibility.PUBLIC if func_name[0].isupper() else Visibility.PRIVATE

        # Get parameters
        params_node = self._find_first_child(node, "parameter_list")
        parameters = self._parse_parameters(params_node, content) if params_node else []

        # Get return type
        return_type = self._parse_return_type(node, content)

        func_entity = FunctionEntity(
            id=create_entity_id(file_entity.file_path, EntityType.FUNCTION, func_name),
            name=func_name,
            entity_type=EntityType.FUNCTION,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
        )

        # Extract calls
        body_node = self._find_first_child(node, "block")
        if body_node:
            self._extract_calls(body_node, content, func_entity)
            self._extract_sql_queries(body_node, content, func_entity)

        return func_entity

    def _parse_method(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> FunctionEntity | None:
        """Parse a Go method declaration (function with receiver)."""
        name_node = self._find_first_child(node, "field_identifier")
        if not name_node:
            return None

        method_name = self._get_node_text(name_node, content)
        visibility = Visibility.PUBLIC if method_name[0].isupper() else Visibility.PRIVATE

        # Get receiver type
        receiver_type = self._get_receiver_type(node, content)

        # Get parameters
        params_list = [n for n in node.children if n.type == "parameter_list"]
        parameters: list[Parameter] = []
        if len(params_list) > 1:
            # First is receiver, second is params
            parameters = self._parse_parameters(params_list[1], content)

        # Get return type
        return_type = self._parse_return_type(node, content)

        method_entity = FunctionEntity(
            id=create_entity_id(
                file_entity.file_path,
                EntityType.METHOD,
                receiver_type or "unknown",
                method_name,
            ),
            name=method_name,
            entity_type=EntityType.METHOD,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
            metadata={"receiver_type": receiver_type},
        )

        # Extract calls
        body_node = self._find_first_child(node, "block")
        if body_node:
            self._extract_calls(body_node, content, method_entity)
            self._extract_sql_queries(body_node, content, method_entity)

        return method_entity

    def _get_receiver_type(self, node: Node, content: str) -> str | None:
        """Get the receiver type for a method."""
        params_list = [n for n in node.children if n.type == "parameter_list"]
        if params_list:
            receiver = params_list[0]
            # Look for type identifier in receiver
            type_nodes = self._find_nodes_recursive(
                receiver, ["type_identifier", "pointer_type"]
            )
            if type_nodes:
                type_text = self._get_node_text(type_nodes[0], content)
                # Remove pointer
                return type_text.lstrip("*")
        return None

    def _parse_parameters(self, node: Node, content: str) -> list[Parameter]:
        """Parse function parameters."""
        parameters: list[Parameter] = []

        param_decls = self._find_nodes(node, ["parameter_declaration"])
        for decl in param_decls:
            # Get names
            names: list[str] = []
            for child in decl.children:
                if child.type == "identifier":
                    names.append(self._get_node_text(child, content))

            # Get type
            type_hint: str | None = None
            for child in decl.children:
                if child.type in [
                    "type_identifier",
                    "pointer_type",
                    "slice_type",
                    "array_type",
                    "map_type",
                    "channel_type",
                    "qualified_type",
                    "interface_type",
                    "function_type",
                ]:
                    type_hint = self._get_node_text(child, content)
                    break

            # Check for variadic
            is_variadic = any(c.type == "variadic_parameter_declaration" for c in decl.children)

            for name in names:
                parameters.append(
                    Parameter(
                        name=name,
                        type_hint=type_hint,
                        is_variadic=is_variadic,
                    )
                )

        # Handle variadic parameters separately
        variadic_decls = self._find_nodes(node, ["variadic_parameter_declaration"])
        for decl in variadic_decls:
            name_node = self._find_first_child(decl, "identifier")
            if name_node:
                name = self._get_node_text(name_node, content)
                type_hint = None
                for child in decl.children:
                    if child.type not in ["identifier", "..."]:
                        type_hint = self._get_node_text(child, content)
                        break
                parameters.append(
                    Parameter(name=name, type_hint=type_hint, is_variadic=True)
                )

        return parameters

    def _parse_return_type(self, node: Node, content: str) -> TypeInfo | None:
        """Parse function return type."""
        # Look for result type
        for child in node.children:
            if child.type == "parameter_list" and child.prev_sibling:
                # This might be the return params
                continue
            if child.type in [
                "type_identifier",
                "pointer_type",
                "slice_type",
                "array_type",
                "map_type",
                "channel_type",
                "qualified_type",
                "interface_type",
            ]:
                return TypeInfo(name=self._get_node_text(child, content))

        # Check for multiple return values (parameter_list after params)
        param_lists = [n for n in node.children if n.type == "parameter_list"]
        if len(param_lists) > 1:
            return TypeInfo(name=self._get_node_text(param_lists[-1], content))

        return None

    def _parse_constants(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> list[ConstantEntity]:
        """Parse Go constant declarations."""
        constants: list[ConstantEntity] = []

        specs = self._find_nodes_recursive(node, ["const_spec"])
        for spec in specs:
            names = [
                self._get_node_text(n, content)
                for n in spec.children
                if n.type == "identifier"
            ]

            # Get value
            value: str | None = None
            for child in spec.children:
                if child.type == "expression_list":
                    value = self._get_node_text(child, content)
                    break

            for const_name in names:
                constants.append(
                    ConstantEntity(
                        id=create_entity_id(
                            file_entity.file_path, EntityType.CONSTANT, const_name
                        ),
                        name=const_name,
                        entity_type=EntityType.CONSTANT,
                        language=self.language,
                        location=self._get_node_location(spec, file_entity.file_path),
                        source_code=self._get_node_text(spec, content),
                        value=value,
                    )
                )

        return constants

    def _extract_calls(
        self,
        body_node: Node,
        content: str,
        func_entity: FunctionEntity,
    ) -> None:
        """Extract function calls from a function body."""
        call_expressions = self._find_nodes_recursive(body_node, ["call_expression"])

        for call in call_expressions:
            func_node = call.children[0] if call.children else None
            if func_node:
                call_text = self._get_node_text(func_node, content)
                func_entity.calls.append(call_text)

    def _extract_sql_queries(
        self,
        body_node: Node,
        content: str,
        func_entity: FunctionEntity,
    ) -> None:
        """Extract SQL queries from string literals."""
        strings = self._find_nodes_recursive(
            body_node, ["interpreted_string_literal", "raw_string_literal"]
        )

        sql_keywords = re.compile(
            r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b",
            re.IGNORECASE,
        )

        for string_node in strings:
            text = self._get_node_text(string_node, content)
            if sql_keywords.search(text):
                sql = text.strip('"`')
                func_entity.sql_queries.append(sql)
