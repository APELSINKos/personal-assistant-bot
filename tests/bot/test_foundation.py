from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import Message, ReplyKeyboardMarkup
from sqlalchemy import func, select

from assistant.bot import sections
from assistant.bot.context import Ctx
from assistant.bot.fsm_storage import current_session
from assistant.bot.keyboards import menu_key, paginate, preview
from assistant.core.models import User
from assistant.core.services import users
from tests.bot.fakes import callback_update, message_update


class Demo(StatesGroup):
    waiting = State()


async def _swallow(message: Message, ctx: Ctx) -> None:
    await message.answer("SAVED " + (message.text or ""))


async def _enter(message: Message, ctx: Ctx) -> None:
    await ctx.state.set_state(Demo.waiting)
    await ctx.state.update_data(hint="cmd-cancel")


def demo_router() -> Router:
    router = Router(name="demo")
    router.message.register(_swallow, Demo.waiting, F.text)
    router.message.register(_enter, F.text == "go")
    return router


async def test_start_creates_user_and_shows_menu(feed, fake, session) -> None:
    await feed(message_update("/start"))
    [reply] = fake.of(SendMessage)
    assert "Привет, Alex" in reply.text
    assert isinstance(reply.reply_markup, ReplyKeyboardMarkup)
    assert (await session.get(User, 1)) is not None


async def test_english_user_gets_english(feed, fake) -> None:
    await feed(message_update("/start", lang="en"))
    assert fake.sent_texts()[0].startswith("👋 Hi, Alex")


async def test_group_messages_are_ignored(feed, fake, session) -> None:
    await feed(message_update("/start", chat_type="group"))
    await feed(message_update("🌤 Погода", chat_type="supergroup"))
    assert fake.calls == []
    assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_menu_label_in_other_language_opens_section(feed, monkeypatch) -> None:
    opened: list[str] = []

    async def show(message: Message, ctx: Ctx) -> None:
        opened.append(ctx.lang)

    monkeypatch.setitem(sections.SECTIONS, "weather", show)
    await feed(message_update("🌤 Weather", lang="ru"))
    await feed(message_update("🌤 Погода", lang="en"))
    assert opened == ["ru", "en"]


async def test_menu_button_mid_dialog_clears_state(make_dp, feed, fake, monkeypatch) -> None:
    dispatcher = make_dp([demo_router()])
    opened: list[str] = []

    async def show(message: Message, ctx: Ctx) -> None:
        opened.append("notes")

    monkeypatch.setitem(sections.SECTIONS, "notes", show)
    await feed(message_update("go"), dispatcher)
    await feed(message_update("📝 Заметки"), dispatcher)
    await feed(message_update("hello"), dispatcher)
    assert opened == ["notes"]
    assert not any(text.startswith("SAVED") for text in fake.sent_texts())
    assert not any(text.startswith("⚠️") for text in fake.sent_texts())


async def test_command_mid_dialog_clears_state(make_dp, feed, fake) -> None:
    dispatcher = make_dp([demo_router()])
    await feed(message_update("go"), dispatcher)
    await feed(message_update("/start"), dispatcher)
    await feed(message_update("hello"), dispatcher)
    assert not any(text.startswith("SAVED") for text in fake.sent_texts())
    assert not any(text.startswith("⚠️") for text in fake.sent_texts())


async def test_sticker_in_dialog_asks_for_text_and_keeps_state(make_dp, feed, fake) -> None:
    dispatcher = make_dp([demo_router()])
    await feed(message_update("go"), dispatcher)
    await feed(message_update(None, sticker=True), dispatcher)
    assert fake.sent_texts()[-1] == "Нужен текст. Отменить ввод"
    await feed(message_update("after"), dispatcher)
    assert fake.sent_texts()[-1] == "SAVED after"


async def test_write_lock_is_released_before_sending_the_reply(feed, fake, monkeypatch) -> None:
    lock_released: list[bool] = []

    def on_request(method: object) -> None:
        if isinstance(method, SendMessage):
            session = current_session.get()
            lock_released.append(session is None or not session.in_transaction())

    fake.on_request = on_request

    async def show(message: Message, ctx: Ctx) -> None:
        # A write straight through ctx.session (not via SqliteStorage, which already
        # commits its own writes immediately) — only CommitBeforeRequest can release
        # this one before the send below.
        ctx.user.first_name = "Changed"
        await ctx.session.flush()
        await message.answer("ok")

    monkeypatch.setitem(sections.SECTIONS, "weather", show)
    await feed(message_update("🌤 Погода"))
    assert lock_released == [True]


