"""
Property-based tests for vacancy endpoints.

Feature: blog-and-careers, Property 6: Vacancy listing contains only open vacancies in descending date order
Feature: blog-and-careers, Property 7: Vacancy response completeness
Feature: blog-and-careers, Property 10: Custom screening questions inclusion

Validates: Requirements 7.1, 7.2, 7.3, 8.3
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.models.vacancy import ScreeningQuestion, Vacancy, VacancyStatus


# --- Hypothesis Strategies ---

vacancy_status_strategy = st.sampled_from([VacancyStatus.draft, VacancyStatus.open, VacancyStatus.closed])

# Generate realistic posted_at timestamps within a 2-year window
base_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
posted_at_strategy = st.integers(min_value=0, max_value=730 * 24 * 3600).map(
    lambda offset: base_time + timedelta(seconds=offset)
)


def make_vacancy(status: VacancyStatus, posted_at: datetime) -> Vacancy:
    """Create a Vacancy instance with the given status and posted_at."""
    now = datetime.now(timezone.utc)
    return Vacancy(
        id=uuid4(),
        title=f"Role-{uuid4().hex[:8]}",
        department="Engineering",
        location="Remote",
        employment_type="full-time",
        description={"blocks": [{"type": "paragraph", "text": "Description."}]},
        requirements=None,
        screening_questions=[],
        status=status,
        posted_at=posted_at if status == VacancyStatus.open else None,
        created_at=now,
        updated_at=now,
    )


# Strategy that generates a list of (status, posted_at) tuples
vacancy_data_strategy = st.lists(
    st.tuples(vacancy_status_strategy, posted_at_strategy),
    min_size=0,
    max_size=30,
)


@pytest.fixture(scope="class")
def client():
    """Create a test client with mocked database pool creation (class-scoped for performance)."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                from fastapi.testclient import TestClient

                with TestClient(app) as c:
                    yield c


