import numpy as np

from phonosyne import settings

from .delay import apply_delay  # Assuming delay can be a building block


def apply_long_reverb(
    audio_data: np.ndarray,
    decay_time_s: float = 2.0,
    mix: float = 0.4,
    diffusion: float = 0.7,
) -> tuple[np.ndarray, int]:
    """
    Applies a simple long reverb effect.
    This uses multiple delays with feedback, attempting a more spacious sound.
    A more advanced reverb would use Schroeder reverberators (comb + all-pass filters).

    Args:
        audio_data: NumPy array of the input audio.
        decay_time_s: Approximate decay time for the reverb.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        diffusion: Controls the 'smearing' of reflections (0.0 to 1.0). Higher values mean more diffusion.

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")
    if not 0.0 <= diffusion <= 1.0:
        raise ValueError("Diffusion must be between 0.0 and 1.0.")

    # Prime numbers are good for delay lengths to avoid correlated reflections
    # These are scaled by decay_time_s and sample_rate
    # For a long reverb, we want longer base delay times.
    base_delay_ratios = [
        0.0297,
        0.0371,
        0.0411,
        0.0437,
        0.0533,
        0.0677,
    ]  # Primes scaled down

    delay_times_s = [
        ratio * decay_time_s * (1 + (np.random.rand() - 0.5) * 0.1 * diffusion)
        for ratio in base_delay_ratios
    ]
    feedbacks = [
        0.6 + 0.2 * diffusion + (np.random.rand() - 0.5) * 0.1
        for _ in base_delay_ratios
    ]  # Add some randomness

    wet_signal = np.zeros_like(audio_data, dtype=np.float64)

    # Apply multiple delays. This is a simplified approach.
    # A real reverb would have a more complex network of delays and filters.
    for i, dt_s in enumerate(delay_times_s):
        if dt_s > 0:
            # Ensure feedback is less than 1 to avoid infinite gain
            current_feedback = min(feedbacks[i], 0.95)

            # Apply some light filtering (e.g., damping high frequencies in feedback) for a more natural reverb tail
            # This is a placeholder; a proper filter would be more involved.
            # For now, we'll just use the delay as is.
            delayed_component, _ = apply_delay(
                audio_data,
                settings.DEFAULT_SR,
                dt_s,
                feedback=current_feedback,
                mix=1.0,
            )

            # Pan the delayed components slightly for stereo width if stereo input
            if audio_data.ndim == 2 and audio_data.shape[1] == 2:
                pan = np.random.rand()  # 0 for left, 1 for right
                if i % 2 == 0:  # Even taps lean left
                    delayed_component[:, 0] *= 1 - pan * 0.5
                    delayed_component[:, 1] *= pan * 0.5
                else:  # Odd taps lean right
                    delayed_component[:, 0] *= pan * 0.5
                    delayed_component[:, 1] *= 1 - pan * 0.5

            wet_signal += delayed_component

    # Normalize the summed wet signal to avoid clipping, then scale by number of taps
    if np.max(np.abs(wet_signal)) > 0:
        wet_signal /= np.max(np.abs(wet_signal))  # Normalize to [-1, 1]
    wet_signal *= 1.0 / np.sqrt(
        len(delay_times_s)
    )  # Attenuate based on number of taps to manage energy

    processed_audio = audio_data * (1 - mix) + wet_signal * mix

    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype)
