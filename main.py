from __future__ import annotations

from pathlib import Path

from core.fixer import PlannedChange, plan_changes
from core.scanner import scan_repository
from utils.bootstrap import ensure_dependencies
from utils.ownership import fix_ownership
from utils.safety import repair_repository

BOOTSTRAP_STATUS = ensure_dependencies(Path(__file__).with_name("requirements.txt"))

import flet as ft


def before_main(page: ft.Page) -> None:
    page.window.icon = "app_icon.ico"


def main(page: ft.Page) -> None:
    page.title = "Git Path Fixer"
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 700
    page.window.height = 500
    page.window.min_width = 700
    page.window.min_height = 500

    selected_repo_root: Path | None = None
    findings_count = 0
    planned_changes: list[PlannedChange] = []

    status_text = ft.Text(
        BOOTSTRAP_STATUS.message + " Choose a repository root, run a dry scan, then approve the repair.",
        selectable=True,
    )
    status_container = ft.Container(
        content=status_text,
        padding=12,
        border=ft.border.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
        bgcolor="#F3F4F6",
    )
    repo_field = ft.TextField(label="Repository Root", read_only=True, expand=True)
    approval_checkbox = ft.Checkbox(
        label="I reviewed the dry run and approve writing changes to .git metadata.",
        value=False,
    )
    results_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

    def render_results() -> None:
        results_column.controls.clear()
        if not planned_changes:
            results_column.controls.append(
                ft.Container(
                    content=ft.Text("No planned changes yet."),
                    padding=12,
                    border=ft.border.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=8,
                )
            )
            page.update()
            return

        for change in planned_changes:
            results_column.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"{change.file_path} : line {change.line_number}",
                                weight=ft.FontWeight.W_600,
                                selectable=True,
                            ),
                            ft.Text(f"Old: {change.original_path}", selectable=True),
                            ft.Text(f"New: {change.replacement_path}", selectable=True),
                            ft.Text(change.line_text, italic=True, selectable=True),
                        ],
                        spacing=4,
                    ),
                    padding=12,
                    border=ft.border.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                    border_radius=8,
                )
            )
        page.update()

    def sync_actions() -> None:
        dry_run_button.disabled = selected_repo_root is None
        fix_ownership_button.disabled = selected_repo_root is None
        repair_button.disabled = not (
            selected_repo_root is not None
            and planned_changes
            and approval_checkbox.value
        )

    def set_status(message: str, bgcolor: str = "#F3F4F6") -> None:
        status_text.value = message
        status_container.bgcolor = bgcolor
        sync_actions()
        page.update()

    def handle_repo_selected(selected_path: str | None) -> None:
        nonlocal selected_repo_root, planned_changes, findings_count
        if not selected_path:
            return
        selected_repo_root = Path(selected_path)
        repo_field.value = str(selected_repo_root)
        findings_count = 0
        planned_changes = []
        approval_checkbox.value = False
        render_results()
        set_status("Repository selected. Run Dry Run to preview repairable paths.")

    def run_dry_run(_: ft.ControlEvent) -> None:
        nonlocal findings_count, planned_changes
        if selected_repo_root is None:
            set_status("Pick a repository before scanning.")
            return

        try:
            findings = scan_repository(selected_repo_root)
            findings_count = len(findings)
            planned_changes = plan_changes(selected_repo_root, findings)
            approval_checkbox.value = False
            render_results()
            if planned_changes:
                set_status(
                    f"Dry run found {findings_count} absolute paths and planned "
                    f"{len(planned_changes)} repair(s). Review them and approve to enable Repair."
                )
            else:
                set_status(
                    f"Dry run found {findings_count} absolute paths, but none were safe to rewrite automatically."
                )
        except Exception as exc:
            planned_changes = []
            render_results()
            set_status(str(exc))

    def run_repair(_: ft.ControlEvent) -> None:
        if selected_repo_root is None:
            set_status("Pick a repository before repairing.")
            return
        if not planned_changes:
            set_status("Run Dry Run first so there is a repair plan to apply.")
            return
        if not approval_checkbox.value:
            set_status("Repair stays disabled until you approve the dry run.")
            return

        report = repair_repository(selected_repo_root, planned_changes)
        approval_checkbox.value = False
        render_results()
        summary = " ".join(report.messages)
        if report.success:
            set_status(
                f"{summary} Backup: {report.backup_path}",
                "#DCFCE7",
            )
        else:
            set_status(
                f"{summary} Backup: {report.backup_path}",
                "#FEE2E2",
            )

    def run_fix_ownership(_: ft.ControlEvent) -> None:
        if selected_repo_root is None:
            set_status("Pick a repository before fixing ownership.")
            return
        result = fix_ownership(selected_repo_root)
        if result.success:
            set_status(result.message, "#DCFCE7")
        else:
            set_status(result.message, "#FEE2E2")

    async def browse_repo(_: ft.ControlEvent) -> None:
        selected_path = await file_picker.get_directory_path(
            dialog_title="Select repository root"
        )
        handle_repo_selected(selected_path)

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    browse_button = ft.Button(
        "Browse",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=browse_repo,
    )
    dry_run_button = ft.Button("Dry Run", icon=ft.Icons.SEARCH, on_click=run_dry_run)
    fix_ownership_button = ft.Button(
        "Fix Git Ownership",
        icon=ft.Icons.LOCK_OPEN,
        on_click=run_fix_ownership,
        tooltip="Adds this repo to git's global safe.directory so git commands work after migration.",
    )
    repair_button = ft.FilledButton("Repair", icon=ft.Icons.BUILD, on_click=run_repair)

    approval_checkbox.on_change = lambda _: sync_actions() or page.update()
    sync_actions()

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Image(
                            src="app_icon.png",
                            width=64,
                            height=64,
                            fit=ft.BoxFit.CONTAIN,
                            border_radius=16,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Git Path Fixer", size=28, weight=ft.FontWeight.BOLD),
                                ft.Text(
                                    "Scans .git metadata for absolute paths, previews rewrites, and applies repairs with backup and rollback.",
                                    selectable=True,
                                ),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=[repo_field, browse_button],
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Row(
                    controls=[dry_run_button, repair_button, fix_ownership_button, approval_checkbox],
                    wrap=True,
                ),
                status_container,
                ft.Container(
                    content=results_column,
                    expand=True,
                    height=500,
                    padding=4,
                ),
            ],
            expand=True,
            spacing=16,
        )
    )


if __name__ == "__main__":
    ft.run(
        main,
        before_main=before_main,
        assets_dir=str(Path(__file__).parent / "assets"),
    )
