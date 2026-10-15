# Развёртывание

На сервере с Ubuntu 24.04 работают две службы systemd в песочнице — бот `assistant-bot` и API приложения `assistant-api` (только на `127.0.0.1:8000`): система доступна только для чтения, запись — только в `/var/lib/assistant`, привилегий нет, соединения в частные сети, link-local и CGNAT `100.64.0.0/10` запрещены (loopback открыт). Снаружи открыт Caddy: HTTPS с автоматическим сертификатом, приложение из `webapp/dist` и `/api` → API.

| Путь | Что там |
|---|---|
| `/opt/assistant/app` | код (git) и окружение `.venv` |
| `/opt/assistant/app/webapp/dist` | собранное приложение; прежняя сборка — в `dist.previous`, пока деплой не завершился |
| `/var/lib/assistant/assistant.db` | база |
| `/etc/assistant/assistant.env` | токен и настройки, права `0640 root:assistant` |
| `/etc/caddy/Caddyfile` | настройки Caddy из `deploy/Caddyfile`, ставятся вручную |
| `/etc/caddy/assistant.env` | имя сайта `SITE_HOST` — отдельно от токена |
| `/var/backups/assistant` | ночные бэкапы (14 последних) и снимки перед деплоем (5 последних) |
| `/etc/systemd/system/assistant-{bot,api,backup}.service`, `assistant-backup.timer`, `/usr/local/sbin/assistant-{deploy,backup}`, `/etc/sudoers.d/assistant-deploy`, `/etc/systemd/system/caddy.service.d/assistant.conf` | из `deploy/`, ставятся вручную ([server-setup.md](../deploy/server-setup.md), разделы 4–5); автодеплой их не меняет |

## Как код попадает на сервер

1. Коммит в `main` запускает CI: для бота и API — ruff, mypy, тесты и проверку миграций, для приложения — ESLint, проверку типов, тесты, сборку и сборку демо с её проверкой.
2. После зелёного CI workflow `Deploy` подключается по SSH пользователем `deploy`. Его ключ позволяет выполнить ровно одну команду: `sudo /usr/local/sbin/assistant-deploy <sha>`.
3. Скрипт проверяет, что коммит есть в `main`, и собирает приложение в отдельной рабочей копии — прежняя версия в это время работает. Затем останавливает бота и API, делает снимок базы, обновляет код и зависимости, подменяет сборку приложения, применяет миграции и запускает обе службы.
4. Новая версия считается рабочей, когда бот записал в журнал «Bot started», а `/api/health` отвечает новым коммитом. Если за 30 секунд этого не случилось, скрипт возвращает базу из снимка, прежний код и прежнюю сборку приложения, а деплой в Actions становится красным. Если приложение не собралось, ничего не останавливается.

Адрес сервера и ключ хранятся только в секретах GitHub: `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.

## Демо на GitHub Pages

Демо приложения (раздел «Демо» в [DEVELOPMENT.md](DEVELOPMENT.md)) живёт по адресу `https://apelsinkos.github.io/personal-assistant-bot/` и к серверу не обращается вовсе. Публикует его workflow `Pages` (`.github/workflows/pages.yml`), отдельный от `Deploy`: сбой Pages не задерживает выкладку на сервер, а право публиковать сайт не оказывается рядом с её секретами.

1. После зелёного CI пуша в `main` этого репозитория задание `build` собирает демо (`npm run build:demo`) и проверяет сборку тем же `check-demo.mjs`, что и CI. CI пулл-реквеста, в том числе из форка с веткой `main`, ничего не публикует.
2. Публикуется только нынешний `main`: если `main` уже ушёл дальше — CI двух пушей закончился не по порядку или старый CI запустили заново, — задание ничего не собирает, и демо догоняет `main` со следующим зелёным пушем.
3. Задание `deploy` выкладывает сборку в окружение `github-pages`, которому разрешена только ветка `main`; на `main` запрещены force push и удаление.

Workflow не называет ни одного секрета: секреты выкладки на сервер — секреты окружения `production`, и заданиям Pages они недоступны. Ничего не коммитится, ветки `gh-pages` нет. Pages отдаёт страницы с кэшем около 10 минут, а бесплатен, пока репозиторий публичный: закрытый репозиторий на бесплатном плане теряет демо.

Pages включается один раз, со сборкой из Actions, а окружение `github-pages` ограничивается веткой `main`:

```bash
gh api -X POST repos/APELSINKos/personal-assistant-bot/pages -f build_type=workflow
gh api repos/APELSINKos/personal-assistant-bot/pages --jq '{html_url, build_type, https_enforced, public}'
gh api repos/APELSINKos/personal-assistant-bot/environments/github-pages/deployment-branch-policies --jq '[.branch_policies[].name]'
```

Первая проверка должна показать адрес демо, `workflow` и `true`, вторая — `["main"]`: включая Pages, GitHub может сам создать окружение с этим правилом, и тогда больше ничего не нужно. Только если окружения ещё нет (ответ 404) или `main` в списке нет, окружению задают список веток — `PUT` заодно создаёт окружение — и добавляют в него `main`, а затем повторяют вторую проверку:

```bash
gh api -X PUT repos/APELSINKos/personal-assistant-bot/environments/github-pages \
  -F 'deployment_branch_policy[protected_branches]=false' -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api -X POST repos/APELSINKos/personal-assistant-bot/environments/github-pages/deployment-branch-policies \
  -f name=main -f type=branch
```

Если Pages включили уже после пуша в `main`, первый запуск workflow упал; тогда его запускают вручную: `gh workflow run pages.yml --ref main`. Сломанное демо чинится следующим коммитом в `main`; в крайнем случае сайт снимается — `gh api -X DELETE repos/APELSINKos/personal-assistant-bot/pages` (до возвращения ссылки README на демо ведут в 404).

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
