from apps.audit.models import AuditLog


def log_action(user=None, action="", module="", object_type="",
               object_id=None, object_repr=None, old_data=None,
               new_data=None, request=None):
    """Create an audit log entry."""
    ip_address = None
    user_agent = None
    request_id = None

    if request:
        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        request_id = request.META.get("HTTP_X_REQUEST_ID", "")

    AuditLog.objects.create(
        actor_user=user,
        actor_email=getattr(user, "email", None),
        action=action,
        module=module,
        object_type=object_type,
        object_id=str(object_id) if object_id else None,
        object_repr=str(object_repr)[:300] if object_repr else None,
        old_data=old_data,
        new_data=new_data,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


def _get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
