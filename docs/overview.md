# Phonosyne System Overview

Phonosyne is an AI-powered system designed to generate collections of audio samples from natural-language sound design briefs. It employs a multi-agent pipeline, where each agent, built using the `openai-agents` SDK, has a specialized role in transforming the initial prompt into validated `.wav` files.

## Core Architecture

The system is built around a central `OrchestratorAgent` (in `phonosyne.agents.orchestrator`) that coordinates a sequence of other specialized agents and utility functions, all operating as tools within the `openai-agents` framework.

1. **Input**: A user-provided text prompt describing the desired sound collection.
2. **Agent Pipeline (as Tools to OrchestratorAgent)**:
   - **`DesignerAgentTool`**: Wraps `DesignerAgent`. Expands the brief into a structured plan (JSON string).
   - **`AnalyzerAgentTool`**: Wraps `AnalyzerAgent`. Enriches individual sample descriptions from the plan into detailed synthesis recipes (JSON string).
   - **`CompilerAgentTool`**: Wraps `CompilerAgent`. Generates Python DSP code from synthesis recipes, executes it, and iteratively refines it, returning a path to a validated temporary WAV file.
   - **`FileMoverTool`**: A `FunctionTool` for moving files.
   - **`ManifestGeneratorTool`**: A `FunctionTool` for creating the `manifest.json`.
3. **Code Execution**: LLM-generated Python code is run using `smolagents.LocalPythonExecutor` (via `phonosyne.utils.exec_env.run_code`) for safer local execution.
4. **Validation**: Generated audio files are validated against technical specifications using `phonosyne.dsp.validators.validate_wav`.
5. **Output**: A directory containing the generated `.wav` files and a `manifest.json` summarizing the collection.

## Detailed Workflow and Data Flow

The process begins when the user invokes Phonosyne, typically via `phonosyne.sdk.run_prompt()`.

### 1. Initialization (`phonosyne.sdk.run_prompt`)

- An `OrchestratorAgent` instance is created.
- The `OrchestratorAgent` initializes instances of `DesignerAgent`, `AnalyzerAgent`, and `CompilerAgent`. Crucially, it provides each of these specialist agents with specific `Model` instances obtained from `OPENROUTER_MODEL_PROVIDER` (defined in `phonosyne.sdk.py`). This ensures they use the correct LLM configurations (e.g., specific models from OpenRouter).
- These specialist agents, along with utility functions like `move_file` and `generate_manifest_file`, are configured as tools available to the `OrchestratorAgent`.
- Configuration settings (LLM models, audio defaults, API keys) are loaded from `phonosyne.settings` (which can be influenced by an `.env` file).
- The `agents.Runner.run()` method is called with the `OrchestratorAgent` as the starting agent, the user's brief as input, and a `RunConfig` specifying `OPENROUTER_MODEL_PROVIDER`.

### 2. Design Phase (OrchestratorAgent using `DesignerAgentTool`)

