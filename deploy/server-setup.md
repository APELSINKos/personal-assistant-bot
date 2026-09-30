# Server setup

Runbook for preparing an Ubuntu 24.04 server to run the Personal Assistant bot
and for wiring up the automated deploy described in
[assistant-deploy](assistant-deploy) and [../.github/workflows/deploy.yml](../.github/workflows/deploy.yml).
Besides the bot it covers the API and the Mini App behind Caddy.
The server is referred to as `<server>` throughout — substitute the operator's
SSH alias or hostname for it; do not write the address into this file.
The Mini App's host name is referred to as `<site host>` — a name that
resolves to the server's address; do not write it into this file either.

## Prerequisites

- Ubuntu 24.04 with a sudo-capable account already reachable over SSH.
- Ports 22 (SSH), 80 and 443 open, both in the cloud provider's firewall
  (security group) and in ufw. Caddy serves the Mini App on 443 and uses 80
  to obtain and renew its certificate.

## 1. Packages and uv

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
apt-get update -qq && apt-get install -y -qq sqlite3 git curl gpg
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/0.12.19/install.sh |
    env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
install -d -m 0755 /etc/apt/keyrings
# Node.js 24 (NodeSource) builds the Mini App during deploys.
if [ ! -f /etc/apt/sources.list.d/nodesource.list ]; then
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key |
    gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
fi
# Caddy (official repository) terminates HTTPS for the Mini App and the API.
if [ ! -f /etc/apt/sources.list.d/caddy-stable.list ]; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key |
    gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
