from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from star_organizer.display import _humanize_age, console

BAR_CHAR = "\u2588"
BAR_WIDTH = 30


def _bar(value: int, max_value: int, width: int = BAR_WIDTH) -> str:
    if max_value <= 0:
        return ""
    filled = max(1, round(value / max_value * width)) if value > 0 else 0
    return BAR_CHAR * filled


def _parse_date(dt_str: str) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _language_breakdown(repos: List[Dict[str, Any]]):
    counts: Counter = Counter()
    for r in repos:
        lang = r.get("language") or "Unknown"
        counts[lang] += 1

    top = counts.most_common(15)
    if not top:
        return

    table = Table(
        title="Language Breakdown",
        title_style="bold blue",
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
        expand=False,
        width=min(70, console.width),
    )
    table.add_column("Language", style="bold cyan", width=14, no_wrap=True)
    table.add_column("Count", style="yellow", justify="right", width=5)
    table.add_column("Bar", ratio=1, no_wrap=True)

    max_count = top[0][1] if top else 1
    for lang, count in top:
        pct = count / len(repos) * 100
        bar = _bar(count, max_count)
        table.add_row(lang, str(count), f"[blue]{bar}[/blue] [dim]{pct:.0f}%[/dim]")

    others = len(repos) - sum(c for _, c in top)
    if others > 0:
        table.add_row("[dim]Other[/dim]", f"[dim]{others}[/dim]", "")

    console.print()
    console.print(table)


def _star_distribution(repos: List[Dict[str, Any]]):
    buckets = [
        ("0-10", 0, 10),
        ("11-50", 11, 50),
        ("51-100", 51, 100),
        ("101-500", 101, 500),
        ("501-1K", 501, 1000),
        ("1K-5K", 1001, 5000),
        ("5K-10K", 5001, 10000),
        ("10K-50K", 10001, 50000),
        ("50K+", 50001, float("inf")),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    for r in repos:
        stars = r.get("stargazers_count", 0)
        for label, lo, hi in buckets:
            if lo <= stars <= hi:
                counts[label] += 1
                break

    table = Table(
        title="Star Count Distribution",
        title_style="bold blue",
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
        expand=False,
        width=min(70, console.width),
    )
    table.add_column("Range", style="bold", width=10, no_wrap=True)
    table.add_column("Repos", style="yellow", justify="right", width=5)
    table.add_column("Bar", ratio=1, no_wrap=True)

    max_count = max(counts.values()) if counts else 1
    for label, _, _ in buckets:
        c = counts[label]
        if c == 0:
            continue
        bar = _bar(c, max_count)
        table.add_row(label, str(c), f"[yellow]{bar}[/yellow]")

    console.print()
    console.print(table)


def _age_histogram(repos: List[Dict[str, Any]]):
    now = datetime.now(timezone.utc)
    buckets = [
        ("<1 mo", 0, 30),
        ("1-3 mo", 31, 90),
        ("3-6 mo", 91, 180),
        ("6-12 mo", 181, 365),
        ("1-2 yr", 366, 730),
        ("2-5 yr", 731, 1825),
        ("5+ yr", 1826, 999999),
    ]
    counts = {label: 0 for label, _, _ in buckets}
    unknown_count = 0
    for r in repos:
        dt = _parse_date(r.get("pushed_at", ""))
        if not dt:
            unknown_count += 1
            continue
        age_days = (now - dt).days
        for label, lo, hi in buckets:
            if lo <= age_days <= hi:
                counts[label] += 1
                break

    table = Table(
        title="Repo Age (by last push)",
        title_style="bold blue",
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
        expand=False,
        width=min(70, console.width),
    )
    table.add_column("Age", style="bold", width=8, no_wrap=True)
    table.add_column("Repos", style="yellow", justify="right", width=5)
    table.add_column("Bar", ratio=1, no_wrap=True)

    all_values = list(counts.values()) + [unknown_count]
    max_count = max(all_values) if all_values else 1
    colors = ["green", "green", "yellow", "yellow", "red", "red", "bold red"]
    for (label, _, _), color in zip(buckets, colors):
        c = counts[label]
        if c == 0:
            continue
        bar = _bar(c, max_count)
        table.add_row(label, str(c), f"[{color}]{bar}[/{color}]")

    if unknown_count > 0:
        bar = _bar(unknown_count, max_count)
        table.add_row("[dim]Unknown[/dim]", str(unknown_count), f"[dim]{bar}[/dim]")

    console.print()
    console.print(table)


def _starred_timeline(repos: List[Dict[str, Any]]):
    monthly: Counter = Counter()
    for r in repos:
        dt = _parse_date(r.get("created_at", ""))
        if not dt:
            continue
        key = dt.strftime("%Y-%m")
        monthly[key] += 1

    if not monthly:
        return

    sorted_months = sorted(monthly.keys())
    recent = sorted_months[-12:] if len(sorted_months) > 12 else sorted_months

    table = Table(
        title="Stars Timeline (last 12 months by repo creation)",
        title_style="bold blue",
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
        expand=False,
        width=min(70, console.width),
    )
    table.add_column("Month", style="bold", width=8, no_wrap=True)
    table.add_column("Repos", style="yellow", justify="right", width=5)
    table.add_column("Bar", ratio=1, no_wrap=True)

    max_count = max(monthly[m] for m in recent) if recent else 1
    for month in recent:
        c = monthly[month]
        bar = _bar(c, max_count)
        table.add_row(month, str(c), f"[magenta]{bar}[/magenta]")

    console.print()
    console.print(table)


def print_dashboard(repos: List[Dict[str, Any]]):
    total = len(repos)
    archived = sum(1 for r in repos if r.get("archived"))
    languages = len({r.get("language") for r in repos if r.get("language")})
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)

    oldest = min((r for r in repos if r.get("pushed_at")), key=lambda r: r["pushed_at"], default=None)
    newest = max((r for r in repos if r.get("pushed_at")), key=lambda r: r["pushed_at"], default=None)

    header = (
        f"[bold cyan]Star Dashboard[/bold cyan]\n\n"
        f"  [dim]Starred repos:[/dim]  [bold]{total}[/bold]\n"
        f"  [dim]Languages:[/dim]      [bold]{languages}[/bold]\n"
        f"  [dim]Total stargazers:[/dim] [bold]{total_stars:,}[/bold]\n"
        f"  [dim]Archived:[/dim]       [bold red]{archived}[/bold red]\n"
    )
    if oldest:
        header += f"  [dim]Oldest push:[/dim]   [bold]{_humanize_age(oldest['pushed_at'])}[/bold]\n"
    if newest:
        header += f"  [dim]Newest push:[/dim]   [bold]{_humanize_age(newest['pushed_at'])}[/bold]"

    console.print()
    console.print(
        Panel(
            Align.center(Text.from_markup(header)),
            border_style="blue",
            padding=(1, 2),
            width=min(55, console.width),
        )
    )

    _language_breakdown(repos)
    _star_distribution(repos)
    _age_histogram(repos)
    _starred_timeline(repos)
    console.print()
