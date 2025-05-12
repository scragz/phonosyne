"""
- @description
- This module defines FunctionTools for the Phonosyne application,
- utilizing the `agents` SDK. These tools encapsulate specific,
- reusable functionalities that can be invoked by agents within the system.
-
- Key features:
- - Wrappers for existing utility functions (e.g., code execution, audio validation).
- - New utility functions for file operations (e.g., moving files, generating manifests).
- - Adherence to the `agents.function_tool` decorator for integration with the SDK.
-
- @dependencies
- - `agents` SDK (specifically `agents.function_tool`)
- - `phonosyne.agents.schemas` for Pydantic models.
- - Standard Python libraries (e.g., `json`, `pathlib`, `shutil`).
-
- @notes
- - Each tool is an asynchronous function.
- - Docstrings of tool functions serve as their descriptions for the calling agents.
"""

import json
import logging  # Added
import shutil
from pathlib import Path

from agents import function_tool

# Import Pydantic models from existing schemas
from phonosyne.agents.schemas import (  # Add other schemas as they become necessary for tool inputs/outputs
    AnalyzerOutput,
    DesignerOutput,
    SampleStub,
)

# Import specific utilities needed for the tools
from phonosyne.utils.exec_env import CodeExecutionError
from phonosyne.utils.exec_env import run_code as existing_run_code

logger = logging.getLogger(__name__)  # Added

# Determine Project Root and Output Directory for executed code
try:
    from phonosyne import settings as app_settings

    # Assuming BASE_DIR is a Path object or string representing the project root
    PROJECT_ROOT = Path(app_settings.BASE_DIR).resolve()
    logger.info(f"Using PROJECT_ROOT from settings.BASE_DIR: {PROJECT_ROOT}")
except (ImportError, AttributeError, TypeError) as e:
    logger.warning(
        f"Could not import or use app_settings.BASE_DIR (Error: {e}). "
        "Falling back to deriving project root from tools.py location."
    )
    # tools.py is in phonosyne/tools.py, so parent.parent should be project root
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    logger.info(f"Using fallback PROJECT_ROOT: {PROJECT_ROOT}")

EXEC_ENV_OUTPUT_DIR = PROJECT_ROOT / "output" / "exec_env_output"
logger.info(f"Execution environment output directory set to: {EXEC_ENV_OUTPUT_DIR}")


