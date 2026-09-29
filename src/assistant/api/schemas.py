"""Request and response models of the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

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
