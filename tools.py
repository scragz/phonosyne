import json
import logging
import shutil
from pathlib import Path

from agents import function_tool

from phonosyne.utils.exec_env import (
    CodeExecutionError,
)
from phonosyne.utils.exec_env import (
    run_supercollider_code as existing_run_supercollider_code,
)

logger = logging.getLogger(__name__)


@function_tool
async def run_supercollider_code(
    code: str,
    output_filename: str,  # This is absolute path as per updated prompt
    effect_name: str,
    duration: float,
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
        duration: The target duration of the sound in seconds.

    Returns:
        Absolute path to the .wav file on success, or an error message string.
    """
    logger.info(
        f"run_supercollider_code: output_filename='{output_filename}', effect_name='{effect_name}', duration='{duration}'"
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
            duration=duration,
            effect_name=effect_name,
            # sclang_path will use its default from existing_run_supercollider_code
        )
        logger.info(f"run_supercollider_code successfully produced: {wav_path_obj}")
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
        err_msg = f"Unexpected error in run_supercollider_code: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return err_msg
