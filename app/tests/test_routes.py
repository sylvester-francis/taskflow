"""
Unit tests for API routes
"""

import pytest

from app.backend.auth import create_access_token, get_password_hash
from app.backend.models import Task, User


class TestUserRegistration:
    """Test user registration endpoint"""

    def test_register_user_success(self, client):
        """Test successful user registration"""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpassword123",
        }

        response = client.post("/api/register", json=user_data)

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        assert "hashed_password" not in data  # Should not expose password

    def test_register_user_duplicate_username(self, client, test_user):
        """Test registration with duplicate username"""
        user_data = {
            "username": "testuser",  # Same as existing user
            "email": "different@example.com",
            "password": "password123",
        }

        response = client.post("/api/register", json=user_data)

        assert response.status_code == 400
        assert "Username already registered" in response.json()["detail"]

    def test_register_user_invalid_data(self, client):
        """Test registration with invalid data"""
        user_data = {
            "username": "",  # Empty username
            "email": "test@example.com",
            "password": "password123",
        }

        response = client.post("/api/register", json=user_data)
        assert response.status_code == 422  # Validation error

    def test_register_user_missing_fields(self, client):
        """Test registration with missing fields"""
        user_data = {
            "username": "testuser"
            # Missing email and password
        }

        response = client.post("/api/register", json=user_data)
        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Test user login endpoint"""

    def test_login_success(self, client, test_user):
        """Test successful login"""
        login_data = {"username": "testuser", "password": "testpassword"}

        response = client.post("/api/login", data=login_data)

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50  # JWT tokens are long

    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password"""
        login_data = {"username": "testuser", "password": "wrongpassword"}

        response = client.post("/api/login", data=login_data)

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user"""
        login_data = {"username": "nonexistent", "password": "password"}

        response = client.post("/api/login", data=login_data)

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_missing_credentials(self, client):
        """Test login with missing credentials"""
        response = client.post("/api/login", data={})
        assert response.status_code == 422  # Validation error


class TestTaskEndpoints:
    """Test task-related endpoints"""

    def test_get_tasks_authenticated(self, client, test_user, test_task, auth_headers):
        """Test getting tasks as authenticated user"""
        response = client.get("/api/tasks", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Task"
        assert data[0]["description"] == "Test Description"
        assert data[0]["priority"] == "high"
        assert data[0]["completed"] is False

    def test_get_tasks_unauthenticated(self, client):
        """Test getting tasks without authentication"""
        response = client.get("/api/tasks")
        assert response.status_code == 401

    def test_get_tasks_invalid_token(self, client):
        """Test getting tasks with invalid token"""
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/tasks", headers=headers)
        assert response.status_code == 401

    def test_create_task_success(self, client, test_user, auth_headers):
        """Test creating a task"""
        task_data = {
            "title": "New Task",
            "description": "New Description",
            "priority": "medium",
        }

        response = client.post("/api/tasks", json=task_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Task"
        assert data["description"] == "New Description"
        assert data["priority"] == "medium"
        assert data["completed"] is False
        assert "id" in data
        assert "created_at" in data

    def test_create_task_minimal_data(self, client, test_user, auth_headers):
        """Test creating task with minimal data"""
        task_data = {"title": "Minimal Task"}

        response = client.post("/api/tasks", json=task_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Minimal Task"
        assert data["description"] is None
        assert data["priority"] == "medium"  # Default value

    def test_create_task_unauthenticated(self, client):
        """Test creating task without authentication"""
        task_data = {"title": "Test Task"}
        response = client.post("/api/tasks", json=task_data)
        assert response.status_code == 401

    def test_create_task_invalid_data(self, client, test_user, auth_headers):
        """Test creating task with invalid data"""
        task_data = {}  # Missing required title
        response = client.post("/api/tasks", json=task_data, headers=auth_headers)
        assert response.status_code == 422

    def test_update_task_success(self, client, test_user, test_task, auth_headers):
        """Test updating a task"""
        update_data = {"title": "Updated Task", "completed": True, "priority": "low"}

        response = client.put(
            f"/api/tasks/{test_task.id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Task"
        assert data["completed"] is True
        assert data["priority"] == "low"
        assert data["description"] == "Test Description"  # Unchanged

    def test_update_task_partial(self, client, test_user, test_task, auth_headers):
        """Test partial task update"""
        update_data = {"completed": True}

        response = client.put(
            f"/api/tasks/{test_task.id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is True
        assert data["title"] == "Test Task"  # Unchanged

    def test_update_task_not_found(self, client, test_user, auth_headers):
        """Test updating non-existent task"""
        update_data = {"title": "Updated Task"}

        response = client.put("/api/tasks/999", json=update_data, headers=auth_headers)

        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    def test_update_task_unauthenticated(self, client, test_task):
        """Test updating task without authentication"""
        update_data = {"title": "Updated Task"}
        response = client.put(f"/api/tasks/{test_task.id}", json=update_data)
        assert response.status_code == 401

    def test_update_other_user_task(self, client, db_session, test_task):
        """Test updating another user's task"""
        # Create another user
        other_user = User(
            username="otheruser",
            email="other@example.com",
            hashed_password=get_password_hash("password"),
        )
        db_session.add(other_user)
        db_session.commit()

        # Create token for other user
        token = create_access_token({"sub": "otheruser"})
        headers = {"Authorization": f"Bearer {token}"}

        update_data = {"title": "Hacked Task"}
        response = client.put(
            f"/api/tasks/{test_task.id}", json=update_data, headers=headers
        )

        assert (
            response.status_code == 404
        )  # Should not find task owned by different user

    def test_delete_task_success(self, client, test_user, test_task, auth_headers):
        """Test deleting a task"""
        response = client.delete(f"/api/tasks/{test_task.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "Task deleted successfully" in data["message"]

        # Verify task is deleted
        get_response = client.get("/api/tasks", headers=auth_headers)
        tasks = get_response.json()
        assert len(tasks) == 0

    def test_delete_task_not_found(self, client, test_user, auth_headers):
        """Test deleting non-existent task"""
        response = client.delete("/api/tasks/999", headers=auth_headers)

        assert response.status_code == 404
        assert "Task not found" in response.json()["detail"]

    def test_delete_task_unauthenticated(self, client, test_task):
        """Test deleting task without authentication"""
        response = client.delete(f"/api/tasks/{test_task.id}")
        assert response.status_code == 401

    def test_delete_other_user_task(self, client, db_session, test_task):
        """Test deleting another user's task"""
        # Create another user
        other_user = User(
            username="otheruser",
            email="other@example.com",
            hashed_password=get_password_hash("password"),
        )
        db_session.add(other_user)
        db_session.commit()

        # Create token for other user
        token = create_access_token({"sub": "otheruser"})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.delete(f"/api/tasks/{test_task.id}", headers=headers)

        assert (
            response.status_code == 404
        )  # Should not find task owned by different user


class TestUserIsolation:
    """Test that users can only access their own data"""

    def test_users_see_only_own_tasks(self, client, db_session):
        """Test that users only see their own tasks"""
        # Create two users
        user1 = User(
            username="user1",
            email="user1@example.com",
            hashed_password=get_password_hash("password1"),
        )
        user2 = User(
            username="user2",
            email="user2@example.com",
            hashed_password=get_password_hash("password2"),
        )
        db_session.add_all([user1, user2])
        db_session.commit()
        db_session.refresh(user1)
        db_session.refresh(user2)

        # Create tasks for each user
        task1 = Task(title="User 1 Task", owner_id=user1.id)
        task2 = Task(title="User 2 Task", owner_id=user2.id)
        db_session.add_all([task1, task2])
        db_session.commit()

        # User 1 should only see their task
        token1 = create_access_token({"sub": "user1"})
        headers1 = {"Authorization": f"Bearer {token1}"}
        response1 = client.get("/api/tasks", headers=headers1)

        assert response1.status_code == 200
        tasks1 = response1.json()
        assert len(tasks1) == 1
        assert tasks1[0]["title"] == "User 1 Task"

        # User 2 should only see their task
        token2 = create_access_token({"sub": "user2"})
        headers2 = {"Authorization": f"Bearer {token2}"}
        response2 = client.get("/api/tasks", headers=headers2)

        assert response2.status_code == 200
        tasks2 = response2.json()
        assert len(tasks2) == 1
        assert tasks2[0]["title"] == "User 2 Task"
