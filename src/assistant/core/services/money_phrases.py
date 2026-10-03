"""Amounts and the quick input «кофе 250»: reading an amount and a phrase, guessing a category
from the words, and showing an amount in the user's currency.

No AI: a small grammar and a word list (money_dictionary), like the reminder phrases. The amount
goes at the end («кофе 250»), or first with a sign or a currency («+5000 стипендия», «250₽ кофе»),
or first and bare when the next word names a category («250 кофе»), or alone («1 200»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from babel.numbers import format_decimal

from assistant.core.config import LIMITS
from assistant.core.money_dictionary import STEMS, WORDS
from assistant.core.money_style import CURRENCIES

NBSP = "\u00a0"
MAX_WORDS = 8  # in the whole phrase, the amount included
MAX_LENGTH = 100
BARE_MINIMUM = 1000  # «250 кофе»: a bare number first is money from 10 up (below, a quantity)
DAYS_AGO = {"вчера": 1, "позавчера": 2, "yesterday": 1}
# Words around the amount that are not part of the note: «хлеб за 85», «taxi for 300».
CONNECTIVES = frozenset({"за", "на", "for", "on", "—", "–", "-", ":", "="})
# A number after one of these is a time or a date, not money: «встреча в 9».
TIME_WORDS = frozenset(
    {"в", "во", "к", "до", "с", "со", "через", "после", "at", "by", "until", "after", "in"}
)
# A number before one of these is a quantity: «2 литра молока», «3 кг».
UNITS = frozenset(
    {
        "шт", "штук", "штуки", "штука", "кг", "г", "гр", "грамм", "граммов", "л", "литр",
        "литра", "литров", "мл", "км", "м", "метр", "метра", "метров", "мин", "минут",
        "минуты", "минуту", "ч", "час", "часа", "часов", "сек", "секунд", "раз", "раза", "%",
        "x", "х", "лет", "год", "года", "день", "дня", "дней", "недель", "недели", "неделю",
        "месяц", "месяца", "месяцев", "человек", "чел", "пара", "пары", "пар", "pcs", "kg",
        "g", "l", "ml", "km", "min", "mins", "minutes", "h", "hr", "hours", "times", "days",
        "weeks", "months", "years", "people",
    }
)  # fmt: skip
# Currency signs and words → ISO code.
MARKERS: dict[str, str] = {
    "₽": "RUB", "р": "RUB", "р.": "RUB", "руб": "RUB", "руб.": "RUB", "рубль": "RUB",
    "рубля": "RUB", "рублей": "RUB", "rub": "RUB",
    "$": "USD", "usd": "USD", "доллар": "USD", "доллара": "USD", "долларов": "USD",
    "dollar": "USD", "dollars": "USD",
    "€": "EUR", "eur": "EUR", "евро": "EUR", "euro": "EUR", "euros": "EUR",
    "£": "GBP", "gbp": "GBP", "¥": "CNY", "cny": "CNY", "юаней": "CNY", "юаня": "CNY",
    "₸": "KZT", "kzt": "KZT", "тг": "KZT", "тенге": "KZT",
    "₴": "UAH", "uah": "UAH", "грн": "UAH",
    "₾": "GEL", "gel": "GEL", "лари": "GEL",
    "₼": "AZN", "azn": "AZN", "манат": "AZN", "манатов": "AZN",
    "₺": "TRY", "лир": "TRY", "лиры": "TRY",
    "֏": "AMD", "amd": "AMD", "драм": "AMD", "драмов": "AMD",
    "br": "BYN", "byn": "BYN", "zł": "PLN", "pln": "PLN", "злотых": "PLN",
    "сом": "KGS", "kgs": "KGS", "сўм": "UZS", "сум": "UZS", "uzs": "UZS",
    "смн": "TJS", "tjs": "TJS", "сомони": "TJS",
}  # fmt: skip
_SIGNS = "".join(re.escape(sign) for sign in MARKERS if len(sign) == 1 and not sign.isalpha())
_WORD_MARKERS = "|".join(re.escape(word) for word in sorted(MARKERS, key=len, reverse=True))
_NUMBER = r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,3})?|\d+(?:[.,]\d{1,3})?"
_THOUSANDS = r"к|k|тыс\.?|тысяч[иа]?"
_AMOUNT = (
    rf"(?P<sign>[+\-−])?(?P<pre>[{_SIGNS}])?(?P<number>{_NUMBER})"
    rf"(?:\s?(?P<k>{_THOUSANDS}))?(?:\s?(?P<cur>{_WORD_MARKERS}))?"
)
_AT_END = re.compile(rf"^(?:(?P<body>.*?)\s+)?{_AMOUNT}$", re.IGNORECASE)
_AT_START = re.compile(rf"^{_AMOUNT}(?:\s+(?P<body>.+))?$", re.IGNORECASE)
_DATE_LIKE = re.compile(r"^(\d{1,2})\.(\d{2})$")
# Only digits, signs, currency signs and punctuation: before a number at the end that is part
# of the amount («1 200», «$1 200», «+7 999 1234567»), not a note.
_NUMERIC_NOTE = re.compile(rf"^[\d\s+\-−.,:;=*/×(){_SIGNS}]+$")


@dataclass(frozen=True)
class Quick:
    amount: int  # hundredths
    note: str  # as typed, without the amount and the day
    income: bool | None  # True after «+», False after «−»; None: the category decides
    days_ago: int = 0  # «вчера» 1, «позавчера» 2


@dataclass(frozen=True)
class OtherCurrency:
    """The phrase named another currency than the user's: «кофе 5$» for roubles."""

    code: str


