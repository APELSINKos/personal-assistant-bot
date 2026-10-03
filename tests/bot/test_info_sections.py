from __future__ import annotations

from aiogram.methods import AnswerCallbackQuery, SendMessage

from assistant.bot.keyboards import MoneyCb, RatesCb, SettingsCb
from tests.bot.fakes import callback_update, message_update

NBSP = " "


async def test_weather(feed, fake) -> None:
    await feed(message_update("🌤 Погода"))
    [reply] = fake.of(SendMessage)
    assert reply.text.startswith("🌤 Москва: +10°C, малооблачно")
    button = reply.reply_markup.inline_keyboard[0][0]
    assert SettingsCb.unpack(button.callback_data).action == "city"


async def test_weather_unavailable(feed, fake, meteo) -> None:
    meteo.fail = True
    await feed(message_update("🌤 Weather", lang="en"))
    assert fake.sent_texts() == ["⚠️ Couldn't get the weather. Please try again a bit later."]


async def test_today(feed, fake) -> None:
    await feed(message_update("📅 Мой день"))
    text = fake.sent_texts()[0]
    assert "📅 Сегодня, " in text and "🌤 Москва: +10°C" in text
    assert "📝 Заметок: 0" in text and "💵 84,20 ₽" in text


async def test_today_survives_upstream_failures(feed, fake, meteo, cbr) -> None:
    meteo.fail = cbr.fail = True
    await feed(message_update("📅 Мой день"))
    text = fake.sent_texts()[0]
    assert "🌤 Погода временно недоступна" in text and "💵" not in text


async def test_rates_and_converter(feed, fake) -> None:
    await feed(callback_update(MoneyCb(action="rates").pack()))  # «💰 Финансы» → «💱 Курсы»
    assert fake.sent_texts()[0].startswith("💱 Курс ЦБ РФ на 28 сентября")
    await feed(callback_update(RatesCb(source="USD", target="RUB").pack()))
    assert fake.sent_texts()[-1] == "Сколько USD перевести в RUB?"
    await feed(message_update(None, sticker=True))
    assert fake.sent_texts()[-1] == "Нужен текст. Напиши сумму числом, например 100 или 99,5."
    for bad in ("nan", "0", "-5", "1e10", "abc"):
        await feed(message_update(bad))
        assert fake.sent_texts()[-1].startswith("Нужно число больше нуля")
    await feed(message_update("100"))
    assert fake.sent_texts()[-1] == f"💱 100,00 USD = 8{NBSP}419,75 RUB"
    await feed(message_update("сто"))  # the dialog is over
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_converter_clears_state_when_rates_fail_at_conversion_time(feed, fake, cbr) -> None:
    await feed(callback_update(RatesCb(source="USD", target="RUB").pack()))
    cbr.fail = True
    await feed(message_update("100"))
    assert fake.sent_texts()[-1] == "⚠️ Не удалось получить курсы. Попробуй чуть позже."
    await feed(message_update("сто"))  # the dialog is over: state was cleared, not stuck
    assert fake.sent_texts()[-1].startswith("🤔")


async def test_converter_rejects_forged_pair(feed, fake) -> None:
    await feed(callback_update(RatesCb(source="RUB", target="RUB").pack()))
    [answer] = fake.of(AnswerCallbackQuery)
    assert answer.text == "Эта кнопка устарела — открой раздел заново из меню."
    assert fake.of(SendMessage) == []


async def test_rates_unavailable(feed, fake, cbr) -> None:
    cbr.fail = True
    await feed(callback_update(MoneyCb(action="rates").pack()))
    assert fake.sent_texts() == ["⚠️ Не удалось получить курсы. Попробуй чуть позже."]