@function_tool
async def execute_python_dsp_code(
    code: str, output_filename: str, recipe_json: str
) -> str:
    """
    Executes Python DSP code, aiming to save the output .wav file directly into
    the project's output directory (output/exec_env_output/).
    If direct save isn't possible, it attempts to move the file from a temporary location.
    The DSP code must return a tuple: (numpy_array, sample_rate).
    'description' and 'duration' from recipe_json are available in the code's scope.

    Args:
        code: The Python DSP code string.
        output_filename: Suggested filename (e.g., "effect_attempt_1.wav"). Path components will be stripped.
        recipe_json: JSON string of the synthesis recipe (AnalyzerOutput schema).

    Returns:
        Absolute path to the .wav file in output/exec_env_output/ on success, or an error message.
    """
    logger.info(f"execute_python_dsp_code: initial output_filename='{output_filename}'")
    code_to_log = code[:500] + "..." if len(code) > 500 else code
    logger.debug(f"Code (first 500 chars):\\n{code_to_log}")

    try:
        recipe_data = json.loads(recipe_json)
        if not isinstance(recipe_data, dict):
            err_msg = f"Error: recipe_json did not decode to a dictionary. Type: {type(recipe_data)}"
            logger.error(err_msg)
            return err_msg

        description = recipe_data.get("description")
        duration = recipe_data.get("duration")
        if description is None or duration is None:
            missing = [
                k
                for k, v in {"description": description, "duration": duration}.items()
                if v is None
            ]
            err_msg = f"Error: {', '.join(missing)} missing from recipe_json."
            logger.error(err_msg)
            return err_msg

        # 1. Ensure the designated output directory exists
        try:
            EXEC_ENV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Ensured execution output directory exists: {EXEC_ENV_OUTPUT_DIR}"
            )
        except Exception as mkdir_err:
            err_msg = f"CRITICAL ERROR: Cannot create/access output directory {EXEC_ENV_OUTPUT_DIR}: {mkdir_err}"
            logger.error(err_msg, exc_info=True)
            return err_msg

        # 2. Sanitize output_filename to get a safe base name.
        base_name_candidate = Path(output_filename).name
        if not base_name_candidate or base_name_candidate in (".", ".."):
            base_name_candidate = "default_dsp_output.wav"
            logger.warning(
                f"Original output_filename '{output_filename}' was invalid/empty, using '{base_name_candidate}'"
            )

        if not base_name_candidate.lower().endswith(".wav"):
            final_base_filename = f"{base_name_candidate}.wav"
        else:
            final_base_filename = base_name_candidate
        logger.info(f"Sanitized base filename: {final_base_filename}")

        # 3. Construct the desired final absolute path.
        desired_final_wav_path = (EXEC_ENV_OUTPUT_DIR / final_base_filename).resolve()
        logger.info(
            f"Targeting final WAV path for direct write: {desired_final_wav_path}"
        )

        # 4. Call existing_run_code, passing the full desired path.
        returned_path_str_from_exec = existing_run_code(
            code=code,
            output_filename=str(
                desired_final_wav_path
            ),  # Attempt direct write to target
            recipe_description=str(description),
            recipe_duration=float(duration),
            recipe_json_str=recipe_json,
        )

        actually_written_path = Path(returned_path_str_from_exec).resolve()
        logger.info(f"existing_run_code reported writing to: {actually_written_path}")

        final_wav_path_to_return: Path | None = None

        # 5. Check where the file actually ended up.
        if not actually_written_path.exists():
            err_msg = (
                f"Error: existing_run_code path {actually_written_path} does not exist."
            )
            logger.error(err_msg)
            # Check if it wrote to desired_final_wav_path anyway and just returned a bad path
            if desired_final_wav_path.exists() and desired_final_wav_path.is_file():
                logger.warning(
                    f"File found at {desired_final_wav_path} despite existing_run_code returning non-existent path. Using this."
                )
                final_wav_path_to_return = desired_final_wav_path
            else:
                return err_msg  # File is truly missing
        elif actually_written_path == desired_final_wav_path:
            logger.info(
                f"Success: existing_run_code wrote directly to desired location: {desired_final_wav_path}"
            )
            final_wav_path_to_return = desired_final_wav_path
        else:
            # existing_run_code wrote somewhere else (e.g., /tmp). Attempt to move.
            logger.warning(
                f"existing_run_code wrote to {actually_written_path} instead of {desired_final_wav_path}. Attempting to move."
            )
            try:
                # Ensure target parent dir exists (should already, but good practice)
                desired_final_wav_path.parent.mkdir(parents=True, exist_ok=True)
                if (
                    desired_final_wav_path.exists()
                ):  # If target (e.g. from a previous failed run) exists
                    logger.warning(
                        f"Target file {desired_final_wav_path} already exists. Overwriting."
                    )
                    desired_final_wav_path.unlink()

                shutil.copy2(str(actually_written_path), str(desired_final_wav_path))
                logger.info(
                    f"File successfully copied from {actually_written_path} to {desired_final_wav_path}"
                )

                if actually_written_path.exists() and actually_written_path.is_file():
                    actually_written_path.unlink()
                    logger.info(
                        f"Successfully unlinked source file: {actually_written_path}"
                    )

                final_wav_path_to_return = desired_final_wav_path
            except Exception as move_err:
                err_msg = f"Error moving file from {actually_written_path} to {desired_final_wav_path}: {move_err}"
                logger.error(err_msg, exc_info=True)
                # File is at actually_written_path but couldn't be moved. Return error to avoid using /tmp path.
                return err_msg

        # 6. Final verification
        if (
            not final_wav_path_to_return
            or not final_wav_path_to_return.exists()
            or not final_wav_path_to_return.is_file()
        ):
            err_msg = f"Error: Final WAV path {final_wav_path_to_return} is invalid or file not found after processing."
            logger.error(err_msg)
            # Check if the original temp file still exists if move failed partway
            if (
                actually_written_path.exists()
                and actually_written_path != final_wav_path_to_return
            ):
                logger.error(
                    f"Original file at {actually_written_path} might still exist if move failed."
                )
            return err_msg

        logger.info(
            f"execute_python_dsp_code successfully produced: {final_wav_path_to_return}"
        )
        return str(final_wav_path_to_return)

    except json.JSONDecodeError as e:
        err_msg = f"JSONDecodeError for recipe_json: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
    except (
        CodeExecutionError
    ) as e:  # Assuming this is a custom error from existing_run_code
        err_msg = f"CodeExecutionError from existing_run_code: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
    except FileNotFoundError as e:
        err_msg = f"FileNotFoundError encountered: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
    except Exception as e:
        err_msg = f"Unexpected error in execute_python_dsp_code: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg


