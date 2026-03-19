"""Fernet symmetric encryption for ApiKeyStore values.

Keys are encrypted before writing to the database and decrypted on read.
ENCRYPTION_KEY must be a URL-safe base64-encoded 32-byte key generated with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import ConfigurationError


def _get_fernet() -> Fernet:
    from app.core.config import settings

    if not settings.ENCRYPTION_KEY:
        raise ConfigurationError(
            "ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and set it in your .env file."
        )
    try:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception as exc:
        raise ConfigurationError(
            f"ENCRYPTION_KEY is invalid: {exc}. "
            "It must be a URL-safe base64-encoded 32-byte key."
        ) from exc


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns a Fernet token as a string."""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a Fernet token string. Returns plaintext.

    Raises ConfigurationError if the key is invalid.
    Raises ValueError if the token is malformed or was encrypted with a different key.
    """
    f = _get_fernet()
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt value — the token is invalid or was encrypted with a different key."
        ) from exc
