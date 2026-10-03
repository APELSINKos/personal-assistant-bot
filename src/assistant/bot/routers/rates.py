"""💱 Exchange rates of the Bank of Russia and a RUB ⇄ USD/EUR converter, reached from
«💰 Финансы»."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from assistant.bot import replies, texts
from assistant.bot.context import Ctx
from assistant.bot.keyboards import MoneyCb, RatesCb, cancel_menu, main_menu
from assistant.bot.states import RatesForm
from assistant.core.errors import UpstreamUnavailable
from assistant.core.i18n import Translator, format_number
from assistant.core.services.rates import convert, parse_amount

PAIRS = (("USD", "RUB"), ("EUR", "RUB"), ("RUB", "USD"), ("RUB", "EUR"))
_SIGN = {"USD": "USD", "EUR": "EUR", "RUB": "₽"}


def converter_markup(t: Translator) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{_SIGN[source]} → {_SIGN[target]}",
            callback_data=RatesCb(source=source, target=target).pack(),
        )
        for source, target in PAIRS
    ]
    chart = InlineKeyboardButton(
        text=t("button-rates-chart"), callback_data=MoneyCb(action="chart").pack()
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:2], buttons[2:], [chart]])


async def send_rates(bot: Bot, user_id: int, ctx: Ctx) -> None:
    """The day's rates with the converter and the 30-day picture."""
    try:
        rates = await ctx.cbr.daily()
    except UpstreamUnavailable:
        await bot.send_message(user_id, ctx.t("rates-unavailable"))
        return
    await bot.send_message(
        user_id,
        texts.rates_text(rates, ctx.t, ctx.user.currency),
        reply_markup=converter_markup(ctx.t),
    )


async def ask_amount(query: CallbackQuery, callback_data: RatesCb, ctx: Ctx, bot: Bot) -> None:
    pair = (callback_data.source, callback_data.target)
    if pair not in PAIRS:
        await query.answer(ctx.t("stale-button"))
        return
    await query.answer()
    await ctx.state.set_state(RatesForm.amount)
    await ctx.state.set_data({"source": pair[0], "target": pair[1], "hint": "hint-amount"})
    await replies.send(
        bot, query, ctx.t("rates-ask", source=pair[0], target=pair[1]), cancel_menu(ctx.t)
    )


async def convert_amount(message: Message, ctx: Ctx) -> None:
    data = await ctx.state.get_data()
    pair = (data.get("source"), data.get("target"))
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(ctx.t("rates-bad-amount"))
        return
    await ctx.state.clear()
    if pair not in PAIRS:
        await message.answer(ctx.t("unknown"), reply_markup=main_menu(ctx.t))
        return
    source, target = str(pair[0]), str(pair[1])
    try:
        rates = await ctx.cbr.daily()
    except UpstreamUnavailable:
        await message.answer(ctx.t("rates-unavailable"), reply_markup=main_menu(ctx.t))
        return
    result = convert(amount, source, target, rates)
    await message.answer(
        ctx.t(
            "rates-result",
            amount=format_number(amount, ctx.lang),
            source=source,
            result=format_number(result, ctx.lang),
            target=target,
        ),
        reply_markup=main_menu(ctx.t),
    )


def create_router() -> Router:
    router = Router(name="rates")
    router.callback_query.register(ask_amount, RatesCb.filter())
    router.message.register(convert_amount, RatesForm.amount, F.text)
    return router
