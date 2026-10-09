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

- Ubuntu 24.04 with a sudo-capable account that already logs in over SSH
  with a key.
- Ports 22 (SSH), 80 and 443 open in the cloud provider's firewall (security
  group); sections 0 and 1 open them in ufw. Caddy serves the Mini App on 443
  and uses 80 to obtain and renew its certificate.

## 0. SSH and firewall

SSH takes keys only and lets in only the accounts it names; ufw turns on with
SSH allowed (section 1 adds the web ports), and fail2ban bans addresses that
keep failing to log in. The account the step is run from is the one SSH lets
in, and section 5 adds `deploy`. An existing `10-hardening.conf` is kept as
it is. Before running the step, open a second session (`ssh <server>`) and
keep it until a new login has worked: the reload leaves running sessions
alone, so a mistake can still be undone from there.

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
: "${SUDO_USER:?run it through sudo from your own account}"
apt-get update -qq
apt-get install -y -qq fail2ban
conf=/etc/ssh/sshd_config.d/10-hardening.conf
if [ ! -f "$conf" ]; then
  printf '%s\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' \
    'PermitRootLogin no' "AllowUsers $SUDO_USER" 'MaxAuthTries 3' 'LoginGraceTime 30' > "$conf"
fi
ufw allow 22/tcp >/dev/null
ufw --force enable >/dev/null
sshd -t
systemctl reload ssh
sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|allowusers|maxauthtries|logingracetime) '
ufw status verbose | grep -E '^(Status|Default):'
fail2ban-client status sshd | grep -F 'Status for the jail'
EOF
```

Expected: the six settings, with `allowusers` naming your account;
`Status: active` and `Default: deny (incoming)`; `Status for the jail: sshd`.
From here on a login without a key, or as another account, is refused.

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
- `WEBAPP_URL` — `https://<site host>/`, set after the first deploy (end of
  section 6), once the web front (section 4) answers over HTTPS; empty until
  then (the bot shows the Mini App buttons only when it is set).
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
    echo 'BOT_TOKEN='
    echo 'DATABASE_URL=sqlite+aiosqlite:////var/lib/assistant/assistant.db'
    echo 'WEBAPP_URL='
    echo 'LOG_LEVEL=INFO'
  } > /etc/assistant/assistant.env
  chown root:assistant /etc/assistant/assistant.env
  chmod 0640 /etc/assistant/assistant.env
fi
EOF
ssh -t <server> 'sudoedit /etc/assistant/assistant.env'
ssh <server> "sudo grep -c '^BOT_TOKEN=.\+' /etc/assistant/assistant.env"
```

Paste the token from @BotFather after `BOT_TOKEN=` in the editor: the token
is never typed on a command line or shown. Expected last line: `1`.

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
systemd-analyze security assistant-backup.service | tail -1
EOF
```

Expected: the backup run prints `no database yet, nothing to back up`; the
bot's and the API's security summaries show an exposure level of 3.5 or
lower, the backup's about 0.4 (it has no network at all). The bot and API
services ([assistant-bot.service](assistant-bot.service),
[assistant-api.service](assistant-api.service)) are only installed here, not
enabled or started: the first deploy starts them, and they are enabled right
after it (end of section 6).

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
ssh <server> 'curl -sSI https://<site host>/ | grep -iE "^(strict-transport|content-security|x-content-type|referrer|permissions|server|alt-svc)"'
```

Expected: the five security headers from the Caddyfile, and no `Server` or
`Alt-Svc` line (no HTTP/3: the firewall lets only TCP through to 443). Later
changes to the Caddyfile on `main` need only `caddy validate`
followed by `systemctl reload caddy`; the `systemctl restart caddy` above is
needed only for this first install, because the drop-in changes the unit's
environment. The Caddyfile takes its host name from `SITE_HOST`, which only
the Caddy service gets (through its drop-in), so a `caddy validate` run by
hand needs it loaded first:

```bash
ssh <server> 'sudo bash -c "set -a; . /etc/caddy/assistant.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"'
```

### Updating Caddy

Caddy comes from its own apt repository, which unattended-upgrades leaves
alone (it takes only Ubuntu's own pockets), and it is kept that way on
purpose: a Caddy release may read a configuration differently, so a new
version is validated by hand before it serves the site. Update it whenever a
release brings work on the server (as 2.6.1 does), and soon after Caddy
publishes a fix in its
[security advisories](https://github.com/caddyserver/caddy/security/advisories):

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
caddy version
apt-get update -qq
apt-get install -y -qq --only-upgrade caddy
caddy version
set -a; . /etc/caddy/assistant.env; set +a
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl restart caddy
sleep 5
curl -sSI "https://$SITE_HOST/" | grep -iE "^(strict-transport|content-security|x-content-type|referrer|permissions|server|alt-svc)" || true
curl -sS "https://$SITE_HOST/api/health"; echo
EOF
```

