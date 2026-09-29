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

## Start and bot profile
welcome =
    👋 Привет, { $name }! Я твой личный помощник.

    🌤 Погода — прогноз с полезными советами
    📅 Мой день — всё важное одним сообщением
    ⏰ Напоминания — напомню в нужное время
    📝 Заметки — сохраню, чтобы не забыть
    🎯 Привычки — отмечай и держи серию
    💱 Курс валют — доллар и евро по ЦБ РФ
    ⚙️ Настройки — город, утренняя сводка и язык

    Выбери раздел в меню ниже 👇
friend = друг
app-soon = 📱 Приложение скоро появится — следи за обновлениями.
app-open = Открой приложение кнопкой ниже 👇
menu-button = Открыть
stale-button = Эта кнопка устарела — открой раздел заново из меню.
bot-name = Личный помощник
bot-short-description = Погода с советами, напоминания, заметки, привычки и курсы валют — в одном чате.
bot-description = Личный помощник: умная погода, напоминания, заметки, трекер привычек, курсы валют и утренняя сводка, которую бот присылает сам.
cmd-start = Главное меню
cmd-app = Открыть приложение
cmd-settings = Настройки
cmd-help = Что умеет бот
cmd-cancel = Отменить ввод

## Weather
weather-now = { $emoji } { $city }: { $temp }, { $description }
weather-feels = Ощущается как { $feels }, ветер { $wind } м/с
weather-range = Сегодня: { $range }
weather-unavailable = ⚠️ Не удалось получить погоду. Попробуй чуть позже.
weather-change-city = 🏙 Сменить город

## My day and the morning digest
today-title = { $part ->
        [morning] 🌅 Доброе утро
        [day] ☀️ Добрый день
        [evening] 🌆 Добрый вечер
       *[night] 🌙 Доброй ночи
    }, { $name }!
today-date = 📅 Сегодня, { $date }, { $weekday }
today-weather-unavailable = 🌤 Погода временно недоступна
today-reminders = { $count ->
        [0] 📌 На сегодня напоминаний нет
        [one] 📌 На сегодня { $count } напоминание:
        [few] 📌 На сегодня { $count } напоминания:
       *[many] 📌 На сегодня { $count } напоминаний:
    }
list-item-time = • { $time } — { $text }
list-more = …и ещё { $count }
today-habits = 🎯 Привычки: { $done } из { $total }
today-habits-none = 🎯 Привычек пока нет
today-streak = 🔥 Лучшая серия: «{ $name }» — { $count } { $count ->
        [one] день
        [few] дня
       *[many] дней
    }
today-notes = 📝 Заметок: { $count }
today-rates = 💵 { $usd } ₽ · 💶 { $eur } ₽
morning-title = ☀️ Доброе утро, { $name }!
morning-date = 📅 { $date }, { $weekday }
morning-weather = 🌡 { $city }: { $range }
morning-reminders = { $count ->
        [0] 📌 На сегодня напоминаний нет
       *[other] 📌 Сегодня:
    }
morning-habits = 🎯 Привычек на сегодня: { $count } — не забудь отметить

## Exchange rates
rates-title = 💱 Курс ЦБ РФ на { $date }
rates-line = { $emoji } { $code }: { $value } ₽  { $arrow } { $change }
rates-converter = Конвертер 👇
rates-unavailable = ⚠️ Не удалось получить курсы. Попробуй чуть позже.
rates-ask = Сколько { $source } перевести в { $target }?
hint-amount = Напиши сумму числом, например 100 или 99,5.
rates-bad-amount = Нужно число больше нуля и не больше миллиарда, например 100 или 99,5. Попробуй ещё раз:
rates-result = 💱 { $amount } { $source } = { $result } { $target }

## Lists
list-item = { $number }. { $text }
button-add = ➕ Добавить
button-delete-item = 🗑 { $number }. { $text }
deleted = 🗑 Удалено

## Notes
notes-empty = 📝 Заметок пока нет. Нажми «➕ Добавить», чтобы создать первую.
notes-title = 📝 Твои заметки ({ $count }/{ $limit }):
notes-limit = Достигнут лимит — { $limit } заметок. Удали лишние.
note-ask = ✍️ Напиши текст заметки (до { $limit } символов):
hint-note = Напиши текст заметки.
note-bad-text = Заметка — это текст от 1 до { $limit } символов. Попробуй ещё раз:
note-saved = ✅ Заметка сохранена.

## Reminders
reminders-empty = ⏰ Активных напоминаний нет. Нажми «➕ Добавить», чтобы создать.
reminders-title = ⏰ Твои напоминания ({ $count }/{ $limit }):
reminder-item = { $number }. { $when } — { $text }
reminders-limit = Достигнут лимит — { $limit } напоминаний. Удали лишние.
reminder-past = Это время уже прошло. Укажи момент в будущем:
reminder-saved = ✅ Напомню { $date } в { $time }: { $text }
reminder-ask-phrase =
    ✍️ Напиши, о чём и когда напомнить. Например:
    • завтра в 9 купить молоко
    • через 20 минут чай
    • каждый понедельник в 10 планёрка
    • по будням в 7:30 зарядка
