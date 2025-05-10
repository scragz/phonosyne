# Phonosyne System Overview

Phonosyne is an AI-powered system designed to generate collections of audio samples from natural-language sound design briefs. It employs a multi-agent pipeline, where each agent has a specialized role in transforming the initial prompt into validated `.wav` files.

## Core Architecture

The system is built around a central `Manager` (in `phonosyne.orchestrator`) that coordinates a sequence of agents and processes. The primary components are:

1.  **Input**: A user-provided text prompt describing the desired sound collection.
2.  **Agent Pipeline**:
    - **DesignerAgent**: Expands the brief into a structured plan.
    - **AnalyzerAgent**: Enriches individual sample descriptions from the plan into detailed synthesis recipes.
    - **CompilerAgent**: Generates Python DSP code from the synthesis recipes, executes it, and iteratively refines it.
3.  **Code Execution**: LLM-generated Python code is run using `smolagents.LocalPythonExecutor` for safer local execution.
4.  **Validation**: Generated audio files are validated against technical specifications.
5.  **Output**: A directory containing the generated `.wav` files and a `manifest.json` summarizing the collection.

## Detailed Workflow and Data Flow

The process begins when the user invokes Phonosyne via its CLI or SDK.

### 1. Initialization

- The `Manager` class is instantiated. It initializes instances of `DesignerAgent`, `AnalyzerAgent`, and `CompilerAgent`.
- Configuration settings (LLM models, audio defaults, API keys) are loaded from `phonosyne.settings` (which can be influenced by an `.env` file).

### 2. Design Phase (DesignerAgent)

- **Input**: The user's sound design brief (a string).
- **Process**:
  - The `Manager` calls `DesignerAgent.process()` with the brief.
  - `DesignerAgent` uses its system prompt (`prompts/designer.md`) and the configured LLM (`MODEL_DESIGNER`) to generate a structured plan.
  - The LLM is instructed to output a JSON object.
- **Output**: A `DesignerOutput` Pydantic model (defined in `phonosyne.agents.schemas`). This model contains:
  - `brief_slug`: A slugified version of the user brief.
  - `movements`: A list of `MovementStub` objects. Each `MovementStub` includes:
    - `id` and `name` for the movement.
    - `samples`: A list of `SampleStub` objects. Each `SampleStub` contains:
      - `id`: Unique ID for the sample (e.g., "L1.1").
      - `seed_description`: A concise textual description of the sound.
      - `duration_s`: The target duration in seconds.
- **Data Flow**: `str (user_brief) -> DesignerAgent -> DesignerOutput (Pydantic model)`

### 3. Sample Generation Loop (Orchestrated by Manager)

The `Manager` iterates through each `SampleStub` in the `DesignerOutput` plan. For each sample, the following sub-pipeline is executed, potentially in parallel using a `ThreadPoolExecutor` (configurable by `num_workers`):

#### 3.a. Analysis Phase (AnalyzerAgent)

- **Input**: An `AnalyzerInput` Pydantic model, derived from the current `SampleStub`. It includes the sample's `id`, `seed_description`, and `duration_s`.
- **Process**:
  - The `Manager` (specifically, its `_static_process_single_sample` worker method) calls `AnalyzerAgent.process()`.
  - `AnalyzerAgent` uses its system prompt (`prompts/analyzer.md`) and `MODEL_ANALYZER` to transform the concise `seed_description` into a detailed, natural-language synthesis recipe.
  - The LLM is instructed to output a single-line JSON object.
- **Output**: An `AnalyzerOutput` Pydantic model. This model contains:
  - `effect_name`: A slugified name for the sound.
  - `duration`: Target duration (float, seconds).
  - `sample_rate`: Target sample rate (int, Hz, typically from `settings.DEFAULT_SR`).
  - `description`: A rich, natural-language text detailing how to synthesize the sound (layers, waveforms, envelopes, effects, etc.).
- **Data Flow**: `AnalyzerInput (from SampleStub) -> AnalyzerAgent -> AnalyzerOutput (Pydantic model)`

#### 3.b. Compilation & Execution Phase (CompilerAgent & exec_env)

