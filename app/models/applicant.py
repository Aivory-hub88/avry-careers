"""
Applicant model for admin display after PII decryption.

This model represents the decrypted view of an applicant's personal information,
used only in admin-authenticated contexts where PII is decrypted for display.
"""

from typing import Optional

from pydantic import BaseModel


class Applicant(BaseModel):
    """Decrypted applicant PII for admin display."""

    full_name: str
    email: str
    phone: Optional[str] = None
