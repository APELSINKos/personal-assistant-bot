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


class FoundCityOut(CityOut):
    """A place the search found. Its GeoNames id goes back with PUT /me/city and POST
    /me/cities: by it a city is known as one already kept."""

    geo_id: int | None = None


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
    currency: str  # ISO 4217, the user's accounts
    money_budget: int | None  # a month's, in hundredths


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["auto", "ru", "en"] | None = None
    morning_enabled: bool | None = None
    morning_time: str | None = Field(default=None, max_length=5)
    currency: str | None = Field(default=None, max_length=3)


# A GeoNames id as SQLite's INTEGER keeps it: signed, 64 bits.
GeoId = Annotated[int, Field(ge=1, le=2**63 - 1)]


class CityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1, max_length=64)
    # The search result's: the new home leaves the extra cities by it, as by its coordinates.
    geo_id: GeoId | None = None


class WeatherCityIn(BaseModel):
    """An extra city of the weather: a place of GET /cities as it came."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    admin: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1, max_length=64)
    geo_id: GeoId | None = None


class WeatherCityOut(BaseModel):
    id: int
    name: str
    admin: str | None
    country: str | None
    lat: float
    lon: float
    timezone: str
    geo_id: int | None


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


class ForecastCityOut(BaseModel):
    id: int  # 0: the home city
    name: str
    home: bool


class ForecastNowOut(BaseModel):
    temperature: float | None
    feels_like: float | None
    wind: float | None
    gusts: float | None
    humidity: float | None  # percent
    is_day: bool
    emoji: str  # the moon at night
    description: str
    # The chance of the hour going on: the label at now rounded up to the hour.
    precip_chance: int | None


class ForecastHourOut(BaseModel):
    time: str  # "HH:MM", the label
    emoji: str
    description: str
    temperature: float
    precip_chance: int | None  # of the hour before the label


class ForecastDayOut(BaseModel):
    date: date
    emoji: str  # of the day's heaviest weather
    description: str
    tmin: float
    tmax: float
    precip_chance: int | None


class ForecastOut(BaseModel):
    """A city's forecast. Every time and date is on the city's clock; the app shows them as
    they are."""

    city: ForecastCityOut
    now: ForecastNowOut
    tips: list[str]
    hours: list[ForecastHourOut]  # up to 23 after now; a missing hour is left out
    days: list[ForecastDayOut]  # up to 7 from the city's today
    sunrise: str | None  # "HH:MM" of days[0]; None on a polar day or night too
    sunset: str | None
    polar: Literal["night", "day"] | None


class RateOut(BaseModel):
    value: float
    change: float


class RatesOut(BaseModel):
    date: date
    usd: RateOut
    eur: RateOut


StreakUnitName = Literal["days", "weeks"]


class HabitOut(BaseModel):
    id: int
    name: str
    emoji: str
    color: str
    weekly_goal: int
    created_on: date
    done_today: bool | None
    streak: int
    streak_unit: StreakUnitName
    record: int
    percent: int
    week_done: int
    week_goal: int
    week: str  # Monday to Sunday: "1" done, "0" missed, "-" no mark, "." before the habit or ahead
    done_days: int
    total_days: int
    last_days: list[bool | None]


class HabitDetailOut(HabitOut):
    year_from: date  # a Monday
    year: str  # 371 days from year_from, in the alphabet of `week`


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
    count: int
    unit: StreakUnitName


class TodayLesson(BaseModel):
    time: str
    end: str
    title: str
    kind: str | None
    room: str | None
    starts_at: datetime
    ends_at: datetime


class TodayMoneyOut(BaseModel):
    """The money of the day for the «Сегодня» card; amounts in hundredths."""

    currency: str
    today: int
    spent: int  # this month
    budget: int | None
    left: int | None
    per_day: int | None
    count: int  # this month's entries


class ClassesWeatherOut(BaseModel):
    """The weather of the way to the first class and home after the last one, on the user's
    clock. It is the whole day's: the app hides the parts that are over."""

    start: str  # "HH:MM", the first class begins
    start_temp: float | None  # None: no forecast for that hour
    start_chance: int | None  # None under 30 % too
    end: str  # the last class ends
    end_temp: float | None
    end_chance: int | None


