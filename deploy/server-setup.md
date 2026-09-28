# Server setup

Runbook for preparing an Ubuntu 24.04 server to run the Personal Assistant bot
and for wiring up the automated deploy described in
[assistant-deploy](assistant-deploy) and [../.github/workflows/deploy.yml](../.github/workflows/deploy.yml).
The server is referred to as `<server>` throughout — substitute the operator's
SSH alias or hostname for it; do not write the address into this file.

## Prerequisites

- Ubuntu 24.04 with a sudo-capable account already reachable over SSH.
- Port 22 (SSH) open. The bot makes only outbound HTTPS connections to
  Telegram, so no other inbound port is required.

## 1. Packages and uv

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
apt-get update -qq && apt-get install -y -qq sqlite3 git curl
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/0.12.19/install.sh |
    env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
EOF
```

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
- `WEBAPP_URL` — left empty until the Mini App exists.
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

Install the unit files and the scripts from branch `v2` (they are not on
`main` yet) and start the nightly backup timer:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin v2
show() { runuser -u assistant -- git show "origin/v2:deploy/$1"; }
show assistant-deploy > /usr/local/sbin/assistant-deploy
show assistant-backup > /usr/local/sbin/assistant-backup
chmod 0755 /usr/local/sbin/assistant-deploy /usr/local/sbin/assistant-backup
for unit in assistant-bot.service assistant-backup.service assistant-backup.timer; do
  show "$unit" > "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now assistant-backup.timer
systemctl start assistant-backup.service
journalctl -u assistant-backup -n 3 -o cat --no-pager
systemd-analyze security assistant-bot.service | tail -1
EOF
```

Expected: the backup run prints `no database yet, nothing to back up`; the
security summary shows an exposure level of 3.5 or lower. The bot service
itself ([assistant-bot.service](assistant-bot.service)) is only installed
here, not enabled or started — that happens at cutover.

## 5. Deploy user

Install the sudoers rule from [sudoers-assistant-deploy](sudoers-assistant-deploy)
and allow the `deploy` account through SSH:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
runuser -u assistant -- git -C /opt/assistant/app show origin/v2:deploy/sudoers-assistant-deploy \
  > /etc/sudoers.d/assistant-deploy
chmod 0440 /etc/sudoers.d/assistant-deploy
visudo -cf /etc/sudoers.d/assistant-deploy
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

```bash
HOST=$(ssh -G <server> | awk '/^hostname /{print $2}')
gh api -X PUT repos/APELSINKos/personal-assistant-bot/environments/production >/dev/null
gh secret set DEPLOY_SSH_KEY < "$SCRATCH/deploy_key"
printf '%s' "$HOST" | gh secret set DEPLOY_HOST
ssh-keyscan -t ed25519 "$HOST" 2>/dev/null | gh secret set DEPLOY_KNOWN_HOSTS
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
gh secret list
```

Expected: `usage: …` with `exit 2`; `refusing: 000… is not on origin/main`
with `exit 2`; the interactive attempt gets no shell (it prints the usage
line — `restrict` refuses a PTY); `gh secret list` shows the three secret
names, never their values.

## 7. Manual deploy and rollback

A deploy can also be triggered by hand from the server, for a drill or when
Actions is unavailable:

```bash
ssh <server> 'sudo /usr/local/sbin/assistant-deploy <40-character commit sha>'
```

Exit codes: `0` deployed; `1` failed and already rolled back to the previous
commit; `2` bad argument or the sha is not on `origin/main`; `3` another
deploy is already running.

Everything the script prints, on success or failure, also goes to the
journal under the `assistant-deploy` syslog identifier:

```bash
ssh <server> 'journalctl -t assistant-deploy -n 100 --no-pager'
```

## 8. Restore from a backup

Nightly backups live in `/var/backups/assistant`
(`assistant-YYYYMMDD.db`, 14 kept); a failed deploy also leaves a
pre-deploy snapshot there (`pre-deploy-<sha12>.db`, 5 kept). To restore one
by hand:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot
cp /var/backups/assistant/<snapshot>.db /var/lib/assistant/assistant.db
rm -f /var/lib/assistant/assistant.db-wal /var/lib/assistant/assistant.db-shm
systemctl start assistant-bot
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
