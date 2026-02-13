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
