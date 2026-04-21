"""CLI interface — Rich + Click based command-line interface.

Provides:
- `run` command for single task execution
- `interactive` mode for continuous task input
- `skills` to list recorded skills
- `config` to show current configuration
"""

from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from desktop_agent.config import get_settings
from desktop_agent.log import setup_logging, get_logger

console = Console()
log = get_logger(__name__)


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(debug: bool) -> None:
    """Desktop Agent — autonomous macOS desktop controller."""
    level = "DEBUG" if debug else get_settings().logging.level
    setup_logging(level=level)


@cli.command()
@click.argument("task")
@click.option("--max-steps", default=None, type=int, help="Override max steps")
def run(task: str, max_steps: int | None) -> None:
    """Execute a single task."""
    from desktop_agent.core.agent import Agent

    if max_steps:
        get_settings().agent.max_steps = max_steps

    console.print(Panel(f"[bold cyan]Task:[/] {task}", title="Desktop Agent"))

    agent = Agent()

    def on_step(step: int, result) -> None:
        action = result.action
        act_name = action.action.value if hasattr(action.action, "value") else str(action.action)
        thought = getattr(action, "thought", "")

        status = "[green]✓[/]" if result.verified else "[red]✗[/]"
        console.print(
            f"  {status} Step {step}: [bold]{act_name}[/] "
            f"[dim]{thought[:60]}[/]"
        )

    agent.on_step(on_step)

    try:
        result = asyncio.run(agent.run_task(task))
        console.print(Panel(f"[bold green]Result:[/] {result}", title="Complete"))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")
    finally:
        asyncio.run(agent.stop())


@cli.command()
def interactive() -> None:
    """Start interactive mode — enter tasks continuously."""
    from desktop_agent.core.agent import Agent

    console.print(Panel(
        "[bold cyan]Interactive Mode[/]\n"
        "Type a task and press Enter. Type 'quit' to exit.",
        title="Desktop Agent",
    ))

    agent = Agent()

    def on_step(step: int, result) -> None:
        action = result.action
        act_name = action.action.value if hasattr(action.action, "value") else str(action.action)
        status = "[green]✓[/]" if result.verified else "[red]✗[/]"
        console.print(f"  {status} Step {step}: [bold]{act_name}[/]")

    agent.on_step(on_step)

    try:
        while True:
            task = console.input("\n[bold cyan]Task>[/] ").strip()
            if not task:
                continue
            if task.lower() in ("quit", "exit", "q"):
                break

            try:
                result = asyncio.run(agent.run_task(task))
                console.print(Panel(f"[bold green]{result}[/]", title="Done"))
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        asyncio.run(agent.stop())
        console.print("[dim]Goodbye.[/]")


@cli.command()
def skills() -> None:
    """List all recorded skills."""
    from desktop_agent.memory.skill_store import SkillLibrary

    library = SkillLibrary()
    all_skills = library.list_all()

    if not all_skills:
        console.print("[dim]No skills recorded yet.[/]")
        return

    table = Table(title="Skill Library")
    table.add_column("Name", style="cyan")
    table.add_column("Steps", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Reliability", justify="right")
    table.add_column("Tags")

    for s in all_skills:
        rel_color = "green" if s.reliability >= 0.7 else "yellow" if s.reliability >= 0.4 else "red"
        table.add_row(
            s.name,
            str(len(s.actions)),
            str(s.times_used),
            f"[{rel_color}]{s.reliability:.0%}[/]",
            ", ".join(s.tags),
        )

    console.print(table)


@cli.command()
def config() -> None:
    """Show current configuration."""
    settings = get_settings()
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Planner model", settings.llm.planner_model)
    table.add_row("Executor model", settings.llm.executor_model)
    table.add_row("Max steps", str(settings.agent.max_steps))
    table.add_row("Screenshot format", settings.screen.screenshot_format)
    table.add_row("Accessibility", str(settings.accessibility.enabled))
    table.add_row("OCR", str(settings.ocr.enabled))
    table.add_row("Log level", settings.logging.level)

    console.print(table)


def main() -> None:
    """Entry point."""
    cli()
