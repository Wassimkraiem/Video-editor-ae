from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings


try:
    from pwdlib import PasswordHash

    _password_hash = PasswordHash.recommended()
except ImportError:  # pragma: no cover - used only in minimal local installs
    _password_hash = None


def hash_password(password: str) -> str:
    if _password_hash:
        return _password_hash.hash(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if _password_hash:
        return _password_hash.verify(password, encoded)
    try:
        _, salt_hex, digest_hex = encoded.split("$", 2)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(subject: str, token_type: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject, "type": token_type, "iat": now, "exp": now + timedelta(seconds=ttl_seconds)},
        get_settings().access_token_secret,
        algorithm="HS256",
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, object]:
    try:
        payload = jwt.decode(token, get_settings().access_token_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


bearer = HTTPBearer(auto_error=False)


def current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    token = credentials.credentials if credentials else request.headers.get("X-Access-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(decode_token(token)["sub"])


def optional_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str | None:
    """Like ``current_user_id`` but for routes that also accept signed URLs."""

    token = credentials.credentials if credentials else request.headers.get("X-Access-Token")
    return str(decode_token(token)["sub"]) if token else None