fi
apt-get update -qq && apt-get install -y -qq nodejs caddy
# 1 GB of swap: headroom for the web app build next to the running services.
if [ -z "$(swapon --show --noheadings)" ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
fi
[ ! -f /swapfile ] || grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
node --version && caddy version && swapon --show --noheadings
EOF
```
Expected: `v24.…`, `v2.11.…`, one swap line. Installing the package starts
Caddy with its welcome page on port 80; section 4 replaces it.

## 2. Users and directories

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
id assistant >/dev/null 2>&1 || useradd --system --home-dir /opt/assistant --shell /usr/sbin/nologin assistant
id deploy >/dev/null 2>&1 || { useradd --create-home --shell /bin/bash deploy; passwd -l deploy; }
install -d -o assistant -g assistant -m 0755 /opt/assistant
install -d -o assistant -g assistant -m 0750 /var/lib/assistant /var/backups/assistant
install -d -o root -g assistant -m 0750 /etc/assistant
EOF
```

`assistant` owns the code and the runtime state and cannot log in.
`deploy` is the account GitHub Actions connects as; it cannot log in with a
password and has no shell access of its own beyond the forced command set up
in section 5.

## 3. Code and environment file

Clone the repository as `assistant` and write
`/etc/assistant/assistant.env` (owner `root:assistant`, mode `0640`, readable
only by root and the `assistant` group):

- `BOT_TOKEN` — the Telegram bot token.
- `DATABASE_URL` — `sqlite+aiosqlite:////var/lib/assistant/assistant.db`.
- `WEBAPP_URL` — `https://<site host>/` once the web front (section 4) answers
  over HTTPS; empty until then (the bot shows the Mini App buttons only when
  it is set).
- `LOG_LEVEL` — `INFO`.

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
[ -d /opt/assistant/app/.git ] ||
  runuser -u assistant -- git clone --quiet https://github.com/APELSINKos/personal-assistant-bot.git /opt/assistant/app
runuser -u assistant -- git -C /opt/assistant/app fetch --quiet origin
if [ ! -f /etc/assistant/assistant.env ]; then
  umask 027
  {
    grep '^BOT_TOKEN=' /opt/tgbot/app/.env
    echo 'DATABASE_URL=sqlite+aiosqlite:////var/lib/assistant/assistant.db'
    echo 'WEBAPP_URL='
    echo 'LOG_LEVEL=INFO'
  } > /etc/assistant/assistant.env
  chown root:assistant /etc/assistant/assistant.env
  chmod 0640 /etc/assistant/assistant.env
fi
grep -c '^BOT_TOKEN=.\+' /etc/assistant/assistant.env
EOF
```

Expected last line: `1` (the token was copied from the old bot's environment
file; its value is never shown). Substitute another source for `BOT_TOKEN` if
the old bot is not on the same host.

## 4. Services and backups

Install the unit files and the scripts from the branch being deployed
(`main`) and start the nightly backup timer:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin main
show() { runuser -u assistant -- git show "origin/main:deploy/$1"; }
# Each script is checked before it replaces the one in use (the rename is atomic).
for script in assistant-deploy assistant-backup; do
  new="/usr/local/sbin/$script.new"
  show "$script" > "$new"
  bash -n "$new"
  chmod 0755 "$new"
  mv "$new" "/usr/local/sbin/$script"
done
for unit in assistant-bot.service assistant-api.service assistant-backup.service assistant-backup.timer; do
  show "$unit" > "/etc/systemd/system/$unit.new"
  mv "/etc/systemd/system/$unit.new" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now assistant-backup.timer
systemctl start assistant-backup.service
journalctl -u assistant-backup -n 3 -o cat --no-pager
systemd-analyze security assistant-bot.service | tail -1
systemd-analyze security assistant-api.service | tail -1
EOF
```

Expected: the backup run prints `no database yet, nothing to back up`; both
security summaries show an exposure level of 3.5 or lower. The bot and API
services ([assistant-bot.service](assistant-bot.service),
[assistant-api.service](assistant-api.service)) are only installed here, not
enabled or started — that happens at cutover
(`systemctl enable --now assistant-api assistant-bot`).

### Web front

Caddy serves the Mini App from `/opt/assistant/app/webapp/dist` (the deploy
script builds it there) and proxies `/api` to the API on `127.0.0.1:8000`,
with a certificate it obtains and renews by itself. Its host name comes from
its own environment file, so Caddy never reads `/etc/assistant/assistant.env`
and never sees the bot token. Like the units, the Caddyfile is installed by
hand from `origin/main` — the deploy script never changes web server
configuration.

```bash
ssh <server> 'sudo SITE_HOST=<site host> bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin main
show() { runuser -u assistant -- git show "origin/main:deploy/$1"; }
printf 'SITE_HOST=%s\n' "$SITE_HOST" > /etc/caddy/assistant.env
chmod 0644 /etc/caddy/assistant.env
install -d -m 0755 /etc/systemd/system/caddy.service.d
show caddy-assistant.conf > /etc/systemd/system/caddy.service.d/assistant.conf.new
mv /etc/systemd/system/caddy.service.d/assistant.conf.new /etc/systemd/system/caddy.service.d/assistant.conf
show Caddyfile > /etc/caddy/Caddyfile.new
caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile
mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl restart caddy
code=""
for _ in $(seq 12); do
  sleep 5
  code=$(curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}' "https://$SITE_HOST/api/health" 2>/dev/null || true)
  if [[ $code == 200* ]]; then
    break
  fi
done
echo "$code"
EOF
```

Expected: `Valid configuration`, then `200 0` once the API answers — the
loop retries for up to a minute while Caddy's certificate is being issued
and the API starts, without aborting on a `curl` failure in between; `502 0`
if it times out before the API is up (the certificate still verified;
nothing behind it yet). The headers can be checked at any time:

```bash
ssh <server> 'curl -sSI https://<site host>/ | grep -iE "^(strict-transport|content-security|x-content-type|referrer|permissions|server)"'
```

Expected: the five security headers from the Caddyfile and no `Server`
line. Later changes to the Caddyfile on `main` need only `caddy validate`
followed by `systemctl reload caddy`; the `systemctl restart caddy` above is
needed only for this first install, because the drop-in changes the unit's
environment. The Caddyfile takes its host name from `SITE_HOST`, which only
the Caddy service gets (through its drop-in), so a `caddy validate` run by
hand needs it loaded first:

```bash
ssh <server> 'sudo bash -c "set -a; . /etc/caddy/assistant.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"'
```

## 5. Deploy user

Install the sudoers rule from [sudoers-assistant-deploy](sudoers-assistant-deploy)
and allow the `deploy` account through SSH:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
# sudo skips files whose name contains a dot, so the rule is checked before it takes effect.
runuser -u assistant -- git -C /opt/assistant/app show origin/main:deploy/sudoers-assistant-deploy \
  > /etc/sudoers.d/assistant-deploy.new
chmod 0440 /etc/sudoers.d/assistant-deploy.new
visudo -cf /etc/sudoers.d/assistant-deploy.new
mv /etc/sudoers.d/assistant-deploy.new /etc/sudoers.d/assistant-deploy
sed -i 's/^AllowUsers ubuntu$/AllowUsers ubuntu deploy/' /etc/ssh/sshd_config.d/10-hardening.conf
sshd -t && systemctl reload ssh
EOF
```

Expected: `visudo` reports `parsed OK`.

Generate the deploy key locally (`$SCRATCH` below is a temporary directory;
the private key never leaves it except into the GitHub secret in section 6,
and is deleted once uploaded) and install its public half as a forced
command, so the key can only ever run `assistant-deploy` with the sha the
caller supplied:

```bash
ssh-keygen -q -t ed25519 -N "" -C "github-actions-deploy" -f "$SCRATCH/deploy_key"
{ printf 'restrict,command="sudo /usr/local/sbin/assistant-deploy \\"$SSH_ORIGINAL_COMMAND\\"" '; cat "$SCRATCH/deploy_key.pub"; } |
  ssh <server> 'sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh && sudo tee /home/deploy/.ssh/authorized_keys >/dev/null && sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys && sudo chmod 600 /home/deploy/.ssh/authorized_keys'
```

## 6. GitHub secrets

Create the `production` environment and restrict it to deployments of the
`main` branch only, so a workflow run on any other branch or ref can never
use its secrets even if the workflow file is changed to try:

```bash
gh api -X PUT repos/APELSINKos/personal-assistant-bot/environments/production \
  -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true' >/dev/null
gh api -X POST repos/APELSINKos/personal-assistant-bot/environments/production/deployment-branch-policies \
  -f name=main >/dev/null
```

(`-F` sends these two fields as JSON booleans, not strings — `gh api -f` always sends a
string, which the API rejects here with "is not a boolean".)

Set the secrets on that environment (`--env production`, not repository-wide):

```bash
HOST=$(ssh -G <server> | awk '/^hostname /{print $2}')
gh secret set DEPLOY_SSH_KEY --env production < "$SCRATCH/deploy_key"
printf '%s' "$HOST" | gh secret set DEPLOY_HOST --env production
ssh-keyscan -t ed25519 "$HOST" 2>/dev/null | gh secret set DEPLOY_KNOWN_HOSTS --env production
```

Verify the forced command before deleting the key (both calls must be
refused with exit code 2 — the second one exercises sudo, `runuser`,
`git fetch` and the ancestor check):

```bash
ssh -i "$SCRATCH/deploy_key" -o IdentitiesOnly=yes "deploy@$HOST" "not-a-sha"; echo "exit $?"
ssh -i "$SCRATCH/deploy_key" -o IdentitiesOnly=yes "deploy@$HOST" "$(printf '0%.0s' {1..40})"; echo "exit $?"
ssh -i "$SCRATCH/deploy_key" -o IdentitiesOnly=yes -t "deploy@$HOST" 2>&1 | head -2; echo "shell attempt done"
rm -f "$SCRATCH"/deploy_key "$SCRATCH"/deploy_key.pub
unset HOST
gh secret list --env production
```

Expected: `usage: …` with `exit 2`; `refusing: 000… is not on origin/main`
with `exit 2`; the interactive attempt gets no shell (it prints the usage
line — `restrict` refuses a PTY); `gh secret list --env production` shows
the three secret names, never their values.

## 7. Manual deploy and rollback

A deploy can also be triggered by hand from the server, for a drill or when
Actions is unavailable:

```bash
ssh <server> 'sudo /usr/local/sbin/assistant-deploy <40-character commit sha>'
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | deployed, or skipped because the sha is older than (an ancestor of) the commit already running |
| `1` | the deploy failed; the previously running commit is still up (the web app did not build) or up again (rolled back) |
| `2` | refused — bad argument, invalid branch name, not root, the git fetch of `origin/main` failed, or the sha is not on `origin/main`; nothing was stopped |
| `3` | another deploy is already running |
| `4` | the rollback did not come up healthy — manual attention needed |

The web app is built in a scratch worktree (`/opt/assistant/build`) before
anything is stopped, so the bot keeps running during the build, and the
previous build stays in `webapp/dist.previous` until the new commit is
healthy. A commit counts as healthy when the bot logged `Bot started` in its
new run and `/api/health` reports that commit.

By default the script refuses to move backwards: if the given sha is an
ancestor of the commit currently running, it exits `0` without touching
anything (this is what keeps an out-of-order Actions run, or a leaked deploy
key, from ever downgrading production). Root can override this from the
server to deploy an older commit on purpose, for example to roll back by
hand:

```bash
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <older commit sha>'
```

If a push to `main` was skipped (exit `0`) because CI for a later push
finished first and that push was deployed before this one's turn came up, no
action is needed: the commit that is running is newer and already contains
this change, and redeploying the skipped commit would just skip again.
Re-running the `Deploy` workflow only helps for the *newest* commit on
`main`, and only when its own deploy run failed or was cancelled before it
finished — in that case, re-run it for that commit from the Actions tab (or
push an empty commit to `main`) to retry it.

Root can also point the script at a different branch for a drill, without
touching what GitHub Actions is allowed to deploy (`DEPLOY_BRANCH` and
`DEPLOY_ALLOW_OLDER` are both stripped from the environment before the
`deploy` user's forced command runs, by the sudoers rule in section 5):

```bash
ssh <server> 'sudo DEPLOY_BRANCH=some-branch /usr/local/sbin/assistant-deploy <sha on some-branch>'
```

If the drill commit is left deployed afterwards (rather than reverted right
away), redeploy the tip of `main` before the next automated deploy is due:

```bash
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <main tip sha>'
```

Otherwise `main`'s own commits can look like an ancestor of the drill
commit to the out-of-order check, and pushes to `main` get skipped instead
of deployed until a commit that is not an ancestor of it comes along.

Everything the script prints, on success or failure, also goes to the
journal under the `assistant-deploy` syslog identifier:

```bash
ssh <server> 'journalctl -t assistant-deploy -n 100 --no-pager'
```

### Going back from 2.2 to 2.1

Version 2.2 adds migration `0002`, which 2.1 does not know, and a deploy only
ever upgrades the schema. To go back to 2.1, first undo the migration with the
2.2 code that is still deployed, then deploy the 2.1 commit on purpose:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic downgrade 0001'
EOF
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.1.0 commit sha>'
```

The services stay stopped between the two commands (2.2 does not run on the
old schema); the deploy starts them again. No reminder is lost: a pending
repeat stays as a one-off at its next firing, and one marked done counts as
sent. If that deploy fails and brings 2.2 back, stop both services, run the
same `runuser` line with `alembic upgrade head` instead, and start them again.

## 8. Restore from a backup

Nightly backups live in `/var/backups/assistant`
(`assistant-YYYYMMDD.db`, 14 kept); a failed deploy also leaves a
pre-deploy snapshot there (`pre-deploy-<sha12>.db`, 5 kept). To restore one
by hand:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
install -o assistant -g assistant -m 0640 /var/backups/assistant/<snapshot>.db /var/lib/assistant/assistant.db
rm -f /var/lib/assistant/assistant.db-wal /var/lib/assistant/assistant.db-shm
systemctl start assistant-api assistant-bot
EOF
```

Replace `<snapshot>` with the file to restore. Removing the `-wal`/`-shm`
files prevents SQLite from replaying write-ahead log entries that belong to
the database file being replaced.

## Security notes

SSH access for GitHub Actions needs port 22 reachable from GitHub-hosted
runners, whose source addresses are not fixed and can change. If SSH on the
server is ever restricted to a single IP address, deploys from GitHub-hosted
runners will stop working; switch to a self-hosted runner on the same
network, or fall back to running `assistant-deploy` manually (section 7)
from a host that is still allowed in.
