"""Request and response models of the API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["ru", "en"]


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    commit: str | None


class CityOut(BaseModel):
    name: str
    admin: str | None = None
    country: str | None = None
    lat: float
    lon: float
    timezone: str


class MorningOut(BaseModel):
    enabled: bool
    time: str


class MeOut(BaseModel):
    id: int
    first_name: str | None
    language: Language
    language_setting: Literal["auto", "ru", "en"]
    city: CityOut
    morning: MorningOut
    can_write: bool


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["auto", "ru", "en"] | None = None
    morning_enabled: bool | None = None
    morning_time: str | None = Field(default=None, max_length=5)


class CityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1, max_length=64)


class WeatherOut(BaseModel):
    city: str
    temperature: float | None
    feels_like: float | None
    wind: float | None
    code: int
    emoji: str
    description: str
    tmin: float | None
    tmax: float | None
    tips: list[str]


class RateOut(BaseModel):
    value: float
    change: float


class RatesOut(BaseModel):
    date: date
    usd: RateOut
    eur: RateOut


class HabitOut(BaseModel):
    id: int
    name: str
    created_on: date
    done_today: bool | None
    streak: int
    done_days: int
    total_days: int
    last_days: list[bool | None]


class TodayReminder(BaseModel):
    id: int
    text: str
    time: str
    due_at: datetime


class TodayHabits(BaseModel):
    done: int
    total: int
    items: list[HabitOut]


class BestStreak(BaseModel):
    name: str
    days: int


class TodayLesson(BaseModel):
    time: str
    end: str
    title: str
    kind: str | None
    room: str | None
    starts_at: datetime
    ends_at: datetime


class TodayOut(BaseModel):
    date: date
    part_of_day: Literal["morning", "day", "evening", "night"]
    weather: WeatherOut | None
    reminders_today: list[TodayReminder]
    habits: TodayHabits
    notes_count: int
    rates: RatesOut | None
    best_streak: BestStreak | None
    has_schedule: bool
    lessons: list[TodayLesson]
    week_label: str | None


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=10_000)


class NoteOut(BaseModel):
    id: int
    text: str
    created_at: datetime
    updated_at: datetime


RepeatName = Literal["none", "daily", "weekly", "monthly"]
Clock = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]
LocalMoment = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")]


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeat: Literal["daily", "weekly", "monthly"]
    time_local: Clock
    weekdays: int | None = Field(default=None, ge=1, le=127)
    interval_weeks: Literal[1, 2] = 1
    month_day: int | None = Field(default=None, ge=1, le=31)
    anchor_date: date | None = None


class RuleOut(BaseModel):
    repeat: Literal["daily", "weekly", "monthly"]
    time_local: str
    weekdays: int | None
    interval_weeks: int
    month_day: int | None
    anchor_date: date


class ReminderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=1_000)
    due_local: LocalMoment | None = None
    rule: RuleIn | None = None


class ReminderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=1_000)
    due_local: LocalMoment | None = None
    rule: RuleIn | None = None


class ReminderOut(BaseModel):
    id: int
    text: str
    due_at: datetime
    due_local: str
    status: str
    repeat: RepeatName
    rule: RuleOut | None
    description: str | None


class ParseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=1_000)


class ParseOut(BaseModel):
    text: str
    repeat: RepeatName
    date: date | None
    time: str | None
    weekdays: int | None
    interval_weeks: int
    month_day: int | None
    description: str | None


class SnoozeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["10m", "1h", "tomorrow"]


class ReminderItemOut(BaseModel):
    kind: Literal["reminder"]
    id: int
    time: str
    text: str
    repeat: RepeatName
    description: str | None


class LessonItemOut(BaseModel):
    kind: Literal["lesson"]
    time: str
    end: str
    title: str
    lesson_kind: str | None
    room: str | None


AgendaItemOut = Annotated[ReminderItemOut | LessonItemOut, Field(discriminator="kind")]


class AgendaDayOut(BaseModel):
    date: date
    label: str | None  # the calendar's week label, «5 неделя»
    items: list[AgendaItemOut]


class AgendaOut(BaseModel):
    days: list[AgendaDayOut]


class HabitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=1_000)


class MarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool | None


ScheduleKindName = Literal["mirea", "url", "file"]


class ScheduleOut(BaseModel):
    kind: ScheduleKindName
    title: str | None
    mirea_id: int | None
    url: str | None
    fetched_at: datetime
    ok_at: datetime | None
    error: str | None
    stale: bool
    lesson_reminder_minutes: int | None
    lessons_ahead: int


class ScheduleState(BaseModel):
    source: ScheduleOut | None


class ScheduleIn(BaseModel):
    """Exactly one of the two."""

    model_config = ConfigDict(extra="forbid")

    mirea_id: int | None = Field(default=None, ge=1, le=1_000_000)
    url: str | None = Field(default=None, max_length=2000)


class SchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_reminder_minutes: Literal[5, 10, 15, 30, 60] | None


class GroupOut(BaseModel):
    id: int
    name: str


class GroupsOut(BaseModel):
    groups: list[GroupOut]
    building: bool  # the directory is not ready: no full crawl finished, or too few groups
