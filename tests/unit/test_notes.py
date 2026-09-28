from __future__ import annotations

import pytest

from assistant.core.errors import InvalidInput, LimitReached, NotFound
from assistant.core.services import notes


async def test_create_strips_and_keeps_order(session, make_user) -> None:
    await make_user()
    await notes.create(session, 1, "  купить хлеб  ")
    await notes.create(session, 1, "позвонить маме")
    assert [n.text for n in await notes.all_for(session, 1)] == ["купить хлеб", "позвонить маме"]


@pytest.mark.parametrize(("length", "ok"), [(1, True), (499, True), (500, True), (501, False)])
async def test_length_boundaries(session, make_user, length: int, ok: bool) -> None:
    await make_user()
    if ok:
        assert len((await notes.create(session, 1, "x" * length)).text) == length
    else:
        with pytest.raises(InvalidInput) as error:
            await notes.create(session, 1, "x" * length)
        assert error.value.params["limit"] == 500


@pytest.mark.parametrize("text", ["", "   ", "\n"])
async def test_empty_rejected(session, make_user, text: str) -> None:
    await make_user()
    with pytest.raises(InvalidInput):
        await notes.create(session, 1, text)


async def test_limit_of_50(session, make_user) -> None:
    await make_user()
    for i in range(50):
        await notes.create(session, 1, f"n{i}")
    with pytest.raises(LimitReached):
        await notes.create(session, 1, "one more")


async def test_other_users_note_is_invisible(session, make_user) -> None:
    await make_user(id=1)
    await make_user(id=2)
    note = await notes.create(session, 1, "secret")
    assert await notes.delete(session, 2, note.id) is False
    with pytest.raises(NotFound):
        await notes.update(session, 2, note.id, "hacked")
    assert await notes.delete(session, 1, note.id) is True
    assert await notes.delete(session, 1, note.id) is False
