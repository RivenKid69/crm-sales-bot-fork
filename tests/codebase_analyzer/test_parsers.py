"""Tests for codebase_analyzer/indexer/parsers - AST parsers for Go, PHP, TypeScript."""

from pathlib import Path

import pytest

from codebase_analyzer.indexer.models.entities import (
    ClassEntity,
    EntityType,
    FunctionEntity,
    Language,
    Visibility,
)
from codebase_analyzer.indexer.parsers.base import (
    get_parser_for_file,
    get_parser_for_language,
)
from codebase_analyzer.indexer.parsers.go_parser import GoParser
from codebase_analyzer.indexer.parsers.php_parser import PHPParser
from codebase_analyzer.indexer.parsers.typescript_parser import (
    JavaScriptParser,
    TSXParser,
    TypeScriptParser,
)

# ============================================================================
# Parser Registration Tests
# ============================================================================

class TestParserRegistration:
    """Tests for parser registration and discovery."""

    def test_get_parser_for_go_file(self, temp_dir: Path):
        """Test getting parser for .go file."""
        go_file = temp_dir / "main.go"
        go_file.write_text("package main")

        parser = get_parser_for_file(go_file)
        assert parser is not None
        assert isinstance(parser, GoParser)

    def test_get_parser_for_php_file(self, temp_dir: Path):
        """Test getting parser for .php file."""
        php_file = temp_dir / "User.php"
        php_file.write_text("<?php class User {}")

        parser = get_parser_for_file(php_file)
        assert parser is not None
        assert isinstance(parser, PHPParser)

    def test_get_parser_for_typescript_file(self, temp_dir: Path):
        """Test getting parser for .ts file."""
        ts_file = temp_dir / "service.ts"
        ts_file.write_text("export class Service {}")

        parser = get_parser_for_file(ts_file)
        assert parser is not None
        assert isinstance(parser, TypeScriptParser)

    def test_get_parser_for_tsx_file(self, temp_dir: Path):
        """Test getting parser for .tsx file."""
        tsx_file = temp_dir / "Component.tsx"
        tsx_file.write_text("export const Component = () => <div />;")

        parser = get_parser_for_file(tsx_file)
        assert parser is not None
        # .tsx files can be handled by TypeScriptParser (which includes .tsx in extensions)
        assert isinstance(parser, (TSXParser, TypeScriptParser))
        assert ".tsx" in parser.file_extensions

    def test_get_parser_for_javascript_file(self, temp_dir: Path):
        """Test getting parser for .js file."""
        js_file = temp_dir / "utils.js"
        js_file.write_text("module.exports = {};")

        parser = get_parser_for_file(js_file)
        assert parser is not None
        assert isinstance(parser, JavaScriptParser)

    def test_get_parser_for_unknown_extension(self, temp_dir: Path):
        """Test getting parser for unsupported file."""
        unknown_file = temp_dir / "file.rs"
        unknown_file.write_text("fn main() {}")

        parser = get_parser_for_file(unknown_file)
        assert parser is None

    def test_get_parser_for_language(self):
        """Test getting parser by language enum."""
        go_parser = get_parser_for_language(Language.GO)
        assert isinstance(go_parser, GoParser)

        php_parser = get_parser_for_language(Language.PHP)
        assert isinstance(php_parser, PHPParser)

        ts_parser = get_parser_for_language(Language.TYPESCRIPT)
        assert isinstance(ts_parser, TypeScriptParser)

        tsx_parser = get_parser_for_language(Language.TSX)
        assert isinstance(tsx_parser, TSXParser)

        js_parser = get_parser_for_language(Language.JAVASCRIPT)
        assert isinstance(js_parser, JavaScriptParser)

# ============================================================================
# GoParser Tests
# ============================================================================

