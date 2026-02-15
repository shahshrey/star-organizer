import logging
import sys
from typing import Optional

import questionary
import structlog
import typer

from star_organizer.awesome import run_awesome_export
from star_organizer.dashboard import print_dashboard
from star_organizer.dead import find_dead_repos, uncertain_repo_names
from star_organizer.display import (
    console,
    print_archived_table,
    print_banner,
    print_categories_table,
    print_cleanup_report,
    print_dead_table,
    print_error,
    print_phase,
    print_stale_table,
    print_success,
    print_summary,
)
from star_organizer.github_client import fetch_starred_repos, unstar_repo
from star_organizer.models import (
    DEFAULT_STALE_THRESHOLD_DAYS,
    GITHUB_TOKEN,
    OUTPUT_FILE,
    STALE_PRESETS,
    SYNC_STATE_FILE,
)
from star_organizer.pipeline import (
    create_backup,
    phase_1_fetch_and_load,
    phase_2_metadata,
    phase_3_categorize,
    phase_4_sync,
    validate_tokens,
)
from star_organizer.prompt_style import MENU_STYLE
from star_organizer.stale import find_stale_repos, parse_threshold, run_stale_check
from star_organizer.store import (
    find_repo_in_organized,
    load_organized_stars,
    load_sync_state,
    remove_repo_from_organized,
    recategorize_repo,
    save_organized_stars,
)


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

ACTIONS = [
    questionary.Choice("Organize my stars (full pipeline)", value="full"),
    questionary.Choice("Organize only (skip GitHub sync)", value="organize"),
    questionary.Choice("Sync only (push existing categories to GitHub)", value="sync"),
    questionary.Separator("─── Analysis ───"),
    questionary.Choice("Find stale stars", value="stale"),
    questionary.Choice("Find dead stars (404/private)", value="dead"),
    questionary.Choice("Find archived stars", value="archived"),
    questionary.Choice("Cleanup report (stale + dead + archived)", value="cleanup"),
    questionary.Choice("Star dashboard", value="dashboard"),
    questionary.Separator("─── Tools ───"),
    questionary.Choice("Re-categorize a repo", value="recategorize"),
    questionary.Choice("Export as awesome-list", value="awesome"),
    questionary.Choice("Preview current categories", value="preview"),
    questionary.Separator("───"),
    questionary.Choice("Reset & re-organize everything", value="reset"),
    questionary.Choice("Exit", value="exit"),
]


def _preview(output_file: str):
    organized = load_organized_stars(output_file)
    if not organized:
        print_error(f"No organized stars found at [bold]{output_file}[/bold]. Run the pipeline first.")
        return
    print_categories_table(organized)


def _parse_threshold_or_exit(raw_value: str) -> int:
    try:
        return parse_threshold(raw_value)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


def _bulk_unstar_and_sync_local(repos: list[dict], output_file: str) -> int:
    organized = load_organized_stars(output_file)
    count = 0
    for repo in repos:
        full_name = repo.get("full_name", "")
        if not isinstance(full_name, str) or "/" not in full_name:
            continue
        owner, name = full_name.split("/", 1)
        if unstar_repo(owner, name):
            count += 1
            remove_repo_from_organized(organized, repo.get("html_url", ""))
    if count > 0:
        save_organized_stars(output_file, organized)
    return count


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


def _run_dead_check(test_limit: int = 0, interactive: bool = True, output_file: str = OUTPUT_FILE):
    with console.status("[bold blue]Fetching starred repos...[/bold blue]"):
        repos = fetch_starred_repos(test_limit)
    if not repos:
        print_error("No repos fetched.")
        return
    with console.status(f"[bold blue]Checking {len(repos)} repos for accessibility...[/bold blue]"):
        dead, status_map = find_dead_repos(repos)
    uncertain = uncertain_repo_names(status_map)
    console.print(
        f"\n  [bold]Checked {len(repos)} repos[/bold] — "
        f"[red]{len(dead)} dead[/red], [yellow]{len(uncertain)} uncertain[/yellow]"
    )
    print_dead_table(dead, status_map, uncertain_count=len(uncertain))
    if dead and interactive:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice("Unstar all dead repos", value="unstar"),
                questionary.Choice("Back", value="back"),
            ],
            style=MENU_STYLE,
        ).ask()
        if action == "unstar":
            confirm = questionary.confirm(
                f"Unstar {len(dead)} dead repos?", default=False, style=MENU_STYLE
            ).ask()
            if confirm:
                count = _bulk_unstar_and_sync_local(dead, output_file)
                print_success(f"Unstarred {count}/{len(dead)} dead repos")


