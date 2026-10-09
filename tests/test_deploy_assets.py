from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
WILDCARD_HOST = re.compile(r"\d{1,3}(?:-\d{1,3}){3}\.(?:sslip|nip)\.io")
# Spec 10.1, verbatim.
SPEC_CSP = (
    "default-src 'self'; script-src 'self' https://telegram.org; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-ancestors 'self' https://web.telegram.org; "
    "base-uri 'none'; form-action 'self'"
)
needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the deploy scripts run on Linux",
)
# The sandbox every unit shares; the network rules are each unit's own.
SANDBOX = (
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "PrivateDevices=true",
    "ProtectSystem=strict",
    "ProtectHome=true",
    "ProtectHostname=true",
    "ProtectClock=true",
    "ProtectKernelTunables=true",
    "ProtectKernelModules=true",
    "ProtectKernelLogs=true",
    "ProtectControlGroups=true",
    "ProtectProc=invisible",
    "ProcSubset=pid",
    "RestrictSUIDSGID=true",
    "RestrictNamespaces=true",
    "RestrictRealtime=true",
    "LockPersonality=true",
    "RemoveIPC=true",
    "CapabilityBoundingSet=",
    "AmbientCapabilities=",
    "SystemCallArchitectures=native",
    "SystemCallFilter=@system-service",
    "SystemCallFilter=~@privileged @resources",
)


@pytest.mark.parametrize(
    ("unit", "module"),
    [("assistant-bot.service", "assistant.bot"), ("assistant-api.service", "assistant.api")],
)
def test_units_are_sandboxed(unit: str, module: str) -> None:
    lines = (DEPLOY / unit).read_text(encoding="utf-8").splitlines()
    for expected in (
        "User=assistant",
        "EnvironmentFile=/etc/assistant/assistant.env",
        f"ExecStart=/opt/assistant/app/.venv/bin/python -m {module}",
        "Restart=always",
        "StateDirectory=assistant",
        *SANDBOX,
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "IPAddressDeny=169.254.0.0/16 fe80::/10 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 "
        "100.64.0.0/10 fc00::/7",
    ):
        assert expected in lines, expected
    assert not [line for line in lines if line.startswith("IPAddressAllow")]


def test_the_backup_is_sandboxed_with_no_network() -> None:
    lines = (DEPLOY / "assistant-backup.service").read_text(encoding="utf-8").splitlines()
    for expected in (
        "User=assistant",
        "ExecStart=/usr/local/sbin/assistant-backup",
        # The database with its -wal and -shm, and the folder of the copies.
        "ReadWritePaths=/var/lib/assistant /var/backups/assistant",
        *SANDBOX,
        # It copies a local file into a local folder.
        "PrivateNetwork=true",
        "RestrictAddressFamilies=AF_UNIX",
        "IPAddressDeny=any",
    ):
        assert expected in lines, expected
    assert not [line for line in lines if line.startswith("EnvironmentFile=")]


@pytest.mark.parametrize(
    ("unit", "module"),
    [("assistant-bot.service", "assistant.bot"), ("assistant-api.service", "assistant.api")],
)
def test_the_process_turns_the_watchdog_on_itself(unit: str, module: str) -> None:
    lines = (DEPLOY / unit).read_text(encoding="utf-8").splitlines()
    assert "NotifyAccess=main" in lines
    # NotifyAccess=main takes the keep-alives from the main process only: the interpreter
    # itself, started with no wrapper.
    assert [line for line in lines if line.startswith("ExecStart=")] == [
        f"ExecStart=/opt/assistant/app/.venv/bin/python -m {module}"
    ]
    # A watchdog kill (SIGABRT) leaves the stack of every thread in the journal.
    assert "Environment=PYTHONFAULTHANDLER=1" in lines
    # WatchdogSec= here would also watch an older commit after a rollback, which never feeds
    # the watchdog: it would be killed every two minutes.
    assert not [line for line in lines if line.startswith("WatchdogSec=")]
    # A start limit would leave the service stopped after a start that failed for a passing
    # reason; at RestartSec=5 the default one is never reached.
    assert not [line for line in lines if line.startswith("StartLimit")]
    assert "RestartSec=5" in lines


