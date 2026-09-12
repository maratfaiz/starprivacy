"""Reply-keyboard button handlers for the persistent main menu.

Each button reuses the exact same text-building/logic as its slash-command
equivalent (see handlers/commands.py and handlers/subscription.py) so the
menu and the commands can never drift apart.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

import keyboards
from . import commands, subscription

router = Router(name="menu")


@router.message(F.text == keyboards.BTN_PROFILE)
async def show_profile(message: Message) -> None:
    await message.answer(await commands.build_status_text(message.from_user.id))


@router.message(F.text == keyboards.BTN_SUBSCRIBE)
async def show_subscribe(message: Message) -> None:
    await subscription.show_plans(message)


@router.message(F.text == keyboards.BTN_CONNECTIONS)
async def show_connections(message: Message) -> None:
    await message.answer(await commands.build_connections_text(message.from_user.id))


@router.message(F.text == keyboards.BTN_HELP)
async def show_help(message: Message) -> None:
    await message.answer(commands.HELP_TEXT)
