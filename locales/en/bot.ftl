## Main menu
menu-weather = 🌤 Weather
menu-today = 📅 My day
menu-reminders = ⏰ Reminders
menu-notes = 📝 Notes
menu-habits = 🎯 Habits
menu-rates = 💱 Exchange rates
menu-money = 💰 Money
menu-schedule = 🎓 Schedule
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
wmo-unknown = no data
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
    💰 Money — expenses, budget and exchange rates
    🎓 Schedule — your MIREA group's classes or any calendar
    ⚙️ Settings — city, morning digest and language

    Pick a section in the menu below 👇
friend = friend
app-soon = 📱 The app is coming soon — stay tuned.
app-open = Open the app with the button below 👇
menu-button = Open
stale-button = This button is outdated — open the section again from the menu.
bot-name = Personal Assistant
bot-short-description = Weather with tips, reminders, class schedule, notes, habits, expenses and exchange rates — in one chat.
bot-description = Personal assistant: smart weather, reminders, a class schedule, notes, a habit tracker, expenses with a budget, exchange rates and a morning digest the bot sends on its own.
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
weather-city-gone = This city is no longer on your list
button-weather-now = 🌤 Now
button-hours = 🕐 Hourly
button-week = 📅 Week
button-city-home = 🏠 { $city }
weather-hours-title = 🕐 { $city } — hourly
weather-hours-title-local = 🕐 { $city } — hourly (local time)
weather-hour = { $time } { $emoji } { $temp }
weather-hour-chance = { $time } { $emoji } { $temp } 💧 { $chance }%
weather-next-day = Tomorrow, { $date }
weather-hours-none = No hourly forecast right now.
weather-week-title = 📅 { $city } — 7 days
weather-day = { $label } { $emoji } { $range }
weather-day-chance = { $label } { $emoji } { $range } 💧 { $chance }%
weather-days-none = No forecast for the week right now.
weather-credit = Weather data: open-meteo.com

## My day and the morning digest
today-title = { $part ->
        [morning] 🌅 Good morning
        [day] ☀️ Good afternoon
        [evening] 🌆 Good evening
       *[night] 🌙 Hello
    }, { $name }!
today-date = 📅 Today, { $weekday }, { $date }
today-weather-unavailable = 🌤 Weather is temporarily unavailable
classes-weather = 🎓 To classes ({ $start }): { $start_weather } · after ({ $end }): { $end_weather }
classes-weather-after = 🎓 After classes ({ $end }): { $end_weather }
classes-temp-chance = { $temp }, 💧 { $chance }%
today-tomorrow = Tomorrow: { $emoji } { $range }
today-tomorrow-chance = Tomorrow: { $emoji } { $range }, 💧 { $chance }%
today-reminders = { $count ->
        [0] 📌 No reminders for today
        [one] 📌 { $count } reminder for today:
       *[other] 📌 { $count } reminders for today:
    }
list-item-time = • { $time } — { $text }
list-more = …and { $count } more
today-lessons = 🎓 Classes:
today-lessons-week = 🎓 Classes · { $week }:
today-lessons-none = 🎓 No classes today
lesson-line = • { $start }–{ $end } { $lesson }
lesson-line-start = • { $start } { $lesson }
today-habits = 🎯 Habits: { $done } of { $total }
today-habits-none = 🎯 No habits yet
today-streak = 🔥 Best streak: “{ $name }” — { $count } { $count ->
        [one] day
       *[other] days
    }
today-streak-weeks = 🔥 Best streak: “{ $name }” — { $count } { $count ->
        [one] week
       *[other] weeks
    }
today-notes = 📝 Notes: { $count }
today-pinned = 📌 { $text }
today-rates = 💵 { $usd } ₽ · 💶 { $eur } ₽
morning-title = ☀️ Good morning, { $name }!
morning-date = 📅 { $weekday }, { $date }
morning-weather = { $emoji } { $city }: { $temp }, { $description } · up to { $max } today
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
button-add = ➕ Add
button-delete-item = 🗑 { $number }. { $text }
deleted = 🗑 Deleted

