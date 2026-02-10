"""Tests for codebase_analyzer/indexer/models/entities.py - Entity data models."""

from pathlib import Path

import pytest

from codebase_analyzer.indexer.models.entities import (
    ClassEntity,
    CodeEntity,
    ComponentEntity,
    ConstantEntity,
    EntityType,
    FileEntity,
    FunctionEntity,
    ImportEntity,
    Language,
    Parameter,
    PropertyEntity,
    RouteEntity,
    SourceLocation,
    TypeInfo,
    Visibility,
    create_entity_id,
)

# ============================================================================
# Enum Tests
# ============================================================================

class TestEntityType:
    """Tests for EntityType enum."""

    def test_all_entity_types_defined(self):
        """Test all expected entity types are defined."""
        expected_types = {
            "FILE",
            "CLASS",
            "INTERFACE",
            "TRAIT",
            "STRUCT",
            "FUNCTION",
            "METHOD",
            "PROPERTY",
            "CONSTANT",
            "VARIABLE",
            "IMPORT",
            "NAMESPACE",
            "PACKAGE",
            "MODULE",
            "COMPONENT",
            "HOOK",
            "ROUTE",
        }

        actual_types = {t.name for t in EntityType}
        assert actual_types == expected_types

    def test_entity_type_values(self):
        """Test entity type values are lowercase strings."""
        assert EntityType.FILE.value == "file"
        assert EntityType.CLASS.value == "class"
        assert EntityType.FUNCTION.value == "function"
        assert EntityType.COMPONENT.value == "component"

    def test_entity_type_is_string_enum(self):
        """Test EntityType is a string enum."""
        assert isinstance(EntityType.CLASS, str)
        assert EntityType.CLASS == "class"

class TestVisibility:
    """Tests for Visibility enum."""

    def test_all_visibilities_defined(self):
        """Test all visibility modifiers are defined."""
        expected = {"PUBLIC", "PROTECTED", "PRIVATE", "INTERNAL"}
        actual = {v.name for v in Visibility}
        assert actual == expected

    def test_visibility_values(self):
        """Test visibility values."""
        assert Visibility.PUBLIC.value == "public"
        assert Visibility.PRIVATE.value == "private"
        assert Visibility.PROTECTED.value == "protected"
        assert Visibility.INTERNAL.value == "internal"

class TestLanguage:
    """Tests for Language enum."""

    def test_all_languages_defined(self):
        """Test all supported languages are defined."""
        expected = {"PHP", "GO", "TYPESCRIPT", "JAVASCRIPT", "TSX", "JSX"}
        actual = {lang.name for lang in Language}
        assert actual == expected

    def test_language_values(self):
        """Test language values are lowercase."""
        assert Language.PHP.value == "php"
        assert Language.GO.value == "go"
        assert Language.TYPESCRIPT.value == "typescript"
        assert Language.TSX.value == "tsx"

# ============================================================================
# SourceLocation Tests
# ============================================================================

class TestSourceLocation:
    """Tests for SourceLocation dataclass."""

    def test_basic_creation(self):
        """Test creating a SourceLocation."""
        loc = SourceLocation(
            file_path=Path("/test/file.go"),
            start_line=10,
            end_line=20,
        )

        assert loc.file_path == Path("/test/file.go")
        assert loc.start_line == 10
        assert loc.end_line == 20
        assert loc.start_column == 0
        assert loc.end_column == 0

    def test_with_columns(self):
        """Test SourceLocation with column information."""
        loc = SourceLocation(
            file_path=Path("/test/file.ts"),
            start_line=5,
            end_line=15,
            start_column=4,
            end_column=32,
        )

        assert loc.start_column == 4
        assert loc.end_column == 32

    def test_line_count_property(self):
        """Test line_count property calculation."""
        # Single line
        loc1 = SourceLocation(
            file_path=Path("/test.go"),
            start_line=1,
            end_line=1,
        )
        assert loc1.line_count == 1

        # Multiple lines
        loc2 = SourceLocation(
            file_path=Path("/test.go"),
            start_line=10,
            end_line=25,
        )
        assert loc2.line_count == 16

    def test_str_representation(self):
        """Test string representation."""
        loc = SourceLocation(
            file_path=Path("/src/User.php"),
            start_line=10,
            end_line=50,
        )

        str_repr = str(loc)
        assert "/src/User.php" in str_repr
        assert "10" in str_repr
        assert "50" in str_repr
        assert str_repr == "/src/User.php:10-50"

