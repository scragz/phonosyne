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

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from phonosyne import __version__
from phonosyne import run_prompt as sdk_run_prompt
from phonosyne import settings
from phonosyne.dsp.master import apply_mastering
from phonosyne.sdk import OpenRouterCreditsError, PhonosyneError

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
def run(  # Changed to synchronous def
    prompt: str = typer.Argument(
        ..., help="The user's natural-language sound design brief."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging output.", is_flag=True
    ),
    # output_dir option removed as it's not directly used by the new run_prompt
    # and OrchestratorAgent handles its own output directory logic based on instructions.
    # workers option removed as num_workers is no longer a parameter to run_prompt.
):
    """
    Runs the Phonosyne sound generation pipeline.
    """
    # Configure logging based on verbosity
    log_level = logging.DEBUG if verbose else logging.INFO
    # A more robust logging setup might involve a shared logger configuration module.
    # For now, basic configuration:
    # logging.basicConfig(
    #     level=log_level,
    #     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    #     datefmt="%Y-%m-%d %H:%M:%S",
    # )
    # Get the root logger
    root_logger = logging.getLogger()  # Get the root logger
    root_logger.setLevel(log_level)  # Set level for your app

    # Remove any existing handlers to avoid duplicate messages or conflicts
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a new stream handler for your application
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Suppress overly verbose logs from common HTTP libraries
    # These should be set AFTER your root logger and its handlers are configured.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    # Specifically target the logger used by openai's base client for HTTP details
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)

    if verbose:
        console.print(f"Verbose mode enabled. Log level set to DEBUG.", style="dim")
        root_logger.debug("Root logger reconfigured for DEBUG level by CLI.")
    else:
        # Optionally, confirm INFO level if not verbose, or remove this else block
        root_logger.info("Root logger reconfigured for INFO level by CLI.")

    console.print(
        Panel(Text(f"Phonosyne v{__version__}", justify="center", style="bold green"))
    )
    console.print(f'🚀 Starting generation for prompt: "{prompt}"', style="cyan")
    # Removed messages for workers and output_dir as these options are removed.

    try:
        # Call the async SDK function using asyncio.run() from the synchronous command
        # The verbose flag is used for local logging setup.
        # It's also passed as a kwarg to sdk_run_prompt, which passes it to OrchestratorAgent.
        result = asyncio.run(sdk_run_prompt(prompt=prompt))

        console.print("\n🎉 Generation Pipeline Complete!", style="bold green")

        summary_table = Table(title="Generation Summary")
        summary_table.add_column("Metric", style="dim")
        summary_table.add_column("Value")

        # The result from the new run_prompt is expected to be a string summary.
        # We need to adapt how results are displayed.
        # For now, just print the string result.
        # A more structured result from OrchestratorAgent (e.g. a JSON string or Pydantic model)
        # would allow for a richer summary table like before.
        # Assuming result is the final string output from OrchestratorAgent.
        console.print(Panel(Text(str(result), style="bold green"), title="Run Result"))

        # A simple check: if the result string contains "error" or "fail", exit with code 1.
        # This is a basic way to indicate issues until a more structured result is implemented.
        if "error" in str(result).lower() or "fail" in str(result).lower():
            error_console.print(
                f"The generation process reported issues. Please check the output message and logs for details."
            )
            raise typer.Exit(code=1)

    except OpenRouterCreditsError as e:
        error_console.print(f"\n💥 OpenRouter Credits Exhausted:", style="bold red")
        error_console.print(str(e))
        error_console.print(
            "Please add more credits to your OpenRouter account and try again."
        )
        raise typer.Exit(code=1)
    except PhonosyneError as e:
        error_console.print(f"\n💥 Phonosyne Error:", style="bold red")
        error_console.print(str(e))
        raise typer.Exit(code=1)
    except Exception as e:
        error_console.print(
            f"\n💥 An critical error occurred in the CLI or Phonosyne pipeline:"
        )
        error_console.print(str(e))  # Ensure e is converted to string
        if verbose:
            # In verbose mode, the full traceback would have been logged by the logger.
            # For non-verbose, we might want to print it here.
            import traceback

            error_console.print(traceback.format_exc())
        raise typer.Exit(code=1)


@app.command(help="Run the mastering effect.")
def master(
    input_file: Path = typer.Argument(
        ..., help="Path to the input audio file to be mastered."
    ),
    output_file: Path = typer.Argument(
        ..., help="Path to save the mastered audio file."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging output.", is_flag=True
    ),
):
    """
    Run the mastering effect on an audio file.
    """
    apply_mastering(input_file, output_file)


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
    # Typer handles running async command functions correctly.
    app()