## Notes
notes-empty = 📝 No notes yet. Tap “➕ Note” or “☑️ List” to create the first one.
notes-title = 📝 Your notes ({ $count }/{ $limit }):
notes-limit = You've reached the limit of { $limit } notes. Delete some first.
note-ask = ✍️ Send the text of the note (up to { $limit } characters):
hint-note = Send the text of the note.
note-bad-text = A note is text from 1 to { $limit } characters. Try again:
note-saved = ✅ Note saved.
note-line = { $number }. { $text }
note-line-pinned = { $number }. 📌 { $text }
note-progress = { $text } ✅ { $done }/{ $total }
note-card-pinned = 📌 { $text }
button-add-note = ➕ Note
item-open = ⬜ { $text }
item-done = ✅ { $text }
button-clear-done = 🧹 Remove checked
button-pin = 📌 Pin
button-unpin = 📌 Unpin
button-delete-note = 🗑 Delete
button-back-notes = ↩️ To notes
note-delete-ask = 🗑 Delete the note “{ $text }”?
pinned-limit = You can pin up to { $limit } notes — unpin one first
button-add-list = ☑️ List
button-find = 🔍 Find
button-reset-search = ✖️ Clear search
button-add-items = ➕ Items
button-edit = ✏️ Edit
items-full = This note already has { $limit } items
note-edit-ask = ✍️ Send the new text of the note (up to { $limit } characters):
hint-note-edit = Send the new text of the note.
note-updated = ✅ Note updated.
items-ask = ✍️ Send the items, one per line (up to { $limit } in a note):
hint-items = Send the items, one per line.
items-room = Only { $count } more { $count ->
        [one] item
       *[other] items
    } will fit — send fewer:
item-too-long = The item “{ $text }” is longer than { $limit } characters — shorten it and try again:
items-added = ✅ Items added: { $count }
list-ask =
    ☑️ Send a list: the title on the first line, then each item on its own line. For example:
    Shopping
    milk
    bread
hint-list = Send the title and the items, each on its own line.
list-need-item = I need at least one item — one per line after the title.
list-too-long = A list can have up to { $limit } items — send a shorter one:
list-saved = ✅ List saved.
search-ask = 🔍 What should I look for? Send a word or part of one:
hint-search = Send a word to search for.
search-bad = A search is up to { $limit } characters. Make it shorter:
search-empty = 🔍 Nothing found for “{ $query }”. Try another word:
search-found = 🔍 Found { $count } { $count ->
        [one] note
       *[other] notes
    }
search-title = 🔍 “{ $query }” — { $count } { $count ->
        [one] note
       *[other] notes
    }:

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
unknown-hint = To create a reminder, just write, e.g. “tomorrow at 9 buy milk”. An expense — like this: “coffee 250”.
button-snooze-10m = +10 min
button-snooze-1h = +1 h
button-snooze-tomorrow = Tomorrow
button-done = ✓ Done
fired-snoozed = ⏭ Moved to { $when }
fired-done = ✓ Done

## Habits
habits-empty = 🎯 No habits yet. Tap “➕ Add” to start.
habits-title = 🎯 Your habits ({ $count }/{ $limit }):
habit-line = { $number }. { $emoji } { $name } — { $done } of { $total } { $total ->
        [one] day
       *[other] days
    }{ $fire }
habit-line-weekly = { $number }. { $emoji } { $name } — this week { $done } of { $goal }{ $fire }
habit-days = { $strip }  streak: { $count } { $count ->
        [one] day
       *[other] days
    }