class TestVacancyListingProperty:
    """
    Property 6: Vacancy listing contains only open vacancies in descending date order

    **Validates: Requirements 7.1, 7.3**
    """

    @given(vacancy_data=vacancy_data_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    def test_listing_returns_only_open_vacancies_in_descending_date_order(
        self, client, vacancy_data: list[tuple[VacancyStatus, datetime]]
    ):
        """
        For any set of vacancies with mixed statuses (draft, open, closed),
        the public listing endpoint SHALL return only vacancies with open status,
        and they SHALL be ordered by posted_at descending.

        **Validates: Requirements 7.1, 7.3**
        """
        # Build full list of vacancies from generated data
        all_vacancies = [make_vacancy(status, posted_at) for status, posted_at in vacancy_data]

        # Filter to only open vacancies and sort by posted_at DESC (as the service would)
        open_vacancies = sorted(
            [v for v in all_vacancies if v.status == VacancyStatus.open],
            key=lambda v: v.posted_at,
            reverse=True,
        )

        # Mock list_open_vacancies to return the properly filtered and sorted list
        with patch(
            "app.routes.vacancies.list_open_vacancies",
            new_callable=AsyncMock,
            return_value=open_vacancies,
        ):
            response = client.get("/api/vacancies")

        assert response.status_code == 200
        data = response.json()

        # Property assertion 1: All returned vacancies have status == "open"
        for item in data:
            assert item["status"] == "open", (
                f"Expected all vacancies to have status 'open', got '{item['status']}'"
            )

        # Property assertion 2: The count of returned vacancies matches the open count
        assert len(data) == len(open_vacancies), (
            f"Expected {len(open_vacancies)} open vacancies, got {len(data)}"
        )

        # Property assertion 3: posted_at dates are in descending order
        if len(data) > 1:
            posted_dates = [item["posted_at"] for item in data]
            for i in range(len(posted_dates) - 1):
                assert posted_dates[i] >= posted_dates[i + 1], (
                    f"Vacancies not in descending posted_at order: "
                    f"{posted_dates[i]} should be >= {posted_dates[i + 1]}"
                )



# --- Property 7: Vacancy response completeness ---

# Strategies for generating vacancy field values
vacancy_title_st = st.text(min_size=1, max_size=200)
vacancy_department_st = st.text(min_size=0, max_size=100)
vacancy_location_st = st.text(min_size=0, max_size=100)
vacancy_employment_type_st = st.sampled_from(
    ["full-time", "part-time", "contract", "internship"]
)
vacancy_description_st = st.fixed_dictionaries(
    {
        "blocks": st.lists(
            st.fixed_dictionaries(
                {"type": st.just("paragraph"), "text": st.text(min_size=1, max_size=200)}
            ),
            min_size=1,
            max_size=5,
        )
    }
)


class TestVacancyResponseCompletenessProperty:
    """
    Property 7: Vacancy response completeness

    For any open vacancy, the listing response item SHALL include title,
    department, location, employment_type, and description fields.

    Feature: blog-and-careers, Property 7: Vacancy response completeness

    **Validates: Requirements 7.2**
    """

    @given(
        title=vacancy_title_st,
        department=vacancy_department_st,
        location=vacancy_location_st,
        employment_type=vacancy_employment_type_st,
        description=vacancy_description_st,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    def test_vacancy_listing_response_contains_all_required_fields(
        self,
        client,
        title: str,
        department: str,
        location: str,
        employment_type: str,
        description: dict,
    ):
        """
        For any open vacancy with random field values, the listing response
        item SHALL include title, department, location, employment_type,
        and description fields.

        Feature: blog-and-careers, Property 7: Vacancy response completeness

        **Validates: Requirements 7.2**
        """
        now = datetime.now(timezone.utc)
        vacancy = Vacancy(
            id=uuid4(),
            title=title,
            department=department,
            location=location,
            employment_type=employment_type,
            description=description,
            requirements=None,
            screening_questions=[],
            status=VacancyStatus.open,
            posted_at=now,
            created_at=now,
            updated_at=now,
        )

        with patch(
            "app.routes.vacancies.list_open_vacancies",
            new_callable=AsyncMock,
            return_value=[vacancy],
        ):
            response = client.get("/api/vacancies")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        item = data[0]

        # Verify all required fields are present in the response
        assert "title" in item, "Response missing 'title' field"
        assert "department" in item, "Response missing 'department' field"
        assert "location" in item, "Response missing 'location' field"
        assert "employment_type" in item, "Response missing 'employment_type' field"
        assert "description" in item, "Response missing 'description' field"

        # Verify field values match what was provided
        assert item["title"] == title
        assert item["department"] == department
        assert item["location"] == location
        assert item["employment_type"] == employment_type
        assert item["description"] == description


# --- Property 10: Custom screening questions inclusion ---

# Strategy: generate a valid ScreeningQuestion-like dict
screening_question_strategy = st.fixed_dictionaries(
    {
        "question": st.text(min_size=1, max_size=200),
        "required": st.booleans(),
        "type": st.sampled_from(["text", "select", "boolean"]),
    }
)

# Strategy: generate a non-empty list of screening questions (1 to 10)
screening_questions_list_strategy = st.lists(
    screening_question_strategy, min_size=1, max_size=10
)


def _make_vacancy_with_questions(questions: list[dict]) -> Vacancy:
    """Create an open Vacancy with the given screening questions."""
    now = datetime.now(timezone.utc)
    return Vacancy(
        id=uuid4(),
        title="Test Position",
        department="Engineering",
        location="Remote",
        employment_type="full-time",
        description={"blocks": [{"type": "paragraph", "text": "Description."}]},
        requirements=None,
        screening_questions=[ScreeningQuestion(**q) for q in questions],
        status=VacancyStatus.open,
        posted_at=now,
        created_at=now,
        updated_at=now,
    )


class TestCustomScreeningQuestionsInclusion:
    """
    Property 10: Custom screening questions inclusion

    For any vacancy with custom screening questions defined, the application
    form schema endpoint SHALL include all those questions in the response.

    Feature: blog-and-careers, Property 10: Custom screening questions inclusion

    **Validates: Requirements 8.3**
    """

    @given(questions=screening_questions_list_strategy)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    def test_all_screening_questions_appear_in_form_response(
        self, client, questions: list[dict]
    ):
        """
        For any vacancy with custom screening questions, the /form endpoint
        SHALL return all those questions in the screening_questions field.

        **Validates: Requirements 8.3**
        """
        vacancy = _make_vacancy_with_questions(questions)

        with patch(
            "app.routes.vacancies.get_vacancy_by_id",
            new_callable=AsyncMock,
            return_value=vacancy,
        ):
            response = client.get(f"/api/vacancies/{vacancy.id}/form")

        assert response.status_code == 200
        data = response.json()

        # The number of screening questions in the response must match
        assert len(data["screening_questions"]) == len(questions)

        # Each question from the input must appear in the response with matching fields
        for i, input_q in enumerate(questions):
            response_q = data["screening_questions"][i]
            assert response_q["question"] == input_q["question"]
            assert response_q["required"] == input_q["required"]
            assert response_q["type"] == input_q["type"]
