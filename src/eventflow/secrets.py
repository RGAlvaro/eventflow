"""Authenticated encryption for endpoint signing secrets."""

import base64
import binascii
import json
import os
import secrets
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from eventflow.config import get_settings

PREFIX = b"EFSG1"
NONCE_BYTES = 12


class SecretUnavailable(Exception):
    """A signing secret cannot be read safely; the delivery must remain recoverable."""


def encryption_keys() -> dict[str, bytes]:
    raw = os.getenv("EVENTFLOW_ENCRYPTION_KEYS") or get_settings().encryption_keys
    if not raw:
        raise SecretUnavailable("Encryption keyring is not configured")
    try:
        encoded = json.loads(raw)
        if not isinstance(encoded, dict) or not encoded:
            raise ValueError("Empty encryption keyring")
        keys = {
            key_id: base64.b64decode(value, validate=True)
            for key_id, value in encoded.items()
            if isinstance(key_id, str) and 0 < len(key_id) <= 40 and isinstance(value, str)
        }
        if len(keys) != len(encoded) or any(len(key) != 32 for key in keys.values()):
            raise ValueError("Invalid encryption keyring")
        return keys
    except (ValueError, TypeError, binascii.Error) as exc:
        raise SecretUnavailable("Encryption keyring is invalid") from exc


def active_key_id() -> str:
    key_id = (
        os.getenv("EVENTFLOW_ACTIVE_ENCRYPTION_KEY_ID") or get_settings().active_encryption_key_id
    )
    if not key_id or key_id not in encryption_keys():
        raise SecretUnavailable("Active encryption key is unavailable")
    return key_id


def associated_data(organization_id: uuid.UUID, endpoint_id: uuid.UUID, version: int) -> bytes:
    if version < 1:
        raise SecretUnavailable("Signing secret version is invalid")
    return (
        b"eventflow-signing-secret-v1:"
        + organization_id.bytes
        + endpoint_id.bytes
        + version.to_bytes(8, "big")
    )


def encrypt_secret(
    secret: bytes,
    organization_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    version: int,
) -> tuple[str, bytes]:
    if not secret:
        raise ValueError("Signing secret cannot be empty")
    key_id = active_key_id()
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = AESGCM(encryption_keys()[key_id]).encrypt(
        nonce, secret, associated_data(organization_id, endpoint_id, version)
    )
    return key_id, PREFIX + nonce + ciphertext


def decrypt_secret(
    key_id: str,
    ciphertext: bytes,
    organization_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    version: int,
) -> bytes:
    key = encryption_keys().get(key_id)
    if key is None:
        raise SecretUnavailable("Encryption key is unavailable")
    if not ciphertext.startswith(PREFIX) or len(ciphertext) <= len(PREFIX) + NONCE_BYTES + 16:
        raise SecretUnavailable("Signing secret ciphertext is invalid")
    nonce = ciphertext[len(PREFIX) : len(PREFIX) + NONCE_BYTES]
    body = ciphertext[len(PREFIX) + NONCE_BYTES :]
    try:
        return AESGCM(key).decrypt(
            nonce, body, associated_data(organization_id, endpoint_id, version)
        )
    except InvalidTag as exc:
        raise SecretUnavailable("Signing secret authentication failed") from exc


def generate_signing_secret() -> bytes:
    return secrets.token_bytes(32)
