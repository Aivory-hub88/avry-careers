"""
Vacancy models for the AVRY Careers Service.

Includes:
- VacancyStatus enum (draft, open, closed)
- ScreeningQuestion model (custom application questions)
- Vacancy model (full vacancy representation)
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VacancyStatus(str, Enum):
    """Status of a job vacancy."""

    draft = "draft"
    open = "open"
    closed = "closed"


class ScreeningQuestion(BaseModel):
    """A custom screening question added to a vacancy's application form."""

    question: str
    required: bool = False
    type: str = "text"  # e.g., 'text', 'select', 'boolean'


class Vacancy(BaseModel):
    """Represents a job vacancy listing."""

    id: UUID
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None  # full-time | part-time | contract | internship
    description: dict | list  # JSONB rich editor output
    requirements: Optional[dict | list] = None  # JSONB
    screening_questions: list[ScreeningQuestion] = Field(default_factory=list)
    status: VacancyStatus = VacancyStatus.draft
    posted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