- **Input to Orchestrator**: The user's sound design brief (a string).
- **Process**:
  - The `OrchestratorAgent`, guided by its instructions (`prompts/orchestrator.md`), calls the `DesignerAgentTool`.
  - `DesignerAgent` (within the tool) uses its system prompt (`prompts/designer.md`) and its configured `Model` instance to generate a plan.
  - Due to the current setup (where `output_type` is not used in `DesignerAgent`'s constructor to ensure compatibility with certain LLMs like Gemini via OpenRouter), the `DesignerAgent`'s LLM is prompted to output a JSON string directly.
- **Output from `DesignerAgentTool`**: A JSON string representing the sound design plan.
- **Orchestrator Processing**: The `OrchestratorAgent`'s LLM receives this JSON string. Its instructions tell it to parse this string. If parsing is successful, it yields a structure equivalent to the `DesignerOutput` Pydantic model, containing:
  - `theme`: A short description of the user brief.
  - `samples`: A list of `SampleStub` structures. Each `SampleStub` contains:
    - `id`: Unique ID for the sample.
    - `seed_description`: A concise textual description of the sound.
    - `duration`: The target duration in seconds.
- **Data Flow**: `str (user_brief) -> OrchestratorAgent (uses DesignerAgentTool) -> str (JSON plan from DesignerAgent's LLM) -> OrchestratorAgent's LLM (parses to internal DesignerOutput structure)`

### 3. Sample Generation Loop (Orchestrated by `OrchestratorAgent`'s LLM logic)

The `OrchestratorAgent`'s LLM iterates through each sound stub derived from the parsed design plan. For each sample:

#### 3.a. Analysis Phase (OrchestratorAgent using `AnalyzerAgentTool`)

- **Input to `AnalyzerAgentTool`**: A JSON string representing the current `SampleStub` (or an equivalent `AnalyzerInput` structure), prepared by the `OrchestratorAgent`'s LLM.
- **Process**:
  - `OrchestratorAgent` calls `AnalyzerAgentTool`.
  - `AnalyzerAgent` (within the tool) uses its system prompt (`prompts/analyzer.md`) and its configured `Model` instance to transform the `seed_description` into a detailed synthesis recipe.
  - Similar to `DesignerAgent`, `AnalyzerAgent` is prompted to output a JSON string directly.
- **Output from `AnalyzerAgentTool`**: A JSON string representing the detailed synthesis recipe.
- **Orchestrator Processing**: The `OrchestratorAgent`'s LLM receives this JSON string and parses it. If successful, it yields a structure equivalent to the `AnalyzerOutput` Pydantic model, containing:
  - `effect_name`: A slugified name for the sound.
  - `duration`: Target duration (float, seconds).
  - `description`: A rich, natural-language text detailing how to synthesize the sound.
- **Data Flow**: `str (SampleStub/AnalyzerInput JSON) -> OrchestratorAgent (uses AnalyzerAgentTool) -> str (JSON recipe from AnalyzerAgent's LLM) -> OrchestratorAgent's LLM (parses to internal AnalyzerOutput structure)`

#### 3.b. Compilation & Execution Phase (OrchestratorAgent using `CompilerAgentTool`)

- **Input to `CompilerAgentTool`**: A JSON string representing the `AnalyzerOutput` (synthesis recipe), prepared by the `OrchestratorAgent`'s LLM.
- **Process (Iterative Loop within `CompilerAgent`)**:
  1. **Code Generation**:
     - `CompilerAgent` uses its system prompt (`prompts/compiler.md`) and its configured `Model` instance.
     - The prompt instructs the LLM to generate Python DSP code based on the `AnalyzerOutput.description`.
     - The generated code **must return a tuple `(audio_data_numpy_array, sample_rate_int)`**.
     - The agent extracts the Python code from the LLM's response.
  2. **Code Execution (`phonosyne.utils.exec_env.run_code`)**:
     - The Python code string is passed to `run_code`.
     - `LocalPythonExecutor` executes the code, returning `(audio_data, sample_rate)`.
     - `run_code` saves this to a temporary `.wav` file and returns its path.
  3. **Validation (via `phonosyne.dsp.validators.validate_wav`)**:
     - `CompilerAgent` calls `validate_wav` with the temporary WAV path and `AnalyzerOutput` specs.
  4. **Repair (If Execution or Validation Fails)**:
     - Errors are fed back to the `CompilerAgent`'s LLM for code correction, iterating up to `settings.MAX_COMPILER_ITERATIONS`.
- **Output from `CompilerAgentTool`**: A string representing the path to the validated temporary `.wav` file.
- **Data Flow**: `str (AnalyzerOutput JSON) -> OrchestratorAgent (uses CompilerAgentTool) -> CompilerAgent -> (LLM for code) -> str (Python code) -> exec_env.run_code -> Path (temp WAV) -> validate_wav -> str (final temp validated WAV path)`

#### 3.c. File Management (OrchestratorAgent using `FileMoverTool`)

- Once `CompilerAgentTool` successfully returns a path:
  - The `OrchestratorAgent`'s LLM determines the final path and uses `FileMoverTool` to move the temporary WAV to the run-specific output directory.
- **Output**: The final `.wav` file in the run's output directory.

### 4. Aggregation and Manifest Generation (OrchestratorAgent using `ManifestGeneratorTool`)

- After all samples are processed:
  - The `OrchestratorAgent`'s LLM aggregates results (status, paths, errors for each sample).
  - It structures this into a comprehensive JSON object for the manifest.
  - It calls `ManifestGeneratorTool` with this JSON data string and the output directory path.
- **Output**: A populated output directory and a `manifest.json`.

### 5. Reporting (OrchestratorAgent)

- The `OrchestratorAgent` (via its LLM) concludes by providing a summary of the operation. This is the final string output of the `OrchestratorAgent.run()` call.

## Entry Points

- **SDK**: The `phonosyne.sdk.run_prompt()` function is the primary entry point. It instantiates `OrchestratorAgent` and uses `agents.Runner` to execute it.
- **CLI**: The `phonosyne` command (defined in `phonosyne.cli`) parses arguments and calls `phonosyne.sdk.run_prompt()`.

## Key Configuration Points (from `phonosyne.settings`)

- `MODEL_DESIGNER`, `MODEL_ANALYZER`, `MODEL_COMPILER`, `MODEL_ORCHESTRATOR` (or `MODEL_DEFAULT`): Specify LLM models. These are used by `OrchestratorAgent` to get `Model` instances for itself and sub-agents via `OPENROUTER_MODEL_PROVIDER`.
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `DEFAULT_OPENROUTER_MODEL_NAME`: Configure OpenRouter access.
- `OPENROUTER_MODEL_PROVIDER` (in `phonosyne.sdk.py`): Central provider for `Model` instances. Used in `RunConfig`.
- `DEFAULT_SR`, `TARGET_PEAK_DBFS`, `DURATION_TOLERANCE_S`, `BIT_DEPTH`: Audio technical specifications.
- `DEFAULT_OUT_DIR`: Base directory for outputs.
- `PROMPTS_DIR`: Location of agent system prompt files.
- `MAX_COMPILER_ITERATIONS`: Controls `CompilerAgent`'s internal refinement loop.
- `EXECUTION_MODE`: For `phonosyne.utils.exec_env.run_code`.
- `AUTHORIZED_IMPORTS_FOR_DSP` (in `exec_env.py`): For `LocalPythonExecutor`.

This overview reflects the Phonosyne system's architecture using the `openai-agents` SDK.
