# Развёртывание

На сервере с Ubuntu 24.04 работают две службы systemd в песочнице — бот `assistant-bot` и API приложения `assistant-api` (только на `127.0.0.1:8000`): система доступна только для чтения, запись — только в `/var/lib/assistant`, привилегий нет, соединения в частные сети и link-local запрещены (loopback открыт). Снаружи открыт Caddy: HTTPS с автоматическим сертификатом, приложение из `webapp/dist` и `/api` → API.

| Путь | Что там |
|---|---|
| `/opt/assistant/app` | код (git) и окружение `.venv` |
| `/opt/assistant/app/webapp/dist` | собранное приложение; прежняя сборка — в `dist.previous`, пока деплой не завершился |
| `/var/lib/assistant/assistant.db` | база |
| `/etc/assistant/assistant.env` | токен и настройки, права `0640 root:assistant` |
| `/etc/caddy/Caddyfile` | настройки Caddy из `deploy/Caddyfile`, ставятся вручную |
| `/etc/caddy/assistant.env` | имя сайта `SITE_HOST` — отдельно от токена |
| `/var/backups/assistant` | ночные бэкапы (14 последних) и снимки перед деплоем (5 последних) |

## Как код попадает на сервер

1. Коммит в `main` запускает CI: ruff, mypy, тесты, проверку миграций.
2. После зелёного CI workflow `Deploy` подключается по SSH пользователем `deploy`. Его ключ позволяет выполнить ровно одну команду: `sudo /usr/local/sbin/assistant-deploy <sha>`.
3. Скрипт проверяет, что коммит есть в `main`, и собирает приложение в отдельной рабочей копии — прежняя версия в это время работает. Затем останавливает бота и API, делает снимок базы, обновляет код и зависимости, подменяет сборку приложения, применяет миграции и запускает обе службы.
4. Новая версия считается рабочей, когда бот записал в журнал «Bot started», а `/api/health` отвечает новым коммитом. Если за 30 секунд этого не случилось, скрипт возвращает базу из снимка, прежний код и прежнюю сборку приложения, а деплой в Actions становится красным. Если приложение не собралось, ничего не останавливается.

Адрес сервера и ключ хранятся только в секретах GitHub: `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.

## Команды на сервере

```bash
sudo systemctl status assistant-bot
sudo systemctl status assistant-api
sudo journalctl -u assistant-bot -n 50 -o cat          # журнал бота
sudo journalctl -u assistant-api -n 50 -o cat          # журнал API
sudo journalctl -t assistant-deploy -n 50 -o cat       # журнал деплоев
sudo /usr/local/sbin/assistant-deploy <sha>            # ручной деплой коммита из main
sudo systemctl list-timers assistant-backup.timer      # когда следующий бэкап
curl -s http://127.0.0.1:8000/api/health                 # версия и коммит API
sudo systemctl reload caddy                            # после правки Caddyfile
```

Подготовка сервера с нуля и восстановление из бэкапа — в [deploy/server-setup.md](../deploy/server-setup.md).
