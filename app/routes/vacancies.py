"""
Public vacancy endpoints for the AVRY Careers Service.

These endpoints are PUBLIC — no authentication required.

Endpoints:
- GET /api/vacancies — list open vacancies ordered by posted_at DESC
- GET /api/vacancies/{vacancy_id} — single vacancy detail (full description)
- GET /api/vacancies/{vacancy_id}/form — application form schema with custom screening questions
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.models.vacancy import VacancyStatus
from app.services.vacancy_service import get_vacancy_by_id, list_open_vacancies

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


@router.get("")
async def get_vacancies():
    """
    List all open vacancies ordered by posted_at descending.

    Returns a list of open vacancies for the public careers page.
    """
    vacancies = await list_open_vacancies()
    return vacancies


@router.get("/{vacancy_id}")
async def get_vacancy(vacancy_id: UUID):
    """
    Get a single vacancy by ID.

    Returns the full vacancy detail including description.
    Returns 404 if the vacancy does not exist or is not open.
    """
    vacancy = await get_vacancy_by_id(vacancy_id)

    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    if vacancy.status != VacancyStatus.open:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    return vacancy


@router.get("/{vacancy_id}/form")
async def get_vacancy_form(vacancy_id: UUID):
    """
    Get the application form schema for a vacancy.

    Returns the standard application fields and any custom screening questions
    defined for this vacancy.

    Returns 404 if the vacancy does not exist or is not open.
    """
    vacancy = await get_vacancy_by_id(vacancy_id)

    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    if vacancy.status != VacancyStatus.open:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Standard application form fields
    fields = [
        {"name": "full_name", "type": "text", "required": True, "label": "Full Name"},
        {"name": "email", "type": "email", "required": True, "label": "Email Address"},
        {"name": "phone", "type": "tel", "required": False, "label": "Phone Number"},
        {"name": "cover_letter", "type": "textarea", "required": False, "label": "Cover Letter"},
        {"name": "github_url", "type": "url", "required": False, "label": "GitHub Profile URL"},
        {"name": "linkedin_url", "type": "url", "required": False, "label": "LinkedIn Profile URL"},
        {"name": "cv", "type": "file", "required": True, "label": "CV / Resume", "accept": ".pdf,.doc,.docx", "max_size_mb": 10},
    ]

    # Include custom screening questions from the vacancy
    screening_questions = [
        {
            "question": sq.question,
            "required": sq.required,
            "type": sq.type,
        }
        for sq in vacancy.screening_questions
    ]

    return {
        "vacancy_id": str(vacancy.id),
        "vacancy_title": vacancy.title,
        "fields": fields,
        "screening_questions": screening_questions,
    }
