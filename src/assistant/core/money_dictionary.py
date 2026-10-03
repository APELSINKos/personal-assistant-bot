"""Words that name a category, for guessing the category of «кофе 250».

A word of the note matches a category when it starts with one of the category's stems (or, for
the short words, equals one of them). Notes are compared lower-cased with «ё» read as «е».
"""

from __future__ import annotations

# fmt: off
# Preset key → stems: a word that starts with a stem matches.
STEMS: dict[str, tuple[str, ...]] = {
    "groceries": (
        "продукт", "пятерочк", "магнит", "ашан", "перекрест", "вкусвилл", "дикси", "лент", "spar",
        "спар", "азбук", "хлеб", "батон", "молок", "кефир", "яйц", "сыр", "мяс", "курин",
        "колбас", "овощ", "фрукт", "картош", "макарон", "крупа", "grocer", "supermarket", "bread",
        "milk", "eggs", "cheese", "vegetabl", "fruit",
    ),
    "cafe": (
        "кофе", "капучин", "латте", "американо", "эспрессо", "кафе", "ресторан", "пицц", "суши",
        "ролл", "бургер", "шаурм", "шаверм", "обед", "ужин", "завтрак", "столов", "макдо", "чаев",
        "coffee", "latte", "cappuccino", "espresso", "cafe", "restaurant", "lunch", "dinner",
        "breakfast", "pizza", "burger", "sushi",
    ),
    "transport": (
        "такси", "метро", "автобус", "трамва", "троллейбус", "маршрутк", "электричк", "поезд",
        "самолет", "бензин", "заправк", "парковк", "каршеринг", "самокат", "проезд", "транспорт",
        "taxi", "uber", "metro", "subway", "flight", "fuel", "petrol", "parking",
    ),
    "home": (
        "квартир", "аренд", "жкх", "коммунал", "электричеств", "мебел", "ремонт", "икеа",
        "хозтовар", "rent", "utilit", "furniture", "repair",
    ),
    "phone": (
        "связь", "телефон", "мобильн", "интернет", "мтс", "билайн", "мегафон", "теле2", "tele2",
        "phone", "mobile", "internet",
    ),
    "health": (
        "аптек", "лекарств", "таблет", "врач", "клиник", "стоматолог", "зуб", "анализ", "витамин",
        "pharmac", "medicin", "doctor", "dentist", "vitamin",
    ),
    "clothes": (
        "одежд", "обув", "кроссовк", "футболк", "джинс", "куртк", "плать", "носк", "clothes",
        "shoes", "sneakers", "jeans", "jacket",
    ),
    "fun": (
        "кино", "игр", "концерт", "театр", "музе", "боулинг", "развлеч", "вечеринк", "cinema",
        "movie", "game", "concert", "theat", "museum", "party",
    ),
    "study": (
        "учеб", "книг", "курс", "тетрад", "ручк", "канцеляр", "репетитор", "course", "tuition",
        "stationery",
    ),
    "gifts": ("подар", "букет", "цвет", "gift", "present", "flower"),
    "subscriptions": (
        "подписк", "spotify", "netflix", "youtube", "кинопоиск", "icloud", "subscription",
    ),
    "salary": (
        "зарплат", "аванс", "премия", "премии", "премию", "премией", "премиальн", "оклад",
        "salary", "paycheck", "wage", "bonus",
    ),
    "stipend": ("стипенд", "stipend", "scholarship", "грант", "grant"),
    "gifts_in": ("подарили",),
    "other_in": ("кэшбэк", "кешбэк", "кэшбек", "кешбек", "cashback", "возврат", "refund"),
}

# Preset key → whole words: short words that would match too much as stems.
WORDS: dict[str, tuple[str, ...]] = {
    "cafe": ("бар", "раф", "кфс", "kfc", "bar"),
    "transport": ("bus", "buses", "train", "trains"),
    "study": ("book", "books"),
    "phone": ("сим", "sim"),
    "salary": ("зп",),
}
# fmt: on
