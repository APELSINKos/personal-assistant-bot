"""GET /api/health — liveness, version and the deployed commit (no authorization)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from assistant import __version__
from assistant.api.deps import State
from assistant.api.schemas import Health

router = APIRouter(tags=["health"])


def read_commit(root: Path) -> str | None:
    """The checked-out commit of the repository at `root`, read from .git without running git."""
    git = root / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref: "):
        return head or None
    ref = head.removeprefix("ref: ")
    try:
        return (git / ref).read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    try:
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            sha, _, name = line.partition(" ")
            if name == ref:
                return sha
    except OSError:
        return None
    return None


@router.get("/health", response_model=Health)
async def health(state: State) -> Health:
    return Health(status="ok", version=__version__, commit=state.commit)
