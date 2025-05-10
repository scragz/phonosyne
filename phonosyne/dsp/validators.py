"""
Audio File Validators for Phonosyne

This module provides functions to validate generated .wav files against
the project's technical specifications.

Key features:
- `validate_wav`: Checks a .wav file for:
  - Correct sample rate (from settings).
  - Duration within a specified tolerance (from settings).
  - Correct bit depth (32-bit float, from settings).
  - Peak audio level below a threshold (from settings).
  - Mono channel.

@dependencies
- `pathlib.Path` for file path operations.
- `soundfile` for reading .wav file metadata and audio data.
- `numpy` for numerical operations on audio data (e.g., finding peak).
- `phonosyne.settings` for accessing global configuration like default sample rate,
  duration tolerance, target peak dBFS, and bit depth.
- `phonosyne.agents.schemas.AnalyzerOutput` for type hinting the specification.
- `logging` for logging validation results.

@notes
- This validator is used by the `CompilerAgent` (or the orchestrator calling it)
  to ensure generated audio meets requirements.
- If validation fails, it should raise a specific exception that the
  `CompilerAgent` can use to inform its repair attempts.
"""

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from phonosyne import settings
from phonosyne.agents.schemas import AnalyzerOutput  # For spec type hint

logger = logging.getLogger(__name__)


class ValidationFailedError(Exception):
    """Custom exception for WAV validation failures."""

    pass


