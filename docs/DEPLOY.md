# Развёртывание

Бот работает на сервере с Ubuntu 24.04 как служба systemd `assistant-bot` в песочнице: система доступна только для чтения, запись — только в `/var/lib/assistant`, привилегий нет.

| Путь | Что там |
|---|---|
| `/opt/assistant/app` | код (git) и окружение `.venv` |
| `/var/lib/assistant/assistant.db` | база |
| `/etc/assistant/assistant.env` | токен и настройки, права `0640 root:assistant` |
| `/var/backups/assistant` | ночные бэкапы (14 последних) и снимки перед деплоем (5 последних) |

## Как код попадает на сервер

1. Коммит в `main` запускает CI: ruff, mypy, тесты, проверку миграций.
2. После зелёного CI workflow `Deploy` подключается по SSH пользователем `deploy`. Его ключ позволяет выполнить ровно одну команду: `sudo /usr/local/sbin/assistant-deploy <sha>`.
3. Скрипт проверяет, что коммит есть в `main`, останавливает бота, делает снимок базы, обновляет код и зависимости, применяет миграции и запускает бота.
4. Если бот не поднялся за 30 секунд, скрипт возвращает базу из снимка и прежнюю версию кода, а деплой в Actions становится красным.

Адрес сервера и ключ хранятся только в секретах GitHub: `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.

## Команды на сервере

```bash
sudo systemctl status assistant-bot
sudo journalctl -u assistant-bot -n 50 -o cat          # журнал бота
sudo journalctl -t assistant-deploy -n 50 -o cat       # журнал деплоев
sudo /usr/local/sbin/assistant-deploy <sha>            # ручной деплой коммита из main
sudo systemctl list-timers assistant-backup.timer      # когда следующий бэкап
```

Подготовка сервера с нуля и восстановление из бэкапа — в [deploy/server-setup.md](../deploy/server-setup.md).