def test_caddy_serves_the_app_with_the_spec_headers() -> None:
    text = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    assert text.count("{$SITE_HOST} {") == 1
    assert f'Content-Security-Policy "{SPEC_CSP}"' in text
    for expected in (
        'Strict-Transport-Security "max-age=31536000"',
        'X-Content-Type-Options "nosniff"',
        'Referrer-Policy "no-referrer"',
        "geolocation=(self)",
        "header -Server",
        "encode zstd gzip",
        "max_size 64KB",
        "reverse_proxy 127.0.0.1:8000",
        "root * /opt/assistant/app/webapp/dist",
        "try_files {path} /index.html",
        'Cache-Control "public, max-age=31536000, immutable"',
        'Cache-Control "no-cache"',
    ):
        assert expected in text, expected
    assert "X-Frame-Options" not in text
    # One CSP for the whole site: the API docs, which wanted a CDN script, are not served.
    assert text.count("Content-Security-Policy") == 1
    assert "/api/docs" not in text


def test_caddy_offers_no_http3() -> None:
    text = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    # HTTP/3 runs over UDP, and the firewall lets only TCP through to port 443. Global options
    # are the first block of the file.
    options = re.match(r"(?:#[^\n]*\n|\n)*\{\n(.*?)\n\}\n", text, re.DOTALL)
    assert options is not None
    assert options.group(1).splitlines() == ["\tservers {", "\t\tprotocols h1 h2", "\t}"]


def test_caddy_lets_a_calendar_file_through() -> None:
    text = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    block = re.search(r"\n\thandle /api/schedule/file \{\n(.*?)\n\t\}\n", text, re.DOTALL)
    assert block is not None
    # 3 MB lets the API answer a file over its 2 MB limit with its own error, not Caddy's 413.
    assert block.group(1).splitlines() == [
        "\t\trequest_body {",
        "\t\t\tmax_size 3MB",
        "\t\t}",
        '\t\theader Cache-Control "no-store"',
        "\t\treverse_proxy 127.0.0.1:8000",
    ]
    # `/api/*` would cut a file off at 64KB with Caddy's own 413, so the narrow block stays above
    # it. Caddy also ranks the longer path first by itself; the written order keeps holding if a
    # matcher ever changes to one Caddy does not rank by path.
    general = text.find("\n\thandle /api/* {\n")
    assert general != -1
    assert block.start() < general


def test_caddy_drops_the_server_header_on_errors_too() -> None:
    text = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    # The site-wide `header -Server` is deferred and never applied when a handler errors.
    block = re.search(r"\n\thandle_errors \{\n(.*?)\n\t\}\n", text, re.DOTALL)
    assert block is not None
    assert block.group(1).splitlines() == [
        "\t\theader -Server",
        '\t\trespond "{err.status_code} {err.status_text}"',
    ]
    assert text.index("{$SITE_HOST} {") < block.start() < text.rindex("\n}")


def test_caddy_reads_the_host_from_its_own_environment_file() -> None:
    lines = (DEPLOY / "caddy-assistant.conf").read_text(encoding="utf-8").splitlines()
    assert "EnvironmentFile=/etc/caddy/assistant.env" in lines
    assert "/etc/assistant/assistant.env" not in "\n".join(lines)


def test_caddy_comes_back_after_a_crash() -> None:
    lines = (DEPLOY / "caddy-assistant.conf").read_text(encoding="utf-8").splitlines()
    # The package's unit never restarts Caddy: after a crash the Mini App would stay down.
    service = lines[lines.index("[Service]") :]
    assert "Restart=on-failure" in service and "RestartSec=5" in service


def test_deploy_builds_the_webapp_and_checks_the_api() -> None:
    text = (DEPLOY / "assistant-deploy").read_text(encoding="utf-8")
    for expected in (
        "git worktree add",
        "npm ci",
        "--ignore-scripts",
        "NODE_OPTIONS=--max-old-space-size=512",
        "http://127.0.0.1:8000/api/health",
        "BOT=assistant-bot",
        "API=assistant-api",
        "dist.previous",
    ):
        assert expected in text, expected


def test_deploy_says_which_commit_a_failed_rollback_left() -> None:
    text = (DEPLOY / "assistant-deploy").read_text(encoding="utf-8")
    # The bot comes up even when the API does not, so "the services are down" may be untrue.
    message = "ROLLBACK FAILED: $previous did not come up healthy, manual attention needed"
    assert text.count(f'echo "{message}" >&2') == 2
    assert "ROLLBACK FAILED: the services are down" not in text
    setup = (DEPLOY / "server-setup.md").read_text(encoding="utf-8")
    assert "| `4` | the rollback did not come up healthy — manual attention needed |" in setup


