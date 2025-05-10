"""
Phonosyne Package Initializer

This module initializes the Phonosyne package and will export key functionalities
such as `run_prompt`.

Key features:
- Marks the 'phonosyne' directory as a Python package.
- Will serve as the main entry point for importing package components.

@dependencies
- None directly at this stage, but will depend on other modules within the package.

@notes
- The `run_prompt` function will be implemented and imported here in a later step (Step 5.2).
"""

import asyncio  # Required for running async code from sync CLI if needed, or for general async ops
from typing import Any, Dict, Optional

from agents import (
    Runner,  # type: ignore # Assuming agents SDK might not be in static analysis path yet
)

# Import the new OrchestratorAgent and the agents SDK Runner
from .orchestrator import OrchestratorAgent


async def run_prompt(
    prompt: str,
    # num_workers and verbose are not directly used by OrchestratorAgent or Runner in this setup.
    # Concurrency and verbosity might be configured differently with the agents SDK,
    # e.g., via Runner run_config or agent's internal logging.
    # For now, these parameters are removed from run_prompt signature for simplicity,
    # unless specific SDK mechanisms for them are identified.
    **kwargs: Any,  # To catch any other potential future args
) -> Any:  # Return type depends on Runner.run and OrchestratorAgent's output_type (str)
    """
    Main SDK entry point to run the Phonosyne generation pipeline using OrchestratorAgent.

    Args:
        prompt: The user's natural-language sound design brief.
        **kwargs: Additional keyword arguments for future flexibility.

    Returns:
        The result from agents.Runner.run(), which is the OrchestratorAgent's final output.
    """
    orchestrator_agent = OrchestratorAgent(
        **kwargs
    )  # Pass kwargs if OrchestratorAgent accepts them

    # The agents.Runner.run() is an async function.
    # The input to the orchestrator is the user's prompt.
    result = await Runner.run(agent=orchestrator_agent, input=prompt)

    # The result.final_output will contain what the OrchestratorAgent ultimately returns.
    # Based on OrchestratorAgent's output_type=str, this should be a string.
    return result.final_output


__version__ = "0.1.0"

__all__ = [
    "run_prompt",
    "OrchestratorAgent",  # Exporting the agent itself might be useful
    "__version__",
]
