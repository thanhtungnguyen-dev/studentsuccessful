"""Cryptographic security utilities for authentication, hashing, and token verification."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

# Standard Argon2id hasher
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hashes a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash in constant time."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    """Generates a cryptographically strong random token (256-bit default = 64 hex characters)."""
    return secrets.token_hex(nbytes)


def hash_token(token: str) -> str:
    """Computes SHA-256 hex digest of a raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(raw_token: str, expected_hash: str) -> bool:
    """Verifies a raw token against an expected SHA-256 hash in constant time."""
    if not raw_token or not expected_hash:
        return False
    candidate_hash = hash_token(raw_token)
    return hmac.compare_digest(candidate_hash, expected_hash)


def normalize_email(email: str) -> str:
    """Normalizes email by lowercasing and trimming whitespace."""
    return email.strip().lower()


__all__ = [
    "hash_password",
    "verify_password",
    "generate_secure_token",
    "hash_token",
    "verify_token",
    "normalize_email",
]
