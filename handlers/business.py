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
import html
import logging

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

import config
from database import db
from database.models import SavedMessage
from middlewares.access import get_access_level
from utils.media import describe_non_downloadable, download_media, extract_media_ref

logger = logging.getLogger(__name__)
router = Router(name="business")


def _display_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Unknown"
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)


def _esc(text: str | None) -> str:
    """HTML-escape user-supplied text before it goes into an HTML-parsed message.

    The bot's default parse mode is HTML (see main.py); an unescaped '<', '>'
    or '&' in a customer's message text breaks Telegram's HTML parsing and
    silently drops the whole notification (send_message raises, and unless
    the caller wraps it in try/except, nothing reaches the owner at all).
    """
    return html.escape(text, quote=False) if text else ""


@router.business_connection()
async def on_business_connection(connection: BusinessConnection, bot: Bot) -> None:
    await db.upsert_business_connection(
        connection_id=connection.id,
        owner_id=connection.user.id,
        is_enabled=connection.is_enabled,
        can_reply=connection.can_reply,
    )

    # The owner may connect the bot straight from Telegram Settings without
    # ever sending /start first - grant the trial here too, otherwise nothing
    # ever gets archived (no active access) and the owner sees no reaction at all.
    trial_note = ""
    if connection.is_enabled and connection.user.id not in config.ADMIN_IDS:
        trial = await db.grant_trial_if_eligible(connection.user.id)
        if trial is not None:
            trial_note = (
                f"\n\n🎁 Вам активирован бесплатный пробный период на "
                f"{config.TRIAL_TARIFF.duration_days} дня — архивирование уже работает.\n"
                f"Действует до {trial.expires_at:%d.%m.%Y %H:%M} UTC."
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
            )
            + trial_note,
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
    text = message.text
    if media_ref is not None:
        content_type, media_file_id = media_ref
        if media_file_id is not None:
            media_local_path = await download_media(
                bot, connection_id, message.chat.id, message.message_id, content_type, media_file_id
            )
        else:
            # location/venue/contact/poll/dice - no file to download, only a summary to store.
            text = describe_non_downloadable(message)

    await db.save_message(
        connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        sender_id=message.from_user.id if message.from_user else None,
        sender_name=_display_name(message),
        is_from_business_owner=False,
        content_type=content_type,
        text=text,
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
    previous_display = _esc(previous_text) or "<i>[без текста]</i>"
    new_display = _esc(new_text) or "<i>[без текста]</i>"
    try:
        await bot.send_message(
            connection.owner_id,
            (
                f"✏️ <b>{_esc(original.sender_name)}</b> изменил(а) сообщение "
                f"({when:%d.%m.%Y %H:%M} UTC):\n\n"
                f"Было:\n<blockquote>{previous_display}</blockquote>\n"
                f"Стало:\n<blockquote>{new_display}</blockquote>"
            ),
        )
    except Exception:
        logger.exception("Failed to notify owner %s about edited message", connection.owner_id)


def _deleted_body(msg: SavedMessage) -> str:
    raw = msg.text or msg.caption
    if raw:
        return _esc(raw)
    return f"<i>[{msg.content_type}]</i>"


@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted, bot: Bot) -> None:
    connection = await db.get_business_connection(event.business_connection_id)
    if connection is None:
        return

    deleted = await db.mark_messages_deleted(
        event.business_connection_id, event.chat.id, list(event.message_ids)
    )
    customer_messages = [msg for msg in deleted if not msg.is_from_business_owner]
    if not customer_messages:
        return  # Only the owner's own messages were deleted - nothing to alert about.

    sender_label = _esc(customer_messages[0].sender_name)

    if len(customer_messages) == 1:
        msg = customer_messages[0]
        header = f"🗑️ <b>{sender_label}</b> удалил(а) сообщение (отправлено {msg.sent_at:%d.%m.%Y %H:%M} UTC):"
        body = f"<blockquote>{_deleted_body(msg)}</blockquote>"
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
        return

    # Several messages deleted at once - one grouped, collapsible summary instead
    # of spamming the owner with N separate notifications.
    entries = "\n".join(
        f"{msg.sent_at:%d.%m.%Y %H:%M} UTC — {_deleted_body(msg)}" for msg in customer_messages
    )
    try:
        await bot.send_message(
            connection.owner_id,
            (
                f"🗑️ <b>{sender_label}</b> удалил(а) {len(customer_messages)} сообщения(ий):\n\n"
                f"<blockquote expandable>{entries}</blockquote>"
            ),
        )
        for msg in customer_messages:
            if not msg.media_local_path:
                continue
            from aiogram.types import FSInputFile

            caption = f"📎 медиафайл к сообщению от {msg.sent_at:%d.%m.%Y %H:%M} UTC"
            if msg.content_type == "photo":
                await bot.send_photo(connection.owner_id, FSInputFile(msg.media_local_path), caption=caption)
            else:
                await bot.send_document(connection.owner_id, FSInputFile(msg.media_local_path), caption=caption)
    except Exception:
        logger.exception("Failed to notify owner %s about deleted messages", connection.owner_id)
