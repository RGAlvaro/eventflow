import uuid

from eventflow.secrets import encrypt_secret


def sealed_secret(
    secret: bytes, organization_id: uuid.UUID, endpoint_id: uuid.UUID
) -> dict[str, object]:
    key_id, ciphertext = encrypt_secret(secret, organization_id, endpoint_id, 1)
    return {
        "signing_secret_ciphertext": ciphertext,
        "signing_secret_key_id": key_id,
        "signing_secret_version": 1,
    }
