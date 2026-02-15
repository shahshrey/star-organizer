from datetime import datetime, timezone
from typing import Any, Dict, List

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from star_organizer.models import OrganizedStarLists

console = Console()


def print_banner():
    title = Text()
    title.append("⭐ ", style="yellow")
    title.append("Star Organizer", style="bold white")
    console.print(
        Panel(
            Align.center(title),
            subtitle="[dim]Organize your GitHub stars with AI[/dim]",
            border_style="blue",
            padding=(1, 2),
            width=min(60, console.width),
        )
    )
    console.print()


def print_phase(phase_num: int, label: str, details: dict):
    detail_parts = [f"[dim]{k}:[/dim] [bold]{v}[/bold]" for k, v in details.items()]
    console.print(f"  [green]✓[/green] [bold]Phase {phase_num}[/bold] — {label}")
    console.print(f"    {' · '.join(detail_parts)}")


def print_error(message: str):
    console.print(f"  [red]✗[/red] {message}")


def print_success(message: str):
    console.print(f"  [green]✓[/green] {message}")


def print_categories_table(organized: OrganizedStarLists):
    if not organized:
        console.print("[yellow]No categories found.[/yellow]")
        return

    table = Table(
        title="Current Categories",
        title_style="bold blue",
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
        expand=False,
        width=min(80, console.width),
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Category", style="bold cyan", max_width=32, no_wrap=True)
    table.add_column("Repos", style="bold yellow", justify="right", width=5)
    table.add_column("Description", style="dim", ratio=1, overflow="ellipsis", no_wrap=True)

    total_repos = 0
    for i, (name, data) in enumerate(sorted(organized.items()), 1):
        repo_count = len(data.get("repos", []))
        total_repos += repo_count
        desc = (data.get("description", "") or "")[:60]
        table.add_row(
            str(i),
            name.replace("_", " ").title(),
            str(repo_count) if repo_count else "[dim]—[/dim]",
            desc,
        )

    console.print()
    console.print(table)
    console.print(
        f"\n  [bold]{len(organized)}[/bold] categories · "
        f"[bold]{total_repos}[/bold] repos total\n"
    )


def _humanize_age(dt_str: str) -> str:
    if not dt_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days < 1:
            return "today"
        if days == 1:
            return "1 day ago"
        if days < 30:
            return f"{days} days ago"
        months = days // 30
        if months < 12:
            return f"{months} month{'s' if months > 1 else ''} ago"
        years = months // 12
        remaining_months = months % 12
        if remaining_months:
            return f"{years}y {remaining_months}mo ago"
        return f"{years} year{'s' if years > 1 else ''} ago"
    except Exception:
        return "unknown"


def _age_style(dt_str: str) -> str:
    if not dt_str:
        return "dim"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        if days > 730:
            return "bold red"
        if days > 365:
            return "red"
        if days > 180:
            return "yellow"
        return "green"
    except Exception:
        return "dim"


def print_stale_header(count: int, total: int, threshold_days: int):
    if threshold_days >= 365:
        years = threshold_days / 365
        threshold_str = f"{years:.0f} year{'s' if years > 1 else ''}" if years == int(years) else f"{years:.1f} years"
    elif threshold_days >= 30:
        months = threshold_days / 30
        threshold_str = f"{months:.0f} month{'s' if months > 1 else ''}" if months == int(months) else f"{months:.1f} months"
    else:
        threshold_str = f"{threshold_days} day{'s' if threshold_days > 1 else ''}"

    console.print()
    console.print(
        Panel(
            Align.center(
                Text.from_markup(
                    f"[bold yellow]Found {count} stale repo{'s' if count != 1 else ''}[/bold yellow]\n\n"
                    f"  [dim]Total stars:[/dim]   [bold]{total}[/bold]\n"
                    f"  [dim]Stale:[/dim]         [bold red]{count}[/bold red]\n"
                    f"  [dim]Active:[/dim]        [bold green]{total - count}[/bold green]\n"
                    f"  [dim]Threshold:[/dim]     [bold]{threshold_str}[/bold]"
                )
            ),
            title="[bold yellow]Stale Stars Report[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
            width=min(55, console.width),
        )
    )


def print_stale_table(stale_repos: List[Dict[str, Any]]):
    if not stale_repos:
        console.print("[green]No stale repos found![/green]")
        return

    table = Table(
        title="Stale Starred Repos",
        title_style="bold yellow",
        border_style="yellow",
        show_lines=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Repository", style="bold cyan", max_width=32, no_wrap=True, overflow="ellipsis")
    table.add_column("Last Push", max_width=14, no_wrap=True)
    table.add_column("Stars", style="yellow", justify="right", width=6)
    table.add_column("Info", ratio=1, overflow="ellipsis", no_wrap=True)

    for i, repo in enumerate(stale_repos, 1):
        pushed = repo.get("pushed_at", "")
        style = _age_style(pushed)
        lang = repo.get("language", "") or ""
        archived = " [red]ARCHIVED[/red]" if repo.get("archived") else ""
        info = f"[dim]{lang}[/dim]{archived}"
        desc = (repo.get("description", "") or "")[:60]
        if desc:
            info += f"  [dim italic]{desc}[/dim italic]"
        table.add_row(
            str(i),
            repo.get("full_name", ""),
            f"[{style}]{_humanize_age(pushed)}[/{style}]",
            str(repo.get("stargazers_count", 0)),
            info,
        )

    console.print()
    console.print(table)
    console.print()


def print_repo_detail(repo: Dict[str, Any], index: int, total: int):
    pushed = repo.get("pushed_at", "")
    style = _age_style(pushed)

    details = Text()
    details.append("  Repository:  ", style="dim")
    details.append(repo.get("full_name", ""), style="bold cyan")
    details.append("\n")

    desc = repo.get("description", "") or "No description"
    details.append("  Description: ", style="dim")
    details.append(desc[:120], style="white")
    details.append("\n")

    details.append("  Language:    ", style="dim")
    details.append(repo.get("language", "") or "—", style="white")
    details.append("    ", style="dim")
    details.append("Stars: ", style="dim")
    details.append(str(repo.get("stargazers_count", 0)), style="yellow")
    details.append("    ", style="dim")
    details.append("Forks: ", style="dim")
    details.append(str(repo.get("forks_count", 0)), style="white")
    details.append("\n")

    details.append("  Last push:   ", style="dim")
    details.append(_humanize_age(pushed), style=style)
    if pushed:
        details.append(f"  ({pushed[:10]})", style="dim")
    details.append("\n")

    details.append("  URL:         ", style="dim")
    details.append(repo.get("html_url", ""), style="blue underline")

    if repo.get("archived"):
        details.append("\n")
        details.append("  Status:      ", style="dim")
        details.append("ARCHIVED", style="bold red")

    topics = repo.get("topics", [])
    if topics:
        details.append("\n")
        details.append("  Topics:      ", style="dim")
        details.append(", ".join(topics[:8]), style="dim italic")

    console.print(
        Panel(
            details,
            title=f"[bold white][{index}/{total}][/bold white]",
            border_style="blue",
            padding=(1, 1),
            width=min(90, console.width),
        )
    )


def print_dead_table(dead_repos: List[Dict[str, Any]], status_map: Dict[str, int], uncertain_count: int = 0):
    if not dead_repos:
        if uncertain_count > 0:
            console.print(
                f"[yellow]No confirmed dead repos. {uncertain_count} checks were inconclusive (auth/rate-limit/network/server).[/yellow]"
            )
        else:
            console.print("[green]No dead repos found — all checked stars are accessible![/green]")
        return

    from star_organizer.dead import dead_status_label

    table = Table(
        title="Dead / Inaccessible Stars",
        title_style="bold red",
        border_style="red",
        show_lines=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Repository", style="bold cyan", max_width=35, no_wrap=True, overflow="ellipsis")
    table.add_column("Status", width=22, no_wrap=True)
    table.add_column("Stars", style="yellow", justify="right", width=6)
    table.add_column("Description", style="dim", ratio=1, overflow="ellipsis", no_wrap=True)

    for i, repo in enumerate(dead_repos, 1):
        full_name = repo.get("full_name", "")
        code = status_map.get(full_name, -1)
        label = dead_status_label(code)
        table.add_row(
            str(i),
            full_name,
            f"[red]{label}[/red]",
            str(repo.get("stargazers_count", 0)),
            (repo.get("description", "") or "")[:60],
        )

    console.print()
    console.print(table)
    if uncertain_count > 0:
        console.print(
            f"[yellow]Skipped {uncertain_count} inconclusive repo checks (auth/rate-limit/network/server errors). Re-run for complete results.[/yellow]"
        )
    console.print()


def print_archived_table(archived_repos: List[Dict[str, Any]]):
    if not archived_repos:
        console.print("[green]No archived repos found![/green]")
        return

    table = Table(
        title="Archived Stars",
        title_style="bold magenta",
        border_style="magenta",
        show_lines=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Repository", style="bold cyan", max_width=35, no_wrap=True, overflow="ellipsis")
    table.add_column("Last Push", max_width=14, no_wrap=True)
    table.add_column("Stars", style="yellow", justify="right", width=6)
    table.add_column("Description", style="dim", ratio=1, overflow="ellipsis", no_wrap=True)

    for i, repo in enumerate(archived_repos, 1):
        pushed = repo.get("pushed_at", "")
        style = _age_style(pushed)
        table.add_row(
            str(i),
            repo.get("full_name", ""),
            f"[{style}]{_humanize_age(pushed)}[/{style}]",
            str(repo.get("stargazers_count", 0)),
            (repo.get("description", "") or "")[:60],
        )

    console.print()
    console.print(table)
    console.print()


def print_cleanup_report(
    total: int,
    stale_names: set,
    dead_names: set,
    archived_names: set,
    uncertain_names: set | None,
    threshold_days: int,
):
    if threshold_days >= 365:
        y = threshold_days / 365
        thr = f"{y:.0f} year{'s' if y > 1 else ''}" if y == int(y) else f"{y:.1f} years"
    elif threshold_days >= 30:
        m = threshold_days / 30
        thr = f"{m:.0f} month{'s' if m > 1 else ''}" if m == int(m) else f"{m:.1f} months"
    else:
        thr = f"{threshold_days} day{'s' if threshold_days != 1 else ''}"

    uncertain_names = uncertain_names or set()
    all_affected = stale_names | dead_names | archived_names
    uncertain_only = uncertain_names - all_affected
    clean = total - len(all_affected) - len(uncertain_only)
    uncertain_line = (
        f"\n  [dim]Uncertain:[/dim]     [bold yellow]{len(uncertain_only)}[/bold yellow]"
        if uncertain_only else ""
    )
    console.print()
    console.print(
        Panel(
            Align.center(
                Text.from_markup(
                    f"[bold cyan]Cleanup Report[/bold cyan]\n\n"
                    f"  [dim]Total stars:[/dim]   [bold]{total}[/bold]\n"
                    f"  [dim]Clean:[/dim]         [bold green]{max(clean, 0)}[/bold green]\n"
                    f"  [dim]Stale ({thr}):[/dim] [bold yellow]{len(stale_names)}[/bold yellow]\n"
                    f"  [dim]Dead/404:[/dim]      [bold red]{len(dead_names)}[/bold red]\n"
                    f"  [dim]Archived:[/dim]      [bold magenta]{len(archived_names)}[/bold magenta]"
                    f"{uncertain_line}"
                )
            ),
            title="[bold cyan]Cleanup Report[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
            width=min(55, console.width),
        )
    )


def print_stale_actions_summary(kept: int, unstarred: int, total: int):
    console.print()
    console.print(
        Panel(
            Align.center(
                Text.from_markup(
                    f"[bold green]Review complete![/bold green]\n\n"
                    f"  [dim]Reviewed:[/dim]  [bold]{total}[/bold]\n"
                    f"  [dim]Kept:[/dim]      [bold green]{kept}[/bold green]\n"
                    f"  [dim]Unstarred:[/dim] [bold red]{unstarred}[/bold red]"
                )
            ),
            title="[bold green]Done[/bold green]",
            border_style="green",
            padding=(1, 2),
            width=min(40, console.width),
        )
    )


def print_summary(organized: OrganizedStarLists):
    total_repos = sum(len(d.get("repos", [])) for d in organized.values())
    non_empty = sum(1 for d in organized.values() if d.get("repos"))

    console.print()
    console.print(
        Panel(
            Align.center(
                Text.from_markup(
                    f"[green bold]Pipeline complete![/green bold]\n\n"
                    f"  [dim]Categories:[/dim]  [bold]{len(organized)}[/bold]\n"
                    f"  [dim]Non-empty:[/dim]   [bold]{non_empty}[/bold]\n"
                    f"  [dim]Total repos:[/dim] [bold]{total_repos}[/bold]"
                )
            ),
            title="[bold green]✓ Done[/bold green]",
            border_style="green",
            padding=(1, 2),
            width=min(50, console.width),
        )
    )
