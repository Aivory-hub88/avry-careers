"""
Property-based tests for authentication and access control (careers service).

Feature: blog-and-careers, Property 14: Public endpoints accessible without authentication

Validates: Requirements 12.3

Uses Hypothesis to verify that public career endpoints are accessible
without any Authorization header — i.e., they never return 401 or 403.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.models.vacancy import ScreeningQuestion, Vacancy, VacancyStatus


# --- Strategies ---

_uuid_strategy = st.builds(uuid.uuid4)

_vacancy_title_strategy = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

_department_strategy = st.text(min_size=0, max_size=100)

_location_strategy = st.text(min_size=0, max_size=100)

_employment_type_strategy = st.sampled_from(
    ["full-time", "part-time", "contract", "internship"]
)

_description_strategy = st.fixed_dictionaries(
    {
        "blocks": st.lists(
            st.fixed_dictionaries(
                {"type": st.just("paragraph"), "text": st.text(min_size=1, max_size=200)}
            ),
            min_size=1,
            max_size=3,
        )
    }
)

_screening_question_strategy = st.fixed_dictionaries(
    {
        "question": st.text(min_size=1, max_size=100),
        "required": st.booleans(),
        "type": st.sampled_from(["text", "select", "boolean"]),
    }
)

_screening_questions_strategy = st.lists(
    _screening_question_strategy, min_size=0, max_size=5
)


# --- Helpers ---


def _make_open_vacancy(
    vacancy_id: uuid.UUID,
    title: str = "Test Role",
    department: str = "Engineering",
    location: str = "Remote",
    employment_type: str = "full-time",
    description: dict | None = None,
    screening_questions: list[dict] | None = None,
) -> Vacancy:
    """Create an open Vacancy for mocking service layer responses."""
    now = datetime.now(timezone.utc)
    return Vacancy(
        id=vacancy_id,
        title=title,
        department=department,
        location=location,
        employment_type=employment_type,
        description=description or {"blocks": [{"type": "paragraph", "text": "Desc"}]},
        requirements=None,
        screening_questions=[
            ScreeningQuestion(**q) for q in (screening_questions or [])
        ],
        status=VacancyStatus.open,
        posted_at=now,
        created_at=now,
        updated_at=now,
    )


# --- Composite strategy for generating a public endpoint request ---


@st.composite
def _public_endpoint_strategy(draw):
    """
    Generate a random public endpoint request configuration for the careers service.

    Public endpoints:
      - GET /api/vacancies
      - GET /api/vacancies/{vacancy_id}
      - GET /api/vacancies/{vacancy_id}/form
    """
    vacancy_id = draw(_uuid_strategy)
    title = draw(_vacancy_title_strategy)
    department = draw(_department_strategy)
    location = draw(_location_strategy)
    employment_type = draw(_employment_type_strategy)
    description = draw(_description_strategy)
    screening_questions = draw(_screening_questions_strategy)

    vacancy = _make_open_vacancy(
        vacancy_id=vacancy_id,
        title=title,
        department=department,
        location=location,
        employment_type=employment_type,
        description=description,
        screening_questions=screening_questions,
    )

    endpoints = [
        {
            "method": "GET",
            "path": "/api/vacancies",
            "patches": {
                "app.routes.vacancies.list_open_vacancies": [vacancy],
            },
            "description": "vacancy listing",
        },
        {
            "method": "GET",
            "path": f"/api/vacancies/{vacancy_id}",
            "patches": {
                "app.routes.vacancies.get_vacancy_by_id": vacancy,
            },
            "description": "vacancy detail",
        },
        {
            "method": "GET",
            "path": f"/api/vacancies/{vacancy_id}/form",
            "patches": {
                "app.routes.vacancies.get_vacancy_by_id": vacancy,
            },
            "description": "application form schema",
        },
    ]

    endpoint = draw(st.sampled_from(endpoints))
    return endpoint


# --- Fixtures ---


@pytest.fixture(scope="class")
def client():
    """Create a test client with mocked database pool (class-scoped for performance)."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                from fastapi.testclient import TestClient

                with TestClient(app) as c:
                    yield c


# --- Property 14: Public endpoints accessible without authentication (careers) ---


class TestPublicEndpointsAccessibleWithoutAuth:
    """
    Feature: blog-and-careers, Property 14: Public endpoints accessible without authentication

    For any public endpoint (vacancy listing, vacancy detail, application form schema),
    requests without an Authorization header SHALL receive a successful response
    (not 401 or 403).

    **Validates: Requirements 12.3**
    """

    @given(endpoint=_public_endpoint_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    def test_public_endpoints_do_not_require_authentication(self, client, endpoint):
        """
        Property 14: For any public endpoint (vacancy listing, vacancy detail,
        application form schema), requests without an Authorization header SHALL
        receive a successful response (not 401 or 403).

        **Validates: Requirements 12.3**
        """
        method = endpoint["method"]
        path = endpoint["path"]
        patches = endpoint["patches"]
        desc = endpoint["description"]

        # Apply all mocks for this endpoint's service layer
        patch_contexts = []
        for target, return_value in patches.items():
            p = patch(target, new_callable=AsyncMock, return_value=return_value)
            patch_contexts.append(p)

        # Enter all patch contexts
        for p in patch_contexts:
            p.start()

        try:
            # Make request WITHOUT any Authorization header
            if method == "GET":
                response = client.get(path)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # PROPERTY ASSERTION: Response should NOT be 401 or 403
            assert response.status_code not in (401, 403), (
                f"Public endpoint {method} {path} ({desc}) returned "
                f"{response.status_code} without Authorization header. "
                f"Public endpoints must not require authentication. "
                f"Response body: {response.text}"
            )
        finally:
            # Stop all patches
            for p in patch_contexts:
                p.stop()