def test_copies_of_the_database_are_for_the_service_only() -> None:
    deploy = (DEPLOY / "assistant-deploy").read_text(encoding="utf-8")
    # The deploy's umask lets Caddy read the web build; a copy of the database gets 0640.
    assert "\numask 0022\n" in deploy
    for copy in (
        """( umask 0027; as_app sqlite3 "$DB" ".backup '$snapshot'" )""",
        '( umask 0027; as_app cp "$snapshot" "$DB.restore" )',
    ):
        assert copy in deploy, copy
    # The nightly copy, also when the script is run by hand.
    backup = (DEPLOY / "assistant-backup").read_text(encoding="utf-8")
    assert "\numask 0027\n" in backup
    assert backup.index("\numask 0027\n") < backup.index(".backup")
    unit = (DEPLOY / "assistant-backup.service").read_text(encoding="utf-8").splitlines()
    assert "UMask=0027" in unit


def test_runbook_checks_what_it_installs_before_it_goes_live() -> None:
    setup = (DEPLOY / "server-setup.md").read_text(encoding="utf-8")
    fstab = (
        "[ ! -f /swapfile ] || grep -q '^/swapfile ' /etc/fstab || "
        "echo '/swapfile none swap sw 0 0' >> /etc/fstab"
    )
    assert fstab in setup
    assert "show assistant-deploy > /usr/local/sbin/assistant-deploy\n" not in setup
    for temporary, check, target in (
        (
            'new="/usr/local/sbin/$script.new"',
            'bash -n "$new"',
            'mv "$new" "/usr/local/sbin/$script"',
        ),
        (
            "> /etc/sudoers.d/assistant-deploy.new",
            "visudo -cf /etc/sudoers.d/assistant-deploy.new",
            "mv /etc/sudoers.d/assistant-deploy.new /etc/sudoers.d/assistant-deploy",
        ),
    ):
        assert setup.index(temporary) < setup.index(check) < setup.index(target), check
    # A hand-run `caddy validate` needs the host name the Caddyfile reads from the environment.
    assert "set -a; . /etc/caddy/assistant.env; set +a" in setup


def runbook_section(heading: str) -> str:
    """The runbook's text under `heading`, up to the next heading of its level or a higher one."""
    setup = (DEPLOY / "server-setup.md").read_text(encoding="utf-8")
    section = setup[setup.index(f"\n{heading}\n") :]
    level = len(heading) - len(heading.lstrip("#"))
    ends = [section.find("\n" + "#" * n + " ", 1) for n in range(2, level + 1)]
    return section[: min((end for end in ends if end != -1), default=len(section))]


def test_restore_migrates_the_copy_before_the_services_start() -> None:
    section = runbook_section("## 8. Restore from a backup")
    remove = section.index(
        "rm -f /var/lib/assistant/assistant.db-wal /var/lib/assistant/assistant.db-shm"
    )
    upgrade = section.index(
        "runuser -u assistant -- bash -c 'set -a; . /etc/assistant/assistant.env; set +a; "
        "exec .venv/bin/alembic upgrade head'"
    )
    start = section.index("systemctl start assistant-api assistant-bot")
    # The services never migrate by themselves: a copy from before the newest migration would
    # start the code on an older schema (notes, checklists and cities fail, reminders work).
    assert remove < upgrade < start
    assert "cd /opt/assistant/app" in section[:upgrade]
    # Every deploy leaves a snapshot, not only a failed one (assistant-deploy, take_snapshot).
    assert "every deploy also leaves a" in section
    assert "a failed deploy also leaves" not in section