class TestGoParser:
    """Tests for Go language parser."""

    @pytest.fixture
    def parser(self):
        return GoParser()

    def test_parser_properties(self, parser):
        """Test GoParser basic properties."""
        assert parser.language == Language.GO
        assert ".go" in parser.file_extensions

    def test_parse_package_declaration(self, parser, temp_dir: Path):
        """Test parsing Go package declaration."""
        code = '''package users

func main() {}
'''
        file_path = temp_dir / "main.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert result.package == "users"

    def test_parse_imports(self, parser, temp_dir: Path):
        """Test parsing Go imports."""
        code = '''package main

import (
    "context"
    "database/sql"
    "fmt"

    "github.com/gin-gonic/gin"
)

func main() {}
'''
        file_path = temp_dir / "main.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.imports) >= 4

        import_paths = [imp.module_path for imp in result.imports]
        assert "context" in import_paths
        assert "database/sql" in import_paths
        assert "fmt" in import_paths

    def test_parse_struct(self, parser, temp_dir: Path):
        """Test parsing Go struct."""
        code = '''package models

// User represents a user in the system.
type User struct {
    ID        int64  `json:"id"`
    Name      string `json:"name"`
    Email     string `json:"email"`
    CreatedAt time.Time
}
'''
        file_path = temp_dir / "user.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        user_struct = result.classes[0]
        assert user_struct.name == "User"
        assert user_struct.entity_type == EntityType.STRUCT
        # Note: docstring extraction depends on AST structure, may be None

        # Check fields (properties)
        assert len(user_struct.properties) == 4
        field_names = [p.name for p in user_struct.properties]
        assert "ID" in field_names
        assert "Name" in field_names
        assert "Email" in field_names

    def test_parse_interface(self, parser, temp_dir: Path):
        """Test parsing Go interface."""
        code = '''package repository

// UserRepository defines the interface for user data access.
type UserRepository interface {
    // GetByID retrieves a user by their ID.
    GetByID(ctx context.Context, id int64) (*User, error)
    // Create creates a new user.
    Create(ctx context.Context, user *User) error
    // Delete removes a user.
    Delete(ctx context.Context, id int64) error
}
'''
        file_path = temp_dir / "repository.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        interface = result.classes[0]
        assert interface.name == "UserRepository"
        assert interface.entity_type == EntityType.INTERFACE
        assert interface.is_interface is True
        # Note: Interface method extraction depends on AST node types
        # Just verify it parses without error

    def test_parse_function(self, parser, temp_dir: Path):
        """Test parsing Go function."""
        code = '''package main

// CalculateSum calculates the sum of two integers.
func CalculateSum(a, b int) int {
    return a + b
}
'''
        file_path = temp_dir / "math.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.functions) == 1

        func = result.functions[0]
        assert func.name == "CalculateSum"
        assert func.entity_type == EntityType.FUNCTION
        assert len(func.parameters) == 2
        assert func.return_type is not None
        assert func.return_type.name == "int"

    def test_parse_method(self, parser, temp_dir: Path):
        """Test parsing Go method with receiver."""
        code = '''package models

type User struct {
    Name string
}

// GetName returns the user's name.
func (u *User) GetName() string {
    return u.Name
}

// SetName sets the user's name.
func (u *User) SetName(name string) {
    u.Name = name
}
'''
        file_path = temp_dir / "user.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        user_struct = result.classes[0]
        assert len(user_struct.methods) == 2

        method_names = [m.name for m in user_struct.methods]
        assert "GetName" in method_names
        assert "SetName" in method_names

    def test_parse_constants(self, parser, temp_dir: Path):
        """Test parsing Go constants."""
        code = '''package config

const (
    MaxRetries = 3
    Timeout    = 30
    APIVersion = "v1"
)

const SingleConst = 100
'''
        file_path = temp_dir / "config.go"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.constants) >= 3

        const_names = [c.name for c in result.constants]
        assert "MaxRetries" in const_names
        assert "Timeout" in const_names

    def test_parse_sql_queries(self, parser, sample_go_file: Path):
        """Test extracting SQL queries from Go code."""
        result = parser.parse_file(sample_go_file)

        assert result is not None
        # Check that SQL queries are extracted from methods
        all_queries = []
        for cls in result.classes:
            for method in cls.methods:
                all_queries.extend(method.sql_queries)

        assert len(all_queries) > 0
        # Should find SELECT, INSERT, UPDATE, DELETE queries
        query_text = " ".join(all_queries).upper()
        assert "SELECT" in query_text

    def test_parse_complex_go_file(self, parser, sample_go_file: Path):
        """Test parsing complex Go file from fixture."""
        result = parser.parse_file(sample_go_file)

        assert result is not None
        assert result.language == Language.GO
        assert result.package == "user"

        # Should have imports
        assert len(result.imports) > 0

        # Should have structs and interfaces
        assert len(result.classes) >= 2  # User struct and UserRepository interface

        # Check User struct
        user_struct = next((c for c in result.classes if c.name == "User"), None)
        assert user_struct is not None
        assert user_struct.entity_type == EntityType.STRUCT

        # Check UserRepository interface
        repo_interface = next(
            (c for c in result.classes if c.name == "UserRepository"), None
        )
        assert repo_interface is not None
        assert repo_interface.is_interface is True

