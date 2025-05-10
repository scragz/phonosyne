"""
Phonosyne Package Initializer

This module initializes the Phonosyne package and exports key functionalities
such as `run_prompt`. It also configures the system to use OpenRouter
as the LLM provider by importing relevant components from `phonosyne.sdk`.

Key features:
- Marks the 'phonosyne' directory as a Python package.
- Serves as the main entry point for importing package components.
- Re-exports `run_prompt` and other necessary components from `phonosyne.sdk`.
"""

# Import the OrchestratorAgent (if it's used directly or needs to be exported)
from .agents.orchestrator import OrchestratorAgent

# Import key functionalities from the sdk module
from .sdk import OpenRouterModelProvider, run_prompt

__version__ = "0.1.0"

__all__ = [
    "run_prompt",
    "OrchestratorAgent",
    "OpenRouterModelProvider",  # Exporting for potential direct use or testing
    "__version__",
]
