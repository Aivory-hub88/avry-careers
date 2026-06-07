"""
Application submission validator.

Validates:
- Required fields: full_name, email, CV file
- CV file size: maximum 10 MB
- CV file format: PDF, DOC, or DOCX (by extension and content-type)
"""

import os
from typing import Optional

# Maximum CV file size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types for CV uploads
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Allowed file extensions for CV uploads
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}


def validate_required_fields(
    full_name: Optional[str],
    email: Optional[str],
    cv_file: object,
) -> None:
    """
    Validate that all required application fields are present.

    Args:
        full_name: Applicant's full name.
        email: Applicant's email address.
        cv_file: Uploaded CV file object (e.g., UploadFile from FastAPI).

    Raises:
        ValueError: If any required field is missing or empty.
    """
    if not full_name or not full_name.strip():
        raise ValueError("Full name is required")

    if not email or not email.strip():
        raise ValueError("Email address is required")

    if cv_file is None:
        raise ValueError("CV file is required")


def validate_cv_file(file) -> None:
    """
    Validate CV file size and format.

    Checks both the file extension and the content-type header to ensure
    the upload is a PDF, DOC, or DOCX file within the 10 MB size limit.

    Args:
        file: An upload file object with `filename`, `content_type`, and `size` attributes.
              For FastAPI UploadFile, `size` may be None until the file is read;
              in that case callers should check size after reading.

    Raises:
        ValueError: If the file exceeds 10 MB or is not in an accepted format.
    """
    # Validate file size if available
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise ValueError("File size exceeds 10 MB limit")

    # Validate file extension
    filename = getattr(file, "filename", None) or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Accepted formats: PDF, DOC, DOCX")

    # Validate content type
    content_type = getattr(file, "content_type", None) or ""
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Accepted formats: PDF, DOC, DOCX")
