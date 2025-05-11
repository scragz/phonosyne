import numpy as np

from phonosyne import settings  # Added

# Potential future imports:
# from scipy.signal import lfilter, resample_poly


def apply_particle(
    audio_data: np.ndarray,
    grain_size_ms: float = 50.0,  # Length of each grain (ms)
    density: float = 10.0,  # Grains per second, or overlap factor
    pitch_shift_semitones: float = 0.0,  # Pitch shift per grain (±12 semitones for an octave)
    pitch_quantize_mode: str = "free",  # "free", "semitone", "octave", etc.
    pitch_randomization_pct: float = 0.0,  # Percentage of pitch randomization (0-100)
    direction_reverse_prob: float = 0.0,  # Probability of reverse playback (0.0 to 1.0)
    delay_ms: float = 0.0,  # Base delay time for grains (0 to 2500ms) - NOT YET IMPLEMENTED
    delay_randomization_pct: float = 0.0,  # Percentage of delay randomization (0-100) - NOT YET IMPLEMENTED
    feedback_amount: float = 0.0,  # Amount of output routed back (0.0 to 1.0, careful with >0.95) - NOT YET IMPLEMENTED
    feedback_tone_rolloff_hz: float = 5000.0,  # Lowpass filter cutoff for feedback path - NOT YET IMPLEMENTED
    freeze_active: bool = False,  # True to freeze the buffer - NOT YET IMPLEMENTED
    lfo_rate_hz: float = 1.0,  # LFO modulation speed - NOT YET IMPLEMENTED
    lfo_to_pitch_depth_st: float = 0.0,  # LFO modulation depth to pitch (semitones) - NOT YET IMPLEMENTED
    lfo_to_delay_depth_ms: float = 0.0,  # LFO modulation depth to delay (ms) - NOT YET IMPLEMENTED
    lfo_to_grain_pos_depth_pct: float = 0.0,  # LFO modulation depth to grain start position (%) - NOT YET IMPLEMENTED
    stereo_pan_width: float = 0.0,  # Random panning width (0.0 mono, 1.0 full stereo) - NOT YET IMPLEMENTED
    mix: float = 0.5,  # Dry/wet mix (0.0 dry to 1.0 wet)
) -> np.ndarray:  # Changed return type
    """
    Applies a "Particle" granular synthesis effect, inspired by the Red Panda Particle V2.
    This effect chops live audio into small "grains" and manipulates their pitch,
    direction, delay, and scheduling, with options for feedback, LFO modulation,
    and buffer freezing.

    Args:
        audio_data: NumPy array of the input audio.
        grain_size_ms: Length of each grain in milliseconds (e.g., 10-500 ms).
        density: Controls how many grains are triggered or overlap.
                 Higher values mean more grains. (e.g., grains per second).
        pitch_shift_semitones: Base pitch shift for each grain in semitones.
        pitch_quantize_mode: Pitch quantization ("free", "semitone", "octave").
        pitch_randomization_pct: Amount of random variation to pitch (0-100%).
        direction_reverse_prob: Probability (0-1) that a grain plays in reverse.
        delay_ms: Base delay time for grains before playback. (NOT YET IMPLEMENTED)
        delay_randomization_pct: Amount of random variation to delay time (0-100%). (NOT YET IMPLEMENTED)
        feedback_amount: Gain of the feedback loop (0.0 to <1.0). (NOT YET IMPLEMENTED)
        feedback_tone_rolloff_hz: Cutoff frequency for a low-pass filter in the feedback path. (NOT YET IMPLEMENTED)
        freeze_active: If True, the current buffer contents are looped. (NOT YET IMPLEMENTED)
        lfo_rate_hz: Frequency of the LFO for modulating parameters. (NOT YET IMPLEMENTED)
        lfo_to_pitch_depth_st: Modulation depth of LFO to pitch shift (semitones). (NOT YET IMPLEMENTED)
        lfo_to_delay_depth_ms: Modulation depth of LFO to delay time (ms). (NOT YET IMPLEMENTED)
        lfo_to_grain_pos_depth_pct: Modulation depth of LFO to grain start position (%). (NOT YET IMPLEMENTED)
        stereo_pan_width: Controls random panning of grains for stereo width (0 mono, 1 full random). (NOT YET IMPLEMENTED)
        mix: Wet/dry mix (0.0 dry, 1.0 wet).

    Returns:
        The processed audio data (NumPy array). # Changed
    """
    # Robustness: If audio_data is a tuple (np.ndarray, int) from a previous effect, unpack it.
    # This handles cases where the output of another effect (audio_array, sample_rate_int)
    # is directly passed as audio_data.
    # REMOVED - This will be handled by dsp.utils.unpack_audio_input before the first effect,
    # or subsequent effects will always receive an ndarray.
    # if (
    #     isinstance(audio_data, tuple)
    #     and len(audio_data) == 2
    #     and isinstance(audio_data[0], np.ndarray)
    #     and isinstance(audio_data[1], int)
    # ):
    #     # The audio data is the first element.
    #     # The sample rate associated with this specific audio data is the second element.
    #     # It's generally safer to use the_sample_rate bundled with the data.
    #     # sample_rate = audio_data[1] # Use settings.DEFAULT_SR
    #     audio_data = audio_data[0]

    current_sample_rate = settings.DEFAULT_SR  # Use global sample rate

    if audio_data.ndim == 0:  # Scalar input
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data  # Return ndarray directly

    original_dtype = audio_data.dtype

    # Determine if input is stereo
    if audio_data.ndim == 1:
        is_stereo = False
        # Convert mono to float64 for processing
        audio_float = audio_data.astype(np.float64)
        num_samples = audio_float.shape[0]
        wet_signal = np.zeros(num_samples, dtype=np.float64)
    elif audio_data.ndim == 2 and audio_data.shape[1] == 2:
        is_stereo = True
        num_samples = audio_data.shape[0]
        # Convert stereo to float64 for processing
        audio_float_L = audio_data[:, 0].astype(np.float64)
        audio_float_R = audio_data[:, 1].astype(np.float64)
        wet_signal_L = np.zeros(num_samples, dtype=np.float64)
        wet_signal_R = np.zeros(num_samples, dtype=np.float64)
    else:  # Unsupported format (e.g. >2 channels or malformed)
        return audio_data  # Return ndarray directly

    # Basic parameter calculations
    grain_size_samples = max(
        1, int(grain_size_ms / 1000.0 * current_sample_rate)
    )  # Use current_sample_rate

    if density <= 1e-6:  # Avoid division by zero or extremely low densities
        inter_onset_interval_samples = num_samples + 1  # Effectively no grains
    else:
        inter_onset_interval_samples = int(
            current_sample_rate / density
        )  # Use current_sample_rate

    max_pitch_random_semitones = (
        12.0  # Max randomization range (e.g., +/- 1 octave if pct is 100)
    )

    # --- Grain Generation Loop ---
    current_grain_trigger_time_samples = 0
    while current_grain_trigger_time_samples < num_samples:
        # Random decisions for this grain instance (correlated for stereo)
        reverse_this_grain = np.random.rand() < direction_reverse_prob
        pitch_random_offset_st = (
            np.random.uniform(-1.0, 1.0)
            * (pitch_randomization_pct / 100.0)
            * max_pitch_random_semitones
        )

        for channel_idx in range(2 if is_stereo else 1):
            if not is_stereo:
                source_channel_audio = audio_float
                target_wet_channel = wet_signal
            else:
                source_channel_audio = (
                    audio_float_L if channel_idx == 0 else audio_float_R
                )
                target_wet_channel = wet_signal_L if channel_idx == 0 else wet_signal_R

            # 1. Extract Raw Grain
            grain_source_start = current_grain_trigger_time_samples
            grain_source_end = grain_source_start + grain_size_samples

            if (
                grain_source_start >= num_samples
            ):  # Should not happen if loop condition is correct
                continue

            raw_grain = source_channel_audio[
                grain_source_start : min(grain_source_end, num_samples)
            ]

            # Pad if grain is shorter than grain_size_samples (e.g., at the end of audio)
            if len(raw_grain) < grain_size_samples:
                padding = np.zeros(
                    grain_size_samples - len(raw_grain), dtype=np.float64
                )
                raw_grain = np.concatenate((raw_grain, padding))

            if len(raw_grain) == 0:  # Should not happen with padding
                continue

            processed_grain = np.copy(raw_grain)

            # 2. Direction
            if reverse_this_grain:
                processed_grain = np.flip(processed_grain)

            # 3. Pitch Shift
            current_pitch_shift_st = pitch_shift_semitones + pitch_random_offset_st

            if pitch_quantize_mode == "semitone":
                current_pitch_shift_st = round(current_pitch_shift_st)
            elif pitch_quantize_mode == "octave":
                current_pitch_shift_st = round(current_pitch_shift_st / 12.0) * 12.0

            pitch_ratio = 2 ** (current_pitch_shift_st / 12.0)

            if (
                abs(pitch_ratio - 1.0) > 1e-6 and pitch_ratio > 1e-6
            ):  # If pitch actually changes & ratio is valid
                original_len = len(processed_grain)
                new_len = int(original_len / pitch_ratio)

                if new_len > 0:
                    x_old = np.linspace(0, original_len - 1, original_len)
                    x_new = np.linspace(
                        0, original_len - 1, new_len
                    )  # Use original_len-1 for endpoint of linspace
                    pitched_data = np.interp(x_new, x_old, processed_grain)

                    current_grain_window = (
                        np.hanning(len(pitched_data))
                        if len(pitched_data) > 0
                        else np.array([1.0])
                    )
                    processed_grain = pitched_data * current_grain_window
                else:
                    processed_grain = np.array([], dtype=np.float64)  # Silent grain
            else:  # No pitch shift or too small
                current_grain_window = (
                    np.hanning(len(processed_grain))
                    if len(processed_grain) > 0
                    else np.array([1.0])
                )
                processed_grain = processed_grain * current_grain_window

            if processed_grain.size == 0:
                continue

            # 4. Add to Wet Signal (no delay implemented yet, grains start at trigger time)
            grain_output_start_time = current_grain_trigger_time_samples
            grain_actual_len = len(processed_grain)

            output_target_start = grain_output_start_time
            output_target_end = grain_output_start_time + grain_actual_len

            if output_target_start < num_samples:
                write_len = min(grain_actual_len, num_samples - output_target_start)
                if write_len > 0:
                    target_wet_channel[
                        output_target_start : output_target_start + write_len
                    ] += processed_grain[:write_len]

        current_grain_trigger_time_samples += inter_onset_interval_samples

    # --- Mix and Finalize ---
    if not is_stereo:
        mixed_output_float = (1.0 - mix) * audio_float + mix * wet_signal
        mixed_output_float = np.clip(mixed_output_float, -1.0, 1.0)
        final_audio = mixed_output_float.astype(original_dtype)
    else:
        mixed_L_float = (1.0 - mix) * audio_float_L + mix * wet_signal_L
        mixed_R_float = (1.0 - mix) * audio_float_R + mix * wet_signal_R
        mixed_L_float = np.clip(mixed_L_float, -1.0, 1.0)
        mixed_R_float = np.clip(mixed_R_float, -1.0, 1.0)
        final_audio = np.stack((mixed_L_float, mixed_R_float), axis=-1).astype(
            original_dtype
        )

    return final_audio  # Return ndarray directly
