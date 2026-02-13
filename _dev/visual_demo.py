import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.rule import Rule

from star_organizer.display import (
    print_banner,
    print_categories_table,
    print_error,
    print_phase,
    print_success,
    print_summary,
)

console = Console()

MOCK_DATA = {
    "AI_AGENTS_FRAMEWORKS": {
        "description": "Frameworks and libraries for building autonomous AI agents",
        "repos": [
            {"url": "https://github.com/langchain-ai/langchain", "description": "Build context-aware reasoning applications"},
            {"url": "https://github.com/microsoft/autogen", "description": "Framework for building multi-agent AI systems"},
            {"url": "https://github.com/crewAI/crewAI", "description": "Orchestrate role-playing AI agents"},
        ],
    },
    "AI_CODING_ASSISTANTS_TOOLS": {
        "description": "AI-powered tools for code generation and assistance",
        "repos": [
            {"url": "https://github.com/getcursor/cursor", "description": "AI-first code editor"},
            {"url": "https://github.com/Aider-AI/aider", "description": "AI pair programming in terminal"},
        ],
    },
    "PYTHON_FRAMEWORKS": {
        "description": "Python web frameworks and server-side libraries",
        "repos": [
            {"url": "https://github.com/fastapi/fastapi", "description": "Modern, fast web framework for Python"},
            {"url": "https://github.com/django/django", "description": "The web framework for perfectionists"},
            {"url": "https://github.com/pallets/flask", "description": "Lightweight WSGI web application framework"},
            {"url": "https://github.com/encode/starlette", "description": "The little ASGI framework that shines"},
        ],
    },
    "REACT_COMPONENTS": {
        "description": "Reusable React UI components and component libraries",
        "repos": [
            {"url": "https://github.com/shadcn-ui/ui", "description": "Beautifully designed components with Radix and Tailwind"},
        ],
    },
    "DEVELOPER_TOOLS": {
        "description": "General-purpose tools for software development",
        "repos": [
            {"url": "https://github.com/jesseduffield/lazygit", "description": "Simple terminal UI for git commands"},
            {"url": "https://github.com/BurntSushi/ripgrep", "description": "Recursively search directories for a regex pattern"},
        ],
    },
    "DEVOPS_INFRASTRUCTURE": {
        "description": "DevOps, CI/CD, and infrastructure automation tools",
        "repos": [],
    },
    "SECURITY_TOOLS": {
        "description": "Security scanning, auditing, and vulnerability tools",
        "repos": [
            {"url": "https://github.com/trufflesecurity/trufflehog", "description": "Find leaked credentials"},
        ],
    },
    "LEARNING_RESOURCES": {
        "description": "Tutorials, courses, guides, and educational materials",
        "repos": [],
    },
}


def section(title):
    console.print()
    console.print(Rule(f" {title} ", style="yellow"))
    console.print()
    time.sleep(0.3)


section("1. WELCOME BANNER")
print_banner()
time.sleep(0.5)

section("2. INTERACTIVE MENU (questionary select)")
console.print("  [yellow]?[/yellow] [bold]What would you like to do?[/bold]")
console.print("  [yellow]❯[/yellow] [yellow bold]Organize my stars (full pipeline)[/yellow bold]")
console.print("    Organize only (skip GitHub sync)")
console.print("    Sync only (push existing categories to GitHub)")
console.print("    Reset & re-organize everything")
console.print("    Preview current categories")
console.print("    Exit")
time.sleep(0.5)

section("3. RESET CONFIRMATION (questionary confirm)")
console.print("  [yellow]?[/yellow] [bold]This will DELETE all existing GitHub lists and re-categorize. Continue?[/bold] [dim](y/N)[/dim]")
console.print("  [yellow]?[/yellow] [bold]Create a backup first?[/bold] [dim](Y/n)[/dim]")
console.print("  [yellow]?[/yellow] [bold]Limit repos? (number, or 0 for all)[/bold] [green]5[/green]")
time.sleep(0.5)

section("4. PIPELINE PROGRESS")
print_success("Backup created: [dim]organized_stars.json.backup.1739512345[/dim]")
console.print()

with console.status("[bold blue]Phase 1 — Fetching starred repos...[/bold blue]"):
    time.sleep(1.5)
print_phase(1, "Fetch & Load", {"starred": 156, "categories": 32, "synced": 89})

with console.status("[bold blue]Phase 2 — Extracting metadata...[/bold blue]"):
    time.sleep(1.5)
print_phase(2, "Metadata", {"total": 156, "new": 12})

with console.status("[bold blue]Phase 3 — Categorizing 12 repos with AI...[/bold blue]"):
    time.sleep(2)
print_phase(3, "Categorize", {"categories": 32})

with console.status("[bold blue]Phase 4 — Syncing to GitHub...[/bold blue]"):
    time.sleep(1.5)
print_phase(4, "GitHub Sync", {"synced": 12, "total": 12})
time.sleep(0.5)

section("5. CATEGORIES TABLE (preview)")
print_categories_table(MOCK_DATA)
time.sleep(0.5)

section("6. SUMMARY PANEL")
print_summary(MOCK_DATA)
time.sleep(0.5)

section("7. ERROR STATES")
print_error("GITHUB_TOKEN is not set")
print_error("No organized data at [bold]organized_stars.json[/bold]")
print_error("No repos fetched. Check your GITHUB_TOKEN.")
time.sleep(0.3)

section("8. SUCCESS MESSAGES")
print_success("Pipeline complete!")
print_success("Backup created: [dim]organized_stars.json.backup.1739512345[/dim]")
console.print()
console.print("[dim]Goodbye![/dim]")

console.print()
console.print(Rule(" VISUAL DEMO COMPLETE ", style="green"))
console.print()