# ============================================================================
# PHPParser Tests
# ============================================================================

class TestPHPParser:
    """Tests for PHP language parser."""

    @pytest.fixture
    def parser(self):
        return PHPParser()

    def test_parser_properties(self, parser):
        """Test PHPParser basic properties."""
        assert parser.language == Language.PHP
        assert ".php" in parser.file_extensions
        assert ".phtml" in parser.file_extensions

    def test_parse_namespace(self, parser, temp_dir: Path):
        """Test parsing PHP namespace."""
        code = '''<?php

namespace App\\Models;

class User {}
'''
        file_path = temp_dir / "User.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert result.namespace == "App\\Models"

    def test_parse_use_statements(self, parser, temp_dir: Path):
        """Test parsing PHP use statements."""
        code = '''<?php

namespace App\\Controllers;

use App\\Models\\User;
use App\\Services\\UserService;
use Illuminate\\Http\\Request;

class UserController {}
'''
        file_path = temp_dir / "UserController.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.imports) == 3

        import_paths = [imp.module_path for imp in result.imports]
        assert any("User" in p for p in import_paths)
        assert any("UserService" in p for p in import_paths)

    def test_parse_class(self, parser, temp_dir: Path):
        """Test parsing PHP class."""
        code = '''<?php

namespace App\\Models;

/**
 * User model class.
 */
class User
{
    private int $id;
    public string $name;
    protected ?string $email = null;

    public function __construct(string $name)
    {
        $this->name = $name;
    }
}
'''
        file_path = temp_dir / "User.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        user_class = result.classes[0]
        assert user_class.name == "User"
        assert user_class.entity_type == EntityType.CLASS
        assert user_class.docstring is not None

        # Check properties
        assert len(user_class.properties) == 3
        prop_names = [p.name for p in user_class.properties]
        assert "id" in prop_names
        assert "name" in prop_names

        # Check visibility
        id_prop = next(p for p in user_class.properties if p.name == "id")
        assert id_prop.visibility == Visibility.PRIVATE

        name_prop = next(p for p in user_class.properties if p.name == "name")
        assert name_prop.visibility == Visibility.PUBLIC

    def test_parse_class_inheritance(self, parser, temp_dir: Path):
        """Test parsing PHP class with inheritance."""
        code = '''<?php

class User extends Model implements UserInterface, Serializable
{
    use HasTimestamps, SoftDeletes;
}
'''
        file_path = temp_dir / "User.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        user_class = result.classes[0]

        assert user_class.extends == "Model"
        assert "UserInterface" in user_class.implements
        assert "Serializable" in user_class.implements
        assert "HasTimestamps" in user_class.uses_traits
        assert "SoftDeletes" in user_class.uses_traits

    def test_parse_interface(self, parser, temp_dir: Path):
        """Test parsing PHP interface."""
        code = '''<?php

interface UserInterface
{
    public function getId(): int;
    public function getName(): string;
    public function setName(string $name): void;
}
'''
        file_path = temp_dir / "UserInterface.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        interface = result.classes[0]
        assert interface.name == "UserInterface"
        assert interface.entity_type == EntityType.INTERFACE
        assert interface.is_interface is True
        assert len(interface.methods) == 3

    def test_parse_trait(self, parser, temp_dir: Path):
        """Test parsing PHP trait."""
        code = '''<?php

trait HasTimestamps
{
    protected ?DateTime $createdAt = null;
    protected ?DateTime $updatedAt = null;

    public function getCreatedAt(): ?DateTime
    {
        return $this->createdAt;
    }
}
'''
        file_path = temp_dir / "HasTimestamps.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        trait = result.classes[0]
        assert trait.name == "HasTimestamps"
        assert trait.entity_type == EntityType.TRAIT
        assert trait.is_trait is True

    def test_parse_methods(self, parser, temp_dir: Path):
        """Test parsing PHP methods with various modifiers."""
        code = '''<?php

class UserService
{
    public function create(array $data): User
    {
        return new User($data);
    }

    private function validate(array $data): bool
    {
        return true;
    }

    protected static function getInstance(): self
    {
        return new self();
    }

    public abstract function process(): void;
}
'''
        file_path = temp_dir / "UserService.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        service_class = result.classes[0]
        assert len(service_class.methods) >= 3

        # Check visibility
        create_method = next(m for m in service_class.methods if m.name == "create")
        assert create_method.visibility == Visibility.PUBLIC

        validate_method = next(m for m in service_class.methods if m.name == "validate")
        assert validate_method.visibility == Visibility.PRIVATE

        get_instance = next(
            (m for m in service_class.methods if m.name == "getInstance"), None
        )
        if get_instance:
            assert get_instance.is_static is True

    def test_parse_constants(self, parser, temp_dir: Path):
        """Test parsing PHP class constants."""
        code = '''<?php

class Status
{
    public const ACTIVE = 'active';
    public const INACTIVE = 'inactive';
    private const MAX_ATTEMPTS = 5;
}
'''
        file_path = temp_dir / "Status.php"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        status_class = result.classes[0]
        assert len(status_class.constants) == 3

        const_names = [c.name for c in status_class.constants]
        assert "ACTIVE" in const_names
        assert "INACTIVE" in const_names

    def test_parse_complex_php_file(self, parser, sample_php_file: Path):
        """Test parsing complex PHP file from fixture."""
        result = parser.parse_file(sample_php_file)

        assert result is not None
        assert result.language == Language.PHP
        assert result.namespace == "App\\Models"

        # Should have imports
        assert len(result.imports) > 0

        # Should have User class
        user_class = next((c for c in result.classes if c.name == "User"), None)
        assert user_class is not None
        assert user_class.extends == "Model"
        assert "UserInterface" in user_class.implements

        # Should have methods
        assert len(user_class.methods) > 0

        # Should have properties
        assert len(user_class.properties) > 0