Expected: the old and the new version, `Valid configuration`, the five
security headers without `Server` or `Alt-Svc`, and the health JSON. If the
validation fails, put back the version that was installed
(`apt-cache policy caddy` lists them) with
`apt-get install -y --allow-downgrades caddy=<version>`, and read Caddy's
release notes before trying again.

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
conf=/etc/ssh/sshd_config.d/10-hardening.conf
if grep -q '^AllowUsers ' "$conf" 2>/dev/null && ! grep -q '^AllowUsers .*\bdeploy\b' "$conf"; then
  sed -i 's/^AllowUsers .*/& deploy/' "$conf"
fi
sshd -t && systemctl reload ssh
EOF
```

Expected: `visudo` reports `parsed OK`. `deploy` joins the `AllowUsers` line
of section 0 once, however often the step runs; with no such line SSH lets
every account with a key in, and nothing needs adding.

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

### First deploy (cutover)

Telegram hands a bot's messages to one poller only, so first stop and disable
whatever else polls the same token (the old server, a run on a laptop). Then
deploy the tip of `main` by hand (section 7): the deploy builds `.venv` and
the web app, creates the database and starts both services. It only starts
them: `enable` brings them back after a reboot. It also creates the database
under its `umask 0022`, so `chmod` makes the database the service's alone,
like its copies:

```bash
ssh <server> 'sudo /usr/local/sbin/assistant-deploy <main tip sha>'
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl enable assistant-api assistant-bot
chmod 0640 /var/lib/assistant/assistant.db*
systemctl is-enabled assistant-bot assistant-api
EOF
```

Expected: `deployed <sha>`, then `enabled` twice. Once
`https://<site host>/api/health` answers `200` (section 4), give the bot the
Mini App's address; it sets the menu button at start:

```bash
ssh <server> "sudo sed -i 's|^WEBAPP_URL=.*|WEBAPP_URL=https://<site host>/|' /etc/assistant/assistant.env && sudo systemctl restart assistant-api assistant-bot"
```

Expected: `/start` in the bot now ends with a «📱 Открыть приложение» button.

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

### Going from 2.2 to 2.3

Version 2.3 changes three files that are installed by hand: both units gain
`IPAddressDeny=` (no connections to link-local, private or CGNAT networks) and the
Caddyfile lets calendar files of up to 2 MB through to the API. Install them
once 2.3 is on `main`, before or after its deploy — the order does not matter,
both files work with 2.2 and 2.3 alike:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin main
show() { runuser -u assistant -- git show "origin/main:deploy/$1"; }
for unit in assistant-bot.service assistant-api.service; do
  show "$unit" > "/etc/systemd/system/$unit.new"
  mv "/etc/systemd/system/$unit.new" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl restart assistant-api assistant-bot
show Caddyfile > /etc/caddy/Caddyfile.new
set -a; . /etc/caddy/assistant.env; set +a
caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile
mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile
systemctl reload caddy
systemctl show -p IPAddressDeny --value assistant-bot
sleep 20
journalctl -u assistant-bot -n 20 -o cat --no-pager | grep -iE "started|error|exception" || true
curl -s http://127.0.0.1:8000/api/health; echo
EOF
```

Expected: `Valid configuration`, the denied ranges, `Bot started` and no errors in
the journal, and the health JSON. On its first start 2.3
builds the MIREA group directory: about 35 minutes of requests, three a
second; the bot's journal says `MIREA directory, full crawl: …` when it is
done. Until then a group the crawl has not reached yet cannot be found, and
the bot and the app say that the directory is still being built; links and
files work at once.

### Going back from 2.3 to 2.2

Version 2.3 adds migration `0003`. As with 2.2 → 2.1, undo it with the 2.3
code that is still deployed, then deploy the 2.2 commit on purpose:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
systemctl start assistant-backup.service
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic downgrade 0002'
EOF
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.2.0 commit sha>'
```