# Import specific utilities needed for the AudioValidationTool
from phonosyne.dsp.validators import (
    ValidationFailedError,
)
from phonosyne.dsp.validators import validate_wav as existing_validate_wav


@function_tool
async def validate_audio_file(file_path: str, spec_json: str) -> str:
    """
    Validates a generated .wav file against technical specifications.

    Args:
        file_path: Path to the temporary .wav file to validate.
        spec_json: A JSON string of the AnalyzerOutput schema containing target specifications
                   (like duration, effect_name). Sample rate is currently assumed from settings.

    Returns:
        "Validation successful" if all checks pass, otherwise a string detailing validation errors.
    """
    try:
        # Resolve path to absolute
        abs_file_path = Path(file_path).resolve()
        print(f"Validating audio file at path: {abs_file_path}")

        if not abs_file_path.exists():
            return f"Validation error: Audio file does not exist at {abs_file_path} (from {file_path})"

        spec_dict = json.loads(spec_json)
        # AnalyzerOutput is already imported at the top of the file
        analyzer_spec = AnalyzerOutput(**spec_dict)

        # existing_validate_wav is synchronous. Assuming openai-agents SDK handles this.
        existing_validate_wav(file_path=abs_file_path, spec=analyzer_spec)
        print(f"Audio file at {abs_file_path} successfully validated")
        return "Validation successful"
    except ValidationFailedError as e:
        return f"ValidationFailedError: {str(e)}"
    except json.JSONDecodeError as e:
        return f"JSONDecodeError for spec_json: {str(e)}"
    except Exception as e:
        return f"Unexpected error during audio validation: {str(e)}"


@function_tool
async def move_file(source_path: str, target_path: str) -> str:
    """
    Moves a file from a source path to a target path.
    Creates the target directory if it doesn't exist.

    Args:
        source_path: The path of the file to move.
        target_path: The destination path for the file.

    Returns:
        A success message with the target path, or an error message string.
    """
    try:
        # Use resolve() to get absolute paths
        source = Path(source_path).resolve()
        target = Path(target_path).resolve()

        # Diagnostic logging - will appear in the agent's output
        print(f"Moving file from {source} to {target}")

        # Check if the file exists at the provided source path
        if not source.exists():
            # Check if this might be a file in the temporary directory
            alternative_sources = []

            # Case 1: If source path is already in /tmp/ or /private/tmp/, no need for alternatives
            if "/tmp/" in str(source_path) or "/private/tmp/" in str(source_path):
                pass  # We'll just return the error below
            else:
                # Case 2: Check if there's a file with the same name in /tmp/
                tmp_path_1 = Path("/tmp") / source.name
                if tmp_path_1.exists() and tmp_path_1.is_file():
                    alternative_sources.append(tmp_path_1)

                # Case 3: Check if there's a file with the same name in /private/tmp/
                tmp_path_2 = Path("/private/tmp") / source.name
                if tmp_path_2.exists() and tmp_path_2.is_file():
                    alternative_sources.append(tmp_path_2)

            if alternative_sources:
                # Use the first found alternative
                source = alternative_sources[0]
                print(f"Found source file at alternative location: {source}")
            else:
                return f"Error: Source file does not exist at {source} (from {source_path})"

        if not source.is_file():
            return f"Error: Source path is not a file: {source} (from {source_path})"

        # Ensure target directory exists
        target_parent_dir = target.parent
        if not target_parent_dir.exists():
            try:
                target_parent_dir.mkdir(parents=True, exist_ok=True)
                print(f"Created target directory: {target_parent_dir}")
            except PermissionError:
                return (
                    f"Error: Permission denied to create directory {target_parent_dir}"
                )
            except Exception as e:
                return f"Error creating target directory {target_parent_dir}: {str(e)}"
        elif not target_parent_dir.is_dir():
            return f"Error: Target parent path {target_parent_dir} exists but is not a directory."

        # Perform the move operation
        if target.exists():
            # If target already exists, remove it first to avoid issues
            target.unlink()
            print(f"Removed existing target file: {target}")

        # Use shutil.copy2 followed by source.unlink() instead of shutil.move
        # This is more robust across different filesystems
        shutil.copy2(str(source), str(target))
        print(f"Copied file to {target}")

        source.unlink()
        print(f"Removed source file: {source}")

        if not target.exists():
            return f"Error: File move operation failed. Target file does not exist at {target} after attempted move."

        return f"File moved successfully to {target}"
    except PermissionError:
        return f"Error: Permission denied during file move from {source_path} to {target_path}."
    except OSError as e:
        return f"OSError moving file from {source_path} to {target_path}: {str(e)}"
    except Exception as e:
        return f"Unexpected error moving file from {source_path} to {target_path}: {str(e)}"


