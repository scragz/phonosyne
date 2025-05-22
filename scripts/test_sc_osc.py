import asyncio
import logging
import os
import sys
from pathlib import Path

# Add phonosyne root to sys.path to allow importing phonosyne modules
PHONOSYNE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PHONOSYNE_ROOT))

try:
    from phonosyne import (
        settings,  # To ensure settings are loaded if exec_env relies on them
    )
    from phonosyne.utils.exec_env import CodeExecutionError, run_supercollider_code
except ImportError as e:
    print(f"Error importing Phonosyne modules: {e}")
    print("Make sure Phonosyne is installed or PHONOSYNE_ROOT is correctly set.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("test_sc_osc")

# --- Configuration ---
# Path to the SuperCollider script designed for OSC control
SCD_FILE_PATH = PHONOSYNE_ROOT / "scripts" / "test.sc"

# Output directory and filename for the WAV file
OUTPUT_DIR = PHONOSYNE_ROOT / "output" / "osc_tests"
OUTPUT_WAV_FILENAME = "test_osc_output.wav"
ABSOLUTE_OUTPUT_WAV_PATH = OUTPUT_DIR / OUTPUT_WAV_FILENAME

# Recipe duration for the test
duration = 8.0  # Shorter for testing

# Paths to SuperCollider executables (adjust if not in PATH)
# On macOS, these are typically in /Applications/SuperCollider.app/Contents/MacOS/
SCLANG_PATH = "sclang"  # Or "/Applications/SuperCollider.app/Contents/MacOS/sclang"
SCSYNTH_PATH = "scsynth"  # Or "/Applications/SuperCollider.app/Contents/MacOS/scsynth"


def main():
    logger.info("Starting OSC SuperCollider test...")

    if not SCD_FILE_PATH.exists():
        logger.error(f"SuperCollider script not found: {SCD_FILE_PATH}")
        return

    try:
        with open(SCD_FILE_PATH, "r", encoding="utf-8") as f:
            sc_code_content = f.read()
    except IOError as e:
        logger.error(f"Error reading SuperCollider script {SCD_FILE_PATH}: {e}")
        return

    # Ensure output directory exists
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured output directory exists: {OUTPUT_DIR}")
    except OSError as e:
        logger.error(f"Could not create output directory {OUTPUT_DIR}: {e}")
        return

    logger.info(f"Attempting to generate WAV file: {ABSOLUTE_OUTPUT_WAV_PATH}")
    logger.info(f"Using SuperCollider script: {SCD_FILE_PATH}")
    logger.info(f"Recipe duration: {duration} seconds")

    # Set some default settings values if not present, for testing standalone
    if not hasattr(settings, "SCLANG_SETUP_TIMEOUT_SECONDS"):
        logger.warning(
            "SCLANG_SETUP_TIMEOUT_SECONDS not in settings, using default 30s for test."
        )
        settings.SCLANG_SETUP_TIMEOUT_SECONDS = 30.0
    if not hasattr(settings, "SCLANG_TIMEOUT_BUFFER_SECONDS"):
        logger.warning(
            "SCLANG_TIMEOUT_BUFFER_SECONDS not in settings, using default 30s for test."
        )
        settings.SCLANG_TIMEOUT_BUFFER_SECONDS = 30.0
    if not hasattr(settings, "SCLANG_STOP_PROCESSING_TIME_SECONDS"):
        logger.warning(
            "SCLANG_STOP_PROCESSING_TIME_SECONDS not in settings, using default 5s for test."
        )
        settings.SCLANG_STOP_PROCESSING_TIME_SECONDS = 5.0

    try:
        generated_wav_path = run_supercollider_code(
            code=sc_code_content,
            output_filename=str(ABSOLUTE_OUTPUT_WAV_PATH),
            duration=duration,
            effect_name="osc_test_effect",
            sclang_executable_path=SCLANG_PATH,
            scsynth_executable_path=SCSYNTH_PATH,
        )
        logger.info(f"SUCCESS! Generated WAV file: {generated_wav_path}")
        if generated_wav_path.exists():
            logger.info(f"File size: {generated_wav_path.stat().st_size} bytes")
        else:
            logger.error("File path returned but file does not exist.")

    except CodeExecutionError as e:
        logger.error(
            f"CodeExecutionError during SuperCollider execution: {e}", exc_info=True
        )
    except ImportError as e:  # Should have been caught earlier, but good to have
        logger.error(f"ImportError: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    # This is a simple synchronous test. If run_supercollider_code becomes async,
    # this would need to be adapted (e.g., using asyncio.run()).
    main()