# ============================================================================
# Parameter Tests
# ============================================================================

class TestParameter:
    """Tests for Parameter dataclass."""

    def test_basic_parameter(self):
        """Test creating a basic parameter."""
        param = Parameter(name="id")

        assert param.name == "id"
        assert param.type_hint is None
        assert param.default_value is None
        assert param.is_variadic is False
        assert param.is_reference is False

    def test_typed_parameter(self):
        """Test parameter with type hint."""
        param = Parameter(name="userId", type_hint="int64")

        assert param.name == "userId"
        assert param.type_hint == "int64"

    def test_parameter_with_default(self):
        """Test parameter with default value."""
        param = Parameter(
            name="limit",
            type_hint="int",
            default_value="10",
        )

        assert param.default_value == "10"

    def test_variadic_parameter(self):
        """Test variadic parameter (Go ...)."""
        param = Parameter(
            name="args",
            type_hint="string",
            is_variadic=True,
        )

        assert param.is_variadic is True

    def test_reference_parameter(self):
        """Test PHP reference parameter."""
        param = Parameter(
            name="data",
            type_hint="array",
            is_reference=True,
        )

        assert param.is_reference is True

# ============================================================================
# TypeInfo Tests
# ============================================================================

class TestTypeInfo:
    """Tests for TypeInfo dataclass."""

    def test_simple_type(self):
        """Test simple type without modifiers."""
        type_info = TypeInfo(name="string")

        assert type_info.name == "string"
        assert type_info.is_nullable is False
        assert type_info.is_array is False
        assert type_info.is_generic is False
        assert type_info.generic_params == []

    def test_nullable_type(self):
        """Test nullable type."""
        type_info = TypeInfo(name="User", is_nullable=True)

        assert type_info.is_nullable is True
        assert str(type_info) == "?User"

    def test_array_type(self):
        """Test array type."""
        type_info = TypeInfo(name="string", is_array=True)

        assert type_info.is_array is True
        assert str(type_info) == "string[]"

    def test_generic_type(self):
        """Test generic type."""
        type_info = TypeInfo(
            name="Map",
            is_generic=True,
            generic_params=["string", "int"],
        )

        assert type_info.is_generic is True
        assert type_info.generic_params == ["string", "int"]
        assert str(type_info) == "Map<string, int>"

    def test_nullable_array_type(self):
        """Test nullable array type."""
        type_info = TypeInfo(
            name="User",
            is_nullable=True,
            is_array=True,
        )

        # Nullable applies to the whole type
        assert str(type_info) == "?User[]"

    def test_complex_generic_type(self):
        """Test complex generic type with array and nullable."""
        type_info = TypeInfo(
            name="Promise",
            is_nullable=True,
            is_generic=True,
            generic_params=["User"],
        )

        assert str(type_info) == "?Promise<User>"

# ============================================================================
# CodeEntity Tests
# ============================================================================

