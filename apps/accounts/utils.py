import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.core.mail import send_mail

def send_invitation_email(user, tenant_name, domain_name):
    """
    Generates a 1-hour JWT invitation token and sends a setup email to the user.
    """
    payload = {
        "user_id": str(user.id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "invitation"
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    setup_url = f"{settings.FRONTEND_BASE_URL}/setup-account?token={token}"
    subject = f"You're Invited to Join {tenant_name}"
    
    first_name = getattr(user, 'first_name', '')
    if not first_name:
        greeting = "Hello, Sir/Ma'am,"
    else:
        greeting = f"Hello {first_name},"

    text_message = (
        f"{greeting}\n\n"
        f"You have been invited to join {tenant_name}’s asset management system.\n\n"
        f"To activate your account, please complete your profile and create your password using the secure link below:\n\n"
        f"{setup_url}\n\n"
        f"For security reasons, this invitation link will expire in 1 hour.\n\n"
        f"If you did not request this invitation or need a new link, please contact your organization administrator.\n\n"
        f"Regards,\n"
        f"{tenant_name} Team"
    )

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #333333;">
        <p>{greeting}</p>
        <p>You have been invited to join <strong>{tenant_name}</strong>’s asset management system.</p>
        <p>To activate your account, please complete your profile and create your password using the secure link below:</p>
        <p>
            <a href="{setup_url}" style="display: inline-block; padding: 12px 24px; color: #ffffff; background-color: #2563eb; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0;">
                Activate Account
            </a>
        </p>
        <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #6b7280; font-size: 14px;"><small>{setup_url}</small></p>
        <p>For security reasons, this invitation link will expire in 1 hour.</p>
        <p>If you did not request this invitation or need a new link, please contact your organization administrator.</p>
        <br>
        <p>Regards,<br><strong>{tenant_name} Team</strong></p>
    </body>
    </html>
    """
    
    # Dynamically set the sender name to the Organization's name
    from_email = f"{tenant_name} Team <{settings.DEFAULT_FROM_EMAIL}>"

    send_mail(
        subject=subject,
        message=text_message,
        html_message=html_message,
        from_email=from_email,
        recipient_list=[user.email],
        fail_silently=False,
    )

def send_password_reset_email(user, tenant_name, domain_name):
    """
    Generates a 1-hour JWT password reset token and sends an email to the user.
    Includes a slice of the user's password hash so the token is single-use.
    """
    # Use first 20 chars of password hash to invalidate token on password change
    pass_hash = user.password[-20:] if user.password else ""
    
    payload = {
        "user_id": str(user.id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "type": "password_reset",
        "hash": pass_hash
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
    subject = f"Password Reset Request - {tenant_name}"
    
    first_name = getattr(user, 'first_name', '')
    if not first_name:
        greeting = "Hello,"
    else:
        greeting = f"Hello {first_name},"

    text_message = (
        f"{greeting}\n\n"
        f"We received a request to reset your password for {tenant_name}.\n\n"
        f"Click the link below to securely reset your password:\n\n"
        f"{reset_url}\n\n"
        f"This link will expire in 1 hour.\n\n"
        f"If you did not request this reset, please ignore this email or contact your administrator.\n\n"
        f"Regards,\n"
        f"{tenant_name} Team"
    )

    html_message = f"""
    <html>
    <body style="font-family: Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #333333;">
        <p>{greeting}</p>
        <p>We received a request to reset your password for <strong>{tenant_name}</strong>.</p>
        <p>Click the link below to securely reset your password:</p>
        <p>
            <a href="{reset_url}" style="display: inline-block; padding: 12px 24px; color: #ffffff; background-color: #2563eb; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0;">
                Reset Password
            </a>
        </p>
        <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #6b7280; font-size: 14px;"><small>{reset_url}</small></p>
        <p>For security reasons, this link will expire in 1 hour.</p>
        <p>If you did not request this reset, please ignore this email or contact your administrator.</p>
        <br>
        <p>Regards,<br><strong>{tenant_name} Team</strong></p>
    </body>
    </html>
    """
    
    from_email = f"{tenant_name} Team <{settings.DEFAULT_FROM_EMAIL}>"

    send_mail(
        subject=subject,
        message=text_message,
        html_message=html_message,
        from_email=from_email,
        recipient_list=[user.email],
        fail_silently=False,
    )
