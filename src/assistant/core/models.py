"""Database schema. All datetimes are stored as naive UTC and exposed as aware UTC."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, MetaData, String, Text, event
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from assistant.core.timeutil import UTC, utcnow


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DONE = "done"


class ReminderStatusType(TypeDecorator[ReminderStatus]):
    impl = String(16)
    cache_ok = True

    def process_bind_param(self, value: ReminderStatus | None, dialect: Dialect) -> str | None:
        return None if value is None else ReminderStatus(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> ReminderStatus | None:
        return None if value is None else ReminderStatus(value)


class Repeat(StrEnum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RepeatType(TypeDecorator[Repeat]):
    impl = String(8)
    cache_ok = True

    def process_bind_param(self, value: Repeat | None, dialect: Dialect) -> str | None:
        return None if value is None else Repeat(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> Repeat | None:
        return None if value is None else Repeat(value)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(8))
    tg_language: Mapped[str | None] = mapped_column(String(16))
    city: Mapped[str] = mapped_column(String(100))
    lat: Mapped[float]
    lon: Mapped[float]
    timezone: Mapped[str] = mapped_column(String(64))
    morning_enabled: Mapped[bool] = mapped_column(default=True)
    morning_time: Mapped[str] = mapped_column(String(5), default="08:00")
    last_morning_date: Mapped[date | None]
    bot_blocked: Mapped[bool] = mapped_column(default=False)
    # The bot may write to this person: they wrote to it, or allowed messages in the app.
    can_write: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Note(Base):
    __tablename__ = "notes"
    # AUTOINCREMENT: ids of deleted rows are never handed out again, so an old inline button
    # (which carries the id) can never act on a newer item. Same for reminders and habits.
    __table_args__ = (Index("ix_notes_user", "user_id", "id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        Index("ix_reminders_queue", "status", "next_attempt_at"),
        Index("ix_reminders_user", "user_id", "status", "due_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[ReminderStatus] = mapped_column(
        ReminderStatusType(), default=ReminderStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Repeats: the rule in explicit fields, in the user's current zone (services/recurrence.py).
    repeat: Mapped[Repeat] = mapped_column(RepeatType(), default=Repeat.NONE)
    time_local: Mapped[str | None] = mapped_column(String(5))
    anchor_date: Mapped[date | None]
    weekdays: Mapped[int | None]
    interval_weeks: Mapped[int] = mapped_column(default=1)
    month_day: Mapped[int | None]
    # The rule's own moment of the pending firing; due_at can differ when it was snoozed.
    occurrence_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # A «+10 мин» copy of a repeat points to it; the copy outlives a deleted series.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("reminders.id", ondelete="SET NULL"))


@event.listens_for(Reminder, "before_insert")
def _occurrence_defaults_to_due(_mapper: object, _connection: object, target: Reminder) -> None:
    if target.occurrence_at is None:
        target.occurrence_at = target.due_at


class Habit(Base):
    __tablename__ = "habits"
    __table_args__ = (Index("ix_habits_user", "user_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    created_on: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class HabitMark(Base):
    __tablename__ = "habit_marks"

    habit_id: Mapped[int] = mapped_column(
        ForeignKey("habits.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    done: Mapped[bool]


class FsmState(Base):
    __tablename__ = "fsm_state"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    state: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