def _run_archived_check(test_limit: int = 0, interactive: bool = True, output_file: str = OUTPUT_FILE):
    with console.status("[bold blue]Fetching starred repos...[/bold blue]"):
        repos = fetch_starred_repos(test_limit)
    if not repos:
        print_error("No repos fetched.")
        return
    archived = [r for r in repos if r.get("archived")]
    console.print(f"\n  [bold]Found {len(archived)} archived repos[/bold] out of {len(repos)} total")
    print_archived_table(archived)
    if archived and interactive:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice("Unstar all archived repos", value="unstar"),
                questionary.Choice("Back", value="back"),
            ],
            style=MENU_STYLE,
        ).ask()
        if action == "unstar":
            confirm = questionary.confirm(
                f"Unstar {len(archived)} archived repos?", default=False, style=MENU_STYLE
            ).ask()
            if confirm:
                count = _bulk_unstar_and_sync_local(archived, output_file)
                print_success(f"Unstarred {count}/{len(archived)} archived repos")


def _run_cleanup(test_limit: int = 0, threshold_days: int = 0, interactive: bool = True):
    if threshold_days <= 0:
        if not interactive:
            threshold_days = DEFAULT_STALE_THRESHOLD_DAYS
        else:
            selected_threshold = questionary.select(
                "Staleness threshold:",
                choices=[
                    questionary.Choice(label, value=days)
                    for label, days in STALE_PRESETS.items()
                ],
                default="1 year",
                style=MENU_STYLE,
            ).ask()
            if selected_threshold is None:
                console.print("[dim]Cancelled.[/dim]")
                return
            threshold_days = selected_threshold

    with console.status("[bold blue]Fetching starred repos...[/bold blue]"):
        repos = fetch_starred_repos(test_limit)
    if not repos:
        print_error("No repos fetched.")
        return

    stale = find_stale_repos(repos, threshold_days)

    with console.status(f"[bold blue]Checking {len(repos)} repos for accessibility...[/bold blue]"):
        dead, status_map = find_dead_repos(repos)
    uncertain_names = uncertain_repo_names(status_map)

    archived = [r for r in repos if r.get("archived")]

    stale_names = {r.get("full_name", "") for r in stale}
    dead_names = {r.get("full_name", "") for r in dead}
    archived_names = {r.get("full_name", "") for r in archived}
    print_cleanup_report(
        len(repos),
        stale_names,
        dead_names,
        archived_names,
        uncertain_names,
        threshold_days,
    )

    if stale:
        print_stale_table(stale)
    if dead or uncertain_names:
        print_dead_table(dead, status_map, uncertain_count=len(uncertain_names))
    if archived:
        print_archived_table(archived)

    if not stale and not dead and not archived and not uncertain_names:
        console.print("\n  [green bold]Your stars are squeaky clean![/green bold]\n")


def _run_dashboard(test_limit: int = 0):
    with console.status("[bold blue]Fetching starred repos...[/bold blue]"):
        repos = fetch_starred_repos(test_limit)
    if not repos:
        print_error("No repos fetched.")
        return
    print_dashboard(repos)


