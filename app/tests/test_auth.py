"""
Unit tests for authentication functions
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from jose import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.database import Base
from app.backend.models import User
from app.backend.auth import (
    verify_password, get_password_hash, get_user, authenticate_user,
    create_access_token, get_current_user, SECRET_KEY, ALGORITHM
)


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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


@pytest.fixture
def test_user(db_session):
    """Create a test user in the database"""
    hashed_password = get_password_hash("testpassword")
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hashed_password,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestPasswordFunctions:
    """Test password hashing and verification"""
    
    def test_password_hashing(self):
        """Test password hashing"""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password  # Should be different from original
        assert len(hashed) > 50  # Bcrypt hashes are typically 60 chars
        assert hashed.startswith("$2b$")  # Bcrypt format
    
    def test_password_verification_success(self):
        """Test successful password verification"""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_password_verification_failure(self):
        """Test failed password verification"""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = get_password_hash(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_different_passwords_different_hashes(self):
        """Test that same password produces different hashes (salt)"""
        password = "testpassword123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        assert hash1 != hash2  # Should be different due to salt
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestUserFunctions:
    """Test user-related functions"""
    
    def test_get_user_exists(self, db_session, test_user):
        """Test getting an existing user"""
        user = get_user(db_session, "testuser")
        
        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active is True
    
    def test_get_user_not_exists(self, db_session):
        """Test getting a non-existent user"""
        user = get_user(db_session, "nonexistentuser")
        assert user is None
    
    def test_authenticate_user_success(self, db_session, test_user):
        """Test successful user authentication"""
        user = authenticate_user(db_session, "testuser", "testpassword")
        
        assert user is not False
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    def test_authenticate_user_wrong_password(self, db_session, test_user):
        """Test authentication with wrong password"""
        user = authenticate_user(db_session, "testuser", "wrongpassword")
        assert user is False
    
    def test_authenticate_user_not_exists(self, db_session):
        """Test authentication with non-existent user"""
        user = authenticate_user(db_session, "nonexistentuser", "anypassword")
        assert user is False
    
    def test_authenticate_inactive_user(self, db_session):
        """Test authentication with inactive user"""
        hashed_password = get_password_hash("testpassword")
        inactive_user = User(
            username="inactiveuser",
            email="inactive@example.com",
            hashed_password=hashed_password,
            is_active=False
        )
        db_session.add(inactive_user)
        db_session.commit()
        
        # Authentication should still work - is_active is not checked in authenticate_user
        user = authenticate_user(db_session, "inactiveuser", "testpassword")
        assert user is not False
        assert user.is_active is False


class TestTokenFunctions:
    """Test JWT token functions"""
    
    def test_create_access_token_default_expiry(self):
        """Test creating access token with default expiry"""
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are quite long
        
        # Decode and verify
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert "exp" in payload
    
    def test_create_access_token_custom_expiry(self):
        """Test creating access token with custom expiry"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=60)
        token = create_access_token(data, expires_delta)
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        
        # Check expiry is approximately 60 minutes from now
        exp_timestamp = payload["exp"]
        expected_exp = datetime.utcnow() + expires_delta
        actual_exp = datetime.fromtimestamp(exp_timestamp)
        
        # Allow 5 second difference for test execution time
        time_diff = abs((actual_exp - expected_exp).total_seconds())
        assert time_diff < 5
    
    def test_create_access_token_with_extra_data(self):
        """Test creating access token with additional data"""
        data = {"sub": "testuser", "role": "admin", "permissions": ["read", "write"]}
        token = create_access_token(data)
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["permissions"] == ["read", "write"]


class TestGetCurrentUser:
    """Test get_current_user dependency"""
    
    @pytest.mark.asyncio
    async def test_get_current_user_success(self, db_session, test_user):
        """Test successful current user retrieval"""
        # Create a valid token
        token = create_access_token({"sub": "testuser"})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        user = await get_current_user(credentials, db_session)
        
        assert user.username == "testuser"
        assert user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, db_session):
        """Test current user retrieval with invalid token"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid_token"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, db_session)
        
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, db_session, test_user):
        """Test current user retrieval with expired token"""
        # Create an expired token
        expired_time = datetime.utcnow() - timedelta(minutes=30)
        payload = {
            "sub": "testuser",
            "exp": expired_time.timestamp()
        }
        expired_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=expired_token
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, db_session)
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_get_current_user_no_username_in_token(self, db_session):
        """Test current user retrieval with token missing username"""
        # Create token without 'sub' field
        token = create_access_token({"user_id": 123})  # Wrong field name
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, db_session)
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self, db_session):
        """Test current user retrieval when user doesn't exist in database"""
        # Create token for non-existent user
        token = create_access_token({"sub": "nonexistentuser"})
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, db_session)
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_get_current_user_malformed_token(self, db_session):
        """Test current user retrieval with malformed token"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="not.a.jwt.token"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, db_session)
        
        assert exc_info.value.status_code == 401


class TestSecurityConstants:
    """Test security configuration"""
    
    def test_secret_key_exists(self):
        """Test that secret key is configured"""
        assert SECRET_KEY is not None
        assert len(SECRET_KEY) > 10  # Should be reasonably long
    
    def test_algorithm_is_secure(self):
        """Test that a secure algorithm is used"""
        assert ALGORITHM == "HS256"  # Should use a secure algorithm
    
    def test_token_expiry_reasonable(self):
        """Test that token expiry is reasonable"""
        from app.backend.auth import ACCESS_TOKEN_EXPIRE_MINUTES
        assert ACCESS_TOKEN_EXPIRE_MINUTES > 0
        assert ACCESS_TOKEN_EXPIRE_MINUTES <= 1440  # No more than 24 hours