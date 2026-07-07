"""Central configuration for StarPrivacyBot.

All secrets and environment-specific values are read from the process
environment (optionally loaded from a local .env file via python-dotenv).
Nothing sensitive is hardcoded except the single lifetime-admin Telegram ID,
which is a deliberate product requirement, not a secret.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _parse_id_set(raw: str) -> frozenset[int]:
    ids = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            ids.add(int(chunk))
    return frozenset(ids)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is required but not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


BOT_TOKEN: str = _require_env("BOT_TOKEN")

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/starprivacy.db")
MEDIA_STORAGE_PATH: str = os.getenv("MEDIA_STORAGE_PATH", "./data/media")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# The Telegram user ID that always gets the full feature set for free, forever.
# This is a product decision (project owner / permanent admin), not a secret.
LIFETIME_FREE_ADMIN_ID: int = 1283428247

ADMIN_IDS: frozenset[int] = frozenset({LIFETIME_FREE_ADMIN_ID}) | _parse_id_set(
    os.getenv("EXTRA_ADMIN_IDS", "")
)

# Telegram Stars payments use the special currency code "XTR" and require no
# payment provider token - Telegram itself settles the Stars transaction.
STARS_CURRENCY = "XTR"


@dataclass(frozen=True)
class Tariff:
    key: str
    title: str
    stars_price: int
    duration_days: int
    max_stored_days: int | None  # None = unlimited retention
    description: str


TARIFFS: dict[str, Tariff] = {
    "basic": Tariff(
        key="basic",
        title="Basic",
        stars_price=100,
        duration_days=30,
        max_stored_days=14,
        description=(
            "Archives text + media from your connected Business chats, "
            "edit/delete alerts, 14 days of history."
        ),
    ),
    "premium": Tariff(
        key="premium",
        title="Premium",
        stars_price=250,
        duration_days=30,
        max_stored_days=None,
        description=(
            "Everything in Basic plus unlimited history retention and "
            "priority media downloads."
        ),
    ),
}


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
