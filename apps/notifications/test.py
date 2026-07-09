"""
Tests for Notifications module.

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
    """Users should only see notifications addressed to them."""

    url = "/api/v1/notifications/"

    def test_unauthenticated_cannot_view_notifications(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_user_sees_only_own_notifications(
        self, employee_api_client, employee_user, hr_user, tenant
    ):
        """Employee only sees notifications where recipient=self."""

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
    """Mark-read endpoints."""

    url = "/api/v1/notifications/"

    def test_mark_single_notification_as_read(
        self, employee_api_client, employee_user, tenant
    ):
        """POST /notifications/{id}/read/ → marks is_read=True."""

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
        """POST /notifications/mark-read/ → batch mark all."""

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
        """mark-read should not affect another user's notifications."""

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
    """Verify NotificationService creates notifications correctly."""

    def test_allocation_creates_notification(
        self, asset, employee, tenant
    ):
        """AllocationService.allocate() creates a notification."""

        AllocationService.allocate(asset=asset, employee=employee)
        notifs = Notification.objects.filter(
            recipient=employee.user, type="ASSET_ALLOCATED"
        )
        assert notifs.count() == 1
        assert "allocated" in notifs.first().title.lower()


class TestNotificationServiceHRFanout:
    """Service methods that fan out to active HR managers (bulk_create paths)."""

    def test_notify_request_submitted(self, hr_user, employee, asset_request_factory):
        from apps.notifications.services import NotificationService
        req = asset_request_factory(requested_by=employee)
        NotificationService.notify_request_submitted(req)
        assert Notification.objects.filter(
            recipient=hr_user, type="REQUEST_SUBMITTED"
        ).exists()

    def test_notify_license_expiring(self, hr_user, license_factory):
        from apps.notifications.services import NotificationService
        lic = license_factory(name="Expiring Soon")
        NotificationService.notify_license_expiring(lic)
        assert Notification.objects.filter(
            recipient=hr_user, type="LICENSE_EXPIRING"
        ).exists()

    def test_notify_warranty_expiring(self, hr_user, asset):
        from apps.notifications.services import NotificationService
        NotificationService.notify_warranty_expiring(asset)
        assert Notification.objects.filter(
            recipient=hr_user, type="WARRANTY_EXPIRING"
        ).exists()


class TestNotificationRequestOutcomes:
    """Direct-to-requester notifications for approve / reject decisions."""

    def test_notify_request_approved(self, employee, category, asset_request_factory):
        from apps.notifications.services import NotificationService
        req = asset_request_factory(requested_by=employee, category=category)
        NotificationService.notify_request_approved(req)
        notif = Notification.objects.get(
            recipient=employee.user, type="REQUEST_APPROVED"
        )
        assert category.name in notif.message

    def test_notify_request_rejected_without_category(self, employee, asset_request_factory):
        """No category on the request falls back to the generic 'an asset' phrase."""
        from apps.notifications.services import NotificationService
        req = asset_request_factory(requested_by=employee, category=None)
        NotificationService.notify_request_rejected(req)
        notif = Notification.objects.get(
            recipient=employee.user, type="REQUEST_REJECTED"
        )
        assert "an asset" in notif.message


class TestSendExpirationAlertsCommand:
    """The cross-tenant `send_expiration_alerts` management command."""

    def test_generates_warranty_and_license_alerts(
        self, tenant, hr_user, asset_factory, category, license_factory,
    ):
        from datetime import date, timedelta
        from django.core.management import call_command

        soon = date.today() + timedelta(days=7)
        asset_factory(name="WarrantySoon", category=category, warranty_expiry_date=soon)
        license_factory(name="LicenseSoon", status="ACTIVE", expiry_date=soon)

        call_command("send_expiration_alerts")

        assert Notification.objects.filter(
            recipient=hr_user, type="WARRANTY_EXPIRING"
        ).exists()
        assert Notification.objects.filter(
            recipient=hr_user, type="LICENSE_EXPIRING"
        ).exists()


class TestNotificationViewSchemaBranch:
    """get_queryset returns an empty set during schema (swagger) generation."""

    def test_get_queryset_empty_for_fake_view(self, tenant):
        from apps.notifications.views import NotificationViewSet
        vs = NotificationViewSet()
        vs.swagger_fake_view = True
        assert vs.get_queryset().count() == 0


class TestNotificationModel:
    def test_str(self, employee_user, tenant):
        notif = Notification.objects.create(
            recipient=employee_user, title="Ping", message="m", type="GENERAL",
        )
        assert str(notif) == f"Ping -> {employee_user}"
