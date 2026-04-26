from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from core.scanner import ScanFinding


@dataclass(frozen=True)
class PlannedChange:
    what_id: str
    file_path: Path
    line_number: int
    original_path: str
    replacement_path: str
    target_path: Path
    line_text: str


def _normalize_relative_path(path_text: str) -> str:
    normalized = path_text.replace("\\", "/")
    if normalized == ".":
        return "./"
    return normalized


def _path_parts_casefold(path_value: Path) -> list[str]:
    return [part.casefold() for part in path_value.parts]


def _infer_target_path(repo_root: Path, finding: ScanFinding) -> Path | None:
    absolute_path = Path(finding.original_path)
    parts = _path_parts_casefold(absolute_path)
    if ".git" in parts:
        git_index = parts.index(".git")
        suffix = absolute_path.parts[git_index + 1 :]
        return repo_root / ".git" / Path(*suffix)

    if "worktree" in finding.line_text.casefold():
        git_modules_root = repo_root / ".git" / "modules"
        try:
            relative_to_modules = finding.file_path.relative_to(git_modules_root)
        except ValueError:
            return repo_root

        if relative_to_modules.parts and relative_to_modules.name == "config":
            submodule_parts = relative_to_modules.parts[:-1]
            return repo_root.joinpath(*submodule_parts)

    if absolute_path.name.casefold() == repo_root.name.casefold():
        return repo_root

    return None


def plan_changes(repo_root: Path, findings: list[ScanFinding]) -> list[PlannedChange]:
    planned_changes: list[PlannedChange] = []
    seen_keys: set[tuple[Path, int, str]] = set()

    for finding in findings:
        target_path = _infer_target_path(repo_root, finding)
        if target_path is None:
            continue

        replacement_path = _normalize_relative_path(
            os.path.relpath(target_path, start=finding.file_path.parent)
        )
        key = (finding.file_path, finding.line_number, finding.original_path)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        planned_changes.append(
            PlannedChange(
                what_id="FIXER",
                file_path=finding.file_path,
                line_number=finding.line_number,
                original_path=finding.original_path,
                replacement_path=replacement_path,
                target_path=target_path,
                line_text=finding.line_text,
            )
        )

    return planned_changes
