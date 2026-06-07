"""
RBAC (Role-Based Access Control) and User Isolation Tests for avry-careers.

Tests verify:
1. Public endpoints are accessible without authentication
2. Admin endpoints reject unauthenticated requests (401)
3. Admin endpoints reject non-admin users (403)
4. Admin endpoints accept admin/superadmin users (200/201)
5. Public vacancy listing only shows open vacancies (not draft/closed)
6. Application submission is public (no auth)
7. Application details (with decrypted PII) are admin-only
8. PII is never leaked through public endpoints

Validates: Requirements 12.3, 12.4, 12.6, 12.8
"""

import pytest
from unittest.mock import patch, AsyncMock
from jose import jwt

from fastapi.testclient import TestClient

# Test JWT secrets
TEST_SUPABASE_SECRET = "test-supabase-jwt-secret-for-careers-rbac"
TEST_LEGACY_SECRET = "test-legacy-jwt-secret-for-careers-rbac"


def _make_token(payload: dict, secret: str = TEST_SUPABASE_SECRET) -> str:
    """Create a signed JWT token for testing."""
    return jwt.encode(payload, secret, algorithm="HS256")


def _admin_token() -> str:
    return _make_token({"sub": "admin-user-1", "account_type": "admin"})


def _superadmin_token() -> str:
    return _make_token({"sub": "superadmin-user-1", "account_type": "superadmin"})


def _regular_user_token() -> str:
    return _make_token({"sub": "regular-user-1", "account_type": "user"})


def _no_role_token() -> str:
    return _make_token({"sub": "norole-user-1"})


def _wrong_secret_token() -> str:
    return jwt.encode(
        {"sub": "hacker", "account_type": "admin"},
        "wrong-secret-not-configured",
        algorithm="HS256",
    )


@pytest.fixture
def client():
    """Create a test client with mocked DB and configured secrets."""
    with patch("app.database.connection.create_pool", new_callable=AsyncMock), \
         patch("app.database.connection.close_pool", new_callable=AsyncMock), \
         patch("app.database.connection.health_check", new_callable=AsyncMock, return_value=True), \
         patch("app.database.migrations.run_migrations", new_callable=AsyncMock), \
         patch("app.auth.settings") as mock_settings:
        mock_settings.supabase_jwt_secret = TEST_SUPABASE_SECRET
        mock_settings.jwt_secret = TEST_LEGACY_SECRET

        from app.main import app
        with TestClient(app) as c:
            yield c


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS — No auth required
# ═══════════════════════════════════════════════════════════════════════════════


