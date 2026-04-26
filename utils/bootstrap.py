from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True)
class DependencyStatus:
    installed_now: bool
    message: str


def _is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def ensure_dependencies(requirements_path: Path) -> DependencyStatus:
    if _is_module_available("flet"):
        return DependencyStatus(installed_now=False, message="Dependencies already installed.")

    if not requirements_path.is_file():
        raise FileNotFoundError(f"Missing dependency manifest: {requirements_path}")

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        error_output = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            "Automatic dependency installation failed.\n"
            f"Command: {' '.join(command)}\n"
            f"Details: {error_output}"
        )

    if not _is_module_available("flet"):
        raise RuntimeError(
            "Dependency installation reported success, but the `flet` module is still unavailable."
        )

    return DependencyStatus(installed_now=True, message="Dependencies were downloaded automatically.")