def test_restore_keeps_the_database_it_replaces() -> None:
    section = runbook_section("## 8. Restore from a backup")
    stop = section.index("systemctl stop assistant-bot assistant-api\n")
    keep = [
        section.index("keep=/var/backups/assistant/before-restore-$(date -u +%Y%m%dT%H%M%S).db\n"),
        section.index(
            "[ ! -f /var/lib/assistant/assistant.db ] || "
            'cp -p /var/lib/assistant/assistant.db "$keep"\n'
        ),
        section.index(
            "[ ! -f /var/lib/assistant/assistant.db-wal ] || "
            'cp -p /var/lib/assistant/assistant.db-wal "$keep-wal"\n'
        ),
    ]
    install = section.index("install -o assistant -g assistant -m 0640 ")
    # A wrong copy picked in an incident loses nothing: the stopped database, with the -wal a
    # crash may have left, is copied as it is (it may be the broken one, and a failed .backup
    # would end the restore) before anything overwrites it.
    assert stop < keep[0] < keep[1] < keep[2] < install
    # No pruning reaches what is kept: it stays until it is deleted by hand.
    kept = ("before-restore-20261009T120000.db", "before-restore-20261009T120000.db-wal")
    for script in ("assistant-backup", "assistant-deploy"):
        text = (DEPLOY / script).read_text(encoding="utf-8")
        patterns = re.findall(r"-name ['\"]([^'\"]+)['\"]", text)
        assert patterns, script
        for pattern in patterns:
            assert not any(fnmatch.fnmatchcase(name, pattern) for name in kept), pattern


def test_runbook_moves_the_site_to_another_host() -> None:
    section = runbook_section("## 9. Changing the site host")
    for expected in (
        "/etc/caddy/assistant.env",
        "caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile",
        "WEBAPP_URL=https://$SITE_HOST/",
        "systemctl restart assistant-api assistant-bot",
        "DEPLOY_KNOWN_HOSTS",
    ):
        assert expected in section, expected


def test_runbook_takes_the_token_in_an_editor_and_needs_no_retired_bot() -> None:
    setup = (DEPLOY / "server-setup.md").read_text(encoding="utf-8")
    # The v1 bot leaves the server after 2026-10-13: a rebuild takes the token from @BotFather,
    # typed into an editor, never onto a command line.
    assert "/opt/tgbot" not in setup
    assert "echo 'BOT_TOKEN='" in setup
    assert "ssh -t <server> 'sudoedit /etc/assistant/assistant.env'" in setup


def test_the_move_to_2_6_1_installs_the_scripts_before_its_deploy_runs() -> None:
    block = runbook_section("### Going from 2.6.0 to 2.6.1")
    # Every file 2.6.1 changed in deploy/ is installed by hand; the deploy touches none of them.
    # The scripts go first, or the deploy's own snapshot is still written 0644. The copies made
    # before them are fixed once, after everything else is in place.
    scripts = block.index("for script in assistant-deploy assistant-backup; do")
    others = [
        block.index(
            "for unit in assistant-bot.service assistant-api.service assistant-backup.service; do"
        ),
        block.index("show caddy-assistant.conf > "),
        block.index("show Caddyfile > "),
    ]
    chmod = block.index(
        "chmod 0640 /var/lib/assistant/assistant.db* /var/backups/assistant/*.db*\n"
    )
    assert scripts < min(others) and max(others) < chmod
    # The units hand the process the notify socket: the watchdog is on once 2.6.1 runs in them.
    assert "systemctl show -p WatchdogUSec assistant-bot assistant-api" in block


def test_the_move_to_2_6_1_leaves_no_copy_readable_by_others() -> None:
    block = runbook_section("### Going from 2.6.0 to 2.6.1")
    # A copy opened read-only keeps the -wal and -shm SQLite made for it, in the copy's mode, and
    # no pruning removes them: those of a copy whose -wal is empty hold nothing and go, the chmod
    # covers whatever is left, and the check at the end finds nothing.
    sides = block.index(
        "for db in /var/backups/assistant/*.db; do "
        '[ -s "$db-wal" ] || rm -f "$db-wal" "$db-shm"; done\n'
    )
    chmod = block.index(
        "chmod 0640 /var/lib/assistant/assistant.db* /var/backups/assistant/*.db*\n"
    )
    check = block.index("find /var/lib/assistant /var/backups/assistant -name '*.db*' -perm /o=r")
    assert sides < chmod < check


def test_the_runbook_shows_the_backups_own_line() -> None:
    # `journalctl -u` also shows systemd's lines about the run, and they come last («Finished …»,
    # and «Consumed …» after a second of CPU); `_SYSTEMD_UNIT=` shows only what the script wrote.
    own_line = "journalctl _SYSTEMD_UNIT=assistant-backup.service -n 1 -o cat --no-pager"
    setup = (DEPLOY / "server-setup.md").read_text(encoding="utf-8")
    assert "journalctl -u assistant-backup" not in setup
    for heading in ("## 4. Services and backups", "### Going from 2.6.0 to 2.6.1"):
        assert own_line in runbook_section(heading), heading


