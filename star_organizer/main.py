import logging
import sys
from typing import Optional

import questionary
import structlog
import typer

from star_organizer.display import (
    console,
    print_banner,
    print_categories_table,
    print_error,
    print_phase,
    print_success,
    print_summary,
)
from star_organizer.models import OUTPUT_FILE, SYNC_STATE_FILE
from star_organizer.pipeline import (
    create_backup,
    phase_1_fetch_and_load,
    phase_2_metadata,
    phase_3_categorize,
    phase_4_sync,
    validate_tokens,
)
from star_organizer.store import load_organized_stars, load_sync_state


def _quiet_logs():
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    logging.getLogger().setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.WARNING)

app = typer.Typer(
    name="star-organizer",
    help="Organize your GitHub stars into categorized lists using AI.",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
)

MENU_STYLE = questionary.Style([
    ("qmark", "fg:yellow bold"),
    ("question", "bold"),
    ("answer", "fg:green bold"),
    ("pointer", "fg:yellow bold"),
    ("highlighted", "fg:yellow bold"),
    ("selected", "fg:green"),
])

ACTIONS = [
    questionary.Choice("Organize my stars (full pipeline)", value="full"),
    questionary.Choice("Organize only (skip GitHub sync)", value="organize"),
    questionary.Choice("Sync only (push existing categories to GitHub)", value="sync"),
    questionary.Choice("Reset & re-organize everything", value="reset"),
    questionary.Choice("Preview current categories", value="preview"),
    questionary.Choice("Exit", value="exit"),
]


def _preview(output_file: str):
    organized = load_organized_stars(output_file)
    if not organized:
        print_error(f"No organized stars found at [bold]{output_file}[/bold]. Run the pipeline first.")
        return
    print_categories_table(organized)


def _run(
    reset: bool = False,
    backup: bool = False,
    organize_only: bool = False,
    sync_only: bool = False,
    test_limit: int = 0,
    output_file: str = OUTPUT_FILE,
    state_file: str = SYNC_STATE_FILE,
    quiet: bool = True,
):
    if quiet:
        _quiet_logs()

    ok, err = validate_tokens(sync_only=sync_only)
    if not ok:
        print_error(err)
        raise typer.Exit(1)

    console.print()

    if reset and backup:
        try:
            path = create_backup(output_file)
        except Exception as e:
            print_error(f"Backup failed: {e} — aborting reset.")
            raise typer.Exit(1) from e
        if path:
            print_success(f"Backup created: [dim]{path}[/dim]")

    if sync_only:
        organized = load_organized_stars(output_file)
        if not organized:
            print_error(f"No organized data at [bold]{output_file}[/bold]")
            raise typer.Exit(1)
        already_synced = set() if reset else load_sync_state(state_file)
        with console.status("[bold blue]Syncing to GitHub...[/bold blue]"):
            total, success, skipped_cats = phase_4_sync(organized, already_synced, reset, state_file)
        print_phase(4, "GitHub Sync", {"synced": success, "total": total})
        if skipped_cats:
            print_error(f"{skipped_cats} categor{'y' if skipped_cats == 1 else 'ies'} skipped (missing list IDs)")
        print_summary(organized)
        return

    with console.status("[bold blue]Phase 1 — Fetching starred repos...[/bold blue]"):
        repos, organized, already_synced = phase_1_fetch_and_load(
            reset, state_file, output_file, test_limit
        )

    if not repos:
        print_error("No repos fetched. Check your GITHUB_TOKEN.")
        raise typer.Exit(1)

    print_phase(1, "Fetch & Load", {
        "starred": len(repos),
        "categories": len(organized),
        "synced": len(already_synced),
    })

    with console.status("[bold blue]Phase 2 — Extracting metadata...[/bold blue]"):
        all_metadata, new_metadata = phase_2_metadata(repos, organized, reset)

    print_phase(2, "Metadata", {
        "total": len(all_metadata),
        "new": len(new_metadata),
    })

    with console.status(
        f"[bold blue]Phase 3 — Categorizing {len(new_metadata)} repos with AI...[/bold blue]"
    ):
        organized = phase_3_categorize(
            all_metadata, new_metadata, organized, reset, output_file
        )

    print_phase(3, "Categorize", {"categories": len(organized)})

    if organize_only:
        print_summary(organized)
        return

    with console.status("[bold blue]Phase 4 — Syncing to GitHub...[/bold blue]"):
        total, success, skipped_cats = phase_4_sync(organized, already_synced, reset, state_file)

    print_phase(4, "GitHub Sync", {"synced": success, "total": total})
    if skipped_cats:
        print_error(f"{skipped_cats} categor{'y' if skipped_cats == 1 else 'ies'} skipped (missing list IDs)")
    print_summary(organized)


