import json
import webbrowser
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import questionary
import structlog

from star_organizer.display import (
    console,
    print_error,
    print_repo_detail,
    print_stale_actions_summary,
    print_stale_header,
    print_stale_table,
    print_success,
)
from star_organizer.github_client import fetch_starred_repos, unstar_repo
from star_organizer.models import (
    DEFAULT_STALE_THRESHOLD_DAYS,
    OUTPUT_FILE,
    STALE_EXPORT_FILE,
    STALE_PRESETS,
)
from star_organizer.store import load_organized_stars, remove_repo_from_organized, save_organized_stars

LOGGER = structlog.get_logger()

MENU_STYLE = questionary.Style([
    ("qmark", "fg:yellow bold"),
    ("question", "bold"),
    ("answer", "fg:green bold"),
    ("pointer", "fg:yellow bold"),
    ("highlighted", "fg:yellow bold"),
    ("selected", "fg:green"),
])


def parse_threshold(value: str) -> int:
    v = value.strip().lower()
    for label, days in STALE_PRESETS.items():
        if v == label:
            return days

    try:
        if v.endswith("d"):
            return int(v[:-1])
        if v.endswith("m"):
            return int(v[:-1]) * 30
        if v.endswith("y"):
            return int(v[:-1]) * 365
        return int(v)
    except (ValueError, IndexError):
        raise ValueError(f"Invalid threshold: '{value}'. Use a number, or append d/m/y (e.g. 90, 6m, 2y)")