@function_tool
async def generate_manifest_file(manifest_data_json: str, output_directory: str) -> str:
    """
    Creates the manifest.json file in the specified output directory
    based on the provided JSON data string. Attempts to extract a valid JSON object
    from the input string if it's not perfectly formatted.

    Args:
        manifest_data_json: A string potentially containing JSON data for the manifest.
        output_directory: The directory where manifest.json will be saved.

    Returns:
        A success message with the path to the manifest, or an error message string.
    """
    try:
        output_dir_path = Path(output_directory)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        manifest_file_path = output_dir_path / "manifest.json"

        # Attempt to extract a valid JSON object from the string
        # This handles cases where the LLM might add leading/trailing text or markdown
        content_to_parse = manifest_data_json.strip()

        # Remove markdown code block fences if present
        if content_to_parse.startswith("```json"):
            content_to_parse = content_to_parse[len("```json") :]
            if content_to_parse.endswith("```"):
                content_to_parse = content_to_parse[: -len("```")]
            content_to_parse = content_to_parse.strip()
        elif content_to_parse.startswith("```"):
            content_to_parse = content_to_parse[len("```") :]
            if content_to_parse.endswith("```"):
                content_to_parse = content_to_parse[: -len("```")]
            content_to_parse = content_to_parse.strip()

        # Find the first '{' or '[' to identify the start of a JSON structure
        first_char_index = -1
        first_brace_index = content_to_parse.find("{")
        first_bracket_index = content_to_parse.find("[")

        if first_brace_index != -1 and first_bracket_index != -1:
            first_char_index = min(first_brace_index, first_bracket_index)
        elif first_brace_index != -1:
            first_char_index = first_brace_index
        elif first_bracket_index != -1:
            first_char_index = first_bracket_index

        if first_char_index != -1:
            json_string_to_decode = content_to_parse[first_char_index:]
            # Use raw_decode to parse the first valid JSON object and ignore trailing data
            decoder = json.JSONDecoder()
            parsed_data, _ = decoder.raw_decode(json_string_to_decode)
        else:
            # If no JSON start character is found, this will likely fail, but try anyway
            parsed_data = json.loads(content_to_parse)

        with open(manifest_file_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=2)
        return f"Manifest generated successfully at {str(manifest_file_path)}"
    except json.JSONDecodeError as e:
        # Log the original input string for better debugging if raw_decode also fails
        # or if the initial content_to_parse was problematic before slicing.
        return f"Error decoding manifest_data_json: {str(e)}. Processed string (first 200 chars): '{content_to_parse[:200]}...'. Original input (first 200 chars): '{manifest_data_json[:200]}...'"
    except Exception as e:
        return f"Error generating manifest file at {output_directory}/manifest.json: {str(e)}"


# Further tool implementations will follow in subsequent steps.
