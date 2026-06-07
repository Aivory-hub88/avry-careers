"""
Application models for the AVRY Careers Service.

Includes:
- ApplicationStatus enum (submitted, shortlisted, rejected)
- Application model (full application representation with encrypted PII fields)
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStatus(str, Enum):
    """Status of a job application."""

    submitted = "submitted"
    shortlisted = "shortlisted"
    rejected = "rejected"


class Application(BaseModel):
    """Represents a job application with encrypted PII fields."""

    id: UUID
    vacancy_id: UUID
    full_name_encrypted: bytes
    email_encrypted: bytes
    phone_encrypted: Optional[bytes] = None
    cover_letter: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    cv_file_path: str
    cv_original_filename: Optional[str] = None
    screening_responses: list = Field(default_factory=list)
    status: ApplicationStatus = ApplicationStatus.submitted
    tags: list = Field(default_factory=list)
    submitted_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