class TestCodeEntity:
    """Tests for CodeEntity base class."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/test/file.go"),
            start_line=1,
            end_line=10,
        )

    def test_basic_creation(self, sample_location):
        """Test creating a CodeEntity."""
        entity = CodeEntity(
            id="test/file.go:function:main",
            name="main",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
        )

        assert entity.id == "test/file.go:function:main"
        assert entity.name == "main"
        assert entity.entity_type == EntityType.FUNCTION
        assert entity.language == Language.GO
        assert entity.location == sample_location

    def test_default_values(self, sample_location):
        """Test CodeEntity default values."""
        entity = CodeEntity(
            id="test:entity",
            name="test",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
        )

        assert entity.docstring is None
        assert entity.comments == []
        assert entity.source_code == ""
        assert entity.metadata == {}

    def test_with_documentation(self, sample_location):
        """Test CodeEntity with documentation."""
        entity = CodeEntity(
            id="test:entity",
            name="test",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            docstring="This is a test function.",
            comments=["// TODO: implement"],
        )

        assert entity.docstring == "This is a test function."
        assert entity.comments == ["// TODO: implement"]

    def test_qualified_name_property(self, sample_location):
        """Test qualified_name returns id."""
        entity = CodeEntity(
            id="src/User.php:class:User:method:getName",
            name="getName",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
        )

        assert entity.qualified_name == "src/User.php:class:User:method:getName"

    def test_metadata_storage(self, sample_location):
        """Test metadata dictionary."""
        entity = CodeEntity(
            id="test:entity",
            name="test",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            metadata={"complexity": 5, "lines": 20},
        )

        assert entity.metadata["complexity"] == 5
        assert entity.metadata["lines"] == 20

# ============================================================================
# FunctionEntity Tests
# ============================================================================

class TestFunctionEntity:
    """Tests for FunctionEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/test/service.ts"),
            start_line=10,
            end_line=25,
        )

    def test_basic_function(self, sample_location):
        """Test creating a basic function entity."""
        func = FunctionEntity(
            id="test:function:calculate",
            name="calculate",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
        )

        assert func.name == "calculate"
        assert func.parameters == []
        assert func.return_type is None
        assert func.is_async is False
        assert func.is_static is False
        assert func.is_abstract is False
        assert func.visibility == Visibility.PUBLIC

    def test_function_with_parameters(self, sample_location):
        """Test function with parameters."""
        func = FunctionEntity(
            id="test:function:add",
            name="add",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            parameters=[
                Parameter(name="a", type_hint="int"),
                Parameter(name="b", type_hint="int"),
            ],
            return_type=TypeInfo(name="int"),
        )

        assert len(func.parameters) == 2
        assert func.parameters[0].name == "a"
        assert func.parameters[1].name == "b"
        assert func.return_type.name == "int"

    def test_async_function(self, sample_location):
        """Test async function."""
        func = FunctionEntity(
            id="test:function:fetchUser",
            name="fetchUser",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            is_async=True,
            return_type=TypeInfo(name="Promise", generic_params=["User"]),
        )

        assert func.is_async is True
        assert func.return_type.name == "Promise"

    def test_method_with_visibility(self, sample_location):
        """Test method with visibility modifier."""
        method = FunctionEntity(
            id="test:class:User:method:setPassword",
            name="setPassword",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PRIVATE,
            is_static=False,
        )

        assert method.visibility == Visibility.PRIVATE
        assert method.entity_type == EntityType.METHOD

    def test_static_method(self, sample_location):
        """Test static method."""
        method = FunctionEntity(
            id="test:class:Factory:method:create",
            name="create",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            is_static=True,
        )

        assert method.is_static is True

    def test_abstract_method(self, sample_location):
        """Test abstract method."""
        method = FunctionEntity(
            id="test:interface:Repository:method:find",
            name="find",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            is_abstract=True,
        )

        assert method.is_abstract is True

    def test_function_calls_tracking(self, sample_location):
        """Test tracking function calls."""
        func = FunctionEntity(
            id="test:function:process",
            name="process",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            calls=["validate", "transform", "save", "log"],
        )

        assert "validate" in func.calls
        assert len(func.calls) == 4

    def test_sql_queries_tracking(self, sample_location):
        """Test tracking SQL queries."""
        func = FunctionEntity(
            id="test:function:getUsers",
            name="getUsers",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            sql_queries=[
                "SELECT * FROM users WHERE active = true",
                "SELECT COUNT(*) FROM users",
            ],
        )

        assert len(func.sql_queries) == 2
        assert "SELECT * FROM users" in func.sql_queries[0]

    def test_exception_tracking(self, sample_location):
        """Test tracking exceptions."""
        func = FunctionEntity(
            id="test:function:risky",
            name="risky",
            entity_type=EntityType.FUNCTION,
            language=Language.PHP,
            location=sample_location,
            exceptions_thrown=["InvalidArgumentException", "RuntimeException"],
            exceptions_caught=["Exception"],
        )

        assert len(func.exceptions_thrown) == 2
        assert "Exception" in func.exceptions_caught

    def test_signature_property_simple(self, sample_location):
        """Test signature property for simple function."""
        func = FunctionEntity(
            id="test:function:greet",
            name="greet",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
        )

        assert func.signature == "greet()"

    def test_signature_property_with_params(self, sample_location):
        """Test signature property with parameters."""
        func = FunctionEntity(
            id="test:function:add",
            name="add",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=sample_location,
            parameters=[
                Parameter(name="a", type_hint="int"),
                Parameter(name="b", type_hint="int"),
            ],
            return_type=TypeInfo(name="int"),
        )

        sig = func.signature
        assert "add(" in sig
        assert "int a" in sig
        assert "int b" in sig
        assert "-> int" in sig

    def test_signature_with_defaults(self, sample_location):
        """Test signature with default parameter values."""
        func = FunctionEntity(
            id="test:function:paginate",
            name="paginate",
            entity_type=EntityType.FUNCTION,
            language=Language.TYPESCRIPT,
            location=sample_location,
            parameters=[
                Parameter(name="page", type_hint="number", default_value="1"),
                Parameter(name="limit", type_hint="number", default_value="10"),
            ],
        )

        sig = func.signature
        assert "= 1" in sig
        assert "= 10" in sig