def _run_recategorize(output_file: str):
    organized = load_organized_stars(output_file)
    if not organized:
        print_error(f"No organized data at [bold]{output_file}[/bold]. Run the pipeline first.")
        return

    query = questionary.text(
        "Search for a repo (name or URL fragment):",
        style=MENU_STYLE,
    ).ask()
    if not query:
        return

    results = find_repo_in_organized(organized, query)
    if not results:
        print_error(f"No repos matching '{query}' found.")
        return

    choices = [
        questionary.Choice(
            (
                f"{repo.get('url', '').split('github.com/')[-1]}  [{cat}]"
                if isinstance(repo.get("url", ""), str) and repo.get("url", "")
                else f"[unknown url]  [{cat}]"
            ),
            value=(cat, repo),
        )
        for cat, repo in results
    ]
    choices.append(questionary.Choice("Cancel", value=None))

    selected = questionary.select(
        "Which repo?",
        choices=choices,
        style=MENU_STYLE,
    ).ask()
    if not selected:
        return

    source_cat, repo = selected
    console.print(f"  [dim]Currently in:[/dim] [bold]{source_cat}[/bold]")

    cat_choices = [
        questionary.Choice(name, value=name)
        for name in sorted(organized.keys())
        if name != source_cat
    ]
    cat_choices.append(questionary.Choice("Cancel", value=None))

    target = questionary.select(
        "Move to which category?",
        choices=cat_choices,
        style=MENU_STYLE,
    ).ask()
    if not target:
        return

    if recategorize_repo(organized, repo.get("url", ""), target):
        save_organized_stars(output_file, organized)
        print_success(f"Moved to [bold]{target}[/bold]")
    else:
        print_error("Failed to move repo.")


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

        if action == "stale":
            if not GITHUB_TOKEN:
                print_error("GITHUB_TOKEN is not set")
                console.print()
                continue
            try:
                run_stale_check(output_file=output_file)
            except Exception as e:
                print_error(f"Stale check failed: {e}")
            console.print()
            continue

        if action == "dead":
            if not GITHUB_TOKEN:
                print_error("GITHUB_TOKEN is not set")
                console.print()
                continue
            try:
                _run_dead_check(output_file=output_file)
            except Exception as e:
                print_error(f"Dead check failed: {e}")
            console.print()
            continue

        if action == "archived":
            if not GITHUB_TOKEN:
                print_error("GITHUB_TOKEN is not set")
                console.print()
                continue
            try:
                _run_archived_check(output_file=output_file)
            except Exception as e:
                print_error(f"Archived check failed: {e}")
            console.print()
            continue

        if action == "cleanup":
            if not GITHUB_TOKEN:
                print_error("GITHUB_TOKEN is not set")
                console.print()
                continue
            try:
                _run_cleanup()
            except Exception as e:
                print_error(f"Cleanup failed: {e}")
            console.print()
            continue

        if action == "dashboard":
            if not GITHUB_TOKEN:
                print_error("GITHUB_TOKEN is not set")
                console.print()
                continue
            try:
                _run_dashboard()
            except Exception as e:
                print_error(f"Dashboard failed: {e}")
            console.print()
            continue

        if action == "recategorize":
            try:
                _run_recategorize(output_file)
            except Exception as e:
                print_error(f"Re-categorize failed: {e}")
            console.print()
            continue

        if action == "awesome":
            try:
                run_awesome_export(output_file)
            except Exception as e:
                print_error(f"Awesome export failed: {e}")
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
    find_stale: bool = typer.Option(False, "--find-stale", help="Find stale/unmaintained starred repos"),
    find_dead: bool = typer.Option(False, "--find-dead", help="Find dead/deleted/private starred repos"),
    find_archived: bool = typer.Option(False, "--find-archived", help="Find archived starred repos"),
    cleanup: bool = typer.Option(False, "--cleanup", help="Run stale + dead + archived report"),
    dashboard: bool = typer.Option(False, "--dashboard", help="Show star dashboard with charts"),
    awesome: bool = typer.Option(False, "--awesome", help="Export organized stars as awesome-list markdown"),
    stale_threshold: str = typer.Option("1y", "--stale-threshold", help="Staleness threshold (e.g. 90, 6m, 1y, 2y)"),
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

    if not verbose:
        _quiet_logs()

    if find_stale:
        if not GITHUB_TOKEN:
            print_error("GITHUB_TOKEN is not set")
            raise typer.Exit(1)
        threshold_days = _parse_threshold_or_exit(stale_threshold)
        run_stale_check(
            test_limit=test_limit,
            threshold_days=threshold_days,
            output_file=output_file,
            interactive=interactive is not False,
        )
        return

    if find_dead:
        if not GITHUB_TOKEN:
            print_error("GITHUB_TOKEN is not set")
            raise typer.Exit(1)
        _run_dead_check(test_limit, interactive=interactive is not False, output_file=output_file)
        return

    if find_archived:
        if not GITHUB_TOKEN:
            print_error("GITHUB_TOKEN is not set")
            raise typer.Exit(1)
        _run_archived_check(test_limit, interactive=interactive is not False, output_file=output_file)
        return

    if cleanup:
        if not GITHUB_TOKEN:
            print_error("GITHUB_TOKEN is not set")
            raise typer.Exit(1)
        threshold_days = _parse_threshold_or_exit(stale_threshold)
        _run_cleanup(test_limit, threshold_days, interactive=interactive is not False)
        return

    if dashboard:
        if not GITHUB_TOKEN:
            print_error("GITHUB_TOKEN is not set")
            raise typer.Exit(1)
        _run_dashboard(test_limit)
        return

    if awesome:
        run_awesome_export(output_file)
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