async def test_cancel_and_unknown(feed, fake) -> None:
    await feed(message_update("/cancel"))
    await feed(message_update("❌ Cancel"))
    await feed(message_update("что-то непонятное"))
    await feed(message_update(None, sticker=True))
    assert fake.sent_texts() == [
        "Отменено.",
        "Отменено.",
        "🤔 Не понял. Выбери раздел в меню ниже 👇\n"
        "Чтобы создать напоминание, просто напиши, например: «завтра в 9 купить молоко».",
        "🤔 Не понял. Выбери раздел в меню ниже 👇\n"
        "Чтобы создать напоминание, просто напиши, например: «завтра в 9 купить молоко».",
    ]


async def test_unknown_button_is_answered(feed, fake) -> None:
    await feed(callback_update("note_add"))  # a button from a v1 message
    [answer] = [c for c in fake.calls if type(c).__name__ == "AnswerCallbackQuery"]
    assert answer.text == "Эта кнопка устарела — открой раздел заново из меню."


async def test_handler_crash_gives_generic_error(feed, fake, monkeypatch) -> None:
    async def boom(message: Message, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(sections.SECTIONS, "rates", boom)
    await feed(message_update("💱 Курс валют"))
    assert fake.sent_texts()[-1].startswith("⚠️")


async def test_callback_crash_answers_query_and_gives_generic_error(make_dp, feed, fake) -> None:
    async def boom(query, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    router = Router(name="boom")
    router.callback_query.register(boom)
    dispatcher = make_dp([router])
    await feed(callback_update("whatever"), dispatcher)
    assert any(type(c).__name__ == "AnswerCallbackQuery" for c in fake.calls)
    assert fake.sent_texts()[-1].startswith("⚠️")


async def test_current_session_is_cleared_after_feed(feed, fake) -> None:
    await feed(message_update("/start"))
    assert current_session.get() is None


async def test_current_session_is_cleared_after_a_crash(feed, fake, monkeypatch) -> None:
    async def boom(message: Message, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(sections.SECTIONS, "rates", boom)
    await feed(message_update("💱 Курс валют"))
    assert current_session.get() is None


async def test_app_command_without_webapp(feed, fake) -> None:
    await feed(message_update("/app"))
    assert fake.sent_texts() == ["📱 Приложение скоро появится — следи за обновлениями."]


def test_helpers() -> None:
    assert menu_key("⚙️ Settings") == "settings"
    assert menu_key("nope") is None and menu_key(None) is None
    assert preview("a" * 70) == "a" * 59 + "…"
    assert preview("line1\nline2") == "line1 line2"
    items = list(range(12))
    assert paginate(items, 2) == ([10, 11], 2, 3)
    assert paginate(items, 99) == ([10, 11], 2, 3)
    assert paginate(items, -1) == ([0, 1, 2, 3, 4], 0, 3)
    assert paginate([], 0) == ([], 0, 1)


TOO_OLD = "Bad Request: query is too old and response timeout expired or query ID is invalid"


async def test_expired_query_does_not_stop_the_error_message(make_dp, feed, fake) -> None:
    async def boom(query, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    router = Router(name="boom")
    router.callback_query.register(boom)
    fake.errors.append(
        TelegramBadRequest(method=AnswerCallbackQuery(callback_query_id="1"), message=TOO_OLD)
    )
    await feed(callback_update("whatever"), make_dp([router]))
    assert [type(c).__name__ for c in fake.calls] == ["AnswerCallbackQuery", "SendMessage"]
    assert fake.sent_texts() == ["⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже."]


async def test_error_message_uses_the_saved_language(feed, fake, make_user, monkeypatch) -> None:
    await make_user(language="en")

    async def boom(message: Message, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(sections.SECTIONS, "rates", boom)
    await feed(message_update("💱 Курс валют", lang="ru"))  # Telegram says Russian
    assert fake.sent_texts()[-1] == "⚠️ Something went wrong. Please try again a bit later."


async def test_error_message_falls_back_to_telegram_language(
    feed, fake, make_user, monkeypatch
) -> None:
    await make_user(language="en")

    async def boom(message: Message, ctx: Ctx) -> None:
        raise RuntimeError("boom")

    async def broken_get(session, user_id):
        raise RuntimeError("database is locked")

    monkeypatch.setitem(sections.SECTIONS, "rates", boom)
    monkeypatch.setattr(users, "get", broken_get)
    await feed(message_update("💱 Курс валют", lang="ru"))
    assert fake.sent_texts()[-1] == "⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже."
