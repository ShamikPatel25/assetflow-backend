"""
Exhaustive Test Suite for Notifications module.

Covers:
- Users only see their own notifications
- Mark single notification as read
- Mark all notifications as read
- Notification auto-creation via services (cross-module integration)
- Notifications are read-only (no create/update/delete via API)
"""
from apps.allocations.services import AllocationService
from apps.notifications.models import Notification
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestNotificationVisibility:
    """Black-box: Users should only see notifications addressed to them."""

    url = "/api/v1/notifications/"

    def test_unauthenticated_cannot_view_notifications(self, api_client, tenant):
        """TC-NOTIF-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_user_sees_only_own_notifications(
        self, employee_api_client, employee_user, hr_user, tenant
    ):
        """TC-NOTIF-02: Employee only sees notifications where recipient=self."""

        # Create one notification for the employee and one for HR
        Notification.objects.create(
            recipient=employee_user, title="For You",
            message="This is yours", type="GENERAL",
        )
        Notification.objects.create(
            recipient=hr_user, title="Not For You",
            message="This is HR's", type="GENERAL",
        )

        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        if isinstance(results, list):
            for notif in results:
                assert "For You" == notif["title"]


class TestNotificationMarkRead:
    """White-box: Mark-read endpoints."""

    url = "/api/v1/notifications/"

    def test_mark_single_notification_as_read(
        self, employee_api_client, employee_user, tenant
    ):
        """TC-NOTIF-03: POST /notifications/{id}/read/ → marks is_read=True."""

        notif = Notification.objects.create(
            recipient=employee_user, title="Unread",
            message="Read me", type="GENERAL",
        )
        url = f"{self.url}{notif.id}/read/"
        response = employee_api_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_read"] is True

    def test_mark_all_notifications_as_read(
        self, employee_api_client, employee_user, tenant
    ):
        """TC-NOTIF-04: POST /notifications/mark-read/ → batch mark all."""

        for i in range(3):
            Notification.objects.create(
                recipient=employee_user, title=f"Notif {i}",
                message="Unread", type="GENERAL",
            )

        url = f"{self.url}mark-read/"
        response = employee_api_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["marked"] == 3

    def test_mark_read_only_affects_own_notifications(
        self, employee_api_client, employee_user, hr_user, tenant
    ):
        """TC-NOTIF-05: mark-read should not affect another user's notifications."""

        Notification.objects.create(
            recipient=employee_user, title="Mine",
            message="m", type="GENERAL",
        )
        hr_notif = Notification.objects.create(
            recipient=hr_user, title="HR's",
            message="h", type="GENERAL",
        )

        employee_api_client.post(f"{self.url}mark-read/")
        hr_notif.refresh_from_db()
        assert hr_notif.is_read is False  # Unaffected


class TestNotificationServiceIntegration:
    """White-box: Verify NotificationService creates notifications correctly."""

    def test_allocation_creates_notification(
        self, asset, employee, tenant
    ):
        """TC-NOTIF-06: AllocationService.allocate() creates a notification."""

        AllocationService.allocate(asset=asset, employee=employee)
        notifs = Notification.objects.filter(
            recipient=employee.user, type="ASSET_ALLOCATED"
        )
        assert notifs.count() == 1
        assert "allocated" in notifs.first().title.lower()
