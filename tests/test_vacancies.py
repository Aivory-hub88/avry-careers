"""Tests for the public vacancy endpoints of avry-careers service."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.vacancy import Vacancy, VacancyStatus, ScreeningQuestion


@pytest.fixture
def client():
    """Create a test client with mocked database pool creation."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                with TestClient(app) as c:
                    yield c


def _make_vacancy(
    status=VacancyStatus.open,
    screening_questions=None,
    **kwargs,
) -> Vacancy:
    """Helper to create a Vacancy instance for testing."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid4(),
        "title": "Software Engineer",
        "department": "Engineering",
        "location": "Remote",
        "employment_type": "full-time",
        "description": {"blocks": [{"type": "paragraph", "text": "A great role."}]},
        "requirements": None,
        "screening_questions": screening_questions or [],
        "status": status,
        "posted_at": now,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return Vacancy(**defaults)


class TestListVacancies:
    """Tests for GET /api/vacancies"""

    def test_returns_open_vacancies(self, client):
        """Should return a list of open vacancies."""
        vacancy = _make_vacancy()
        with patch(
            "app.routes.vacancies.list_open_vacancies",
            new_callable=AsyncMock,
            return_value=[vacancy],
        ):
            response = client.get("/api/vacancies")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Software Engineer"
        assert data[0]["status"] == "open"

    def test_returns_empty_list_when_no_vacancies(self, client):
        """Should return an empty list when no open vacancies exist."""
        with patch(
            "app.routes.vacancies.list_open_vacancies",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get("/api/vacancies")

        assert response.status_code == 200
        assert response.json() == []

    def test_no_auth_required(self, client):
        """Public endpoint should not require authentication."""
        with patch(
            "app.routes.vacancies.list_open_vacancies",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = client.get("/api/vacancies")

        # No 401 or 403
        assert response.status_code == 200


class TestGetVacancy:
    """Tests for GET /api/vacancies/{vacancy_id}"""

    def test_returns_open_vacancy(self, client):
        """Should return the full vacancy detail for an open vacancy."""
        vacancy = _make_vacancy()
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Software Engineer"
        assert data["department"] == "Engineering"
        assert data["description"] == {"blocks": [{"type": "paragraph", "text": "A great role."}]}

    def test_returns_404_for_nonexistent_vacancy(self, client):
        """Should return 404 when vacancy does not exist."""
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get(f"/api/vacancies/{uuid4()}")

        assert response.status_code == 404

    def test_returns_404_for_closed_vacancy(self, client):
        """Should return 404 when vacancy is closed."""
        vacancy = _make_vacancy(status=VacancyStatus.closed)
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}")

        assert response.status_code == 404

    def test_returns_404_for_draft_vacancy(self, client):
        """Should return 404 when vacancy is in draft status."""
        vacancy = _make_vacancy(status=VacancyStatus.draft)
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}")

        assert response.status_code == 404

    def test_invalid_uuid_returns_422(self, client):
        """Should return 422 for an invalid UUID path parameter."""
        response = client.get("/api/vacancies/not-a-uuid")
        assert response.status_code == 422


class TestGetVacancyForm:
    """Tests for GET /api/vacancies/{vacancy_id}/form"""

    def test_returns_form_schema_with_standard_fields(self, client):
        """Should return standard application fields."""
        vacancy = _make_vacancy()
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        assert response.status_code == 200
        data = response.json()
        assert data["vacancy_id"] == str(vacancy.id)
        assert data["vacancy_title"] == "Software Engineer"

        field_names = [f["name"] for f in data["fields"]]
        assert "full_name" in field_names
        assert "email" in field_names
        assert "phone" in field_names
        assert "cover_letter" in field_names
        assert "github_url" in field_names
        assert "linkedin_url" in field_names
        assert "cv" in field_names

    def test_required_fields_marked_correctly(self, client):
        """full_name, email, and cv should be required; others optional."""
        vacancy = _make_vacancy()
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        data = response.json()
        fields_by_name = {f["name"]: f for f in data["fields"]}

        assert fields_by_name["full_name"]["required"] is True
        assert fields_by_name["email"]["required"] is True
        assert fields_by_name["cv"]["required"] is True
        assert fields_by_name["phone"]["required"] is False
        assert fields_by_name["cover_letter"]["required"] is False
        assert fields_by_name["github_url"]["required"] is False
        assert fields_by_name["linkedin_url"]["required"] is False

    def test_includes_custom_screening_questions(self, client):
        """Should include custom screening questions defined on the vacancy."""
        questions = [
            ScreeningQuestion(question="Why do you want this role?", required=True, type="text"),
            ScreeningQuestion(question="Are you willing to relocate?", required=False, type="boolean"),
        ]
        vacancy = _make_vacancy(screening_questions=questions)
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        data = response.json()
        assert len(data["screening_questions"]) == 2
        assert data["screening_questions"][0]["question"] == "Why do you want this role?"
        assert data["screening_questions"][0]["required"] is True
        assert data["screening_questions"][1]["question"] == "Are you willing to relocate?"
        assert data["screening_questions"][1]["type"] == "boolean"

    def test_empty_screening_questions_when_none_defined(self, client):
        """Should return empty screening_questions list when no custom questions."""
        vacancy = _make_vacancy(screening_questions=[])
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        data = response.json()
        assert data["screening_questions"] == []

    def test_returns_404_for_nonexistent_vacancy(self, client):
        """Should return 404 when vacancy does not exist."""
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = client.get(f"/api/vacancies/{uuid4()}/form")

        assert response.status_code == 404

    def test_returns_404_for_non_open_vacancy(self, client):
        """Should return 404 when vacancy is not open."""
        vacancy = _make_vacancy(status=VacancyStatus.closed)
        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        assert response.status_code == 404
