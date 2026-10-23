"""Single-operator signed bearer authentication.

The configured password is stored as a scrypt verifier, never as plaintext.
Tokens are short-lived and signed with the deployment SECRET_KEY.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def auth_is_configured() -> bool:
    secret = settings.SECRET_KEY.encode("utf-8")
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, digest_raw = settings.AUTH_PASSWORD_HASH.split("$", 5)
        password_hash_valid = (
            algorithm == "scrypt"
            and 2**14 <= int(n_raw) <= 2**18
            and int(r_raw) == 8
            and int(p_raw) == 1
            and len(_unb64(salt_raw)) >= 16
            and len(_unb64(digest_raw)) >= 32
        )
    except (ValueError, TypeError):
        password_hash_valid = False
    return bool(
        settings.AUTH_USERNAME.strip()
        and password_hash_valid
        and len(secret) >= 32
        and settings.SECRET_KEY != "dev-secret-key-change-in-production"
    )


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024
    )
    return f"scrypt$32768$8$1${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if (
            algorithm != "scrypt"
            or n < 2**14
            or n > 2**18
            or r != 8
            or p != 1
        ):
            return False
        expected = _unb64(digest_raw)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_raw),
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=256 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False


def issue_token(username: str) -> tuple[str, int]:
    expires_at = int(time.time()) + max(300, min(settings.AUTH_TOKEN_TTL_SECONDS, 604800))
    payload = _b64(
        json.dumps({"sub": username, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
    )
    signature = _b64(
        hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}", expires_at


def verify_token(token: str) -> str | None:
    try:
        payload, signature = token.split(".", 1)
        expected_signature = _b64(
            hmac.new(
                settings.SECRET_KEY.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(signature, expected_signature):
            return None
        claims = json.loads(_unb64(payload))
        username = claims.get("sub")
        expiration = claims.get("exp")
        if (
            not isinstance(username, str)
            or username != settings.AUTH_USERNAME
            or not isinstance(expiration, int)
            or expiration <= int(time.time())
        ):
            return None
        return username
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