The downgrade drops the schedule tables: timetables, the group directory and
the lesson alert settings are gone, reminders, notes and habits stay. That is
why `assistant-backup.service` runs first: the deploy's own snapshot is taken
after the downgrade, when those tables are already gone. The copy is written to
`/var/backups/assistant/assistant-<UTC date>.db` and replaces today's nightly
copy if it is already there (`assistant-backup` names the file by the UTC
date and overwrites it, and so does the nightly run at 03:30 UTC, so before that
time copy the file under another name). If the copy fails, the commands above
stop before the downgrade. The new units and Caddyfile can stay as they are.

### Going from 2.3 to 2.4

Nothing is installed by hand: the deploy runs migration `0004` (the habits' emoji,
colour and weekly goal, with defaults for the habits that exist, and the
`share_cards` table) and installs Pillow with the other dependencies. A card
shared from the app is downloaded by Telegram from the site in `WEBAPP_URL`,
which both services already read from `/etc/assistant/assistant.env`.

### Going back from 2.4 to 2.3

As with 2.3 → 2.2, undo migration `0004` with the 2.4 code that is still
deployed, then deploy the 2.3 commit on purpose:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
systemctl start assistant-backup.service
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic downgrade 0003'
EOF
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.3.0 commit sha>'
```

The downgrade drops the cards kept for sharing and the habits' emoji, colour
and weekly goal: every habit counts as a daily one again, while the habits
and their marks stay. The backup runs first for the same reason as in
2.3 → 2.2: the deploy's own snapshot is taken after the downgrade. That copy is
the only up-to-date one with the goals, emoji and colours, and as there it is
`assistant-<UTC date>.db`, overwritten by the nightly run at 03:30 UTC: copy it
under another name before then.

### Going from 2.4 to 2.5

Nothing is installed by hand: the deploy runs migration `0005` (the users'
currency and monthly budget, and the `money_categories`, `money_entries`,
`money_words` and `money_alerts` tables). The 30-day rates come from the Bank
of Russia's own site (`https://www.cbr.ru/scripts/XML_dynamic.asp`), a public
address the services may already reach.

### Going back from 2.5 to 2.4

As with 2.4 → 2.3, undo migration `0005` with the 2.5 code that is still
deployed, then deploy the 2.4 commit on purpose:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
systemctl start assistant-backup.service
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic downgrade 0004'
EOF
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.4.0 commit sha>'
```

The downgrade drops the money tables and the users' currency and budget:
every entry, category and budget is gone, while everything else stays. The
backup runs first for the same reason as in 2.3 → 2.2: the deploy's own
snapshot is taken after the downgrade. That copy is the only up-to-date one
with the money, and as there it is `assistant-<UTC date>.db`, overwritten by
the nightly run at 03:30 UTC: copy it under another name before then.

### Going from 2.5 to 2.6

Nothing is installed by hand, and the Caddyfile and the units stay as they
are: the deploy runs migration `0006` (the notes' pins, and the `note_items`
and `weather_cities` tables). The forecast and the city search still come
from Open-Meteo (`api.open-meteo.com`, `geocoding-api.open-meteo.com`),
public addresses the services already reach.

From 2.6 on the bot sets its name, commands, descriptions and menu button in
the background, for at most 120 seconds, so `Bot started` reaches the journal
within the deploy's health check even while Telegram answers slowly; running
out of that time is only a warning in the journal.

### Going back from 2.6 to 2.5

As with 2.5 → 2.4, undo migration `0006` with the 2.6 code that is still
deployed, then deploy the 2.5.1 commit on purpose:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
systemctl start assistant-backup.service
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic downgrade 0005'
EOF
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.5.1 commit sha>'
```

The downgrade drops the checklist items, the extra weather cities and the
notes' pins; the notes themselves stay (a checklist keeps its title), and so
does everything else. It keeps the AUTOINCREMENT counters of the two dropped
tables in `sqlite_sequence`, so after a later upgrade to 2.6 new items and
cities go on numbering where they stopped, and a button left in a chat never
reaches a new item or city. The pin column is removed by SQLite's own
`ALTER TABLE … DROP COLUMN` (SQLite 3.35 or newer; the server has 3.45),
which leaves `notes` with its counter as it is. The backup runs first for the
same reason as in 2.3 → 2.2: the deploy's own snapshot is taken after the
downgrade. That copy is the only up-to-date one with the items, the cities
and the pins, and as there it is `assistant-<UTC date>.db`, overwritten by
the nightly run at 03:30 UTC: copy it under another name before then.

