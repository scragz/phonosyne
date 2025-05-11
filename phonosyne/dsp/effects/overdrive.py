import numpy as np

from phonosyne import settings


def apply_overdrive(
    audio_data: np.ndarray,
    drive: float = 0.5,
    tone: float = 0.5,
    mix: float = 1.0,
) -> np.ndarray:
    """
    Applies a simple overdrive effect using a tanh function for soft clipping.

    Args:
        audio_data: NumPy array of the input audio.
        drive: Amount of overdrive (0.0 to 1.0). Controls the input gain to the tanh function.
        tone: Controls the brightness of the overdriven signal (0.0 dark to 1.0 bright).
              This is a very simple high-shelf filter.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        The processed audio data (NumPy array).
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
        return audio_data  # Return ndarray

    original_dtype = audio_data.dtype
    audio_float = audio_data.astype(np.float64)

    gain = 1.0 + drive * 5.0
    driven_audio = audio_float * gain
    overdriven_signal = np.tanh(driven_audio)

    if tone != 0.5 and overdriven_signal.size > 1:
        toned_signal = np.copy(overdriven_signal)
        tone_coeff = (tone - 0.5) * 0.8
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

    processed_audio = audio_float * (1.0 - mix) + overdriven_signal * mix

    if np.issubdtype(original_dtype, np.integer):
        max_val = np.iinfo(original_dtype).max
        min_val = np.iinfo(original_dtype).min
        processed_audio = np.clip(processed_audio, min_val, max_val)
    else:  # Float output
        processed_audio = np.clip(processed_audio, -1.0, 1.0)

    return processed_audio.astype(original_dtype)  # Return ndarray
