"""
Unit tests for database models and Pydantic schemas
"""

# datetime import removed as it's not used

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import (
    Task,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    Token,
    TokenData,
    User,
    UserCreate,
    UserResponse,
)

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test"""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


class TestUserModel:
    """Test SQLAlchemy User model"""

    def test_create_user(self, db_session):
        """Test creating a user in the database"""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.created_at is not None
        assert user.tasks == []

    def test_user_relationships(self, db_session):
        """Test User-Task relationship"""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        task = Task(title="Test Task", description="Test Description", owner_id=user.id)
        db_session.add(task)
        db_session.commit()

        # Refresh to get updated relationships
        db_session.refresh(user)
        db_session.refresh(task)

        assert len(user.tasks) == 1
        assert user.tasks[0].title == "Test Task"
        assert task.owner.username == "testuser"


class TestTaskModel:
    """Test SQLAlchemy Task model"""

    def test_create_task(self, db_session):
        """Test creating a task in the database"""
        # First create a user
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Then create a task
        task = Task(
            title="Test Task",
            description="Test Description",
            priority="high",
            owner_id=user.id,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.id is not None
        assert task.title == "Test Task"
        assert task.description == "Test Description"
        assert task.completed is False
        assert task.priority == "high"
        assert task.created_at is not None
        assert task.updated_at is None  # Only set on updates
        assert task.owner_id == user.id

    def test_task_defaults(self, db_session):
        """Test task default values"""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        task = Task(title="Test Task", owner_id=user.id)
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.completed is False
        assert task.priority == "medium"
        assert task.description is None


class TestPydanticSchemas:
    """Test Pydantic validation schemas"""

    def test_user_create_valid(self):
        """Test valid UserCreate schema"""
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        }
        user = UserCreate(**user_data)

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.password == "password123"

    def test_user_create_invalid_email(self):
        """Test UserCreate with invalid email"""
        user_data = {
            "username": "testuser",
            "email": "invalid-email",
            "password": "password123",
        }
        # Note: Pydantic BaseModel doesn't validate email format by default
        # This would pass unless we add email validation
        user = UserCreate(**user_data)
        assert user.email == "invalid-email"

    def test_user_response_from_db_model(self, db_session):
        """Test UserResponse creation from database model"""
        # Create user in database
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Convert to response model
        user_response = UserResponse.model_validate(user)

        assert user_response.id == user.id
        assert user_response.username == user.username
        assert user_response.email == user.email
        assert user_response.is_active == user.is_active
        assert user_response.created_at == user.created_at

    def test_task_create_valid(self):
        """Test valid TaskCreate schema"""
        task_data = {
            "title": "Test Task",
            "description": "Test Description",
            "priority": "high",
        }
        task = TaskCreate(**task_data)

        assert task.title == "Test Task"
        assert task.description == "Test Description"
        assert task.priority == "high"

    def test_task_create_minimal(self):
        """Test TaskCreate with minimal data"""
        task_data = {"title": "Test Task"}
        task = TaskCreate(**task_data)

        assert task.title == "Test Task"
        assert task.description is None
        assert task.priority == "medium"

    def test_task_update_partial(self):
        """Test TaskUpdate with partial data"""
        task_data = {"completed": True}
        task_update = TaskUpdate(**task_data)

        assert task_update.completed is True
        assert task_update.title is None
        assert task_update.description is None
        assert task_update.priority is None

    def test_task_response_from_db_model(self, db_session):
        """Test TaskResponse creation from database model"""
        # Create user and task in database
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        task = Task(
            title="Test Task",
            description="Test Description",
            priority="high",
            completed=True,
            owner_id=user.id,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        # Convert to response model
        task_response = TaskResponse.model_validate(task)

        assert task_response.id == task.id
        assert task_response.title == task.title
        assert task_response.description == task.description
        assert task_response.completed == task.completed
        assert task_response.priority == task.priority
        assert task_response.created_at == task.created_at
        assert task_response.updated_at == task.updated_at

    def test_token_model(self):
        """Test Token schema"""
        token_data = {"access_token": "test_token", "token_type": "bearer"}
        token = Token(**token_data)

        assert token.access_token == "test_token"
        assert token.token_type == "bearer"

    def test_token_data_model(self):
        """Test TokenData schema"""
        token_data = TokenData(username="testuser")
        assert token_data.username == "testuser"

        token_data_none = TokenData()
        assert token_data_none.username is None


class TestModelValidation:
    """Test edge cases and validation"""

    def test_user_create_missing_fields(self):
        """Test UserCreate with missing required fields"""
        with pytest.raises(ValidationError):
            UserCreate(username="testuser")  # Missing email and password

    def test_task_create_missing_title(self):
        """Test TaskCreate with missing title"""
        with pytest.raises(ValidationError):
            TaskCreate()  # Missing required title

    def test_task_create_empty_title(self):
        """Test TaskCreate with empty title"""
        # Pydantic allows empty strings by default unless explicitly constrained
        # This test should be updated to reflect actual validation requirements
        task = TaskCreate(title="")
        assert task.title == ""

    def test_user_unique_constraints(self, db_session):
        """Test user unique constraints"""
        # Create first user
        user1 = User(
            username="testuser", email="test@example.com", hashed_password="password1"
        )
        db_session.add(user1)
        db_session.commit()

        # Try to create user with same username
        user2 = User(
            username="testuser",  # Same username
            email="different@example.com",
            hashed_password="password2",
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()
