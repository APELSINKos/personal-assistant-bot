from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerCallbackQuery, SendMessage
from sqlalchemy import select

from assistant.bot.keyboards import ReminderCb, SettingsCb
from assistant.bot.routers import reminders as reminders_router
from assistant.core.models import Reminder, ReminderStatus, Repeat
from assistant.core.services import reminders
from tests.bot.fakes import callback_update, message_update

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # Monday, 15:00 in Moscow
ASK_TIME = "🕘 Во сколько? Выбери или напиши, например 18:30 или «завтра в 10»."


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW)


async def all_reminders(session) -> list[Reminder]:
    session.expire_all()
    return list((await session.scalars(select(Reminder).order_by(Reminder.id))).all())


def last_markup_texts(fake) -> list[str]:
    markup = fake.of(SendMessage)[-1].reply_markup
    return [button.text for row in markup.inline_keyboard for button in row]


def button_data(fake, text: str) -> str:
    """The callback data of the newest sent button with this text."""
    for sent in reversed(fake.of(SendMessage)):
        markup = sent.reply_markup
        for row in getattr(markup, "inline_keyboard", None) or []:
            for button in row:
                if button.text == text:
                    return button.callback_data
    raise AssertionError(f"no button {text!r}")


async def test_a_phrase_anywhere_shows_a_card_and_creates(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    assert fake.sent_texts()[-1] == "⏰ Завтра, 09:00 — купить молоко"
    assert last_markup_texts(fake) == ["✅ Создать", "🕘 Другое время", "✖️ Отмена"]
    assert await all_reminders(session) == []
    await feed(callback_update(button_data(fake, "✅ Создать")))
    assert fake.sent_texts()[-1] == "✅ Напомню 29 сентября в 09:00: купить молоко"
    (stored,) = await all_reminders(session)
    assert stored.due_at == datetime(2026, 9, 29, 6, 0, tzinfo=UTC)


async def test_casual_message_never_creates_without_a_press(feed, fake, session) -> None:
    await feed(message_update("завтра экзамен, волнуюсь"))
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("привет"))  # not a time: ask again
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("/cancel"))
    assert await all_reminders(session) == []


async def test_missing_time_from_a_button(feed, fake, session) -> None:
    await feed(message_update("завтра позвонить маме"))
    assert fake.sent_texts()[-1] == ASK_TIME
    assert last_markup_texts(fake) == ["09:00", "12:00", "18:00", "✖️ Отмена"]
    await feed(callback_update(button_data(fake, "18:00")))
    assert fake.sent_texts()[-1] == "⏰ Завтра, 18:00 — позвонить маме"
    await feed(callback_update(button_data(fake, "✅ Создать")))
    (stored,) = await all_reminders(session)
    assert stored.due_at == datetime(2026, 9, 29, 15, 0, tzinfo=UTC)


async def test_a_repeat_card_and_the_list(feed, fake, session) -> None:
    await feed(message_update("по будням в 7:30 зарядка"))
    assert fake.sent_texts()[-1] == "↻ по будням в 07:30 — зарядка\nПервый раз: Завтра, 07:30"
    await feed(callback_update(button_data(fake, "✅ Создать")))
    assert fake.sent_texts()[-1] == "✅ Буду напоминать по будням в 07:30: зарядка"
    (stored,) = await all_reminders(session)
    assert stored.repeat is Repeat.WEEKLY and stored.weekdays == 31
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Твои напоминания (1/20):\n\n1. ↻ по будням в 07:30 — зарядка"
    )


