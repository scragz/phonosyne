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
from agents import (
    Agent,  # type: ignore # Assuming agents SDK might not be in static analysis path yet
)
from agents import FunctionTool  # For type hinting if needed, tools are passed directly

from phonosyne import settings
from phonosyne.agents.analyzer import AnalyzerAgent
from phonosyne.agents.compiler import CompilerAgent
from phonosyne.agents.designer import DesignerAgent

# Schemas might be needed for parsing outputs if not automatically handled by output_type of sub-agents
from phonosyne.agents.schemas import AnalyzerOutput, DesignerOutput
from phonosyne.tools import generate_manifest_file, move_file

logger = logging.getLogger(__name__)

# Detailed Orchestrator Instructions
ORCHESTRATOR_INSTRUCTIONS = """
You are the Phonosyne Orchestrator, a meticulous project manager for sound library generation.
Your primary goal is to take a user's input brief and manage a pipeline of specialized agents and tools to generate a collection of sound effects and a manifest file.

**Input Processing:**
1.  The user will provide a natural language `user_brief` as input. Store this brief.

**Directory and Path Management:**
2.  You need to define a unique `run_output_directory_name` for this specific generation run. A good format is `YYYYMMDD-HHMMSS_brief_slug`, where `brief_slug` is a short, filesystem-safe version of the user_brief (e.g., first 3-5 words, lowercase, hyphen-separated). Example: `20250509-213000_futuristic-cityscape-sounds`.
3.  All final WAV files and the `manifest.json` will be placed in this directory. The tools (`FileMoverTool`, `ManifestGeneratorTool`) will create this directory if it doesn't exist when they are called with a path inside it. You must consistently use this `run_output_directory_name` string when constructing target paths for these tools.

**Core Workflow - Step-by-Step Tool Usage:**
4.  **Design Phase:**
    *   Call the `DesignerAgentTool` with the `user_brief` as input.
    *   The tool will return a JSON string representing the `DesignPlan`. Parse this JSON string.
    *   If `DesignerAgentTool` fails or returns invalid JSON, report the error and stop.
    *   Store the parsed `DesignPlan` (which includes a list of `SampleStub` objects).

5.  **Sample Generation Loop:**
    *   Initialize an empty list called `sample_generation_results` to store the outcome of each sample.
    *   Iterate through each `SampleStub` in the `DesignPlan.samples` list. For each `SampleStub`:
        a.  **Analysis Phase:**
            *   Prepare the input for `AnalyzerAgentTool`: this is a JSON string representation of the current `SampleStub`.
            *   Call `AnalyzerAgentTool` with this JSON string.
            *   The tool returns a JSON string representing the `SynthesisRecipe`. Parse this JSON.
            *   If `AnalyzerAgentTool` fails or returns invalid JSON for this sample, record the error (including `sample_id` and `seed_description` from the `SampleStub`, and the error message) in `sample_generation_results`. Then, continue to the next `SampleStub`.
            *   Store the parsed `SynthesisRecipe`.

        b.  **Compilation Phase:**
            *   The input for `CompilerAgentTool` is the `SynthesisRecipe` (as a JSON string) obtained from `AnalyzerAgentTool`.
            *   Call `CompilerAgentTool` with this `SynthesisRecipe` JSON string.
            *   The tool returns a string, which is the path to the temporary validated `.wav` file (`temp_wav_path`).
            *   If `CompilerAgentTool` fails (e.g., returns an error message instead of a path, or an obviously invalid path), record the error (including `sample_id`, `seed_description`, `SynthesisRecipe`, and the error message) in `sample_generation_results`. Then, continue to the next `SampleStub`.
            *   Store the `temp_wav_path`.

        c.  **File Finalization Phase (if Compilation Succeeded):**
            *   Construct the `final_wav_filename`. Use the `sample_id` from the `SampleStub` and the `effect_name` from the `SynthesisRecipe`. A good format is `{sample_id}_{safe_effect_name}.wav`. Ensure `safe_effect_name` is filesystem-safe (e.g., replace spaces/special characters with underscores, or use a slugified version if you can generate one).
            *   Construct the `final_wav_path` string: `{run_output_directory_name}/{final_wav_filename}`.
            *   Call `FileMoverTool` with `source_path=temp_wav_path` and `target_path=final_wav_path`.
            *   If `FileMoverTool` returns an error message, record this error (including `sample_id`, `temp_wav_path`, `final_wav_path`, and error) in `sample_generation_results`. The sample is considered failed at this stage.
            *   If `FileMoverTool` succeeds, record the success (including `sample_id`, `SynthesisRecipe`, and `final_wav_path`) in `sample_generation_results`.

6.  **Manifest Generation:**
    *   After iterating through all `SampleStub`s, prepare the `manifest_data`. This should be a comprehensive JSON object containing:
        *   The original `user_brief`.
        *   The `run_output_directory_name`.
        *   The full `DesignPlan` (as a JSON object, not string).
        *   The list of `sample_generation_results` (each entry detailing `sample_id`, status (e.g., "success", "failed_analysis", "failed_compilation", "failed_file_move"), `final_wav_path` if successful, `SynthesisRecipe` used, and any `error_message`).
    *   Convert this `manifest_data` object into a JSON string (`manifest_data_json`).
    *   Call `ManifestGeneratorTool` with `manifest_data_json=manifest_data_json` and `output_directory=run_output_directory_name`.
    *   If `ManifestGeneratorTool` returns an error, note this failure. The primary sound generation might be complete, but the manifest failed.

**Final Output:**
7.  Your final output should be a single string message summarizing the entire operation. Include:
    *   The `run_output_directory_name`.
    *   The number of samples planned, successfully generated, and failed.
    *   The path to the `manifest.json` file: `{run_output_directory_name}/manifest.json`.
    *   Mention if manifest generation itself failed.

**Important Considerations:**
*   **JSON Handling:** Be meticulous. Outputs from tools like `DesignerAgentTool`, `AnalyzerAgentTool` are JSON strings that YOU must parse. Inputs to tools like `AnalyzerAgentTool` (a `SampleStub`), `CompilerAgentTool` (a `SynthesisRecipe`), and `ManifestGeneratorTool` (the `manifest_data`) must be formatted by YOU as JSON strings.
*   **Path Construction:** You are responsible for constructing path strings. Tools like `FileMoverTool` and `ManifestGeneratorTool` expect directory and file path strings.
*   **Error Propagation:** If a tool returns an error message (as a string), treat it as a failure for that step and record it. Do not try to pass error messages as valid data to subsequent tools unless explicitly instructed for a retry mechanism (which is internal to `CompilerAgentTool`).
*   **Statefulness:** You need to maintain context throughout this process (e.g., `user_brief`, `run_output_directory_name`, `DesignPlan`, `sample_generation_results`).
*   **Filenames:** When constructing `final_wav_filename`, ensure it's filesystem-safe. A simple approach for `safe_effect_name` is to take `effect_name` from the recipe, convert to lowercase, and replace spaces and non-alphanumeric characters (except dots and underscores) with underscores. Limit its length if necessary.
"""


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

        # Instantiate specialist agents
        designer_agent_instance = DesignerAgent()
        analyzer_agent_instance = AnalyzerAgent()
        compiler_agent_instance = CompilerAgent()

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
            move_file,  # FunctionTool for moving files
            generate_manifest_file,  # FunctionTool for generating the manifest
        ]

        # The `instructions` will be refined in Step 13.
        # `output_type` for OrchestratorAgent could be a Pydantic model summarizing the run,
        # or simply a string (e.g., path to manifest or success/failure message).
        # For now, let's use str, assuming it will output a final status message.
        super().__init__(
            name=agent_name,
            instructions=ORCHESTRATOR_INSTRUCTIONS,  # Placeholder, to be detailed in Step 13
            model=model,
            tools=agent_tools,
            output_type=str,
            **kwargs,
        )


# The old Manager class and its methods like _process_single_sample, run,
# and _static_process_single_sample are now superseded by the OrchestratorAgent's
# instruction-driven workflow using the agents SDK.
# The main application entry point (phonosyne.run_prompt) will instantiate and
# run this OrchestratorAgent.