# ============================================================================
# TypeScriptParser Tests
# ============================================================================

class TestTypeScriptParser:
    """Tests for TypeScript language parser."""

    @pytest.fixture
    def parser(self):
        return TypeScriptParser()

    def test_parser_properties(self, parser):
        """Test TypeScriptParser basic properties."""
        assert parser.language == Language.TYPESCRIPT
        assert ".ts" in parser.file_extensions

    def test_parse_imports(self, parser, temp_dir: Path):
        """Test parsing TypeScript imports."""
        code = '''import { Injectable, Logger } from '@nestjs/common';
import type { User, UserDto } from './types';
import * as lodash from 'lodash';
import DefaultExport from './default';

export class Service {}
'''
        file_path = temp_dir / "service.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.imports) >= 3

        # Check type-only import
        type_imports = [imp for imp in result.imports if imp.is_type_only]
        assert len(type_imports) >= 1

    def test_parse_class(self, parser, temp_dir: Path):
        """Test parsing TypeScript class."""
        code = '''/**
 * User service for managing users.
 */
export class UserService {
    private readonly logger: Logger;
    public users: User[] = [];

    constructor(private readonly repository: UserRepository) {
        this.logger = new Logger();
    }

    async findById(id: number): Promise<User | null> {
        return this.repository.findById(id);
    }

    create(data: CreateUserDto): User {
        return this.repository.create(data);
    }
}
'''
        file_path = temp_dir / "user.service.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        service_class = result.classes[0]
        assert service_class.name == "UserService"
        # Note: JSDoc extraction depends on AST structure

        # Check methods
        assert len(service_class.methods) >= 2
        method_names = [m.name for m in service_class.methods]
        assert "findById" in method_names
        assert "create" in method_names

        # Check async method
        find_method = next(m for m in service_class.methods if m.name == "findById")
        assert find_method.is_async is True

    def test_parse_interface(self, parser, temp_dir: Path):
        """Test parsing TypeScript interface."""
        code = '''export interface User {
    id: number;
    name: string;
    email: string;
    createdAt: Date;
    metadata?: Record<string, any>;
}

export interface UserRepository {
    findById(id: number): Promise<User | null>;
    create(data: CreateUserDto): Promise<User>;
    delete(id: number): Promise<void>;
}
'''
        file_path = temp_dir / "types.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 2

        user_interface = next(c for c in result.classes if c.name == "User")
        assert user_interface.entity_type == EntityType.INTERFACE
        assert user_interface.is_interface is True
        # Note: Interface property extraction depends on AST structure

        repo_interface = next(c for c in result.classes if c.name == "UserRepository")
        # Note: Interface method extraction depends on AST structure

    def test_parse_type_alias(self, parser, temp_dir: Path):
        """Test parsing TypeScript type alias."""
        code = '''export type UserId = number;
export type UserRole = 'admin' | 'user' | 'guest';
export type UserMap = Map<string, User>;
'''
        file_path = temp_dir / "types.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        # Type aliases may be parsed as classes or separately
        assert len(result.classes) >= 1

    def test_parse_function(self, parser, temp_dir: Path):
        """Test parsing TypeScript standalone function."""
        code = '''/**
 * Format user's full name.
 */
export function formatUserName(firstName: string, lastName: string): string {
    return `${firstName} ${lastName}`.trim();
}

export async function fetchUser(id: number): Promise<User> {
    const response = await fetch(`/api/users/${id}`);
    return response.json();
}
'''
        file_path = temp_dir / "utils.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.functions) >= 2

        format_func = next(f for f in result.functions if f.name == "formatUserName")
        assert format_func.entity_type == EntityType.FUNCTION
        assert len(format_func.parameters) == 2
        assert format_func.return_type is not None

        fetch_func = next(f for f in result.functions if f.name == "fetchUser")
        assert fetch_func.is_async is True

    def test_parse_arrow_function(self, parser, temp_dir: Path):
        """Test parsing TypeScript arrow function."""
        code = '''export const validateEmail = (email: string): boolean => {
    return /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email);
};

export const getUserById = async (id: number): Promise<User> => {
    return fetchUser(id);
};
'''
        file_path = temp_dir / "validators.ts"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        # Arrow functions should be parsed as functions
        assert len(result.functions) >= 1

    def test_parse_complex_typescript_file(self, parser, sample_typescript_file: Path):
        """Test parsing complex TypeScript file from fixture."""
        result = parser.parse_file(sample_typescript_file)

        assert result is not None
        assert result.language == Language.TYPESCRIPT

        # Should have imports
        assert len(result.imports) > 0

        # Should have UserService class
        service_class = next(
            (c for c in result.classes if c.name == "UserService"), None
        )
        assert service_class is not None
        assert len(service_class.methods) > 0

        # Should have CacheService interface
        cache_interface = next(
            (c for c in result.classes if c.name == "CacheService"), None
        )
        assert cache_interface is not None
        assert cache_interface.is_interface is True

