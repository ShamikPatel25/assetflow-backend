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
    subject = f"Welcome to {tenant_name} - Complete Your Account Setup"
    message = (
        f"Hello,\n\n"
        f"An account has been created for you at {tenant_name}.\n\n"
        f"Please click the link below to set up your account and choose a password.\n"
        f"This link will expire in 1 hour.\n\n"
        f"Setup Link: {setup_url}\n\n"
        f"Thank you,\n"
        f"Platform Team"
    )
    
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
