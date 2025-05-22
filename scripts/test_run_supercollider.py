import logging
import os
import shutil
import sys
from pathlib import Path

# Adjust path to import from phonosyne if necessary
# This assumes the script is run from the root of the phonosyne project
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from phonosyne import settings
    from phonosyne.utils.exec_env import CodeExecutionError, run_supercollider_code

    SCLANG_EXEC_PATH = getattr(settings, "SCLANG_PATH", "sclang")
except ImportError as e:
    print(
        f"Could not import phonosyne modules: {e}. Ensure phonosyne is installed or PYTHONPATH is set correctly."
    )
    print(
        "Defaulting SCLANG_PATH to 'sclang'. run_supercollider_code might not be available."
    )

    # Provide dummy implementations if phonosyne is not available, so script can be outlined
    class CodeExecutionError(Exception):
        pass

    def run_supercollider_code(
        code, output_filename, duration, effect_name, sclang_path
    ):
        raise NotImplementedError(
            "phonosyne.utils.exec_env.run_supercollider_code is not available"
        )

    SCLANG_EXEC_PATH = "sclang"


# Configure basic logging for the test script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_run_supercollider")
# Reduce verbosity of other loggers if they are pulled in
logging.getLogger("phonosyne.utils.exec_env").setLevel(logging.INFO)


def main():
    logger.info("Starting SuperCollider execution test script.")

    base_dir = Path(__file__).resolve().parent.parent
    test_output_dir = base_dir / "output" / "test_sc_output"

    # Clean up previous test output if it exists
    if test_output_dir.exists():
        logger.info(f"Removing previous test output directory: {test_output_dir}")
        try:
            shutil.rmtree(test_output_dir)
        except OSError as e:
            logger.error(f"Could not remove directory {test_output_dir}: {e}")
            # Decide if this is fatal or if we can try to continue
            # For a test script, it might be okay to try, or exit.
            # Let's try to continue, mkdir will fail if it's still problematic.

    try:
        test_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured test output directory exists: {test_output_dir}")
    except OSError as e:
        logger.error(
            f"Could not create test output directory {test_output_dir}: {e}. Exiting."
        )
        return

    output_filename = test_output_dir / "test_sound.wav"
    duration = 1.5  # seconds

    absolute_output_filename = str(output_filename.resolve())
    sc_output_path_str_for_sc = Path(absolute_output_filename).as_posix()

    # Simplified SC code to test error logging
    sc_code = f"""
(
Routine {{
    "--- THIS IS A DELIBERATE TEST ERROR SENT TO STDERR ---".error;
    "This is a postln after the error.".postln;
    // Try to ensure output is flushed if possible, though .error should go to stderr
    AppClock.tick; // Process events
    SystemClock.sched(0.1, {{ "Exiting from SC script.".postln; 0.exit; nil }});
    // Keep routine alive briefly to allow exit command to be processed
    1.wait;
}}.play;
)
    """
    logger.info(f"Attempting to generate sound: {absolute_output_filename}")
    logger.info(f"Recipe duration: {duration}s")
    logger.info(f"Using sclang path: {SCLANG_EXEC_PATH}")
    # logger.debug(f"SuperCollider code to be executed:\\n{sc_code}")

    if not callable(run_supercollider_code):
        logger.error(
            "run_supercollider_code is not available (likely due to import errors). Cannot run test."
        )
        return

    try:
        generated_wav_path = run_supercollider_code(
            code=sc_code,
            output_filename=absolute_output_filename,
            duration=duration,  # This duration is for timeout calculation
            effect_name="test_effect_run_sc",
            sclang_path=SCLANG_EXEC_PATH,
        )
        logger.info(f"run_supercollider_code call completed.")
        logger.info(f"Expected WAV file at: {generated_wav_path}")

        if generated_wav_path.exists() and generated_wav_path.stat().st_size > 0:
            logger.info(
                f"Test PASSED: WAV file '{generated_wav_path}' exists and is not empty (size: {generated_wav_path.stat().st_size} bytes)."
            )
        elif not generated_wav_path.exists():
            logger.error(
                f"Test FAILED: WAV file '{generated_wav_path}' does not exist."
            )
        else:  # Exists but is empty
            logger.error(
                f"Test FAILED: WAV file '{generated_wav_path}' exists but is empty (size: {generated_wav_path.stat().st_size} bytes)."
            )

    except CodeExecutionError as e:
        logger.error(
            f"SuperCollider code execution failed: {e}", exc_info=False
        )  # exc_info=False as error from SC is already formatted
        logger.error("Test FAILED due to CodeExecutionError.")
    except Exception as e:
        logger.error(
            f"An unexpected Python error occurred during the test: {e}", exc_info=True
        )
        logger.error("Test FAILED due to unexpected Python error.")


if __name__ == "__main__":
    main()
