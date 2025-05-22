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
from scipy import signal  # Added for filtering

from phonosyne import settings
from phonosyne.agents.schemas import AnalyzerOutput  # For spec type hint

logger = logging.getLogger(__name__)


class ValidationFailedError(Exception):
    """Custom exception for WAV validation failures."""

    pass


def validate_wav(file_path: Path, effect_name: str, duration: float) -> bool:
    """
    Validates a .wav file against specified criteria.

    Args:
        file_path: Path to the .wav file.
        effect_name: The name of the effect to validate.
        duration: The target duration of the sound in seconds.

    Returns:
        True if validation passes.

    Raises:
        ValidationFailedError: If any validation check fails.
        FileNotFoundError: If the .wav file does not exist.
    """
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"WAV file not found at: {file_path}")

    errors = []

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
    # So, `sample_rate` should be the target.
    expected_sr = settings.DEFAULT_SR
    if info.samplerate != expected_sr:
        errors.append(
            f"Sample rate mismatch: expected {expected_sr}, got {info.samplerate}."
        )

    # 2. Check Duration
    # duration is the target duration from AnalyzerOutput
    expected_duration = duration
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

    # Read audio data once for subsequent checks (Peak and Silence)
    audio_data_mono = None
    try:
        # Read the raw audio data
        raw_audio_data, read_sr = sf.read(file_path, dtype="float32", always_2d=False)
        # Note: sf.read by default gives sr of file, which we already have in info.samplerate

        # Ensure it's mono for peak and silence checks
        if raw_audio_data.ndim > 1:
            if raw_audio_data.shape[1] == 1:  # Already mono but in 2D array
                audio_data_mono = raw_audio_data[:, 0]
            else:  # Actual stereo or multi-channel
                # This case should ideally be caught by the channel check earlier if spec is mono.
                # If it reaches here and is multi-channel, it's an unexpected state.
                # For robustness in calculation, we'll average to mono.
                # A warning/error about unexpected channels might be better if spec is strictly mono.
                logger.debug(
                    f"Audio data for {file_path} has {raw_audio_data.shape[1]} channels; averaging to mono for peak/silence check."
                )
                audio_data_mono = np.mean(raw_audio_data, axis=1)
        else:
            audio_data_mono = raw_audio_data

    except Exception as e:
        msg = f"Could not read audio data from {file_path} for peak/silence checks: {e}"
        logger.error(msg)
        errors.append(msg)
        # If audio can't be read, peak and silence checks below will be skipped if they depend on audio_data_mono

    # 5. Check Peak Level
    # Technical spec: "Peak level <= -1 dBFS"
    # settings.TARGET_PEAK_DBFS = -1.0
    if audio_data_mono is not None:  # Only proceed if audio was read successfully
        try:
            peak_linear = np.max(np.abs(audio_data_mono))
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
            msg = f"Error during peak check for {file_path}: {e}"
            logger.error(msg)
            errors.append(msg)

    # 6. Check for Silence
    # Use a small threshold to define silence.
    # This value means that the loudest sample is quieter than -100dBFS.
    if audio_data_mono is not None:  # Only proceed if audio was read successfully
        try:
            # --- BEGIN AUDIO FILTERING FOR SILENCE CHECK ---
            audio_for_silence_check = audio_data_mono.copy()  # Work on a copy

            # Configuration for filtering (consider moving to settings.py)
            APPLY_BANDPASS_FILTER_FOR_SILENCE = True  # Set to False to disable
            FILTER_LOW_CUT_HZ = 20.0
            FILTER_HIGH_CUT_HZ = 20000.0
            FILTER_ORDER = 4

            if APPLY_BANDPASS_FILTER_FOR_SILENCE and audio_for_silence_check.size > 0:
                if not np.issubdtype(audio_for_silence_check.dtype, np.floating):
                    logger.debug(
                        f"Audio data for silence check dtype is {audio_for_silence_check.dtype}. Converting to float32."
                    )
                    audio_for_silence_check = audio_for_silence_check.astype(np.float32)

                current_sample_rate = (
                    info.samplerate
                )  # Use the actual sample rate of the file
                nyquist = 0.5 * current_sample_rate
                low_norm = FILTER_LOW_CUT_HZ / nyquist
                high_norm = FILTER_HIGH_CUT_HZ / nyquist

                if high_norm >= 1.0:
                    high_norm = 0.999
                if low_norm <= 0.0:
                    low_norm = 0.00001

                if low_norm < high_norm:
                    # Check minimum length for sosfiltfilt
                    # Default padlen for sosfiltfilt is 3 * (sos.shape[1] // 2 - 1) = 6 for a typical 6-column SOS array.
                    # Signal length must be > padlen.
                    min_len_for_filter = 3 * FILTER_ORDER  # Conservative estimate
                    if len(audio_for_silence_check) > min_len_for_filter:
                        try:
                            sos = signal.butter(
                                FILTER_ORDER,
                                [low_norm, high_norm],
                                btype="bandpass",
                                output="sos",
                            )
                            audio_for_silence_check = signal.sosfiltfilt(
                                sos, audio_for_silence_check
                            )
                            logger.debug(
                                f"Applied band-pass filter ({FILTER_LOW_CUT_HZ}Hz - {FILTER_HIGH_CUT_HZ}Hz) "
                                f"to audio data for silence check."
                            )
                        except Exception as e_filter:
                            logger.warning(
                                f"Error applying band-pass filter for silence check: {e_filter}. Proceeding with unfiltered audio for silence check."
                            )
                    else:
                        logger.debug(
                            f"Audio data length {len(audio_for_silence_check)} too short for filtering (min_len ~{min_len_for_filter}). Skipping filter for silence check."
                        )
                else:
                    logger.debug(
                        f"Invalid filter cutoffs for silence check (low_norm: {low_norm:.4f}, high_norm: {high_norm:.4f}). Skipping filter."
                    )
            # --- END AUDIO FILTERING FOR SILENCE CHECK ---

            if (
                np.max(np.abs(audio_for_silence_check))
                < settings.SILENCE_THRESHOLD_LINEAR
            ):
                errors.append(
                    f"Audio content is effectively silent (peak < {settings.SILENCE_THRESHOLD_LINEAR:.0e} linear, after attempting to filter for check)."
                )
        except Exception as e:
            # Changed error message to be more specific to silence check
            msg = f"Error during silence check for {file_path}: {e}"
            logger.error(msg)
            errors.append(msg)

    if errors:
        full_error_message = (
            f"WAV file validation failed for {file_path}:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
        logger.warning(full_error_message)
        raise ValidationFailedError(full_error_message)

    logger.info(
        f"WAV file {file_path} passed all validation checks against spec for '{effect_name}'."
    )
    return True
