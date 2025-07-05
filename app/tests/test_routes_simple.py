"""
Simplified route tests with better database isolation
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base, get_db
from app.main import app


@pytest.fixture(scope="function")
def test_client():
    """Create a test client with isolated database"""
    # Create a fresh in-memory database for each test
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Override the dependency
    original_dependency = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        # Restore original dependency
        if original_dependency:
            app.dependency_overrides[get_db] = original_dependency
        else:
            app.dependency_overrides.pop(get_db, None)


def test_register_user_success(test_client):
    """Test successful user registration"""
    user_data = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "newpassword123",
    }

    response = test_client.post("/api/register", json=user_data)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "hashed_password" not in data  # Should not expose password


def test_register_duplicate_user(test_client):
    """Test registration with duplicate username"""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123",
    }

    # First registration should succeed
    response1 = test_client.post("/api/register", json=user_data)
    assert response1.status_code == 200

    # Second registration with same username should fail
    user_data2 = {
        "username": "testuser",  # Same username
        "email": "different@example.com",
        "password": "password123",
    }
    response2 = test_client.post("/api/register", json=user_data2)
    assert response2.status_code == 400
    assert "Username already registered" in response2.json()["detail"]


def test_login_success(test_client):
    """Test successful login"""
    # First register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
    }
    register_response = test_client.post("/api/register", json=user_data)
    assert register_response.status_code == 200

    # Now try to login
    login_data = {"username": "testuser", "password": "testpassword"}
    response = test_client.post("/api/login", data=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 50  # JWT tokens are long


def test_login_wrong_password(test_client):
    """Test login with wrong password"""
    # First register a user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword",
    }
    register_response = test_client.post("/api/register", json=user_data)
    assert register_response.status_code == 200

    # Try to login with wrong password
    login_data = {"username": "testuser", "password": "wrongpassword"}
    response = test_client.post("/api/login", data=login_data)

    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["detail"]
