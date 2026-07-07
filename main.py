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
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database.db import init_db
from handlers import build_root_router

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

    logger.info("Starting StarPrivacyBot polling loop")
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dispatcher.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("StarPrivacyBot stopped")
