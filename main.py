"""StarPrivacyBot entry point.

Educational reference implementation of a Telegram bot built on the official
Bot API "Business" features (Bot API 7.2+): it archives incoming messages
from a connected Business account so the owner can still see them if the
sender edits or deletes them, and gates that feature behind a Telegram Stars
subscription.

Run with: python main.py
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
from database.db import init_db
from handlers import build_root_router
from webapp.server import run_webapp

logger = logging.getLogger(__name__)

# All update types the bot needs delivered, including the Business API ones.
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "pre_checkout_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


async def main() -> None:
    config.setup_logging()
    await init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_root_router())

    logger.info("Starting StarPrivacyBot polling loop and Mini App web server")
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начало работы и инструкция"),
            BotCommand(command="menu", description="Показать главное меню"),
            BotCommand(command="status", description="Профиль и тариф"),
            BotCommand(command="subscribe", description="Оформить подписку"),
            BotCommand(command="help", description="Справка"),
        ]
    )
    webapp_task = asyncio.create_task(run_webapp(bot))
    try:
        await dispatcher.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
    finally:
        webapp_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await webapp_task
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("StarPrivacyBot stopped")
