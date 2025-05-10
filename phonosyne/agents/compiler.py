"""
Compiler Agent for Phonosyne (Refactored for agents SDK)

This module defines the `CompilerAgent`, which is responsible for the code
generation and execution part of the Phonosyne pipeline. It takes a detailed
synthesis recipe (from the AnalyzerAgent), generates Python DSP code,
and uses tools to execute and validate this code. It's designed to iteratively
refine the code if errors occur. This version is refactored for the `agents` SDK.

Key features:
- Inherits from `agents.Agent`.
- Instructions are loaded from `prompts/compiler.md`.
- Input: `AnalyzerOutput` schema (as a JSON string).
- Output: Path to a validated temporary .wav file (as a string).
- Uses `PythonCodeExecutionTool` and `AudioValidationTool`.
- The iterative loop for code generation, execution, validation, and repair
  is guided by its instructions and managed by the `agents` SDK.

@dependencies
- `agents.Agent` (from the new SDK)
- `phonosyne.agents.schemas.AnalyzerOutput` (as conceptual input)
- `phonosyne.settings` (for `MODEL_COMPILER`, `MAX_COMPILER_ITERATIONS`)
- `phonosyne.tools.execute_python_dsp_code` (as PythonCodeExecutionTool)
- `phonosyne.tools.validate_audio_file` (as AudioValidationTool)
- `logging`
- `pathlib`

@notes
- The effectiveness of the iterative repair loop depends heavily on the quality
  of the instructions in `prompts/compiler.md` and the LLM's ability to
  use the provided tools and feedback.
"""

import logging
from pathlib import Path
from typing import Any

# Import the new Agent class from the SDK
from agents import (
    Agent,
    ModelSettings,
)

from phonosyne import settings
from phonosyne.agents.schemas import AnalyzerOutput  # Conceptual input schema
from phonosyne.tools import execute_python_dsp_code, validate_audio_file

logger = logging.getLogger(__name__)

# --- Load Instructions ---
try:
    PROMPT_FILE_PATH = (
        Path(__file__).resolve().parent.parent.parent / "prompts" / "compiler.md"
    )
    with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
        COMPILER_INSTRUCTIONS = f.read()
except FileNotFoundError:
    logger.error(
        f"CRITICAL: Compiler prompt file not found at {PROMPT_FILE_PATH}. "
        "CompilerAgent will not function correctly."
    )
    COMPILER_INSTRUCTIONS = (
        "ERROR: Compiler prompt not loaded. "
        "Your task is to take a synthesis recipe (JSON), generate Python DSP code, "
        "use tools to execute and validate it, and return a WAV file path."
    )


# --- Define Agent ---
class CompilerAgent(Agent):
    """
    The CompilerAgent generates, executes, and refines Python DSP code using tools,
    based on instructions from `prompts/compiler.md`.
    Input is expected to be a JSON string of an AnalyzerOutput.
    Output is expected to be a string path to the generated WAV file.
    """

    def __init__(self, **kwargs: Any):
        """
        Initializes the CompilerAgent.

        Args:
            **kwargs: Additional keyword arguments to pass to the `agents.Agent` constructor.
                      The 'model' kwarg can be a model name (str) or a Model instance.
        """
        agent_name = kwargs.pop("name", "PhonosyneCompiler_Agent")
        # The 'model' kwarg will be passed in by OrchestratorAgent.
        model_arg = kwargs.pop("model", settings.MODEL_COMPILER)

        # The tools available to this agent
        # The SDK will use the function signatures and docstrings of these tools
        # to inform the LLM.
        agent_tools = [
            execute_python_dsp_code,  # Referred to as PythonCodeExecutionTool in spec
            validate_audio_file,  # Referred to as AudioValidationTool in spec
        ]

        super().__init__(
            name=agent_name,
            instructions=COMPILER_INSTRUCTIONS,
            model=model_arg,  # Pass the model name or Model instance
            tools=agent_tools,
            output_type=str,  # Expects a string (file path) as the final output
            model_settings=ModelSettings(
                temperature=0.3,  # Recommended 0.2 to 0.4
                top_p=0.9,
                frequency_penalty=0.0,
                presence_penalty=0.0,
            ),
            **kwargs,
        )


# Note: The old `if __name__ == "__main__":` block has been removed.
# The iterative logic is now part of the agent's instructions and SDK execution.
# Step 10 will focus on refining these instructions for the iterative loop.