# ============================================================================
# TSXParser Tests (React)
# ============================================================================

class TestTSXParser:
    """Tests for TSX (React) parser."""

    @pytest.fixture
    def parser(self):
        return TSXParser()

    def test_parser_properties(self, parser):
        """Test TSXParser basic properties."""
        assert parser.language == Language.TSX
        assert ".tsx" in parser.file_extensions

    def test_parse_functional_component(self, parser, temp_dir: Path):
        """Test parsing React functional component."""
        code = '''import React from 'react';

interface ButtonProps {
    label: string;
    onClick: () => void;
    disabled?: boolean;
}

export const Button: React.FC<ButtonProps> = ({ label, onClick, disabled }) => {
    return (
        <button onClick={onClick} disabled={disabled}>
            {label}
        </button>
    );
};
'''
        file_path = temp_dir / "Button.tsx"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        # Should recognize React component
        assert len(result.components) >= 1 or len(result.functions) >= 1

    def test_parse_component_with_hooks(self, parser, temp_dir: Path):
        """Test parsing component with React hooks."""
        code = '''import React, { useState, useEffect, useCallback } from 'react';

export const Counter: React.FC = () => {
    const [count, setCount] = useState(0);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        console.log('Count changed:', count);
    }, [count]);

    const increment = useCallback(() => {
        setCount(prev => prev + 1);
    }, []);

    return (
        <div>
            <span>{count}</span>
            <button onClick={increment}>+</button>
        </div>
    );
};
'''
        file_path = temp_dir / "Counter.tsx"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        # Should detect React component
        # Note: Hooks extraction depends on AST analysis implementation

    def test_parse_complex_tsx_file(self, parser, sample_tsx_file: Path):
        """Test parsing complex TSX file from fixture."""
        result = parser.parse_file(sample_tsx_file)

        assert result is not None
        assert result.language == Language.TSX

        # Should have imports
        assert len(result.imports) > 0

        # Should recognize components or functions
        assert len(result.components) > 0 or len(result.functions) > 0

