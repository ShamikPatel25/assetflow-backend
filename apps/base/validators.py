"""
Shared field-level validators for AssetFlow serializers.

Import and assign directly as a class attribute to avoid repeating the
same validation logic across multiple serializers:

    from apps.base.validators import validate_phone_number, validate_email_format

    class MySerializer(serializers.ModelSerializer):
        validate_phone = validate_phone_number       # ← one line, done
        validate_email = validate_email_format        # ← same pattern
"""

from rest_framework import serializers


def validate_phone_number(value):
    """
    Validate a phone number field.
    - Must contain digits only.
    - Must be 10–15 characters long.
    - Empty / None values are passed through unchanged.
    """
    if not value:
        return value
    if not value.isdigit():
        raise serializers.ValidationError("Only numbers are allowed.")
    if not (10 <= len(value) <= 15):
        raise serializers.ValidationError("10-15 digits only allowed.")
    return value


def validate_email_format(value):
    """
    Validate that an email address is lowercase and space-free.
    Intended for use alongside DRF's built-in EmailField validation.
    """
    if " " in value:
        raise serializers.ValidationError("Email cannot contain spaces.")
    if any(char.isupper() for char in value):
        raise serializers.ValidationError("Email must be in lowercase.")
    return value