def find_stale_repos(repos: List[Dict[str, Any]], threshold_days: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - (threshold_days * 86400)
    stale = []

    for repo in repos:
        pushed_at = repo.get("pushed_at", "")
        if not pushed_at:
            stale.append(repo)
            continue

        try:
            pushed_ts = datetime.fromisoformat(pushed_at.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            stale.append(repo)
            continue

        if pushed_ts < cutoff:
            stale.append(repo)

    stale.sort(key=lambda r: r.get("pushed_at", "") or "")
    return stale


def _ask_threshold() -> int:
    choices = [
        questionary.Choice(label, value=days)
        for label, days in STALE_PRESETS.items()
    ]
    choices.append(questionary.Choice("Custom (enter days)", value=-1))

    result = questionary.select(
        "How long without a push makes a repo stale?",
        choices=choices,
        style=MENU_STYLE,
    ).ask()

    if result is None:
        return 0
    if result == -1:
        custom = questionary.text(
            "Enter threshold (e.g. 90 for days, 6m for months, 2y for years):",
            validate=lambda x: True if _validate_threshold(x) else "Use a number, or append d/m/y (e.g. 90, 6m, 2y)",
            style=MENU_STYLE,
        ).ask()
        if not custom:
            return 0
        return parse_threshold(custom)
    return result


def _validate_threshold(value: str) -> bool:
    v = value.strip().lower()
    if not v:
        return False
    try:
        if v[-1] in ("d", "m", "y"):
            return int(v[:-1]) > 0
        return int(v) > 0
    except ValueError:
        return False


def _export_stale(stale_repos: List[Dict[str, Any]], output_path: str = STALE_EXPORT_FILE):
    export = []
    for repo in stale_repos:
        export.append({
            "full_name": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "description": repo.get("description", ""),
            "language": repo.get("language", ""),
            "stars": repo.get("stargazers_count", 0),
            "last_pushed": repo.get("pushed_at", ""),
            "archived": repo.get("archived", False),
        })

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"stale_repos": export, "count": len(export)}, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print_error(f"Failed to write stale export to [bold]{output_path}[/bold]: {e}")
        return
    print_success(f"Exported {len(export)} stale repos to [bold]{output_path}[/bold]")


def _unstar_single(repo: Dict[str, Any]) -> bool:
    full_name = repo.get("full_name", "")
    if not full_name or "/" not in full_name:
        return False
    owner, name = full_name.split("/", 1)
    return unstar_repo(owner, name)


def _review_one_by_one(
    stale_repos: List[Dict[str, Any]],
    output_file: str = OUTPUT_FILE,
) -> Tuple[int, int]:
    kept = 0
    unstarred = 0
    total = len(stale_repos)
    organized = load_organized_stars(output_file)

    review_actions = [
        questionary.Choice("Keep — I still want this starred", value="keep"),
        questionary.Choice("Unstar — remove the star", value="unstar"),
        questionary.Choice("Open in browser — then decide", value="open"),
        questionary.Choice("Skip remaining — stop review", value="stop"),
    ]

    for i, repo in enumerate(stale_repos, 1):
        print_repo_detail(repo, i, total)

        action = questionary.select(
            "What do you want to do with this repo?",
            choices=review_actions,
            style=MENU_STYLE,
        ).ask()

        if not action or action == "stop":
            remaining = total - i + 1
            if remaining > 0:
                console.print(f"[dim]Skipped remaining {remaining} repos.[/dim]")
            break

        if action == "open":
            url = repo.get("html_url", "")
            if url:
                webbrowser.open(url)
            reask = questionary.select(
                "Now what?",
                choices=[
                    questionary.Choice("Keep", value="keep"),
                    questionary.Choice("Unstar", value="unstar"),
                ],
                style=MENU_STYLE,
            ).ask()
            action = reask or "keep"

        if action == "unstar":
            success = _unstar_single(repo)
            if success:
                unstarred += 1
                remove_repo_from_organized(organized, repo.get("html_url", ""))
                console.print(f"  [red]✗ Unstarred[/red] {repo.get('full_name', '')}")
            else:
                kept += 1
                print_error(f"Failed to unstar {repo.get('full_name', '')} — kept")
        else:
            kept += 1
            console.print(f"  [green]✓ Kept[/green] {repo.get('full_name', '')}")

        console.print()

    if unstarred > 0 and organized is not None:
        save_organized_stars(output_file, organized)

    return kept, unstarred


def _bulk_unstar(
    stale_repos: List[Dict[str, Any]],
    output_file: str = OUTPUT_FILE,
) -> Tuple[int, int]:
    confirm = questionary.confirm(
        f"Unstar ALL {len(stale_repos)} stale repos? This cannot be undone.",
        default=False,
        style=MENU_STYLE,
    ).ask()

    if not confirm:
        console.print("[dim]Cancelled.[/dim]")
        return 0, 0

    organized = load_organized_stars(output_file)
    unstarred = 0
    failed = 0

    with console.status(f"[bold red]Unstarring {len(stale_repos)} repos...[/bold red]"):
        for repo in stale_repos:
            if _unstar_single(repo):
                unstarred += 1
                remove_repo_from_organized(organized, repo.get("html_url", ""))
            else:
                failed += 1

    if unstarred > 0 and organized is not None:
        save_organized_stars(output_file, organized)

    print_success(f"Unstarred {unstarred} repos" + (f" ({failed} failed)" if failed else ""))
    return failed, unstarred


def run_stale_check(
    test_limit: int = 0,
    threshold_days: int = 0,
    output_file: str = OUTPUT_FILE,
    interactive: bool = True,
):
    if interactive and threshold_days <= 0:
        threshold_days = _ask_threshold()
        if threshold_days <= 0:
            console.print("[dim]Cancelled.[/dim]")
            return

    if threshold_days <= 0:
        threshold_days = DEFAULT_STALE_THRESHOLD_DAYS

    with console.status("[bold blue]Fetching starred repos...[/bold blue]"):
        repos = fetch_starred_repos(test_limit)

    if not repos:
        print_error("No repos fetched. Check your GITHUB_TOKEN.")
        return

    stale = find_stale_repos(repos, threshold_days)
    print_stale_header(len(stale), len(repos), threshold_days)

    if not stale:
        console.print("\n  [green bold]All your stars are actively maintained![/green bold]\n")
        return

    print_stale_table(stale)

    if not interactive:
        return

    action_choices = [
        questionary.Choice("Review repos one by one", value="review"),
        questionary.Choice("Unstar all stale repos", value="bulk_unstar"),
        questionary.Choice("Export stale list to JSON", value="export"),
        questionary.Choice("Back to menu", value="back"),
    ]

    action = questionary.select(
        "What would you like to do?",
        choices=action_choices,
        style=MENU_STYLE,
    ).ask()

    if not action or action == "back":
        return

    if action == "review":
        kept, unstarred = _review_one_by_one(stale, output_file)
        print_stale_actions_summary(kept, unstarred, kept + unstarred)
    elif action == "bulk_unstar":
        failed, unstarred = _bulk_unstar(stale, output_file)
        if unstarred or failed:
            print_stale_actions_summary(0, unstarred, unstarred + failed)
    elif action == "export":
        _export_stale(stale)