### Going from 2.6.0 to 2.6.1

Version 2.6.1 has no migration, but it changes seven files that are installed
by hand, and the deploy changes none of them:

- `assistant-deploy` and `assistant-backup` write the copies of the database
  `0640`, for the service alone;
- `assistant-bot.service` and `assistant-api.service` hand the process
  systemd's notify socket (`NotifyAccess=main`): 2.6.1 turns the watchdog on
  itself, and a bot or API frozen for two minutes is killed and started
  again, with the stacks of its threads in the journal;
- `assistant-backup.service` runs the nightly copy in the bot's sandbox and
  with no network at all;
- `caddy-assistant.conf` restarts Caddy after a crash;
- the `Caddyfile` turns HTTP/3 off (the firewall lets only TCP through to
  443) and drops the exception that let the API's docs load their script from
  a CDN: 2.6.1 keeps the docs off on the server.

As soon as 2.6.1 is on `main`, while its CI still runs, install the two
scripts, so that the deploy which follows writes its snapshot `0640` already:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin main
show() { runuser -u assistant -- git show "origin/main:deploy/$1"; }
for script in assistant-deploy assistant-backup; do
  new="/usr/local/sbin/$script.new"
  show "$script" > "$new"
  bash -n "$new"
  chmod 0755 "$new"
  mv "$new" "/usr/local/sbin/$script"
done
EOF
```

If the deploy gets there first, nothing is lost: the `chmod` below covers its
snapshot too. Once the deploy has finished (`journalctl -t assistant-deploy`
says `deployed <sha>`), install the units and Caddy's files, restart the
services in the new units, make every copy of the database the service's
alone and run the nightly copy once:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
cd /opt/assistant/app
runuser -u assistant -- git fetch --quiet origin main
show() { runuser -u assistant -- git show "origin/main:deploy/$1"; }
for unit in assistant-bot.service assistant-api.service assistant-backup.service; do
  show "$unit" > "/etc/systemd/system/$unit.new"
  mv "/etc/systemd/system/$unit.new" "/etc/systemd/system/$unit"
done
show caddy-assistant.conf > /etc/systemd/system/caddy.service.d/assistant.conf.new
mv /etc/systemd/system/caddy.service.d/assistant.conf.new /etc/systemd/system/caddy.service.d/assistant.conf
systemctl daemon-reload
systemctl restart assistant-api assistant-bot
show Caddyfile > /etc/caddy/Caddyfile.new
set -a; . /etc/caddy/assistant.env; set +a
caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile
mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile
systemctl reload caddy
chmod 0640 /var/lib/assistant/assistant.db* /var/backups/assistant/*.db
systemctl start assistant-backup.service
journalctl -u assistant-backup -n 1 -o cat --no-pager
systemd-analyze security assistant-backup.service | tail -1
sleep 20
journalctl -u assistant-bot -n 20 -o cat --no-pager | grep -iE "started|watchdog|error|exception" || true
curl -s http://127.0.0.1:8000/api/health; echo
systemctl show -p WatchdogUSec assistant-bot assistant-api
ss -Hulpn 'sport = :443' | grep . || echo 'UDP 443: nothing listens'
headers=$(curl -sSI "https://$SITE_HOST/")
grep -i '^alt-svc' <<<"$headers" || echo 'no Alt-Svc'
find /var/lib/assistant /var/backups/assistant -name '*.db*' -perm /o=r | grep . || echo 'no copy is readable by others'
EOF
```

Expected: `Valid configuration`; `backup written: …` and an exposure level of
about 0.4 for the backup; `Bot started`, `systemd watchdog on: 120 s` and no
errors in the bot's journal; the health JSON with the 2.6.1 commit;
`WatchdogUSec=2min` twice; `UDP 443: nothing listens`; `no Alt-Svc`;
`no copy is readable by others`. If Caddy still holds UDP 443 after the
reload, one `systemctl restart caddy` closes it. Then update Caddy as
section 4 describes (Updating Caddy).

