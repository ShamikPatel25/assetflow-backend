import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable audit trail for tenant-level actions.
    No soft delete. No update. Append-only.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_user = models.ForeignKey(
        "employees.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    actor_email = models.EmailField(null=True, blank=True)
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=50)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, null=True, blank=True)
    object_repr = models.CharField(max_length=300, null=True, blank=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    request_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor_user"], name="idx_audit_actor"),
            models.Index(fields=["action"], name="idx_audit_action"),
            models.Index(fields=["module"], name="idx_audit_module"),
            models.Index(fields=["object_type"], name="idx_audit_obj_type"),
            models.Index(fields=["object_id"], name="idx_audit_obj_id"),
            models.Index(fields=["created_at"], name="idx_audit_created"),
            models.Index(fields=["actor_user", "created_at"], name="idx_audit_user_time"),
            models.Index(fields=["module", "created_at"], name="idx_audit_mod_time"),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor_email} at {self.created_at}"
