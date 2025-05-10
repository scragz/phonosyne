"""
Analyzer Agent for Phonosyne (Refactored for agents SDK)

This module defines the `AnalyzerAgent`, responsible for taking a single sample
description (a "stub") from the DesignerAgent's plan and expanding it into a
detailed, natural-language synthesis recipe. This recipe is then structured
as an `AnalyzerOutput` Pydantic model, ready for the CompilerAgent.
It now uses the `agents` SDK.

Key features:
- Inherits from `agents.Agent`.
- Instructions are loaded from `prompts/analyzer.md`.
- Input: `AnalyzerInput` schema (or a JSON string representation of it).
- Output: `AnalyzerOutput` schema (facilitated by `output_type`).
- Focuses on enriching a concise idea into a more actionable set of instructions
  for DSP code generation.

@dependencies
- `agents.Agent` (from the new SDK)
- `phonosyne.agents.schemas.AnalyzerInput`, `phonosyne.agents.schemas.AnalyzerOutput`
- `phonosyne.settings` (for `MODEL_ANALYZER`, `DEFAULT_SR`)
- `logging`
- `pathlib`

@notes
- The quality of the `description` field in `AnalyzerOutput` is critical for the
  success of the subsequent CompilerAgent.
- The prompt (`analyzer.md`) guides the LLM to produce JSON conforming to `AnalyzerOutput`.
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
from pydantic import BaseModel, Field  # For AnalyzerInput

from phonosyne import settings
from phonosyne.agents.schemas import AnalyzerInput, AnalyzerOutput

# Note: phonosyne.utils.slugify is no longer directly used here.
# The prompt instructs the LLM to generate a snake_case_slug.

logger = logging.getLogger(__name__)


# --- Load Instructions ---
try:
    PROMPT_FILE_PATH = (
        Path(__file__).resolve().parent.parent.parent / "prompts" / "analyzer.md"
    )
    with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
        ANALYZER_INSTRUCTIONS = f.read()
except FileNotFoundError:
    logger.error(
        f"CRITICAL: Analyzer prompt file not found at {PROMPT_FILE_PATH}. "
        "AnalyzerAgent will not function correctly."
    )
    ANALYZER_INSTRUCTIONS = (
        "ERROR: Analyzer prompt not loaded. "
        "Your task is to take a sound idea and expand it into a detailed synthesis recipe."
    )


# --- Define Agent ---
class AnalyzerAgent(Agent):
    """
    The AnalyzerAgent enriches a sample stub into a detailed synthesis recipe,
    using the `agents.Agent` SDK.
    Its instructions are loaded from `prompts/analyzer.md`.
    The input (e.g., a JSON string of AnalyzerInput or a descriptive string)
    is provided when this agent is run.
    It aims to output a JSON string conforming to the AnalyzerOutput schema.
    """

    def __init__(self, **kwargs: Any):
        """
        Initializes the AnalyzerAgent.

        Args:
            **kwargs: Additional keyword arguments to pass to the `agents.Agent` constructor.
                      The 'model' kwarg can be a model name (str) or a Model instance.
        """
        agent_name = kwargs.pop("name", "PhonosyneAnalyzer_Agent")
        # The 'model' kwarg will be passed in by OrchestratorAgent.
        model_arg = kwargs.pop("model", settings.MODEL_ANALYZER)

        # The `instructions` are the system prompt for the LLM.
        # The actual sound stub data (e.g., from AnalyzerInput) will be passed as `input`
        # to `Runner.run(agent, input=...)`.
        super().__init__(
            name=agent_name,
            instructions=ANALYZER_INSTRUCTIONS,
            model=model_arg,  # Pass the model name or Model instance
            # output_type=AnalyzerOutput,  # Temporarily removed to rely on prompt for JSON structure
            tools=[],  # AnalyzerAgent itself does not use tools
            temperature=0.6,  # Recommended 0.5 to 0.7
            top_p=0.95,
            top_k=0,
            frequency_penalty=0.2,  # Recommended 0.1 to 0.3
            presence_penalty=0.2,  # Recommended 0.1 to 0.3
            repetition_penalty=1.0,
            min_p=0.0,
            top_a=0.0,
            **kwargs,
        )


# Note: The old `if __name__ == "__main__":` block has been removed.
# Testing will be done using `agents.Runner` in dedicated test files (Step 17).