def validate_wav(file_path: Path, spec: AnalyzerOutput) -> bool:
    """
    Validates a .wav file against specified criteria.

    Args:
        file_path: Path to the .wav file.
        spec: An AnalyzerOutput object containing the target specifications
              (primarily duration and sample rate from the recipe).

    Returns:
        True if validation passes.

    Raises:
        ValidationFailedError: If any validation check fails.
        FileNotFoundError: If the .wav file does not exist.
    """
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"WAV file not found at: {file_path}")

    try:
        info = sf.info(file_path)
    except Exception as e:
        msg = f"Could not read WAV file info from {file_path}: {e}"
        logger.error(msg)
        raise ValidationFailedError(msg) from e

    errors = []

    # 1. Check Sample Rate
    # The spec for validate_wav says "SR, duration +-0.5s, bit-depth, peak checks"
    # The AnalyzerOutput schema has `sample_rate` which defaults to settings.DEFAULT_SR
    # So, `spec.sample_rate` should be the target.
    expected_sr = spec.sample_rate
    if info.samplerate != expected_sr:
        errors.append(
            f"Sample rate mismatch: expected {expected_sr}, got {info.samplerate}."
        )

    # 2. Check Duration
    # spec.duration is the target duration from AnalyzerOutput
    expected_duration = spec.duration
    duration_tolerance = settings.DURATION_TOLERANCE_S
    lower_bound = expected_duration - duration_tolerance
    upper_bound = expected_duration + duration_tolerance
    if not (lower_bound <= info.duration <= upper_bound):
        errors.append(
            f"Duration out of tolerance: expected {expected_duration:.2f}s "
            f"(±{duration_tolerance:.2f}s, range [{lower_bound:.2f}s - {upper_bound:.2f}s]), "
            f"got {info.duration:.2f}s."
        )

    # 3. Check Bit Depth (Subtype for soundfile)
    # Technical spec: "32-bit float PCM"
    # soundfile subtypes for float: 'FLOAT' (32-bit), 'DOUBLE' (64-bit)
    # settings.BIT_DEPTH is 32.
    # sf.info().format is 'WAV', sf.info().subtype is 'FLOAT' for 32-bit float.
    expected_subtype = "PCM_F"  # This is what sf.write(..., subtype='FLOAT') produces as info.subtype_info for subtype
    # Actually, sf.info().subtype gives 'FLOAT'
    if info.subtype != "FLOAT":  # Check against 'FLOAT' for 32-bit float
        errors.append(
            f"Bit depth/subtype mismatch: expected 32-bit float ('FLOAT' subtype), "
            f"got subtype '{info.subtype}' (format: {info.format}, subtype_info: {info.subtype_info})."
        )

    # 4. Check Channels (Mono)
    # Technical spec: "mono"
    if info.channels != 1:
        errors.append(
            f"Channel count mismatch: expected 1 (mono), got {info.channels}."
        )

    # 5. Check Peak Level
    # Technical spec: "Peak level <= -1 dBFS"
    # settings.TARGET_PEAK_DBFS = -1.0
    try:
        audio_data, _ = sf.read(file_path, dtype="float32")
        if audio_data.ndim > 1:  # If stereo (should have been caught by channel check)
            audio_data = np.mean(
                audio_data, axis=1
            )  # Convert to mono for peak check, though ideally it's already mono

        peak_linear = np.max(np.abs(audio_data))
        if peak_linear == 0:  # Avoid log(0)
            peak_dbfs = -np.inf
        else:
            peak_dbfs = 20 * np.log10(peak_linear)

        if peak_dbfs > settings.TARGET_PEAK_DBFS:
            errors.append(
                f"Peak level too high: got {peak_dbfs:.2f} dBFS, "
                f"expected <= {settings.TARGET_PEAK_DBFS:.2f} dBFS."
            )
    except Exception as e:
        msg = f"Could not read audio data for peak check from {file_path}: {e}"
        logger.error(msg)
        errors.append(msg)  # Add as a validation error string

    if errors:
        full_error_message = (
            f"WAV file validation failed for {file_path}:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
        logger.warning(full_error_message)
        raise ValidationFailedError(full_error_message)

    logger.info(
        f"WAV file {file_path} passed all validation checks against spec for '{spec.effect_name}'."
    )
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger.info("Testing WAV validator...")

    # Create a dummy spec for testing
    dummy_spec = AnalyzerOutput(
        effect_name="test_sound",
        duration=1.0,
        sample_rate=settings.DEFAULT_SR,  # Use from settings
        description="A test sound for validation.",
    )

    # Create a temporary directory for test WAV files
    temp_dir = Path(tempfile.mkdtemp(prefix="phonosyne_validator_test_"))

    # Test case 1: Valid WAV file
    valid_wav_path = temp_dir / "valid.wav"
    sr = dummy_spec.sample_rate
    duration = dummy_spec.duration
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Generate audio slightly below target peak
    amplitude_valid = 10 ** ((settings.TARGET_PEAK_DBFS - 0.1) / 20)
    audio_valid = amplitude_valid * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(valid_wav_path, audio_valid, sr, subtype="FLOAT")

    try:
        print(f"\n--- Validating {valid_wav_path} (should pass) ---")
        validate_wav(valid_wav_path, dummy_spec)
        print(f"Validation PASSED for {valid_wav_path}")
    except ValidationFailedError as e:
        print(f"Validation FAILED for {valid_wav_path}: {e}")
    except FileNotFoundError:
        print(f"File not found for {valid_wav_path}")

    # Test case 2: WAV with wrong sample rate
    wrong_sr_wav_path = temp_dir / "wrong_sr.wav"
    sf.write(wrong_sr_wav_path, audio_valid, sr // 2, subtype="FLOAT")
    try:
        print(f"\n--- Validating {wrong_sr_wav_path} (should fail: wrong SR) ---")
        validate_wav(wrong_sr_wav_path, dummy_spec)
        print(f"Validation PASSED for {wrong_sr_wav_path} (UNEXPECTED)")
    except ValidationFailedError as e:
        print(f"Validation FAILED for {wrong_sr_wav_path} (expected): {e}")

    # Test case 3: WAV with wrong duration (too short)
    short_duration_wav_path = temp_dir / "short_duration.wav"
    audio_short = audio_valid[: len(audio_valid) // 2]  # Half duration
    sf.write(short_duration_wav_path, audio_short, sr, subtype="FLOAT")
    # Update spec for this test if duration is part of spec, or adjust tolerance
    # dummy_spec_short = dummy_spec.copy(update={"duration": duration / 2}) # if spec changes
    try:
        print(
            f"\n--- Validating {short_duration_wav_path} (should fail: too short) ---"
        )
        # Using original dummy_spec, so duration should be 1.0s, this is 0.5s
        validate_wav(short_duration_wav_path, dummy_spec)
        print(f"Validation PASSED for {short_duration_wav_path} (UNEXPECTED)")
    except ValidationFailedError as e:
        print(f"Validation FAILED for {short_duration_wav_path} (expected): {e}")

    # Test case 4: WAV with peak too high
    high_peak_wav_path = temp_dir / "high_peak.wav"
    amplitude_invalid = 10 ** (
        (settings.TARGET_PEAK_DBFS + 0.1) / 20
    )  # 0.1 dB too loud
    audio_high_peak = amplitude_invalid * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(high_peak_wav_path, audio_high_peak, sr, subtype="FLOAT")
    try:
        print(f"\n--- Validating {high_peak_wav_path} (should fail: peak too high) ---")
        validate_wav(high_peak_wav_path, dummy_spec)
        print(f"Validation PASSED for {high_peak_wav_path} (UNEXPECTED)")
    except ValidationFailedError as e:
        print(f"Validation FAILED for {high_peak_wav_path} (expected): {e}")

    # Test case 5: Stereo WAV
    stereo_wav_path = temp_dir / "stereo.wav"
    audio_stereo = np.vstack([audio_valid, audio_valid]).T  # Make it stereo
    sf.write(stereo_wav_path, audio_stereo, sr, subtype="FLOAT")
    try:
        print(f"\n--- Validating {stereo_wav_path} (should fail: stereo) ---")
        validate_wav(stereo_wav_path, dummy_spec)
        print(f"Validation PASSED for {stereo_wav_path} (UNEXPECTED)")
    except ValidationFailedError as e:
        print(f"Validation FAILED for {stereo_wav_path} (expected): {e}")

    # Clean up temporary directory
    try:
        import shutil

        shutil.rmtree(temp_dir)
        print(f"\nCleaned up temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Error cleaning up temp dir {temp_dir}: {e}")

    print("\nValidator testing complete.")
