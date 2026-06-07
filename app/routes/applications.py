"""
Application submission endpoint for the AVRY Careers Service.

This endpoint is PUBLIC — no authentication required.

Endpoints:
- POST /api/vacancies/{vacancy_id}/apply — submit a job application (multipart form)

Validation:
- Required fields: full_name, email, CV file
- CV file size: maximum 10 MB
- CV file format: PDF, DOC, or DOCX

Errors:
- 404: Vacancy not found or not open
- 413: CV file exceeds 10 MB
- 422: Invalid file format or missing required fields
"""

import json
import logging
import os
import uuid as uuid_mod
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.database.connection import execute_query, fetch_one
from app.models.vacancy import VacancyStatus
from app.services.encryption_service import encrypt_file, encrypt_pii
from app.validators.application_validator import (
    MAX_FILE_SIZE,
    validate_cv_file,
    validate_required_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vacancies", tags=["applications"])

# Directory for storing encrypted CV files
CV_STORAGE_DIR = os.getenv("CV_STORAGE_DIR", "/app/data/cvs")


@router.post("/{vacancy_id}/apply", status_code=201)
async def submit_application(
    vacancy_id: UUID,
    full_name: str = Form(default=None),
    email: str = Form(default=None),
    phone: Optional[str] = Form(default=None),
    cover_letter: Optional[str] = Form(default=None),
    github_url: Optional[str] = Form(default=None),
    linkedin_url: Optional[str] = Form(default=None),
    screening_responses: Optional[str] = Form(default=None),
    cv: UploadFile = File(default=None),
):
    """
    Submit a job application for a specific vacancy.

    Accepts multipart form data with applicant details and CV file upload.
    Encrypts PII fields and CV file before storage.

    Returns 201 with a confirmation message on success.
    """
    # 1. Validate vacancy exists and is open
    vacancy_row = await fetch_one(
        "SELECT id, status FROM vacancies WHERE id = $1",
        vacancy_id,
    )

    if vacancy_row is None:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    if vacancy_row["status"] != VacancyStatus.open.value:
        raise HTTPException(status_code=404, detail="Vacancy is not accepting applications")

    # 2. Validate required fields
    try:
        validate_required_fields(full_name, email, cv)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 3. Validate CV file (format check before reading)
    try:
        validate_cv_file(cv)
    except ValueError as e:
        # Determine if this is a size error or format error
        error_msg = str(e)
        if "10 MB" in error_msg or "size" in error_msg.lower():
            raise HTTPException(status_code=413, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)

    # 4. Read CV file content and verify size after reading
    cv_bytes = await cv.read()

    if len(cv_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds 10 MB limit")

    # 5. Parse screening responses JSON string
    parsed_screening_responses = []
    if screening_responses:
        try:
            parsed_screening_responses = json.loads(screening_responses)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=422,
                detail="Screening responses must be a valid JSON string",
            )

    # 6. Encrypt PII fields
    full_name_encrypted = encrypt_pii(full_name.strip())
    email_encrypted = encrypt_pii(email.strip())
    phone_encrypted = encrypt_pii(phone.strip()) if phone and phone.strip() else None

    # 7. Encrypt CV file and save to disk
    encrypted_cv = encrypt_file(cv_bytes)

    # Generate unique filename for encrypted CV
    cv_file_id = str(uuid_mod.uuid4())
    cv_file_path = os.path.join(CV_STORAGE_DIR, f"{cv_file_id}.enc")

    # Ensure storage directory exists
    os.makedirs(CV_STORAGE_DIR, exist_ok=True)

    try:
        with open(cv_file_path, "wb") as f:
            f.write(encrypted_cv)
    except IOError as e:
        logger.error(f"Failed to write encrypted CV to disk: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

    # 8. Insert application into database
    try:
        query = """
            INSERT INTO applications (
                vacancy_id, full_name_encrypted, email_encrypted, phone_encrypted,
                cover_letter, github_url, linkedin_url, cv_file_path,
                cv_original_filename, screening_responses, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            RETURNING id, submitted_at
        """

        row = await fetch_one(
            query,
            vacancy_id,
            full_name_encrypted,
            email_encrypted,
            phone_encrypted,
            cover_letter,
            github_url,
            linkedin_url,
            cv_file_path,
            cv.filename,
            json.dumps(parsed_screening_responses),
            "submitted",
        )

        logger.info(
            f"Application submitted for vacancy {vacancy_id}: id={row['id']}"
        )

        return {
            "message": "Application submitted successfully",
            "application_id": str(row["id"]),
            "submitted_at": row["submitted_at"].isoformat(),
        }

    except Exception as e:
        # Clean up the encrypted CV file if database insert fails
        if os.path.exists(cv_file_path):
            try:
                os.remove(cv_file_path)
            except OSError:
                pass
        logger.error(f"Failed to persist application: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit application")
