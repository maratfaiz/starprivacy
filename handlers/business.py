"""Core StarPrivacyBot feature: archiving Telegram Business messages and
alerting the business owner about edits/deletions.

Everything here only ever touches messages that:
  * arrived through an active Business connection (never secret chats -
    Telegram's Business API does not deliver secret-chat messages at all,
    so that exclusion is enforced by Telegram itself), and
  * were sent *to* the business account (i.e. incoming, from the customer),
    never messages the owner sent themselves, and
  * arrived after the connection was enabled and the owner had a usable
    subscription - nothing is ever backfilled or captured retroactively.
"""
from __future__ import annotations

import datetime as dt
import logging

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from database import db
from middlewares.access import get_access_level
from utils.media import download_media, extract_media_ref

logger = logging.getLogger(__name__)
router = Router(name="business")


def _display_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Unknown"
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


@router.business_connection()
async def on_business_connection(connection: BusinessConnection, bot: Bot) -> None:
    await db.upsert_business_connection(
        connection_id=connection.id,
        owner_id=connection.user.id,
        is_enabled=connection.is_enabled,
        can_reply=connection.can_reply,
    )

    status = "подключено ✅" if connection.is_enabled else "отключено ⛔"
    try:
        await bot.send_message(
            connection.user.id,
            f"Бизнес-подключение: {status}.\n"
            + (
                "Новые входящие сообщения теперь будут архивироваться. "
                "Проверить тариф — /status."
                if connection.is_enabled
                else "Архивирование для этого подключения приостановлено."
            ),
        )
    except Exception:
        # The owner may not have started a private chat with the bot yet - non-fatal.
        logger.info("Could not notify owner %s about connection change", connection.user.id)


@router.business_message()
async def on_business_message(message: Message, bot: Bot) -> None:
    connection_id = message.business_connection_id
    if connection_id is None:
        return

    connection = await db.get_business_connection(connection_id)
    if connection is None or not connection.is_enabled:
        return  # Unknown or disabled connection - never store anything.

    owner_id = connection.owner_id
    if message.from_user and message.from_user.id == owner_id:
        return  # Outgoing message sent by the business owner themselves - not "incoming".

    access = await get_access_level(owner_id)
    if not access.allowed:
        return  # No active subscription (and not admin) - do not record anything.

    media_ref = extract_media_ref(message)
    content_type = media_ref[0] if media_ref else "text"
    media_local_path = None
    media_file_id = None
    if media_ref is not None:
        content_type, media_file_id = media_ref
        media_local_path = await download_media(
            bot, connection_id, message.chat.id, message.message_id, content_type, media_file_id
        )

    await db.save_message(
        connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=message.from_user.id if message.from_user else None,
        sender_name=_display_name(message),
        is_from_business_owner=False,
        content_type=content_type,
        text=message.text,
        caption=message.caption,
        media_file_id=media_file_id,
        media_local_path=media_local_path,
        sent_at=message.date,
    )

    if access.max_stored_days is not None:
        await db.purge_expired_messages(connection_id, access.max_stored_days)


@router.edited_business_message()
async def on_edited_business_message(message: Message, bot: Bot) -> None:
    connection_id = message.business_connection_id
    if connection_id is None:
        return

    connection = await db.get_business_connection(connection_id)
    if connection is None:
        return

    original = await db.get_message(connection_id, message.chat.id, message.message_id)
    if original is None or original.is_from_business_owner:
        return  # We never archived this one (no subscription at the time, or it was outgoing).

    new_text = message.text or message.caption
    previous_text = original.text or original.caption
    await db.mark_message_edited(connection_id, message.chat.id, message.message_id, previous_text, new_text)

    when = message.edit_date or dt.datetime.now(dt.timezone.utc)
    await bot.send_message(
        connection.owner_id,
        (
            f"✏️ <b>Сообщение отредактировано</b> ({original.sender_name}, {when:%d.%m.%Y %H:%M} UTC)\n\n"
            f"<b>Было:</b>\n{previous_text or '<i>[без текста]</i>'}\n\n"
            f"<b>Стало:</b>\n{new_text or '<i>[без текста]</i>'}"
        ),
    )


@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted, bot: Bot) -> None:
    connection = await db.get_business_connection(event.business_connection_id)
    if connection is None:
        return

    deleted = await db.mark_messages_deleted(
        event.business_connection_id, event.chat.id, list(event.message_ids)
    )

    for msg in deleted:
        if msg.is_from_business_owner:
            continue  # Only alert about the customer's own messages disappearing.

        body = msg.text or msg.caption or "<i>[без текста]</i>"
        header = (
            f"🗑️ <b>Сообщение удалено</b> ({msg.sender_name}, отправлено {msg.sent_at:%d.%m.%Y %H:%M} UTC)"
        )
        try:
            if msg.media_local_path and msg.content_type == "photo":
                from aiogram.types import FSInputFile

                await bot.send_photo(
                    connection.owner_id, FSInputFile(msg.media_local_path), caption=f"{header}\n\n{body}"
                )
            elif msg.media_local_path:
                from aiogram.types import FSInputFile

                await bot.send_document(
                    connection.owner_id, FSInputFile(msg.media_local_path), caption=f"{header}\n\n{body}"
                )
            else:
                await bot.send_message(connection.owner_id, f"{header}\n\n{body}")
        except Exception:
            logger.exception("Failed to notify owner %s about deleted message", connection.owner_id)