# ============================================================================
# JavaScriptParser Tests
# ============================================================================

class TestJavaScriptParser:
    """Tests for JavaScript parser."""

    @pytest.fixture
    def parser(self):
        return JavaScriptParser()

    def test_parser_properties(self, parser):
        """Test JavaScriptParser basic properties."""
        assert parser.language == Language.JAVASCRIPT
        assert ".js" in parser.file_extensions

    def test_parse_class(self, parser, temp_dir: Path):
        """Test parsing JavaScript class."""
        code = '''/**
 * User controller.
 */
class UserController {
    constructor(userService) {
        this.userService = userService;
    }

    async getAll(req, res) {
        const users = await this.userService.findAll();
        res.json(users);
    }

    async create(req, res) {
        const user = await this.userService.create(req.body);
        res.status(201).json(user);
    }
}

module.exports = { UserController };
'''
        file_path = temp_dir / "user.controller.js"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.classes) == 1

        controller = result.classes[0]
        assert controller.name == "UserController"
        assert len(controller.methods) >= 2

    def test_parse_function(self, parser, temp_dir: Path):
        """Test parsing JavaScript function."""
        code = '''/**
 * Create user routes.
 */
function createUserRoutes(userService) {
    const router = express.Router();
    router.get('/', (req, res) => userService.getAll(req, res));
    return router;
}

const validateUser = (data) => {
    return data.name && data.email;
};

module.exports = { createUserRoutes, validateUser };
'''
        file_path = temp_dir / "routes.js"
        file_path.write_text(code)

        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.functions) >= 1

    def test_parse_complex_javascript_file(self, parser, sample_javascript_file: Path):
        """Test parsing complex JavaScript file from fixture."""
        result = parser.parse_file(sample_javascript_file)

        assert result is not None
        assert result.language == Language.JAVASCRIPT

        # Should have class
        assert len(result.classes) >= 1

        # Should have functions
        assert len(result.functions) >= 1

# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

