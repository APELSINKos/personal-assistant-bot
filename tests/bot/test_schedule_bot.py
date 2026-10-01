from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from assistant.bot.keyboards import ScheduleCb
from assistant.bot.routers import schedule as schedule_router
from assistant.core.models import ScheduleKind
from assistant.core.services import groups, schedule
from assistant.core.services.group_names import GroupHeader
from tests.bot.fakes import callback_update, message_update

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schedule"
MIREA = (FIXTURES / "mirea_ikbo_63_24.ics").read_bytes()
OUTLOOK = (FIXTURES / "outlook.ics").read_bytes()
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)  # Monday, 15:00 in Moscow
CONNECTED = "✅ Расписание подключено: ИКБО-63-24. Пар впереди: 36."
MONDAY = "🎓 Сегодня · понедельник, 28 сентября · 5 неделя\n\nПар нет 🎉"
WEDNESDAY = (
    "🎓 среда, 30 сентября · 5 неделя\n\n• 12:40–14:10 ПР Разработка баз данных · И-212-б (В-78)"
)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch) -> None:
    monkeypatch.setattr(schedule_router, "clock", lambda: NOW)


@pytest.fixture
def mirea(calendars):
    calendars.bodies[groups.calendar_url(4805)] = MIREA
    return calendars


async def directory(session, *names: tuple[int, str], ends: date = date(2026, 12, 31)) -> None:
    for group_id, name in names or ((4805, "ИКБО-63-24"),):
        await groups.remember(session, group_id, GroupHeader(name, ends), NOW)
    await session.commit()


def press(action: str, value: str = "") -> object:
    return callback_update(ScheduleCb(action=action, value=value).pack())


def buttons(message) -> list[str]:
    return [button.text for row in message.reply_markup.inline_keyboard for button in row]


async def test_the_section_offers_three_ways_to_connect(feed, fake) -> None:
    await feed(message_update("🎓 Расписание"))
    (reply,) = fake.of(SendMessage)
    assert reply.text.startswith("🎓 Расписание пар")
    assert buttons(reply) == ["🔎 Найти группу МИРЭА", "🔗 По ссылке", "📎 Файлом .ics"]


async def test_find_a_group_and_see_today(feed, fake, session, mirea) -> None:
    await directory(session)
    await feed(press("find"))
    assert fake.sent_texts()[-1] == "Напиши название группы, например ИКБО-63-24:"
    await feed(message_update("икбо-63"))
    assert fake.sent_texts()[-2:] == [CONNECTED, MONDAY]
    assert buttons(fake.of(SendMessage)[-1]) == ["‹", "Завтра", "›", "📅 Неделя", "⚙️ Источник"]
    source = await schedule.get_source(session, 1)
    assert source is not None and source.kind is ScheduleKind.MIREA
    await feed(message_update("🎓 Расписание"))  # the section now opens on today
    assert fake.sent_texts()[-1] == MONDAY


async def test_the_group_search_goes_by_the_section_clock(feed, fake, session, mirea) -> None:
    # The semester ends the day after NOW: by the section's clock the group is current, by the
    # real date it is over — a search by the real date would not find it.
    await directory(session, ends=NOW.date() + timedelta(days=1))
    await feed(press("find"))
    await feed(message_update("ИКБО-63-24"))
    assert fake.sent_texts()[-2:] == [CONNECTED, MONDAY]


async def test_several_groups_offer_a_choice(feed, fake, session, mirea) -> None:
    await directory(session, (4805, "ИКБО-63-24"), (4804, "ИКБО-62-24"))
    await feed(press("find"))
    await feed(message_update("ИКБО"))
    reply = fake.of(SendMessage)[-1]
    assert reply.text == "Нашлось несколько групп — выбери свою:"
    assert buttons(reply) == ["ИКБО-62-24", "ИКБО-63-24"]
    await feed(press("group", "4805"))
    assert fake.sent_texts()[-2:] == [CONNECTED, MONDAY]


async def test_no_such_group_and_a_directory_in_the_making(
    feed, fake, session, monkeypatch
) -> None:
    await feed(press("find"))
    assert fake.sent_texts()[-1].startswith("Справочник групп МИРЭА ещё собирается")
    await directory(session)  # the first full crawl has found one group so far
    await feed(press("find"))
    await feed(message_update("ЯЯЯЯ-01-99"))
    assert fake.sent_texts()[-1].startswith("Справочник групп МИРЭА ещё собирается")
    monkeypatch.setattr(groups, "PRUNE_MIN_FOUND", 1)  # a directory this small counts as built
    await groups.record_run(session, groups.FULL_JOB, NOW, "checked 6000, found 1")
    await session.commit()
    await feed(message_update("ЯЯЯЯ-01-99"))
    assert fake.sent_texts()[-1].startswith("Не нашёл группу «ЯЯЯЯ-01-99»")
    await feed(press("group", "4000"))  # a group missing from the directory
    assert fake.sent_texts()[-1] == "⚠️ Этой группы уже нет в справочнике — найди её заново."


async def test_connect_by_link(feed, fake, session, calendars) -> None:
    calendars.bodies["https://uni.example/t.ics"] = (FIXTURES / "foreign.ics").read_bytes()
    await feed(press("link"))
    await feed(message_update("http://uni.example/t.ics"))
    assert fake.sent_texts()[-1].startswith("⚠️ Эта ссылка не подходит")
    await feed(message_update("webcal://uni.example/t.ics"))  # still in the dialog: try again
    assert fake.sent_texts()[-2].startswith("✅ Расписание подключено: Physics 101.")
    source = await schedule.get_source(session, 1)
    assert source is not None and source.url == "https://uni.example/t.ics"


