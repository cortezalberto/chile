"""
Pytest configuration and fixtures for backend tests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rest_api.main import app
from rest_api.db import get_db
from rest_api.models import Base, Tenant, Branch, User, UserBranchRole
from shared.password import hash_password


# SQLite in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Create a fresh database session for each test.
    Uses SQLite in-memory for isolation.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    Create a test client with database session override.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def seed_tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Restaurant",
        slug="test",
        description="Test restaurant for unit tests",
        theme_color="#f97316",
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def seed_branch(db_session, seed_tenant):
    """Create a test branch."""
    branch = Branch(
        tenant_id=seed_tenant.id,
        name="Test Branch",
        slug="test-branch",
        address="123 Test St",
        phone="+1234567890",
        opening_time="09:00",
        closing_time="22:00",
    )
    db_session.add(branch)
    db_session.commit()
    db_session.refresh(branch)
    return branch


@pytest.fixture
def seed_admin_user(db_session, seed_tenant, seed_branch):
    """Create an admin user for testing authenticated endpoints."""
    user = User(
        tenant_id=seed_tenant.id,
        email="admin@test.com",
        password=hash_password("testpass123"),
        first_name="Test",
        last_name="Admin",
    )
    db_session.add(user)
    db_session.flush()

    role = UserBranchRole(
        user_id=user.id,
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        role="ADMIN",
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, seed_admin_user):
    """Get authentication headers for API calls."""
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "testpass123"},
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_waiter_user(db_session, seed_tenant, seed_branch):
    """Create a waiter user for testing."""
    user = User(
        tenant_id=seed_tenant.id,
        email="waiter@test.com",
        password=hash_password("waiter123"),
        first_name="Test",
        last_name="Waiter",
    )
    db_session.add(user)
    db_session.flush()

    role = UserBranchRole(
        user_id=user.id,
        tenant_id=seed_tenant.id,
        branch_id=seed_branch.id,
        role="WAITER",
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def waiter_auth_headers(client, seed_waiter_user):
    """Get authentication headers for waiter API calls."""
    response = client.post(
        "/api/auth/login",
        json={"email": "waiter@test.com", "password": "waiter123"},
    )
    assert response.status_code == 200, f"Login failed: {response.json()}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
