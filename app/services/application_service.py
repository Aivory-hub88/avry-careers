"""
Application service — business logic for admin application management.

Provides:
- list_applications: all applications with decrypted names, grouped by vacancy
- get_application_detail: full application details with all PII decrypted
- update_application_status: shortlist or reject an application
- add_tag: add a custom label to an application
- get_cv_file: read and decrypt CV file from disk, return bytes + filename
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from app.database.connection import execute_query, fetch_all, fetch_one
from app.models.application import Application, ApplicationStatus
from app.services.encryption_service import decrypt_file, decrypt_pii

logger = logging.getLogger(__name__)


async def list_applications() -> list[dict[str, Any]]:
    """
    List all applications grouped by vacancy.

    Returns a list of vacancy groups, each containing:
    - vacancy_id, vacancy_title
    - applications: list of application summaries with decrypted full_name

    Used for the admin applications listing panel (Requirement 10.1).
    """
    query = """
        SELECT
            a.id,
            a.vacancy_id,
            a.full_name_encrypted,
            a.status,
            a.tags,
            a.submitted_at,
            v.title AS vacancy_title
        FROM applications a
        JOIN vacancies v ON v.id = a.vacancy_id
        ORDER BY v.title ASC, a.submitted_at DESC
    """

    rows = await fetch_all(query)

    # Group by vacancy
    groups: dict[str, dict[str, Any]] = {}

    for row in rows:
        vacancy_id = str(row["vacancy_id"])

        if vacancy_id not in groups:
            groups[vacancy_id] = {
                "vacancy_id": vacancy_id,
                "vacancy_title": row["vacancy_title"],
                "applications": [],
            }

        # Decrypt the full name for display in the listing
        try:
            full_name = decrypt_pii(bytes(row["full_name_encrypted"]))
        except Exception:
            full_name = "[Decryption Error]"

        # Parse tags from JSONB
        tags = row["tags"]
        if isinstance(tags, str):
            tags = json.loads(tags)

        groups[vacancy_id]["applications"].append(
            {
                "id": str(row["id"]),
                "full_name": full_name,
                "status": row["status"],
                "tags": tags or [],
                "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
            }
        )

    return list(groups.values())


async def get_application_detail(app_id: UUID) -> Optional[dict[str, Any]]:
    """
    Get full application details with all PII decrypted.

    Returns all fields including decrypted full_name, email, phone,
    cover letter, linked profiles, screening responses, and CV filename.

    Used for the admin application detail view (Requirement 10.2).
    """
    query = """
        SELECT
            a.id,
            a.vacancy_id,
            a.full_name_encrypted,
            a.email_encrypted,
            a.phone_encrypted,
            a.cover_letter,
            a.github_url,
            a.linkedin_url,
            a.cv_file_path,
            a.cv_original_filename,
            a.screening_responses,
            a.status,
            a.tags,
            a.submitted_at,
            a.updated_at,
            v.title AS vacancy_title
        FROM applications a
        JOIN vacancies v ON v.id = a.vacancy_id
        WHERE a.id = $1
    """

    row = await fetch_one(query, app_id)
    if row is None:
        return None

    # Decrypt PII fields
    try:
        full_name = decrypt_pii(bytes(row["full_name_encrypted"]))
    except Exception:
        full_name = "[Decryption Error]"

    try:
        email = decrypt_pii(bytes(row["email_encrypted"]))
    except Exception:
        email = "[Decryption Error]"

    phone = None
    if row["phone_encrypted"]:
        try:
            phone = decrypt_pii(bytes(row["phone_encrypted"]))
        except Exception:
            phone = "[Decryption Error]"

    # Parse JSONB fields
    screening_responses = row["screening_responses"]
    if isinstance(screening_responses, str):
        screening_responses = json.loads(screening_responses)

    tags = row["tags"]
    if isinstance(tags, str):
        tags = json.loads(tags)

    return {
        "id": str(row["id"]),
        "vacancy_id": str(row["vacancy_id"]),
        "vacancy_title": row["vacancy_title"],
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "cover_letter": row["cover_letter"],
        "github_url": row["github_url"],
        "linkedin_url": row["linkedin_url"],
        "cv_original_filename": row["cv_original_filename"],
        "screening_responses": screening_responses or [],
        "status": row["status"],
        "tags": tags or [],
        "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def update_application_status(app_id: UUID, new_status: str) -> Optional[dict[str, Any]]:
    """
    Update the status of an application (shortlist or reject).

    Args:
        app_id: Application UUID
        new_status: One of 'shortlisted' or 'rejected'

    Returns:
        Updated application summary, or None if not found.

    Validates: Requirements 10.3, 10.7
    """
    # Validate the status value
    application_status = ApplicationStatus(new_status)

    query = """
        UPDATE applications
        SET status = $1, updated_at = $2
        WHERE id = $3
        RETURNING id, status, updated_at
    """

    row = await fetch_one(query, application_status.value, datetime.now(timezone.utc), app_id)
    if row is None:
        return None

    logger.info(f"Updated application {app_id} status to '{application_status.value}'")
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def add_tag(app_id: UUID, tag: str) -> Optional[dict[str, Any]]:
    """
    Add a custom tag/label to an application.

    Appends the tag to the existing tags JSONB array (no duplicates).

    Args:
        app_id: Application UUID
        tag: The tag string to add

    Returns:
        Updated application with tags, or None if not found.

    Validates: Requirement 10.4
    """
    # First fetch current tags to avoid duplicates
    current = await fetch_one("SELECT tags FROM applications WHERE id = $1", app_id)
    if current is None:
        return None

    tags = current["tags"]
    if isinstance(tags, str):
        tags = json.loads(tags)
    if tags is None:
        tags = []

    # Avoid duplicate tags
    if tag not in tags:
        tags.append(tag)

    tags_json = json.dumps(tags)

    query = """
        UPDATE applications
        SET tags = $1::jsonb, updated_at = $2
        WHERE id = $3
        RETURNING id, tags, updated_at
    """

    row = await fetch_one(query, tags_json, datetime.now(timezone.utc), app_id)
    if row is None:
        return None

    result_tags = row["tags"]
    if isinstance(result_tags, str):
        result_tags = json.loads(result_tags)

    logger.info(f"Added tag '{tag}' to application {app_id}")
    return {
        "id": str(row["id"]),
        "tags": result_tags or [],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def get_cv_file(app_id: UUID) -> Optional[tuple[bytes, str]]:
    """
    Read and decrypt the CV file for an application.

    Args:
        app_id: Application UUID

    Returns:
        Tuple of (decrypted_bytes, original_filename), or None if not found.
        Raises FileNotFoundError if the encrypted file is missing from disk.
    """
    query = """
        SELECT cv_file_path, cv_original_filename
        FROM applications
        WHERE id = $1
    """

    row = await fetch_one(query, app_id)
    if row is None:
        return None

    cv_file_path = row["cv_file_path"]
    original_filename = row["cv_original_filename"] or "cv_download"

    # Read the encrypted file from disk
    file_path = Path(cv_file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"CV file not found at path: {cv_file_path}")

    encrypted_bytes = file_path.read_bytes()

    # Decrypt the file content
    decrypted_bytes = decrypt_file(encrypted_bytes)

    logger.info(f"Decrypted CV for application {app_id}: {original_filename}")
    return decrypted_bytes, original_filename
