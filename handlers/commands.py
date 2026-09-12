"""Общие команды бота: /start, /help, /status, /menu.

The text-building functions here are shared with `handlers/menu.py` so the
persistent reply-keyboard buttons (Профиль/Подключения) and their slash-command
equivalents (/status/etc.) always show identical content.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import config
import keyboards
from database import db
from middlewares.access import get_access_level

router = Router(name="commands")

WELCOME_TEXT = (
    "👋 <b>StarPrivacyBot</b>\n\n"
    "Этот бот подключается к вашему <b>Telegram Business</b>-аккаунту и делает "
    "приватную копию сообщений, которые вам присылают, — так вы сможете увидеть "
    "их, даже если отправитель отредактирует или удалит сообщение.\n\n"
    "<b>Как подключить:</b>\n"
    "1. Настройки Telegram → Бизнес → Чат-боты\n"
    "2. Выберите этого бота и включите его для нужных чатов\n"
    "3. Отправьте /subscribe, чтобы активировать тариф (до этого момента ничего не сохраняется)\n\n"
    "⚠️ <b>Уведомление о приватности:</b> включайте бота только для тех чатов, "
    "где у вас есть право хранить переписку. Подробности — в README проекта.\n\n"
    "Пользуйтесь меню ниже 👇, или командами: /menu /help /status /subscribe"
)

HELP_TEXT = (
    "<b>Меню</b>\n"
    f"{keyboards.BTN_PROFILE} — ваш тариф и статус бизнес-подключения\n"
    f"{keyboards.BTN_SUBSCRIBE} — тарифы и оплата через Telegram Stars\n"
    f"{keyboards.BTN_CONNECTIONS} — список подключённых бизнес-чатов\n"
    f"{keyboards.BTN_HELP} — это сообщение\n\n"
    "<b>Команды</b>\n"
    "/start — приветствие и инструкция по подключению\n"
    "/menu — показать меню, если оно пропало\n"
    "/status — то же, что кнопка «Профиль»\n"
    "/subscribe — то же, что кнопка «Подписка»\n"
    "/help — это сообщение"
)


async def build_status_text(user_id: int) -> str:
    access = await get_access_level(user_id)
    connections = await db.get_connections_for_owner(user_id)

    if access.tier == "admin":
        plan_line = "Тариф: <b>Администратор (бесплатно навсегда)</b>"
    elif access.tier == "trial":
        sub = await db.get_active_subscription(user_id)
        until = f" до {sub.expires_at:%d.%m.%Y %H:%M} UTC" if sub and sub.expires_at else ""
        plan_line = f"Тариф: <b>Пробный период</b>{until}"
    elif access.allowed:
        retention = "без ограничений" if access.max_stored_days is None else f"{access.max_stored_days} дней"
        sub = await db.get_active_subscription(user_id)
        until = f", действует до {sub.expires_at:%d.%m.%Y %H:%M} UTC" if sub and sub.expires_at else ""
        tariff_title = config.TARIFFS[access.tier].title if access.tier in config.TARIFFS else access.tier
        plan_line = f"Тариф: <b>{tariff_title}</b> (история: {retention}{until})"
    else:
        plan_line = "Тариф: <b>не активен</b> — используйте /subscribe, чтобы включить архивирование"

    if connections:
        active = [c for c in connections if c.is_enabled]
        conn_line = f"Бизнес-подключения: {len(active)} активно из {len(connections)}"
    else:
        conn_line = "Бизнес-подключения: пока нет — подключите бота в Настройках Telegram → Бизнес"

    return f"👤 <b>Профиль</b>\n\n{plan_line}\n{conn_line}"


async def build_connections_text(user_id: int) -> str:
    connections = await db.get_connections_for_owner(user_id)
    if not connections:
        return (
            "🔌 <b>Бизнес-подключения</b>\n\n"
            "Пока нет ни одного подключения.\n"
            "Настройки Telegram → Бизнес → Чат-боты → добавьте этого бота."
        )

    lines = ["🔌 <b>Бизнес-подключения</b>\n"]
    for conn in connections:
        icon = "✅ активно" if conn.is_enabled else "⛔ отключено"
        lines.append(f"{icon} — обновлено {conn.updated_at:%d.%m.%Y %H:%M} UTC")
    return "\n".join(lines)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await message.answer(WELCOME_TEXT, reply_markup=keyboards.MAIN_MENU)

    if user.telegram_id not in config.ADMIN_IDS:
        trial = await db.grant_trial_if_eligible(user.telegram_id)
        if trial is not None:
            await message.answer(
                f"🎁 Вам активирован бесплатный пробный период на "
                f"{config.TRIAL_TARIFF.duration_days} дня — попробуйте все возможности бота.\n"
                f"Действует до {trial.expires_at:%d.%m.%Y %H:%M} UTC."
            )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню 👇", reply_markup=keyboards.MAIN_MENU)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    await message.answer(await build_status_text(message.from_user.id))