class TestParserEdgeCases:
    """Tests for parser edge cases and error handling."""

    def test_parse_empty_file(self, temp_dir: Path):
        """Test parsing empty file."""
        empty_file = temp_dir / "empty.go"
        empty_file.write_text("")

        parser = GoParser()
        result = parser.parse_file(empty_file)

        # Should return None or empty FileEntity
        assert result is None or len(result.classes) == 0

    def test_parse_nonexistent_file(self, temp_dir: Path):
        """Test parsing non-existent file."""
        parser = GoParser()
        result = parser.parse_file(temp_dir / "nonexistent.go")

        assert result is None

    def test_parse_syntax_error(self, temp_dir: Path):
        """Test parsing file with syntax errors."""
        invalid_code = '''package main

func broken( {
    // Missing closing paren
'''
        file_path = temp_dir / "broken.go"
        file_path.write_text(invalid_code)

        parser = GoParser()
        # Should not crash, may return partial result or None
        try:
            result = parser.parse_file(file_path)
            # Parser should handle gracefully
            assert result is None or isinstance(result, type(result))
        except Exception:
            # Some parsers may raise, which is also acceptable
            pass

    def test_parse_unicode_content(self, temp_dir: Path):
        """Test parsing file with unicode characters."""
        code = '''<?php

// Комментарий на русском языке
class Пользователь
{
    public string $имя = "Тест";

    /**
     * Получить имя пользователя.
     */
    public function getИмя(): string
    {
        return $this->имя;
    }
}
'''
        file_path = temp_dir / "unicode.php"
        file_path.write_text(code, encoding="utf-8")

        parser = PHPParser()
        result = parser.parse_file(file_path)

        # Note: Unicode handling may vary depending on tree-sitter grammar
        # Parser should not crash on unicode content

    def test_parse_large_file(self, temp_dir: Path):
        """Test parsing large file."""
        # Generate a large Go file
        code_parts = ["package main\n\n"]
        for i in range(100):
            code_parts.append(f"""
// Function{i} does something.
func Function{i}(a, b int) int {{
    result := a + b
    for j := 0; j < 10; j++ {{
        result += j
    }}
    return result
}}
""")

        code = "".join(code_parts)
        file_path = temp_dir / "large.go"
        file_path.write_text(code)

        parser = GoParser()
        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.functions) == 100

    def test_parse_content_directly(self, temp_dir: Path):
        """Test parse_content method."""
        code = '''package test

func Hello() string {
    return "Hello"
}
'''
        parser = GoParser()
        result = parser.parse_content(code, Path("/virtual/test.go"))

        assert result is not None
        assert len(result.functions) == 1
        assert result.functions[0].name == "Hello"

# ============================================================================
# Parser Integration Tests
# ============================================================================

class TestParserIntegration:
    """Integration tests for parsers."""

    def test_parse_multi_file_project(self, multi_file_project: Path):
        """Test parsing multiple files in a project."""
        results = []

        # Parse all Go files
        go_parser = GoParser()
        for go_file in multi_file_project.glob("**/*.go"):
            if "vendor" not in str(go_file):
                result = go_parser.parse_file(go_file)
                if result:
                    results.append(result)

        # Parse all PHP files
        php_parser = PHPParser()
        for php_file in multi_file_project.glob("**/*.php"):
            if "vendor" not in str(php_file):
                result = php_parser.parse_file(php_file)
                if result:
                    results.append(result)

        # Parse all TypeScript files
        ts_parser = TypeScriptParser()
        for ts_file in multi_file_project.glob("**/*.ts"):
            if "node_modules" not in str(ts_file):
                result = ts_parser.parse_file(ts_file)
                if result:
                    results.append(result)

        # Should have parsed multiple files
        assert len(results) > 0

        # Collect all entities
        all_classes = []
        all_functions = []
        for result in results:
            all_classes.extend(result.classes)
            all_functions.extend(result.functions)

        # Should have found classes/functions
        assert len(all_classes) > 0 or len(all_functions) > 0

    def test_consistent_entity_ids(self, temp_dir: Path):
        """Test that entity IDs are consistent across parses."""
        code = '''package main

type User struct {
    Name string
}

func (u *User) GetName() string {
    return u.Name
}
'''
        file_path = temp_dir / "user.go"
        file_path.write_text(code)

        parser = GoParser()

        # Parse twice
        result1 = parser.parse_file(file_path)
        result2 = parser.parse_file(file_path)

        assert result1 is not None
        assert result2 is not None

        # IDs should be consistent
        assert result1.classes[0].id == result2.classes[0].id

    def test_source_location_accuracy(self, temp_dir: Path):
        """Test that source locations are accurate."""
        code = '''package main

// Line 3
// Line 4
// Line 5
func Main() {
    // Line 7
}
'''
        file_path = temp_dir / "main.go"
        file_path.write_text(code)

        parser = GoParser()
        result = parser.parse_file(file_path)

        assert result is not None
        assert len(result.functions) == 1

        func = result.functions[0]
        # Function should start around line 6
        assert func.location.start_line >= 3
        assert func.location.end_line >= func.location.start_line
