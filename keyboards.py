"""Reply-keyboard main menu shown to business owners after /start.

Kept separate from handlers so button labels are defined once and reused by
both the keyboard itself and the `F.text == ...` handlers that react to taps.
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_PROFILE = "👤 Профиль"
BTN_SUBSCRIBE = "💳 Подписка"
BTN_CONNECTIONS = "🔌 Подключения"
BTN_HELP = "❓ Помощь"

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_SUBSCRIBE)],
        [KeyboardButton(text=BTN_CONNECTIONS), KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)
