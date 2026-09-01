"""Password, opaque session and CSRF primitives."""

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from pwdlib import PasswordHash

from app.config import config

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_auth_secret() -> bytes:
    if config.auth_secret_key:
        return config.auth_secret_key.encode("utf-8")
    path = Path("./volumes/app/.auth_secret").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip().encode("utf-8")


def csrf_token(session_token: str) -> str:
    return hmac.new(get_auth_secret(), session_token.encode("utf-8"), hashlib.sha256).hexdigest()


def valid_csrf(session_token: str, supplied: str) -> bool:
    return bool(supplied) and hmac.compare_digest(csrf_token(session_token), supplied)
