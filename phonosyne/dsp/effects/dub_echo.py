import numpy as np

from phonosyne import settings  # Added import

from .delay import apply_delay


# A simple low-pass filter for the feedback path, can be expanded
def _simple_lowpass_filter(
    audio_data: np.ndarray, cutoff_freq_normalized: float
) -> np.ndarray:
    """
    A very basic IIR low-pass filter (single pole).
    cutoff_freq_normalized is fc / (fs/2).
    """
    # For simplicity, we'll use a weighted average. This is not a proper filter design.
    # A more robust implementation would use scipy.signal.lfilter or similar.
    # This is a placeholder for a more sophisticated filter if needed.
    if audio_data.ndim == 0 or audio_data.size == 0:
        return audio_data

    filtered_data = np.copy(audio_data)
    # alpha = cutoff_freq_normalized # This is not how alpha is typically derived for an IIR
    # A common simple IIR lowpass: y[n] = alpha * x[n] + (1-alpha) * y[n-1]
    # For this example, let's just slightly attenuate, as a proper filter is more complex.
    # A real dub echo would have a more pronounced filter.
    # This is a conceptual placeholder for filtering in the feedback loop.
    # For now, let's just return the data, or apply a very mild fixed smoothing.
    # To actually implement a filter in the feedback loop of apply_delay would require modifying apply_delay
    # or creating a version of it that accepts a filter function for the feedback path.

    # Given the current apply_delay, we can't easily insert a filter into its feedback loop directly.
    # A true dub echo often has the filter *inside* the feedback loop.
    # What we can do here is simulate it by filtering the *output* of the delay before mixing,
    # or by creating a custom delay loop here.

    # For now, let's assume the apply_delay is the primary tool and we are characterizing its use.
    # A more advanced dub echo would require a dedicated delay implementation with feedback path filtering.
    return filtered_data


def apply_dub_echo(
    audio_data: np.ndarray,
    echo_time_s: float = 0.7,
    feedback: float = 0.65,
    mix: float = 0.6,
    damping_factor: float = 0.3,
) -> np.ndarray:  # Changed return type
    """
    Applies a dub-style echo effect.
    Characterized by significant feedback and often a damping of high frequencies in the echoes.
    This implementation uses the existing delay and simulates damping by filtering the wet signal slightly.
    A more authentic dub echo would filter within the feedback loop.

    Args:
        audio_data: NumPy array of the input audio.
        echo_time_s: Time for each echo repetition in seconds.
        feedback: Feedback gain (0.0 to <1.0).
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        damping_factor: How much to damp high frequencies in echoes (0.0 no damping, 1.0 max damping).
                        This is a conceptual parameter for this simplified version.

    Returns:
        The processed audio data (NumPy array). # Changed return type in docstring
    """
    if not 0.0 <= damping_factor <= 1.0:
        raise ValueError("Damping factor must be between 0.0 and 1.0.")

    # Get the full wet signal from the delay
    # apply_delay will now use settings.DEFAULT_SR internally and return only the array
    wet_signal = apply_delay(  # Removed sample_rate, updated return handling
        audio_data, delay_time_s=echo_time_s, feedback=feedback, mix=1.0
    )

    # Simulate damping - this is a very crude way.
    # A proper way involves filtering in the feedback path of the delay itself.
    # Here, we just apply a simple smoothing to the overall wet signal as a proxy.
    if damping_factor > 0 and wet_signal.size > 1:
        # This is a placeholder for a more sophisticated filter.
        # For example, a simple moving average or a proper low-pass filter.
        # Let's try a very simple smoothing by averaging with a slightly delayed version.
        # This is not a standard filter but will have a mild low-pass effect.
        damped_wet_signal = np.copy(wet_signal)
        if wet_signal.ndim == 1:
            rolled_signal = np.roll(wet_signal, 1)
            rolled_signal[0] = wet_signal[0]  # Avoid wrapping the first element
            damped_wet_signal = wet_signal * (
                1 - damping_factor * 0.5
            ) + rolled_signal * (damping_factor * 0.5)
        elif wet_signal.ndim == 2:
            for ch in range(wet_signal.shape[1]):
                rolled_signal_ch = np.roll(wet_signal[:, ch], 1)
                if wet_signal.shape[0] > 0:  # Ensure not empty before assignment
                    rolled_signal_ch[0] = wet_signal[0, ch]
                damped_wet_signal[:, ch] = wet_signal[:, ch] * (
                    1 - damping_factor * 0.5
                ) + rolled_signal_ch * (damping_factor * 0.5)
        wet_signal = damped_wet_signal

    # Mix dry and (damped) wet signal
    processed_audio = audio_data * (1 - mix) + wet_signal * mix

    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype)  # Changed return
