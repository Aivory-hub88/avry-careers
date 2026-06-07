"""
Admin endpoints for the AVRY Careers Service.

All endpoints require admin JWT authentication (admin or superadmin account_type).

Vacancy Endpoints:
- POST /api/admin/vacancies — create vacancy with Rich_Editor content and custom screening questions
- GET /api/admin/vacancies — list all vacancies (all statuses) for admin management
- PUT /api/admin/vacancies/{vacancy_id} — edit vacancy
- PATCH /api/admin/vacancies/{vacancy_id}/status — change status (open/closed/draft)

Application Management Endpoints:
- GET /api/admin/applications — all applications grouped by vacancy
- GET /api/admin/applications/{app_id} — full details with decrypted PII
- PATCH /api/admin/applications/{app_id}/status — shortlist/reject
- POST /api/admin/applications/{app_id}/tags — add custom tag
- GET /api/admin/applications/{app_id}/cv — download decrypted CV
"""

import mimetypes
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import require_admin
from app.database.connection import fetch_one
from app.models.application import ApplicationStatus
from app.services.application_service import (
    add_tag,
    get_application_detail,
    get_cv_file,
    list_applications,
    update_application_status,
)
from app.services.email_service import send_email
from app.services.encryption_service import decrypt_pii
from app.services.vacancy_service import (
    change_status,
    create_vacancy,
    get_vacancy_by_id,
    list_all_vacancies,
    update_vacancy,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Request Models ──────────────────────────────────────────────────────────


class VacancyCreate(BaseModel):
    """Request body for creating a new vacancy."""

    title: str
    description: Any  # Rich editor JSONB content
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    requirements: Optional[Any] = None
    screening_questions: Optional[list[dict]] = None
    status: str = Field(default="draft")


class VacancyUpdate(BaseModel):
    """Request body for updating a vacancy. All fields are optional."""

    title: Optional[str] = None
    description: Optional[Any] = None
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    requirements: Optional[Any] = None
    screening_questions: Optional[list[dict]] = None


class StatusChange(BaseModel):
    """Request body for changing a vacancy's status."""

    status: str  # "open" or "closed"


class ApplicationStatusChange(BaseModel):
    """Request body for changing an application's status."""

    status: str  # "shortlisted" or "rejected"


class TagAdd(BaseModel):
    """Request body for adding a tag to an application."""

    tag: str


class EmailCompose(BaseModel):
    """Request body for sending an email to an applicant."""

    subject: str
    body: str


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/vacancies", status_code=201)
async def create_vacancy_endpoint(
    body: VacancyCreate,
    _admin: dict = Depends(require_admin),
):
    """
    Create a new vacancy.

    Accepts Rich_Editor JSONB content for the description and optional
    custom screening questions.
    """
    vacancy = await create_vacancy(
        title=body.title,
        description=body.description,
        department=body.department,
        location=body.location,
        employment_type=body.employment_type,
        requirements=body.requirements,
        screening_questions=body.screening_questions,
        status=body.status,
    )
    return vacancy


@router.get("/vacancies")
async def list_vacancies_admin(
    _admin: dict = Depends(require_admin),
):
    """
    List all vacancies (all statuses) for the admin management panel.
    """
    vacancies = await list_all_vacancies()
    return vacancies


@router.put("/vacancies/{vacancy_id}")
async def update_vacancy_endpoint(
    vacancy_id: UUID,
    body: VacancyUpdate,
    _admin: dict = Depends(require_admin),
):
    """
    Edit an existing vacancy.

    Only provided fields are updated; omitted fields remain unchanged.
    """
    # Build kwargs from non-None fields
    update_fields = body.model_dump(exclude_none=True)

    if not update_fields:
        # Nothing to update — return current state
        vacancy = await get_vacancy_by_id(vacancy_id)
        if vacancy is None:
            raise HTTPException(status_code=404, detail="Vacancy not found")
        return vacancy

    vacancy = await update_vacancy(vacancy_id, **update_fields)

    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    return vacancy


@router.patch("/vacancies/{vacancy_id}/status")
async def change_vacancy_status(
    vacancy_id: UUID,
    body: StatusChange,
    _admin: dict = Depends(require_admin),
):
    """
    Change the status of a vacancy (open/closed/draft).

    When transitioning to 'open', the vacancy's posted_at timestamp is set.
    """
    # Validate the status value
    valid_statuses = {"open", "closed", "draft"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    vacancy = await change_status(vacancy_id, body.status)

    if vacancy is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    return vacancy


# ─── Application Management Endpoints ────────────────────────────────────────


@router.get("/applications")
async def list_applications_admin(
    _admin: dict = Depends(require_admin),
):
    """
    List all applications grouped by vacancy.

    Returns vacancy groups with application summaries including decrypted
    applicant names, status, tags, and submission dates.
    """
    applications = await list_applications()
    return applications


@router.get("/applications/{app_id}")
async def get_application_detail_endpoint(
    app_id: UUID,
    _admin: dict = Depends(require_admin),
):
    """
    Get full application details with decrypted PII.

    Returns all form responses, decrypted personal information,
    linked profiles (GitHub, LinkedIn), and CV filename.
    """
    application = await get_application_detail(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.patch("/applications/{app_id}/status")
async def change_application_status(
    app_id: UUID,
    body: ApplicationStatusChange,
    _admin: dict = Depends(require_admin),
):
    """
    Update the status of an application (shortlist or reject).

    Valid statuses: 'shortlisted', 'rejected', 'submitted'.
    """
    valid_statuses = {s.value for s in ApplicationStatus}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    result = await update_application_status(app_id, body.status)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.post("/applications/{app_id}/tags")
async def add_application_tag(
    app_id: UUID,
    body: TagAdd,
    _admin: dict = Depends(require_admin),
):
    """
    Add a custom tag/label to an application.

    Tags are used for organizing applicants (e.g., 'interview scheduled',
    'needs follow-up', 'strong candidate').
    """
    if not body.tag or not body.tag.strip():
        raise HTTPException(status_code=422, detail="Tag cannot be empty")

    result = await add_tag(app_id, body.tag.strip())
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.get("/applications/{app_id}/cv")
async def download_application_cv(
    app_id: UUID,
    _admin: dict = Depends(require_admin),
):
    """
    Download the decrypted CV file for an application.

    Returns the file with appropriate content type based on the
    original filename extension.
    """
    try:
        result = await get_cv_file(app_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="CV file not found on disk")

    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")

    decrypted_bytes, original_filename = result

    # Determine content type from the original filename
    content_type, _ = mimetypes.guess_type(original_filename)
    if content_type is None:
        content_type = "application/octet-stream"

    return Response(
        content=decrypted_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{original_filename}"',
        },
    )


@router.post("/applications/{app_id}/email")
async def send_email_to_applicant(
    app_id: UUID,
    body: EmailCompose,
    _admin: dict = Depends(require_admin),
):
    """
    Compose and send an email to an applicant.

    Looks up the application, decrypts the applicant's email address,
    and sends the email via SMTP.
    """
    if not body.subject or not body.subject.strip():
        raise HTTPException(status_code=422, detail="Subject cannot be empty")
    if not body.body or not body.body.strip():
        raise HTTPException(status_code=422, detail="Body cannot be empty")

    # Look up the application to get the encrypted email
    row = await fetch_one(
        "SELECT email_encrypted FROM applications WHERE id = $1",
        app_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")

    # Decrypt the applicant's email address
    try:
        applicant_email = decrypt_pii(row["email_encrypted"])
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt applicant email",
        )

    # Send the email
    try:
        await send_email(
            to_email=applicant_email,
            subject=body.subject.strip(),
            body=body.body.strip(),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"detail": "Email sent successfully", "to": applicant_email}
