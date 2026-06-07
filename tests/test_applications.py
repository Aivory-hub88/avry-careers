"""Tests for the application submission endpoint of avry-careers service."""

import io
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked database pool creation."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                with TestClient(app) as c:
                    yield c


@pytest.fixture
def vacancy_id():
    return uuid4()


@pytest.fixture
def open_vacancy_row(vacancy_id):
    """Mock DB row for an open vacancy."""
    return {"id": vacancy_id, "status": "open"}


@pytest.fixture
def closed_vacancy_row(vacancy_id):
    """Mock DB row for a closed vacancy."""
    return {"id": vacancy_id, "status": "closed"}


@pytest.fixture
def inserted_application_row():
    """Mock DB row returned after insert."""
    return {
        "id": uuid4(),
        "submitted_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def valid_cv_file():
    """A minimal valid PDF file for upload."""
    return ("test_cv.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")


class TestSubmitApplication:
    """Tests for POST /api/vacancies/{vacancy_id}/apply"""

    def test_successful_submission(self, client, vacancy_id, open_vacancy_row, inserted_application_row, valid_cv_file):
        """Should return 201 with confirmation on valid submission."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            side_effect=[open_vacancy_row, inserted_application_row],
        ):
            with patch("app.routes.applications.encrypt_pii", return_value=b"encrypted"):
                with patch("app.routes.applications.encrypt_file", return_value=b"encrypted_cv"):
                    with patch("builtins.open", MagicMock()):
                        with patch("os.makedirs"):
                            response = client.post(
                                f"/api/vacancies/{vacancy_id}/apply",
                                data={
                                    "full_name": "John Doe",
                                    "email": "john@example.com",
                                    "phone": "+1234567890",
                                    "cover_letter": "I want this job",
                                    "github_url": "https://github.com/johndoe",
                                    "linkedin_url": "https://linkedin.com/in/johndoe",
                                },
                                files={"cv": valid_cv_file},
                            )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Application submitted successfully"
        assert "application_id" in data
        assert "submitted_at" in data

    def test_returns_404_when_vacancy_not_found(self, client, vacancy_id):
        """Should return 404 when vacancy does not exist."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John", "email": "john@test.com"},
                files={"cv": ("cv.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_404_when_vacancy_not_open(self, client, vacancy_id, closed_vacancy_row):
        """Should return 404 when vacancy is closed."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=closed_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John", "email": "john@test.com"},
                files={"cv": ("cv.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )

        assert response.status_code == 404
        assert "not accepting" in response.json()["detail"].lower()

    def test_returns_422_when_full_name_missing(self, client, vacancy_id, open_vacancy_row):
        """Should return 422 when full_name is not provided."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"email": "john@test.com"},
                files={"cv": ("cv.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )

        assert response.status_code == 422
        assert "full name" in response.json()["detail"].lower()

    def test_returns_422_when_email_missing(self, client, vacancy_id, open_vacancy_row):
        """Should return 422 when email is not provided."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John Doe"},
                files={"cv": ("cv.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )

        assert response.status_code == 422
        assert "email" in response.json()["detail"].lower()

    def test_returns_422_when_cv_missing(self, client, vacancy_id, open_vacancy_row):
        """Should return 422 when CV file is not provided."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John Doe", "email": "john@test.com"},
            )

        assert response.status_code == 422
        assert "cv" in response.json()["detail"].lower()

    def test_returns_422_for_invalid_file_format(self, client, vacancy_id, open_vacancy_row):
        """Should return 422 when CV is not PDF/DOC/DOCX."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John Doe", "email": "john@test.com"},
                files={"cv": ("cv.txt", io.BytesIO(b"text content"), "text/plain")},
            )

        assert response.status_code == 422
        assert "accepted formats" in response.json()["detail"].lower()

    def test_returns_413_for_oversized_file(self, client, vacancy_id, open_vacancy_row):
        """Should return 413 when CV exceeds 10 MB."""
        # Create a file that reports a size > 10 MB via the size attribute
        oversized_content = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={"full_name": "John Doe", "email": "john@test.com"},
                files={"cv": ("cv.pdf", io.BytesIO(oversized_content), "application/pdf")},
            )

        assert response.status_code == 413
        assert "10 mb" in response.json()["detail"].lower()

    def test_no_auth_required(self, client, vacancy_id, open_vacancy_row, inserted_application_row, valid_cv_file):
        """Public endpoint should not require authentication."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            side_effect=[open_vacancy_row, inserted_application_row],
        ):
            with patch("app.routes.applications.encrypt_pii", return_value=b"encrypted"):
                with patch("app.routes.applications.encrypt_file", return_value=b"encrypted_cv"):
                    with patch("builtins.open", MagicMock()):
                        with patch("os.makedirs"):
                            response = client.post(
                                f"/api/vacancies/{vacancy_id}/apply",
                                data={
                                    "full_name": "Jane Doe",
                                    "email": "jane@example.com",
                                },
                                files={"cv": valid_cv_file},
                            )

        # No 401 or 403
        assert response.status_code == 201

    def test_screening_responses_parsed_as_json(self, client, vacancy_id, open_vacancy_row, inserted_application_row, valid_cv_file):
        """Should parse screening_responses as a JSON string."""
        responses_json = json.dumps([{"question": "Why?", "answer": "Because"}])
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            side_effect=[open_vacancy_row, inserted_application_row],
        ) as mock_fetch:
            with patch("app.routes.applications.encrypt_pii", return_value=b"encrypted"):
                with patch("app.routes.applications.encrypt_file", return_value=b"encrypted_cv"):
                    with patch("builtins.open", MagicMock()):
                        with patch("os.makedirs"):
                            response = client.post(
                                f"/api/vacancies/{vacancy_id}/apply",
                                data={
                                    "full_name": "John Doe",
                                    "email": "john@test.com",
                                    "screening_responses": responses_json,
                                },
                                files={"cv": valid_cv_file},
                            )

        assert response.status_code == 201

    def test_returns_422_for_invalid_screening_responses_json(self, client, vacancy_id, open_vacancy_row, valid_cv_file):
        """Should return 422 when screening_responses is not valid JSON."""
        with patch(
            "app.routes.applications.fetch_one",
            new_callable=AsyncMock,
            return_value=open_vacancy_row,
        ):
            response = client.post(
                f"/api/vacancies/{vacancy_id}/apply",
                data={
                    "full_name": "John Doe",
                    "email": "john@test.com",
                    "screening_responses": "not valid json {[",
                },
                files={"cv": valid_cv_file},
            )

        assert response.status_code == 422
        assert "screening responses" in response.json()["detail"].lower()
