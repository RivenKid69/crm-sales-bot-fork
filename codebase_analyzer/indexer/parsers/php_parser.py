"""PHP AST parser using tree-sitter."""

import re
from pathlib import Path

import tree_sitter_php
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


@register_parser(CodeLanguage.PHP)
class PHPParser(BaseParser):
    """Parser for PHP source code."""

    @property
    def language(self) -> CodeLanguage:
        return CodeLanguage.PHP

    @property
    def file_extensions(self) -> list[str]:
        return [".php", ".phtml"]

    def _init_language(self) -> Language:
        return Language(tree_sitter_php.language_php())

    def _extract_entities(
        self,
        root_node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Extract PHP entities from AST."""
        # Extract namespace
        namespace_nodes = self._find_nodes_recursive(root_node, ["namespace_definition"])
        if namespace_nodes:
            ns_node = namespace_nodes[0]
            name_node = self._find_first_child(ns_node, "namespace_name")
            if name_node:
                file_entity.namespace = self._get_node_text(name_node, content)

        # Extract imports (use statements)
        use_nodes = self._find_nodes_recursive(root_node, ["namespace_use_declaration"])
        for use_node in use_nodes:
            import_entity = self._parse_use_statement(use_node, content, file_entity)
            if import_entity:
                file_entity.imports.append(import_entity)

        # Extract classes
        class_nodes = self._find_nodes_recursive(root_node, ["class_declaration"])
        for class_node in class_nodes:
            class_entity = self._parse_class(class_node, content, file_entity)
            if class_entity:
                file_entity.classes.append(class_entity)

        # Extract interfaces
        interface_nodes = self._find_nodes_recursive(root_node, ["interface_declaration"])
        for iface_node in interface_nodes:
            iface_entity = self._parse_interface(iface_node, content, file_entity)
            if iface_entity:
                file_entity.classes.append(iface_entity)

        # Extract traits
        trait_nodes = self._find_nodes_recursive(root_node, ["trait_declaration"])
        for trait_node in trait_nodes:
            trait_entity = self._parse_trait(trait_node, content, file_entity)
            if trait_entity:
                file_entity.classes.append(trait_entity)

        # Extract standalone functions
        func_nodes = self._find_nodes_recursive(root_node, ["function_definition"])
        for func_node in func_nodes:
            # Skip methods (those inside classes)
            if func_node.parent and func_node.parent.type in [
                "class_declaration",
                "interface_declaration",
                "trait_declaration",
            ]:
                continue
            func_entity = self._parse_function(func_node, content, file_entity)
            if func_entity:
                file_entity.functions.append(func_entity)

        # Extract constants
        const_nodes = self._find_nodes_recursive(root_node, ["const_declaration"])
        for const_node in const_nodes:
            # Skip class constants
            if const_node.parent and const_node.parent.type == "declaration_list":
                continue
            const_entity = self._parse_constant(const_node, content, file_entity)
            if const_entity:
                file_entity.constants.append(const_entity)

    def _parse_use_statement(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ImportEntity | None:
        """Parse a PHP use statement."""
        # Find the namespace name
        clause_nodes = self._find_nodes_recursive(node, ["namespace_use_clause"])
        if not clause_nodes:
            return None

        imported_names: list[str] = []
        module_path = ""
        alias: str | None = None

        for clause in clause_nodes:
            name_node = self._find_first_child(clause, "qualified_name")
            if name_node:
                full_name = self._get_node_text(name_node, content)
                if not module_path:
                    module_path = full_name
                imported_names.append(full_name.split("\\")[-1])

            # Check for alias
            alias_node = self._find_first_child(clause, "namespace_aliasing_clause")
            if alias_node:
                name = self._find_first_child(alias_node, "name")
                if name:
                    alias = self._get_node_text(name, content)

        return ImportEntity(
            id=create_entity_id(file_entity.file_path, EntityType.IMPORT, module_path),
            name=module_path.split("\\")[-1],
            entity_type=EntityType.IMPORT,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            module_path=module_path,
            imported_names=imported_names,
            alias=alias,
        )

    def _parse_class(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse a PHP class declaration."""
        name_node = self._find_first_child(node, "name")
        if not name_node:
            return None

        class_name = self._get_node_text(name_node, content)

        # Check modifiers
        is_abstract = False
        is_final = False
        for child in node.children:
            if child.type == "abstract_modifier":
                is_abstract = True
            elif child.type == "final_modifier":
                is_final = True

        # Get extends
        extends: str | None = None
        extends_node = self._find_first_child(node, "base_clause")
        if extends_node:
            name = self._find_first_child(extends_node, "name")
            if name:
                extends = self._get_node_text(name, content)

        # Get implements
        implements: list[str] = []
        impl_node = self._find_first_child(node, "class_interface_clause")
        if impl_node:
            names = self._find_nodes_recursive(impl_node, ["name", "qualified_name"])
            implements = [self._get_node_text(n, content) for n in names]

        class_entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.CLASS, class_name),
            name=class_name,
            entity_type=EntityType.CLASS,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            extends=extends,
            implements=implements,
            is_abstract=is_abstract,
            is_final=is_final,
        )

        # Parse class body
        body_node = self._find_first_child(node, "declaration_list")
        if body_node:
            self._parse_class_body(body_node, content, file_entity, class_entity)

        return class_entity

    def _parse_interface(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse a PHP interface declaration."""
        name_node = self._find_first_child(node, "name")
        if not name_node:
            return None

        interface_name = self._get_node_text(name_node, content)

        # Get extends (interfaces can extend other interfaces)
        extends: list[str] = []
        extends_node = self._find_first_child(node, "base_clause")
        if extends_node:
            names = self._find_nodes_recursive(extends_node, ["name", "qualified_name"])
            extends = [self._get_node_text(n, content) for n in names]

        class_entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.INTERFACE, interface_name),
            name=interface_name,
            entity_type=EntityType.INTERFACE,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            implements=extends,  # interfaces extend, stored as implements for simplicity
            is_interface=True,
        )

        # Parse interface body
        body_node = self._find_first_child(node, "declaration_list")
        if body_node:
            self._parse_class_body(body_node, content, file_entity, class_entity)

        return class_entity

    def _parse_trait(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse a PHP trait declaration."""
        name_node = self._find_first_child(node, "name")
        if not name_node:
            return None

        trait_name = self._get_node_text(name_node, content)

        class_entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.TRAIT, trait_name),
            name=trait_name,
            entity_type=EntityType.TRAIT,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            is_trait=True,
        )

        # Parse trait body
        body_node = self._find_first_child(node, "declaration_list")
        if body_node:
            self._parse_class_body(body_node, content, file_entity, class_entity)

        return class_entity

    def _parse_class_body(
        self,
        body_node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> None:
        """Parse the body of a class/interface/trait."""
        # Parse trait uses
        use_nodes = self._find_nodes_recursive(body_node, ["use_declaration"])
        for use_node in use_nodes:
            names = self._find_nodes_recursive(use_node, ["name", "qualified_name"])
            for name in names:
                class_entity.uses_traits.append(self._get_node_text(name, content))

        # Parse methods
        method_nodes = self._find_nodes(body_node, ["method_declaration"])
        for method_node in method_nodes:
            method = self._parse_method(method_node, content, file_entity, class_entity)
            if method:
                class_entity.methods.append(method)

        # Parse properties
        prop_nodes = self._find_nodes(body_node, ["property_declaration"])
        for prop_node in prop_nodes:
            props = self._parse_properties(prop_node, content, file_entity, class_entity)
            class_entity.properties.extend(props)

        # Parse class constants
        const_nodes = self._find_nodes(body_node, ["const_declaration"])
        for const_node in const_nodes:
            const = self._parse_class_constant(const_node, content, file_entity, class_entity)
            if const:
                class_entity.constants.append(const)

    def _parse_method(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> FunctionEntity | None:
        """Parse a PHP method declaration."""
        name_node = self._find_first_child(node, "name")
        if not name_node:
            return None

        method_name = self._get_node_text(name_node, content)

        # Get visibility and modifiers
        visibility = Visibility.PUBLIC
        is_static = False
        is_abstract = False

        for child in node.children:
            if child.type == "visibility_modifier":
                vis_text = self._get_node_text(child, content).lower()
                visibility = Visibility(vis_text)
            elif child.type == "static_modifier":
                is_static = True
            elif child.type == "abstract_modifier":
                is_abstract = True

        # Get parameters
        params_node = self._find_first_child(node, "formal_parameters")
        parameters = self._parse_parameters(params_node, content) if params_node else []

        # Get return type
        return_type: TypeInfo | None = None
        return_node = self._find_first_child(node, "return_type")
        if return_node:
            return_type = self._parse_type(return_node, content)

        method_entity = FunctionEntity(
            id=create_entity_id(
                file_entity.file_path, EntityType.METHOD, class_entity.name, method_name
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
            is_static=is_static,
            is_abstract=is_abstract,
        )

        # Extract function calls
        body_node = self._find_first_child(node, "compound_statement")
        if body_node:
            self._extract_calls(body_node, content, method_entity)
            self._extract_sql_queries(body_node, content, method_entity)

        return method_entity

    def _parse_function(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> FunctionEntity | None:
        """Parse a PHP function declaration."""
        name_node = self._find_first_child(node, "name")
        if not name_node:
            return None

        func_name = self._get_node_text(name_node, content)

        # Get parameters
        params_node = self._find_first_child(node, "formal_parameters")
        parameters = self._parse_parameters(params_node, content) if params_node else []

        # Get return type
        return_type: TypeInfo | None = None
        return_node = self._find_first_child(node, "return_type")
        if return_node:
            return_type = self._parse_type(return_node, content)

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
        )

        # Extract function calls
        body_node = self._find_first_child(node, "compound_statement")
        if body_node:
            self._extract_calls(body_node, content, func_entity)
            self._extract_sql_queries(body_node, content, func_entity)

        return func_entity

    def _parse_parameters(self, node: Node, content: str) -> list[Parameter]:
        """Parse function parameters."""
        parameters: list[Parameter] = []

        for child in node.children:
            if child.type == "simple_parameter":
                param = self._parse_single_parameter(child, content)
                if param:
                    parameters.append(param)
            elif child.type == "variadic_parameter":
                param = self._parse_single_parameter(child, content)
                if param:
                    param.is_variadic = True
                    parameters.append(param)

        return parameters

    def _parse_single_parameter(self, node: Node, content: str) -> Parameter | None:
        """Parse a single parameter."""
        name_node = self._find_first_child(node, "variable_name")
        if not name_node:
            return None

        name = self._get_node_text(name_node, content).lstrip("$")

        # Get type hint
        type_hint: str | None = None
        type_node = self._find_first_child(node, "type_list")
        if type_node:
            type_hint = self._get_node_text(type_node, content)
        else:
            # Try other type nodes
            for type_type in ["named_type", "primitive_type", "optional_type"]:
                t = self._find_first_child(node, type_type)
                if t:
                    type_hint = self._get_node_text(t, content)
                    break

        # Get default value
        default_value: str | None = None
        for child in node.children:
            if child.type == "=":
                # Next sibling is the default value
                idx = node.children.index(child)
                if idx + 1 < len(node.children):
                    default_value = self._get_node_text(node.children[idx + 1], content)
                break

        # Check for reference
        is_reference = any(c.type == "reference_modifier" for c in node.children)

        return Parameter(
            name=name,
            type_hint=type_hint,
            default_value=default_value,
            is_reference=is_reference,
        )

    def _parse_type(self, node: Node, content: str) -> TypeInfo | None:
        """Parse a type annotation."""
        # Handle union types
        text = self._get_node_text(node, content)

        # Check for nullable
        is_nullable = text.startswith("?")
        if is_nullable:
            text = text[1:]

        # Check for array
        is_array = text.endswith("[]")
        if is_array:
            text = text[:-2]

        return TypeInfo(name=text, is_nullable=is_nullable, is_array=is_array)

    def _parse_properties(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> list[PropertyEntity]:
        """Parse property declarations."""
        properties: list[PropertyEntity] = []

        # Get visibility
        visibility = Visibility.PUBLIC
        is_static = False
        is_readonly = False

        for child in node.children:
            if child.type == "visibility_modifier":
                vis_text = self._get_node_text(child, content).lower()
                visibility = Visibility(vis_text)
            elif child.type == "static_modifier":
                is_static = True
            elif child.type == "readonly_modifier":
                is_readonly = True

        # Get type hint
        type_hint: TypeInfo | None = None
        type_node = self._find_first_child(node, "type_list")
        if type_node:
            type_hint = self._parse_type(type_node, content)

        # Get property elements
        prop_elements = self._find_nodes_recursive(node, ["property_element"])
        for elem in prop_elements:
            var_node = self._find_first_child(elem, "variable_name")
            if var_node:
                prop_name = self._get_node_text(var_node, content).lstrip("$")

                # Get default value
                default_value: str | None = None
                for child in elem.children:
                    if child.type == "=":
                        idx = elem.children.index(child)
                        if idx + 1 < len(elem.children):
                            default_value = self._get_node_text(elem.children[idx + 1], content)
                        break

                prop = PropertyEntity(
                    id=create_entity_id(
                        file_entity.file_path,
                        EntityType.PROPERTY,
                        class_entity.name,
                        prop_name,
                    ),
                    name=prop_name,
                    entity_type=EntityType.PROPERTY,
                    language=self.language,
                    location=self._get_node_location(elem, file_entity.file_path),
                    source_code=self._get_node_text(node, content),
                    docstring=self._get_docstring(node, content),
                    type_hint=type_hint,
                    default_value=default_value,
                    visibility=visibility,
                    is_static=is_static,
                    is_readonly=is_readonly,
                )
                properties.append(prop)

        return properties

    def _parse_constant(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ConstantEntity | None:
        """Parse a standalone constant declaration."""
        # define() calls
        if node.type == "const_declaration":
            elements = self._find_nodes_recursive(node, ["const_element"])
            if elements:
                elem = elements[0]
                name_node = self._find_first_child(elem, "name")
                if name_node:
                    const_name = self._get_node_text(name_node, content)
                    value: str | None = None

                    for child in elem.children:
                        if child.type == "=":
                            idx = elem.children.index(child)
                            if idx + 1 < len(elem.children):
                                value = self._get_node_text(elem.children[idx + 1], content)
                            break

                    return ConstantEntity(
                        id=create_entity_id(
                            file_entity.file_path, EntityType.CONSTANT, const_name
                        ),
                        name=const_name,
                        entity_type=EntityType.CONSTANT,
                        language=self.language,
                        location=self._get_node_location(node, file_entity.file_path),
                        source_code=self._get_node_text(node, content),
                        value=value,
                    )
        return None

    def _parse_class_constant(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> ConstantEntity | None:
        """Parse a class constant declaration."""
        elements = self._find_nodes_recursive(node, ["const_element"])
        if elements:
            elem = elements[0]
            name_node = self._find_first_child(elem, "name")
            if name_node:
                const_name = self._get_node_text(name_node, content)
                value: str | None = None

                for child in elem.children:
                    if child.type == "=":
                        idx = elem.children.index(child)
                        if idx + 1 < len(elem.children):
                            value = self._get_node_text(elem.children[idx + 1], content)
                        break

                return ConstantEntity(
                    id=create_entity_id(
                        file_entity.file_path,
                        EntityType.CONSTANT,
                        class_entity.name,
                        const_name,
                    ),
                    name=const_name,
                    entity_type=EntityType.CONSTANT,
                    language=self.language,
                    location=self._get_node_location(node, file_entity.file_path),
                    source_code=self._get_node_text(node, content),
                    value=value,
                )
        return None

    def _extract_calls(
        self,
        body_node: Node,
        content: str,
        func_entity: FunctionEntity,
    ) -> None:
        """Extract function/method calls from a function body."""
        # Function calls
        func_calls = self._find_nodes_recursive(body_node, ["function_call_expression"])
        for call in func_calls:
            func_node = self._find_first_child(call, "name")
            if func_node:
                func_entity.calls.append(self._get_node_text(func_node, content))

        # Method calls
        method_calls = self._find_nodes_recursive(body_node, ["member_call_expression"])
        for call in method_calls:
            name_node = self._find_first_child(call, "name")
            if name_node:
                func_entity.calls.append(self._get_node_text(name_node, content))

        # Static method calls
        static_calls = self._find_nodes_recursive(body_node, ["scoped_call_expression"])
        for call in static_calls:
            name_node = self._find_first_child(call, "name")
            if name_node:
                func_entity.calls.append(self._get_node_text(name_node, content))

    def _extract_sql_queries(
        self,
        body_node: Node,
        content: str,
        func_entity: FunctionEntity,
    ) -> None:
        """Extract SQL queries from string literals in function body."""
        # Find all string literals
        strings = self._find_nodes_recursive(
            body_node, ["string", "encapsed_string", "heredoc"]
        )

        sql_keywords = re.compile(
            r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b",
            re.IGNORECASE,
        )

        for string_node in strings:
            text = self._get_node_text(string_node, content)
            if sql_keywords.search(text):
                # Clean up the SQL
                sql = text.strip("\"'")
                func_entity.sql_queries.append(sql)
