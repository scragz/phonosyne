"""
Command-Line Interface for Phonosyne

This module provides the CLI for the Phonosyne application using Typer.
It allows users to run the sound generation pipeline from the command line.

Key features:
- `run` command to initiate the sound generation process.
- Arguments for user prompt, number of workers, and verbosity.
- Calls the main SDK function `phonosyne.run_prompt`.
- Provides user-friendly output and error handling.

@dependencies
- `typer` for creating the CLI application.
- `typing.Optional` for type hinting optional arguments.
- `phonosyne.run_prompt` (the main SDK entry point).
- `phonosyne.settings` (for default values, though Typer can have its own defaults).
- `logging` for configuring log levels based on verbosity.
- `rich.console` for potentially richer terminal output (optional).

@notes
- This CLI will be registered as an entry point in `pyproject.toml` (Step 6.1).
- Error messages from the pipeline should be caught and presented clearly to the user.
"""

import logging
from pathlib import Path  # Moved import to top
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from phonosyne import __version__  # To display version
from phonosyne import run_prompt as sdk_run_prompt  # Alias to avoid conflict
from phonosyne import settings

# Initialize Typer app
app = typer.Typer(
    name="phonosyne",
    help="Phonosyne: Multi-Agent Sound-Library Generator.",
    add_completion=False,
)

console = Console()
error_console = Console(stderr=True, style="bold red")


def version_callback(value: bool):
    if value:
        console.print(f"Phonosyne CLI Version: {__version__}", style="bold green")
        raise typer.Exit()


@app.command(help="Run the Phonosyne sound generation pipeline with a user brief.")
def run(
    prompt: str = typer.Argument(
        ..., help="The user's natural-language sound design brief."
    ),
    workers: Optional[int] = typer.Option(
        None,  # Default will be handled by Manager using settings.DEFAULT_WORKERS
        "--workers",
        "-w",
        help="Number of parallel workers. 0 for serial. Defaults to system/settings config.",
        min=0,  # Allow 0 for serial
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging output.", is_flag=True
    ),
    output_dir: Optional[
        Path
    ] = typer.Option(  # typer.Path doesn't exist, use pathlib.Path
        None,  # Default will be handled by Manager using settings.DEFAULT_OUT_DIR
        "--output-dir",
        "-o",
        help="Custom base output directory. Defaults to './output'.",
        # Note: Typer needs `path_type=Path` if it supported it directly.
        # For now, we'll take string and convert, or let Manager handle Path conversion.
        # The Manager already uses settings.DEFAULT_OUT_DIR.
        # This CLI option would override it if Manager is adapted or if we set settings here.
        # For now, this option is illustrative; Manager's current output path is not easily changed post-init.
    ),
):
    """
    Runs the Phonosyne sound generation pipeline.
    """
    # Configure logging based on verbosity
    log_level = logging.DEBUG if verbose else logging.INFO
    # A more robust logging setup might involve a shared logger configuration module.
    # For now, basic configuration:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress overly verbose logs from dependencies if needed
    # logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("openai").setLevel(logging.WARNING)

    if verbose:
        console.print(f"Verbose mode enabled. Log level set to DEBUG.", style="dim")

    console.print(
        Panel(Text(f"Phonosyne v{__version__}", justify="center", style="bold green"))
    )
    console.print(f'🚀 Starting generation for prompt: "{prompt}"', style="cyan")
    if workers is not None:
        console.print(
            f"🛠️  Using {workers if workers > 0 else 'serial'} worker(s).", style="dim"
        )
    if output_dir:
        # This is tricky as Manager's output_base_dir is set at init from settings.
        # To make this work, we'd need to either:
        # 1. Modify settings.DEFAULT_OUT_DIR before Manager init (global state change, not ideal)
        # 2. Pass output_dir to Manager and have it use it. (Manager needs update)
        # For now, this option is noted but not fully plumbed through Manager.
        console.print(
            f"📂 Custom output directory specified: {output_dir} (Note: Manager needs to support this)",
            style="yellow",
        )

    try:
        # Call the SDK function
        result = sdk_run_prompt(
            prompt=prompt,
            num_workers=workers,  # Manager handles None by using default
            verbose=verbose,
        )

        console.print("\n🎉 Generation Pipeline Complete!", style="bold green")

        summary_table = Table(title="Generation Summary")
        summary_table.add_column("Metric", style="dim")
        summary_table.add_column("Value")

        summary_table.add_row(
            "Status",
            Text(
                str(result.get("status")),
                style=(
                    "bold green"
                    if result.get("status") == "success"
                    else (
                        "bold yellow"
                        if result.get("status") == "partial_success"
                        else "bold red"
                    )
                ),
            ),
        )
        summary_table.add_row("Total Samples Planned", str(result.get("total_planned")))
        summary_table.add_row(
            "Samples Successfully Rendered", str(result.get("rendered"))
        )
        summary_table.add_row("Output Directory", str(result.get("output_dir")))

        console.print(summary_table)

        if result.get("status") != "success":
            error_console.print(
                f"Some samples may have failed. Check logs and manifest.json in the output directory for details."
            )
            raise typer.Exit(code=1)

    except Exception as e:
        error_console.print(f"\n💥 An error occurred during the Phonosyne pipeline:")
        error_console.print(str(e))
        if verbose:
            # In verbose mode, the full traceback would have been logged by the logger.
            # For non-verbose, we might want to print it here.
            # import traceback
            # error_console.print(traceback.format_exc())
            pass
        raise typer.Exit(code=1)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show CLI version and exit.",
    )
):
    """
    Phonosyne CLI main callback.
    """
    pass  # version_callback handles --version


if __name__ == "__main__":
    # This allows running the CLI directly using `python phonosyne/cli.py run ...`
    # For production, it's better to install the package and use the entry point.
    app()

# Need to import Path for Typer Option type hint if used, but Typer doesn't directly support it.
# For now, output_dir is illustrative.
# from pathlib import Path # Commented out / removed from bottom