# ============================================================================
# ClassEntity Tests
# ============================================================================

class TestClassEntity:
    """Tests for ClassEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/User.php"),
            start_line=10,
            end_line=100,
        )

    def test_basic_class(self, sample_location):
        """Test creating a basic class entity."""
        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
        )

        assert cls.name == "User"
        assert cls.entity_type == EntityType.CLASS
        assert cls.extends is None
        assert cls.implements == []
        assert cls.uses_traits == []
        assert cls.methods == []
        assert cls.properties == []
        assert cls.constants == []

    def test_class_with_inheritance(self, sample_location):
        """Test class with inheritance."""
        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            extends="Model",
            implements=["UserInterface", "Serializable"],
        )

        assert cls.extends == "Model"
        assert "UserInterface" in cls.implements
        assert "Serializable" in cls.implements

    def test_class_with_traits(self, sample_location):
        """Test PHP class with traits."""
        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            uses_traits=["HasTimestamps", "SoftDeletes"],
        )

        assert "HasTimestamps" in cls.uses_traits
        assert len(cls.uses_traits) == 2

    def test_interface_entity(self, sample_location):
        """Test interface entity."""
        interface = ClassEntity(
            id="src/UserInterface.php:interface:UserInterface",
            name="UserInterface",
            entity_type=EntityType.INTERFACE,
            language=Language.PHP,
            location=sample_location,
            is_interface=True,
        )

        assert interface.is_interface is True
        assert interface.entity_type == EntityType.INTERFACE

    def test_trait_entity(self, sample_location):
        """Test trait entity."""
        trait = ClassEntity(
            id="src/HasTimestamps.php:trait:HasTimestamps",
            name="HasTimestamps",
            entity_type=EntityType.TRAIT,
            language=Language.PHP,
            location=sample_location,
            is_trait=True,
        )

        assert trait.is_trait is True

    def test_struct_entity(self, sample_location):
        """Test Go struct entity."""
        struct = ClassEntity(
            id="src/user.go:struct:User",
            name="User",
            entity_type=EntityType.STRUCT,
            language=Language.GO,
            location=SourceLocation(
                file_path=Path("/src/user.go"),
                start_line=10,
                end_line=20,
            ),
        )

        assert struct.entity_type == EntityType.STRUCT
        assert struct.language == Language.GO

    def test_abstract_class(self, sample_location):
        """Test abstract class."""
        cls = ClassEntity(
            id="src/BaseModel.php:class:BaseModel",
            name="BaseModel",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            is_abstract=True,
        )

        assert cls.is_abstract is True

    def test_final_class(self, sample_location):
        """Test final class."""
        cls = ClassEntity(
            id="src/FinalClass.php:class:FinalClass",
            name="FinalClass",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            is_final=True,
        )

        assert cls.is_final is True

    def test_class_with_methods(self, sample_location):
        """Test class with methods."""
        method1 = FunctionEntity(
            id="src/User.php:class:User:method:getName",
            name="getName",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PUBLIC,
        )
        method2 = FunctionEntity(
            id="src/User.php:class:User:method:setPassword",
            name="setPassword",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PRIVATE,
        )

        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            methods=[method1, method2],
        )

        assert len(cls.methods) == 2
        assert cls.methods[0].name == "getName"

    def test_public_methods_property(self, sample_location):
        """Test public_methods property filters correctly."""
        public_method = FunctionEntity(
            id="test:method:public",
            name="publicMethod",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PUBLIC,
        )
        private_method = FunctionEntity(
            id="test:method:private",
            name="privateMethod",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PRIVATE,
        )
        protected_method = FunctionEntity(
            id="test:method:protected",
            name="protectedMethod",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PROTECTED,
        )

        cls = ClassEntity(
            id="test:class:Test",
            name="Test",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            methods=[public_method, private_method, protected_method],
        )

        public_methods = cls.public_methods
        assert len(public_methods) == 1
        assert public_methods[0].name == "publicMethod"

    def test_class_with_properties(self, sample_location):
        """Test class with properties."""
        prop = PropertyEntity(
            id="src/User.php:class:User:property:name",
            name="name",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            type_hint=TypeInfo(name="string"),
            visibility=Visibility.PRIVATE,
        )

        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            properties=[prop],
        )

        assert len(cls.properties) == 1
        assert cls.properties[0].name == "name"

    def test_public_properties_property(self, sample_location):
        """Test public_properties property filters correctly."""
        public_prop = PropertyEntity(
            id="test:property:public",
            name="publicProp",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PUBLIC,
        )
        private_prop = PropertyEntity(
            id="test:property:private",
            name="privateProp",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PRIVATE,
        )

        cls = ClassEntity(
            id="test:class:Test",
            name="Test",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            properties=[public_prop, private_prop],
        )

        public_props = cls.public_properties
        assert len(public_props) == 1
        assert public_props[0].name == "publicProp"

# ============================================================================
# PropertyEntity Tests
# ============================================================================

class TestPropertyEntity:
    """Tests for PropertyEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/User.php"),
            start_line=15,
            end_line=15,
        )

    def test_basic_property(self, sample_location):
        """Test creating a basic property."""
        prop = PropertyEntity(
            id="src/User.php:class:User:property:id",
            name="id",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
        )

        assert prop.name == "id"
        assert prop.type_hint is None
        assert prop.default_value is None
        assert prop.visibility == Visibility.PUBLIC
        assert prop.is_static is False
        assert prop.is_readonly is False

    def test_typed_property(self, sample_location):
        """Test property with type hint."""
        prop = PropertyEntity(
            id="test:property:name",
            name="name",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            type_hint=TypeInfo(name="string"),
        )

        assert prop.type_hint.name == "string"

    def test_property_with_default(self, sample_location):
        """Test property with default value."""
        prop = PropertyEntity(
            id="test:property:count",
            name="count",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            type_hint=TypeInfo(name="int"),
            default_value="0",
        )

        assert prop.default_value == "0"

    def test_private_static_property(self, sample_location):
        """Test private static property."""
        prop = PropertyEntity(
            id="test:property:instance",
            name="instance",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            visibility=Visibility.PRIVATE,
            is_static=True,
        )

        assert prop.visibility == Visibility.PRIVATE
        assert prop.is_static is True

    def test_readonly_property(self, sample_location):
        """Test readonly property (PHP 8.1+)."""
        prop = PropertyEntity(
            id="test:property:createdAt",
            name="createdAt",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
            is_readonly=True,
        )

        assert prop.is_readonly is True

