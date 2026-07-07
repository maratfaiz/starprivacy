"""Admin-only commands, restricted to config.ADMIN_IDS."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import config
from database import db

router = Router(name="admin")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in config.ADMIN_IDS:
        return  # silently ignore for non-admins, don't reveal the command exists

    stats = await db.get_stats()
    await message.answer(
        "<b>StarPrivacyBot stats</b>\n"
        f"Users: {stats['users']}\n"
        f"Business connections: {stats['active_connections']} active / {stats['connections']} total\n"
        f"Active subscriptions: {stats['active_subscriptions']}\n"
        f"Saved messages: {stats['messages']}"
    )
