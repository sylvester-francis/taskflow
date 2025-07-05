"""
Pytest configuration and shared fixtures
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.auth import create_access_token, get_password_hash
from app.backend.database import Base, get_db
from app.backend.models import Task, User
from app.main import app


# Test database URL - use in-memory SQLite for speed
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine for the session"""
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    return engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    """Create session factory for testing"""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session(test_engine, test_session_factory):
    """Create a fresh database session for each test"""
    # Create tables
    Base.metadata.create_all(bind=test_engine)

    # Create session
    session = test_session_factory()
    
    try:
        yield session
    finally:
        session.close()
        # Drop tables to ensure clean state
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(test_engine, test_session_factory):
    """Create FastAPI test client with test database"""
    # Create tables
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    # Override dependency
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Clean up
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123"
    }


@pytest.fixture
def sample_task_data():
    """Sample task data for testing"""
    return {
        "title": "Test Task",
        "description": "This is a test task",
        "priority": "medium"
    }


@pytest.fixture
def test_user(db_session, sample_user_data):
    """Create a test user in the database"""
    user = User(
        username=sample_user_data["username"],
        email=sample_user_data["email"],
        hashed_password=get_password_hash(sample_user_data["password"]),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_2(db_session):
    """Create a second test user"""
    user = User(
        username="testuser2",
        email="test2@example.com",
        hashed_password=get_password_hash("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_task(db_session, test_user, sample_task_data):
    """Create a test task in the database"""
    task = Task(
        title=sample_task_data["title"],
        description=sample_task_data["description"],
        priority=sample_task_data["priority"],
        owner_id=test_user.id
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def completed_task(db_session, test_user):
    """Create a completed test task"""
    task = Task(
        title="Completed Task",
        description="This task is completed",
        priority="high",
        completed=True,
        owner_id=test_user.id
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def multiple_tasks(db_session, test_user):
    """Create multiple test tasks"""
    tasks = []
    for i in range(5):
        task = Task(
            title=f"Task {i+1}",
            description=f"Description for task {i+1}",
            priority=["low", "medium", "high"][i % 3],
            completed=(i % 2 == 0),
            owner_id=test_user.id
        )
        tasks.append(task)
    
    db_session.add_all(tasks)
    db_session.commit()
    
    for task in tasks:
        db_session.refresh(task)
    
    return tasks


@pytest.fixture
def auth_token(test_user):
    """Create authentication token for test user"""
    return create_access_token({"sub": test_user.username})


@pytest.fixture
def auth_headers(auth_token):
    """Create authentication headers"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def auth_token_2(test_user_2):
    """Create authentication token for second test user"""
    return create_access_token({"sub": test_user_2.username})


@pytest.fixture
def auth_headers_2(auth_token_2):
    """Create authentication headers for second user"""
    return {"Authorization": f"Bearer {auth_token_2}"}


@pytest.fixture
def temp_database_file():
    """Create temporary database file for file-based tests"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name
    
    try:
        yield db_path
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest settings"""
    # Add custom markers
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "auth: mark test as authentication related"
    )
    config.addinivalue_line(
        "markers", "database: mark test as database related"
    )


# Test environment cleanup
@pytest.fixture(autouse=True)
def clean_environment():
    """Clean environment variables for each test"""
    # Store original environment
    original_env = os.environ.copy()
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# Mock external dependencies
@pytest.fixture
def mock_external_api():
    """Mock external API calls"""
    # This can be used for mocking external services
    # when the application integrates with external APIs
    pass


# Performance testing helpers
@pytest.fixture
def benchmark_database_operations():
    """Helper for benchmarking database operations"""
    import time
    
    def benchmark(operation, *args, **kwargs):
        start_time = time.time()
        result = operation(*args, **kwargs)
        end_time = time.time()
        return result, end_time - start_time
    
    return benchmark


# Error simulation helpers
@pytest.fixture
def simulate_database_error():
    """Helper for simulating database errors"""
    class DatabaseErrorSimulator:
        def __init__(self, session):
            self.session = session
            self.original_commit = session.commit
            self.error_on_next_commit = False
        
        def enable_error(self):
            self.error_on_next_commit = True
            
        def mock_commit(self):
            if self.error_on_next_commit:
                self.error_on_next_commit = False
                raise Exception("Simulated database error")
            return self.original_commit()
    
    return DatabaseErrorSimulator