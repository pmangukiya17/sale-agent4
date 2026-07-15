from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# Hashing goes straight through `bcrypt`, deliberately without passlib as a
# middle layer. passlib has been unmaintained since 2020 and its bcrypt
# backend detects which code path to use by probing `bcrypt.__about__`, a
# submodule bcrypt itself removed in 4.1.0. That broken probe is what caused
# the AttributeError and the incorrect 72-byte handling seen during startup.
# bcrypt's own public API (hashpw/checkpw/gensalt) has been stable across the
# 3.x and 4.x lines, so calling it directly removes the fragile dependency
# instead of pinning around it.
_BCRYPT_ROUNDS = 12
_MAX_PASSWORD_BYTES = 72  # hard limit of the bcrypt algorithm itself


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        # Reject at the boundary rather than silently truncating (bcrypt<4's
        # old behavior) or letting bcrypt>=4 raise its own less-actionable
        # ValueError deeper in the call stack.
        raise ValueError(
            f"Password must be at most {_MAX_PASSWORD_BYTES} bytes "
            f"(got {len(password_bytes)})."
        )
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"exp": expire, "sub": subject}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
