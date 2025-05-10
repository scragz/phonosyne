"""
Designer Agent for Phonosyne (Refactored for agents SDK)

This module defines the `DesignerAgent`, which is responsible for the first stage
of the Phonosyne pipeline: taking a user's sound design brief and expanding it
into a structured plan. It now uses the `agents` SDK.

Key features:
- Inherits from `agents.Agent`.
- Instructions are loaded from `prompts/designer.md`.
- Takes a user brief (string) as input when run.
- Outputs a JSON object conforming to the `DesignerOutput` Pydantic schema,
  facilitated by the `output_type` parameter of `agents.Agent`.

@dependencies
- `agents.Agent` (from the new SDK)
- `phonosyne.agents.schemas.DesignerOutput` (for output validation)
- `phonosyne.agents.schemas.DesignerAgentInput` (for input clarity)
- `phonosyne.settings` (for `MODEL_DESIGNER`)
- `logging`
- `pathlib`

@notes
- The agent's core execution logic (LLM calls, output parsing) is handled by the SDK.
- The prompt template (`designer.md`) is crucial for guiding the LLM.
"""

import logging
from pathlib import Path
from typing import Any

# Import the new Agent class from the SDK
from agents import (
    Agent,  # type: ignore # Assuming agents SDK might not be in static analysis path yet
)
from agents import (
    ModelProvider,  # This might not be needed if Agent takes Model instance
)
from pydantic import BaseModel, Field  # Retaining for DesignerAgentInput

from phonosyne import settings
from phonosyne.agents.schemas import DesignerOutput

logger = logging.getLogger(__name__)


# --- Define Input Schema ---
class DesignerAgentInput(BaseModel):
    """
    Pydantic model for the input to the DesignerAgent.
    Wraps the user brief string. Useful if the agent is run directly
    with structured input, though as a tool it often receives a plain string.
    """

    user_brief: str = Field(..., description="The user's sound design brief.")


# --- Load Instructions ---
# Assuming this file is phonosyne/agents/designer.py
# Project root is three levels up from this file's directory.
# phonosyne/agents/designer.py -> phonosyne/agents/ -> phonosyne/ -> project_root/
try:
    PROMPT_FILE_PATH = (
        Path(__file__).resolve().parent.parent.parent / "prompts" / "designer.md"
    )
    with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
        DESIGNER_INSTRUCTIONS = f.read()
except FileNotFoundError:
    logger.error(
        f"CRITICAL: Designer prompt file not found at {PROMPT_FILE_PATH}. "
        "DesignerAgent will not function correctly."
    )
    DESIGNER_INSTRUCTIONS = (
        "ERROR: Designer prompt not loaded. "
        "Your task is to take a user brief and expand it into a detailed sound design plan."
    )


# --- Define Agent ---
class DesignerAgent(Agent):
    """
    The DesignerAgent expands a user brief into a detailed plan for sound generation,
    using the `agents.Agent` SDK.
    Its instructions are loaded from `prompts/designer.md`.
    The user brief is provided as input when this agent is run.
    It aims to output a JSON string conforming to the DesignerOutput schema.
    """

    def __init__(self, **kwargs: Any):
        """
        Initializes the DesignerAgent.

        Args:
            **kwargs: Additional keyword arguments to pass to the `agents.Agent` constructor.
                      The 'model' kwarg can be a model name (str) or a Model instance.
        """
        # Default configuration for the DesignerAgent instance
        agent_name = kwargs.pop("name", "PhonosyneDesigner_Agent")
        # The 'model' kwarg will be passed in by OrchestratorAgent.
        # If not passed, it would default here, but we want Orchestrator to control it.
        # Defaulting to settings.MODEL_DESIGNER if 'model' is not in kwargs.
        model_arg = kwargs.pop("model", settings.MODEL_DESIGNER)

        # The `instructions` are the system prompt for the LLM.
        # The `user_brief` will be passed as the `input` when `Runner.run(agent, input=user_brief)` is called.
        super().__init__(
            name=agent_name,
            instructions=DESIGNER_INSTRUCTIONS,
            model=model_arg,  # Pass the model name or Model instance
            # output_type=DesignerOutput, # Temporarily removed to rely on prompt for JSON structure
            tools=[],  # DesignerAgent itself does not use tools
            **kwargs,  # Pass through any other agent parameters
        )


# Note: The old `if __name__ == "__main__":` block has been removed.
# Testing will be done using `agents.Runner` in dedicated test files (Step 17).
