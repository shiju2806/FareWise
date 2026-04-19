"""Tenant resolution helper — single place to extract company_id from a user.

All tenant-scoped queries must filter by the value returned here. Keeping the
lookup in one function makes it easy to swap in a richer resolver later
(impersonation, service accounts, etc.) without touching call sites.
"""

import uuid

from app.models.user import User


class TenantError(Exception):
    """Raised when a request cannot be associated with a tenant."""


def get_company_id(user: User) -> uuid.UUID:
    if user.company_id is None:
        raise TenantError(f"user {user.id} has no company_id")
    return user.company_id
