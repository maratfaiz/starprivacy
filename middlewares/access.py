"""Subscription / access-level helpers.

Kept separate from the handlers so the "who is allowed to have their
messages archived right now" rule lives in exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from database import db
from database.models import Subscription


@dataclass(frozen=True)
class AccessLevel:
    allowed: bool
    tier: str | None
    max_stored_days: int | None  # None = unlimited


async def get_access_level(user_id: int) -> AccessLevel:
    """Determine whether `user_id` (a Business account owner) currently has
    an active subscription, including the permanent free admin override.
    """
    if user_id in config.ADMIN_IDS:
        return AccessLevel(allowed=True, tier="admin", max_stored_days=None)

    sub: Subscription | None = await db.get_active_subscription(user_id)
    if sub is None:
        return AccessLevel(allowed=False, tier=None, max_stored_days=None)

    tariff = config.TARIFFS.get(sub.tier)
    max_days = tariff.max_stored_days if tariff else None
    return AccessLevel(allowed=True, tier=sub.tier, max_stored_days=max_days)
