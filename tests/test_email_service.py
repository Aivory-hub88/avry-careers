"""
Tests for the email service and the POST /api/admin/applications/{app_id}/email endpoint.
"""

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Set test environment before importing app modules
os.environ.setdefault("ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-unit-tests")

from app.config import settings
from app.services.email_service import send_email
from app.services.encryption_service import encrypt_pii

TEST_JWT_SECRET = settings.supabase_jwt_secret or settings.jwt_secret or "test-jwt-secret-for-unit-tests"


@pytest.fixture
def client():
    """Create a test client with mocked database pool creation."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                with TestClient(app) as c:
                    yield c


def _admin_headers():
    """Generate a valid admin JWT Authorization header."""
    payload = {"sub": "admin-user", "account_type": "admin"}
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _non_admin_headers():
    """Generate a valid JWT with non-admin account_type."""
    payload = {"sub": "user-1", "account_type": "member"}
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ─── Unit tests for send_email function ──────────────────────────────────────


@pytest.mark.asyncio
async def test_send_email_calls_aiosmtplib():
    """send_email should invoke aiosmtplib.send with proper message."""
    with patch("app.services.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_email("test@example.com", "Hello", "World")
        mock_send.assert_called_once()

        # Verify the message was constructed correctly
        call_args = mock_send.call_args
        message = call_args[0][0] if call_args[0] else call_args[1].get("message")
        assert message["To"] == "test@example.com"
        assert message["Subject"] == "Hello"


@pytest.mark.asyncio
async def test_send_email_raises_runtime_error_on_failure():
    """send_email should raise RuntimeError when SMTP fails."""
    import aiosmtplib

    with patch(
        "app.services.email_service.aiosmtplib.send",
        new_callable=AsyncMock,
        side_effect=aiosmtplib.SMTPException("Connection refused"),
    ):
        with pytest.raises(RuntimeError, match="Failed to send email"):
            await send_email("test@example.com", "Hello", "World")


# ─── Endpoint tests for POST /api/admin/applications/{app_id}/email ──────────


class TestSendEmailEndpoint:
    """Tests for POST /api/admin/applications/{app_id}/email"""

    def test_requires_admin_auth(self, client):
        """Should return 401 without auth token."""
        app_id = uuid.uuid4()
        response = client.post(
            f"/api/admin/applications/{app_id}/email",
            json={"subject": "Test", "body": "Hello"},
        )
        assert response.status_code == 401

    def test_requires_admin_role(self, client):
        """Should return 403 for non-admin user."""
        app_id = uuid.uuid4()
        response = client.post(
            f"/api/admin/applications/{app_id}/email",
            json={"subject": "Test", "body": "Hello"},
            headers=_non_admin_headers(),
        )
        assert response.status_code == 403

    def test_returns_422_for_empty_subject(self, client):
        """Should return 422 when subject is empty."""
        app_id = uuid.uuid4()
        response = client.post(
            f"/api/admin/applications/{app_id}/email",
            json={"subject": "", "body": "Hello"},
            headers=_admin_headers(),
        )
        assert response.status_code == 422
        assert "Subject cannot be empty" in response.json()["detail"]

    def test_returns_422_for_empty_body(self, client):
        """Should return 422 when body is empty."""
        app_id = uuid.uuid4()
        response = client.post(
            f"/api/admin/applications/{app_id}/email",
            json={"subject": "Test", "body": "   "},
            headers=_admin_headers(),
        )
        assert response.status_code == 422
        assert "Body cannot be empty" in response.json()["detail"]

    def test_returns_404_for_missing_application(self, client):
        """Should return 404 when application does not exist."""
        app_id = uuid.uuid4()
        with patch("app.routes.admin.fetch_one", new_callable=AsyncMock, return_value=None):
            response = client.post(
                f"/api/admin/applications/{app_id}/email",
                json={"subject": "Test", "body": "Hello"},
                headers=_admin_headers(),
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"

    def test_sends_email_successfully(self, client):
        """Should decrypt email, send it, and return 200 with confirmation."""
        app_id = uuid.uuid4()
        encrypted_email = encrypt_pii("applicant@example.com")
        fake_row = {"email_encrypted": encrypted_email}

        with patch("app.routes.admin.fetch_one", new_callable=AsyncMock, return_value=fake_row):
            with patch("app.routes.admin.send_email", new_callable=AsyncMock) as mock_send:
                response = client.post(
                    f"/api/admin/applications/{app_id}/email",
                    json={"subject": "Interview", "body": "We'd like to chat."},
                    headers=_admin_headers(),
                )

        assert response.status_code == 200
        data = response.json()
        assert data["detail"] == "Email sent successfully"
        assert data["to"] == "applicant@example.com"
        mock_send.assert_called_once_with(
            to_email="applicant@example.com",
            subject="Interview",
            body="We'd like to chat.",
        )

    def test_returns_502_on_smtp_failure(self, client):
        """Should return 502 when the email service fails to send."""
        app_id = uuid.uuid4()
        encrypted_email = encrypt_pii("applicant@example.com")
        fake_row = {"email_encrypted": encrypted_email}

        with patch("app.routes.admin.fetch_one", new_callable=AsyncMock, return_value=fake_row):
            with patch(
                "app.routes.admin.send_email",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Failed to send email: Connection refused"),
            ):
                response = client.post(
                    f"/api/admin/applications/{app_id}/email",
                    json={"subject": "Test", "body": "Hello"},
                    headers=_admin_headers(),
                )

        assert response.status_code == 502
        assert "Failed to send email" in response.json()["detail"]

    def test_returns_500_on_decryption_failure(self, client):
        """Should return 500 if email decryption fails."""
        app_id = uuid.uuid4()
        # Provide corrupted encrypted data
        fake_row = {"email_encrypted": b"corrupted-data-too-short"}

        with patch("app.routes.admin.fetch_one", new_callable=AsyncMock, return_value=fake_row):
            response = client.post(
                f"/api/admin/applications/{app_id}/email",
                json={"subject": "Test", "body": "Hello"},
                headers=_admin_headers(),
            )

        assert response.status_code == 500
        assert "decrypt" in response.json()["detail"].lower()
