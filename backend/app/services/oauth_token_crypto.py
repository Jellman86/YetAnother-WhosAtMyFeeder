"""Helpers for encrypting OAuth tokens at rest."""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet

from app.config import settings

ENCRYPTED_TOKEN_PREFIX = "enc:"


def _get_fernet() -> Fernet:
    secret_value = getattr(settings.auth, "oauth_token_secret", None) or settings.auth.session_secret or ""
    secret = secret_value.encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted_token(value: Optional[str]) -> bool:
    return bool(value and value.startswith(ENCRYPTED_TOKEN_PREFIX))


def encrypt_oauth_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if is_encrypted_token(value):
        return value
    encrypted = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_TOKEN_PREFIX}{encrypted}"


def decrypt_oauth_token(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if not is_encrypted_token(value):
        return value
    token = value[len(ENCRYPTED_TOKEN_PREFIX) :]
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
