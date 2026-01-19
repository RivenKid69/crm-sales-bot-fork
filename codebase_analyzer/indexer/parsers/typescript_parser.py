"""TypeScript/JavaScript/React AST parser using tree-sitter."""

import re
from pathlib import Path

import tree_sitter_typescript
from tree_sitter import Language, Node

from ..models.entities import (
    ClassEntity,
    ComponentEntity,
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


class TypeScriptParserBase(BaseParser):
    """Base parser for TypeScript/JavaScript."""

    def _extract_entities(
        self,
        root_node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Extract TypeScript/JavaScript entities from AST."""
        # Extract imports
        import_nodes = self._find_nodes_recursive(root_node, ["import_statement"])
        for import_node in import_nodes:
            import_entity = self._parse_import(import_node, content, file_entity)
            if import_entity:
                file_entity.imports.append(import_entity)

        # Extract exports (for understanding module structure)
        export_nodes = self._find_nodes_recursive(
            root_node, ["export_statement", "export_clause"]
        )
        for export_node in export_nodes:
            self._parse_export(export_node, content, file_entity)

        # Extract classes
        class_nodes = self._find_nodes_recursive(root_node, ["class_declaration"])
        for class_node in class_nodes:
            class_entity = self._parse_class(class_node, content, file_entity)
            if class_entity:
                file_entity.classes.append(class_entity)

        # Extract interfaces (TypeScript)
        interface_nodes = self._find_nodes_recursive(root_node, ["interface_declaration"])
        for iface_node in interface_nodes:
            iface_entity = self._parse_interface(iface_node, content, file_entity)
            if iface_entity:
                file_entity.classes.append(iface_entity)

        # Extract type aliases (TypeScript)
        type_nodes = self._find_nodes_recursive(root_node, ["type_alias_declaration"])
        for type_node in type_nodes:
            type_entity = self._parse_type_alias(type_node, content, file_entity)
            if type_entity:
                file_entity.classes.append(type_entity)

        # Extract functions
        func_nodes = self._find_nodes_recursive(
            root_node, ["function_declaration", "function"]
        )
        for func_node in func_nodes:
            # Skip methods (those inside classes)
            if func_node.parent and func_node.parent.type in [
                "class_body",
                "method_definition",
            ]:
                continue
            func_entity = self._parse_function(func_node, content, file_entity)
            if func_entity:
                file_entity.functions.append(func_entity)

        # Extract arrow functions assigned to variables
        var_nodes = self._find_nodes_recursive(
            root_node, ["lexical_declaration", "variable_declaration"]
        )
        for var_node in var_nodes:
            func_entity = self._parse_arrow_function_variable(var_node, content, file_entity)
            if func_entity:
                file_entity.functions.append(func_entity)

        # Extract React components
        self._extract_react_components(root_node, content, file_entity)

    def _parse_import(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ImportEntity | None:
        """Parse an import statement."""
        # Get module path
        source_node = self._find_first_child(node, "string")
        if not source_node:
            return None

        module_path = self._get_node_text(source_node, content).strip("'\"")

        imported_names: list[str] = []
        alias: str | None = None
        is_type_only = False

        # Check for type-only import
        for child in node.children:
            if child.type == "type":
                is_type_only = True
                break

        # Get imported names
        import_clause = self._find_first_child(node, "import_clause")
        if import_clause:
            for child in import_clause.children:
                if child.type == "identifier":
                    # Default import
                    imported_names.append(self._get_node_text(child, content))
                elif child.type == "namespace_import":
                    # import * as name
                    name_node = self._find_first_child(child, "identifier")
                    if name_node:
                        alias = self._get_node_text(name_node, content)
                        imported_names.append("*")
                elif child.type == "named_imports":
                    # import { a, b }
                    specifiers = self._find_nodes_recursive(child, ["import_specifier"])
                    for spec in specifiers:
                        names = [
                            n for n in spec.children if n.type == "identifier"
                        ]
                        if names:
                            imported_names.append(self._get_node_text(names[0], content))

        return ImportEntity(
            id=create_entity_id(file_entity.file_path, EntityType.IMPORT, module_path),
            name=module_path.split("/")[-1],
            entity_type=EntityType.IMPORT,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            module_path=module_path,
            imported_names=imported_names,
            alias=alias,
            is_type_only=is_type_only,
        )

    def _parse_export(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Parse export statements to track exported names."""
        # This information can be stored in metadata
        pass

    def _parse_class(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse a class declaration."""
        name_node = self._find_first_child(node, "type_identifier")
        if not name_node:
            name_node = self._find_first_child(node, "identifier")
        if not name_node:
            return None

        class_name = self._get_node_text(name_node, content)

        # Check for extends
        extends: str | None = None
        heritage = self._find_first_child(node, "class_heritage")
        if heritage:
            extends_clause = self._find_first_child(heritage, "extends_clause")
            if extends_clause:
                type_node = self._find_first_child(extends_clause, "type_identifier")
                if type_node:
                    extends = self._get_node_text(type_node, content)

        # Check for implements
        implements: list[str] = []
        if heritage:
            impl_clause = self._find_first_child(heritage, "implements_clause")
            if impl_clause:
                types = self._find_nodes_recursive(impl_clause, ["type_identifier"])
                implements = [self._get_node_text(t, content) for t in types]

        # Check modifiers
        is_abstract = any(c.type == "abstract" for c in node.children)

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
        )

        # Parse class body
        body_node = self._find_first_child(node, "class_body")
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
        """Parse the body of a class."""
        for child in body_node.children:
            if child.type == "method_definition":
                method = self._parse_method(child, content, file_entity, class_entity)
                if method:
                    class_entity.methods.append(method)
            elif child.type in ["public_field_definition", "field_definition"]:
                prop = self._parse_property(child, content, file_entity, class_entity)
                if prop:
                    class_entity.properties.append(prop)

    def _parse_method(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> FunctionEntity | None:
        """Parse a method definition."""
        name_node = self._find_first_child(node, "property_identifier")
        if not name_node:
            return None

        method_name = self._get_node_text(name_node, content)

        # Get visibility
        visibility = Visibility.PUBLIC
        is_static = False
        is_async = False
        is_abstract = False

        for child in node.children:
            if child.type == "accessibility_modifier":
                vis_text = self._get_node_text(child, content).lower()
                if vis_text in ["private", "protected", "public"]:
                    visibility = Visibility(vis_text)
            elif child.type == "static":
                is_static = True
            elif child.type == "async":
                is_async = True
            elif child.type == "abstract":
                is_abstract = True

        # Get parameters
        params_node = self._find_first_child(node, "formal_parameters")
        parameters = self._parse_parameters(params_node, content) if params_node else []

        # Get return type
        return_type = self._parse_return_type(node, content)

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
            is_async=is_async,
            is_abstract=is_abstract,
        )

        # Extract calls
        body_node = self._find_first_child(node, "statement_block")
        if body_node:
            self._extract_calls(body_node, content, method_entity)

        return method_entity

    def _parse_property(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        class_entity: ClassEntity,
    ) -> PropertyEntity | None:
        """Parse a class property."""
        name_node = self._find_first_child(node, "property_identifier")
        if not name_node:
            return None

        prop_name = self._get_node_text(name_node, content)

        # Get visibility
        visibility = Visibility.PUBLIC
        is_static = False
        is_readonly = False

        for child in node.children:
            if child.type == "accessibility_modifier":
                vis_text = self._get_node_text(child, content).lower()
                if vis_text in ["private", "protected", "public"]:
                    visibility = Visibility(vis_text)
            elif child.type == "static":
                is_static = True
            elif child.type == "readonly":
                is_readonly = True

        # Get type
        type_hint: TypeInfo | None = None
        type_ann = self._find_first_child(node, "type_annotation")
        if type_ann:
            type_node = type_ann.children[-1] if type_ann.children else None
            if type_node:
                type_hint = TypeInfo(name=self._get_node_text(type_node, content))

        return PropertyEntity(
            id=create_entity_id(
                file_entity.file_path,
                EntityType.PROPERTY,
                class_entity.name,
                prop_name,
            ),
            name=prop_name,
            entity_type=EntityType.PROPERTY,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            type_hint=type_hint,
            visibility=visibility,
            is_static=is_static,
            is_readonly=is_readonly,
        )

    def _parse_interface(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse an interface declaration."""
        name_node = self._find_first_child(node, "type_identifier")
        if not name_node:
            return None

        interface_name = self._get_node_text(name_node, content)

        # Get extends
        extends: list[str] = []
        extends_clause = self._find_first_child(node, "extends_type_clause")
        if extends_clause:
            types = self._find_nodes_recursive(extends_clause, ["type_identifier"])
            extends = [self._get_node_text(t, content) for t in types]

        entity = ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.INTERFACE, interface_name),
            name=interface_name,
            entity_type=EntityType.INTERFACE,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            implements=extends,
            is_interface=True,
        )

        # Parse interface body
        body_node = self._find_first_child(node, "object_type")
        if body_node:
            for child in body_node.children:
                if child.type == "property_signature":
                    prop = self._parse_interface_property(child, content, file_entity, entity)
                    if prop:
                        entity.properties.append(prop)
                elif child.type == "method_signature":
                    method = self._parse_interface_method(child, content, file_entity, entity)
                    if method:
                        entity.methods.append(method)

        return entity

    def _parse_interface_property(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        interface_entity: ClassEntity,
    ) -> PropertyEntity | None:
        """Parse an interface property signature."""
        name_node = self._find_first_child(node, "property_identifier")
        if not name_node:
            return None

        prop_name = self._get_node_text(name_node, content)

        # Get type
        type_hint: TypeInfo | None = None
        type_ann = self._find_first_child(node, "type_annotation")
        if type_ann:
            type_node = type_ann.children[-1] if type_ann.children else None
            if type_node:
                type_hint = TypeInfo(name=self._get_node_text(type_node, content))

        return PropertyEntity(
            id=create_entity_id(
                file_entity.file_path,
                EntityType.PROPERTY,
                interface_entity.name,
                prop_name,
            ),
            name=prop_name,
            entity_type=EntityType.PROPERTY,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            type_hint=type_hint,
        )

    def _parse_interface_method(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
        interface_entity: ClassEntity,
    ) -> FunctionEntity | None:
        """Parse an interface method signature."""
        name_node = self._find_first_child(node, "property_identifier")
        if not name_node:
            return None

        method_name = self._get_node_text(name_node, content)

        # Get parameters
        params_node = self._find_first_child(node, "formal_parameters")
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
            is_abstract=True,
        )

    def _parse_type_alias(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> ClassEntity | None:
        """Parse a type alias declaration."""
        name_node = self._find_first_child(node, "type_identifier")
        if not name_node:
            return None

        type_name = self._get_node_text(name_node, content)

        return ClassEntity(
            id=create_entity_id(file_entity.file_path, EntityType.CLASS, type_name),
            name=type_name,
            entity_type=EntityType.CLASS,
            language=self.language,
            location=self._get_node_location(node, file_entity.file_path),
            source_code=self._get_node_text(node, content),
            docstring=self._get_docstring(node, content),
            metadata={"is_type_alias": True},
        )

    def _parse_function(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> FunctionEntity | None:
        """Parse a function declaration."""
        name_node = self._find_first_child(node, "identifier")
        if not name_node:
            return None

        func_name = self._get_node_text(name_node, content)

        # Check for async
        is_async = any(c.type == "async" for c in node.children)

        # Get parameters
        params_node = self._find_first_child(node, "formal_parameters")
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
            is_async=is_async,
        )

        # Extract calls
        body_node = self._find_first_child(node, "statement_block")
        if body_node:
            self._extract_calls(body_node, content, func_entity)

        return func_entity

    def _parse_arrow_function_variable(
        self,
        node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> FunctionEntity | None:
        """Parse an arrow function assigned to a variable."""
        # Find variable declarator
        declarators = self._find_nodes_recursive(node, ["variable_declarator"])
        for decl in declarators:
            name_node = self._find_first_child(decl, "identifier")
            arrow_func = self._find_first_child(decl, "arrow_function")

            if name_node and arrow_func:
                func_name = self._get_node_text(name_node, content)

                # Check for async
                is_async = any(c.type == "async" for c in arrow_func.children)

                # Get parameters
                params_node = self._find_first_child(arrow_func, "formal_parameters")
                parameters = (
                    self._parse_parameters(params_node, content) if params_node else []
                )

                # Get return type
                return_type = self._parse_return_type(arrow_func, content)

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
                    is_async=is_async,
                )

                # Extract calls
                body_node = self._find_first_child(arrow_func, "statement_block")
                if body_node:
                    self._extract_calls(body_node, content, func_entity)

                return func_entity

        return None

    def _parse_parameters(self, node: Node, content: str) -> list[Parameter]:
        """Parse function parameters."""
        parameters: list[Parameter] = []

        for child in node.children:
            if child.type in [
                "required_parameter",
                "optional_parameter",
                "rest_parameter",
            ]:
                param = self._parse_single_parameter(child, content)
                if param:
                    parameters.append(param)
            elif child.type == "identifier":
                # Simple parameter without type
                parameters.append(
                    Parameter(name=self._get_node_text(child, content))
                )

        return parameters

    def _parse_single_parameter(self, node: Node, content: str) -> Parameter | None:
        """Parse a single parameter."""
        # Handle destructuring patterns
        pattern = self._find_first_child(node, "object_pattern")
        if pattern:
            return Parameter(
                name=self._get_node_text(pattern, content),
                type_hint=self._get_param_type(node, content),
            )

        # Handle array destructuring
        array_pattern = self._find_first_child(node, "array_pattern")
        if array_pattern:
            return Parameter(
                name=self._get_node_text(array_pattern, content),
                type_hint=self._get_param_type(node, content),
            )

        # Regular parameter
        name_node = self._find_first_child(node, "identifier")
        if not name_node:
            return None

        name = self._get_node_text(name_node, content)
        type_hint = self._get_param_type(node, content)

        # Get default value
        default_value: str | None = None
        for i, child in enumerate(node.children):
            if child.type == "=":
                if i + 1 < len(node.children):
                    default_value = self._get_node_text(node.children[i + 1], content)
                break

        # Check for rest parameter
        is_variadic = node.type == "rest_parameter"

        return Parameter(
            name=name,
            type_hint=type_hint,
            default_value=default_value,
            is_variadic=is_variadic,
        )

    def _get_param_type(self, node: Node, content: str) -> str | None:
        """Get parameter type annotation."""
        type_ann = self._find_first_child(node, "type_annotation")
        if type_ann:
            type_node = type_ann.children[-1] if type_ann.children else None
            if type_node:
                return self._get_node_text(type_node, content)
        return None

    def _parse_return_type(self, node: Node, content: str) -> TypeInfo | None:
        """Parse function return type."""
        type_ann = self._find_first_child(node, "type_annotation")
        if type_ann:
            type_node = type_ann.children[-1] if type_ann.children else None
            if type_node:
                return TypeInfo(name=self._get_node_text(type_node, content))
        return None

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

    def _extract_react_components(
        self,
        root_node: Node,
        content: str,
        file_entity: FileEntity,
    ) -> None:
        """Extract React components from the file."""
        # Look for functions that return JSX
        for func in file_entity.functions:
            if self._is_react_component(func, content):
                component = self._create_component_entity(func, content, file_entity)
                file_entity.components.append(component)

        # Look for arrow functions that return JSX
        func_nodes = self._find_nodes_recursive(
            root_node, ["lexical_declaration", "variable_declaration"]
        )
        for node in func_nodes:
            declarators = self._find_nodes_recursive(node, ["variable_declarator"])
            for decl in declarators:
                arrow_func = self._find_first_child(decl, "arrow_function")
                if arrow_func:
                    body = (
                        self._find_first_child(arrow_func, "statement_block")
                        or self._find_first_child(arrow_func, "jsx_element")
                        or self._find_first_child(arrow_func, "jsx_fragment")
                    )
                    if body:
                        jsx_elements = self._find_nodes_recursive(
                            body if body.type == "statement_block" else arrow_func,
                            ["jsx_element", "jsx_fragment", "jsx_self_closing_element"],
                        )
                        if jsx_elements:
                            name_node = self._find_first_child(decl, "identifier")
                            if name_node:
                                comp_name = self._get_node_text(name_node, content)
                                # Check if name starts with uppercase (React convention)
                                if comp_name and comp_name[0].isupper():
                                    component = ComponentEntity(
                                        id=create_entity_id(
                                            file_entity.file_path,
                                            EntityType.COMPONENT,
                                            comp_name,
                                        ),
                                        name=comp_name,
                                        entity_type=EntityType.COMPONENT,
                                        language=self.language,
                                        location=self._get_node_location(
                                            node, file_entity.file_path
                                        ),
                                        source_code=self._get_node_text(node, content),
                                        is_functional=True,
                                    )
                                    self._extract_hooks(arrow_func, content, component)
                                    self._extract_child_components(
                                        arrow_func, content, component
                                    )
                                    file_entity.components.append(component)

    def _is_react_component(self, func: FunctionEntity, content: str) -> bool:
        """Check if a function is a React component."""
        # React components start with uppercase
        if not func.name or not func.name[0].isupper():
            return False

        # Check if the function returns JSX
        return "jsx" in func.source_code.lower() or "<" in func.source_code

    def _create_component_entity(
        self,
        func: FunctionEntity,
        content: str,
        file_entity: FileEntity,
    ) -> ComponentEntity:
        """Create a ComponentEntity from a function."""
        component = ComponentEntity(
            id=create_entity_id(file_entity.file_path, EntityType.COMPONENT, func.name),
            name=func.name,
            entity_type=EntityType.COMPONENT,
            language=self.language,
            location=func.location,
            source_code=func.source_code,
            docstring=func.docstring,
            is_functional=True,
        )

        # Try to find props type
        if func.parameters:
            first_param = func.parameters[0]
            if first_param.type_hint:
                component.props_type = first_param.type_hint

        return component

    def _extract_hooks(
        self,
        node: Node,
        content: str,
        component: ComponentEntity,
    ) -> None:
        """Extract React hooks used in a component."""
        call_expressions = self._find_nodes_recursive(node, ["call_expression"])

        hook_pattern = re.compile(r"^use[A-Z]")

        for call in call_expressions:
            func_node = call.children[0] if call.children else None
            if func_node:
                func_name = self._get_node_text(func_node, content)
                if hook_pattern.match(func_name):
                    component.hooks_used.append(func_name)

    def _extract_child_components(
        self,
        node: Node,
        content: str,
        component: ComponentEntity,
    ) -> None:
        """Extract child components rendered by this component."""
        jsx_elements = self._find_nodes_recursive(
            node, ["jsx_element", "jsx_self_closing_element"]
        )

        for jsx in jsx_elements:
            tag_node = (
                self._find_first_child(jsx, "jsx_opening_element")
                or self._find_first_child(jsx, "jsx_self_closing_element")
            )
            if tag_node:
                name_node = self._find_first_child(tag_node, "identifier")
                if name_node:
                    tag_name = self._get_node_text(name_node, content)
                    # Components start with uppercase
                    if tag_name and tag_name[0].isupper():
                        if tag_name not in component.child_components:
                            component.child_components.append(tag_name)


@register_parser(CodeLanguage.TYPESCRIPT)
class TypeScriptParser(TypeScriptParserBase):
    """Parser for TypeScript source code."""

    @property
    def language(self) -> CodeLanguage:
        return CodeLanguage.TYPESCRIPT

    @property
    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx"]

    def _init_language(self) -> Language:
        return Language(tree_sitter_typescript.language_typescript())


@register_parser(CodeLanguage.TSX)
class TSXParser(TypeScriptParserBase):
    """Parser for TSX (TypeScript + JSX) source code."""

    @property
    def language(self) -> CodeLanguage:
        return CodeLanguage.TSX

    @property
    def file_extensions(self) -> list[str]:
        return [".tsx"]

    def _init_language(self) -> Language:
        return Language(tree_sitter_typescript.language_tsx())


@register_parser(CodeLanguage.JAVASCRIPT)
class JavaScriptParser(TypeScriptParserBase):
    """Parser for JavaScript source code."""

    @property
    def language(self) -> CodeLanguage:
        return CodeLanguage.JAVASCRIPT

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

    def _init_language(self) -> Language:
        # JavaScript uses TypeScript parser with appropriate settings
        return Language(tree_sitter_typescript.language_typescript())
