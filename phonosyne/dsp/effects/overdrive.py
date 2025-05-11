import numpy as np


def apply_overdrive(
    audio_data: np.ndarray,
    sample_rate: int,
    drive: float = 0.5,
    tone: float = 0.5,
    mix: float = 1.0,
) -> tuple[np.ndarray, int]:
    """
    Applies a simple overdrive effect using a tanh function for soft clipping.

    Args:
        audio_data: NumPy array of the input audio.
        sample_rate: Sample rate of the audio in Hz.
        drive: Amount of overdrive (0.0 to 1.0). Controls the input gain to the tanh function.
        tone: Controls the brightness of the overdriven signal (0.0 dark to 1.0 bright).
              This is a very simple high-shelf filter.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= drive <= 1.0:
        raise ValueError("Drive must be between 0.0 and 1.0.")
    if not 0.0 <= tone <= 1.0:
        raise ValueError("Tone must be between 0.0 and 1.0.")
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data, sample_rate

    original_dtype = audio_data.dtype
    # Work with float64 for processing to maintain precision
    audio_float = audio_data.astype(np.float64)

    # Apply drive: scale the signal. Max gain of 1 + 5*drive = 6x for drive=1
    # This determines how much the signal is pushed into the non-linear part of tanh
    gain = 1.0 + drive * 5.0
    driven_audio = audio_float * gain

    # Soft clipping using tanh function
    # np.tanh ranges from -1 to 1.
    overdriven_signal = np.tanh(driven_audio)

    # Simple tone control (post-distortion)
    # This is a very basic first-order high-shelf filter approximation.
    # A more sophisticated filter (e.g., from scipy.signal) would be better for a real tone stack.
    if tone != 0.5 and overdriven_signal.size > 1:
        # If tone > 0.5, boost highs. If tone < 0.5, cut highs.
        # Simple FIR filter: y[n] = x[n] + (tone - 0.5) * (x[n] - x[n-1])
        # This is a high-frequency emphasis/de-emphasis.
        toned_signal = np.copy(overdriven_signal)
        # Tone coefficient: positive for high boost, negative for high cut.
        tone_coeff = (tone - 0.5) * 0.8  # Scaled to be somewhat subtle

        if overdriven_signal.ndim == 1:
            diff = np.diff(overdriven_signal, prepend=overdriven_signal[0])
            toned_signal += tone_coeff * diff
        elif overdriven_signal.ndim == 2:
            for ch in range(overdriven_signal.shape[1]):
                diff_ch = np.diff(
                    overdriven_signal[:, ch], prepend=overdriven_signal[0, ch]
                )
                toned_signal[:, ch] += tone_coeff * diff_ch
        overdriven_signal = toned_signal
        # Normalize after tone control if it significantly boosts levels
        # max_abs = np.max(np.abs(overdriven_signal))
        # if max_abs > 1.0:
        #     overdriven_signal /= max_abs

    # Mix dry and wet
    # The output of tanh is already in [-1, 1], so direct mixing is fine.
    processed_audio = audio_float * (1.0 - mix) + overdriven_signal * mix

    # Final clipping to ensure output is within [-1, 1] for float types,
    # or within integer limits for integer types.
    if np.issubdtype(original_dtype, np.integer):
        max_val = np.iinfo(original_dtype).max
        min_val = np.iinfo(original_dtype).min
        # If original was int, scale processed_audio (which is -1 to 1 float from tanh) to int range
        # This assumes the original int audio used its full range. A better approach might be needed
        # if the input int audio was not normalized.
        # For now, let's assume the float processing result should be scaled back.
        # However, effects often change loudness. Let's clip the mixed result.
        processed_audio = np.clip(processed_audio, min_val, max_val)
    else:  # Float output
        processed_audio = np.clip(processed_audio, -1.0, 1.0)

    return processed_audio.astype(original_dtype), sample_rate
