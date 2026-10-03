"""💰 Финансы: the month so far, its report picture and the bank's rates."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from assistant.bot.context import Ctx
from assistant.bot.keyboards import MoneyCb
from assistant.bot.money_texts import money, section_text
from assistant.bot.routers.rates import send_rates
from assistant.bot.sections import section
from assistant.core.errors import UpstreamUnavailable
from assistant.core.services import money as money_service
from assistant.core.services import money_cards, money_month
from assistant.core.timeutil import local_today

RATE_LINES = ("USD", "EUR")


def _button(text: str, data: MoneyCb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())


def section_markup(ctx: Ctx) -> InlineKeyboardMarkup:
    t = ctx.t
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(t("button-money-report"), MoneyCb(action="report")),
                _button(t("button-money-rates"), MoneyCb(action="rates")),
            ]
        ]
    )


async def names(ctx: Ctx) -> dict[int, str]:
    """Every category's name in the user's language."""
    found = await money_service.categories(ctx.session, ctx.user)
    return {item.id: money_service.name_of(item, ctx.t) for item in found}


@section("money")
async def show_money(message: Message, ctx: Ctx) -> None:
    month = await money_month.month(ctx.session, ctx.user)
    text = section_text(month, await names(ctx), ctx.user.currency, ctx.t)
    await message.answer(text, reply_markup=section_markup(ctx))


def _month(value: str, today: date) -> date | None:
    """The month a report button asks for: «» is this one; a forged or future one is None."""
    if not value:
        return today.replace(day=1)
    try:
        first = datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        return None
    return first if first <= today else None


async def on_report(query: CallbackQuery, callback_data: MoneyCb, ctx: Ctx, bot: Bot) -> None:
    """The month as a picture, to forward anywhere; a button under it shows the month before."""
    today = local_today(ctx.user.timezone)
    first = _month(callback_data.value, today)
    if first is None:
        await query.answer(ctx.t("stale-button"))
        return
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    await query.answer()
    month = await money_month.month(ctx.session, ctx.user, first)
    me = await bot.me()
    report = money_cards.report_for(month, await names(ctx), ctx.user.currency, me.username or "")
    image = await money_cards.draw_report(report, ctx.t)
    previous = (first - timedelta(days=1)).replace(day=1)
    oldest = await money_month.first_month(ctx.session, ctx.user)
    markup = None
    if oldest is not None and oldest <= previous:
        title = money_cards.month_title(previous, ctx.lang)
        data = MoneyCb(action="report", value=previous.strftime("%Y-%m"))
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[_button(ctx.t("button-money-previous", month=title), data)]]
        )
    caption = ctx.t(
        "money-report-caption",
        month=money_cards.month_title(first, ctx.lang),
        amount=money(month.spent, ctx.user.currency, ctx.t),
    )
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="money.jpg"),
        caption=caption,
        reply_markup=markup,
    )


async def on_rates(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    await query.answer()
    await send_rates(bot, ctx.user.id, ctx)


async def on_chart(query: CallbackQuery, ctx: Ctx, bot: Bot) -> None:
    """USD and EUR over 30 days as a picture."""
    wait = ctx.cards.check(ctx.user.id)
    if wait is not None:
        await query.answer(ctx.t("habit-cards-wait", seconds=math.ceil(wait)), show_alert=True)
        return
    await query.answer()
    try:
        lines = tuple([(code, tuple(await ctx.cbr.history(code))) for code in RATE_LINES])
    except (UpstreamUnavailable, LookupError):
        await bot.send_message(ctx.user.id, ctx.t("rates-unavailable"))
        return
    me = await bot.me()
    card = money_cards.RatesCard(lines, local_today(ctx.user.timezone), me.username or "")
    image = await money_cards.draw_rates(card, ctx.t)
    await bot.send_photo(
        ctx.user.id,
        BufferedInputFile(image, filename="rates.jpg"),
        caption=ctx.t("rates-card-caption"),
    )


def create_router() -> Router:
    router = Router(name="money")
    router.callback_query.register(on_report, MoneyCb.filter(F.action == "report"))
    router.callback_query.register(on_rates, MoneyCb.filter(F.action == "rates"))
    router.callback_query.register(on_chart, MoneyCb.filter(F.action == "chart"))
    return router
