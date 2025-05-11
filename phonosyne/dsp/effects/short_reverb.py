import numpy as np

from phonosyne import settings

from .delay import apply_delay  # Assuming delay can be a building block


def apply_short_reverb(
    audio_data: np.ndarray,
    decay_time_s: float = 0.2,
    mix: float = 0.3,
) -> np.ndarray:
    """
    Applies a simple short reverb effect.
    This is a very basic implementation, often using multiple short delays (comb filters) and all-pass filters.
    For simplicity, this example might use a few instances of the delay effect.

    Args:
        audio_data: NumPy array of the input audio.
        decay_time_s: Approximate decay time for the reverb.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    # Parameters for a simple multi-tap delay reverb-like effect
    delay_times = [
        decay_time_s * 0.05,
        decay_time_s * 0.07,
        decay_time_s * 0.09,
        decay_time_s * 0.11,
    ]
    feedbacks = [0.25, 0.2, 0.15, 0.1]

    wet_signal = np.zeros_like(audio_data, dtype=np.float64)

    # Apply multiple delays in parallel and sum them
    # This is a highly simplified reverb (more like a multi-tap echo)
    for i, dt in enumerate(delay_times):
        if dt > 0:
            # Corrected call to apply_delay: removed sample_rate, dt is delay_time_s
            delayed_component = apply_delay(
                audio_data, dt, feedback=feedbacks[i], mix=1.0
            )  # full wet for component
            wet_signal += delayed_component * (1.0 / len(delay_times))  # Mix components

    # Normalize wet signal to prevent clipping if summing causes overflow, though unlikely with these params
    if np.max(np.abs(wet_signal)) > 1.0:
        wet_signal /= np.max(np.abs(wet_signal))

    processed_audio = audio_data * (1 - mix) + wet_signal * mix

    # Ensure output dtype matches input
    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype)
