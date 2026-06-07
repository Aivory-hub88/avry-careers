"""Unit tests for the encryption service."""

import os
import pytest
from unittest.mock import patch


# Set encryption key before importing the module
os.environ["ENCRYPTION_KEY"] = "a" * 64  # 64 hex chars = 32 bytes


@pytest.fixture(autouse=True)
def set_encryption_key():
    """Ensure encryption key is set for all tests."""
    with patch("app.services.encryption_service.settings") as mock_settings:
        mock_settings.encryption_key = "a" * 64
        yield mock_settings


class TestEncryptPII:
    """Tests for PII encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self, set_encryption_key):
        """Encrypting then decrypting a PII string returns the original."""
        from app.services.encryption_service import encrypt_pii, decrypt_pii

        original = "test@example.com"
        encrypted = encrypt_pii(original)
        decrypted = decrypt_pii(encrypted)

        assert decrypted == original

    def test_encrypted_differs_from_plaintext(self, set_encryption_key):
        """Encrypted bytes must not equal the plaintext bytes."""
        from app.services.encryption_service import encrypt_pii

        original = "sensitive@email.com"
        encrypted = encrypt_pii(original)

        assert encrypted != original.encode("utf-8")

    def test_different_nonces_produce_different_ciphertext(self, set_encryption_key):
        """Each encryption uses a random nonce, so outputs differ."""
        from app.services.encryption_service import encrypt_pii

        original = "+31612345678"
        encrypted_1 = encrypt_pii(original)
        encrypted_2 = encrypt_pii(original)

        assert encrypted_1 != encrypted_2

    def test_encrypted_contains_nonce_prefix(self, set_encryption_key):
        """Encrypted data starts with a 12-byte nonce."""
        from app.services.encryption_service import encrypt_pii

        encrypted = encrypt_pii("test data")
        # Must be at least nonce (12) + some ciphertext + tag (16)
        assert len(encrypted) > 12 + 16

    def test_empty_string_roundtrip(self, set_encryption_key):
        """Empty string encrypts and decrypts correctly."""
        from app.services.encryption_service import encrypt_pii, decrypt_pii

        encrypted = encrypt_pii("")
        assert decrypt_pii(encrypted) == ""

    def test_unicode_roundtrip(self, set_encryption_key):
        """Unicode characters encrypt and decrypt correctly."""
        from app.services.encryption_service import encrypt_pii, decrypt_pii

        original = "José García — +34 912 345 678"
        encrypted = encrypt_pii(original)
        assert decrypt_pii(encrypted) == original

    def test_decrypt_invalid_data_raises(self, set_encryption_key):
        """Decrypting tampered/invalid data raises an error."""
        from app.services.encryption_service import decrypt_pii

        with pytest.raises((ValueError, Exception)):
            decrypt_pii(b"\x00" * 13)  # valid nonce length but garbage ciphertext


class TestEncryptFile:
    """Tests for file encryption/decryption."""

    def test_encrypt_decrypt_file_roundtrip(self, set_encryption_key):
        """Encrypting then decrypting file bytes returns the original."""
        from app.services.encryption_service import encrypt_file, decrypt_file

        original = b"%PDF-1.4 fake pdf content here with binary \x00\x01\x02"
        encrypted = encrypt_file(original)
        decrypted = decrypt_file(encrypted)

        assert decrypted == original

    def test_encrypted_file_differs_from_original(self, set_encryption_key):
        """Encrypted file bytes must not equal the original bytes."""
        from app.services.encryption_service import encrypt_file

        original = b"CV content in PDF format"
        encrypted = encrypt_file(original)

        assert encrypted != original

    def test_different_ivs_produce_different_ciphertext(self, set_encryption_key):
        """Each file encryption uses a random IV, so outputs differ."""
        from app.services.encryption_service import encrypt_file

        original = b"Same file content"
        encrypted_1 = encrypt_file(original)
        encrypted_2 = encrypt_file(original)

        assert encrypted_1 != encrypted_2

    def test_large_file_roundtrip(self, set_encryption_key):
        """Large file (simulating a multi-MB CV) encrypts and decrypts correctly."""
        from app.services.encryption_service import encrypt_file, decrypt_file

        # ~1MB of random bytes
        original = os.urandom(1024 * 1024)
        encrypted = encrypt_file(original)
        decrypted = decrypt_file(encrypted)

        assert decrypted == original

    def test_empty_file_roundtrip(self, set_encryption_key):
        """Empty file content encrypts and decrypts correctly."""
        from app.services.encryption_service import encrypt_file, decrypt_file

        encrypted = encrypt_file(b"")
        assert decrypt_file(encrypted) == b""

    def test_decrypt_invalid_file_raises(self, set_encryption_key):
        """Decrypting tampered/invalid file data raises an error."""
        from app.services.encryption_service import decrypt_file

        with pytest.raises((ValueError, Exception)):
            decrypt_file(b"\x00" * 13)  # valid IV length but garbage ciphertext


class TestKeyDerivation:
    """Tests for encryption key handling."""

    def test_hex_key_used_directly(self):
        """A 64-char hex string is used directly as the key (32 bytes)."""
        from app.services.encryption_service import _get_key

        with patch("app.services.encryption_service.settings") as mock_settings:
            mock_settings.encryption_key = "ab" * 32  # 64 hex chars
            key = _get_key()
            assert key == bytes.fromhex("ab" * 32)
            assert len(key) == 32

    def test_non_hex_key_hashed_to_32_bytes(self):
        """A non-hex key is hashed with SHA-256 to produce 32 bytes."""
        import hashlib
        from app.services.encryption_service import _get_key

        with patch("app.services.encryption_service.settings") as mock_settings:
            mock_settings.encryption_key = "my-secret-passphrase"
            key = _get_key()
            expected = hashlib.sha256("my-secret-passphrase".encode("utf-8")).digest()
            assert key == expected
            assert len(key) == 32

    def test_missing_key_raises_error(self):
        """Missing ENCRYPTION_KEY raises a ValueError."""
        from app.services.encryption_service import _get_key

        with patch("app.services.encryption_service.settings") as mock_settings:
            mock_settings.encryption_key = ""
            with pytest.raises(ValueError, match="ENCRYPTION_KEY is not configured"):
                _get_key()
