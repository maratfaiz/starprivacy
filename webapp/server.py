"""aiohttp web server hosting the Mini App's static frontend and JSON API.

Runs as a background asyncio task alongside the bot's long-polling loop (see
main.py) - same process, same database, no separate deployment needed beyond
a reverse proxy for TLS.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot
from aiohttp import web

import config
from webapp.api import auth_middleware, routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def build_web_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app["bot"] = bot
    app.add_routes(routes)
    app.router.add_static("/", STATIC_DIR, show_index=False, name="static")
    return app


async def run_webapp(bot: Bot) -> None:
    app = build_web_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
    await site.start()
    logger.info("Mini App web server listening on %s:%s", config.WEBAPP_HOST, config.WEBAPP_PORT)
    try:
        # Runs until cancelled by main() when the bot shuts down.
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
