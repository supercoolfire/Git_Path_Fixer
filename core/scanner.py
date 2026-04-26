from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


WINDOWS_ABSOLUTE_RE = r"[A-Za-z]:[\\/][^\s\"']+"
UNC_ABSOLUTE_RE = r"\\\\[^\s\\]+\\[^\s\"']+"
POSIX_ABSOLUTE_RE = r"(?<![A-Za-z]:)(?<!\.)/[^\s\"']+"
ABSOLUTE_PATH_RE = re.compile(
    rf"(?P<path>{WINDOWS_ABSOLUTE_RE}|{UNC_ABSOLUTE_RE}|{POSIX_ABSOLUTE_RE})"
)


@dataclass(frozen=True)
class ScanFinding:
    what_id: str
    file_path: Path
    line_number: int
    original_path: str
    line_text: str


SCAN_TARGETS = (
    Path("config"),
    Path("hooks"),
    Path("modules"),
)


def iter_scan_targets(git_dir: Path) -> Iterable[Path]:
    for relative_target in SCAN_TARGETS:
        target = git_dir / relative_target
        if target.is_file():
            yield target
            continue
        if target.is_dir():
            for file_path in target.rglob("*"):
                if file_path.is_file():
                    yield file_path


def is_probably_text(file_path: Path) -> bool:
    try:
        raw = file_path.read_bytes()
    except OSError:
        return False
    return b"\x00" not in raw


def scan_repository(repo_root: Path) -> list[ScanFinding]:
    git_dir = repo_root / ".git"
    if not git_dir.is_dir():
        raise FileNotFoundError(f"No .git directory found under {repo_root}")

    findings: list[ScanFinding] = []
    for file_path in iter_scan_targets(git_dir):
        if not is_probably_text(file_path):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in ABSOLUTE_PATH_RE.finditer(line):
                findings.append(
                    ScanFinding(
                        what_id="SCANNER",
                        file_path=file_path,
                        line_number=line_number,
                        original_path=match.group("path"),
                        line_text=line.strip(),
                    )
                )
    return findings
