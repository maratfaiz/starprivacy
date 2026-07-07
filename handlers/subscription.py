"""Оплата подписки через Telegram Stars (/subscribe, инвойсы, платежи)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import config
from database import db

logger = logging.getLogger(__name__)
router = Router(name="subscription")


def _plans_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{tariff.title} — {tariff.stars_price}⭐/мес",
                callback_data=f"sub:{tariff.key}",
            )
        ]
        for tariff in config.TARIFFS.values()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    if message.from_user.id in config.ADMIN_IDS:
        await message.answer(
            "У вас уже есть бесплатный доступ администратора — покупать ничего не нужно. 🎉"
        )
        return

    lines = ["<b>Выберите тариф</b> (оплата ежемесячно, в Telegram Stars):\n"]
    for tariff in config.TARIFFS.values():
        lines.append(f"• <b>{tariff.title}</b> — {tariff.stars_price}⭐\n  {tariff.description}")
    await message.answer("\n".join(lines), reply_markup=_plans_keyboard())


@router.callback_query(F.data.startswith("sub:"))
async def on_plan_chosen(callback: CallbackQuery) -> None:
    tariff_key = callback.data.split(":", 1)[1]
    tariff = config.TARIFFS.get(tariff_key)
    if tariff is None:
        await callback.answer("Тариф не найден.", show_alert=True)
        return

    await callback.message.answer_invoice(
        title=f"StarPrivacyBot — тариф «{tariff.title}»",
        description=tariff.description,
        payload=f"subscription:{tariff.key}",
        currency=config.STARS_CURRENCY,
        prices=[LabeledPrice(label=f"{tariff.title} (30 дней)", amount=tariff.stars_price)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload
    tariff_key = payload.split(":", 1)[1] if payload.startswith("subscription:") else None
    if tariff_key not in config.TARIFFS:
        await pre_checkout_query.answer(ok=False, error_message="Этот тариф больше недоступен.")
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload
    tariff_key = payload.split(":", 1)[1] if payload.startswith("subscription:") else None
    tariff = config.TARIFFS.get(tariff_key)
    if tariff is None:
        logger.error("Received payment with unknown payload: %s", payload)
        return

    await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )
    await db.create_subscription(
        user_id=message.from_user.id,
        tier=tariff.key,
        stars_paid=payment.total_amount,
        duration_days=tariff.duration_days,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
    )
    await message.answer(
        f"✅ Тариф «<b>{tariff.title}</b>» активирован на {tariff.duration_days} дней.\n"
        "Теперь подключите бота в разделе Настройки Telegram → Бизнес, чтобы начать архивирование."
    )
