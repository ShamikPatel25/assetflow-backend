import jwt
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail

def send_invitation_email(user, tenant_name, domain_name):
    """
    Generates a 1-hour JWT invitation token and sends a setup email to the user.
    """
    payload = {
        "user_id": str(user.id),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "type": "invitation"
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    setup_url = f"http://{domain_name}:3000/setup-account?token={token}"
    subject = f"You're Invited to Join {tenant_name}"
    try:
        first_name = user.employee_profile.first_name
    except Exception:
        first_name = "there"
    message = (
        f"Hello {first_name},\n\n"
        f"You have been invited to join {tenant_name}’s asset management system.\n\n"
        f"To activate your account, please complete your profile and create your password using the secure link below:\n\n"
        f"{setup_url}\n\n"
        f"For security reasons, this invitation link will expire in 1 hour.\n\n"
        f"If you did not request this invitation or need a new link, please contact your organization administrator.\n\n"
        f"Regards,\n"
        f"{tenant_name} Team"
    )
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
