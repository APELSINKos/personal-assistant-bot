"""Request and response models of the API."""

from __future__ import annotations

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
