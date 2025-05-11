import numpy as np


def apply_distortion(
    audio_data: np.ndarray, sample_rate: int, drive: float = 0.5, mix: float = 1.0
) -> tuple[np.ndarray, int]:
    """
    Applies a simple distortion effect using hard clipping.

    Args:
        audio_data: NumPy array of the input audio.
        sample_rate: Sample rate of the audio in Hz.
        drive: Amount of distortion (0.0 to 1.0). Higher values increase clipping.
               This will scale the input signal before clipping.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= drive <= 1.0:
        raise ValueError("Drive must be between 0.0 and 1.0.")
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data, sample_rate

    original_dtype = audio_data.dtype
    audio_float = audio_data.astype(np.float64)

    # Apply drive: scale the signal. Max gain of 1 + 9 = 10x for drive=1
    # Drive affects how much of the signal exceeds the clipping threshold.
    gain = 1 + drive * 9.0
    driven_audio = audio_float * gain

    # Hard clipping
    # Threshold is typically +/- 1.0 for normalized audio.
    # A more controllable threshold could be added.
    # For simplicity, let's assume a fixed clipping threshold, e.g. 0.8
    threshold = 0.8
    clipped_audio = np.clip(driven_audio, -threshold, threshold)

    # Scale back down if we used a threshold other than 1.0 to somewhat preserve level
    # Or, often distortion makes things louder, so makeup gain is part of the effect.
    # For this simple version, let's not scale down, allowing it to get louder.

    # Mix dry and wet
    processed_audio = audio_float * (1 - mix) + clipped_audio * mix

    if np.issubdtype(original_dtype, np.integer):
        # Ensure clipping for integer types if mix is not 1.0 or if original was not full scale
        max_val = np.iinfo(original_dtype).max
        min_val = np.iinfo(original_dtype).min
        processed_audio = np.clip(processed_audio, min_val, max_val)
    else:
        # For float, ensure it's still within -1 to 1 if it's the final output stage
        # However, individual effects might output values outside -1 to 1,
        # expecting later normalization. For now, let's clip to -1,1 for float too.
        processed_audio = np.clip(processed_audio, -1.0, 1.0)

    return processed_audio.astype(original_dtype), sample_rate