class PinnedNoteOut(BaseModel):
    id: int
    text: str  # whole: the app cuts it
    done: int  # a checklist's checked items; 0 of 0 for a note without items
    total: int


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
    money: TodayMoneyOut | None
    tomorrow: ForecastDayOut | None  # from 17:00 on the user's clock, with the weather
    classes_weather: ClassesWeatherOut | None  # None without today's classes or the forecast
    pinned_notes: list[PinnedNoteOut]  # the first three, in the order of the notes


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=10_000)  # a checklist's title
    # No bounds on the items here: the service measures each one after trimming it and gives
    # the limits the app knows (422 for an item's length, 409 for their number).
    items: list[str] = Field(default_factory=list)
    pinned: bool = False


class NotePatch(BaseModel):
    """At least one of the two."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=10_000)
    pinned: bool | None = None


class NoteItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str  # measured by the service after trimming, as NoteIn.items


class NoteItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool  # set, not switched: a second request changes nothing


class NoteItemOut(BaseModel):
    id: int
    text: str
    done: bool


class NoteOut(BaseModel):
    id: int
    text: str
    pinned: bool
    items: list[NoteItemOut]  # in the order they were added
    created_at: datetime
    updated_at: datetime  # the text's last change: pins and items leave it


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
    emoji: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=16)
    weekly_goal: int | None = Field(default=None, ge=1, le=7)


class HabitPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=1_000)
    emoji: str | None = Field(default=None, max_length=16)
    color: str | None = Field(default=None, max_length=16)
    weekly_goal: int | None = Field(default=None, ge=1, le=7)


class SharedOut(BaseModel):
    prepared_id: str  # for Telegram.WebApp.shareMessage


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


# An amount as the app sends it: a decimal with a point, in the user's currency («430.50»).
Amount = Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,2})?$")]  # ASCII digits
KindName = Literal["expense", "income"]
DbId = Annotated[int, Field(ge=1, le=2**63 - 1)]


class MoneyCategoryOut(BaseModel):
    id: int
    kind: KindName
    name: str  # in the user's language
    emoji: str
    hidden: bool
    can_hide: bool  # false for the «Другое» of each kind
    budget: int | None  # a month's, in hundredths


class MoneyEntryOut(BaseModel):
    id: int
    amount: int  # hundredths
    category_id: int
    note: str
    day: date


class CategoryTotalOut(BaseModel):
    category_id: int
    amount: int
    share: int  # percent of the month's expenses; 0 for incomes
    left: int | None  # what the category's budget leaves


class MoneyMonthOut(BaseModel):
    month: str  # «2026-10»
    first_month: str | None  # the month of the oldest entry
    currency: str
    spent: int
    income: int
    balance: int
    budget: int | None
    left: int | None
    per_day: int | None
    expenses: list[CategoryTotalOut]  # the largest first
    incomes: list[CategoryTotalOut]
    days: list[int | None]  # spent on each day; None for the days still ahead
    categories: list[MoneyCategoryOut]  # all of them, hidden ones too
    entries: list[MoneyEntryOut]  # the month's, the newest first


class MoneyEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount
    category_id: DbId
    note: str = Field(default="", max_length=1_000)
    day: date | None = None  # today when left out


class MoneyEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount | None = None
    category_id: DbId | None = None
    note: str | None = Field(default=None, max_length=1_000)
    day: date | None = None


class AlertOut(BaseModel):
    category_id: int | None  # None: the budget of all expenses
    emoji: str | None  # the category's
    name: str | None  # the category's, in the user's language
    threshold: int  # 80 or 100
    spent: int
    budget: int


class MoneyEntrySaved(BaseModel):
    entry: MoneyEntryOut
    alerts: list[AlertOut]  # the budget warnings this change set off


class MoneyCategoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: KindName
    name: str = Field(max_length=1_000)
    emoji: str = Field(max_length=16)


class MoneyCategoryPatch(BaseModel):
    """Every field may be left out; `budget: null` removes the budget."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=1_000)
    emoji: str | None = Field(default=None, max_length=16)
    hidden: bool | None = None
    budget: Amount | None = None


class BudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Amount | None  # null removes the budget


class CurrencyRateOut(BaseModel):
    code: str
    name: str  # in the user's language
    value: float  # roubles for one unit
    change: float


class RatesAllOut(BaseModel):
    date: date
    currencies: list[CurrencyRateOut]  # USD, EUR and the user's currency first


class RatePointOut(BaseModel):
    day: date
    value: float


class RateHistoryOut(BaseModel):
    code: str
    points: list[RatePointOut]  # the oldest first; working days only
