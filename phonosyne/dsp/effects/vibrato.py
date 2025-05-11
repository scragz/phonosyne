import numpy as np

# Note: A true pitch-shifting vibrato is more complex, often involving
# granular synthesis or phase vocoder techniques for high quality.
# This implementation will use a modulated delay line, which creates a Doppler effect
# that results in pitch shifting. It's more akin to a chorus/flanger with no dry signal.


def apply_vibrato(
    audio_data: np.ndarray,
    sample_rate: int,
    rate_hz: float = 6.0,
    depth_ms: float = 1.0,  # Depth of delay modulation in milliseconds
    stereo_phase_deg: float = 0.0,
) -> tuple[np.ndarray, int]:
    """
    Applies a vibrato effect to audio data using modulated delay lines.
    This creates pitch modulation via the Doppler effect.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        sample_rate: Sample rate of the audio in Hz.
        rate_hz: Frequency of the LFO modulating the delay time, in Hz.
        depth_ms: Maximum deviation of the delay time from its average, in milliseconds.
                  This controls the intensity of the pitch shift.
        stereo_phase_deg: LFO phase difference between L/R channels in degrees (0-180).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if depth_ms <= 0:
        return audio_data, sample_rate  # No effect if depth is zero
    if not 0.0 <= stereo_phase_deg <= 180.0:
        raise ValueError("Stereo phase must be between 0.0 and 180.0 degrees.")

    # Convert depth from ms to samples
    depth_samples = depth_ms / 1000.0 * sample_rate
    # Average delay needs to be at least the depth to allow full sweep
    average_delay_samples = depth_samples * 1.1  # Add a small margin
    max_delay_samples = int(
        average_delay_samples + depth_samples + 2
    )  # +2 for safety with interpolation

    # LFO generation (sine wave)
    num_samples = audio_data.shape[0]
    t = np.arange(num_samples) / sample_rate
    lfo = np.sin(2 * np.pi * rate_hz * t)

    # Modulated delay time in samples
    # Delay varies from (average_delay - depth) to (average_delay + depth)
    modulated_delay_samples_l = average_delay_samples + lfo * depth_samples
    # Ensure delay is not negative (shouldn't happen with current setup but good check)
    modulated_delay_samples_l = np.maximum(
        0.001 * sample_rate, modulated_delay_samples_l
    )

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    is_stereo = audio_data.ndim == 2 and audio_data.shape[1] == 2
    num_output_channels = 2 if is_stereo else 1
    # Output will be float64 for processing, then converted back
    processed_audio = np.zeros(
        (num_samples, num_output_channels) if is_stereo else num_samples,
        dtype=np.float64,
    )

    original_dtype = audio_data.dtype
    audio_data_float = audio_data.astype(np.float64)

    if not is_stereo:
        delay_buffer = np.zeros(max_delay_samples, dtype=np.float64)
        for i in range(num_samples):
            current_delay = modulated_delay_samples_l[i]
            idx_int = int(current_delay)
            idx_frac = current_delay - idx_int

            # Ensure indices are within buffer bounds for interpolation (using np.roll logic)
            # delay_buffer is filled from right (index 0 is newest sample)
            # So, to get sample delayed by `idx_int`, we look at `delay_buffer[idx_int]`
            # if buffer was `delay_buffer[current_input, prev_input, prev_prev_input ...]`
            # With np.roll, delay_buffer[0] is newest, delay_buffer[idx_int] is the one.

            # Correct indexing for linear interpolation with np.roll based buffer:
            # delay_buffer[0] is x[n-1], delay_buffer[1] is x[n-2] etc. (if we roll then assign to 0)
            # If current_delay is D, we need x[n-D]. This would be at index D if buffer is x[n-1], x[n-2]...
            # Let's use a fixed size buffer and manual indexing for clarity here.
            # Buffer: [oldest ... newest]
            # Read from: buffer_len - 1 - delay_samples

            # Simpler: use a buffer that stores past input samples directly
            # delay_line[write_ptr] = input; read_ptr = (write_ptr - delay_samples + max_delay) % max_delay
            # For interpolation, read two samples around read_ptr

            # Using the roll method from chorus/flanger for consistency:
            # delay_buffer[d_idx_1] and delay_buffer[d_idx_2]
            d_idx_1 = (
                max_delay_samples - 1 - idx_int + max_delay_samples
            ) % max_delay_samples
            d_idx_2 = (
                max_delay_samples - 1 - (idx_int + 1) + max_delay_samples
            ) % max_delay_samples
            delayed_sample_1 = delay_buffer[d_idx_1]
            delayed_sample_2 = delay_buffer[d_idx_2]
            interpolated_delayed_sample = (
                delayed_sample_1 * (1 - idx_frac) + delayed_sample_2 * idx_frac
            )

            processed_audio[i] = interpolated_delayed_sample  # Vibrato is 100% wet

            # Update delay buffer (current input goes to the "start" of the rolled buffer)
            delay_buffer = np.roll(delay_buffer, 1)
            delay_buffer[0] = audio_data_float[i]
    else:
        delay_buffer_l = np.zeros(max_delay_samples, dtype=np.float64)
        delay_buffer_r = np.zeros(max_delay_samples, dtype=np.float64)

        modulated_delay_samples_r = modulated_delay_samples_l
        if stereo_phase_deg > 0.0:
            phase_offset_rad = np.deg2rad(stereo_phase_deg)
            lfo_r = np.sin(2 * np.pi * rate_hz * t + phase_offset_rad)
            modulated_delay_samples_r = average_delay_samples + lfo_r * depth_samples
            modulated_delay_samples_r = np.maximum(
                0.001 * sample_rate, modulated_delay_samples_r
            )

        for i in range(num_samples):
            # Left channel
            current_delay_l = modulated_delay_samples_l[i]
            idx_int_l = int(current_delay_l)
            idx_frac_l = current_delay_l - idx_int_l
            d_idx_l1 = (
                max_delay_samples - 1 - idx_int_l + max_delay_samples
            ) % max_delay_samples
            d_idx_l2 = (
                max_delay_samples - 1 - (idx_int_l + 1) + max_delay_samples
            ) % max_delay_samples
            delayed_l1 = delay_buffer_l[d_idx_l1]
            delayed_l2 = delay_buffer_l[d_idx_l2]
            interp_delayed_l = delayed_l1 * (1 - idx_frac_l) + delayed_l2 * idx_frac_l
            processed_audio[i, 0] = interp_delayed_l

            delay_buffer_l = np.roll(delay_buffer_l, 1)
            delay_buffer_l[0] = audio_data_float[i, 0]

            # Right channel
            current_delay_r = modulated_delay_samples_r[i]
            idx_int_r = int(current_delay_r)
            idx_frac_r = current_delay_r - idx_int_r
            d_idx_r1 = (
                max_delay_samples - 1 - idx_int_r + max_delay_samples
            ) % max_delay_samples
            d_idx_r2 = (
                max_delay_samples - 1 - (idx_int_r + 1) + max_delay_samples
            ) % max_delay_samples
            delayed_r1 = delay_buffer_r[d_idx_r1]
            delayed_r2 = delay_buffer_r[d_idx_r2]
            interp_delayed_r = delayed_r1 * (1 - idx_frac_r) + delayed_r2 * idx_frac_r
            processed_audio[i, 1] = interp_delayed_r

            delay_buffer_r = np.roll(delay_buffer_r, 1)
            delay_buffer_r[0] = audio_data_float[i, 1]

    if np.issubdtype(original_dtype, np.integer):
        processed_audio = np.clip(
            processed_audio, np.iinfo(original_dtype).min, np.iinfo(original_dtype).max
        )

    return processed_audio.astype(original_dtype), sample_rate
