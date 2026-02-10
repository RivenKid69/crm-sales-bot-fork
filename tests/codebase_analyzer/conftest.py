"""Shared fixtures for codebase_analyzer tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

# ============================================================================
# Path Fixtures
# ============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def temp_project(temp_dir: Path) -> Path:
    """Create a temporary project structure."""
    # Create standard directory structure
    (temp_dir / "src").mkdir()
    (temp_dir / "src" / "models").mkdir()
    (temp_dir / "src" / "services").mkdir()
    (temp_dir / "tests").mkdir()
    (temp_dir / "vendor").mkdir()
    (temp_dir / "node_modules").mkdir()
    return temp_dir

# ============================================================================
# Sample Code Fixtures - Go
# ============================================================================

@pytest.fixture
def sample_go_code() -> str:
    """Sample Go code for parser testing."""
    return '''package user

import (
    "context"
    "database/sql"
    "errors"
    "fmt"
    "time"
)

// User represents a user in the system.
// It contains all user-related information.
type User struct {
    ID        int64     `json:"id"`
    Name      string    `json:"name"`
    Email     string    `json:"email"`
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
}

// UserRepository defines the interface for user data access.
type UserRepository interface {
    // GetByID retrieves a user by their ID.
    GetByID(ctx context.Context, id int64) (*User, error)
    // Create creates a new user.
    Create(ctx context.Context, user *User) error
    // Update updates an existing user.
    Update(ctx context.Context, user *User) error
    // Delete removes a user by ID.
    Delete(ctx context.Context, id int64) error
}

// userRepo implements UserRepository using SQL.
type userRepo struct {
    db *sql.DB
}

// NewUserRepository creates a new user repository.
func NewUserRepository(db *sql.DB) UserRepository {
    return &userRepo{db: db}
}

// GetByID retrieves a user by ID.
func (r *userRepo) GetByID(ctx context.Context, id int64) (*User, error) {
    query := "SELECT id, name, email, created_at, updated_at FROM users WHERE id = $1"

    user := &User{}
    err := r.db.QueryRowContext(ctx, query, id).Scan(
        &user.ID, &user.Name, &user.Email, &user.CreatedAt, &user.UpdatedAt,
    )
    if err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, fmt.Errorf("user not found: %d", id)
        }
        return nil, fmt.Errorf("failed to get user: %w", err)
    }
    return user, nil
}

// Create inserts a new user into the database.
func (r *userRepo) Create(ctx context.Context, user *User) error {
    query := "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, created_at, updated_at"
    return r.db.QueryRowContext(ctx, query, user.Name, user.Email).Scan(
        &user.ID, &user.CreatedAt, &user.UpdatedAt,
    )
}

// Update modifies an existing user.
func (r *userRepo) Update(ctx context.Context, user *User) error {
    query := "UPDATE users SET name = $1, email = $2, updated_at = NOW() WHERE id = $3"
    _, err := r.db.ExecContext(ctx, query, user.Name, user.Email, user.ID)
    return err
}

// Delete removes a user from the database.
func (r *userRepo) Delete(ctx context.Context, id int64) error {
    query := "DELETE FROM users WHERE id = $1"
    _, err := r.db.ExecContext(ctx, query, id)
    return err
}

const (
    MaxNameLength  = 100
    MaxEmailLength = 255
)

var ErrInvalidUser = errors.New("invalid user data")
'''

@pytest.fixture
def sample_go_file(temp_dir: Path, sample_go_code: str) -> Path:
    """Create a sample Go file."""
    file_path = temp_dir / "user.go"
    file_path.write_text(sample_go_code)
    return file_path

# ============================================================================
# Sample Code Fixtures - PHP
# ============================================================================

@pytest.fixture
def sample_php_code() -> str:
    """Sample PHP code for parser testing."""
    return '''<?php

namespace App\\Models;

use App\\Interfaces\\UserInterface;
use App\\Traits\\HasTimestamps;
use App\\Traits\\Validatable;
use Illuminate\\Database\\Eloquent\\Model;

/**
 * User model representing application users.
 *
 * @property int $id
 * @property string $name
 * @property string $email
 */
class User extends Model implements UserInterface
{
    use HasTimestamps, Validatable;

    public const STATUS_ACTIVE = 'active';
    public const STATUS_INACTIVE = 'inactive';
    private const MAX_LOGIN_ATTEMPTS = 5;

    protected string $table = 'users';

    private int $id;
    protected string $name;
    public string $email;
    private ?string $password = null;

    /**
     * Create a new user instance.
     *
     * @param string $name User's full name
     * @param string $email User's email address
     */
    public function __construct(string $name, string $email)
    {
        $this->name = $name;
        $this->email = $email;
    }

    /**
     * Get the user's ID.
     */
    public function getId(): int
    {
        return $this->id;
    }

    /**
     * Get the user's full name.
     */
    public function getName(): string
    {
        return $this->name;
    }

    /**
     * Set the user's name.
     *
     * @param string $name The new name
     * @return self
     */
    public function setName(string $name): self
    {
        $this->name = $name;
        return $this;
    }

    /**
     * Check if the user is active.
     */
    public function isActive(): bool
    {
        return $this->status === self::STATUS_ACTIVE;
    }

    /**
     * Validate the user data.
     *
     * @throws \\InvalidArgumentException If validation fails
     */
    public function validate(): void
    {
        if (empty($this->name)) {
            throw new \\InvalidArgumentException('Name is required');
        }
        if (!filter_var($this->email, FILTER_VALIDATE_EMAIL)) {
            throw new \\InvalidArgumentException('Invalid email format');
        }
    }

    /**
     * Save the user to database.
     */
    public function save(): bool
    {
        $this->validate();
        $query = "INSERT INTO users (name, email) VALUES (?, ?)";
        return $this->executeQuery($query, [$this->name, $this->email]);
    }

    /**
     * Find user by email.
     *
     * @param string $email
     * @return static|null
     */
    public static function findByEmail(string $email): ?self
    {
        $query = "SELECT * FROM users WHERE email = ?";
        // Implementation
        return null;
    }

    private function executeQuery(string $query, array $params): bool
    {
        // Implementation
        return true;
    }
}

interface UserInterface
{
    public function getId(): int;
    public function getName(): string;
    public function validate(): void;
}

trait HasTimestamps
{
    protected ?\\DateTime $createdAt = null;
    protected ?\\DateTime $updatedAt = null;

    public function getCreatedAt(): ?\\DateTime
    {
        return $this->createdAt;
    }
}
'''

@pytest.fixture
def sample_php_file(temp_dir: Path, sample_php_code: str) -> Path:
    """Create a sample PHP file."""
    file_path = temp_dir / "User.php"
    file_path.write_text(sample_php_code)
    return file_path

# ============================================================================
# Sample Code Fixtures - TypeScript
# ============================================================================

@pytest.fixture
def sample_typescript_code() -> str:
    """Sample TypeScript code for parser testing."""
    return '''import { Injectable, Logger } from '@nestjs/common';
import { Repository } from 'typeorm';
import type { User, CreateUserDto, UpdateUserDto } from './types';

/**
 * User service handling all user-related operations.
 */
@Injectable()
export class UserService {
    private readonly logger = new Logger(UserService.name);

    constructor(
        private readonly userRepository: Repository<User>,
        private readonly cacheService: CacheService,
    ) {}

    /**
     * Create a new user.
     * @param dto - User creation data
     * @returns The created user
     */
    async createUser(dto: CreateUserDto): Promise<User> {
        this.logger.log(`Creating user: ${dto.email}`);

        const user = this.userRepository.create(dto);
        const saved = await this.userRepository.save(user);

        await this.cacheService.invalidate('users');

        return saved;
    }

    /**
     * Find user by ID.
     */
    async findById(id: number): Promise<User | null> {
        const cached = await this.cacheService.get(`user:${id}`);
        if (cached) return cached;

        const user = await this.userRepository.findOne({ where: { id } });
        if (user) {
            await this.cacheService.set(`user:${id}`, user);
        }
        return user;
    }

    /**
     * Update user data.
     */
    async updateUser(id: number, dto: UpdateUserDto): Promise<User> {
        const user = await this.findById(id);
        if (!user) {
            throw new Error(`User ${id} not found`);
        }

        Object.assign(user, dto);
        return this.userRepository.save(user);
    }

    /**
     * Delete a user.
     */
    async deleteUser(id: number): Promise<void> {
        await this.userRepository.delete(id);
        await this.cacheService.delete(`user:${id}`);
    }

    /**
     * Find all users with pagination.
     */
    async findAll(page: number = 1, limit: number = 10): Promise<User[]> {
        return this.userRepository.find({
            skip: (page - 1) * limit,
            take: limit,
        });
    }
}

export interface CacheService {
    get<T>(key: string): Promise<T | null>;
    set<T>(key: string, value: T, ttl?: number): Promise<void>;
    delete(key: string): Promise<void>;
    invalidate(pattern: string): Promise<void>;
}

export type UserRole = 'admin' | 'user' | 'guest';

export const DEFAULT_PAGE_SIZE = 10;
export const MAX_PAGE_SIZE = 100;

const validateEmail = (email: string): boolean => {
    return /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(email);
};

export function formatUserName(firstName: string, lastName: string): string {
    return `${firstName} ${lastName}`.trim();
}

export async function hashPassword(password: string): Promise<string> {
    // Implementation
    return password;
}
'''

@pytest.fixture
def sample_typescript_file(temp_dir: Path, sample_typescript_code: str) -> Path:
    """Create a sample TypeScript file."""
    file_path = temp_dir / "user.service.ts"
    file_path.write_text(sample_typescript_code)
    return file_path

# ============================================================================
# Sample Code Fixtures - TSX/React
# ============================================================================

@pytest.fixture
def sample_tsx_code() -> str:
    """Sample TSX/React code for parser testing."""
    return '''import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { UserCard } from './UserCard';
import { LoadingSpinner } from '../common/LoadingSpinner';
import type { User, UserFormData } from '../types';

interface UserProfileProps {
    userId: number;
    onUpdate?: (user: User) => void;
    showActions?: boolean;
}

/**
 * User profile component displaying user information.
 */
export const UserProfile: React.FC<UserProfileProps> = ({
    userId,
    onUpdate,
    showActions = true
}) => {
    const [isEditing, setIsEditing] = useState(false);
    const [formData, setFormData] = useState<UserFormData | null>(null);

    const navigate = useNavigate();
    const { id } = useParams<{ id: string }>();

    const { data: user, isLoading, error, refetch } = useQuery({
        queryKey: ['user', userId],
        queryFn: () => fetchUser(userId),
    });

    const mutation = useMutation({
        mutationFn: (data: UserFormData) => updateUser(userId, data),
        onSuccess: (updatedUser) => {
            setIsEditing(false);
            onUpdate?.(updatedUser);
            refetch();
        },
    });

    useEffect(() => {
        if (user) {
            setFormData({
                name: user.name,
                email: user.email,
            });
        }
    }, [user]);

    const handleSubmit = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();
        if (formData) {
            mutation.mutate(formData);
        }
    }, [formData, mutation]);

    const handleDelete = useCallback(async () => {
        if (window.confirm('Are you sure?')) {
            await deleteUser(userId);
            navigate('/users');
        }
    }, [userId, navigate]);

    const displayName = useMemo(() => {
        return user ? `${user.firstName} ${user.lastName}` : '';
    }, [user]);

    if (isLoading) return <LoadingSpinner />;
    if (error) return <div>Error loading user</div>;
    if (!user) return <div>User not found</div>;

    return (
        <div className="user-profile">
            <h1>{displayName}</h1>
            <UserCard user={user} />

            {showActions && (
                <div className="actions">
                    <button onClick={() => setIsEditing(true)}>Edit</button>
                    <button onClick={handleDelete}>Delete</button>
                </div>
            )}

            {isEditing && (
                <form onSubmit={handleSubmit}>
                    <input
                        value={formData?.name ?? ''}
                        onChange={(e) => setFormData(prev => ({
                            ...prev!,
                            name: e.target.value
                        }))}
                    />
                    <button type="submit">Save</button>
                </form>
            )}
        </div>
    );
};

export default UserProfile;

// Helper functions
async function fetchUser(id: number): Promise<User> {
    const response = await fetch(`/api/users/${id}`);
    return response.json();
}

async function updateUser(id: number, data: UserFormData): Promise<User> {
    const response = await fetch(`/api/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
    return response.json();
}

async function deleteUser(id: number): Promise<void> {
    await fetch(`/api/users/${id}`, { method: 'DELETE' });
}
'''

@pytest.fixture
def sample_tsx_file(temp_dir: Path, sample_tsx_code: str) -> Path:
    """Create a sample TSX file."""
    file_path = temp_dir / "UserProfile.tsx"
    file_path.write_text(sample_tsx_code)
    return file_path

# ============================================================================
# Sample Code Fixtures - JavaScript
# ============================================================================

@pytest.fixture
def sample_javascript_code() -> str:
    """Sample JavaScript code for parser testing."""
    return '''const express = require('express');
const { validateUser, sanitizeInput } = require('./validators');

/**
 * User controller handling HTTP requests.
 */
class UserController {
    constructor(userService) {
        this.userService = userService;
    }

    /**
     * Get all users.
     */
    async getAll(req, res) {
        try {
            const { page = 1, limit = 10 } = req.query;
            const users = await this.userService.findAll(page, limit);
            res.json({ success: true, data: users });
        } catch (error) {
            res.status(500).json({ success: false, error: error.message });
        }
    }

    /**
     * Get user by ID.
     */
    async getById(req, res) {
        try {
            const user = await this.userService.findById(req.params.id);
            if (!user) {
                return res.status(404).json({ success: false, error: 'User not found' });
            }
            res.json({ success: true, data: user });
        } catch (error) {
            res.status(500).json({ success: false, error: error.message });
        }
    }

    /**
     * Create new user.
     */
    async create(req, res) {
        try {
            const data = sanitizeInput(req.body);
            const errors = validateUser(data);
            if (errors.length > 0) {
                return res.status(400).json({ success: false, errors });
            }
            const user = await this.userService.create(data);
            res.status(201).json({ success: true, data: user });
        } catch (error) {
            res.status(500).json({ success: false, error: error.message });
        }
    }
}

/**
 * Create user routes.
 */
function createUserRoutes(userService) {
    const router = express.Router();
    const controller = new UserController(userService);

    router.get('/', (req, res) => controller.getAll(req, res));
    router.get('/:id', (req, res) => controller.getById(req, res));
    router.post('/', (req, res) => controller.create(req, res));

    return router;
}

const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 100;

module.exports = { UserController, createUserRoutes, DEFAULT_LIMIT, MAX_LIMIT };
'''

@pytest.fixture
def sample_javascript_file(temp_dir: Path, sample_javascript_code: str) -> Path:
    """Create a sample JavaScript file."""
    file_path = temp_dir / "user.controller.js"
    file_path.write_text(sample_javascript_code)
    return file_path

# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def sample_config_yaml(temp_dir: Path) -> Path:
    """Create a sample configuration YAML file."""
    config_content = '''
llm:
  model_name: "test-model"
  temperature: 0.5
  max_tokens: 2048
  api_base: "http://test:8000/v1"

embedding:
  model_name: "test-embed"
  device: "cpu"
  batch_size: 16

rag:
  vector_db: "chroma"
  top_k_initial: 30
  top_k_final: 5

chunking:
  strategy: "ast"
  chunk_size_tokens: 1000

indexer:
  languages:
    - php
    - go
  parallel_workers: 4

generator:
  output_format: "markdown"
  language: "ru"

log_level: "DEBUG"
batch_size: 5
'''
    config_path = temp_dir / "config.yaml"
    config_path.write_text(config_content)
    return config_path

@pytest.fixture
def invalid_config_yaml(temp_dir: Path) -> Path:
    """Create an invalid configuration YAML file."""
    config_content = '''
llm:
  gpu_memory_utilization: 1.5  # Invalid: > 0.99
  temperature: 3.0  # Invalid: > 2.0
'''
    config_path = temp_dir / "invalid_config.yaml"
    config_path.write_text(config_content)
    return config_path

# ============================================================================
# Multi-File Project Fixtures
# ============================================================================

@pytest.fixture
def multi_file_project(temp_project: Path) -> Path:
    """Create a realistic multi-file project structure."""
    # Go files
    (temp_project / "src" / "main.go").write_text('''package main

import (
    "src/models"
    "src/services"
)

func main() {
    userService := services.NewUserService()
    user := models.NewUser("test", "test@example.com")
    userService.Create(user)
}
''')

    (temp_project / "src" / "models" / "user.go").write_text('''package models

type User struct {
    ID    int64
    Name  string
    Email string
}

func NewUser(name, email string) *User {
    return &User{Name: name, Email: email}
}
''')

    (temp_project / "src" / "services" / "user_service.go").write_text('''package services

import "src/models"

type UserService struct{}

func NewUserService() *UserService {
    return &UserService{}
}

func (s *UserService) Create(user *models.User) error {
    // Implementation
    return nil
}
''')

    # PHP files
    (temp_project / "src" / "User.php").write_text('''<?php
namespace App;

class User {
    private int $id;
    public string $name;

    public function __construct(string $name) {
        $this->name = $name;
    }

    public function save(): bool {
        return true;
    }
}
''')

    # TypeScript files
    (temp_project / "src" / "index.ts").write_text('''import { UserService } from './services/user.service';

const userService = new UserService();
userService.createUser({ name: 'test', email: 'test@example.com' });
''')

    (temp_project / "src" / "services" / "user.service.ts").write_text('''export class UserService {
    async createUser(data: { name: string; email: string }) {
        // Implementation
        return { id: 1, ...data };
    }
}
''')

    # Files in excluded directories (should be ignored)
    (temp_project / "vendor" / "external.php").write_text('<?php // vendor code')
    (temp_project / "node_modules" / "package").mkdir(parents=True, exist_ok=True)
    (temp_project / "node_modules" / "package" / "index.js").write_text('// node module')

    return temp_project

# ============================================================================
# Entity Fixtures
# ============================================================================

@pytest.fixture
def sample_source_location():
    """Create a sample SourceLocation."""
    from codebase_analyzer.indexer.models.entities import SourceLocation

    return SourceLocation(
        file_path=Path("/test/file.go"),
        start_line=10,
        end_line=25,
        start_column=0,
        end_column=1,
    )

@pytest.fixture
def sample_function_entity(sample_source_location):
    """Create a sample FunctionEntity."""
    from codebase_analyzer.indexer.models.entities import (
        EntityType,
        FunctionEntity,
        Language,
        Parameter,
        TypeInfo,
        Visibility,
    )

    return FunctionEntity(
        id="test/file.go:function:GetUser",
        name="GetUser",
        entity_type=EntityType.FUNCTION,
        language=Language.GO,
        location=sample_source_location,
        docstring="Get user by ID.",
        parameters=[
            Parameter(name="ctx", type_hint="context.Context"),
            Parameter(name="id", type_hint="int64"),
        ],
        return_type=TypeInfo(name="User", is_nullable=True),
        visibility=Visibility.PUBLIC,
        calls=["db.Query", "json.Marshal"],
    )

@pytest.fixture
def sample_class_entity(sample_source_location, sample_function_entity):
    """Create a sample ClassEntity."""
    from codebase_analyzer.indexer.models.entities import (
        ClassEntity,
        EntityType,
        Language,
        PropertyEntity,
        Visibility,
    )

    return ClassEntity(
        id="test/User.php:class:User",
        name="User",
        entity_type=EntityType.CLASS,
        language=Language.PHP,
        location=sample_source_location,
        docstring="User model class.",
        extends="Model",
        implements=["UserInterface"],
        methods=[sample_function_entity],
        properties=[
            PropertyEntity(
                id="test/User.php:class:User:property:name",
                name="name",
                entity_type=EntityType.PROPERTY,
                language=Language.PHP,
                location=sample_source_location,
                visibility=Visibility.PRIVATE,
            )
        ],
    )
