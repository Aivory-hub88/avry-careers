"""
Encryption service for PII fields and CV files.

Uses AES-256-GCM with per-operation random 12-byte nonces.
The encryption key is derived from the ENCRYPTION_KEY environment variable.

Storage format (both PII and files):
    [12-byte nonce/IV] + [ciphertext] + [16-byte GCM auth tag]
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

# Nonce size for AES-GCM (96 bits / 12 bytes as recommended by NIST)
_NONCE_SIZE = 12

# AES-256 key size in bytes
_KEY_SIZE = 32


def _get_key() -> bytes:
    """
    Derive a 32-byte AES-256 key from the configured encryption key.

    If the key is already 32 bytes (hex-encoded 64 chars), decode it directly.
    Otherwise, hash it with SHA-256 to produce a consistent 32-byte key.
    """
    raw_key = settings.encryption_key

    if not raw_key:
        raise ValueError(
            "ENCRYPTION_KEY is not configured. "
            "Set the ENCRYPTION_KEY environment variable to enable encryption."
        )

    # If the key looks like a 64-char hex string (32 bytes), use it directly
    if len(raw_key) == 64:
        try:
            return bytes.fromhex(raw_key)
        except ValueError:
            pass

    # Otherwise, hash it to get a consistent 32-byte key
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def encrypt_pii(plaintext: str) -> bytes:
    """
    Encrypt a PII string field using AES-256-GCM.

    Args:
        plaintext: The PII string to encrypt (e.g., email, phone number).

    Returns:
        Encrypted bytes in format: [nonce (12 bytes)] + [ciphertext + tag].
        Suitable for storage as BYTEA in PostgreSQL.
    """
    key = _get_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)

    # Encrypt the plaintext encoded as UTF-8
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # Prepend nonce for storage
    return nonce + ciphertext_with_tag


def decrypt_pii(encrypted_data: bytes) -> str:
    """
    Decrypt PII bytes back to the original string.

    Args:
        encrypted_data: Bytes in format [nonce (12 bytes)] + [ciphertext + tag].

    Returns:
        The original plaintext string.

    Raises:
        ValueError: If the encrypted data is too short or tampered with.
    """
    if len(encrypted_data) <= _NONCE_SIZE:
        raise ValueError("Encrypted data is too short to contain a valid nonce and ciphertext.")

    key = _get_key()

    # Extract nonce and ciphertext+tag
    nonce = encrypted_data[:_NONCE_SIZE]
    ciphertext_with_tag = encrypted_data[_NONCE_SIZE:]

    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

    return plaintext_bytes.decode("utf-8")


def encrypt_file(file_bytes: bytes) -> bytes:
    """
    Encrypt file content (e.g., CV) using AES-256-GCM.

    Args:
        file_bytes: The raw file bytes to encrypt.

    Returns:
        Encrypted bytes in format: [IV (12 bytes)] + [ciphertext + tag].
        Suitable for writing to disk as an encrypted file.
    """
    key = _get_key()
    iv = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)

    ciphertext_with_tag = aesgcm.encrypt(iv, file_bytes, None)

    # Prepend IV for storage
    return iv + ciphertext_with_tag


def decrypt_file(encrypted_bytes: bytes) -> bytes:
    """
    Decrypt file content back to the original bytes.

    Args:
        encrypted_bytes: Bytes in format [IV (12 bytes)] + [ciphertext + tag].

    Returns:
        The original file bytes.

    Raises:
        ValueError: If the encrypted data is too short or tampered with.
    """
    if len(encrypted_bytes) <= _NONCE_SIZE:
        raise ValueError("Encrypted data is too short to contain a valid IV and ciphertext.")

    key = _get_key()

    # Extract IV and ciphertext+tag
    iv = encrypted_bytes[:_NONCE_SIZE]
    ciphertext_with_tag = encrypted_bytes[_NONCE_SIZE:]

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext_with_tag, None)
