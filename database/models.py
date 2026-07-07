"""SQLAlchemy ORM models for StarPrivacyBot."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    """A Telegram user who has talked to the bot (business owner or admin)."""

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    business_connections: Mapped[list["BusinessConnection"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class BusinessConnection(Base):
    """Mirrors a Telegram Business connection granted to this bot.

    Created/updated from the `business_connection` update. `is_enabled` reflects
    whether the business account owner currently has the bot active; when it
    is False we must not process or store any new messages for this chat.
    """

    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="business_connections")
    messages: Mapped[list["SavedMessage"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class Subscription(Base):
    """A paid (or admin/lifetime-free) subscription period for a user."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    tier: Mapped[str] = mapped_column(String(32))  # "basic" | "premium" | "admin"
    is_lifetime: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stars_paid: Mapped[int] = mapped_column(Integer, default=0)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class SavedMessage(Base):
    """A cached copy of a message from a connected Business chat.

    Only ever created for messages that arrive *after* the business
    connection is active and the owner has a usable subscription; see
    handlers/business.py for the gating logic.
    """

    __tablename__ = "saved_messages"
    __table_args__ = (
        UniqueConstraint("connection_id", "chat_id", "message_id", name="uq_message_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("business_connections.connection_id"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)

    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_from_business_owner: Mapped[bool] = mapped_column(Boolean, default=False)

    content_type: Mapped[str] = mapped_column(String(32))  # text/photo/video/voice/document/...
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connection: Mapped["BusinessConnection"] = relationship(back_populates="messages")