# ============================================================================
# ConstantEntity Tests
# ============================================================================

class TestConstantEntity:
    """Tests for ConstantEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/config.go"),
            start_line=5,
            end_line=5,
        )

    def test_basic_constant(self, sample_location):
        """Test creating a basic constant."""
        const = ConstantEntity(
            id="src/config.go:constant:MaxSize",
            name="MaxSize",
            entity_type=EntityType.CONSTANT,
            language=Language.GO,
            location=sample_location,
            value="100",
        )

        assert const.name == "MaxSize"
        assert const.value == "100"
        assert const.type_hint is None

    def test_typed_constant(self, sample_location):
        """Test constant with type hint."""
        const = ConstantEntity(
            id="test:constant:PI",
            name="PI",
            entity_type=EntityType.CONSTANT,
            language=Language.GO,
            location=sample_location,
            value="3.14159",
            type_hint=TypeInfo(name="float64"),
        )

        assert const.type_hint.name == "float64"
        assert const.value == "3.14159"

# ============================================================================
# ImportEntity Tests
# ============================================================================

class TestImportEntity:
    """Tests for ImportEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/main.ts"),
            start_line=1,
            end_line=1,
        )

    def test_basic_import(self, sample_location):
        """Test creating a basic import."""
        imp = ImportEntity(
            id="src/main.ts:import:react",
            name="react",
            entity_type=EntityType.IMPORT,
            language=Language.TYPESCRIPT,
            location=sample_location,
            module_path="react",
        )

        assert imp.module_path == "react"
        assert imp.imported_names == []
        assert imp.alias is None
        assert imp.is_type_only is False

    def test_named_import(self, sample_location):
        """Test named import."""
        imp = ImportEntity(
            id="src/main.ts:import:nestjs",
            name="nestjs",
            entity_type=EntityType.IMPORT,
            language=Language.TYPESCRIPT,
            location=sample_location,
            module_path="@nestjs/common",
            imported_names=["Injectable", "Controller", "Get"],
        )

        assert "@nestjs/common" in imp.module_path
        assert "Injectable" in imp.imported_names
        assert len(imp.imported_names) == 3

    def test_aliased_import(self, sample_location):
        """Test import with alias."""
        imp = ImportEntity(
            id="src/main.ts:import:lodash",
            name="lodash",
            entity_type=EntityType.IMPORT,
            language=Language.TYPESCRIPT,
            location=sample_location,
            module_path="lodash",
            alias="_",
        )

        assert imp.alias == "_"

    def test_type_only_import(self, sample_location):
        """Test TypeScript type-only import."""
        imp = ImportEntity(
            id="src/main.ts:import:types",
            name="types",
            entity_type=EntityType.IMPORT,
            language=Language.TYPESCRIPT,
            location=sample_location,
            module_path="./types",
            imported_names=["User", "Product"],
            is_type_only=True,
        )

        assert imp.is_type_only is True

