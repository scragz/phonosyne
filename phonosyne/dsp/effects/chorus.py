import numpy as np


def apply_chorus(
    audio_data: np.ndarray,
    sample_rate: int,
    rate_hz: float = 1.0,
    depth_ms: float = 2.0,
    mix: float = 0.5,
    feedback: float = 0.2,
    stereo_spread_ms: float = 0.5,
) -> tuple[np.ndarray, int]:
    """
    Applies a chorus effect to audio data.
    Chorus is created by mixing the original signal with delayed, pitch-modulated copies.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        sample_rate: Sample rate of the audio in Hz.
        rate_hz: Frequency of the LFO modulating the delay time, in Hz.
        depth_ms: Maximum deviation of the delay time from its average, in milliseconds.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        feedback: Feedback gain for the delayed signal (0.0 to <1.0). Adds a flanger-like quality.
        stereo_spread_ms: Additional LFO phase offset for stereo channels to enhance stereo width, in ms.
                          Only used if input is stereo.

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")
    if not 0.0 <= feedback < 1.0:
        raise ValueError("Feedback must be between 0.0 and just under 1.0.")
    if depth_ms <= 0:
        # No modulation, effectively a short delay/flanger if feedback is high
        depth_ms = 0.001  # Ensure it's not zero for calculations

    # Convert depth and spread from ms to samples
    depth_samples = depth_ms / 1000.0 * sample_rate
    # Average delay is often around the depth, or slightly more, to avoid very short delays
    average_delay_samples = depth_samples * 1.5
    max_delay_samples = int(
        average_delay_samples + depth_samples + 2
    )  # +2 for safety with interpolation

    # LFO generation
    num_samples = audio_data.shape[0]
    t = np.arange(num_samples) / sample_rate
    lfo = np.sin(2 * np.pi * rate_hz * t)

    # Modulated delay time in samples
    # Delay varies from (average_delay - depth) to (average_delay + depth)
    modulated_delay_samples = average_delay_samples + lfo * depth_samples

    # Ensure audio_data is at least 1D
    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    is_stereo = audio_data.ndim == 2 and audio_data.shape[1] == 2
    num_output_channels = 2 if is_stereo else 1
    processed_audio = np.zeros(
        (num_samples, num_output_channels) if is_stereo else num_samples,
        dtype=audio_data.dtype,
    )

    if not is_stereo:
        # Mono processing
        delay_buffer = np.zeros(max_delay_samples, dtype=audio_data.dtype)
        for i in range(num_samples):
            current_delay = modulated_delay_samples[i]
            # Linear interpolation for fractional delay
            idx_int = int(current_delay)
            idx_frac = current_delay - idx_int

            d_idx = (
                np.arange(max_delay_samples) - idx_int - 1 + max_delay_samples
            ) % max_delay_samples
            delayed_sample_1 = delay_buffer[d_idx[-1]]  # delay_buffer[idx_int]
            delayed_sample_2 = delay_buffer[d_idx[-2]]  # delay_buffer[idx_int + 1]
            interpolated_delayed_sample = (
                delayed_sample_1 * (1 - idx_frac) + delayed_sample_2 * idx_frac
            )

            output_sample = (
                audio_data[i] * (1 - mix) + interpolated_delayed_sample * mix
            )

            new_buffer_input = audio_data[i] + interpolated_delayed_sample * feedback
            delay_buffer = np.roll(delay_buffer, 1)
            delay_buffer[0] = new_buffer_input
            processed_audio[i] = output_sample
    else:
        # Stereo processing
        delay_buffer_l = np.zeros(max_delay_samples, dtype=audio_data.dtype)
        delay_buffer_r = np.zeros(max_delay_samples, dtype=audio_data.dtype)

        # LFO for right channel with phase offset for stereo spread
        spread_delay_offset_samples = stereo_spread_ms / 1000.0 * sample_rate
        lfo_r_phase_offset = (
            (rate_hz * stereo_spread_ms / 1000.0) * 2 * np.pi
        )  # phase = 2*pi*f*t_offset
        lfo_r = np.sin(2 * np.pi * rate_hz * t + lfo_r_phase_offset)
        modulated_delay_samples_r = average_delay_samples + lfo_r * depth_samples

        for i in range(num_samples):
            # Left channel
            current_delay_l = modulated_delay_samples[i]
            idx_int_l = int(current_delay_l)
            idx_frac_l = current_delay_l - idx_int_l
            d_idx_l = (
                np.arange(max_delay_samples) - idx_int_l - 1 + max_delay_samples
            ) % max_delay_samples
            delayed_l1 = delay_buffer_l[d_idx_l[-1]]
            delayed_l2 = delay_buffer_l[d_idx_l[-2]]
            interp_delayed_l = delayed_l1 * (1 - idx_frac_l) + delayed_l2 * idx_frac_l

            # Right channel
            current_delay_r = modulated_delay_samples_r[i]
            idx_int_r = int(current_delay_r)
            idx_frac_r = current_delay_r - idx_int_r
            d_idx_r = (
                np.arange(max_delay_samples) - idx_int_r - 1 + max_delay_samples
            ) % max_delay_samples
            delayed_r1 = delay_buffer_r[d_idx_r[-1]]
            delayed_r2 = delay_buffer_r[d_idx_r[-2]]
            interp_delayed_r = delayed_r1 * (1 - idx_frac_r) + delayed_r2 * idx_frac_r

            # Output samples
            processed_audio[i, 0] = (
                audio_data[i, 0] * (1 - mix) + interp_delayed_l * mix
            )
            processed_audio[i, 1] = (
                audio_data[i, 1] * (1 - mix) + interp_delayed_r * mix
            )

            # Update delay buffers with feedback
            new_buf_in_l = audio_data[i, 0] + interp_delayed_l * feedback
            delay_buffer_l = np.roll(delay_buffer_l, 1)
            delay_buffer_l[0] = new_buf_in_l

            new_buf_in_r = audio_data[i, 1] + interp_delayed_r * feedback
            delay_buffer_r = np.roll(delay_buffer_r, 1)
            delay_buffer_r[0] = new_buf_in_r

    return processed_audio, sample_rate
