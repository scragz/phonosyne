"""
Compiler Agent for Phonosyne

This module defines the `CompilerAgent`, which is responsible for the code
generation and execution part of the Phonosyne pipeline. It takes a detailed
synthesis recipe (from the AnalyzerAgent), generates Python DSP code,
executes it in a sandboxed environment, and iteratively refines the code
if errors occur or validation fails.

Key features:
- Inherits from `AgentBase`.
- Uses the `prompts/compiler.md` template for LLM calls.
- Input: `AnalyzerOutput` schema (the synthesis recipe).
- Output: Path to a validated .wav file.
- Implements an iterative loop for code generation, execution, validation, and repair.
  - Uses `phonosyne.utils.exec_env.run_code` for sandboxed execution.
  - (Validation logic will be added in Step 4.2, for now, it assumes success or handles exec_env errors).
- Manages error messages from code execution to feed back into the LLM for repair.

@dependencies
- `phonosyne.agents.base.AgentBase`
- `phonosyne.agents.schemas.AnalyzerOutput` (as input)
- `phonosyne.settings` (for `MODEL_COMPILER`, `MAX_COMPILER_ITERATIONS`, etc.)
- `phonosyne.utils.exec_env.run_code`
- `pathlib.Path`
- `logging`
- `re` for extracting code from Markdown blocks.

@notes
- The iterative repair loop is a key aspect of this agent's robustness.
- The agent needs to carefully manage the conversation history with the LLM
  during the repair cycle to provide context about previous errors.
- Validation of the generated .wav file (e.g., duration, sample rate, peak levels)
  is a crucial step that will be integrated with `phonosyne.dsp.validators`.
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional, Tuple

from phonosyne import settings
from phonosyne.agents.base import AgentBase
from phonosyne.agents.schemas import AnalyzerOutput  # Input schema
from phonosyne.utils.exec_env import SecurityException, run_code  # For execution

logger = logging.getLogger(__name__)

# Output of CompilerAgent is a Path to the generated WAV file.
# AgentBase is generic on InputSchema, OutputSchema.
# For CompilerAgent, InputSchema is AnalyzerOutput, OutputSchema is effectively Path.
# Pydantic doesn't directly model Path as a schema in the same way as BaseModel.
# So, the `run` method will return Path, and `_parse_output` won't be used for Pydantic.


class CompilerAgent(AgentBase[AnalyzerOutput, Path]):  # OutputSchema is Path
    """
    The CompilerAgent generates, executes, and refines Python DSP code.
    """

    agent_name = "CompilerAgent"
    prompt_template_name = "compiler.md"  # Corresponds to prompts/compiler.md
    input_schema = AnalyzerOutput
    # output_schema = Path # Not a Pydantic model, so _parse_output won't be used.
    # The run method will directly return a Path.
    llm_model_name = settings.MODEL_COMPILER

    def _extract_python_code(self, llm_response: str) -> Optional[str]:
        """
        Extracts Python code from a Markdown fenced code block in the LLM's response.
        The compiler.md prompt asks for "only a Markdown fenced code-block".
        """
        # Regex to find a Python code block
        # It looks for ```python ... ``` or just ``` ... ```
        match = re.search(r"```(?:python\n)?(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: if no triple backticks, assume the whole response might be code
        # if it looks like Python (e.g., starts with import or def).
        # This is risky but can be a fallback.
        # The prompt is strict, so this should ideally not be needed.
        # if llm_response.strip().startswith(("import ", "def ", "#", "from ")):
        #    logger.warning("LLM response for CompilerAgent did not use Markdown fences, but looks like code. Attempting to use as is.")
        #    return llm_response.strip()

        logger.warning("Could not extract Python code block from LLM response.")
        logger.debug(f"Full LLM response for code extraction: {llm_response}")
        return None

    def run(self, inputs: AnalyzerOutput, **kwargs: Any) -> Path:
        """
        Executes the CompilerAgent's logic: generate, run, validate, repair code.

        Args:
            inputs: An AnalyzerOutput Pydantic model (the synthesis recipe).
            **kwargs: Additional keyword arguments.
                      `validator_fn`: An optional callable for validating the WAV.

        Returns:
            Path to the successfully generated and validated .wav file.

        Raises:
            ValueError: If prompt template not loaded or max iterations reached.
            FileNotFoundError: If WAV file not produced.
            Exception: Various exceptions from code execution or LLM calls.
        """
        if not self.prompt_template:
            logger.error("CompilerAgent prompt template not loaded.")
            raise ValueError("Prompt template is essential for CompilerAgent.")

        synthesis_recipe_json = inputs.model_dump_json(indent=2)

        # The compiler.md prompt is a system prompt.
        # The user message should contain the synthesis recipe.
        # The prompt also mentions "If you receive a traceback... assume it was produced by your previous script."
        # This implies a conversational history for the repair loop.

        # For now, let's structure the initial user message.
        # Conversation history will be managed within the loop.

        current_error_feedback: Optional[str] = None
        generated_code: Optional[str] = None
        wav_file_path: Optional[Path] = None

        # TODO (Step 4.2): Integrate actual validator function
        validator_fn = kwargs.get("validator_fn")

        for attempt in range(1, settings.MAX_COMPILER_ITERATIONS + 1):
            logger.info(
                f"CompilerAgent attempt {attempt}/{settings.MAX_COMPILER_ITERATIONS} "
                f"for effect: {inputs.effect_name}"
            )

            user_message_parts = []
            user_message_parts.append(
                f"Synthesis Recipe (JSON):\n```json\n{synthesis_recipe_json}\n```"
            )

            if current_error_feedback:
                user_message_parts.append(
                    f"\nPrevious attempt failed. Please fix the error.\nError details:\n```\n{current_error_feedback}\n```"
                )

            user_message_prompt = "\n".join(user_message_parts)

            raw_llm_response = self._llm_call(
                prompt=user_message_prompt,
                system_prompt=self.prompt_template,  # compiler.md is system prompt
                temperature=0.3,  # Compiler needs to be precise
                max_tokens=3072,  # Python code can be lengthy
            )

            generated_code = self._extract_python_code(raw_llm_response)
            if not generated_code:
                current_error_feedback = "LLM did not produce a valid Python code block. Please ensure the response is only a Markdown fenced code block containing Python code."
                logger.error(current_error_feedback)
                if attempt == settings.MAX_COMPILER_ITERATIONS:
                    raise ValueError(
                        f"CompilerAgent failed to generate valid code structure after {settings.MAX_COMPILER_ITERATIONS} attempts for {inputs.effect_name}."
                    )
                continue  # Retry LLM call

            logger.debug(
                f"Attempt {attempt}: Generated Python code:\n{generated_code[:500]}..."
            )

            try:
                # Execute the generated code
                # output_filename should be unique for this attempt or handled by exec_env
                # The compiler.md prompt says: "write to ./output/{effect_name}.wav"
                # exec_env.py currently copies to a persistent temp file.
                # The orchestrator will later move this to the final ./output/{slug}/<sample_id>.wav
                # For now, let's use effect_name as the base for the temp output.

                # The `run_code` function in `exec_env` now returns a path to a file
                # in `settings.DEFAULT_OUT_DIR / "exec_env_output"`.
                # This file is persistent until explicitly deleted.

                wav_file_path_attempt = run_code(
                    code=generated_code,
                    output_filename=f"{inputs.effect_name}_attempt{attempt}.wav",  # Unique temp name
                    mode=settings.EXECUTION_MODE,  # from settings
                    timeout_s=settings.COMPILER_TIMEOUT_S,
                )

                logger.info(
                    f"Attempt {attempt}: Code executed. WAV produced at: {wav_file_path_attempt}"
                )

                # --- Validation Step (Placeholder for Step 4.2) ---
                is_valid = False
                validation_error_msg = "Validation not yet implemented."
                if validator_fn:
                    try:
                        # validator_fn(path_to_wav, analyzer_output_spec)
                        validator_fn(wav_file_path_attempt, inputs)
                        is_valid = True
                        logger.info(
                            f"Attempt {attempt}: WAV file at {wav_file_path_attempt} passed validation."
                        )
                    except Exception as val_e:
                        is_valid = False
                        validation_error_msg = f"Validation failed: {str(val_e)}"
                        logger.warning(
                            f"Attempt {attempt}: Validation failed for {wav_file_path_attempt}. Reason: {validation_error_msg}"
                        )
                else:
                    # If no validator, assume valid for now (until Step 4.2)
                    logger.warning(
                        f"Attempt {attempt}: No validator function provided. Assuming WAV is valid."
                    )
                    is_valid = True
                # --- End Validation Placeholder ---

                if is_valid:
                    wav_file_path = (
                        wav_file_path_attempt  # Store the path of the valid WAV
                    )
                    logger.info(
                        f"Successfully generated and validated WAV for {inputs.effect_name} on attempt {attempt}."
                    )
                    return wav_file_path  # Success!
                else:
                    current_error_feedback = validation_error_msg
                    # Clean up the invalid WAV from this attempt
                    if wav_file_path_attempt.exists():
                        try:
                            wav_file_path_attempt.unlink()
                            logger.debug(
                                f"Cleaned up invalid WAV: {wav_file_path_attempt}"
                            )
                        except OSError as e_unlink:
                            logger.error(
                                f"Error cleaning up invalid WAV {wav_file_path_attempt}: {e_unlink}"
                            )

            except FileNotFoundError as e_fnf:  # From run_code if WAV not produced
                logger.warning(
                    f"Attempt {attempt}: Code executed but did not produce WAV file. Error: {e_fnf}"
                )
                current_error_feedback = f"Code executed but did not produce the expected WAV file. Error: {e_fnf}. Ensure the script writes to OUTPUT_WAV_PATH and prints its path."
            except SecurityException as e_sec:  # Custom exception from exec_env
                logger.error(
                    f"Attempt {attempt}: Security exception during code execution. Error: {e_sec}"
                )
                current_error_feedback = f"Security critical error during code execution: {e_sec}. The code might be attempting restricted operations."
                # This might be a non-recoverable error for the LLM, consider breaking loop.
                # For now, let it retry.
            except (
                Exception
            ) as e_exec:  # Includes subprocess.TimeoutExpired, CalledProcessError from run_code
                logger.warning(
                    f"Attempt {attempt}: Error during code execution. Error: {type(e_exec).__name__}: {e_exec}"
                )
                # Format a useful error message for the LLM
                tb_str = getattr(
                    e_exec, "stderr", str(e_exec)
                )  # Prefer stderr if available (from CalledProcessError)
                current_error_feedback = f"Error during code execution:\nType: {type(e_exec).__name__}\nDetails: {tb_str}"

            # If we are here, it means this attempt failed (either execution or validation)
            # Loop will continue if attempts remain.

        # If loop finishes without returning, all attempts failed.
        logger.error(
            f"CompilerAgent failed to produce a valid WAV for {inputs.effect_name} after {settings.MAX_COMPILER_ITERATIONS} attempts."
        )
        raise ValueError(
            f"Max iterations reached for CompilerAgent on effect {inputs.effect_name}. Last error: {current_error_feedback or 'Unknown error'}"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if not settings.OPENROUTER_API_KEY:
        print("Skipping CompilerAgent test: OPENROUTER_API_KEY not set.")
    else:
        print("Testing CompilerAgent (will make real LLM calls and execute code)...")
        compiler_agent = CompilerAgent()

        # Example AnalyzerOutput (input for CompilerAgent)
        # This would typically come from a real AnalyzerAgent run.
        test_analyzer_output = AnalyzerOutput(
            effect_name="simple_sine_test",
            duration=1.0,
            sample_rate=48000,
            description=(
                "Generate a simple 440 Hz sine wave at -6 dBFS peak for 1 second. "
                "Ensure it's mono, 48kHz, 32-bit float. "
                "Write to OUTPUT_WAV_PATH and print the absolute path of the file to stdout."
            ),
        )

        # Dummy validator for testing
        def dummy_validator(path: Path, spec: AnalyzerOutput):
            print(
                f"[DummyValidator] Validating {path} against spec for {spec.effect_name}..."
            )
            if not path.exists():
                raise FileNotFoundError("WAV file does not exist.")
            if path.stat().st_size == 0:
                raise ValueError("WAV file is empty.")
            print(f"[DummyValidator] {path} seems OK (basic checks).")
            # Real validator would check SR, duration, peak, etc.

        try:
            # Using process method which handles input schema validation (though not strictly needed here)
            # result_wav_path = compiler_agent.process(test_analyzer_output.model_dump())
            # Calling run directly for this test as process expects Dict for raw_inputs
            result_wav_path = compiler_agent.run(
                inputs=test_analyzer_output, validator_fn=dummy_validator
            )

            print(
                f"\nCompilerAgent Test Output: Successfully generated WAV at {result_wav_path}"
            )
            assert (
                result_wav_path.exists()
            ), "CompilerAgent should produce an existing WAV file."
            assert (
                result_wav_path.stat().st_size > 0
            ), "Generated WAV file should not be empty."

            print("\nCompilerAgent test successful.")
            # Note: The generated WAV file is in settings.DEFAULT_OUT_DIR / "exec_env_output"
            # and needs manual cleanup if this test is run repeatedly.
            print(
                f"Please check for {result_wav_path.name} in {result_wav_path.parent} and clean up manually."
            )

        except Exception as e:
            print(
                f"\nAn unexpected error occurred during CompilerAgent test: {e}",
                exc_info=True,
            )