async def test_connect_by_file(feed, fake, session, monkeypatch) -> None:
    async def download(bot, file_id: str) -> bytes:
        assert file_id == "doc"
        return OUTLOOK

    monkeypatch.setattr(schedule_router, "download", download)
    await feed(press("file"))
    await feed(message_update("вот"))
    assert fake.sent_texts()[-1] == "Пришли файл календаря .ics."
    big = {"file_name": "big.ics", "file_size": schedule.FILE_LIMIT + 1}
    await feed(message_update(document=big))
    assert fake.sent_texts()[-1] == "⚠️ Календарь слишком большой: больше 2 МБ или 3000 занятий."
    await feed(message_update(document={"file_name": "Английский.ics", "file_size": 500}))
    # The Outlook fixture's only class is tomorrow, 29 September.
    assert fake.sent_texts()[-2] == "✅ Расписание подключено: Английский. Пар впереди: 1."


async def test_a_calendar_without_classes_is_connected_with_a_warning(
    feed, fake, monkeypatch
) -> None:
    async def download(bot, file_id: str) -> bytes:
        return "BEGIN:VCALENDAR\nVERSION:2.0\nX-WR-CALNAME:Пусто\nEND:VCALENDAR\n".encode()

    monkeypatch.setattr(schedule_router, "download", download)
    await feed(press("file"))
    await feed(message_update(document={"file_name": "empty.ics", "file_size": 60}))
    assert fake.sent_texts()[-2] == (
        "✅ Расписание подключено: Пусто. Но занятий на ближайшие месяцы в нём нет."
    )


async def connect(feed, session) -> None:
    await directory(session)
    await feed(press("find"))
    await feed(message_update("ИКБО-63-24"))


async def test_days_and_weeks(feed, fake, session, mirea) -> None:
    await connect(feed, session)
    await feed(press("day", "2026-09-30"))
    edited = fake.of(EditMessageText)[-1]
    assert edited.text == WEDNESDAY
    assert buttons(edited)[:3] == ["‹", "Сегодня", "›"]
    await feed(press("week", "2026-09-30"))
    assert fake.of(EditMessageText)[-1].text == (
        "🎓 5 неделя · 28 сентября – 4 октября\n"
        "\n"
        "ср, 30 сент.\n"
        "• 12:40–14:10 ПР Разработка баз данных · И-212-б (В-78)\n"
        "\n"
        "чт, 1 окт.\n"
        "• 09:00–10:30 ДОП Военная кафедра · ВУЦ (У-7/1)\n"
        "\n"
        "пт, 2 окт.\n"
        "• 09:00–10:30 ЛК Проектирование и разработка мобильных приложений на языке Котлин"
        " · А-18 (В-78)"
    )
    await feed(press("day"))  # «📅 День» from the week goes back to today
    assert fake.of(EditMessageText)[-1].text == MONDAY


async def test_the_source_its_refresh_and_alerts(feed, fake, session, mirea, monkeypatch) -> None:
    await connect(feed, session)
    await feed(press("src"))
    source_text = fake.of(EditMessageText)[-1].text
    assert source_text == (
        "⚙️ Источник расписания\n"
        "\n"
        "Группа МИРЭА: ИКБО-63-24\n"
        "Обновлено: 28 сент., 15:00\n"
        "🔕 Напоминания о парах выключены"
    )
    await feed(press("refresh"))  # connected this very minute
    assert fake.of(AnswerCallbackQuery)[-1].text == "Только что обновлял — подожди минуту"
    later = NOW + timedelta(minutes=2)
    monkeypatch.setattr(schedule_router, "clock", lambda: later)
    await feed(press("refresh"))
    assert "Обновлено: 28 сент., 15:02" in fake.of(EditMessageText)[-1].text
    await feed(press("alerts"))
    assert buttons(fake.of(EditMessageText)[-1])[:4] == [
        "✓ Не напоминать",
        "За 5 мин",
        "За 10 мин",
        "За 15 мин",
    ]
    await feed(press("alert", "15"))
    assert fake.of(EditMessageText)[-1].text.endswith("🔔 Напоминаю о парах за 15 мин")
    await feed(press("alert", "7"))  # not one of the choices
    assert fake.of(AnswerCallbackQuery)[-1].text.startswith("Эта кнопка устарела")


async def test_disconnect(feed, fake, session, mirea) -> None:
    await connect(feed, session)
    await feed(press("off"))
    assert fake.of(EditMessageText)[-1].text.startswith("Отключить расписание?")
    await feed(press("offyes"))
    assert fake.of(AnswerCallbackQuery)[-1].text == "Расписание отключено."
    assert await schedule.get_source(session, 1) is None
    await feed(press("day", "2026-09-30"))  # a button of the old timetable
    assert fake.of(AnswerCallbackQuery)[-1].text.startswith("Эта кнопка устарела")


async def test_a_forged_day_is_a_stale_button(feed, fake, session, mirea) -> None:
    await connect(feed, session)
    for value in ("yesterday", "9999-12-31"):
        await feed(press("day", value))
        assert fake.of(AnswerCallbackQuery)[-1].text.startswith("Эта кнопка устарела")


async def test_old_data_is_marked(feed, fake, session, mirea, monkeypatch) -> None:
    await connect(feed, session)
    later = NOW + timedelta(days=4)
    monkeypatch.setattr(schedule_router, "clock", lambda: later)
    await feed(message_update("🎓 Расписание"))
    assert fake.sent_texts()[-1].endswith("⚠️ Данные от 28 сентября — источник пока недоступен.")
