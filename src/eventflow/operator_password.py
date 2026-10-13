"""Password hashing for locally provisioned demo operators."""

import base64
import binascii
import hashlib
import hmac
import re
import secrets

USERNAME_PATTERN = re.compile(r"[a-z][a-z0-9._-]{2,79}\Z")
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
HASH_BYTES = 32


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must be 3 to 80 lowercase letters, digits, dots, underscores or hyphens"
        )
    return username


def password_digest(raw_password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        raw_password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=HASH_BYTES,
    )


def hash_password(raw_password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = password_digest(raw_password, salt)
    return ":".join(
        (
            "scrypt-v1",
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(raw_password: str, stored: str) -> bool:
    try:
        version, encoded_salt, encoded_digest = stored.split(":")
        if version != "scrypt-v1":
            return False
        salt = base64.b64decode(encoded_salt, altchars=b"-_", validate=True)
        expected = base64.b64decode(encoded_digest, altchars=b"-_", validate=True)
        if len(salt) != SALT_BYTES or len(expected) != HASH_BYTES:
            return False
        return hmac.compare_digest(password_digest(raw_password, salt), expected)
    except (ValueError, UnicodeError, binascii.Error):
        return False


DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")
