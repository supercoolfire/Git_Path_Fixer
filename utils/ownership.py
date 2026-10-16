from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class OwnershipResult:
    already_trusted: bool
    success: bool
    message: str


def check_ownership_error(repo_root: Path) -> bool:
    """Return True if git reports a dubious-ownership error for this repo."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # git not on PATH — cannot check, treat as no error
        return False

    output = completed.stderr or completed.stdout
    return "dubious ownership" in output.lower()


def fix_ownership(repo_root: Path) -> OwnershipResult:
    """
    Add repo_root to git's global safe.directory list.

    This is the scoped fix: it trusts only this one directory, leaving
    git's ownership checks intact everywhere else.
    """
    if not check_ownership_error(repo_root):
        return OwnershipResult(
            already_trusted=True,
            success=True,
            message="Repository is already trusted by git — no change needed.",
        )

    safe_path = str(repo_root).replace("\\", "/")
    try:
        completed = subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", safe_path],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return OwnershipResult(
            already_trusted=False,
            success=False,
            message="git executable not found on PATH. Install git and try again.",
        )

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return OwnershipResult(
            already_trusted=False,
            success=False,
            message=f"git config failed: {detail}",
        )

    # Confirm the error is gone
    if check_ownership_error(repo_root):
        return OwnershipResult(
            already_trusted=False,
            success=False,
            message="safe.directory was written but git still reports dubious ownership.",
        )

    return OwnershipResult(
        already_trusted=False,
        success=True,
        message=f"Trusted: added '{safe_path}' to git global safe.directory.",
    )
