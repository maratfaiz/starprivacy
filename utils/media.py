"""Media download/caching helpers.

Business messages can carry photos, videos, voice notes or documents. We
download a local copy as soon as we see the message so that, if the sender
later deletes it, we still have the bytes on disk (Telegram stops serving a
file_id once the source message is gone).
"""
from __future__ import annotations

import logging
import os

from aiogram import Bot
from aiogram.types import Message

import config

logger = logging.getLogger(__name__)

# (content_type, file_id, suggested extension)
_MEDIA_EXTENSIONS = {
    "photo": "jpg",
    "video": "mp4",
    "voice": "ogg",
    "video_note": "mp4",
    "audio": "mp3",
    "document": "bin",
    "animation": "mp4",
    "sticker": "webp",
}


def extract_media_ref(message: Message) -> tuple[str, str | None] | None:
    """Return (content_type, file_id) for the highest-quality media on a message.

    `file_id` is None for content types that have no downloadable file
    (location/venue/contact/poll/dice) - callers must skip `download_media`
    for those and fall back to `describe_non_downloadable` for a text summary.
    """
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.document:
        return "document", message.document.file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.location:
        return "location", None
    if message.venue:
        return "venue", None
    if message.contact:
        return "contact", None
    if message.poll:
        return "poll", None
    if message.dice:
        return "dice", None
    return None


def describe_non_downloadable(message: Message) -> str | None:
    """Human-readable summary for a content type with no file and no text/caption."""
    if message.location:
        loc = message.location
        return f"📍 Геолокация: {loc.latitude:.5f}, {loc.longitude:.5f}"
    if message.venue:
        venue = message.venue
        return f"📍 Место: {venue.title}, {venue.address}"
    if message.contact:
        contact = message.contact
        name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
        return f"👤 Контакт: {name} ({contact.phone_number})"
    if message.poll:
        return f"📊 Опрос: {message.poll.question}"
    if message.dice:
        return f"🎲 {message.dice.emoji} ({message.dice.value})"
    return None


async def download_media(
    bot: Bot, connection_id: str, chat_id: int, message_id: int, content_type: str, file_id: str
) -> str | None:
    """Download a media file to local storage, return its local path (or None on failure)."""
    folder = os.path.join(config.MEDIA_STORAGE_PATH, connection_id, str(chat_id))
    os.makedirs(folder, exist_ok=True)
    ext = _MEDIA_EXTENSIONS.get(content_type, "bin")
    destination = os.path.join(folder, f"{message_id}_{content_type}.{ext}")

    try:
        await bot.download(file_id, destination=destination)
    except Exception:
        logger.exception(
            "Failed to download media for connection=%s chat=%s message=%s",
            connection_id,
            chat_id,
            message_id,
        )
        return None
    return destination
