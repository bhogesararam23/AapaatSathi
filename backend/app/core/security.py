"""Password hashing and JWT issuing.

``bcrypt`` is used directly rather than through ``passlib``: the passlib/bcrypt
4.x version dance has broken more hackathon demos than it has saved. Passwords
are SHA-256 pre-hashed so that inputs longer than bcrypt's 72-byte limit do not
raise (the same approach Django's bcrypt hasher takes).
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

__all__ = [
    "hash_password",
    "verify_password",
    "create_token",
    "decode_token",
    "password_problems",
    "generate_code",
    "ALGORITHM",
]

ALGORITHM = settings.jwt_algorithm


def _prep(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prep(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(
    subject: str | int,
    *,
    role: str,
    token_type: str = "access",
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    minutes = expires_minutes or (
        settings.access_token_minutes
        if token_type == "access"
        else settings.refresh_token_minutes
    )
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate. Raises ``jwt.PyJWTError`` subclasses on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def password_problems(password: str) -> list[str]:
    """Return human-readable policy failures (empty list == acceptable).

    The letter test is Unicode-aware on purpose. This product's users type in
    Devanagari; a ``[A-Za-z]`` check would tell a Hindi or Garhwali speaker that
    their passphrase "must contain a letter" and lock them out of registering —
    while the SHA-256 pre-hash below handles those characters perfectly well.
    """
    problems: list[str] = []
    if len(password) < 8:
        problems.append("must be at least 8 characters")
    if not re.search(r"[^\W\d_]", password, re.UNICODE):
        problems.append("must contain a letter")
    if not re.search(r"\d", password):
        problems.append("must contain a digit")
    if len(password) > 128:
        problems.append("must be at most 128 characters")
    return problems


def generate_code(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(2).upper()}"
