"""Request and response models of the API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

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


class TodayOut(BaseModel):
    date: date
    part_of_day: Literal["morning", "day", "evening", "night"]
    weather: WeatherOut | None
    reminders_today: list[TodayReminder]
    habits: TodayHabits
    notes_count: int
    rates: RatesOut | None
    best_streak: BestStreak | None


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=10_000)


class NoteOut(BaseModel):
    id: int
    text: str
    created_at: datetime
    updated_at: datetime


class ReminderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=1_000)
    due_local: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


class ReminderOut(BaseModel):
    id: int
    text: str
    due_at: datetime
    due_local: str
    status: str


class HabitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=1_000)


class MarkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool | None
