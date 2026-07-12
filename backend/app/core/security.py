"""Password hashing and JWT issuance/verification.

WHY argon2 (via argon2-cffi) over bcrypt: it's the PHC winner and the current
OWASP recommendation, and the library exposes a single `PasswordHasher` with
sane defaults — no separate salt handling to get wrong.

WHY a hand-rolled JWT helper instead of a bigger auth framework: this phase
needs exactly two operations (issue a token, verify a token) with one claim
(the user id). PyJWT does that in a few lines; anything more is the
"no OAuth providers yet, don't gold-plate" the phase spec asks for.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    """Returns the user id encoded in the token. Raises jwt.PyJWTError (or
    ValueError for a malformed subject) on any invalid/expired token — callers
    turn that into a 401, they don't need to inspect the exception type."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    return uuid.UUID(payload["sub"])
