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


@function_tool
async def execute_python_dsp_code(
    code: str, output_filename: str, recipe_json: str
) -> str:
    """
    Executes the provided Python DSP code safely and saves the output as a temporary .wav file.
    The DSP code must return a tuple: (numpy_array, sample_rate).
    The 'description' and 'duration' from the recipe_json will be available in the executed code's scope.

    Args:
        code: The Python DSP code string to execute.
        output_filename: Desired unique name for the output .wav file (e.g., "effect_attempt_1.wav").
        recipe_json: A JSON string of the synthesis recipe (AnalyzerOutput schema)
                     containing 'description' and 'duration'.

    Returns:
        Path to the generated temporary .wav file if successful, or an error message string.
    """
    try:
        recipe_data = json.loads(recipe_json)

        if not isinstance(recipe_data, dict):
            return f"Error: recipe_json did not decode to a dictionary. Decoded to: {type(recipe_data)}"

        description = recipe_data.get("description")
        duration = recipe_data.get("duration")

        if description is None or duration is None:
            missing_keys = []
            if description is None:
                missing_keys.append("'description'")
            if duration is None:
                missing_keys.append("'duration'")
            return f"Error: {', '.join(missing_keys)} missing from recipe_json."

        # existing_run_code is synchronous. The openai-agents SDK's @function_tool
        # should handle running synchronous functions in a thread pool if called from an async agent.
        # If direct async execution of run_code is required, run_code itself would need to be async
        # or wrapped with asyncio.to_thread. For now, assuming SDK handles it.

        # Sanitize output_filename to remove any leading slashes
        # to prevent it from being treated as an absolute path from root by Path.
        sanitized_output_filename = output_filename.lstrip('/')

        wav_path: Path = existing_run_code(
            code=code,
            output_filename=sanitized_output_filename, # Use sanitized version
            recipe_description=str(description),  # Ensure string type for description
            recipe_duration=float(duration),  # Ensure float type for duration
            recipe_json_str=recipe_json,  # Pass the received recipe_json string
            mode="local_executor",
        )
        return str(wav_path.resolve())
    except json.JSONDecodeError as e:
        return f"JSONDecodeError for recipe_json: {str(e)}"
    except CodeExecutionError as e:
        return f"CodeExecutionError: {str(e)}"
    except Exception as e:
        return f"Unexpected error during code execution: {str(e)}"


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
        spec_dict = json.loads(spec_json)
        # AnalyzerOutput is already imported at the top of the file
        analyzer_spec = AnalyzerOutput(**spec_dict)

        # existing_validate_wav is synchronous. Assuming openai-agents SDK handles this.
        existing_validate_wav(file_path=Path(file_path), spec=analyzer_spec)
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
        source = Path(source_path)
        target = Path(target_path)

        if not source.exists():
            return f"Error: Source file does not exist at {source_path}"
        if not source.is_file():
            return f"Error: Source path is not a file: {source_path}"

        # Ensure target directory exists
        target_parent_dir = target.parent
        if not target_parent_dir.exists():
            try:
                target_parent_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                return (
                    f"Error: Permission denied to create directory {target_parent_dir}"
                )
            except Exception as e:
                return f"Error creating target directory {target_parent_dir}: {str(e)}"
        elif not target_parent_dir.is_dir():
            return f"Error: Target parent path {target_parent_dir} exists but is not a directory."

        # Perform the move operation
        shutil.move(str(source), str(target))
        return f"File moved successfully to {str(target)}"
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