# ============================================================================
# FileEntity Tests
# ============================================================================

class TestFileEntity:
    """Tests for FileEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/User.php"),
            start_line=1,
            end_line=100,
        )

    def test_basic_file_entity(self, sample_location):
        """Test creating a basic file entity."""
        file_entity = FileEntity(
            id="src/User.php:file",
            name="User.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=sample_location,
            file_path=Path("/src/User.php"),
            file_size=2048,
            line_count=100,
        )

        assert file_entity.file_path == Path("/src/User.php")
        assert file_entity.file_size == 2048
        assert file_entity.line_count == 100
        assert file_entity.namespace is None
        assert file_entity.package is None

    def test_file_with_namespace(self, sample_location):
        """Test file with namespace (PHP)."""
        file_entity = FileEntity(
            id="src/User.php:file",
            name="User.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=sample_location,
            file_path=Path("/src/User.php"),
            namespace="App\\Models",
        )

        assert file_entity.namespace == "App\\Models"

    def test_file_with_package(self, sample_location):
        """Test file with package (Go)."""
        go_location = SourceLocation(
            file_path=Path("/src/user.go"),
            start_line=1,
            end_line=50,
        )
        file_entity = FileEntity(
            id="src/user.go:file",
            name="user.go",
            entity_type=EntityType.FILE,
            language=Language.GO,
            location=go_location,
            file_path=Path("/src/user.go"),
            package="models",
        )

        assert file_entity.package == "models"

    def test_file_with_imports(self, sample_location):
        """Test file with imports."""
        import1 = ImportEntity(
            id="src/User.php:import:1",
            name="Model",
            entity_type=EntityType.IMPORT,
            language=Language.PHP,
            location=sample_location,
            module_path="Illuminate\\Database\\Eloquent\\Model",
        )
        import2 = ImportEntity(
            id="src/User.php:import:2",
            name="UserInterface",
            entity_type=EntityType.IMPORT,
            language=Language.PHP,
            location=sample_location,
            module_path="App\\Interfaces\\UserInterface",
        )

        file_entity = FileEntity(
            id="src/User.php:file",
            name="User.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=sample_location,
            file_path=Path("/src/User.php"),
            imports=[import1, import2],
        )

        assert len(file_entity.imports) == 2

    def test_file_with_classes(self, sample_location):
        """Test file with classes."""
        cls = ClassEntity(
            id="src/User.php:class:User",
            name="User",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
        )

        file_entity = FileEntity(
            id="src/User.php:file",
            name="User.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=sample_location,
            file_path=Path("/src/User.php"),
            classes=[cls],
        )

        assert len(file_entity.classes) == 1
        assert file_entity.classes[0].name == "User"

    def test_file_with_functions(self, sample_location):
        """Test file with standalone functions."""
        func = FunctionEntity(
            id="src/helpers.go:function:calculateSum",
            name="calculateSum",
            entity_type=EntityType.FUNCTION,
            language=Language.GO,
            location=SourceLocation(
                file_path=Path("/src/helpers.go"),
                start_line=10,
                end_line=20,
            ),
        )

        file_entity = FileEntity(
            id="src/helpers.go:file",
            name="helpers.go",
            entity_type=EntityType.FILE,
            language=Language.GO,
            location=SourceLocation(
                file_path=Path("/src/helpers.go"),
                start_line=1,
                end_line=50,
            ),
            file_path=Path("/src/helpers.go"),
            functions=[func],
        )

        assert len(file_entity.functions) == 1

    def test_all_entities_property(self, sample_location):
        """Test all_entities property returns all nested entities."""
        method = FunctionEntity(
            id="test:method",
            name="method",
            entity_type=EntityType.METHOD,
            language=Language.PHP,
            location=sample_location,
        )
        prop = PropertyEntity(
            id="test:property",
            name="prop",
            entity_type=EntityType.PROPERTY,
            language=Language.PHP,
            location=sample_location,
        )
        const = ConstantEntity(
            id="test:constant",
            name="CONST",
            entity_type=EntityType.CONSTANT,
            language=Language.PHP,
            location=sample_location,
        )
        cls = ClassEntity(
            id="test:class",
            name="TestClass",
            entity_type=EntityType.CLASS,
            language=Language.PHP,
            location=sample_location,
            methods=[method],
            properties=[prop],
            constants=[const],
        )
        imp = ImportEntity(
            id="test:import",
            name="import",
            entity_type=EntityType.IMPORT,
            language=Language.PHP,
            location=sample_location,
        )
        func = FunctionEntity(
            id="test:function",
            name="func",
            entity_type=EntityType.FUNCTION,
            language=Language.PHP,
            location=sample_location,
        )

        file_entity = FileEntity(
            id="test:file",
            name="test.php",
            entity_type=EntityType.FILE,
            language=Language.PHP,
            location=sample_location,
            file_path=Path("/test.php"),
            imports=[imp],
            classes=[cls],
            functions=[func],
            constants=[const],
        )

        all_entities = file_entity.all_entities

        # Should include: file itself, import, class, method, property, class constant, function, file constant
        assert len(all_entities) >= 7

        # Verify types are present
        entity_types = [e.entity_type for e in all_entities]
        assert EntityType.FILE in entity_types
        assert EntityType.CLASS in entity_types
        assert EntityType.METHOD in entity_types
        assert EntityType.PROPERTY in entity_types
        assert EntityType.IMPORT in entity_types
        assert EntityType.FUNCTION in entity_types

# ============================================================================
# ComponentEntity Tests
# ============================================================================

class TestComponentEntity:
    """Tests for React ComponentEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/UserProfile.tsx"),
            start_line=10,
            end_line=50,
        )

    def test_basic_component(self, sample_location):
        """Test creating a basic component."""
        component = ComponentEntity(
            id="src/UserProfile.tsx:component:UserProfile",
            name="UserProfile",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
        )

        assert component.name == "UserProfile"
        assert component.is_functional is True
        assert component.props_type is None
        assert component.hooks_used == []
        assert component.child_components == []
        assert component.state_variables == []

    def test_component_with_props(self, sample_location):
        """Test component with props type."""
        component = ComponentEntity(
            id="src/UserProfile.tsx:component:UserProfile",
            name="UserProfile",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
            props_type="UserProfileProps",
        )

        assert component.props_type == "UserProfileProps"

    def test_component_with_hooks(self, sample_location):
        """Test component with React hooks."""
        component = ComponentEntity(
            id="src/UserProfile.tsx:component:UserProfile",
            name="UserProfile",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
            hooks_used=["useState", "useEffect", "useCallback", "useMemo"],
        )

        assert "useState" in component.hooks_used
        assert "useEffect" in component.hooks_used
        assert len(component.hooks_used) == 4

    def test_component_with_children(self, sample_location):
        """Test component with child components."""
        component = ComponentEntity(
            id="src/UserProfile.tsx:component:UserProfile",
            name="UserProfile",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
            child_components=["Avatar", "UserCard", "Button"],
        )

        assert "Avatar" in component.child_components
        assert len(component.child_components) == 3

    def test_component_with_state(self, sample_location):
        """Test component with state variables."""
        component = ComponentEntity(
            id="src/UserProfile.tsx:component:UserProfile",
            name="UserProfile",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
            state_variables=["isLoading", "userData", "error"],
        )

        assert "isLoading" in component.state_variables
        assert len(component.state_variables) == 3

    def test_class_component(self, sample_location):
        """Test class-based component."""
        component = ComponentEntity(
            id="src/LegacyComponent.tsx:component:LegacyComponent",
            name="LegacyComponent",
            entity_type=EntityType.COMPONENT,
            language=Language.TSX,
            location=sample_location,
            is_functional=False,
        )

        assert component.is_functional is False

