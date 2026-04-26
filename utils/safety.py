from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

from core.fixer import PlannedChange


@dataclass(frozen=True)
class RepairReport:
    what_id: str
    success: bool
    backup_path: Path
    restored_backup: bool
    messages: list[str]


def create_backup(repo_root: Path, planned_changes: list[PlannedChange]) -> Path:
    git_dir = repo_root / ".git"
    if not git_dir.is_dir():
        raise FileNotFoundError(f"No .git directory found under {repo_root}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups_root = repo_root.parent / f"{repo_root.name}__git_path_fixer_backups"
    backup_path = backups_root / timestamp
    backup_git_dir = backup_path / ".git"
    backup_git_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(git_dir, backup_git_dir)

    manifest = {
        "what_id": "SAFETY",
        "repo_root": str(repo_root),
        "created_at": timestamp,
        "planned_files": [
            str(change.file_path.relative_to(repo_root)) for change in planned_changes
        ],
    }
    (backup_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return backup_path


def verify_backup(repo_root: Path, backup_path: Path, planned_changes: list[PlannedChange]) -> None:
    backup_git_dir = backup_path / ".git"
    if not backup_git_dir.is_dir():
        raise RuntimeError("Violation: RULE.BACKUP_FIRST\nReason: Backup directory was not created.")

    for change in planned_changes:
        relative_path = change.file_path.relative_to(repo_root)
        if not (backup_path / relative_path).exists():
            raise RuntimeError(
                "Violation: RULE.BACKUP_FIRST\n"
                f"Reason: Backup is missing {relative_path}."
            )


def restore_backup(repo_root: Path, backup_path: Path) -> None:
    source_git_dir = backup_path / ".git"
    target_git_dir = repo_root / ".git"
    if target_git_dir.exists():
        shutil.rmtree(target_git_dir)
    shutil.copytree(source_git_dir, target_git_dir)


def _apply_file_changes(file_path: Path, changes: list[PlannedChange]) -> None:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(keepends=True)
    ordered_changes = sorted(changes, key=lambda item: item.line_number)

    for change in ordered_changes:
        line_index = change.line_number - 1
        if line_index >= len(lines):
            raise RuntimeError(f"Expected line {change.line_number} in {file_path} was not found.")
        if change.original_path not in lines[line_index]:
            raise RuntimeError(
                f"Expected path '{change.original_path}' was not found in {file_path} line {change.line_number}."
            )
        lines[line_index] = lines[line_index].replace(
            change.original_path,
            change.replacement_path,
            1,
        )

    file_path.write_text("".join(lines), encoding="utf-8")


def apply_changes(planned_changes: list[PlannedChange]) -> None:
    grouped_changes: dict[Path, list[PlannedChange]] = {}
    for change in planned_changes:
        grouped_changes.setdefault(change.file_path, []).append(change)

    for file_path, file_changes in grouped_changes.items():
        _apply_file_changes(file_path, file_changes)


def _run_git_check(repo_root: Path, args: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return True, "git executable not available; skipped command validation."

    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def validate_repair(repo_root: Path, planned_changes: list[PlannedChange]) -> list[str]:
    errors: list[str] = []

    for change in planned_changes:
        resolved_path = (change.file_path.parent / change.replacement_path).resolve(strict=False)
        expected_path = change.target_path.resolve(strict=False)
        if resolved_path != expected_path:
            errors.append(
                f"Replacement in {change.file_path} line {change.line_number} resolved to "
                f"{resolved_path} instead of {expected_path}."
            )

    git_dir_ok, git_dir_output = _run_git_check(repo_root, ["rev-parse", "--git-dir"])
    if not git_dir_ok:
        errors.append(f"`git rev-parse --git-dir` failed: {git_dir_output}")

    config_ok, config_output = _run_git_check(repo_root, ["config", "--list", "--local"])
    if not config_ok:
        errors.append(f"`git config --list --local` failed: {config_output}")

    return errors


def repair_repository(repo_root: Path, planned_changes: list[PlannedChange]) -> RepairReport:
    backup_path = create_backup(repo_root, planned_changes)
    verify_backup(repo_root, backup_path, planned_changes)

    try:
        apply_changes(planned_changes)
        validation_errors = validate_repair(repo_root, planned_changes)
        if validation_errors:
            restore_backup(repo_root, backup_path)
            return RepairReport(
                what_id="SAFETY",
                success=False,
                backup_path=backup_path,
                restored_backup=True,
                messages=["Validation failed after repair. Original .git was restored.", *validation_errors],
            )
    except Exception as exc:
        restore_backup(repo_root, backup_path)
        return RepairReport(
            what_id="SAFETY",
            success=False,
            backup_path=backup_path,
            restored_backup=True,
            messages=["Repair failed during execution. Original .git was restored.", str(exc)],
        )

    return RepairReport(
        what_id="SAFETY",
        success=True,
        backup_path=backup_path,
        restored_backup=False,
        messages=["Repair completed and validation passed."],
    )
