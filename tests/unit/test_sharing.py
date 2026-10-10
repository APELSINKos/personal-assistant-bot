from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from assistant.core.models import Habit, ShareCard
from assistant.core.services import sharing

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


async def _habit(session, make_user, user_id: int = 1) -> Habit:
    user = await make_user(id=user_id)
    habit = Habit(user_id=user.id, name="Спорт", created_on=date(2026, 10, 1))
    session.add(habit)
    await session.flush()
    return habit


async def test_a_saved_card_is_served_by_its_token(session, make_user) -> None:
    habit = await _habit(session, make_user)
    token = await sharing.save(session, habit.user_id, b"jpeg", NOW, habit_id=habit.id)
    assert sharing.is_token(token)
    assert await sharing.image(session, token, NOW) == b"jpeg"
    assert await sharing.image(session, "x" * 43, NOW) is None  # well-formed but unknown
    for forged in ("", "../../etc/passwd", token + "x", token[:-1] + "!"):
        assert await sharing.image(session, forged, NOW) is None


async def test_a_card_lives_until_its_message_expires_and_an_hour_more(session, make_user) -> None:
    habit = await _habit(session, make_user)
    token = await sharing.save(session, habit.user_id, b"jpeg", NOW, habit_id=habit.id)
    await sharing.keep_until(session, token, NOW + timedelta(hours=24), NOW)
    assert await sharing.image(session, token, NOW + timedelta(hours=25) - timedelta(seconds=1))
    assert await sharing.image(session, token, NOW + timedelta(hours=25)) is None
    assert await sharing.prune(session, NOW + timedelta(hours=25)) == 1
    assert (await session.scalars(select(ShareCard))).all() == []


async def test_a_card_is_never_kept_longer_than_a_week(session, make_user) -> None:
    habit = await _habit(session, make_user)
    token = await sharing.save(session, habit.user_id, b"jpeg", NOW, habit_id=habit.id)
    assert await sharing.image(session, token, NOW + timedelta(days=7)) is None  # no answer yet
    await sharing.keep_until(session, token, NOW + timedelta(days=30), NOW)
    card = await session.get(ShareCard, token)
    assert card is not None
    assert card.expires_at == NOW + timedelta(days=7)


async def test_a_user_keeps_only_the_newest_cards(session, make_user) -> None:
    habit = await _habit(session, make_user)
    other = await _habit(session, make_user, user_id=2)
    theirs = await sharing.save(session, other.user_id, b"theirs", NOW, habit_id=other.id)
    tokens = [
        await sharing.save(
            session, habit.user_id, b"%d" % n, NOW + timedelta(minutes=n), habit_id=habit.id
        )
        for n in range(sharing.PER_USER + 2)
    ]
    kept = set((await session.scalars(select(ShareCard.token))).all())
    assert kept == {theirs, *tokens[2:]}


async def test_a_picture_of_no_habit_is_kept_the_same_way(session, make_user) -> None:
    # The week's forecast: served by its token and counted among the user's newest pictures.
    habit = await _habit(session, make_user)
    forecast = await sharing.save(session, habit.user_id, b"week", NOW)
    assert await sharing.image(session, forecast, NOW) == b"week"
    assert (await session.get(ShareCard, forecast)).habit_id is None
    cards = [
        await sharing.save(
            session, habit.user_id, b"%d" % n, NOW + timedelta(minutes=n + 1), habit_id=habit.id
        )
        for n in range(sharing.PER_USER)
    ]
    kept = set((await session.scalars(select(ShareCard.token))).all())
    assert kept == set(cards)  # the forecast was the oldest of eleven


async def test_forget_removes_a_card(session, make_user) -> None:
    habit = await _habit(session, make_user)
    token = await sharing.save(session, habit.user_id, b"jpeg", NOW, habit_id=habit.id)
    await sharing.forget(session, token)
    assert await sharing.image(session, token, NOW) is None