def test_a_new_caddy_validates_the_caddyfile_before_it_is_installed() -> None:
    section = runbook_section("### Updating Caddy")
    # The package restarts Caddy as it installs, so the new version checks the Caddyfile from a
    # scratch folder first; dpkg keeps the project's Caddyfile, a configuration file of the
    # package, without asking.
    steps = [
        section.index("apt-get download -qq caddy"),
        section.index('dpkg-deb -x "$new"/caddy_*.deb "$new/root"'),
        section.index('"$new/root/usr/bin/caddy" validate --config /etc/caddy/Caddyfile'),
        section.index(
            "apt-get install -y -qq --only-upgrade -o Dpkg::Options::=--force-confold caddy"
        ),
    ]
    assert steps == sorted(steps)


def test_timer_runs_nightly() -> None:
    timer = (DEPLOY / "assistant-backup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 03:30:00 UTC" in timer and "Persistent=true" in timer


@needs_bash
@pytest.mark.parametrize("script", ["assistant-deploy", "assistant-backup"])
def test_scripts_are_valid_bash(script: str) -> None:
    subprocess.run(["bash", "-n", str(DEPLOY / script)], check=True)


@needs_bash
@pytest.mark.parametrize("arg", ["", "main", "deadbeef", "g" * 40, "A" * 40, "0" * 40 + ";true"])
def test_deploy_accepts_only_a_full_commit_sha(arg: str) -> None:
    result = subprocess.run(
        ["bash", str(DEPLOY / "assistant-deploy"), arg], capture_output=True, text=True
    )
    assert result.returncode == 2 and "usage" in result.stderr


@needs_bash
@pytest.mark.parametrize("branch", ["-rf", "a b", "x;y", "$(id)"])
def test_deploy_rejects_strange_branch_names(branch: str) -> None:
    result = subprocess.run(
        ["bash", str(DEPLOY / "assistant-deploy"), "a" * 40],
        capture_output=True,
        text=True,
        env={**os.environ, "DEPLOY_BRANCH": branch},
    )
    assert result.returncode == 2 and "invalid branch name" in result.stderr


def test_no_addresses_or_secrets_in_deploy_files() -> None:
    files = [*DEPLOY.iterdir(), ROOT / ".github" / "workflows" / "deploy.yml"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        # Loopback is fine (the API listens there), and so are the private ranges the units deny
        # (that line is pinned by test_units_are_sandboxed); a real address or host name is not.
        kept = [line for line in text.splitlines() if not line.startswith("IPAddressDeny=")]
        found = [ip for line in kept for ip in IPV4.findall(line)]
        assert not [ip for ip in found if not ip.startswith("127.")], path
        assert not WILDCARD_HOST.search(text), path
        assert "BEGIN " + "OPENSSH PRIVATE KEY" not in text
        assert not re.search(r"\d{6,}:[\w-]{30,}", text)


def test_workflow_deploys_only_green_pushes_to_main() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "workflows: [CI]" in text and "branches: [main]" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.event == 'push'" in text
    assert "cancel-in-progress: false" in text


def test_ci_runs_the_servers_sqlite_and_checks_the_lock() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # The 3.12 leg runs the runner's own Python, as the server does, and checks it has the
    # server's SQLite: a migration 3.45 cannot run fails in CI, not in the deploy.
    assert "UV_NO_MANAGED_PYTHON: ${{ matrix.python == '3.12' }}" in text
    assert "sqlite3.sqlite_version_info[:2] == (3, 45)" in text
    # A uv.lock that pyproject.toml has moved past fails CI; the server installs the lock as it is.
    assert "uv sync --locked" in text and "uv sync --frozen" not in text
    # A hung test stops the run after 15 minutes, not GitHub's 6 hours.
    assert text.count("timeout-minutes: 15") == 2


def test_ci_builds_and_checks_the_demo() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    webapp = text[text.index("\n  webapp:") :]
    # After the build for Telegram: none of the demo's code in it, then the demo is built and
    # checked, so a pull request that breaks the demo or leaks an address into it fails.
    steps = [
        "- run: npm run build\n",
        "run: test -d dist && ! grep -rq __demoHost dist\n",
        "- run: npm run build:demo\n",
        "- run: node scripts/check-demo.mjs dist-demo\n",
    ]
    assert all(step in webapp for step in steps)
    assert [webapp.index(step) for step in steps] == sorted(webapp.index(step) for step in steps)
