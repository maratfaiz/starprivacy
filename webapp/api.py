"""JSON API backing the StarPrivacyBot Mini App.

Every route (except static assets) requires a valid Telegram Mini App
`initData` payload, sent as `Authorization: tma <initData>`. Ownership checks
(a connection/chat/message must belong to the authenticated Telegram user) are
enforced on every read - being an admin only affects the subscription
requirement, never who a person's archived data belongs to.
"""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import LabeledPrice
from aiohttp import web

import config
from database import db
from middlewares.access import get_access_level
from webapp.auth import extract_init_data, validate_init_data

logger = logging.getLogger(__name__)
routes = web.RouteTableDef()


def _bot(request: web.Request) -> Bot:
    return request.app["bot"]


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)

    init_data = extract_init_data(request)
    user = validate_init_data(init_data, config.BOT_TOKEN) if init_data else None
    if user is None:
        raise web.HTTPUnauthorized(reason="Invalid or missing Telegram initData")

    request["tg_user_id"] = int(user["id"])
    return await handler(request)


def _serialize_message(msg) -> dict:
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
        "sender_name": msg.sender_name,
        "content_type": msg.content_type,
        "text": msg.text,
        "caption": msg.caption,
        "has_media": bool(msg.media_local_path),
        "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
        "is_edited": msg.is_edited,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "previous_text": msg.previous_text,
        "is_deleted": msg.is_deleted,
        "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
    }


@routes.get("/api/me")
async def get_me(request: web.Request) -> web.Response:
    user_id = request["tg_user_id"]
    access = await get_access_level(user_id)
    sub = await db.get_active_subscription(user_id) if access.allowed and access.tier != "admin" else None
    connections = await db.get_connections_for_owner(user_id)
    return web.json_response(
        {
            "user_id": user_id,
            "is_admin": user_id in config.ADMIN_IDS,
            "tier": access.tier,
            "allowed": access.allowed,
            "max_stored_days": access.max_stored_days,
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
            "connections": [
                {"connection_id": c.connection_id, "is_enabled": c.is_enabled, "can_reply": c.can_reply}
                for c in connections
            ],
        }
    )


@routes.get("/api/tariffs")
async def get_tariffs(request: web.Request) -> web.Response:
    return web.json_response(
        [
            {
                "key": t.key,
                "title": t.title,
                "stars_price": t.stars_price,
                "duration_days": t.duration_days,
                "description": t.description,
            }
            for t in config.TARIFFS.values()
        ]
    )


@routes.post("/api/subscribe")
async def post_subscribe(request: web.Request) -> web.Response:
    user_id = request["tg_user_id"]
    if user_id in config.ADMIN_IDS:
        raise web.HTTPBadRequest(reason="Admin accounts do not need a subscription")

    body = await request.json()
    tariff = config.TARIFFS.get(body.get("tariff", ""))
    if tariff is None:
        raise web.HTTPBadRequest(reason="Unknown tariff")

    bot = _bot(request)
    invoice_url = await bot.create_invoice_link(
        title=f"StarPrivacyBot — тариф «{tariff.title}»",
        description=tariff.description,
        payload=f"subscription:{tariff.key}",
        currency=config.STARS_CURRENCY,
        prices=[LabeledPrice(label=f"{tariff.title} (30 дней)", amount=tariff.stars_price)],
    )
    return web.json_response({"invoice_url": invoice_url})


async def _owned_connection(request: web.Request, connection_id: str):
    connection = await db.get_business_connection(connection_id)
    if connection is None or connection.owner_id != request["tg_user_id"]:
        raise web.HTTPNotFound(reason="Unknown connection")
    return connection


@routes.get("/api/connections/{connection_id}/chats")
async def get_chats(request: web.Request) -> web.Response:
    connection = await _owned_connection(request, request.match_info["connection_id"])
    chats = await db.get_chats_for_connection(connection.connection_id)
    for chat in chats:
        if chat["last_sent_at"] is not None:
            chat["last_sent_at"] = chat["last_sent_at"].isoformat()
    return web.json_response(chats)


@routes.get("/api/connections/{connection_id}/chats/{chat_id}/messages")
async def get_messages(request: web.Request) -> web.Response:
    connection = await _owned_connection(request, request.match_info["connection_id"])
    chat_id = int(request.match_info["chat_id"])
    before_id = request.query.get("before_id")
    limit = min(int(request.query.get("limit", 50)), 100)

    messages = await db.get_messages_for_chat(
        connection.connection_id, chat_id, before_id=int(before_id) if before_id else None, limit=limit
    )
    return web.json_response([_serialize_message(m) for m in messages])


@routes.get("/api/media/{message_id}")
async def get_media(request: web.Request) -> web.StreamResponse:
    message_id = int(request.match_info["message_id"])
    msg = await db.get_saved_message_by_id(message_id)
    if msg is None or not msg.media_local_path:
        raise web.HTTPNotFound()

    connection = await db.get_business_connection(msg.connection_id)
    if connection is None or connection.owner_id != request["tg_user_id"]:
        raise web.HTTPNotFound()

    path = Path(msg.media_local_path)
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)
