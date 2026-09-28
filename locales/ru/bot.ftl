## Main menu
menu-weather = 🌤 Погода
menu-today = 📅 Мой день
menu-reminders = ⏰ Напоминания
menu-notes = 📝 Заметки
menu-habits = 🎯 Привычки
menu-rates = 💱 Курс валют
menu-settings = ⚙️ Настройки
menu-cancel = ❌ Отмена

## Common
days = { $count ->
    [one] { $count } день
    [few] { $count } дня
   *[many] { $count } дней
}
cancelled = Отменено.
need-text = Нужен текст. { $hint }
already-deleted = Этого уже нет.
error-generic = ⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже.
unknown = 🤔 Не понял. Выбери раздел в меню ниже 👇
open-app = 📱 Открыть приложение
page = Стр. { $current } из { $total }
prev = ◀️
next = ▶️

## Weather
wmo-clear = ясно
wmo-partly = малооблачно
wmo-cloudy = пасмурно
wmo-fog = туман
wmo-drizzle = морось
wmo-rain = дождь
wmo-snow = снег
wmo-showers = ливень
wmo-snowfall = снегопад
wmo-storm = гроза
wmo-unknown = без осадков
tip-precip-now = { $kind ->
    [snow] 🌨 Сейчас идёт снег — надень капюшон
   *[rain] 🌧 Сейчас идёт дождь — возьми зонт
}
tip-precip-soon = { $kind ->
    [snow] 🌨 Через { $minutes } { $minutes ->
        [one] минуту
        [few] минуты
       *[many] минут
    } снег — надень капюшон
   *[rain] 🌧 Через { $minutes } { $minutes ->
        [one] минуту
        [few] минуты
       *[many] минут
    } дождь — возьми зонт
}
tip-precip-later = { $kind ->
    [snow] 🌨 Снег ожидается после { $hour } — капюшон сегодня пригодится
   *[rain] ☔ Дождь ожидается после { $hour } — зонт сегодня пригодится
}
tip-warmer-evening = 🧥 Утром холодно, вечером потеплеет
tip-colder-evening = 🌡 К вечеру похолодает — захвати кофту
tip-wind = 💨 Сильный ветер — одевайся плотнее
tip-frost = 🥶 Очень холодно — одевайся теплее
tip-heat = 🥵 Жара — пей больше воды
tip-bike = 🚲 Сегодня хороший день для велосипеда
tip-calm = 👌 Погода без сюрпризов
