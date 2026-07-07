"""General bot commands: /start, /help, /status."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import config
from database import db
from middlewares.access import get_access_level

router = Router(name="commands")

WELCOME_TEXT = (
    "👋 <b>StarPrivacyBot</b>\n\n"
    "This bot connects to your Telegram <b>Business account</b> and keeps a private "
    "backup of messages sent to you, so you can still see them if the sender "
    "edits or deletes them.\n\n"
    "<b>How to connect:</b>\n"
    "1. Telegram Settings → Business → Chatbots\n"
    "2. Choose this bot and enable it for the chats you want\n"
    "3. Send /subscribe to activate a plan (nothing is recorded before you do)\n\n"
    "⚠️ <b>Privacy notice:</b> only enable this for chats where you have the "
    "right to keep records of the conversation. See the project README for "
    "the full disclaimer.\n\n"
    "Commands: /help /status /subscribe"
)

HELP_TEXT = (
    "<b>Commands</b>\n"
    "/start — welcome message and setup instructions\n"
    "/status — your subscription and business connection status\n"
    "/subscribe — view plans and pay with Telegram Stars\n"
    "/help — this message"
)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user_id = message.from_user.id
    access = await get_access_level(user_id)
    connections = await db.get_connections_for_owner(user_id)

    if access.tier == "admin":
        plan_line = "Plan: <b>Admin (lifetime free)</b>"
    elif access.allowed:
        retention = "unlimited" if access.max_stored_days is None else f"{access.max_stored_days} days"
        plan_line = f"Plan: <b>{access.tier.title()}</b> (history retention: {retention})"
    else:
        plan_line = "Plan: <b>none</b> — use /subscribe to activate archiving"

    if connections:
        active = [c for c in connections if c.is_enabled]
        conn_line = f"Business connections: {len(active)} active / {len(connections)} total"
    else:
        conn_line = "Business connections: none yet — connect this bot in Telegram Business settings"

    await message.answer(f"{plan_line}\n{conn_line}")
