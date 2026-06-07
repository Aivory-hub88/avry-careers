"""
Property-based tests for the encryption service.

Feature: blog-and-careers, Property 13: Sensitive data encryption round-trip

Validates: Requirements 11.3, 11.4

For any PII field value (full_name, email, phone) and any CV file content,
encrypting then decrypting SHALL produce the original value. Additionally,
the stored encrypted form SHALL NOT equal the plaintext.
"""

from unittest.mock import patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# Fixed test encryption key (64 hex chars = 32 bytes AES-256 key)
TEST_ENCRYPTION_KEY = "a" * 64


@pytest.fixture(autouse=True)
def mock_encryption_key():
    """Mock the settings.encryption_key for all tests in this module."""
    with patch("app.services.encryption_service.settings") as mock_settings:
        mock_settings.encryption_key = TEST_ENCRYPTION_KEY
        yield mock_settings


class TestEncryptionRoundTripProperty:
    """
    Property 13: Sensitive data encryption round-trip

    **Validates: Requirements 11.3, 11.4**
    """

    @given(plaintext=st.text())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pii_encrypt_decrypt_roundtrip(self, mock_encryption_key, plaintext: str):
        """
        For any arbitrary PII string, encrypt_pii followed by decrypt_pii
        SHALL produce the original value.

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import decrypt_pii, encrypt_pii

        encrypted = encrypt_pii(plaintext)
        decrypted = decrypt_pii(encrypted)

        assert decrypted == plaintext

    @given(file_bytes=st.binary())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_file_encrypt_decrypt_roundtrip(self, mock_encryption_key, file_bytes: bytes):
        """
        For any arbitrary file content (bytes), encrypt_file followed by
        decrypt_file SHALL produce the original value.

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import decrypt_file, encrypt_file

        encrypted = encrypt_file(file_bytes)
        decrypted = decrypt_file(encrypted)

        assert decrypted == file_bytes

    @given(plaintext=st.text(min_size=1))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pii_encrypted_form_differs_from_plaintext(self, mock_encryption_key, plaintext: str):
        """
        For any non-empty PII string, the encrypted form SHALL NOT equal
        the plaintext (as bytes).

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import encrypt_pii

        encrypted = encrypt_pii(plaintext)

        assert encrypted != plaintext.encode("utf-8")

    @given(file_bytes=st.binary(min_size=1))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_file_encrypted_form_differs_from_original(self, mock_encryption_key, file_bytes: bytes):
        """
        For any non-empty file content, the encrypted form SHALL NOT equal
        the original bytes.

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import encrypt_file

        encrypted = encrypt_file(file_bytes)

        assert encrypted != file_bytes

    @given(plaintext=st.text())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pii_encryption_produces_different_ciphertext_each_time(
        self, mock_encryption_key, plaintext: str
    ):
        """
        Each encryption of the same PII input SHALL produce different ciphertext
        (due to random nonces).

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import encrypt_pii

        encrypted_1 = encrypt_pii(plaintext)
        encrypted_2 = encrypt_pii(plaintext)

        assert encrypted_1 != encrypted_2

    @given(file_bytes=st.binary())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_file_encryption_produces_different_ciphertext_each_time(
        self, mock_encryption_key, file_bytes: bytes
    ):
        """
        Each encryption of the same file content SHALL produce different ciphertext
        (due to random IVs).

        **Validates: Requirements 11.3, 11.4**
        """
        from app.services.encryption_service import encrypt_file

        encrypted_1 = encrypt_file(file_bytes)
        encrypted_2 = encrypt_file(file_bytes)

        assert encrypted_1 != encrypted_2
