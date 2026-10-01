from __future__ import annotations

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
        "ProtectSystem=strict",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
        "IPAddressDeny=169.254.0.0/16 fe80::/10 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 "
        "100.64.0.0/10 fc00::/7",
    ):
        assert expected in lines
    assert not [line for line in lines if line.startswith("IPAddressAllow")]


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
