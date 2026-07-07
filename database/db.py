"""Async database engine/session management and CRUD helpers."""
from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import config
from database.models import Base, BusinessConnection, SavedMessage, Subscription, User

_engine = create_async_engine(config.DATABASE_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory() as session:
        yield session


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------

async def get_or_create_user(
    telegram_id: int, username: str | None = None, first_name: str | None = None
) -> User:
    async with get_session() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_admin=telegram_id in config.ADMIN_IDS,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        elif username != user.username or first_name != user.first_name:
            user.username = username
            user.first_name = first_name
            await session.commit()
            await session.refresh(user)
        return user


async def grant_trial_if_eligible(user_id: int) -> Subscription | None:
    """Grant the one-time free trial to a brand-new user, if they qualify.

    Returns the created Subscription, or None if the user already used their
    trial before or already has some other active subscription.
    """
    now = dt.datetime.now(dt.timezone.utc)
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user is None or user.trial_used:
            return None

        active = await session.scalar(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where((Subscription.expires_at.is_(None)) | (Subscription.expires_at > now))
        )
        if active is not None:
            return None

        sub = Subscription(
            user_id=user_id,
            tier=config.TRIAL_TARIFF.key,
            is_lifetime=False,
            started_at=now,
            expires_at=now + dt.timedelta(days=config.TRIAL_TARIFF.duration_days),
            stars_paid=0,
        )
        session.add(sub)
        user.trial_used = True
        await session.commit()
        await session.refresh(sub)
        return sub


# --------------------------------------------------------------------------
# Business connections
# --------------------------------------------------------------------------

async def upsert_business_connection(
    connection_id: str, owner_id: int, is_enabled: bool, can_reply: bool
) -> BusinessConnection:
    async with get_session() as session:
        await get_or_create_user(owner_id)
        conn = await session.scalar(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        )
        if conn is None:
            conn = BusinessConnection(
                connection_id=connection_id,
                owner_id=owner_id,
                is_enabled=is_enabled,
                can_reply=can_reply,
            )
            session.add(conn)
        else:
            conn.is_enabled = is_enabled
            conn.can_reply = can_reply
        await session.commit()
        await session.refresh(conn)
        return conn


async def get_business_connection(connection_id: str) -> BusinessConnection | None:
    async with get_session() as session:
        return await session.scalar(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        )


async def get_connections_for_owner(owner_id: int) -> list[BusinessConnection]:
    async with get_session() as session:
        result = await session.scalars(
            select(BusinessConnection)
            .where(BusinessConnection.owner_id == owner_id)
            .order_by(BusinessConnection.updated_at.desc())
        )
        return list(result)


# --------------------------------------------------------------------------
# Subscriptions
# --------------------------------------------------------------------------

async def get_active_subscription(user_id: int) -> Subscription | None:
    """Return the currently active subscription for a user, if any.

    Lifetime-free admins always have an implicit active subscription even
    without a row in the table (see access.has_active_access), so this
    function only concerns itself with real, paid/expiring subscriptions.
    """
    now = dt.datetime.now(dt.timezone.utc)
    async with get_session() as session:
        return await session.scalar(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where((Subscription.expires_at.is_(None)) | (Subscription.expires_at > now))
            .order_by(Subscription.expires_at.desc().nullsfirst())
        )


async def create_subscription(
    user_id: int,
    tier: str,
    stars_paid: int,
    duration_days: int,
    telegram_payment_charge_id: str | None = None,
    is_lifetime: bool = False,
) -> Subscription:
    now = dt.datetime.now(dt.timezone.utc)
    expires_at = None if is_lifetime else now + dt.timedelta(days=duration_days)
    async with get_session() as session:
        sub = Subscription(
            user_id=user_id,
            tier=tier,
            is_lifetime=is_lifetime,
            started_at=now,
            expires_at=expires_at,
            stars_paid=stars_paid,
            telegram_payment_charge_id=telegram_payment_charge_id,
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


# --------------------------------------------------------------------------
# Saved messages
# --------------------------------------------------------------------------

async def save_message(**fields) -> SavedMessage:
    async with get_session() as session:
        msg = SavedMessage(**fields)
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg


async def get_saved_message_by_id(row_id: int) -> SavedMessage | None:
    async with get_session() as session:
        return await session.get(SavedMessage, row_id)


async def get_chats_for_connection(connection_id: str) -> list[dict]:
    """Per-chat summary (last message + counters) for the archive browser."""
    async with get_session() as session:
        chat_ids = list(
            await session.scalars(
                select(SavedMessage.chat_id)
                .where(SavedMessage.connection_id == connection_id)
                .distinct()
            )
        )

        summaries: list[dict] = []
        for chat_id in chat_ids:
            base = select(SavedMessage).where(
                SavedMessage.connection_id == connection_id, SavedMessage.chat_id == chat_id
            )
            last_message = await session.scalar(base.order_by(SavedMessage.sent_at.desc()))
            total = await session.scalar(
                select(func.count()).select_from(SavedMessage).where(
                    SavedMessage.connection_id == connection_id, SavedMessage.chat_id == chat_id
                )
            )
            edited = await session.scalar(
                select(func.count()).select_from(SavedMessage).where(
                    SavedMessage.connection_id == connection_id,
                    SavedMessage.chat_id == chat_id,
                    SavedMessage.is_edited.is_(True),
                )
            )
            deleted = await session.scalar(
                select(func.count()).select_from(SavedMessage).where(
                    SavedMessage.connection_id == connection_id,
                    SavedMessage.chat_id == chat_id,
                    SavedMessage.is_deleted.is_(True),
                )
            )
            summaries.append(
                {
                    "chat_id": chat_id,
                    "sender_name": last_message.sender_name if last_message else None,
                    "last_message_preview": (last_message.text or last_message.caption or f"[{last_message.content_type}]")
                    if last_message
                    else None,
                    "last_sent_at": last_message.sent_at if last_message else None,
                    "total_messages": total or 0,
                    "edited_count": edited or 0,
                    "deleted_count": deleted or 0,
                }
            )

        summaries.sort(key=lambda row: row["last_sent_at"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        return summaries


async def get_messages_for_chat(
    connection_id: str, chat_id: int, before_id: int | None = None, limit: int = 50
) -> list[SavedMessage]:
    """Latest `limit` messages in a chat, ordered oldest-to-newest for display.

    Pass `before_id` (the smallest `id` already loaded) to page further back.
    """
    async with get_session() as session:
        query = select(SavedMessage).where(
            SavedMessage.connection_id == connection_id, SavedMessage.chat_id == chat_id
        )
        if before_id is not None:
            query = query.where(SavedMessage.id < before_id)
        query = query.order_by(SavedMessage.id.desc()).limit(limit)
        rows = list(await session.scalars(query))
        rows.reverse()
        return rows


async def get_message(connection_id: str, chat_id: int, message_id: int) -> SavedMessage | None:
    async with get_session() as session:
        return await session.scalar(
            select(SavedMessage)
            .where(SavedMessage.connection_id == connection_id)
            .where(SavedMessage.chat_id == chat_id)
            .where(SavedMessage.message_id == message_id)
        )


async def mark_message_edited(
    connection_id: str, chat_id: int, message_id: int, previous_text: str | None, new_text: str | None
) -> SavedMessage | None:
    async with get_session() as session:
        msg = await session.scalar(
            select(SavedMessage)
            .where(SavedMessage.connection_id == connection_id)
            .where(SavedMessage.chat_id == chat_id)
            .where(SavedMessage.message_id == message_id)
        )
        if msg is None:
            return None
        msg.is_edited = True
        msg.edited_at = dt.datetime.now(dt.timezone.utc)
        msg.previous_text = previous_text
        msg.text = new_text
        await session.commit()
        await session.refresh(msg)
        return msg


async def mark_messages_deleted(
    connection_id: str, chat_id: int, message_ids: list[int]
) -> list[SavedMessage]:
    now = dt.datetime.now(dt.timezone.utc)
    async with get_session() as session:
        result = await session.scalars(
            select(SavedMessage)
            .where(SavedMessage.connection_id == connection_id)
            .where(SavedMessage.chat_id == chat_id)
            .where(SavedMessage.message_id.in_(message_ids))
        )
        messages = list(result)
        for msg in messages:
            msg.is_deleted = True
            msg.deleted_at = now
        await session.commit()
        for msg in messages:
            await session.refresh(msg)
        return messages


async def get_stats() -> dict[str, int]:
    async with get_session() as session:
        users = await session.scalar(select(func.count()).select_from(User))
        connections = await session.scalar(select(func.count()).select_from(BusinessConnection))
        active_connections = await session.scalar(
            select(func.count()).select_from(BusinessConnection).where(BusinessConnection.is_enabled.is_(True))
        )
        messages = await session.scalar(select(func.count()).select_from(SavedMessage))
        active_subs = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where((Subscription.expires_at.is_(None)) | (Subscription.expires_at > dt.datetime.now(dt.timezone.utc)))
        )
        return {
            "users": users or 0,
            "connections": connections or 0,
            "active_connections": active_connections or 0,
            "messages": messages or 0,
            "active_subscriptions": active_subs or 0,
        }


async def purge_expired_messages(connection_id: str, max_stored_days: int) -> int:
    """Delete saved messages older than the retention window for a tariff."""
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_stored_days)
    async with get_session() as session:
        result = await session.scalars(
            select(SavedMessage)
            .where(SavedMessage.connection_id == connection_id)
            .where(SavedMessage.sent_at < cutoff)
        )
        rows = list(result)
        for row in rows:
            await session.delete(row)
        await session.commit()
        return len(rows)