async def test_another_time_and_cancel(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    await feed(callback_update(button_data(fake, "🕘 Другое время")))
    assert fake.sent_texts()[-1] == ASK_TIME
    await feed(message_update("послезавтра в 10"))
    assert fake.sent_texts()[-1] == "⏰ Послезавтра, 10:00 — купить молоко"
    await feed(callback_update(button_data(fake, "✖️ Отмена")))
    assert fake.sent_texts()[-1] == "Отменено."
    assert await all_reminders(session) == []
    await feed(callback_update(button_data(fake, "✅ Создать")))  # the card is gone
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert await all_reminders(session) == []


async def test_a_past_time_asks_again(feed, fake) -> None:
    await feed(message_update("сегодня в 10 кино"))
    assert fake.sent_texts()[-2:] == ["Это время уже прошло. Укажи момент в будущем:", ASK_TIME]


async def test_the_add_button_asks_for_a_phrase(feed, fake) -> None:
    await feed(message_update("⏰ Напоминания"))
    assert fake.sent_texts()[-1] == (
        "⏰ Активных напоминаний нет. Нажми «➕ Добавить», чтобы создать."
    )
    await feed(callback_update(ReminderCb(action="add").pack()))
    assert fake.sent_texts()[-1].startswith("✍️ Напиши, о чём и когда напомнить.")
    await feed(message_update("купить хлеб"))
    assert fake.sent_texts()[-1].startswith("🤔 Не нашёл, когда напомнить.")
    await feed(message_update("через 20 минут чай"))
    assert fake.sent_texts()[-1] == "⏰ Сегодня, 15:20 — чай"


async def test_a_phrase_without_text_asks_what(feed, fake) -> None:
    await feed(message_update("завтра в 9"))
    assert fake.sent_texts()[-1].startswith("✍️ О чём напомнить?")


async def test_deleting_a_repeat_asks_first(feed, fake, session, make_user) -> None:
    await feed(message_update("каждый день в 21 таблетки"))
    await feed(callback_update(button_data(fake, "✅ Создать")))
    (series,) = await all_reminders(session)
    await feed(callback_update(ReminderCb(action="delask", id=series.id).pack()))
    assert fake.sent_texts()[-1] == "Удалить повтор «таблетки» целиком?"
    await feed(callback_update(ReminderCb(action="del", id=series.id).pack()))
    (series,) = await all_reminders(session)
    assert series.status is ReminderStatus.CANCELLED


async def test_cancel_by_button_double_tap_and_foreign(feed, fake, session, make_user) -> None:
    user = await make_user()
    reminder = await reminders.create(session, user, "созвон", datetime(2099, 1, 1, 10, 0))
    await session.commit()
    data = ReminderCb(action="del", id=reminder.id).pack()
    await feed(callback_update(data, user_id=2))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(callback_update(data))
    await feed(callback_update(data))
    assert [a.text for a in fake.of(AnswerCallbackQuery)[-2:]] == ["🗑 Удалено", "Этого уже нет."]
    await session.refresh(reminder)
    assert reminder.status == ReminderStatus.CANCELLED


async def test_an_old_card_is_gone(feed, fake, session, monkeypatch) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    ok = button_data(fake, "✅ Создать")
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW + timedelta(hours=25))
    await feed(callback_update(ok))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert await all_reminders(session) == []


async def test_a_card_pressed_after_its_time_asks_again(feed, fake, session, monkeypatch) -> None:
    await feed(message_update("через 20 минут чай"))
    ok = button_data(fake, "✅ Создать")
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW + timedelta(minutes=30))
    await feed(callback_update(ok))
    assert fake.sent_texts()[-2:] == ["Это время уже прошло. Укажи момент в будущем:", ASK_TIME]
    assert await all_reminders(session) == []


async def test_a_repeat_card_pressed_later_starts_from_the_press(
    feed, fake, session, monkeypatch
) -> None:
    await feed(message_update("каждый день в 21 таблетки"))
    ok = button_data(fake, "✅ Создать")
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW + timedelta(hours=7))
    await feed(callback_update(ok))
    (stored,) = await all_reminders(session)
    assert stored.due_at == datetime(2026, 9, 29, 18, 0, tzinfo=UTC)
    assert stored.anchor_date == date(2026, 9, 29)