- **Input**: The `AnalyzerOutput` model (synthesis recipe) from the AnalyzerAgent.
- **Process (Iterative Loop within CompilerAgent)**:
  1.  **Code Generation**:
      - `CompilerAgent` uses its system prompt (`prompts/compiler.md`) and `MODEL_COMPILER`.
      - The prompt instructs the LLM to generate Python DSP code based on the `AnalyzerOutput.description`.
      - Crucially, the generated code **must return a tuple `(audio_data_numpy_array, sample_rate_int)`**. It does _not_ write a file itself.
      - The agent extracts the Python code from the LLM's Markdown response.
  2.  **Code Execution (`phonosyne.utils.exec_env.run_code`)**:
      - The extracted Python code string is passed to `run_code` using the `"local_executor"` mode.
      - `LocalPythonExecutor` (from `smolagents`) executes the code. It has a list of authorized imports (`numpy`, `scipy`, `math`, `random`, etc.) and an operation limit for safety.
      - If execution is successful, `LocalPythonExecutor` returns the `(audio_data, sample_rate)` tuple.
      - `run_code` then takes this tuple and saves the `audio_data` to a temporary `.wav` file using `soundfile.write()`. The path to this temporary WAV is returned by `run_code`.
  3.  **Validation (via `phonosyne.dsp.validators.validate_wav`)**:
      - The `CompilerAgent` calls `validate_wav` (passed as `validator_fn`) with the path to the temporary WAV file and the `AnalyzerOutput` (which contains the target specifications like duration and sample rate).
      - `validate_wav` checks:
        - Sample rate.
        - Duration (within tolerance defined in `settings.DURATION_TOLERANCE_S`).
        - Bit depth (32-bit float).
        - Channels (mono).
        - Peak audio level (must be `≤ settings.TARGET_PEAK_DBFS`).
      - If validation passes, the loop for this sample ends, and the path to the (still temporary) WAV is considered final for this stage.
  4.  **Repair (If Execution or Validation Fails)**:
      - If code execution raises an error (e.g., `InterpreterError` from `LocalPythonExecutor`, or an error during `soundfile.write`), or if `validate_wav` raises `ValidationFailedError`, the `CompilerAgent` captures the error.
      - The error message is formatted and provided back to the LLM in the next iteration of the code generation prompt, asking it to fix the issue.
      - This loop continues for a maximum of `settings.MAX_COMPILER_ITERATIONS`.
- **Output (from CompilerAgent.run)**: A `pathlib.Path` object pointing to the validated `.wav` file (still in a persistent temporary location managed by `exec_env.run_code`).
- **Data Flow**: `AnalyzerOutput -> CompilerAgent -> (LLM for code) -> str (Python code) -> exec_env.run_code (with LocalPythonExecutor) -> (np.array, int) -> soundfile.write -> Path (temp WAV) -> validate_wav -> Path (final temp validated WAV)`

#### 3.c. File Management (Manager)

- Once `CompilerAgent.run()` successfully returns a path to a validated temporary WAV file:
  - The `Manager` moves this file from its persistent temporary location (e.g., in `./output/exec_env_output/`) to the final run-specific output directory (e.g., `./output/YYYYMMDD-HHMMSS_brief-slug/sample_id_effect-name.wav`).
- **Output**: The final `.wav` file in the run's output directory.

### 4. Aggregation and Manifest Generation (Manager)

- After all samples have been processed (or attempted):
  - The `Manager` collects `SampleGenerationResult` objects for each sample, detailing its status (`success`, `failed_compilation`, `failed_validation`, etc.), final path (if successful), and any error messages.
  - A `manifest.json` file is written to the root of the run-specific output directory. This JSON file includes:
    - The original user brief and its slug.
    - The path to the output directory.
    - Counts of planned, succeeded, and failed samples.
    - Total generation time.
    - The original `DesignerOutput` plan structure.
    - A list of detailed results for each sample.
- **Output**: A populated output directory and a `manifest.json`.

## Entry Points

- **SDK**: The `phonosyne.run_prompt()` function is the primary entry point for programmatic use. It instantiates and runs the `Manager`.
- **CLI**: The `phonosyne` command (defined in `phonosyne.cli` using Typer) parses command-line arguments and calls `phonosyne.run_prompt()`. The `scripts/phonosyne_cli.py` wrapper allows direct execution.

## Key Configuration Points (from `phonosyne.settings`)

- `MODEL_DESIGNER`, `MODEL_ANALYZER`, `MODEL_COMPILER`: Specify the LLM models for each agent.
- `OPENROUTER_API_KEY`: Essential for LLM calls.
- `DEFAULT_SR`, `TARGET_PEAK_DBFS`, `DURATION_TOLERANCE_S`, `BIT_DEPTH`: Define audio technical specifications.
- `DEFAULT_OUT_DIR`: Base directory for all generated outputs.
- `PROMPTS_DIR`: Location of agent system prompt files.
- `MAX_COMPILER_ITERATIONS`, `COMPILER_TIMEOUT_S` (timeout for inline exec, op limit for LocalPythonExecutor): Control CompilerAgent behavior.
- `AGENT_MAX_RETRIES`: For LLM API call retries in `AgentBase`.
- `EXECUTION_MODE`: Defaults to `"local_executor"` (if previous default was "subprocess") or can be set to `"inline"`.
- `DEFAULT_WORKERS`: Default number of parallel workers for sample processing.
- `AUTHORIZED_IMPORTS_FOR_DSP` (in `exec_env.py`): Controls what modules generated code can import when using `LocalPythonExecutor`.

This overview describes the main flow and components of the Phonosyne system as implemented up to Step 6.1 of the development plan.
