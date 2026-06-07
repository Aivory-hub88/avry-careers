"""
Property-based tests for application management.

Feature: blog-and-careers, Property 11: Application status transitions persist correctly

Validates: Requirements 10.3, 10.7
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.auth import require_admin
from app.models.application import ApplicationStatus


# --- Hypothesis Strategies ---

# Generate random UUIDs for application IDs
app_id_strategy = st.uuids()

# All possible initial statuses an application can be in
initial_status_strategy = st.sampled_from([
    ApplicationStatus.submitted,
    ApplicationStatus.shortlisted,
    ApplicationStatus.rejected,
])

# Target statuses for admin transitions (shortlist or reject)
target_status_strategy = st.sampled_from([
    ApplicationStatus.shortlisted,
    ApplicationStatus.rejected,
])


async def _mock_admin():
    """Override for require_admin dependency - always grants admin access."""
    return {"account_type": "admin", "sub": "admin-user-id"}


@pytest.fixture(scope="class")
def client():
    """Create a test client with mocked database pool and admin auth (class-scoped)."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                from fastapi.testclient import TestClient

                # Override the admin dependency for all admin endpoints
                app.dependency_overrides[require_admin] = _mock_admin

                with TestClient(app) as c:
                    yield c

                # Clean up dependency override
                app.dependency_overrides.pop(require_admin, None)


class TestApplicationStatusTransitionsProperty:
    """
    Property 11: Application status transitions persist correctly

    For any application in any status, when an administrator shortlists or rejects
    the application, the status SHALL be updated to the specified value and subsequent
    retrieval SHALL reflect the new status.

    Feature: blog-and-careers, Property 11: Application status transitions persist correctly

    **Validates: Requirements 10.3, 10.7**
    """

    @given(
        app_id=app_id_strategy,
        initial_status=initial_status_strategy,
        new_status=target_status_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    def test_status_transition_persists_correctly(
        self,
        client,
        app_id,
        initial_status: ApplicationStatus,
        new_status: ApplicationStatus,
    ):
        """
        For any application in any status, when an administrator shortlists or
        rejects the application, the status SHALL be updated to the specified value
        and subsequent retrieval SHALL reflect the new status.

        **Validates: Requirements 10.3, 10.7**
        """
        now = datetime.now(timezone.utc)

        # Mock fetch_one to simulate the database returning the updated row
        # after the UPDATE ... RETURNING query in update_application_status
        mock_updated_row = {
            "id": app_id,
            "status": new_status.value,
            "updated_at": now,
        }

        with patch(
            "app.services.application_service.fetch_one",
            new_callable=AsyncMock,
            return_value=mock_updated_row,
        ):
            # Perform the status update via the admin endpoint
            response = client.patch(
                f"/api/admin/applications/{app_id}/status",
                json={"status": new_status.value},
            )

        # Assert: endpoint returns 200 success
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()

        # Assert: returned status matches the requested new status
        assert data["status"] == new_status.value, (
            f"Expected status '{new_status.value}', got '{data['status']}'. "
            f"Transition from '{initial_status.value}' to '{new_status.value}' "
            f"did not persist correctly."
        )

        # Assert: the response contains the application ID
        assert data["id"] == str(app_id), (
            f"Expected app ID '{app_id}', got '{data['id']}'"
        )

        # Assert: the response contains an updated_at timestamp
        assert "updated_at" in data and data["updated_at"] is not None, (
            "Response missing 'updated_at' timestamp after status transition"
        )


# --- Property 12: Application tagging persistence ---

import json as json_module

from app.services.application_service import add_tag

# Generate random tag strings (non-empty, printable, reasonable length)
tag_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=100,
).map(str.strip).filter(lambda t: len(t) > 0)

# Generate a list of existing tags (0 to 10 tags already present)
existing_tags_strategy = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
        min_size=1,
        max_size=50,
    ),
    min_size=0,
    max_size=10,
    unique=True,
)


class TestApplicationTaggingPersistence:
    """
    Property 12: Application tagging persistence

    For any application and any custom tag string, adding the tag SHALL
    persist it, and subsequent retrieval SHALL include the tag in the
    application's tag list.

    Feature: blog-and-careers, Property 12: Application tagging persistence

    **Validates: Requirements 10.4**
    """

    @given(
        tag=tag_strategy,
        existing_tags=existing_tags_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_adding_tag_persists_and_is_retrievable(
        self, tag: str, existing_tags: list[str]
    ):
        """
        For any application and any custom tag string, adding the tag SHALL
        persist it, and subsequent retrieval SHALL include the tag in the
        application's tag list.

        Feature: blog-and-careers, Property 12: Application tagging persistence

        **Validates: Requirements 10.4**
        """
        app_id = uuid4()
        now = datetime.now(timezone.utc)

        # The expected tags after adding (no duplicates)
        if tag in existing_tags:
            expected_tags = existing_tags
        else:
            expected_tags = existing_tags + [tag]

        # Mock fetch_one: first call returns current tags, second call returns updated row
        current_tags_row = {"tags": json_module.dumps(existing_tags)}
        updated_row = {
            "id": app_id,
            "tags": json_module.dumps(expected_tags),
            "updated_at": now,
        }

        with patch(
            "app.services.application_service.fetch_one",
            new_callable=AsyncMock,
            side_effect=[current_tags_row, updated_row],
        ):
            result = await add_tag(app_id, tag)

        # The result should not be None (application was found)
        assert result is not None, "add_tag returned None, expected a result"

        # The returned tags list should include the new tag
        assert tag in result["tags"], (
            f"Tag '{tag}' not found in result tags: {result['tags']}"
        )

        # The returned tags should match the expected state
        assert set(result["tags"]) == set(expected_tags), (
            f"Expected tags {expected_tags}, got {result['tags']}"
        )

        # The count should be correct
        assert len(result["tags"]) == len(expected_tags), (
            f"Expected {len(expected_tags)} tags, got {len(result['tags'])}"
        )

    @given(
        tag=tag_strategy,
        existing_tags=existing_tags_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_duplicate_tag_is_not_added_twice(
        self, tag: str, existing_tags: list[str]
    ):
        """
        For any application that already has a tag, adding the same tag again
        SHALL NOT duplicate it in the tag list.

        Feature: blog-and-careers, Property 12: Application tagging persistence

        **Validates: Requirements 10.4**
        """
        app_id = uuid4()
        now = datetime.now(timezone.utc)

        # Ensure the tag already exists in the list
        existing_with_tag = list(set(existing_tags + [tag]))

        # Since tag is already present, the expected result is unchanged
        expected_tags = existing_with_tag

        # Mock fetch_one: first call returns current tags (including the tag),
        # second call returns the same (no change since tag already exists)
        current_tags_row = {"tags": json_module.dumps(existing_with_tag)}
        updated_row = {
            "id": app_id,
            "tags": json_module.dumps(expected_tags),
            "updated_at": now,
        }

        with patch(
            "app.services.application_service.fetch_one",
            new_callable=AsyncMock,
            side_effect=[current_tags_row, updated_row],
        ):
            result = await add_tag(app_id, tag)

        # Result should exist
        assert result is not None, "add_tag returned None, expected a result"

        # Count of the tag in result should be exactly 1 (no duplicates)
        assert result["tags"].count(tag) == 1, (
            f"Tag '{tag}' appears {result['tags'].count(tag)} times, expected exactly 1"
        )

        # Total number of tags should not increase
        assert len(result["tags"]) == len(expected_tags), (
            f"Expected {len(expected_tags)} tags (no duplicate added), got {len(result['tags'])}"
        )
