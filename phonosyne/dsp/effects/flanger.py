import numpy as np


def apply_flanger(
    audio_data: np.ndarray,
    sample_rate: int,
    rate_hz: float = 0.2,
    depth_ms: float = 1.5,  # Flangers use shorter delays than chorus
    mix: float = 0.5,
    feedback: float = 0.7,  # Flangers often have higher feedback
    stereo_spread_ms: float = 0.2,
) -> tuple[np.ndarray, int]:
    """
    Applies a flanger effect to audio data.
    Flanging is created by mixing the signal with a slightly delayed copy, where the delay time is modulated by an LFO.
    It's similar to chorus but typically uses shorter delay times and more feedback, creating a "jet plane" sweeping sound.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        sample_rate: Sample rate of the audio in Hz.
        rate_hz: Frequency of the LFO modulating the delay time, in Hz.
        depth_ms: Maximum deviation of the delay time from its average, in milliseconds.
                  Typical flanger delays are 0.5ms to 5ms.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        feedback: Feedback gain for the delayed signal (0.0 to <1.0). Crucial for the flanger sound.
        stereo_spread_ms: Additional LFO phase offset for stereo channels.

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")
    if not 0.0 <= feedback < 1.0:
        raise ValueError("Feedback must be between 0.0 and just under 1.0.")
    if depth_ms <= 0:
        depth_ms = 0.001  # Ensure positive for calculations
    if depth_ms > 10:  # Flanger delays are typically short
        print(
            f"Warning: Flanger depth_ms ({depth_ms}ms) is quite long, may sound more like chorus."
        )

    # Convert depth from ms to samples. For flanger, the base delay is very short.
    depth_samples = depth_ms / 1000.0 * sample_rate
    # Average delay for flanger is often centered around a very small value, or even such that min delay is near zero.
    # Let's set average_delay_samples such that the delay line sweeps from ~0.1ms up to (0.1ms + 2*depth_ms)
    min_practical_delay_ms = 0.1
    average_delay_samples = (
        min_practical_delay_ms / 1000.0 * sample_rate
    ) + depth_samples
    max_delay_samples = int(
        average_delay_samples + depth_samples + 2
    )  # +2 for safety with interpolation

    # LFO generation
    num_samples = audio_data.shape[0]
    t = np.arange(num_samples) / sample_rate
    lfo = np.sin(2 * np.pi * rate_hz * t)  # Sine LFO
    # lfo = (np.abs(np.sin(2 * np.pi * rate_hz * t / 2)) * 2 - 1) # Triangle LFO (approx)

    # Modulated delay time in samples
    # Delay varies from (average_delay - depth) to (average_delay + depth)
    modulated_delay_samples = average_delay_samples + lfo * depth_samples
    # Ensure delay is not negative (shouldn't happen with current setup but good check)
    modulated_delay_samples = np.maximum(0.001 * sample_rate, modulated_delay_samples)

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    is_stereo = audio_data.ndim == 2 and audio_data.shape[1] == 2
    num_output_channels = 2 if is_stereo else 1
    processed_audio = np.zeros(
        (num_samples, num_output_channels) if is_stereo else num_samples,
        dtype=audio_data.dtype,
    )

    if not is_stereo:
        delay_buffer = np.zeros(max_delay_samples, dtype=audio_data.dtype)
        for i in range(num_samples):
            current_delay = modulated_delay_samples[i]
            idx_int = int(current_delay)
            idx_frac = current_delay - idx_int

            # Ensure indices are within buffer bounds for interpolation
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

            output_sample = (
                audio_data[i] * (1 - mix) + interpolated_delayed_sample * mix
            )

            new_buffer_input = audio_data[i] + interpolated_delayed_sample * feedback
            delay_buffer = np.roll(delay_buffer, 1)
            delay_buffer[0] = new_buffer_input
            processed_audio[i] = output_sample
    else:
        delay_buffer_l = np.zeros(max_delay_samples, dtype=audio_data.dtype)
        delay_buffer_r = np.zeros(max_delay_samples, dtype=audio_data.dtype)

        lfo_r_phase_offset = (rate_hz * stereo_spread_ms / 1000.0) * 2 * np.pi
        lfo_r = np.sin(2 * np.pi * rate_hz * t + lfo_r_phase_offset)
        modulated_delay_samples_r = average_delay_samples + lfo_r * depth_samples
        modulated_delay_samples_r = np.maximum(
            0.001 * sample_rate, modulated_delay_samples_r
        )

        for i in range(num_samples):
            # Left channel
            current_delay_l = modulated_delay_samples[i]
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

            processed_audio[i, 0] = (
                audio_data[i, 0] * (1 - mix) + interp_delayed_l * mix
            )
            processed_audio[i, 1] = (
                audio_data[i, 1] * (1 - mix) + interp_delayed_r * mix
            )

            new_buf_in_l = audio_data[i, 0] + interp_delayed_l * feedback
            delay_buffer_l = np.roll(delay_buffer_l, 1)
            delay_buffer_l[0] = new_buf_in_l

            new_buf_in_r = audio_data[i, 1] + interp_delayed_r * feedback
            delay_buffer_r = np.roll(delay_buffer_r, 1)
            delay_buffer_r[0] = new_buf_in_r

    return processed_audio, sample_rate
