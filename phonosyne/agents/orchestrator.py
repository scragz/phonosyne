"""
Orchestrator Agent for the Phonosyne Pipeline (Refactored for agents SDK)

This module defines the `OrchestratorAgent`, which replaces the old `Manager`
and orchestrates the entire Phonosyne sound generation pipeline using the
`agents` SDK.

Key features:
- Inherits from `agents.Agent`.
- Uses refactored `DesignerAgent`, `AnalyzerAgent`, `CompilerAgent` as tools.
- Uses `FileMoverTool` and `ManifestGeneratorTool` (FunctionTools).
- Manages the overall workflow from user brief to a collection of WAV files
  and a manifest.json, guided by its instructions.

@dependencies
- `agents.Agent` (from the new SDK)
- `phonosyne.agents.designer.DesignerAgent`
- `phonosyne.agents.analyzer.AnalyzerAgent`
- `phonosyne.agents.compiler.CompilerAgent`
- `phonosyne.tools.move_file` (as FileMoverTool)
- `phonosyne.tools.generate_manifest_file` (as ManifestGeneratorTool)
- `phonosyne.settings` (for `MODEL_ORCHESTRATOR` or a default model)
- `logging`
- `pathlib`

@notes
- The detailed workflow logic will be defined in the agent's `instructions` (Step 13).
- Error handling and state management across tool calls are crucial for robustness.
"""

import logging
from pathlib import Path
from typing import Any, List

# Import the new Agent class from the SDK
from agents import Agent, ModelSettings

from phonosyne import settings
from phonosyne.agents.analyzer import AnalyzerAgent
from phonosyne.agents.compiler import CompilerAgent
from phonosyne.agents.designer import DesignerAgent

# Schemas might be needed for parsing outputs if not automatically handled by output_type of sub-agents
from phonosyne.agents.schemas import AnalyzerOutput, DesignerOutput
from phonosyne.sdk import OPENROUTER_MODEL_PROVIDER  # Import our model provider
from phonosyne.tools import generate_manifest_file, move_file

logger = logging.getLogger(__name__)


# Function to load instructions from a file
def load_instructions_from_file(file_path: Path) -> str:
    """Loads agent instructions from a markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Instruction file not found: {file_path}")
        # Fallback or raise an error, depending on desired behavior
        return "Default instructions: Orchestrate the Phonosyne pipeline."
    except Exception as e:
        logger.error(f"Error loading instructions from {file_path}: {e}")
        return "Error loading instructions."


# Determine the absolute path to the prompts directory
# Assuming this script is in phonosyne/agents/ and prompts is at phonosyne/../prompts/
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
ORCHESTRATOR_INSTRUCTIONS_PATH = PROMPTS_DIR / "orchestrator.md"


class OrchestratorAgent(Agent):
    """
    Orchestrates the Phonosyne sound generation pipeline using specialized agents and tools.
    """

    def __init__(self, **kwargs: Any):
        """
        Initializes the OrchestratorAgent.

        Args:
            **kwargs: Additional keyword arguments to pass to the `agents.Agent` constructor.
        """
        agent_name = kwargs.pop("name", "PhonosyneOrchestrator_Agent")
        # Assuming a model for the orchestrator, or use a general powerful model
        model = kwargs.pop(
            "model", getattr(settings, "MODEL_ORCHESTRATOR", settings.MODEL_DEFAULT)
        )
        # The OrchestratorAgent itself will get its model_provider from the RunConfig
        # when Runner.run is called in sdk.py.

        # Instantiate specialist agents by providing them with Model instances
        # obtained from our OPENROUTER_MODEL_PROVIDER.
        designer_model_instance = OPENROUTER_MODEL_PROVIDER.get_model(
            settings.MODEL_DESIGNER
        )
        designer_agent_instance = DesignerAgent(model=designer_model_instance)

        analyzer_model_instance = OPENROUTER_MODEL_PROVIDER.get_model(
            settings.MODEL_ANALYZER
        )
        analyzer_agent_instance = AnalyzerAgent(model=analyzer_model_instance)

        compiler_model_instance = OPENROUTER_MODEL_PROVIDER.get_model(
            settings.MODEL_COMPILER
        )
        compiler_agent_instance = CompilerAgent(model=compiler_model_instance)

        # Prepare tools for the OrchestratorAgent
        agent_tools: List[Any] = [
            designer_agent_instance.as_tool(
                tool_name="DesignerAgentTool",
                tool_description="Expands a user's sound design brief into a structured plan (JSON) detailing themes and individual sound stubs with descriptions and target durations. Input is the user brief string.",
            ),
            analyzer_agent_instance.as_tool(
                tool_name="AnalyzerAgentTool",
                tool_description="Takes a single sound stub (JSON from DesignerAgentTool's plan) and enriches it into a detailed, natural-language synthesis recipe (JSON). Input is a JSON string of the sound stub.",
            ),
            compiler_agent_instance.as_tool(
                tool_name="CompilerAgentTool",
                tool_description="Takes a detailed synthesis recipe (JSON from AnalyzerAgentTool), generates Python DSP code, orchestrates its execution and validation using its internal tools, and returns the path to a validated temporary .wav file (string). Input is a JSON string of the synthesis recipe.",
            ),
            move_file,
            generate_manifest_file,
        ]

        # Load instructions from the markdown file
        orchestrator_instructions = load_instructions_from_file(
            ORCHESTRATOR_INSTRUCTIONS_PATH
        )

        # `output_type` for OrchestratorAgent could be a Pydantic model summarizing the run,
        # or simply a string (e.g., path to manifest or success/failure message).
        # For now, let's use str, assuming it will output a final status message.
        super().__init__(
            name=agent_name,
            instructions=orchestrator_instructions,
            model=model,
            tools=agent_tools,
            output_type=str,
            model_settings=ModelSettings(
                temperature=0.4,  # Recommended 0.3 to 0.5
                top_p=0.9,
                frequency_penalty=0.1,  # Recommended 0.0 to 0.2
                presence_penalty=0.15,  # Recommended 0.0 to 0.3
            ),
            **kwargs,
        )


# The old Manager class and its methods like _process_single_sample, run,
# and _static_process_single_sample are now superseded by the OrchestratorAgent's
# instruction-driven workflow using the agents SDK.
# The main application entry point (phonosyne.run_prompt) will instantiate and
# run this OrchestratorAgent.
