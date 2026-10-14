# Разработка

## Окружение

Нужны Python 3.12 или 3.13, [uv](https://docs.astral.sh/uv/) и, для приложения, Node.js 24.

```bash
uv sync                          # зависимости и окружение .venv
cp .env.example .env             # токен отдельного тестового бота
uv run alembic upgrade head      # создать или обновить assistant.db
uv run python -m assistant.bot   # запустить
```

Для разработки нужен отдельный тестовый бот: один токен нельзя опрашивать из двух процессов, и рабочий бот перестал бы получать сообщения.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BOT_TOKEN` | — | токен бота |
| `DATABASE_URL` | `sqlite+aiosqlite:///./assistant.db` | база |
| `WEBAPP_URL` | пусто | адрес Mini App (`https://…/`); пока пусто, кнопки приложения скрыты |
| `LOG_LEVEL` | `INFO` | уровень журнала |
| `HTTP_TIMEOUT` | `10` | таймаут и общий срок запросов бота к Open-Meteo и ЦБ, с |
| `SCHEDULER_INTERVAL` | `20` | пауза между проходами планировщика, с |
| `DEFAULT_CITY`, `DEFAULT_LAT`, `DEFAULT_LON`, `DEFAULT_TIMEZONE` | Москва | город новых пользователей |
| `DEFAULT_MORNING_TIME` | `08:00` | время сводки новых пользователей |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8000` | где слушает API |
| `API_RATE_LIMIT` | `120` | запросов в минуту на пользователя (не меньше 1) |
| `API_DOCS` | `false` | описание API на `/api/docs` и `/api/openapi.json` — для разработки; в `.env.example` включено |
| `MIREA_DIRECTORY` | `true` | собирать справочник групп МИРЭА в фоне (полный обход — около 35 минут); в `.env.example` выключено |

## Mini App

Вне Telegram у приложения нет подписанной initData, поэтому для разработки её подписывает скрипт токеном тестового бота из `.env`:

```bash
uv run python -m assistant.api                                   # API на 127.0.0.1:8000
echo "VITE_DEV_INIT_DATA=$(uv run python scripts/dev_init_data.py --user-id <id>)" > webapp/.env.local
cd webapp && npm ci && npm run dev                               # http://localhost:5173
```

Подпись действует 24 часа. `webapp/.env.local` не попадает в git, а в production-сборку переменная не входит: приложение читает её только в режиме разработки и показывает плашку «Режим разработки». Сервер разработки перенаправляет `/api` на `127.0.0.1:8000`. Описание API — на `http://127.0.0.1:8000/api/docs`, когда в `.env` стоит `API_DOCS=true` (как в `.env.example`); на сервере его нет.

## Демо

Демо — то же приложение без единой правки во второй сборке, для GitHub Pages: страница-стенд (`webapp/demo/index.html`, код — `src/demo/host`) рисует то, что в Telegram рисует сам Telegram (шапку, главную кнопку, диалоги, выбор чата), и отвечает приложению выдуманными данными из памяти вкладки (`src/demo/api`); приложение (`webapp/demo/app.html`) работает во фрейме того же источника, а мосты `src/demo/bridge` подменяют ему часы, `Telegram.WebApp` и `fetch`. Ни сервер, ни Telegram, ни `.env` демо не нужны.

```bash
cd webapp
npm run dev:demo       # демо с горячей заменой
npm run build:demo     # сборка в webapp/dist-demo, рядом — копия обложки og.jpg
npm run preview:demo   # собранное демо, как на Pages
```

Адрес демо понимает `?lang=ru|en` (иначе язык браузера), `?theme=dark|light` (иначе тема системы), `?at=2026-10-07T10:30` — часы демо с этого момента по Москве (при одном `?at` данные одинаковы при каждой загрузке) и `?shot=1` — только экран устройства 390×844, для снимков README; маршрут приложения — после `#`: `?lang=en#/weather`.

- **Каждое изменение API меняет и `src/demo/api` с его тестами.** Ответы демо типизированы `src/api/types.ts`, поэтому изменённый ответ не соберётся, а `src/demo/api/coverage.test.ts` находит каждый вызов `api(…)` в `src/api` и валит `npm test`, если у пары «метод + путь» нет маршрута в демо.
- **Новый внешний адрес в приложении** (ссылка на источник, сайт) добавляется и в список хостов `scripts/check-demo.mjs`: проверка сборки демо падает на любом адресе не из списка, и без этого не пройдёт CI, а с ним и выкладка. Найденный адрес проверка не печатает, только файл и правило: журналы Actions публичны.
- **Правила исходников** — во всём `webapp` нет регулярных выражений с lookbehind (`(?<=`, `(?<!`): Safari до 16.4 не разбирает такой файл целиком, и страница остаётся пустой; код приложения (`src` вне `src/demo`) не импортирует демо, иначе демо попало бы в сборку для Telegram. Это не правила ESLint, а тест Vitest `src/test/sourceRules.test.ts`, его запускает `npm test`; lookbehind в собранном JS ищет ещё и `check-demo.mjs`. Папки `dist-demo` нет в игноре ESLint, и `npm run lint` с ней проходит: правила ESLint проверяют только `.ts` и `.tsx`.
- CI на каждый пуш и PR собирает демо и проверяет сборку (`check-demo.mjs`), а в сборке для Telegram ищет код демо. Публикация — в [DEPLOY.md](DEPLOY.md), раздел «Демо на GitHub Pages».

## Проверки

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
uv run alembic upgrade head && uv run alembic check   # миграции совпадают с моделями
```

```bash
cd webapp
npm run lint
npm run typecheck
npm test
npm run build
```

CI запускает Python-проверки на 3.12 и 3.13, проверки приложения на Node.js 24 и сверяет миграции с моделями. Форматирование CI не правит, а проверяет — `uv run ruff format --check .`: неотформатированный файл делает CI красным. На 3.12 CI берёт системный Python Ubuntu 24.04 — тот же, что на сервере, — и проверяет, что у него SQLite 3.45: миграция, которую сервер не выполнит, падает в CI, а не при деплое.

Зависимости CI ставит командой `uv sync --locked`: если `uv.lock` отстал от `pyproject.toml`, CI красный — после правки зависимостей запустите `uv lock` и закоммитьте оба файла.

Тесты не ходят в сеть: календари лежат в `tests/fixtures/schedule` (вырезка настоящего календаря группы МИРЭА без имён, календарь другого вуза и календарь Outlook), загрузчик проверяется на подменённом транспорте httpx и подменённом разрешении имён, а ответы Open-Meteo строит `forecast_payload` из `tests/stubs.py` — секундами Unix, как настоящий.

Тесты не зависят от настоящей даты: роутеры бота берут время из модульной функции `clock` (тесты её подменяют), сервисы получают `now` аргументом, тесты приложения ставят время через `vi.setSystemTime`.

## Картинки

Карточку привычки, отчёт месяца, курсы за 30 дней и прогноз на неделю рисует Pillow только из файлов `src/assistant/assets`: шрифты Manrope, Unbounded и запасной Onest из `google/fonts` (SIL Open Font License 1.1) и картинки Noto Emoji 128×128 из `googlefonts/noto-emoji` — эмодзи привычек и категорий и значки погоды (файл `LICENSE` этого репозитория с 2024 года — тоже SIL OFL 1.1, но его README по-прежнему называет Apache 2.0, поэтому у картинок лежат оба текста); тексты лицензий лежат рядом с файлами. Буквы, которых нет в Manrope (казахские Ә Ғ Қ Ң Ұ, многие другие буквы кириллицы стран СНГ, ʼ и ʻ), `card_kit.write` берёт из Onest и рисует кусками на одной базовой линии с Manrope; строка без таких букв даёт те же байты, что и без запасного шрифта. Откуда и с какого коммита взят каждый файл, написано в `assets/SOURCES.md`; проверить, что файлы не менялись: `cd src/assistant/assets && sha256sum -c SHA256SUMS`. Новое эмодзи для привычек добавляется в оба списка — `core/habit_style.py` и `webapp/src/lib/habits.ts` (тесты обоих проверяют, что эмодзи 32, — поправьте и их) — вместе с его картинкой `emoji_u<код>.png` и строкой в `SHA256SUMS`. Эмодзи категорий денег — так же в `core/money_style.py` и `webapp/src/lib/money.ts`; эти два списка, как и валюты, сверяет `tests/unit/test_money_style.py`. Новый значок погоды — тоже картинка `emoji_u<код>.png` и строка в `SHA256SUMS`: `tests/unit/test_forecast_cards.py` проверяет, что у каждого значка, который может показать погода, картинка есть. Новая валюта — строка в `CURRENCIES` обоих файлов и её знак в `MARKERS` (`core/services/money_phrases.py`, иначе фраза с этим знаком не разберётся); число валют проверяет тот же тест, миграция не нужна.

Картинки в README нарисованы тем же кодом из выдуманной привычки:

```bash
uv run python scripts/habit_card.py --lang ru --out docs/images/habit-card.jpg
uv run python scripts/habit_card.py --lang en --out docs/images/habit-card.en.jpg
```

`tests/unit/test_sample_card.py` сверяет эти файлы с тем, что рисует скрипт, а `tests/unit/test_cards.py` — суммы двух карточек, одинаковые на Windows и Linux. Если после обновления Pillow или шрифта, правки карточки или правил привычек тесты разошлись с картинками, перерисуйте их командами выше и обновите суммы в `test_cards.py`.

Отчёт месяца в README нарисован так же — из выдуманного октября:

```bash
uv run python scripts/money_report.py --lang ru --out docs/images/money-report.jpg
uv run python scripts/money_report.py --lang en --out docs/images/money-report.en.jpg
```

Их сверяет `tests/unit/test_sample_report.py`, а суммы отчёта и курсов — `tests/unit/test_money_cards.py`; после правки картинок или правил месяца перерисуйте отчёты и обновите суммы там.

Прогноз в README нарисован из выдуманной недели Москвы — той же, что в сообщении «📅 Неделя» в README (`scripts/showcase/world.py`):

```bash
uv run python scripts/forecast_card.py --lang ru --out docs/images/forecast-card.jpg
uv run python scripts/forecast_card.py --lang en --out docs/images/forecast-card.en.jpg
```

`tests/unit/test_sample_forecast.py` сверяет эти файлы с тем, что рисует скрипт, а подписи прогноза (`alt`) в обоих README — с `forecast_alt()` того же скрипта; суммы картинки прогноза — в `tests/unit/test_forecast_cards.py`.

### Картинки README

Экраны приложения, сетки из четырёх телефонов, анимацию и сообщения бота рисует генератор `scripts/showcase`: экраны и анимацию — из сборки демо в безголовом Edge или Chrome (протокол DevTools, без новых зависимостей), сообщения — кодом самого бота с выдуманными данными, без сети и без `.env`.

```bash
uv run python -m scripts.showcase             # всё: сборка демо, экраны, сетки, анимация, чаты, блок README
uv run python -m scripts.showcase compose     # только сетки — из docs/images/screens, без браузера
uv run python -m scripts.showcase chats       # сообщения бота и их расшифровки
uv run python -m scripts.showcase readme      # блок «В чате» обоих README — из расшифровок
```

Остальные шаги — `screens` и `walk`; `--lang ru,en` и `--theme dark,light` сужают прогон, `--browser ПУТЬ` (или переменная `SHOWCASE_BROWSER`) задаёт браузер, `--keep ПАПКА` оставляет кадры для разбора. Нужны Edge или Chrome, Node для сборки демо и сеть при первом прогоне: два шрифта — Roboto из `google/fonts` для картинок чата и Noto Color Emoji (COLRv1) из `googlefonts/noto-emoji` для эмодзи, оба под SIL OFL 1.1, — скачиваются по закреплённым коммитам в кэш пользователя (`%LOCALAPPDATA%\personal-assistant-bot\showcase`, `~/.cache/personal-assistant-bot/showcase`), сверяются по SHA-256 и в репозиторий не попадают. На Windows генератор запускают из PowerShell. Он пишет только `docs/images/**` и блоки README между метками и записывает сделанное в манифест `docs/images/showcase.json`; анимация — только тёмная, прогон с `--theme light` её пропускает.

- **Знаки из системного шрифта.** Знак, которого нет ни в Roboto, ни в Noto, браузер берёт из шрифтов машины; генератор печатает такие знаки и пишет их в манифест — сейчас это «↻» и «✓». Поэтому все картинки одного выпуска рисуются одним прогоном на одной машине.
- **Бюджеты** (их проверяет `tests/test_repository.py`): снимок, сетка или картинка чата — до 400 КБ, анимация — до 1,5 МБ, все картинки одного README вместе (обе темы, кадр анимации, обложка и аватар) — до 4 МБ.
- **Что видит CI.** Без браузера `tests/unit/test_showcase_chats.py` сверяет расшифровки чатов и блоки README с ботом, `test_showcase_manifest.py` — картинки с манифестом, `test_showcase_compose.py` — сетки со снимками. Правка любого из шести сообщений бота в сценах валит CI, пока не запущены `chats` и `readme`.
- **Когда пересобирать.** К выпуску, который меняет сообщения бота в сценах (это скажет CI) или вид любого из четырёх экранов и пяти сцен анимации (этого CI не видит): полный прогон, затем обложка (`scripts/cover.py`) и превью репозитория — его загружают руками. Полная пересборка навсегда добавляет в историю git около 5,5 МБ, поэтому картинки пересобираются к выпуску, а не после каждой правки текста.

### Обложка

Обложку `docs/images/cover.jpg` и `cover.en.jpg` (1280×640) рисует `scripts/cover.py`: слева название, подзаголовок и чипы, справа — два телефона с тёмными экранами демо `docs/images/screens/{today,weather}.dark(.en).webp` в рамке сеток README (вид A). Пока этих экранов нет, скрипт рисует вид B — веером три картинки бота `docs/images/{forecast-card,habit-card,money-report}(.en).jpg`; `--variant a|b` выбирает вид явно. Тот же скрипт рисует значок демо.

```bash
uv run python scripts/cover.py --lang ru --out docs/images/cover.jpg
uv run python scripts/cover.py --lang en --out docs/images/cover.en.jpg
uv run python scripts/cover.py --icon webapp/demo/public/apple-touch-icon.png
uv run python scripts/cover.py --favicon webapp/demo/public/favicon.svg
```

`tests/unit/test_sample_cover.py` сверяет обложки с тем, что рисует скрипт, поэтому новые тёмные экраны (а у вида B — новые картинки бота), правка рамки `compose.phone()`, шрифта или обновление Pillow требуют перерисовать и обложки: до этого тест падает. Порядок пересборки: демо → `scripts.showcase` → `scripts/cover.py` → превью репозитория руками: Settings → General → Social preview → `docs/images/cover.jpg` (проверка — `gh repo view --json usesCustomOpenGraphImage`). Превью ссылки на демо — русская обложка: сборка демо копирует её в `og.jpg`. Telegram хранит превью ссылок; обновить его можно, отправив адрес боту @WebpageBot.

## Миграции

```bash
uv run alembic revision --autogenerate --rev-id 0008 -m "short description"   # номер — следующий за последним в migrations/versions
uv run alembic upgrade head
```

Сгенерированную миграцию нужно прочитать перед коммитом: SQLite меняет таблицы через пересоздание (`render_as_batch`). Перед миграцией на сервере делается снимок базы, и при неудачном деплое база возвращается из него.

Миграции идут с выключенными внешними ключами, иначе пересоздание `users` каскадно удалило бы заметки, напоминания и привычки. После миграций `PRAGMA foreign_key_check` проверяет ссылки, и при нарушении миграция завершается ошибкой.

Таблицы, чьи id попадают в кнопки, объявлены с AUTOINCREMENT (`{"sqlite_autoincrement": True}` в `__table_args__` модели): id удалённых записей не выдаются снова, и старая кнопка не подействует на новую запись. Счётчик таблицы лежит в `sqlite_sequence`, и миграции его берегут:

- новая такая таблица создаётся с `sqlite_autoincrement=True`;
- пересоздание таблицы (`batch_alter_table`) получает `table_kwargs={"sqlite_autoincrement": True}`, иначе пропадёт сам AUTOINCREMENT. Оно сбрасывает счётчик до наибольшего id, поэтому строка `sqlite_sequence` запоминается до пересоздания и возвращается после (`_keep_reminders_sequence` в `0002`, `_keep_habits_sequence` в `0004`);
- откат, который удаляет такую таблицу, запоминает её строку `sqlite_sequence` и возвращает после удаления (`_keep_sequences` в `0006`), чтобы после нового обновления id продолжились. Откаты `0001` (к пустой базе) и `0005` написаны раньше этого правила и счётчиков не берегут: после отката к `0004` и нового обновления id категорий и записей денег снова начнутся с 1;
- колонка добавляется обычным `ALTER TABLE … ADD COLUMN`, а удаляется, если у неё нет индекса и ограничений, родным `ALTER TABLE … DROP COLUMN` (SQLite 3.35+; на сервере — 3.45, на ней же идут проверки CI на Python 3.12): так таблица не пересоздаётся.

Тест миграций берёт список таких таблиц из моделей и проверяет, что у каждой есть AUTOINCREMENT и что все счётчики `sqlite_sequence` переживают `upgrade head`.

## Тексты

Новый текст добавляется ключом в оба файла: `locales/ru/bot.ftl` и `locales/en/bot.ftl`. Числа со словами («1 день», «2 дня», «5 дней») оформляются выбором Fluent по `$count`. Строк для пользователя в коде Python нет. Строки приложения — в `webapp/src/i18n/ru.ts` и `en.ts`; английский словарь типизирован по русскому, так что пропущенный ключ не соберётся.

Длина введённого текста везде считается в символах Unicode (кодовых точках): на сервере — `len()`, в приложении — `codePoints` из `lib/format.ts`. Атрибут `maxLength` у полей не ставится: он считает единицы UTF-16, и эмодзи весит в нём вдвое. Длину сообщения Telegram, наоборот, считает в UTF-16 `texts.utf16_len` (предел — 3900 единиц).

## Поиск заметок

Поиск в боте (`notes.search` и `notes.fold` в `core/services/notes.py`) и в приложении (`webapp/src/lib/search.ts`, по списку, который уже пришёл из `GET /notes`) должен находить одно и то же: текст сворачивается `lower()` / `toLowerCase()`, «ё» становится «е», пробелы делятся так же, как их делит `str.split()` в Python. `casefold()` не используется: в JavaScript его нет, а `toLowerCase()` с ним расходится («ß», «ς»).

Обе стороны проверяет общая таблица случаев `webapp/src/lib/searchCases.json` — строки `{"text": …, "items": […], "query": …, "match": true | false}`; её читают `tests/unit/test_notes.py` и `webapp/src/lib/search.test.ts`. Правило сворачивания меняется в обоих файлах сразу, а новый случай добавляется строкой в таблицу, а не в один из тестов.

## Коды ошибок

Сервисы ядра бросают `InvalidInput` (поле `field`, причина `reason`, предел `limit`), `LimitReached` (`entity`, `limit`), `NotFound` (`entity`) и `UpstreamUnavailable` (`service`). Бот отвечает на них своими текстами из `bot.ftl`, а API — ответом `application/problem+json` (`api/errors.py`), где параметры ошибки идут рядом с `code`:

| Статус | `code` | Параметры |
|---|---|---|
| 401 | `invalid_init_data`, `expired_init_data` | — |
| 403 | `write_forbidden` | — |
| 404 | `not_found` | `entity` |
| 409 | `limit_reached` | `entity` и `limit`: `note` 50, `pinned_note` 5, `note_item` 20, `city` 4, `reminder` 20, `habit` 10, `category` 40, `entry` 50 000, `entry_month` 1 000 |
| 422 | `validation_error` | `field`, `reason`, `limit`: например, `{"field": "items", "reason": "length", "limit": 100}`; повтор — `reason: "duplicate"` |
| 429 | `rate_limited` | заголовок `Retry-After` |
| 503 | `upstream_unavailable` | `service`: `open-meteo`, `cbr` или `telegram` |

Сервер текстов для пользователя не пишет: их выбирает `errorCode()` в `webapp/src/api/queries.ts` и показывает всплывающей подсказкой.

1. Нет связи с сервером — `network`; ошибка не от API — `generic`.
2. 409 — `limit_<entity>`, если такой ключ есть в `errors` словаря («В заметке уже 20 пунктов»), иначе общий `limit_reached`.
3. Повтор города (`field: "city"`, `reason: "duplicate"`) — `duplicate_city`.
4. Причина со своим текстом (`OWN_TEXT_REASONS`: `duplicate`, `length`, `past`, причины календаря …) — сама `reason`.
5. Иначе — `code`; если и для него ключа нет, `generic`.

Новый текст ошибки — ключ в `errors` обоих словарей; для нового предела достаточно ключа `limit_<entity>`, а новой причине со своим текстом нужна ещё строка в `OWN_TEXT_REASONS`.

## Ветки и коммиты

- Работа идёт в отдельной ветке; в `main` — через pull request после зелёного CI.
- Сообщения коммитов — по-русски в формате conventional commits: `feat(bot): …`, `fix(core): …`, `test: …`, `docs: …`, `ci: …`, `refactor: …`, `chore: …`.
- Коммит в `main` после CI автоматически разворачивается на сервере — см. [DEPLOY.md](DEPLOY.md).
