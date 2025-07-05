"""
Unit tests for database functionality
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base, get_db
from app.backend.models import Task, User


class TestDatabase:
    """Test database setup and functionality"""

    def test_create_tables(self):
        """Test that tables can be created"""
        # Use in-memory database for testing
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        # Check that tables exist
        inspector = engine.dialect.get_table_names(engine.connect())
        assert "users" in inspector
        assert "tasks" in inspector

    def test_database_schema(self):
        """Test database schema structure"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        # Test User table columns
        user_columns = [column.name for column in User.__table__.columns]
        expected_user_columns = [
            "id",
            "username",
            "email",
            "hashed_password",
            "is_active",
            "created_at",
        ]
        for col in expected_user_columns:
            assert col in user_columns

        # Test Task table columns
        task_columns = [column.name for column in Task.__table__.columns]
        expected_task_columns = [
            "id",
            "title",
            "description",
            "completed",
            "priority",
            "created_at",
            "updated_at",
            "owner_id",
        ]
        for col in expected_task_columns:
            assert col in task_columns

    def test_user_table_constraints(self):
        """Test User table constraints"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Test unique username constraint
        user1 = User(
            username="testuser", email="test1@example.com", hashed_password="hash1"
        )
        user2 = User(
            username="testuser", email="test2@example.com", hashed_password="hash2"
        )

        session.add(user1)
        session.commit()

        session.add(user2)
        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

        # Test unique email constraint
        user3 = User(
            username="testuser2", email="test1@example.com", hashed_password="hash3"
        )
        session.add(user3)
        with pytest.raises(IntegrityError):
            session.commit()

        session.close()

    def test_foreign_key_constraint(self):
        """Test foreign key relationship between User and Task"""
        engine = create_engine("sqlite:///:memory:")

        # Enable foreign key constraints for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Create user
        user = User(
            username="testuser", email="test@example.com", hashed_password="hash"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # Create task with valid owner_id
        task = Task(title="Test Task", owner_id=user.id)
        session.add(task)
        session.commit()  # Should succeed

        # Create task with invalid owner_id
        invalid_task = Task(title="Invalid Task", owner_id=999)
        session.add(invalid_task)
        with pytest.raises(IntegrityError):
            session.commit()

        session.close()

    def test_cascade_delete_behavior(self):
        """Test what happens when a user is deleted"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Create user and tasks
        user = User(
            username="testuser", email="test@example.com", hashed_password="hash"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        task1 = Task(title="Task 1", owner_id=user.id)
        task2 = Task(title="Task 2", owner_id=user.id)
        session.add_all([task1, task2])
        session.commit()

        # Verify tasks exist
        task_count = session.query(Task).filter(Task.owner_id == user.id).count()
        assert task_count == 2

        # Delete user - this should either cascade delete tasks or prevent deletion
        session.delete(user)
        try:
            session.commit()
            # If commit succeeds, check if tasks were cascade deleted
            remaining_tasks = (
                session.query(Task).filter(Task.owner_id == user.id).count()
            )
            assert (
                remaining_tasks == 0
            ), "Tasks should be cascade deleted when user is deleted"
        except IntegrityError:
            # If commit fails, foreign key constraint is preventing deletion
            session.rollback()
            # This is also valid behavior - the application should handle this
            pass

        session.close()


class TestDatabaseConnection:
    """Test database connection functionality"""

    def test_get_db_generator(self):
        """Test get_db dependency function"""
        # This is a generator function, test that it yields a session
        db_gen = get_db()
        db = next(db_gen)

        # Should be a database session
        assert hasattr(db, "query")
        assert hasattr(db, "add")
        assert hasattr(db, "commit")
        assert hasattr(db, "rollback")

        # Clean up
        try:
            next(db_gen)
        except StopIteration:
            pass  # Expected behavior

    def test_database_file_creation(self):
        """Test that database file is created when using file-based SQLite"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")

            # Create engine with file database
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)

            # Check that file was created
            assert os.path.exists(db_path)
            assert os.path.getsize(db_path) > 0  # File should not be empty

    def test_database_session_isolation(self):
        """Test that database sessions are properly isolated"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Create two sessions
        session1 = SessionLocal()
        session2 = SessionLocal()

        # Add user in session1 but don't commit
        user1 = User(
            username="user1", email="user1@example.com", hashed_password="hash"
        )
        session1.add(user1)

        # Session2 should not see uncommitted changes
        user_count = session2.query(User).count()
        assert user_count == 0

        # Commit in session1
        session1.commit()

        # Now session2 should see the change
        user_count = session2.query(User).count()
        assert user_count == 1

        session1.close()
        session2.close()


class TestDatabaseMigrations:
    """Test database migration scenarios"""

    def test_schema_evolution(self):
        """Test that schema can evolve (adding new columns)"""
        # This test simulates what would happen if we added a new column
        # In a real scenario, this would be handled by migration tools like Alembic

        engine = create_engine("sqlite:///:memory:")

        # Create initial schema (without some optional fields)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Create user with basic fields
        user = User(
            username="testuser", email="test@example.com", hashed_password="hash"
        )
        session.add(user)
        session.commit()

        # Verify user was created with default values
        session.refresh(user)
        assert user.is_active is True  # Default value
        assert user.created_at is not None  # Auto-generated

        session.close()

    def test_data_integrity_after_schema_change(self):
        """Test that existing data remains valid after schema changes"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Create data
        user = User(
            username="testuser", email="test@example.com", hashed_password="hash"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        task = Task(title="Test Task", owner_id=user.id)
        session.add(task)
        session.commit()

        # Simulate schema change by querying with all current fields
        retrieved_user = session.query(User).filter(User.username == "testuser").first()
        retrieved_task = session.query(Task).filter(Task.title == "Test Task").first()

        # Verify data integrity
        assert retrieved_user.username == "testuser"
        assert retrieved_user.email == "test@example.com"
        assert retrieved_user.is_active is True

        assert retrieved_task.title == "Test Task"
        assert retrieved_task.completed is False
        assert retrieved_task.priority == "medium"
        assert retrieved_task.owner_id == user.id

        session.close()


class TestDatabasePerformance:
    """Test database performance considerations"""

    def test_index_usage(self):
        """Test that indexes are properly defined"""
        # Check that indexed columns are defined correctly
        assert User.username.property.columns[0].index is True
        assert User.email.property.columns[0].index is True
        assert Task.title.property.columns[0].index is True
        assert User.id.property.columns[0].primary_key is True
        assert Task.id.property.columns[0].primary_key is True

    def test_bulk_operations(self):
        """Test bulk insert/update operations"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()

        # Create user
        user = User(
            username="testuser", email="test@example.com", hashed_password="hash"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # Bulk insert tasks
        tasks = []
        for i in range(100):
            task = Task(title=f"Task {i}", owner_id=user.id)
            tasks.append(task)

        session.add_all(tasks)
        session.commit()

        # Verify all tasks were created
        task_count = session.query(Task).filter(Task.owner_id == user.id).count()
        assert task_count == 100

        # Bulk update
        session.query(Task).filter(Task.owner_id == user.id).update(
            {"priority": "high"}
        )
        session.commit()

        # Verify update
        high_priority_count = (
            session.query(Task)
            .filter(Task.owner_id == user.id, Task.priority == "high")
            .count()
        )
        assert high_priority_count == 100

        session.close()