# ============================================================================
# RouteEntity Tests
# ============================================================================

class TestRouteEntity:
    """Tests for RouteEntity."""

    @pytest.fixture
    def sample_location(self):
        return SourceLocation(
            file_path=Path("/src/routes/user.ts"),
            start_line=10,
            end_line=15,
        )

    def test_basic_route(self, sample_location):
        """Test creating a basic route."""
        route = RouteEntity(
            id="src/routes/user.ts:route:getUsers",
            name="getUsers",
            entity_type=EntityType.ROUTE,
            language=Language.TYPESCRIPT,
            location=sample_location,
            http_method="GET",
            path="/api/users",
            handler="UserController.getAll",
        )

        assert route.http_method == "GET"
        assert route.path == "/api/users"
        assert route.handler == "UserController.getAll"

    def test_route_with_middleware(self, sample_location):
        """Test route with middleware."""
        route = RouteEntity(
            id="src/routes/user.ts:route:createUser",
            name="createUser",
            entity_type=EntityType.ROUTE,
            language=Language.TYPESCRIPT,
            location=sample_location,
            http_method="POST",
            path="/api/users",
            handler="UserController.create",
            middleware=["auth", "validate", "rateLimit"],
        )

        assert "auth" in route.middleware
        assert len(route.middleware) == 3

    def test_route_with_params(self, sample_location):
        """Test route with request parameters."""
        route = RouteEntity(
            id="src/routes/user.ts:route:getUser",
            name="getUser",
            entity_type=EntityType.ROUTE,
            language=Language.TYPESCRIPT,
            location=sample_location,
            http_method="GET",
            path="/api/users/:id",
            handler="UserController.getById",
            request_params=[Parameter(name="id", type_hint="number")],
        )

        assert len(route.request_params) == 1
        assert route.request_params[0].name == "id"

    def test_route_with_response_type(self, sample_location):
        """Test route with response type."""
        route = RouteEntity(
            id="src/routes/user.ts:route:getUsers",
            name="getUsers",
            entity_type=EntityType.ROUTE,
            language=Language.TYPESCRIPT,
            location=sample_location,
            http_method="GET",
            path="/api/users",
            handler="UserController.getAll",
            response_type=TypeInfo(name="User", is_array=True),
        )

        assert route.response_type.name == "User"
        assert route.response_type.is_array is True

