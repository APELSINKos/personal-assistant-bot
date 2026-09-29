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
| `DEFAULT_CITY`, `DEFAULT_LAT`, `DEFAULT_LON`, `DEFAULT_TIMEZONE` | Москва | город новых пользователей |
| `DEFAULT_MORNING_TIME` | `08:00` | время сводки новых пользователей |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8000` | где слушает API |
| `API_RATE_LIMIT` | `120` | запросов в минуту на пользователя |

## Mini App

Вне Telegram у приложения нет подписанной initData, поэтому для разработки её подписывает скрипт токеном тестового бота из `.env`:

```bash
uv run python -m assistant.api                                   # API на 127.0.0.1:8000
echo "VITE_DEV_INIT_DATA=$(uv run python scripts/dev_init_data.py --user-id <id>)" > webapp/.env.local
cd webapp && npm ci && npm run dev                               # http://localhost:5173
```

Подпись действует 24 часа. `webapp/.env.local` не попадает в git, а в production-сборку переменная не входит: приложение читает её только в режиме разработки и показывает плашку «Режим разработки». Сервер разработки перенаправляет `/api` на `127.0.0.1:8000`. Описание API — на `http://127.0.0.1:8000/api/docs`.

## Проверки

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

```bash
cd webapp
npm run lint
npm run typecheck
npm test
npm run build
```

CI запускает Python-проверки на 3.12 и 3.13, проверки приложения на Node.js 24 и сверяет миграции с моделями.

## Миграции

```bash
uv run alembic revision --autogenerate -m "short description"
uv run alembic upgrade head
```

Сгенерированную миграцию нужно прочитать перед коммитом: SQLite меняет таблицы через пересоздание (`render_as_batch`). Перед миграцией на сервере делается снимок базы, и при неудачном деплое база возвращается из него.

Миграции идут с выключенными внешними ключами, иначе пересоздание `users` каскадно удалило бы заметки, напоминания и привычки. После миграций `PRAGMA foreign_key_check` проверяет ссылки, и при нарушении миграция завершается ошибкой. При пересоздании `notes`, `reminders` и `habits` нужно передать `table_kwargs={"sqlite_autoincrement": True}`, иначе пропадёт AUTOINCREMENT и id удалённых записей снова начнут выдаваться новым; это ловит тест миграций.

## Тексты

Новый текст добавляется ключом в оба файла: `locales/ru/bot.ftl` и `locales/en/bot.ftl`. Числа со словами («1 день», «2 дня», «5 дней») оформляются выбором Fluent по `$count`. Строк для пользователя в коде Python нет. Строки приложения — в `webapp/src/i18n/ru.ts` и `en.ts`; английский словарь типизирован по русскому, так что пропущенный ключ не соберётся.

## Ветки и коммиты

- Работа идёт в отдельной ветке; в `main` — через pull request после зелёного CI.
- Сообщения коммитов — по-русски в формате conventional commits: `feat(bot): …`, `fix(core): …`, `test: …`, `docs: …`, `ci: …`, `refactor: …`, `chore: …`.
- Коммит в `main` после CI автоматически разворачивается на сервере — см. [DEPLOY.md](DEPLOY.md).