hint-reminder-phrase = Напиши, о чём и когда напомнить, например «завтра в 9 купить молоко».
reminder-not-understood = 🤔 Не нашёл, когда напомнить. { reminder-ask-phrase }
reminder-need-text = ✍️ О чём напомнить? Напиши фразу целиком, например «завтра в 9 купить молоко».
reminder-ask-time = 🕘 Во сколько? Выбери или напиши, например 18:30 или «завтра в 10».
hint-reminder-time = Напиши время, например 18:30 или «завтра в 10».
reminder-card = ⏰ { $when }, { $time } — { $text }
reminder-card-repeat =
    ↻ { $rule } — { $text }
    Первый раз: { $first }
button-create = ✅ Создать
button-retime = 🕘 Другое время
button-card-cancel = ✖️ Отмена
reminder-saved-repeat = ✅ Буду напоминать { $rule }: { $text }
reminder-item-repeat = { $number }. ↻ { $rule } — { $text }
reminder-delete-series = Удалить повтор «{ $text }» целиком?
day-today = Сегодня
day-tomorrow = Завтра
day-after-tomorrow = Послезавтра
unknown-hint = Чтобы создать напоминание, просто напиши, например: «завтра в 9 купить молоко».
button-snooze-10m = +10 мин
button-snooze-1h = +1 ч
button-snooze-tomorrow = Завтра
button-done = ✓ Готово
fired-snoozed = ⏭ Перенёс на { $when }
fired-done = ✓ Готово

## Habits
habits-empty = 🎯 Привычек пока нет. Нажми «➕ Добавить», чтобы начать.
habits-title = 🎯 Твои привычки ({ $count }/{ $limit }):
habit-line = { $number }. { $name } — { $done } из { $total } { $total ->
        [one] дня
       *[other] дней
    }{ $fire }
habit-days = { $strip }  серия: { $count } { $count ->
        [one] день
        [few] дня
       *[many] дней
    }
habits-legend = 🟩 выполнено · 🟥 пропущено · ⬜ без отметки — последние 9 дней
button-mark-today = ✅ Отметить сегодня
button-delete = 🗑 Удалить
button-back = ↩️ Назад
habits-mark-title = 📅 Отметь привычки за { $date }
habits-mark-help = Нажимай на привычку: ✅ выполнено → ❌ пропущено → ⬜ без отметки
habits-mark-progress = Выполнено: { $done } из { $total }
habits-need-one = Сначала добавь хотя бы одну привычку.
habits-delete-title = Какую привычку удалить?
habit-delete-confirm = Удалить привычку «{ $name }» вместе со всей статистикой?
button-confirm-delete = 🗑 Да, удалить
habits-limit = Достигнут лимит — { $limit } привычек. Удали лишние.
habit-ask = ✍️ Как называется привычка? (до { $limit } символов)
hint-habit = Напиши название привычки.
habit-bad-name = Название — это текст от 1 до { $limit } символов. Попробуй ещё раз:
habit-duplicate = Такая привычка уже есть. Придумай другое название:
habit-added = ✅ Привычка «{ $name }» добавлена.

## Settings
settings-title = ⚙️ Настройки
settings-city = 🏙 Город: { $city }
settings-morning-on = 🌅 Утренняя сводка: включена ✅
settings-morning-off = 🌅 Утренняя сводка: выключена ❌
settings-time = 🕗 Время сводки: { $time }
settings-language = 🌐 Язык: { $language }
settings-language-auto = 🌐 Язык: как в Telegram ({ $language })
button-time = 🕗 Время сводки
button-morning-off = 🔕 Выключить сводку
button-morning-on = 🔔 Включить сводку
button-language = 🌐 Язык
language-name = Русский
language-button = 🇷🇺 Русский
language-auto = 📱 Как в Telegram
language-pick = 🌐 Выбери язык:
language-changed = ✅ Язык: { $language }
city-ask = 🏙 Напиши название города:
hint-city = Напиши название города.
city-bad-name = Название города — текст до { $limit } символов. Попробуй ещё раз:
city-not-found = Не нашёл город «{ $name }». Проверь название и напиши ещё раз:
city-unavailable = ⚠️ Сервис поиска городов недоступен. Попробуй позже.
city-choose = Нашлось несколько городов — выбери свой:
city-saved = ✅ Город сохранён: { $city }
time-ask = 🕗 Во сколько присылать утреннюю сводку? Формат ЧЧ:ММ, например 07:30
hint-time = Напиши время в формате ЧЧ:ММ, например 07:30.
time-bad = Не похоже на время. Нужен формат ЧЧ:ММ, например 07:30:
time-saved = ✅ Сводка будет приходить в { $time }

## Delivery
reminder-fire = ⏰ Напоминание: { $text }
reminder-fire-late = ⏰ Напоминание: { $text } (было на { $when })

## Repeats
repeat-daily = каждый день в { $time }
repeat-weekdays = по будням в { $time }
repeat-weekends = по выходным в { $time }
repeat-weekly = { $days } в { $time }
repeat-biweekly = раз в 2 недели: { $days } в { $time }
repeat-monthly = каждый месяц { $day }-го в { $time }
