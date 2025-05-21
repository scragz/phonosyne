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

from phonosyne import settings as app_settings

# Import Pydantic models from existing schemas
from phonosyne.agents.schemas import (  # Add other schemas as they become necessary for tool inputs/outputs
    AnalyzerOutput,
    DesignerOutput,
    SampleStub,
)

# Import specific utilities needed for the tools
from phonosyne.utils.exec_env import CodeExecutionError
from phonosyne.utils.exec_env import (
    run_supercollider_code as existing_run_supercollider_code,
)

logger = logging.getLogger(__name__)  # Added

# Determine Project Root and Output Directory for executed code
EXEC_ENV_OUTPUT_DIR = Path(app_settings.DEFAULT_OUT_DIR).resolve() / "exec_env_output"
logger.info(f"Execution environment output directory set to: {EXEC_ENV_OUTPUT_DIR}")


@function_tool
async def run_supercollider_code(
    code: str,
    output_filename: str,  # This is absolute path as per updated prompt
    effect_name: str,
    recipe_duration: float,
) -> str:
    """
    Executes a SuperCollider script and saves the output .wav file.
    The SC script itself is responsible for audio generation and saving.
    This tool facilitates the execution using sclang.

    Args:
        code: The SuperCollider code string.
        output_filename: Absolute path for the output .wav file. The SC script
                         must write to this exact path.
        effect_name: The name of the effect, for context.
        recipe_duration: The target duration of the sound in seconds.

    Returns:
        Absolute path to the .wav file on success, or an error message string.
    """
    logger.info(
        f"run_supercollider_code_tool: output_filename='{output_filename}', effect_name='{effect_name}', duration='{recipe_duration}'"
    )
    code_to_log = code[:500] + "..." if len(code) > 500 else code
    logger.debug(f"Code (first 500 chars):\n{code_to_log}")

    try:
        # existing_run_supercollider_code is synchronous.
        # The agents SDK's @function_tool and runner should handle
        # running this in a way that doesn't block the event loop (e.g. thread pool).
        wav_path_obj = existing_run_supercollider_code(
            code=code,
            output_filename=output_filename,  # This is the absolute path
            recipe_duration=recipe_duration,
            effect_name=effect_name,
            # sclang_path will use its default from existing_run_supercollider_code
        )
        logger.info(
            f"run_supercollider_code_tool successfully produced: {wav_path_obj}"
        )
        return str(wav_path_obj)
    except CodeExecutionError as e:  # Make sure CodeExecutionError is imported
        err_msg = f"CodeExecutionError from existing_run_supercollider_code: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
    except (
        FileNotFoundError
    ) as e:  # Specific error from existing_run_supercollider_code
        err_msg = f"FileNotFoundError (e.g., sclang not found) from existing_run_supercollider_code: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
    except Exception as e:
        err_msg = f"Unexpected error in run_supercollider_code_tool: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg


# Import specific utilities needed for the AudioValidationTool
from phonosyne.dsp.validators import (
    ValidationFailedError,
)
from phonosyne.dsp.validators import validate_wav as existing_validate_wav


@function_tool
async def validate_audio_file(file_path: str, recipe_json: str) -> str:
    """
    Validates a generated .wav file against technical specifications.

    Args:
        file_path: Path to the temporary .wav file to validate.
        recipe_json: A JSON string of the AnalyzerOutput schema containing target specifications
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

        spec_dict = json.loads(recipe_json)
        # AnalyzerOutput is already imported at the top of the file
        analyzer_spec = AnalyzerOutput(**spec_dict)

        # existing_validate_wav is synchronous. Assuming openai-agents SDK handles this.
        existing_validate_wav(file_path=abs_file_path, spec=analyzer_spec)
        print(f"Audio file at {abs_file_path} successfully validated")
        return "Validation successful"
    except ValidationFailedError as e:
        return f"ValidationFailedError: {str(e)}"
    except json.JSONDecodeError as e:
        return f"JSONDecodeError for recipe_json: {str(e)}"
    except Exception as e:
        return f"Unexpected error during audio validation: {str(e)}"


@function_tool
async def move_file(source_path: str, target_path: str) -> str:
    """
    Moves a file from a source path to a target path.
    Creates the target directory if it doesn't exist.
    The source_path MUST be an absolute path to an existing file.

    Args:
        source_path: The absolute path of the file to move.
        target_path: The absolute destination path for the file.

    Returns:
        A success message with the target path, or an error message string.
    """
    try:
        # Ensure paths are absolute. If not, resolve them.
        # Path.resolve() will make a relative path absolute from the current working directory.
        # If the path is already absolute, resolve() will normalize it (e.g., remove '..').
        source = Path(source_path)
        if not source.is_absolute():
            logger.warning(
                f"move_file: Received relative source_path '{source_path}'. Resolving it to an absolute path."
            )
            source = source.resolve()

        target = Path(target_path)
        if not target.is_absolute():
            logger.warning(
                f"move_file: Received relative target_path '{target_path}'. Resolving it to an absolute path."
            )
            target = target.resolve()

        logger.info(f"Attempting to move file from (resolved absolute): {source}")
        logger.info(f"Attempting to move file to   (resolved absolute): {target}")

        # Critical Check: Source file must exist and be a file.
        if not source.exists():
            return f"Error: Source file does not exist at the specified absolute path: {source} (original input: '{source_path}')"
        if not source.is_file():
            return f"Error: Source path is not a file: {source} (original input: '{source_path}')"

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