habit-weeks = { $strip }  streak: { $count } { $count ->
        [one] week
       *[other] weeks
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
button-cities = 🏙 Cities
cities-title = 🏙 Cities
cities-home = 🏠 { $city } — home city: reminders and the morning digest follow its time
cities-item = • { $city }
cities-none = No other cities yet — add up to { $limit }, and their weather will be one tap away under “🌤 Weather”.
button-change-home = ✏️ Change home city
button-delete-city = 🗑 { $city }
button-add-city = ➕ Add a city
city-add-ask = 🏙 Which city should I add? Send its name:
hint-city-add = Send the name of the city to add.
city-choose-add = I found several cities — pick the one you mean:
city-added = ✅ City added: { $city }. Its weather is the “{ $city }” button under “🌤 Weather”.
city-duplicate = This city is already on your list. Send another one:
cities-limit = You can add up to { $limit } cities.
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

## Schedule
lesson-alert = 🎓 In { $minutes } min: { $lesson }
day-yesterday = Yesterday
schedule-intro =
    🎓 Class schedule

    Connect your timetable — classes will appear here, in “My day”, the morning digest and the app's calendar.
button-find-group = 🔎 Find a MIREA group
button-by-link = 🔗 By link
button-by-file = 📎 As an .ics file
schedule-ask-group = Send the group name, e.g. ИКБО-63-24:
hint-group = Send the group name, e.g. ИКБО-63-24.
schedule-group-not-found = I couldn't find the group “{ $name }”. Check the name — e.g. ИКБО-63-24:
schedule-group-choose = I found several groups — pick yours:
schedule-directory-empty = The MIREA group directory isn't ready yet — try again later or connect a timetable by link.
schedule-ask-link = Send a calendar link — webcal://… or https://…
hint-link = Send a calendar link, e.g. webcal://…
schedule-ask-file = Send an .ics calendar file (up to 2 MB).
hint-file = Send an .ics calendar file.
schedule-connected = ✅ Timetable connected: { $title }. Classes ahead: { $count }.
schedule-connected-empty = ✅ Timetable connected: { $title }. But it has no classes in the coming months.
schedule-error-forbidden_host = ⚠️ This link won't do: I need an https:// or webcal:// link to a calendar on the internet.
schedule-error-unreachable = ⚠️ I couldn't download the calendar. Check the link or try later.
schedule-error-too_large = ⚠️ The calendar is too big or too complex to read.
schedule-error-not_calendar = ⚠️ This doesn't look like an .ics calendar.
schedule-error-group = ⚠️ This group is no longer in the directory — search for it again.
schedule-day = 🎓 { $day }
schedule-day-week = 🎓 { $day } · { $week }
schedule-week = 🎓 { $range }
schedule-week-label = 🎓 { $week } · { $range }
schedule-free = No classes 🎉
schedule-stale = ⚠️ Data from { $date } — the source is unavailable for now.
button-schedule-today = Today
button-schedule-tomorrow = Tomorrow
button-schedule-week = 📅 Week
button-schedule-day = 📅 Day
button-schedule-source = ⚙️ Source
schedule-source-title = ⚙️ Timetable source
schedule-source-mirea = MIREA group: { $title }
schedule-source-url = By link: { $title }
schedule-source-file = File: { $title }
schedule-source-untitled = an untitled calendar
schedule-updated = Updated: { $when }
schedule-failed = ⚠️ The last update failed.
schedule-alerts-off = 🔕 Class alerts are off
schedule-alerts-on = 🔔 I alert you { $minutes } min before each class
button-refresh = 🔄 Update
button-lesson-alerts = 🔔 Class alerts
button-change-source = 🔁 Change source
button-disconnect = 🗑 Disconnect
schedule-refresh-wait = Just updated — wait a minute
schedule-too-many = ⏳ Too many attempts in a row — try again in { $seconds } s.
schedule-alerts-pick = How many minutes before a class should I alert you?
button-alerts-off = No alerts
button-alerts-minutes = { $minutes } min before
schedule-disconnect-ask = Disconnect the timetable? Classes will disappear from the calendar and “My day”.
button-disconnect-yes = Yes, disconnect
schedule-disconnected = Timetable disconnected.
card-goal-daily = Every day
card-goal-weekly = { $count ->
        [one] Once a week
       *[other] { $count } times a week
    }
card-since = since { $date }
card-unit-days = { $count ->
        [one] day
       *[other] days
    }
card-unit-weeks = { $count ->
        [one] week
       *[other] weeks
    }
card-in-a-row = in a row
card-record = Record
card-year = Past year
card-week = This week
card-week-value = { $done } of { $goal }
card-map = Last 12 months
card-done = done
card-missed = skipped
card-unmarked = no mark
card-tagline = personal assistant in Telegram
card-months = Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
card-caption = { $emoji } { $name } — { $count } { $unit } in a row
habit-card-streak-days = 🔥 Streak: { $count } { $count ->
        [one] day
       *[other] days
    }
habit-card-streak-weeks = 🔥 Streak: { $count } { $count ->
        [one] week
       *[other] weeks
    }
habit-card-record-days = 🏆 Record: { $count } { $count ->
        [one] day
       *[other] days
    }
habit-card-record-weeks = 🏆 Record: { $count } { $count ->
        [one] week
       *[other] weeks
    }
habit-card-year = 📊 Past year: { $percent }%
habit-card-week = 📅 This week: { $done } of { $goal }
button-habit-map = 📊 Year map
button-habit-days = 📅 Past days
button-habit-goal = 🎯 Goal
button-habit-style = 🎨 Emoji and color
button-habit-rename = ✏️ Rename
button-to-habits = ↩️ To habits
habit-days-title = 📅 { $emoji } { $name }: the last days
habit-days-help = Tap a day: ✅ done → ❌ skipped → ⬜ no mark
habit-goal-ask = 🎯 How many times a week — “{ $name }”? The streak and percentages are recounted for the new goal.
habit-emoji-ask = 🎨 Pick an emoji for “{ $name }”:
habit-color-ask = 🎨 And a color — for the card and the app:
habit-rename-ask = ✍️ A new name for “{ $name }” (up to { $limit } characters):
habit-renamed = ✅ Done: “{ $name }”.
habit-cards-wait = ⏳ Too many cards in a row — try again in { $seconds } s.

## Money
money-cat-groceries = Groceries
money-cat-cafe = Eating out
money-cat-transport = Transport
money-cat-home = Home
money-cat-phone = Phone & internet
money-cat-health = Health
money-cat-clothes = Clothes
money-cat-fun = Fun
money-cat-study = Study
money-cat-gifts = Gifts
money-cat-subscriptions = Subscriptions
money-cat-other = Other
money-cat-salary = Salary
money-cat-stipend = Stipend
money-cat-gifts_in = Gifts received
money-cat-other_in = Other
money-report-subtitle = Expenses this month
money-report-budget = { $percent }% of the budget
money-report-of = of { $amount }
money-report-share = { $percent }%
money-report-left = { $amount } left
money-report-left-per-day = { $amount } left — { $per_day } a day
money-report-over = { $amount } over the budget
money-report-income = Income { $income } · balance { $balance }
money-report-empty = No expenses this month
money-report-entries = { $count ->
        [one] entry
       *[other] entries
    }
money-report-rest = Other
money-report-days = Day by day
money-report-caption = 💰 { $month }: spent { $amount }
rates-card-title = Bank of Russia rates
rates-card-period = 30 days · { $start } — { $end }
rates-card-name-usd = US dollar
rates-card-name-eur = Euro
rates-card-change = { $amount } · { $percent }% in 30 days
rates-card-unavailable = The bank's rates are not available now
rates-card-caption = 📈 Bank of Russia rates for 30 days
money-title = 💰 { $month }
money-spent = Spent: { $amount }
money-spent-budget = Spent: { $amount } of { $budget } ({ $percent }%)
money-income = Income: { $amount } · balance { $balance }
money-left = { $amount } left — { $per_day } a day
money-over = Over the budget: { $amount }
money-category = { $bar } { $emoji } { $name } — { $amount } ({ $share }%)
money-none = No expenses this month yet.
money-hint = To note an expense, just write: coffee 250. Income goes with a plus: +5000 salary
button-money-report = 📊 Report
button-money-rates = 💱 Rates
button-money-previous = ◀️ { $month }
button-rates-chart = 📈 30 days
button-entry-category = 🗂 Category
button-entry-undo = ↩️ Undo
button-entry-income = 🔁 It's income
button-entry-expense = 🔁 It's an expense
button-entry-new = ➕ New
money-entry-month = { $month }: { $spent } of { $budget }
money-entry-month-plain = { $month }: { $spent }
money-undone = ↩️ Undone: { $what }
money-pick = 🗂 Where does “{ $note }” go?
money-pick-plain = 🗂 Which category?
money-new-ask = ✍️ The new category's name (up to { $limit } characters):
money-new-emoji = 🎨 An emoji for “{ $name }”:
money-category-created = ✅ New category: { $emoji } { $name }
money-duplicate = There is already such a category — try another name:
money-duplicate-late = There is already such a category — the entry stayed where it was.
money-bad-name = A name is 1 to { $limit } characters. Try again:
money-categories-full = There are already { $limit } categories — no room for more. You can rename one you don't need in the app.
money-other-currency = Amounts are noted in { $sign } — the currency is changed in ⚙️ Settings.
money-limit = There are already { $limit } entries — no room for more.
money-limit-month = This month already has { $limit } entries — no more can be added.
money-bad-note = A note is up to { $limit } characters.
money-day-1 = yesterday
money-day-2 = the day before yesterday
money-alert-total-80 = ⚠️ { $percent }% of the { $month } budget is spent: { $spent } of { $budget }
money-alert-total-100 = 🚨 The { $month } budget has run out: { $spent } of { $budget }
money-alert-category-80 = ⚠️ { $percent }% of the “{ $name }” budget for { $month } is spent: { $spent } of { $budget }
money-alert-category-100 = 🚨 The “{ $name }” budget for { $month } has run out: { $spent } of { $budget }
hint-money-category = Write the category's name.
button-money-entries = 📜 Entries
button-money-budget = 🎯 Budget
button-budget-total = ✏️ Total budget
button-budget-categories = 🗂 By category
money-entries-title = 📜 { $month } · { $count } { $count ->
        [one] entry
       *[other] entries
    }
money-entries-line = { $number }. { $day } · { $what }
money-entries-empty = 📜 No entries this month yet.
money-delete-ask = 🗑 Delete “{ $what }”?
money-budget-title = 🎯 The budget for { $month }
money-budget-total = Total
money-budget-total-none = No total budget yet.
money-budget-line = { $label }: { $budget } — spent { $spent }, { $rest } left
money-budget-line-over = { $label }: { $budget } — spent { $spent }, { $rest } over
money-budget-hint = I'll warn you at 80% and 100%. A budget holds for every month.
money-budget-pick = 🗂 Which category gets a budget?
money-budget-ask-total = 🎯 How much may a month cost? Write an amount, e.g. 30000, or 0 to remove the budget:
money-budget-ask = 🎯 A month's budget for “{ $name }”? Write an amount, e.g. 5000, or 0 to remove it:
money-budget-bad = I need an amount, e.g. 30000 or 30 000, or 0 to remove the budget. Try again:
money-budget-saved = ✅ The budget is saved.
money-budget-removed = ✅ The budget is removed.
hint-money-budget = Write an amount, e.g. 30000, or 0.
settings-currency = 💱 Currency: { $sign } ({ $code })
button-currency = 💱 Currency
currency-pick = 💱 Which currency do you keep accounts in? Amounts already noted are not converted.
currency-changed = Currency: { $sign }
today-money = 💰 Today: { $today } · { $month }: { $spent } of { $budget }
today-money-plain = 💰 Today: { $today } · { $month }: { $spent }
morning-money = 💰 Yesterday: { $yesterday } · { $left } left — { $per_day } a day
morning-money-over = 💰 Yesterday: { $yesterday } · { $over } over the budget
morning-money-plain = 💰 Yesterday: { $yesterday }
today-rates-own = 💵 { $usd } ₽ · 💶 { $eur } ₽ · 💱 { $code } { $own } ₽