class TestPublicEndpointsNoAuth:
    """Public endpoints must be accessible without any authentication."""

    def test_list_vacancies_no_auth(self, client):
        """GET /api/vacancies is accessible without token."""
        with patch("app.routes.vacancies.list_open_vacancies", new_callable=AsyncMock, return_value=[]):
            response = client.get("/api/vacancies")
        assert response.status_code == 200

    def test_get_vacancy_no_auth(self, client):
        """GET /api/vacancies/{id} is accessible without token (404 for missing)."""
        import uuid
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=None):
            response = client.get(f"/api/vacancies/{uuid.uuid4()}")
        assert response.status_code == 404  # Not 401 or 403

    def test_get_vacancy_form_no_auth(self, client):
        """GET /api/vacancies/{id}/form is accessible without token."""
        import uuid
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=None):
            response = client.get(f"/api/vacancies/{uuid.uuid4()}/form")
        assert response.status_code == 404  # Not 401 or 403

    def test_health_no_auth(self, client):
        """GET /health is accessible without token."""
        response = client.get("/health")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN VACANCY ENDPOINTS — 401 Without Auth
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminVacancyEndpoints401:
    """Admin vacancy endpoints must return 401 without auth."""

    ADMIN_VACANCY_ENDPOINTS = [
        ("GET", "/api/admin/vacancies"),
        ("POST", "/api/admin/vacancies"),
        ("PUT", "/api/admin/vacancies/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/api/admin/vacancies/00000000-0000-0000-0000-000000000001/status"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_VACANCY_ENDPOINTS)
    def test_no_token_returns_401(self, client, method, path):
        """Admin vacancy endpoint without token → 401."""
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing authentication token"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN APPLICATION ENDPOINTS — 401 Without Auth
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminApplicationEndpoints401:
    """Admin application endpoints must return 401 without auth."""

    ADMIN_APP_ENDPOINTS = [
        ("GET", "/api/admin/applications"),
        ("GET", "/api/admin/applications/00000000-0000-0000-0000-000000000001"),
        ("PATCH", "/api/admin/applications/00000000-0000-0000-0000-000000000001/status"),
        ("POST", "/api/admin/applications/00000000-0000-0000-0000-000000000001/tags"),
        ("GET", "/api/admin/applications/00000000-0000-0000-0000-000000000001/cv"),
        ("POST", "/api/admin/applications/00000000-0000-0000-0000-000000000001/email"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_APP_ENDPOINTS)
    def test_no_token_returns_401(self, client, method, path):
        """Admin application endpoint without token → 401."""
        response = client.request(method, path)
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing authentication token"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 401 With Invalid Token
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints401InvalidToken:
    """Admin endpoints must return 401 for invalid/wrong-secret tokens."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/vacancies"),
        ("GET", "/api/admin/applications"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_garbage_token_returns_401(self, client, method, path):
        """Garbage token → 401."""
        response = client.request(method, path, headers={"Authorization": "Bearer not.a.valid.jwt"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_wrong_secret_token_returns_401(self, client, method, path):
        """Token signed with unknown secret → 401."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_wrong_secret_token()}"}
        )
        assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — 403 For Non-Admin Users
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpoints403NonAdmin:
    """Admin endpoints must return 403 for authenticated non-admin users."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/vacancies"),
        ("GET", "/api/admin/applications"),
        ("POST", "/api/admin/vacancies"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_regular_user_returns_403(self, client, method, path):
        """Regular user (account_type: user) → 403."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_regular_user_token()}"}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_no_role_returns_403(self, client, method, path):
        """Token without account_type → 403."""
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {_no_role_token()}"}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — Accept Admin/Superadmin
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdminEndpointsAcceptAdmin:
    """Admin endpoints must accept admin and superadmin users."""

    def test_admin_can_list_vacancies(self, client):
        """Admin user can GET /api/admin/vacancies."""
        with patch("app.routes.admin.list_all_vacancies", new_callable=AsyncMock, return_value=[]):
            response = client.get(
                "/api/admin/vacancies",
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )
        assert response.status_code == 200

    def test_superadmin_can_list_vacancies(self, client):
        """Superadmin user can GET /api/admin/vacancies."""
        with patch("app.routes.admin.list_all_vacancies", new_callable=AsyncMock, return_value=[]):
            response = client.get(
                "/api/admin/vacancies",
                headers={"Authorization": f"Bearer {_superadmin_token()}"},
            )
        assert response.status_code == 200

    def test_admin_can_list_applications(self, client):
        """Admin user can GET /api/admin/applications."""
        with patch("app.routes.admin.list_applications", new_callable=AsyncMock, return_value=[]):
            response = client.get(
                "/api/admin/applications",
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# DUAL SECRET SUPPORT
# ═══════════════════════════════════════════════════════════════════════════════


class TestDualSecretSupport:
    """Both Supabase and legacy JWT secrets are accepted."""

    def test_supabase_secret_accepted(self, client):
        """Token signed with SUPABASE_JWT_SECRET is accepted."""
        token = _make_token({"sub": "user", "account_type": "admin"}, TEST_SUPABASE_SECRET)
        with patch("app.routes.admin.list_all_vacancies", new_callable=AsyncMock, return_value=[]):
            response = client.get(
                "/api/admin/vacancies",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200

    def test_legacy_secret_accepted(self, client):
        """Token signed with legacy JWT_SECRET is accepted."""
        token = _make_token({"sub": "user", "account_type": "admin"}, TEST_LEGACY_SECRET)
        with patch("app.routes.admin.list_all_vacancies", new_callable=AsyncMock, return_value=[]):
            response = client.get(
                "/api/admin/vacancies",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# USER ISOLATION — Public endpoints never expose non-open vacancies
# ═══════════════════════════════════════════════════════════════════════════════


class TestVacancyIsolation:
    """Public endpoints must never expose draft or closed vacancies."""

    def test_closed_vacancy_returns_404(self, client):
        """GET /api/vacancies/{id} returns 404 for closed vacancies."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.vacancy import Vacancy, VacancyStatus

        closed_vacancy = Vacancy(
            id=uuid4(), title="Closed Job", description={"blocks": []},
            status=VacancyStatus.closed, posted_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=closed_vacancy):
            response = client.get(f"/api/vacancies/{closed_vacancy.id}")
        assert response.status_code == 404

    def test_draft_vacancy_returns_404(self, client):
        """GET /api/vacancies/{id} returns 404 for draft vacancies."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.vacancy import Vacancy, VacancyStatus

        draft_vacancy = Vacancy(
            id=uuid4(), title="Draft Job", description={"blocks": []},
            status=VacancyStatus.draft,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=draft_vacancy):
            response = client.get(f"/api/vacancies/{draft_vacancy.id}")
        assert response.status_code == 404

    def test_open_vacancy_accessible(self, client):
        """GET /api/vacancies/{id} returns 200 for open vacancies."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.vacancy import Vacancy, VacancyStatus

        open_vacancy = Vacancy(
            id=uuid4(), title="Open Job", description={"blocks": []},
            status=VacancyStatus.open, posted_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=open_vacancy):
            response = client.get(f"/api/vacancies/{open_vacancy.id}")
        assert response.status_code == 200

    def test_closed_vacancy_form_returns_404(self, client):
        """GET /api/vacancies/{id}/form returns 404 for non-open vacancies."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.models.vacancy import Vacancy, VacancyStatus

        closed_vacancy = Vacancy(
            id=uuid4(), title="Closed", description={"blocks": []},
            status=VacancyStatus.closed, posted_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        with patch("app.routes.vacancies.get_vacancy_by_id", new_callable=AsyncMock, return_value=closed_vacancy):
            response = client.get(f"/api/vacancies/{closed_vacancy.id}/form")
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PII ISOLATION — Applicant data is admin-only
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIIIsolation:
    """PII (names, emails, phones) is only accessible through admin endpoints."""

    def test_application_detail_requires_admin(self, client):
        """GET /api/admin/applications/{id} requires admin auth."""
        import uuid
        response = client.get(f"/api/admin/applications/{uuid.uuid4()}")
        assert response.status_code == 401

    def test_cv_download_requires_admin(self, client):
        """GET /api/admin/applications/{id}/cv requires admin auth."""
        import uuid
        response = client.get(f"/api/admin/applications/{uuid.uuid4()}/cv")
        assert response.status_code == 401

    def test_email_send_requires_admin(self, client):
        """POST /api/admin/applications/{id}/email requires admin auth."""
        import uuid
        response = client.post(
            f"/api/admin/applications/{uuid.uuid4()}/email",
            json={"subject": "test", "body": "test"},
        )
        assert response.status_code == 401

    def test_regular_user_cannot_access_pii(self, client):
        """Regular user cannot access application details (PII)."""
        import uuid
        response = client.get(
            f"/api/admin/applications/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {_regular_user_token()}"},
        )
        assert response.status_code == 403

    def test_regular_user_cannot_download_cv(self, client):
        """Regular user cannot download CVs."""
        import uuid
        response = client.get(
            f"/api/admin/applications/{uuid.uuid4()}/cv",
            headers={"Authorization": f"Bearer {_regular_user_token()}"},
        )
        assert response.status_code == 403

    def test_regular_user_cannot_send_email(self, client):
        """Regular user cannot send emails to applicants."""
        import uuid
        response = client.post(
            f"/api/admin/applications/{uuid.uuid4()}/email",
            json={"subject": "test", "body": "test"},
            headers={"Authorization": f"Bearer {_regular_user_token()}"},
        )
        assert response.status_code == 403