### Going back from 2.6.1 to 2.6.0

Version 2.6.1 has no migration, so there is nothing to undo first: deploy the
2.6.0 commit on purpose.

```bash
ssh <server> 'sudo DEPLOY_ALLOW_OLDER=1 /usr/local/sbin/assistant-deploy <v2.6.0 commit sha>'
```

The scripts, units and Caddy files of 2.6.1 can stay as they are: 2.6.0
never turns the watchdog on, so systemd does not watch it.

## 8. Restore from a backup

Nightly backups live in `/var/backups/assistant`
(`assistant-YYYYMMDD.db`, 14 kept); every deploy also leaves a
pre-deploy snapshot there (`pre-deploy-<sha12>.db`, 5 kept), taken before its
migrations run. All of them are on the same disk as the database, and none
leaves the server: losing the disk or the server loses the copies too. To
restore one by hand:

```bash
ssh <server> 'sudo bash -s' <<'EOF'
set -euo pipefail
systemctl stop assistant-bot assistant-api
install -o assistant -g assistant -m 0640 /var/backups/assistant/<snapshot>.db /var/lib/assistant/assistant.db
rm -f /var/lib/assistant/assistant.db-wal /var/lib/assistant/assistant.db-shm
cd /opt/assistant/app
runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; exec .venv/bin/alembic upgrade head'
systemctl start assistant-api assistant-bot
EOF
```

Replace `<snapshot>` with the file to restore. Removing the `-wal`/`-shm`
files prevents SQLite from replaying write-ahead log entries that belong to
the database file being replaced. The services never migrate the database
themselves, and a copy made before the newest migration (any pre-deploy
snapshot, a nightly copy from before a release) has the older schema:
`alembic upgrade head` brings it to the schema of the checked-out code, as a
deploy does. If it stops with `Can't locate revision`, the copy is newer than
the code (it was made before a downgrade, section 7): the services stay
stopped; deploy that version's commit, and the deploy starts them. The
revision of a copy can be read without touching it — `immutable=1` keeps
SQLite from creating `-wal`/`-shm` files next to it:

```bash
ssh <server> "sudo runuser -u assistant -- sqlite3 'file:/var/backups/assistant/<snapshot>.db?immutable=1' 'select version_num from alembic_version'"
```

## 9. Changing the site host

The Mini App's address is a wildcard-DNS name that embeds the server's Elastic
IP. If that service stops answering, or the site moves to the owner's own
domain, point a new name at the same IP (for `nip.io` nothing is needed, for a
domain an `A` record), then:

```bash
ssh <server> 'sudo SITE_HOST=<new site host> bash -s' <<'EOF'
set -euo pipefail
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
printf 'SITE_HOST=%s\n' "$SITE_HOST" > /etc/caddy/assistant.env
systemctl restart caddy
code=""
for _ in $(seq 12); do
  sleep 5
  code=$(curl -sS -o /dev/null -w '%{http_code}' "https://$SITE_HOST/api/health" 2>/dev/null || true)
  if [[ $code == 200 ]]; then
    break
  fi
done
echo "$code"
[[ $code == 200 ]]
sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://$SITE_HOST/|" /etc/assistant/assistant.env
systemctl restart assistant-api assistant-bot
EOF
```

Expected: `Valid configuration`, then `200` once Caddy has the certificate for
the new name, which it gets by itself; only then does the bot get the new
address, and it sets its menu button to it at start. If the step stops
without `200`, the bot still has the old address and Caddy serves only the
new one: run the step again with the old name to go back. Buttons already sent
into chats keep the old address; a share card prepared before the change does
too. A Main Mini App link set in @BotFather is changed there. If the IP itself
changed (the Elastic IP was released, the server was rebuilt), the GitHub
secrets `DEPLOY_HOST` and `DEPLOY_KNOWN_HOSTS` are set again as in section 6,
and the `<server>` alias is pointed at the new address.

## Security notes

SSH access for GitHub Actions needs port 22 reachable from GitHub-hosted
runners, whose source addresses are not fixed and can change. If SSH on the
server is ever restricted to a single IP address, deploys from GitHub-hosted
runners will stop working; switch to a self-hosted runner on the same
network, or fall back to running `assistant-deploy` manually (section 7)
from a host that is still allowed in.