async def test_an_older_card_cannot_create_a_newer_one(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    old_ok = button_data(fake, "✅ Создать")
    await feed(message_update("через 20 минут чай"))
    await feed(callback_update(old_ok))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert await all_reminders(session) == []
    await feed(callback_update(button_data(fake, "✅ Создать")))
    (stored,) = await all_reminders(session)
    assert stored.text == "чай"


async def test_a_long_text_is_refused_before_the_card(feed, fake) -> None:
    await feed(message_update("завтра в 9 " + "x" * 250))
    assert fake.sent_texts()[-1] == "✍️ Слишком длинно — до 200 символов. Напиши фразу короче."
    assert not any(
        button.text == "✅ Создать"
        for sent in fake.of(SendMessage)
        for row in getattr(sent.reply_markup, "inline_keyboard", None) or []
        for button in row
    )


async def test_the_limit_on_create(feed, fake, session, make_user) -> None:
    user = await make_user()
    for i in range(20):
        await reminders.create(session, user, f"r{i}", datetime(2026, 9, 29, 9, i), now=NOW)
    await session.commit()
    await feed(message_update("завтра в 9 купить молоко"))
    await feed(callback_update(button_data(fake, "✅ Создать")))
    assert fake.sent_texts()[-1] == "Достигнут лимит — 20 напоминаний. Удали лишние."
    assert len(await all_reminders(session)) == 20


async def test_the_english_card(feed, fake) -> None:
    await feed(message_update("tomorrow at 9 buy milk", lang="en"))
    assert fake.sent_texts()[-1] == "⏰ Tomorrow, 09:00 — buy milk"


async def test_a_reply_while_a_card_is_open_points_to_it(feed, fake) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    await feed(message_update("ок"))
    assert fake.sent_texts()[-1] == "Нажми «✅ Создать» под карточкой — или напиши новую фразу."


async def state_of(dp, bot) -> str | None:
    return await dp.storage.get_state(StorageKey(bot_id=bot.id, chat_id=1, user_id=1))


async def test_a_new_phrase_at_the_time_prompt_gets_its_own_card(feed, fake, session) -> None:
    await feed(message_update("завтра экзамен, волнуюсь"))
    assert fake.sent_texts()[-1] == ASK_TIME
    prompt_card = ReminderCb.unpack(button_data(fake, "18:00")).id
    await feed(message_update("завтра в 9 купить молоко"))
    assert fake.sent_texts()[-1] == "⏰ Завтра, 09:00 — купить молоко"
    ok = button_data(fake, "✅ Создать")
    assert ReminderCb.unpack(ok).id != prompt_card
    await feed(callback_update(ok))
    (stored,) = await all_reminders(session)
    assert (stored.text, stored.due_at) == (
        "купить молоко",
        datetime(2026, 9, 29, 6, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("answer", "card"),
    [
        ("18:30", "⏰ Завтра, 18:30 — экзамен, волнуюсь"),
        ("в 18", "⏰ Завтра, 18:00 — экзамен, волнуюсь"),
        ("завтра в 10", "⏰ Завтра, 10:00 — экзамен, волнуюсь"),
        ("в 18 обязательно", "⏰ Завтра, 18:00 — экзамен, волнуюсь"),
    ],
)
async def test_a_bare_answer_completes_the_first_draft(feed, fake, answer, card) -> None:
    await feed(message_update("завтра экзамен, волнуюсь"))
    await feed(message_update(answer))
    assert fake.sent_texts()[-1] == card


async def test_an_old_time_prompt_is_no_dialog(feed, fake, dp, bot, monkeypatch) -> None:
    await feed(message_update("завтра экзамен, волнуюсь"))
    assert await state_of(dp, bot) is not None
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW + timedelta(hours=25))
    await feed(message_update("привет"))
    assert fake.sent_texts()[-1].startswith("🤔 Не понял.")
    assert await state_of(dp, bot) is None


async def test_an_old_card_does_not_take_a_reply(feed, fake, dp, bot, monkeypatch) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    monkeypatch.setattr(reminders_router, "clock", lambda: NOW + timedelta(hours=25))
    await feed(message_update("ок"))
    assert fake.sent_texts()[-1].startswith("🤔 Не понял.")
    assert await state_of(dp, bot) is None
    await feed(message_update("послезавтра в 10 кино"))  # a phrase still makes a card
    assert fake.sent_texts()[-1] == "⏰ Послезавтра, 10:00 — кино"


@pytest.mark.parametrize("value", ["25:99", "abc", ""])
async def test_a_forged_time_button_changes_nothing(feed, fake, dp, bot, value) -> None:
    await feed(message_update("завтра позвонить маме"))
    card = ReminderCb.unpack(button_data(fake, "18:00")).id
    sent = len(fake.sent_texts())
    await feed(callback_update(ReminderCb(action="t", id=card, value=value).pack()))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    assert len(fake.sent_texts()) == sent
    assert await state_of(dp, bot) == "ReminderForm:time"
    await feed(callback_update(button_data(fake, "18:00")))  # the real buttons still work
    assert fake.sent_texts()[-1] == "⏰ Завтра, 18:00 — позвонить маме"


async def test_the_time_prompt_can_be_cancelled(feed, fake) -> None:
    await feed(message_update("завтра позвонить маме"))
    await feed(callback_update(button_data(fake, "✖️ Отмена")))
    assert fake.sent_texts()[-1] == "Отменено."
    await feed(message_update("привет"))
    assert fake.sent_texts()[-1].startswith("🤔 Не понял.")


async def test_a_date_next_year_shows_the_year(feed, fake) -> None:
    await feed(message_update("29.02 в 10 тест"))
    assert fake.sent_texts()[-1] == "⏰ вт, 29 февр. 2028, 10:00 — тест"


async def test_a_stale_card_does_not_break_another_dialog(feed, fake, session) -> None:
    await feed(message_update("завтра в 9 купить молоко"))
    old_ok = button_data(fake, "✅ Создать")
    await feed(callback_update(SettingsCb(action="city").pack()))  # an unrelated dialog starts
    await feed(callback_update(old_ok))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Этого уже нет."
    await feed(message_update("Москва"))  # the city dialog must still be listening
    assert fake.sent_texts()[-1] == "Не нашёл город «Москва». Проверь название и напиши ещё раз:"
    assert await all_reminders(session) == []


def test_looks_like_reminder() -> None:
    assert reminders_router.looks_like_reminder("завтра в 9 купить молоко")
    assert not reminders_router.looks_like_reminder("купить 2 батона")
