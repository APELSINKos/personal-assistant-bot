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
reminder-past = That time has already passed. Pick a moment in the future:
reminder-saved = ✅ I'll remind you on { $date } at { $time }: { $text }
reminder-ask-phrase =
    ✍️ Tell me what to remind you about and when. For example:
    • tomorrow at 9 buy milk
    • in 20 minutes tea
    • every monday at 10 planning
    • on weekdays at 7:30 workout
hint-reminder-phrase = Tell me what and when, e.g. “tomorrow at 9 buy milk”.
reminder-not-understood = 🤔 I couldn't find when to remind you. { reminder-ask-phrase }
reminder-need-text = ✍️ What should I remind you about? Send the whole phrase, e.g. “tomorrow at 9 buy milk”.
reminder-long-text = ✍️ Too long — up to { $limit } characters. Write a shorter phrase.
reminder-ask-time = 🕘 At what time? Pick one or send it, e.g. 18:30 or “tomorrow at 10”.
hint-reminder-time = Send a time, e.g. 18:30 or “tomorrow at 10”.
reminder-use-card = Tap “✅ Create” under the card — or write a new phrase.
reminder-card = ⏰ { $when }, { $time } — { $text }
reminder-card-repeat =
    ↻ { $rule } — { $text }
    First time: { $first }
button-create = ✅ Create
button-retime = 🕘 Another time
button-card-cancel = ✖️ Cancel
reminder-saved-repeat = ✅ I'll remind you { $rule }: { $text }
reminder-item-repeat = { $number }. ↻ { $rule } — { $text }
reminder-delete-series = Delete the repeat “{ $text }” entirely?
day-today = Today
day-tomorrow = Tomorrow
day-after-tomorrow = The day after tomorrow
unknown-hint = To create a reminder, just write, e.g. “tomorrow at 9 buy milk”.
button-snooze-10m = +10 min
button-snooze-1h = +1 h
button-snooze-tomorrow = Tomorrow
button-done = ✓ Done
fired-snoozed = ⏭ Moved to { $when }
fired-done = ✓ Done

## Habits
habits-empty = 🎯 No habits yet. Tap “➕ Add” to start.
habits-title = 🎯 Your habits ({ $count }/{ $limit }):
habit-line = { $number }. { $name } — { $done } of { $total } { $total ->
        [one] day
       *[other] days
    }{ $fire }
habit-days = { $strip }  streak: { $count } { $count ->
        [one] day
       *[other] days
    }
habits-legend = 🟩 done · 🟥 skipped · ⬜ no mark — the last 9 days
button-mark-today = ✅ Mark today
button-delete = 🗑 Delete
button-back = ↩️ Back
habits-mark-title = 📅 Mark your habits for { $date }
habits-mark-help = Tap a habit: ✅ done → ❌ skipped → ⬜ no mark
habits-mark-progress = Done: { $done } of { $total }
habits-need-one = Add at least one habit first.
habits-delete-title = Which habit should I delete?
habit-delete-confirm = Delete the habit “{ $name }” with all its statistics?
button-confirm-delete = 🗑 Yes, delete
habits-limit = You've reached the limit of { $limit } habits. Delete some first.
habit-ask = ✍️ What is the habit called? (up to { $limit } characters)
hint-habit = Send the name of the habit.
habit-bad-name = A name is text from 1 to { $limit } characters. Try again:
habit-duplicate = You already have this habit. Pick another name:
habit-added = ✅ Habit “{ $name }” added.

## Settings
settings-title = ⚙️ Settings
settings-city = 🏙 City: { $city }
settings-morning-on = 🌅 Morning digest: on ✅
settings-morning-off = 🌅 Morning digest: off ❌
settings-time = 🕗 Digest time: { $time }
settings-language = 🌐 Language: { $language }
settings-language-auto = 🌐 Language: same as Telegram ({ $language })
button-time = 🕗 Digest time
button-morning-off = 🔕 Turn the digest off
button-morning-on = 🔔 Turn the digest on
button-language = 🌐 Language
language-name = English
language-button = 🇬🇧 English
language-auto = 📱 Same as Telegram
language-pick = 🌐 Choose a language:
language-changed = ✅ Language: { $language }
city-ask = 🏙 Send the name of your city:
hint-city = Send the name of your city.
city-bad-name = A city name is text up to { $limit } characters. Try again:
city-not-found = I couldn't find “{ $name }”. Check the name and send it again:
city-unavailable = ⚠️ City search is unavailable. Please try later.
city-choose = I found several cities — pick yours:
city-saved = ✅ City saved: { $city }
time-ask = 🕗 When should I send the morning digest? Format HH:MM, e.g. 07:30
hint-time = Send a time as HH:MM, e.g. 07:30.
time-bad = That doesn't look like a time. I need HH:MM, e.g. 07:30:
time-saved = ✅ The digest will arrive at { $time }

## Delivery
reminder-fire = ⏰ Reminder: { $text }
reminder-fire-late = ⏰ Reminder: { $text } (was due at { $when })

## Repeats
repeat-daily = every day at { $time }
repeat-weekdays = on weekdays at { $time }
repeat-weekends = on weekends at { $time }
repeat-weekly = { $days } at { $time }
repeat-biweekly = every other week: { $days } at { $time }
repeat-monthly = monthly on day { $day } at { $time }
