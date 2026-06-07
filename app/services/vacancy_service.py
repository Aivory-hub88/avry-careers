"""
Vacancy service — business logic for vacancy CRUD operations.

Provides:
- create_vacancy: create a new vacancy (defaults to draft status)
- get_vacancy_by_id: retrieve a single vacancy by UUID
- list_open_vacancies: public listing (status=open, ordered by posted_at DESC)
- list_all_vacancies: admin listing (all statuses)
- update_vacancy: partial update of vacancy fields
- change_status: transition vacancy status with side effects (set posted_at on publish)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.database.connection import execute_query, fetch_all, fetch_one
from app.models.vacancy import ScreeningQuestion, Vacancy, VacancyStatus

logger = logging.getLogger(__name__)


def _row_to_vacancy(row) -> Vacancy:
    """Convert an asyncpg Record to a Vacancy model instance."""
    screening_questions_raw = row["screening_questions"]
    if isinstance(screening_questions_raw, str):
        screening_questions_raw = json.loads(screening_questions_raw)

    screening_questions = [
        ScreeningQuestion(**sq) if isinstance(sq, dict) else sq
        for sq in (screening_questions_raw or [])
    ]

    description = row["description"]
    if isinstance(description, str):
        description = json.loads(description)

    requirements = row["requirements"]
    if isinstance(requirements, str):
        requirements = json.loads(requirements)

    return Vacancy(
        id=row["id"],
        title=row["title"],
        department=row["department"],
        location=row["location"],
        employment_type=row["employment_type"],
        description=description,
        requirements=requirements,
        screening_questions=screening_questions,
        status=VacancyStatus(row["status"]),
        posted_at=row["posted_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def create_vacancy(
    title: str,
    description: Any,
    department: Optional[str] = None,
    location: Optional[str] = None,
    employment_type: Optional[str] = None,
    requirements: Optional[Any] = None,
    screening_questions: Optional[list[dict]] = None,
    status: str = "draft",
) -> Vacancy:
    """
    Create a new vacancy.

    Args:
        title: Job title (required)
        description: JSONB content from rich editor (required)
        department: Department name
        location: Job location
        employment_type: One of full-time, part-time, contract, internship
        requirements: JSONB requirements content
        screening_questions: List of {question, required, type} dicts
        status: Initial status (defaults to 'draft')

    Returns:
        The created Vacancy instance.
    """
    # Validate status
    vacancy_status = VacancyStatus(status)

    # If publishing immediately, set posted_at
    posted_at = None
    if vacancy_status == VacancyStatus.open:
        posted_at = datetime.now(timezone.utc)

    # Serialize JSONB fields
    description_json = json.dumps(description) if not isinstance(description, str) else description
    requirements_json = json.dumps(requirements) if requirements is not None else None
    questions_json = json.dumps(screening_questions or [])

    query = """
        INSERT INTO vacancies (title, department, location, employment_type, description, requirements, screening_questions, status, posted_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, $9)
        RETURNING id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
    """

    row = await fetch_one(
        query,
        title,
        department,
        location,
        employment_type,
        description_json,
        requirements_json,
        questions_json,
        vacancy_status.value,
        posted_at,
    )

    logger.info(f"Created vacancy '{title}' with status '{vacancy_status.value}' (id={row['id']})")
    return _row_to_vacancy(row)


async def get_vacancy_by_id(vacancy_id: UUID) -> Optional[Vacancy]:
    """
    Retrieve a single vacancy by its UUID.

    Returns None if no vacancy exists with the given ID.
    """
    query = """
        SELECT id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
        FROM vacancies
        WHERE id = $1
    """

    row = await fetch_one(query, vacancy_id)
    if row is None:
        return None

    return _row_to_vacancy(row)


async def list_open_vacancies() -> list[Vacancy]:
    """
    List all open vacancies ordered by posted_at descending.

    Used for the public careers page listing.
    """
    query = """
        SELECT id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
        FROM vacancies
        WHERE status = 'open'
        ORDER BY posted_at DESC
    """

    rows = await fetch_all(query)
    return [_row_to_vacancy(row) for row in rows]


async def list_all_vacancies() -> list[Vacancy]:
    """
    List all vacancies regardless of status, ordered by created_at descending.

    Used for the admin vacancy management panel.
    """
    query = """
        SELECT id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
        FROM vacancies
        ORDER BY created_at DESC
    """

    rows = await fetch_all(query)
    return [_row_to_vacancy(row) for row in rows]


async def update_vacancy(vacancy_id: UUID, **fields: Any) -> Optional[Vacancy]:
    """
    Partially update a vacancy's fields.

    Accepts any combination of: title, department, location, employment_type,
    description, requirements, screening_questions.

    Returns the updated Vacancy, or None if the vacancy was not found.
    """
    # Only allow known mutable fields
    allowed_fields = {
        "title",
        "department",
        "location",
        "employment_type",
        "description",
        "requirements",
        "screening_questions",
    }

    updates = {k: v for k, v in fields.items() if k in allowed_fields and v is not None}

    if not updates:
        # Nothing to update — just return current state
        return await get_vacancy_by_id(vacancy_id)

    # Build the SET clause dynamically
    set_clauses = []
    params: list[Any] = []
    param_idx = 1

    for field, value in updates.items():
        # JSONB fields need serialization
        if field in ("description", "requirements", "screening_questions"):
            serialized = json.dumps(value) if not isinstance(value, str) else value
            set_clauses.append(f"{field} = ${param_idx}::jsonb")
            params.append(serialized)
        else:
            set_clauses.append(f"{field} = ${param_idx}")
            params.append(value)
        param_idx += 1

    # Always update updated_at
    set_clauses.append(f"updated_at = ${param_idx}")
    params.append(datetime.now(timezone.utc))
    param_idx += 1

    # Add vacancy_id as the last parameter
    params.append(vacancy_id)

    query = f"""
        UPDATE vacancies
        SET {', '.join(set_clauses)}
        WHERE id = ${param_idx}
        RETURNING id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
    """

    row = await fetch_one(query, *params)
    if row is None:
        return None

    logger.info(f"Updated vacancy {vacancy_id}: fields={list(updates.keys())}")
    return _row_to_vacancy(row)


async def change_status(vacancy_id: UUID, new_status: str) -> Optional[Vacancy]:
    """
    Change the status of a vacancy.

    When transitioning to 'open', posted_at is set to the current timestamp.
    When transitioning to 'closed' or 'draft', posted_at is left unchanged.

    Returns the updated Vacancy, or None if the vacancy was not found.
    """
    vacancy_status = VacancyStatus(new_status)

    # Set posted_at when publishing (transitioning to open)
    posted_at_clause = ""
    params: list[Any] = [vacancy_status.value, datetime.now(timezone.utc)]

    if vacancy_status == VacancyStatus.open:
        posted_at_clause = ", posted_at = $3"
        params.append(datetime.now(timezone.utc))
        params.append(vacancy_id)
        param_idx_id = 4
    else:
        params.append(vacancy_id)
        param_idx_id = 3

    query = f"""
        UPDATE vacancies
        SET status = $1, updated_at = $2{posted_at_clause}
        WHERE id = ${param_idx_id}
        RETURNING id, title, department, location, employment_type, description, requirements, screening_questions, status, posted_at, created_at, updated_at
    """

    row = await fetch_one(query, *params)
    if row is None:
        return None

    logger.info(f"Changed vacancy {vacancy_id} status to '{vacancy_status.value}'")
    return _row_to_vacancy(row)
