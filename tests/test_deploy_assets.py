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
needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the deploy scripts run on Linux",
)


def test_bot_unit_is_sandboxed() -> None:
    lines = (DEPLOY / "assistant-bot.service").read_text(encoding="utf-8").splitlines()
    for expected in (
        "User=assistant",
        "EnvironmentFile=/etc/assistant/assistant.env",
        "ExecStart=/opt/assistant/app/.venv/bin/python -m assistant.bot",
        "Restart=always",
        "StateDirectory=assistant",
        "ProtectSystem=strict",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
    ):
        assert expected in lines


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
        assert not IPV4.search(text), path
        assert "BEGIN " + "OPENSSH PRIVATE KEY" not in text
        assert not re.search(r"\d{6,}:[\w-]{30,}", text)


def test_workflow_deploys_only_green_pushes_to_main() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "workflows: [CI]" in text and "branches: [main]" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "cancel-in-progress: false" in text
