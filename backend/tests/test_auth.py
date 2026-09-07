"""Dedicated authentication, session, and inspection-ownership coverage."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from backend.app.api.auth import get_current_user, hash_password, token_hash
from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models import AuthSession, Base, Inspection, User


@pytest.fixture
def auth_database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with sessions() as session:
            yield session

    # The legacy test suite supplies an inspection-only principal globally.
    # Dedicated auth tests must instead use the real cookie/session dependency.
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = override_db
    yield sessions
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def auth_client(auth_database):
    with TestClient(app) as client:
        yield client


def create_user(sessions, username: str, password: str = "correct-horse-battery-staple") -> User:
    with sessions() as db:
        user = User(
            email=f"{username}@example.invalid",
            username=username,
            full_name=username.title(),
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        return user


@pytest.fixture
def test_user(auth_database) -> User:
    return create_user(auth_database, "first-user")


@pytest.fixture
def second_test_user(auth_database) -> User:
    return create_user(auth_database, "second-user", "another-correct-password")


@pytest.fixture
def authenticated_client(auth_client, test_user) -> TestClient:
    response = auth_client.post("/api/auth/login", json={"username": test_user.username, "password": "correct-horse-battery-staple"})
    assert response.status_code == 200
    return auth_client


@pytest.fixture
def second_authenticated_client(auth_database, second_test_user) -> TestClient:
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": second_test_user.username, "password": "another-correct-password"})
        assert response.status_code == 200
        yield client


@pytest.fixture
def authenticated_session(authenticated_client, auth_database, test_user) -> AuthSession:
    with auth_database() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == test_user.id))
        assert session is not None
        return session


def test_user_creation_hashes_password_and_never_stores_plaintext(auth_database) -> None:
    password = "correct-horse-battery-staple"
    user = create_user(auth_database, "created-user", password)
    with auth_database() as db:
        stored = db.get(User, user.id)
        assert stored is not None
        assert stored.password_hash.startswith("scrypt$")
        assert stored.password_hash != password
        assert password not in stored.password_hash


def test_duplicate_username_is_rejected(auth_database) -> None:
    create_user(auth_database, "duplicate-user")
    with pytest.raises(IntegrityError):
        create_user(auth_database, "duplicate-user")


def test_valid_login_establishes_session_and_me_returns_user(authenticated_client, authenticated_session, test_user) -> None:
    response = authenticated_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(test_user.id), "username": test_user.username,
        "email": test_user.email, "is_active": True,
    }
    assert authenticated_session.token_hash != authenticated_client.cookies[get_settings().session_cookie_name]


@pytest.mark.parametrize("username,password", [
    ("first-user", "wrong-password"),
    ("missing-user", "correct-horse-battery-staple"),
])
def test_invalid_login_credentials_are_generic(auth_client, test_user, username: str, password: str) -> None:
    response = auth_client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}


def test_me_without_a_session_returns_401(auth_client) -> None:
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_expired_session_returns_401(auth_client, auth_database, test_user) -> None:
    token = "expired-test-token"
    with auth_database() as db:
        db.add(AuthSession(token_hash=token_hash(token), user_id=test_user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    auth_client.cookies.set(get_settings().session_cookie_name, token)
    assert auth_client.get("/api/auth/me").status_code == 401


def test_logout_revokes_the_authenticated_session(authenticated_client) -> None:
    assert authenticated_client.post("/api/auth/logout").status_code == 204
    assert authenticated_client.get("/api/auth/me").status_code == 401


def test_unauthenticated_inspection_creation_returns_401(auth_client) -> None:
    assert auth_client.post("/api/inspections", json={}).status_code == 401


def test_authenticated_inspection_creation_records_the_current_user(authenticated_client, auth_database, test_user) -> None:
    response = authenticated_client.post("/api/inspections", json={})
    assert response.status_code == 201
    with auth_database() as db:
        inspection = db.get(Inspection, UUID(response.json()["id"]))
        assert inspection is not None
        assert inspection.user_id == test_user.id


def test_owner_can_access_own_inspection(authenticated_client) -> None:
    inspection = authenticated_client.post("/api/inspections", json={}).json()
    assert authenticated_client.get(f"/api/inspections/{inspection['id']}").status_code == 200


@pytest.fixture
def owned_inspection(authenticated_client) -> dict:
    response = authenticated_client.post("/api/inspections", json={})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("operation", [
    "access", "upload", "ocr", "extract", "compliance", "process", "retry",
])
def test_second_user_cannot_access_or_operate_on_another_users_inspection(second_authenticated_client, owned_inspection, operation: str) -> None:
    inspection_id = owned_inspection["id"]
    if operation == "access":
        response = second_authenticated_client.get(f"/api/inspections/{inspection_id}")
    elif operation == "upload":
        response = second_authenticated_client.post(f"/api/inspections/{inspection_id}/image", files={"image": ("label.png", b"not-read", "image/png")})
    elif operation == "ocr":
        response = second_authenticated_client.post(f"/api/inspections/{inspection_id}/images/{uuid4()}/ocr")
    elif operation == "extract":
        response = second_authenticated_client.post(f"/api/inspections/{inspection_id}/extract")
    elif operation == "compliance":
        response = second_authenticated_client.post(f"/api/inspections/{inspection_id}/compliance")
    else:
        response = second_authenticated_client.post(f"/api/inspections/{inspection_id}/process")
    assert response.status_code == 404
    assert response.json() == {"detail": "Inspection not found."}


def test_auth_endpoints_do_not_expose_sensitive_authentication_data(authenticated_client, test_user) -> None:
    login_response = authenticated_client.post("/api/auth/login", json={"username": test_user.username, "password": "correct-horse-battery-staple"})
    me_response = authenticated_client.get("/api/auth/me")
    for response in (login_response, me_response):
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {"id", "username", "email", "is_active"}
        serialized = str(payload).lower()
        assert "password" not in serialized
        assert "hash" not in serialized
        assert "token" not in serialized
        assert "session" not in serialized


def test_registration_creates_a_hashed_user_and_authenticated_session(auth_client, auth_database) -> None:
    password = "register-password"
    response = auth_client.post("/api/auth/register", json={"username": "registered-user", "email": "registered@example.invalid", "password": password})
    assert response.status_code == 201
    assert set(response.json()) == {"id", "username", "email", "is_active"}
    assert password not in str(response.json())
    with auth_database() as db:
        user = db.scalar(select(User).where(User.username == "registered-user"))
        assert user and user.password_hash.startswith("scrypt$") and password not in user.password_hash
    assert auth_client.get("/api/auth/me").json()["username"] == "registered-user"


def test_registration_rejects_duplicate_username_and_email(auth_client, test_user) -> None:
    username = test_user.username
    response = auth_client.post("/api/auth/register", json={"username": username, "email": "new@example.invalid", "password": "register-password"})
    assert response.status_code == 409
    response = auth_client.post("/api/auth/register", json={"username": "new-user", "email": test_user.email, "password": "register-password"})
    assert response.status_code == 409


@pytest.mark.parametrize("payload", [
    {"username": "!", "email": "valid@example.invalid", "password": "register-password"},
    {"username": "valid-user", "email": "not-an-email", "password": "register-password"},
    {"username": "valid-user", "email": "valid@example.invalid", "password": "short"},
])
def test_registration_validates_username_email_and_password(auth_client, payload) -> None:
    assert auth_client.post("/api/auth/register", json=payload).status_code == 422


def test_newly_registered_user_can_log_in_after_logout(auth_client) -> None:
    payload = {"username": "login-after-register", "email": "login-after-register@example.invalid", "password": "register-password"}
    assert auth_client.post("/api/auth/register", json=payload).status_code == 201
    assert auth_client.post("/api/auth/logout").status_code == 204
    assert auth_client.post("/api/auth/login", json={"username": payload["username"], "password": payload["password"]}).status_code == 200
