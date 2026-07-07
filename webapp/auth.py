"""Validation for Telegram Mini App `initData`.

Implements the check described at
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app:
the payload is HMAC-signed with a key derived from the bot token, so only
Telegram itself (which generated it when the Mini App was opened) could have
produced a matching hash.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_INIT_DATA_AGE_SECONDS = 24 * 60 * 60


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Return the Telegram user dict encoded in `init_data`, or None if invalid/stale."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if time.time() - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    if "id" not in user:
        return None
    return user


def extract_init_data(request) -> str | None:
    """Pull initData out of the `Authorization: tma <initData>` header (Telegram's
    documented convention), falling back to an `X-Telegram-Init-Data` header.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("tma "):
        return auth_header[4:].strip()
    return request.headers.get("X-Telegram-Init-Data")