def _interactive(output_file: str, state_file: str):
    print_banner()

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=ACTIONS,
            style=MENU_STYLE,
        ).ask()

        if not action or action == "exit":
            console.print("[dim]Goodbye![/dim]")
            return

        if action == "preview":
            _preview(output_file)
            console.print()
            continue

        reset = action == "reset"
        organize_only = action == "organize"
        sync_only = action == "sync"
        backup = False

        if reset:
            confirm = questionary.confirm(
                "This will DELETE all existing GitHub lists and re-categorize. Continue?",
                default=False,
                style=MENU_STYLE,
            ).ask()
            if not confirm:
                console.print("[dim]Cancelled.[/dim]")
                console.print()
                continue
            backup = questionary.confirm(
                "Create a backup first?",
                default=True,
                style=MENU_STYLE,
            ).ask()
            if backup is None:
                console.print("[dim]Cancelled.[/dim]")
                console.print()
                continue

        test_limit = 0
        if not sync_only:
            limit_str = questionary.text(
                "Limit repos? (number, or 0 for all)",
                default="0",
                validate=lambda x: True if x.isdigit() else "Enter a number",
                style=MENU_STYLE,
            ).ask()
            if limit_str is None:
                console.print("[dim]Cancelled.[/dim]")
                console.print()
                continue
            test_limit = int(limit_str) if limit_str.isdigit() else 0

        try:
            _run(
                reset=reset,
                backup=backup,
                organize_only=organize_only,
                sync_only=sync_only,
                test_limit=test_limit,
                output_file=output_file,
                state_file=state_file,
            )
        except SystemExit as se:
            if se.code not in (None, 0):
                raise
        except Exception as e:
            print_error(f"Unexpected error: {e}")
        console.print()


@app.command()
def cli(
    reset: bool = typer.Option(False, "--reset", help="Full reset: delete lists, re-categorize, re-sync"),
    backup: bool = typer.Option(False, "--backup", help="Backup organized_stars.json before reset"),
    organize_only: bool = typer.Option(False, "--organize-only", help="Only organize, skip GitHub sync"),
    sync_only: bool = typer.Option(False, "--sync-only", help="Only sync existing organized_stars.json"),
    test_limit: int = typer.Option(0, "--test-limit", help="Limit starred repos fetched (for testing)"),
    output_file: str = typer.Option(OUTPUT_FILE, "--output-file", help="Path to organized_stars.json"),
    state_file: str = typer.Option(SYNC_STATE_FILE, "--state-file", help="Path to sync state file"),
    interactive: Optional[bool] = typer.Option(
        None, "--interactive/--no-interactive", "-i",
        help="Force interactive/non-interactive mode",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed log output"),
):
    no_args = len(sys.argv) <= 1
    if interactive is True or (interactive is None and no_args):
        _interactive(output_file, state_file)
        return

    _run(
        reset=reset,
        backup=backup,
        organize_only=organize_only,
        sync_only=sync_only,
        test_limit=test_limit,
        output_file=output_file,
        state_file=state_file,
        quiet=not verbose,
    )


def main():
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
