"""
Unit tests for application validator functions.

Tests validate_required_fields and validate_cv_file with specific
examples and edge cases.
"""

import pytest

from app.validators.application_validator import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_cv_file,
    validate_required_fields,
)


class FakeUploadFile:
    """Minimal fake upload file for testing."""

    def __init__(self, filename: str = "cv.pdf", content_type: str = "application/pdf", size: int = 1024):
        self.filename = filename
        self.content_type = content_type
        self.size = size


class TestValidateRequiredFields:
    """Tests for validate_required_fields."""

    def test_valid_fields_passes(self):
        """All required fields present — no exception."""
        validate_required_fields("Alice Smith", "alice@example.com", FakeUploadFile())

    def test_missing_full_name_raises(self):
        with pytest.raises(ValueError, match="Full name is required"):
            validate_required_fields(None, "alice@example.com", FakeUploadFile())

    def test_empty_full_name_raises(self):
        with pytest.raises(ValueError, match="Full name is required"):
            validate_required_fields("", "alice@example.com", FakeUploadFile())

    def test_whitespace_full_name_raises(self):
        with pytest.raises(ValueError, match="Full name is required"):
            validate_required_fields("   ", "alice@example.com", FakeUploadFile())

    def test_missing_email_raises(self):
        with pytest.raises(ValueError, match="Email address is required"):
            validate_required_fields("Alice", None, FakeUploadFile())

    def test_empty_email_raises(self):
        with pytest.raises(ValueError, match="Email address is required"):
            validate_required_fields("Alice", "", FakeUploadFile())

    def test_whitespace_email_raises(self):
        with pytest.raises(ValueError, match="Email address is required"):
            validate_required_fields("Alice", "  ", FakeUploadFile())

    def test_missing_cv_file_raises(self):
        with pytest.raises(ValueError, match="CV file is required"):
            validate_required_fields("Alice", "alice@example.com", None)


class TestValidateCvFile:
    """Tests for validate_cv_file."""

    def test_valid_pdf_passes(self):
        validate_cv_file(FakeUploadFile("resume.pdf", "application/pdf", 1024))

    def test_valid_doc_passes(self):
        validate_cv_file(FakeUploadFile("resume.doc", "application/msword", 5000))

    def test_valid_docx_passes(self):
        validate_cv_file(
            FakeUploadFile(
                "resume.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                2048,
            )
        )

    def test_file_exactly_10mb_passes(self):
        """Exactly 10 MB should be accepted."""
        validate_cv_file(FakeUploadFile("cv.pdf", "application/pdf", MAX_FILE_SIZE))

    def test_file_exceeds_10mb_raises(self):
        with pytest.raises(ValueError, match="File size exceeds 10 MB limit"):
            validate_cv_file(FakeUploadFile("cv.pdf", "application/pdf", MAX_FILE_SIZE + 1))

    def test_invalid_extension_raises(self):
        with pytest.raises(ValueError, match="Accepted formats: PDF, DOC, DOCX"):
            validate_cv_file(FakeUploadFile("cv.txt", "text/plain", 1024))

    def test_invalid_content_type_raises(self):
        with pytest.raises(ValueError, match="Accepted formats: PDF, DOC, DOCX"):
            validate_cv_file(FakeUploadFile("cv.pdf", "image/png", 1024))

    def test_no_extension_raises(self):
        with pytest.raises(ValueError, match="Accepted formats: PDF, DOC, DOCX"):
            validate_cv_file(FakeUploadFile("cv", "application/pdf", 1024))

    def test_size_none_skips_size_check(self):
        """When size is None (not yet read), size check is skipped."""
        validate_cv_file(FakeUploadFile("cv.pdf", "application/pdf", None))

    def test_max_file_size_is_10mb(self):
        assert MAX_FILE_SIZE == 10 * 1024 * 1024

    def test_allowed_extensions(self):
        assert ALLOWED_EXTENSIONS == {".pdf", ".doc", ".docx"}

    def test_allowed_content_types(self):
        assert ALLOWED_CONTENT_TYPES == {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