def to_hundredths(number: str, thousands: bool = False) -> int | None:
    """«1 200» → 120000, «430,50» → 43050, «1,200» → 120000 (three digits after the separator
    group thousands), «1,5» with thousands → 150000; None for anything out of (0, 10⁹]."""
    digits = re.sub(r"[ \u00a0\u202f]", "", number)
    match = re.fullmatch(r"(\d+)(?:[.,](\d{1,3}))?", digits)
    if match is None:
        return None
    whole, fraction = match.group(1), match.group(2) or ""
    if len(fraction) == 3 and not thousands:
        if digits != number.strip():  # «1 200,500»: grouped and then thousands again
            return None
        whole, fraction = whole + fraction, ""
    try:
        value = Decimal(f"{whole}.{fraction or 0}") * (1000 if thousands else 1) * 100
    except InvalidOperation:
        return None
    if value != value.to_integral_value() or not 0 < value <= Decimal(LIMITS.amount_max) * 100:
        return None
    return int(value)


def note_key(note: str) -> str:
    """The note as the memory of categories compares it: lower case, «ё» as «е», only letters
    and digits, single spaces."""
    flat = re.sub(r"[^\w]+", " ", note.casefold().replace("ё", "е")).replace("_", " ")
    return " ".join(flat.split())[:MAX_LENGTH]


def dictionary_guess(note: str) -> str | None:
    """The preset key the note's words name: the first word that matches a category wins, and
    for that word the longest stem («подарили» is income, «подарок» an expense)."""
    for word in note_key(note).split():
        found = [(len(stem), key) for key, stems in STEMS.items() for stem in stems
                 if word.startswith(stem)]  # fmt: skip
        found += [(len(word), key) for key, words in WORDS.items() if word in words]
        if found:
            return max(found)[1]
    return None


def _trim(words: list[str], at_end: bool) -> list[str]:
    """Drop the connectives on the amount's side: «хлеб за 85» → «хлеб»."""
    while words and (words[-1] if at_end else words[0]).casefold() in CONNECTIVES:
        words = words[:-1] if at_end else words[1:]
    return words


def parse_quick(text: str, currency: str) -> Quick | OtherCurrency | None:
    """An expense or income in a chat message, or None when the message is something else."""
    phrase = text.strip()
    if not phrase or "\n" in phrase or len(phrase) > MAX_LENGTH:
        return None
    first, _, rest = phrase.partition(" ")
    days_ago = DAYS_AGO.get(first.casefold(), 0)
    if days_ago:
        phrase = rest.strip()
    for pattern, at_end in ((_AT_END, True), (_AT_START, False)):
        match = pattern.match(phrase)
        if match is None:
            continue
        words = _trim((match.group("body") or "").split(), at_end)
        if len(words) + 1 > MAX_WORDS:
            return None
        found = _quick(match, words, at_end, days_ago, currency)
        if found is not None:
            return found
    return None


def _quick(
    match: re.Match[str], words: list[str], at_end: bool, days_ago: int, currency: str
) -> Quick | OtherCurrency | None:
    sign, number = match.group("sign"), match.group("number")
    named = match.group("pre") or match.group("cur")
    if named is not None and MARKERS[named.casefold()] != currency:
        return OtherCurrency(MARKERS[named.casefold()])
    if at_end and words and words[-1].casefold() in TIME_WORDS:
        return None  # «встреча в 9»
    if not match.group("k") and named is None:
        date = _DATE_LIKE.match(number)
        if date and 1 <= int(date.group(1)) <= 31 and 1 <= int(date.group(2)) <= 12:
            return None  # «12.10» is a date
    amount = to_hundredths(number, thousands=bool(match.group("k")))
    if amount is None:
        return None
    note = " ".join(words)
    if at_end and _NUMERIC_NOTE.match(note):
        return None  # «1 200» is one amount: it is read again from the start
    if not at_end:
        if not words and match.group("body"):
            return None  # «250 за»: only a connective after the number
        if words and words[0].casefold() in UNITS:
            return None  # «+2 кг», «-5 %»: a quantity, not money
        if words and sign is not None and named is None and _NUMERIC_NOTE.match(words[0]):
            return None  # «+7 999 1234567», «+7 (999) 123-45-67»: a phone number
        # «250 кофе»: a bare number first is money only when the next word names a category;
        # alone it is an amount («15 000»).
        if (
            sign is None
            and named is None
            and words
            and (amount < BARE_MINIMUM or dictionary_guess(words[0]) is None)
        ):
            return None
    income = None if sign is None else sign == "+"
    return Quick(amount=amount, note=note, income=income, days_ago=days_ago)


def format_amount(
    hundredths: int, currency: str, lang: str, *, plus: bool = False, sign: str | None = None
) -> str:
    """«1 200 ₽», «430,50 ₽», in English «$1,200» and «1,200 ₽»; kopecks only when there are
    some. `plus` marks an income: «+5 000 ₽». `sign` replaces the currency's sign (a picture
    draws «AMD» where its fonts lack «֏»)."""
    whole = hundredths % 100 == 0
    value = Decimal(hundredths) / 100
    number = str(format_decimal(value, format="#,##0" if whole else "#,##0.00", locale=lang))
    number = number.replace("\u202f", NBSP).replace(" ", NBSP)
    style = CURRENCIES.get(currency)
    mark = sign or (style.sign if style else currency)
    before = style is not None and style.before and lang == "en" and mark == style.sign
    text = f"{mark}{number}" if before else f"{number}{NBSP}{mark}"
    return f"+{text}" if plus else text
