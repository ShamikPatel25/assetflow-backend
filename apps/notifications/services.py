from apps.notifications.models import Notification
from apps.employees.models import TenantUser


class NotificationService:
    """Service to handle creation of automated notifications."""

    @staticmethod
    def _get_hr_managers():
        """Helper to fetch all active HR Managers."""
        return list(TenantUser.objects.filter(
            role=TenantUser.Role.HR_MANAGER,
            is_active=True
        ))

    @staticmethod
    def _bulk_notify_hr(title, message, notification_type, payload=None):
        """
        Create one Notification for every active HR Manager.

        Shared skeleton used by all HR-broadcast notify_* methods to avoid
        repeating the get_hr_managers → loop → bulk_create pattern.
        """
        hr_managers = NotificationService._get_hr_managers()
        notifications = [
            Notification(
                recipient=hr,
                title=title,
                message=message,
                type=notification_type,
                payload=payload or {},
            )
            for hr in hr_managers
        ]
        if notifications:
            Notification.objects.bulk_create(notifications)

    # ── Employee-direct notifications (single Notification.objects.create) ──

    @staticmethod
    def notify_asset_allocated(allocation):
        """Notify the employee that an asset has been allocated to them."""
        recipient = allocation.employee.user
        Notification.objects.create(
            recipient=recipient,
            title="New Asset Allocated",
            message=f"You have been allocated a new asset: {allocation.asset.name}.",
            type=Notification.Type.ASSET_ALLOCATED,
            payload={
                "allocation_id": str(allocation.id),
                "asset_id": str(allocation.asset.id)
            }
        )

    @staticmethod
    def notify_request_approved(request_obj):
        """Notify the employee that their request was approved."""
        recipient = request_obj.requested_by.user
        Notification.objects.create(
            recipient=recipient,
            title="Asset Request Approved",
            message=f"Your request for {request_obj.category.name if request_obj.category else 'an asset'} has been approved.",
            type=Notification.Type.REQUEST_APPROVED,
            payload={"request_id": str(request_obj.id)}
        )

    @staticmethod
    def notify_request_rejected(request_obj):
        """Notify the employee that their request was rejected."""
        recipient = request_obj.requested_by.user
        Notification.objects.create(
            recipient=recipient,
            title="Asset Request Rejected",
            message=f"Your request for {request_obj.category.name if request_obj.category else 'an asset'} has been rejected.",
            type=Notification.Type.REQUEST_REJECTED,
            payload={"request_id": str(request_obj.id)}
        )

    @staticmethod
    def notify_incident_updated(incident):
        """Notify the employee that their incident was updated (resolved/closed)."""
        recipient = incident.reported_by.user
        subject = incident.asset.name if incident.asset else incident.incident_number
        Notification.objects.create(
            recipient=recipient,
            title=f"Incident {incident.status.title()}",
            message=f"Your incident for {subject} is now {incident.status.title()}.",
            type=Notification.Type.INCIDENT_UPDATED,
            payload={
                "incident_id": str(incident.id),
                "asset_id": str(incident.asset.id) if incident.asset else None,
            }
        )

    # ── HR-broadcast notifications (use _bulk_notify_hr) ──────────────────

    @staticmethod
    def notify_asset_returned(allocation):
        """Notify HR Managers that an employee has returned an asset."""
        NotificationService._bulk_notify_hr(
            title="Asset Returned",
            message=f"Employee {allocation.employee.get_full_name()} has returned asset: {allocation.asset.name}.",
            notification_type=Notification.Type.ASSET_RETURNED,
            payload={
                "allocation_id": str(allocation.id),
                "asset_id": str(allocation.asset.id),
            },
        )

    @staticmethod
    def notify_request_submitted(request_obj):
        """Notify HR Managers that a new asset request was submitted."""
        NotificationService._bulk_notify_hr(
            title="New Asset Request",
            message=f"Employee {request_obj.requested_by.get_full_name()} has requested a new asset.",
            notification_type=Notification.Type.REQUEST_SUBMITTED,
            payload={"request_id": str(request_obj.id)},
        )

    @staticmethod
    def notify_incident_reported(incident):
        """Notify HR Managers that a new incident was reported."""
        asset_phrase = (
            f"for asset: {incident.asset.name}" if incident.asset else "(no asset linked)"
        )
        NotificationService._bulk_notify_hr(
            title="New Incident Reported",
            message=f"Employee {incident.reported_by.get_full_name()} reported an incident {asset_phrase}: {incident.title}.",
            notification_type=Notification.Type.INCIDENT_REPORTED,
            payload={
                "incident_id": str(incident.id),
                "asset_id": str(incident.asset.id) if incident.asset else None,
            },
        )

    @staticmethod
    def notify_license_expiring(license_obj):
        """Notify HR Managers that a license is expiring soon."""
        NotificationService._bulk_notify_hr(
            title="License Expiring",
            message=f"The license for {license_obj.name} expires on {license_obj.expiry_date}. Please renew it before it stops working.",
            notification_type=Notification.Type.LICENSE_EXPIRING,
            payload={"license_id": str(license_obj.id)},
        )

    @staticmethod
    def notify_license_expired(license_obj):
        """Notify HR Managers daily that a license has already expired and is not working."""
        NotificationService._bulk_notify_hr(
            title="License Expired — Action Required",
            message=f"The license for {license_obj.name} expired on {license_obj.expiry_date}. Software may have stopped working. Please renew immediately.",
            notification_type=Notification.Type.LICENSE_EXPIRED,
            payload={"license_id": str(license_obj.id)},
        )

    @staticmethod
    def notify_warranty_expiring(asset):
        """Notify HR Managers that an asset warranty is expiring."""
        NotificationService._bulk_notify_hr(
            title="Warranty Expiring",
            message=f"The warranty for asset {asset.name} expires on {asset.warranty_expiry_date}.",
            notification_type=Notification.Type.WARRANTY_EXPIRING,
            payload={"asset_id": str(asset.id)},
        )

    @staticmethod
    def notify_warranty_expired(asset):
        """Notify HR Managers that an asset warranty has already expired."""
        NotificationService._bulk_notify_hr(
            title="Warranty Expired",
            message=f"The warranty for asset {asset.name} expired on {asset.warranty_expiry_date}. Please renew or take necessary action.",
            notification_type=Notification.Type.WARRANTY_EXPIRED,
            payload={"asset_id": str(asset.id)},
        )
