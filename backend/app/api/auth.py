"""Opaque, HTTP-only cookie authentication backed by persisted sessions."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.database import get_db
from backend.app.models import AuthSession, User

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; username: str; email: str; is_active: bool

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"
def verify_password(password: str, encoded: str | None) -> bool:
    try:
        _, salt, digest = (encoded or "").split("$", 2)
        return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$", 2)[2], digest)
    except (ValueError, TypeError): return False
def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()
def safe_user(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), username=user.username or user.email, email=user.email, is_active=user.is_active)
def establish_session(user: User, response: Response, db: Session) -> None:
    token = secrets.token_urlsafe(32); settings = get_settings()
    db.add(AuthSession(token_hash=token_hash(token), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours))); db.commit()
    response.set_cookie(settings.session_cookie_name, token, httponly=True, secure=settings.session_secure, samesite="lax", max_age=settings.session_ttl_hours * 3600, path="/")

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token: raise HTTPException(status_code=401, detail="Not authenticated.")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else session.expires_at if session else None
    if not session or expires_at <= datetime.now(timezone.utc):
        if session: db.delete(session); db.commit()
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = db.get(User, session.user_id)
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="Not authenticated.")
    return user

@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> UserResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    establish_session(user, response, db)
    return safe_user(user)
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> UserResponse:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", payload.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if db.scalar(select(User).where((User.username == payload.username) | (User.email == payload.email))):
        raise HTTPException(status_code=409, detail="An account with those details already exists.")
    user = User(email=payload.email, username=payload.username, full_name=payload.username, password_hash=hash_password(payload.password), is_active=True)
    try:
        db.add(user); db.commit(); db.refresh(user)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with those details already exists.") from error
    establish_session(user, response, db)
    return safe_user(user)
@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse: return safe_user(user)
@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    name = get_settings().session_cookie_name; token = request.cookies.get(name)
    if token: db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token))); db.commit()
    response.delete_cookie(name, path="/"); response.status_code = status.HTTP_204_NO_CONTENT; return response
