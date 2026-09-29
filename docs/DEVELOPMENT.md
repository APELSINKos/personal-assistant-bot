# Разработка

## Окружение

Нужны Python 3.12 или 3.13 и [uv](https://docs.astral.sh/uv/).

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
| `WEBAPP_URL` | пусто | адрес Mini App; пока пусто, кнопки приложения скрыты |
| `LOG_LEVEL` | `INFO` | уровень журнала |
| `DEFAULT_CITY`, `DEFAULT_LAT`, `DEFAULT_LON`, `DEFAULT_TIMEZONE` | Москва | город новых пользователей |
| `DEFAULT_MORNING_TIME` | `08:00` | время сводки новых пользователей |

## Проверки

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

CI запускает то же на Python 3.12 и 3.13 и проверяет, что миграции совпадают с моделями.

## Миграции

```bash
uv run alembic revision --autogenerate -m "short description"
uv run alembic upgrade head
```

Сгенерированную миграцию нужно прочитать перед коммитом: SQLite меняет таблицы через пересоздание (`render_as_batch`). Перед миграцией на сервере делается снимок базы, и при неудачном деплое база возвращается из него.

Миграции идут с выключенными внешними ключами, иначе пересоздание `users` каскадно удалило бы заметки, напоминания и привычки. После миграций `PRAGMA foreign_key_check` проверяет ссылки, и при нарушении миграция завершается ошибкой. При пересоздании `notes`, `reminders` и `habits` нужно передать `table_kwargs={"sqlite_autoincrement": True}`, иначе пропадёт AUTOINCREMENT и id удалённых записей снова начнут выдаваться новым; это ловит тест миграций.

## Тексты

Новый текст добавляется ключом в оба файла: `locales/ru/bot.ftl` и `locales/en/bot.ftl`. Числа со словами («1 день», «2 дня», «5 дней») оформляются выбором Fluent по `$count`. Строк для пользователя в коде Python нет.

## Ветки и коммиты

- Работа идёт в отдельной ветке; в `main` — через pull request после зелёного CI.
- Сообщения коммитов — по-русски в формате conventional commits: `feat(bot): …`, `fix(core): …`, `test: …`, `docs: …`, `ci: …`, `refactor: …`, `chore: …`.
- Коммит в `main` после CI автоматически разворачивается на сервере — см. [DEPLOY.md](DEPLOY.md).
