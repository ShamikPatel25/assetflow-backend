"""
Shared service utilities for AssetFlow.

Thin helpers that are called from multiple apps and do not belong to any
single domain.
"""

import uuid


def generate_reference_number(prefix: str) -> str:
    """
    Generate a unique, human-readable reference number.

    Format: ``<PREFIX>-<8 hex chars uppercase>``
    Example: ``ALLOC-3F9A2B1C``

    Args:
        prefix: The prefix string (e.g. ``ReferencePrefix.ALLOCATION``).

    Returns:
        A unique reference number string.
    """
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def get_primary_domain(tenant, fallback: str = "localhost") -> str:
    """
    Return the primary domain hostname for *tenant*.

    Replaces the repeated idiom::

        domain_obj = tenant.domains.filter(is_primary=True).first()
        domain_name = domain_obj.domain if domain_obj else "localhost"

    Args:
        tenant: A django-tenants Organization (or any model with a
                ``domains`` reverse relation where each domain has a
                ``domain`` string field and ``is_primary`` boolean).
        fallback: Value returned when no primary domain is found.

    Returns:
        The ``domain`` string of the primary domain, or *fallback*.
    """
    domain_obj = tenant.domains.filter(is_primary=True).first()
    return domain_obj.domain if domain_obj else fallback