# ============================================================================
# create_entity_id Tests
# ============================================================================

class TestCreateEntityId:
    """Tests for create_entity_id function."""

    def test_simple_id(self):
        """Test creating simple entity ID."""
        entity_id = create_entity_id(
            Path("/src/main.go"),
            EntityType.FUNCTION,
            "main",
        )

        assert entity_id == "/src/main.go:function:main"

    def test_nested_id(self):
        """Test creating nested entity ID."""
        entity_id = create_entity_id(
            Path("/src/User.php"),
            EntityType.METHOD,
            "User",
            "getName",
        )

        assert entity_id == "/src/User.php:method:User:getName"

    def test_deeply_nested_id(self):
        """Test creating deeply nested entity ID."""
        entity_id = create_entity_id(
            Path("/src/User.php"),
            EntityType.PROPERTY,
            "User",
            "Address",
            "street",
        )

        assert entity_id == "/src/User.php:property:User:Address:street"

    def test_id_with_relative_path(self):
        """Test creating ID with relative path."""
        entity_id = create_entity_id(
            Path("src/main.go"),
            EntityType.FUNCTION,
            "main",
        )

        assert entity_id == "src/main.go:function:main"

    def test_different_entity_types(self):
        """Test creating IDs for different entity types."""
        file_path = Path("/test/file.ts")

        class_id = create_entity_id(file_path, EntityType.CLASS, "User")
        assert ":class:" in class_id

        interface_id = create_entity_id(file_path, EntityType.INTERFACE, "IUser")
        assert ":interface:" in interface_id

        component_id = create_entity_id(file_path, EntityType.COMPONENT, "UserProfile")
        assert ":component:" in component_id

    def test_id_uniqueness(self):
        """Test that different inputs produce different IDs."""
        id1 = create_entity_id(Path("/a.go"), EntityType.FUNCTION, "foo")
        id2 = create_entity_id(Path("/b.go"), EntityType.FUNCTION, "foo")
        id3 = create_entity_id(Path("/a.go"), EntityType.FUNCTION, "bar")
        id4 = create_entity_id(Path("/a.go"), EntityType.METHOD, "foo")

        assert id1 != id2  # Different files
        assert id1 != id3  # Different names
        assert id1 != id4  # Different types
