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
    ):
        assert expected in lines


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


def test_caddy_reads_the_host_from_its_own_environment_file() -> None:
    lines = (DEPLOY / "caddy-assistant.conf").read_text(encoding="utf-8").splitlines()
    assert "EnvironmentFile=/etc/caddy/assistant.env" in lines
    assert "/etc/assistant/assistant.env" not in "\n".join(lines)


def test_deploy_builds_the_webapp_and_checks_the_api() -> None:
    text = (DEPLOY / "assistant-deploy").read_text(encoding="utf-8")
    for expected in (
        "git worktree add",
        "npm ci",
        "NODE_OPTIONS=--max-old-space-size=512",
        "http://127.0.0.1:8000/api/health",
        "BOT=assistant-bot",
        "API=assistant-api",
        "dist.previous",
    ):
        assert expected in text, expected


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
        # Loopback is fine (the API listens there); a real address or host name is not.
        assert not [ip for ip in IPV4.findall(text) if not ip.startswith("127.")], path
        assert not WILDCARD_HOST.search(text), path
        assert "BEGIN " + "OPENSSH PRIVATE KEY" not in text
        assert not re.search(r"\d{6,}:[\w-]{30,}", text)


def test_workflow_deploys_only_green_pushes_to_main() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "workflows: [CI]" in text and "branches: [main]" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.event == 'push'" in text
    assert "cancel-in-progress: false" in text
