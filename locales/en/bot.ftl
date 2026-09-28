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
