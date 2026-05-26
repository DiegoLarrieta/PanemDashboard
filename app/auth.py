"""Bcrypt password hashing + JWT cookie session + role dependencies."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import User

COOKIE_NAME = "panem_session"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def issue_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "u": user.username,
        "r": user.role,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session") from e


def current_user(
    panem_session: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_session),
) -> User:
    if not panem_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = _decode(panem_session)
    user_id = int(payload["sub"])
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def current_user_optional(
    panem_session: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_session),
) -> Optional[User]:
    if not panem_session:
        return None
    try:
        payload = _decode(panem_session)
        return db.get(User, int(payload["sub"]))
    except HTTPException:
        return None


def require_analyst(user: User = Depends(current_user)) -> User:
    if user.role != "analyst":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Analyst role required")
    return user


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    u = db.exec(select(User).where(User.username == username)).first()
    if not u or not verify_password(password, u.password_hash):
        return None
    return u
