"""Core objects → API response models."""

from __future__ import annotations

from assistant.api.schemas import CityOut, MeOut, MorningOut
from assistant.core.i18n import Translator, resolve_language, translator
from assistant.core.models import User


def user_language(user: User) -> str:
    return resolve_language(user.language, user.tg_language)


def user_translator(user: User) -> Translator:
    return translator(user_language(user))


def me_out(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        language=user_language(user),  # type: ignore[arg-type]
        language_setting=user.language or "auto",  # type: ignore[arg-type]
        city=CityOut(name=user.city, lat=user.lat, lon=user.lon, timezone=user.timezone),
        morning=MorningOut(enabled=user.morning_enabled, time=user.morning_time),
    )
