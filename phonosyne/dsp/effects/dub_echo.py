import numpy as np

from phonosyne import settings

from .delay import apply_delay


# A simple low-pass filter for the feedback path, can be expanded
def _simple_lowpass_filter(
    audio_data: np.ndarray,
    cutoff_freq_normalized: float,
    prev_y: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    A very basic IIR low-pass filter (single pole).
    cutoff_freq_normalized is fc / (fs/2).
    A common simple IIR lowpass: y[n] = alpha * x[n] + (1-alpha) * y[n-1]
    alpha = cutoff_freq_normalized (this is a simplification, proper alpha depends on filter design)
    """
    if audio_data.ndim == 0 or audio_data.size == 0:
        return audio_data, (np.zeros_like(audio_data) if prev_y is None else prev_y)

    alpha = np.clip(
        cutoff_freq_normalized, 0.01, 0.99
    )  # Ensure alpha is in a stable range

    filtered_data = np.copy(audio_data)

    if audio_data.ndim == 1:
        if prev_y is None:
            prev_y_channel = np.zeros(1, dtype=audio_data.dtype)
        else:
            prev_y_channel = prev_y

        for i in range(len(audio_data)):
            filtered_data[i] = alpha * audio_data[i] + (1 - alpha) * prev_y_channel
            prev_y_channel = filtered_data[i]
        current_prev_y = prev_y_channel
    elif audio_data.ndim == 2:
        num_channels = audio_data.shape[1]
        if prev_y is None:
            current_prev_y = np.zeros(num_channels, dtype=audio_data.dtype)
        else:
            current_prev_y = prev_y.copy()

        for ch in range(num_channels):
            prev_y_channel = current_prev_y[ch]
            for i in range(audio_data.shape[0]):
                filtered_data[i, ch] = (
                    alpha * audio_data[i, ch] + (1 - alpha) * prev_y_channel
                )
                prev_y_channel = filtered_data[i, ch]
            current_prev_y[ch] = prev_y_channel
    else:
        # Should not happen for typical audio
        return audio_data, (np.zeros_like(audio_data) if prev_y is None else prev_y)

    return filtered_data, current_prev_y


def apply_dub_echo(
    audio_data: np.ndarray,
    delay_time_s: float = 0.7,
    feedback: float = 0.65,
    mix: float = 0.6,
    damping_factor: float = 0.3,  # 0.0 (no damping) to 1.0 (max damping)
) -> np.ndarray:
    """
    Applies a dub-style echo effect with filtered feedback.
    High frequencies in echoes are damped based on damping_factor.

    Args:
        audio_data: NumPy array of the input audio.
        delay_time_s: Time for each echo repetition in seconds.
        feedback: Feedback gain (0.0 to <1.0).
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        damping_factor: Controls high-frequency damping in echoes.
                        0.0 = no damping, 1.0 = significant damping.

    Returns:
        The processed audio data (NumPy array).
    """
    if not 0.0 <= damping_factor <= 1.0:
        raise ValueError("Damping factor must be between 0.0 and 1.0.")
    if not 0.0 <= feedback < 1.0:
        raise ValueError("Feedback must be between 0.0 and just under 1.0.")
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    sample_rate = settings.DEFAULT_SR
    delay_samples = int(delay_time_s * sample_rate)

    if delay_samples <= 0:
        # No actual delay, just mix
        return (audio_data * (1 - mix) + audio_data * mix).astype(audio_data.dtype)

    original_dtype = audio_data.dtype
    if np.issubdtype(original_dtype, np.integer):
        # Convert to float for processing
        audio_data_float = audio_data.astype(np.float64) / np.iinfo(original_dtype).max
    else:
        audio_data_float = audio_data.astype(np.float64)

    num_samples = audio_data_float.shape[0]
    is_stereo = audio_data_float.ndim == 2 and audio_data_float.shape[1] == 2

    wet_signal = np.zeros_like(audio_data_float)

    if is_stereo:
        delay_buffer_l = np.zeros(delay_samples, dtype=np.float64)
        delay_buffer_r = np.zeros(delay_samples, dtype=np.float64)
        prev_y_filter_l = np.zeros(1, dtype=np.float64)
        prev_y_filter_r = np.zeros(1, dtype=np.float64)
    else:
        delay_buffer = np.zeros(delay_samples, dtype=np.float64)
        prev_y_filter = np.zeros(1, dtype=np.float64)

    # Damping factor to filter cutoff:
    # Higher damping_factor means lower cutoff for the LPF in feedback.
    # Max cutoff (no damping) could be Nyquist/2, min cutoff (max damping) much lower.
    # Let's map damping_factor: 0 -> ~0.9 (very little filtering), 1 -> ~0.05 (strong filtering)
    # This normalized cutoff is fc / (fs/2).
    # A simple linear mapping: (1.0 - damping_factor) * (max_norm_cutoff - min_norm_cutoff) + min_norm_cutoff
    min_norm_cutoff = 0.05  # Heavy damping
    max_norm_cutoff = 0.8  # Light damping
    filter_cutoff_normalized = max_norm_cutoff - damping_factor * (
        max_norm_cutoff - min_norm_cutoff
    )
    # Ensure cutoff is positive
    filter_cutoff_normalized = max(0.01, filter_cutoff_normalized)

    for i in range(num_samples):
        if is_stereo:
            input_l = audio_data_float[i, 0]
            input_r = audio_data_float[i, 1]

            delayed_sample_l = delay_buffer_l[-1] if delay_samples > 0 else 0.0
            delayed_sample_r = delay_buffer_r[-1] if delay_samples > 0 else 0.0

            wet_signal[i, 0] = delayed_sample_l
            wet_signal[i, 1] = delayed_sample_r

            # Filter the feedback signal
            # The filter needs to process a single sample at a time for the feedback loop
            if damping_factor > 0 and delay_samples > 0:
                # Pass single sample arrays to the filter
                filtered_feedback_l, prev_y_filter_l_updated = _simple_lowpass_filter(
                    np.array([delayed_sample_l * feedback]),
                    filter_cutoff_normalized,
                    prev_y_filter_l,
                )
                filtered_feedback_r, prev_y_filter_r_updated = _simple_lowpass_filter(
                    np.array([delayed_sample_r * feedback]),
                    filter_cutoff_normalized,
                    prev_y_filter_r,
                )
                prev_y_filter_l = prev_y_filter_l_updated
                prev_y_filter_r = prev_y_filter_r_updated
                feedback_input_l = filtered_feedback_l[0]
                feedback_input_r = filtered_feedback_r[0]
            else:  # No damping or no delay
                feedback_input_l = delayed_sample_l * feedback
                feedback_input_r = delayed_sample_r * feedback

            if delay_samples > 0:
                delay_buffer_l = np.roll(delay_buffer_l, 1)
                delay_buffer_l[0] = input_l + feedback_input_l
                delay_buffer_r = np.roll(delay_buffer_r, 1)
                delay_buffer_r[0] = input_r + feedback_input_r
        else:  # Mono
            input_mono = audio_data_float[i]
            delayed_sample_mono = delay_buffer[-1] if delay_samples > 0 else 0.0
            wet_signal[i] = delayed_sample_mono

            if damping_factor > 0 and delay_samples > 0:
                filtered_feedback_mono, prev_y_filter_updated = _simple_lowpass_filter(
                    np.array([delayed_sample_mono * feedback]),
                    filter_cutoff_normalized,
                    prev_y_filter,
                )
                prev_y_filter = prev_y_filter_updated
                feedback_input_mono = filtered_feedback_mono[0]
            else:  # No damping or no delay
                feedback_input_mono = delayed_sample_mono * feedback

            if delay_samples > 0:
                delay_buffer = np.roll(delay_buffer, 1)
                delay_buffer[0] = input_mono + feedback_input_mono

    # Mix dry and wet signal
    processed_audio_float = audio_data_float * (1 - mix) + wet_signal * mix

    # Convert back to original dtype
    if np.issubdtype(original_dtype, np.integer):
        processed_audio = np.clip(
            processed_audio_float * np.iinfo(original_dtype).max,
            np.iinfo(original_dtype).min,
            np.iinfo(original_dtype).max,
        ).astype(original_dtype)
    else:
        processed_audio = processed_audio_float.astype(original_dtype)
        # Clip if original was float but might have been e.g. float32 with -1 to 1 range
        if np.issubdtype(original_dtype, np.floating):
            processed_audio = np.clip(processed_audio, -1.0, 1.0)

    return processed_audio
