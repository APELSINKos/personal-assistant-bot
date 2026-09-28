## Main menu
menu-weather = 🌤 Weather
menu-today = 📅 My day
menu-reminders = ⏰ Reminders
menu-notes = 📝 Notes
menu-habits = 🎯 Habits
menu-rates = 💱 Exchange rates
menu-settings = ⚙️ Settings
menu-cancel = ❌ Cancel

## Common
days = { $count ->
    [one] { $count } day
   *[other] { $count } days
}
cancelled = Cancelled.
need-text = I need text here. { $hint }
already-deleted = That is already gone.
error-generic = ⚠️ Something went wrong. Please try again a bit later.
unknown = 🤔 I didn't get that. Pick a section in the menu below 👇
open-app = 📱 Open the app
page = Page { $current } of { $total }
prev = ◀️
next = ▶️

## Weather
wmo-clear = clear
wmo-partly = partly cloudy
wmo-cloudy = overcast
wmo-fog = fog
wmo-drizzle = drizzle
wmo-rain = rain
wmo-snow = snow
wmo-showers = showers
wmo-snowfall = heavy snow
wmo-storm = thunderstorm
wmo-unknown = no precipitation
tip-precip-now = { $kind ->
    [snow] 🌨 It's snowing now — put your hood on
   *[rain] 🌧 It's raining now — take an umbrella
}
tip-precip-soon = { $kind ->
    [snow] 🌨 Snow in { $minutes } min — put your hood on
   *[rain] 🌧 Rain in { $minutes } min — take an umbrella
}
tip-precip-later = { $kind ->
    [snow] 🌨 Snow expected after { $hour } — a hood will come in handy
   *[rain] ☔ Rain expected after { $hour } — an umbrella will come in handy
}
tip-warmer-evening = 🧥 Cold in the morning, warmer in the evening
tip-colder-evening = 🌡 It gets colder by the evening — take a sweater
tip-wind = 💨 Strong wind — dress warmly
tip-frost = 🥶 Very cold — wrap up
tip-heat = 🥵 It's hot — drink more water
tip-bike = 🚲 A great day for a bike ride
tip-calm = 👌 No weather surprises today

## Start and bot profile
welcome =
    👋 Hi, { $name }! I'm your personal assistant.

    🌤 Weather — forecast with useful tips
    📅 My day — everything important in one message
    ⏰ Reminders — I'll ping you at the right time
    📝 Notes — keep what you don't want to forget
    🎯 Habits — mark them daily and keep the streak
    💱 Exchange rates — USD and EUR by the Bank of Russia
    ⚙️ Settings — city, morning digest and language

    Pick a section in the menu below 👇
friend = friend
app-soon = 📱 The app is coming soon — stay tuned.
app-open = Open the app with the button below 👇
menu-button = Open
stale-button = This button is outdated — open the section again from the menu.
bot-name = Personal Assistant
bot-short-description = Weather with tips, reminders, notes, habits and exchange rates — in one chat.
bot-description = Personal assistant: smart weather, reminders, notes, a habit tracker, exchange rates and a morning digest the bot sends on its own.
cmd-start = Main menu
cmd-app = Open the app
cmd-settings = Settings
cmd-help = What the bot can do
cmd-cancel = Cancel input

## Weather
weather-now = { $emoji } { $city }: { $temp }, { $description }
weather-feels = Feels like { $feels }, wind { $wind } m/s
weather-range = Today: { $range }
weather-unavailable = ⚠️ Couldn't get the weather. Please try again a bit later.
weather-change-city = 🏙 Change city

## My day and the morning digest
today-title = { $part ->
        [morning] 🌅 Good morning
        [day] ☀️ Good afternoon
        [evening] 🌆 Good evening
       *[night] 🌙 Hello
    }, { $name }!
today-date = 📅 Today, { $weekday }, { $date }
today-weather-unavailable = 🌤 Weather is temporarily unavailable
today-reminders = { $count ->
        [0] 📌 No reminders for today
        [one] 📌 { $count } reminder for today:
       *[other] 📌 { $count } reminders for today:
    }
list-item-time = • { $time } — { $text }
list-more = …and { $count } more
today-habits = 🎯 Habits: { $done } of { $total }
today-habits-none = 🎯 No habits yet
today-streak = 🔥 Best streak: “{ $name }” — { $count } { $count ->
        [one] day
       *[other] days
    }
today-notes = 📝 Notes: { $count }
today-rates = 💵 { $usd } ₽ · 💶 { $eur } ₽
morning-title = ☀️ Good morning, { $name }!
morning-date = 📅 { $weekday }, { $date }
morning-weather = 🌡 { $city }: { $range }
morning-reminders = { $count ->
        [0] 📌 No reminders for today
       *[other] 📌 Today:
    }
morning-habits = 🎯 Habits for today: { $count } — don't forget to mark them

## Exchange rates
rates-title = 💱 Bank of Russia rates for { $date }
rates-line = { $emoji } { $code }: { $value } ₽  { $arrow } { $change }
rates-converter = Converter 👇
rates-unavailable = ⚠️ Couldn't get the rates. Please try again a bit later.
rates-ask = How many { $source } to convert to { $target }?
hint-amount = Send the amount as a number, e.g. 100 or 99.5.
rates-bad-amount = I need a number above zero and up to one billion, e.g. 100 or 99.5. Try again:
rates-result = 💱 { $amount } { $source } = { $result } { $target }

## Lists
list-item = { $number }. { $text }
button-add = ➕ Add
button-delete-item = 🗑 { $number }. { $text }
deleted = 🗑 Deleted

## Notes
notes-empty = 📝 No notes yet. Tap “➕ Add” to create the first one.
notes-title = 📝 Your notes ({ $count }/{ $limit }):
notes-limit = You've reached the limit of { $limit } notes. Delete some first.
note-ask = ✍️ Send the text of the note (up to { $limit } characters):
hint-note = Send the text of the note.
note-bad-text = A note is text from 1 to { $limit } characters. Try again:
note-saved = ✅ Note saved.

## Reminders
reminders-empty = ⏰ No active reminders. Tap “➕ Add” to create one.
reminders-title = ⏰ Your reminders ({ $count }/{ $limit }):
reminder-item = { $number }. { $when } — { $text }
reminders-limit = You've reached the limit of { $limit } reminders. Delete some first.
reminder-ask-text = ✍️ What should I remind you about? (up to { $limit } characters)
hint-reminder-text = Send what to remind you about.
reminder-bad-text = I need text from 1 to { $limit } characters. Try again:
reminder-ask-when =
    When should I remind you? Examples:
    • 18:30 — today (or tomorrow if the time has passed)
    • 25.09 18:30 — this year (day.month)
    • 25.09.2027 18:30 — exact date
hint-when = Send a time, e.g. 18:30 or 25.09 18:30.
reminder-bad-when = I didn't get the time. { reminder-ask-when }
reminder-past = That time has already passed. Pick a moment in the future:
reminder-saved = ✅ I'll remind you on { $date } at { $time }: { $text }
