import numpy as np
from scipy.signal import lfilter

from phonosyne import settings


def apply_rainbow_machine(
    audio_data: np.ndarray,
    # sample_rate: int, # Removed parameter
    pitch_semitones: float = 0.0,
    primary_level: float = 0.8,
    secondary_mode: float = 0.0,  # -1: full octave down, 0: off, +1: full octave up
    tracking_ms: float = 20.0,
    tone_rolloff: float = 0.5,  # 0: dark (more rolloff), 1: bright (less rolloff)
    magic_feedback: float = 0.0,  # Gain of the magic feedback loop
    magic_feedback_delay_ms: float = 50.0,  # Delay in the magic feedback loop
    magic_iterations: int = 1,  # Number of iterations for the magic feedback
    mod_rate_hz: float = 0.5,
    mod_depth_ms: float = 5.0,
    mix: float = 0.5,
) -> np.ndarray:  # Changed return type
    """
    Applies a "Rainbow Machine" type effect with iterative "Magic" feedback.
    This includes pitch shifting, delay, modulation, tone control, and a
    regenerative feedback path that routes the processed signal back into the
    pitch shifters' input.

    Args:
        audio_data: NumPy array of the input audio.
        # sample_rate: Sample rate of the audio in Hz. # Removed from docstring
        pitch_semitones: Primary pitch shift in semitones (-4.0 to +3.0).
        primary_level: Level of the primary pitch-shifted signal (0.0 to 1.0).
        secondary_mode: Controls secondary octave (-1.0 octave down, 0.0 off, +1.0 octave up).
                        The magnitude of the value acts as the level for the secondary signal.
        tracking_ms: Delay/lag between dry and pitch-shifted signals in milliseconds.
        tone_rolloff: Controls a low-pass filter on the wet signal (0.0 dark to 1.0 bright).
        magic_feedback: Gain of the "Magic" feedback loop (0.0 to 0.98 for stability, higher can oscillate).
        magic_feedback_delay_ms: Delay time for the "Magic" feedback path in milliseconds.
        magic_iterations: Number of times the "Magic" feedback loop is processed.
                          More iterations lead to more pronounced effects but increase processing time
                          and potential for instability.
        mod_rate_hz: LFO rate for chorus/flange modulation in Hz.
        mod_depth_ms: LFO depth for chorus/flange modulation in milliseconds.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        The processed audio data (NumPy array). # Changed return type in docstring

    Note:
        The "Magic" feedback loop can be computationally intensive, especially with
        higher `magic_iterations` or long audio inputs, due to the iterative
        processing of the entire wet signal chain. The pitch shifting is a simplified
        time-domain method and may produce artifacts, which can be part of the charm
        for this type of effect.
    """
    if audio_data.ndim == 0:  # Scalar input
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data  # Changed return

    original_dtype = audio_data.dtype
    audio_float = audio_data.astype(np.float64)
    num_samples = len(audio_float)

    # --- Parameter validation and conversion ---
    pitch_semitones = np.clip(pitch_semitones, -4.0, 3.0)
    primary_level = np.clip(primary_level, 0.0, 1.0)
    secondary_level_abs = np.clip(abs(secondary_mode), 0.0, 1.0)
    secondary_pitch_ratio = 1.0
    if secondary_mode > 0:
        secondary_pitch_ratio = 2.0  # Octave up
    elif secondary_mode < 0:
        secondary_pitch_ratio = 0.5  # Octave down

    tracking_samples = int(
        np.clip(tracking_ms, 0, 1000)
        / 1000.0
        * settings.DEFAULT_SR  # Used settings.DEFAULT_SR
    )  # Increased max tracking
    tone_rolloff = np.clip(tone_rolloff, 0.0, 1.0)

    magic_feedback = np.clip(magic_feedback, 0.0, 0.98)  # Clipping for stability
    magic_feedback_delay_samples = int(
        np.clip(magic_feedback_delay_ms, 1, 2000)
        / 1000.0
        * settings.DEFAULT_SR  # Used settings.DEFAULT_SR
    )  # Min 1ms
    magic_iterations = max(1, int(magic_iterations))  # At least one pass

    mod_rate_hz = np.clip(mod_rate_hz, 0.05, 20.0)  # Increased max mod rate
    mod_depth_samples = int(
        np.clip(mod_depth_ms, 0, 30)
        / 1000.0
        * settings.DEFAULT_SR  # Used settings.DEFAULT_SR
    )  # Increased max mod depth
    mix = np.clip(mix, 0.0, 1.0)

    # --- Helper: Simplified Pitch Shifting (Time-Domain Resampling by Interpolation) ---
    def shift_pitch_crude(data, ratio):
        if ratio == 1.0 or data.size == 0:
            return np.copy(data)

        original_indices = np.arange(len(data))
        # Create new time indices for reading from the original data
        # If ratio > 1 (pitch down), new_time_indices effectively compress data reading
        # If ratio < 1 (pitch up), new_time_indices effectively stretch data reading
        read_indices = np.arange(len(data)) * ratio

        # Clip indices to prevent reading out of bounds during interpolation
        read_indices = np.clip(read_indices, 0, len(data) - 1)

        # Interpolate.
        shifted = np.interp(read_indices, original_indices, data)
        return shifted

    # --- Iterative "Magic" Feedback Loop ---
    # This buffer holds the delayed version of the output of the tone filter from the PREVIOUS iteration.
    # It's what gets fed back into the input of the pitch shifters.
    delayed_toned_signal_for_feedback = np.zeros_like(audio_float)

    # This will store the output of the tone filter from the current iteration of the magic loop
    current_iter_toned_signal = np.zeros_like(audio_float)

    for iteration in range(magic_iterations):
        # 1. Form input to pitch shifters for the current iteration
        # On the first iteration (iteration == 0), delayed_toned_signal_for_feedback is all zeros.
        input_to_shifters = (
            audio_float + magic_feedback * delayed_toned_signal_for_feedback
        )
        # Clip input to shifters to prevent extreme values if feedback runs away
        input_to_shifters = np.clip(input_to_shifters, -1.0, 1.0)

        # 2. Pitch Shifting
        shifted_primary = (
            shift_pitch_crude(input_to_shifters, 2 ** (pitch_semitones / 12.0))
            * primary_level
        )

        shifted_secondary = np.zeros_like(input_to_shifters)
        if secondary_level_abs > 0:
            shifted_secondary = (
                shift_pitch_crude(input_to_shifters, secondary_pitch_ratio)
                * secondary_level_abs
            )

        pitch_shifted_signal = shifted_primary + shifted_secondary
        pitch_shifted_signal = np.clip(
            pitch_shifted_signal, -1.0, 1.0
        )  # Clip after summing shifters

        # 3. Tracking Delay
        if tracking_samples > 0 and pitch_shifted_signal.size > tracking_samples:
            tracked_signal = np.concatenate(
                (np.zeros(tracking_samples), pitch_shifted_signal[:-tracking_samples])
            )
        elif tracking_samples > 0:  # if signal is shorter than delay
            tracked_signal = np.zeros_like(pitch_shifted_signal)
        else:
            tracked_signal = pitch_shifted_signal

        # 4. Modulation (Chorus/Flange)
        if mod_depth_samples > 0 and mod_rate_hz > 0 and tracked_signal.size > 0:
            t = np.arange(num_samples) / settings.DEFAULT_SR  # Used settings.DEFAULT_SR
            # LFO signal: a sine wave for delay modulation
            lfo_modulation = mod_depth_samples * np.sin(2 * np.pi * mod_rate_hz * t)

            modulated_signal = np.zeros_like(tracked_signal)

            # Max positive excursion of LFO determines necessary padding/buffer start
            # Add a small base delay for chorus (e.g. mod_depth_samples) so LFO modulates around it
            base_chorus_delay_samples = mod_depth_samples

            # Pad signal for delay reads. Total padding needs to account for base_chorus_delay + LFO swing.
            # Max delay = base_chorus_delay_samples + mod_depth_samples
            # Min delay = base_chorus_delay_samples - mod_depth_samples
            # We need to ensure read indices are always positive.
            # Let's make the read relative to `i + base_chorus_delay_samples - lfo_modulation[i]`

            # Effective delay for each sample: base_chorus_delay_samples - lfo_modulation[i]
            # (subtracting LFO means positive LFO reduces delay, negative LFO increases it)
            # This is a common way to implement chorus/flanger.

            # Pad the input signal at the beginning to handle negative indices from LFO
            # The maximum lookback needed is roughly base_chorus_delay + mod_depth_samples
            padding_amount = (
                base_chorus_delay_samples + mod_depth_samples + 1
            )  # +1 for safety
            padded_tracked_signal = np.concatenate(
                (np.zeros(padding_amount), tracked_signal)
            )

            for i in range(num_samples):
                # Current delay amount in samples, modulated by LFO
                # Positive lfo_modulation value should decrease delay time (sharper pitch for vibrato-like effect)
                # Negative lfo_modulation value should increase delay time (flatter pitch)
                current_delay_samps = base_chorus_delay_samples - lfo_modulation[i]

                read_idx_float = padding_amount + i - current_delay_samps

                # Linear interpolation for fractional delay
                idx_floor = int(np.floor(read_idx_float))
                idx_ceil = int(np.ceil(read_idx_float))
                frac = read_idx_float - idx_floor

                val_floor, val_ceil = 0.0, 0.0
                if idx_floor >= 0 and idx_floor < len(padded_tracked_signal):
                    val_floor = padded_tracked_signal[idx_floor]
                if idx_ceil >= 0 and idx_ceil < len(padded_tracked_signal):
                    val_ceil = padded_tracked_signal[idx_ceil]
                else:  # if ceil is out of bounds, use floor value to avoid issues
                    val_ceil = val_floor

                if idx_floor == idx_ceil:  # No fraction
                    modulated_signal[i] = val_floor
                else:
                    modulated_signal[i] = val_floor * (1.0 - frac) + val_ceil * frac
        else:
            modulated_signal = np.copy(tracked_signal)
        modulated_signal = np.clip(modulated_signal, -1.0, 1.0)

        # 5. Tone Control (Simple Low-Pass Filter)
        if modulated_signal.size > 0:
            lpf_a_pole = 0.99 - tone_rolloff * (
                0.99 - 0.05
            )  # Pole from ~0.05 (bright) to ~0.99 (dark)
            lpf_b_coeffs = [1.0 - lpf_a_pole]  # Numerator: 1-a
            lpf_a_coeffs = [1.0, -lpf_a_pole]  # Denominator: [1, -a]
            current_iter_toned_signal = lfilter(
                lpf_b_coeffs, lpf_a_coeffs, modulated_signal
            )
        else:
            current_iter_toned_signal = np.zeros_like(audio_float)
        current_iter_toned_signal = np.clip(current_iter_toned_signal, -1.0, 1.0)

        # 6. Prepare feedback for the NEXT iteration (or for output if this is the last iteration)
        # This involves delaying the `current_iter_toned_signal`.
        if (
            magic_feedback_delay_samples > 0
            and current_iter_toned_signal.size > magic_feedback_delay_samples
        ):
            delayed_toned_signal_for_feedback = np.concatenate(
                (
                    np.zeros(magic_feedback_delay_samples),
                    current_iter_toned_signal[:-magic_feedback_delay_samples],
                )
            )
        elif magic_feedback_delay_samples > 0:  # if signal is shorter than delay
            delayed_toned_signal_for_feedback = np.zeros_like(current_iter_toned_signal)
        else:  # No delay
            delayed_toned_signal_for_feedback = np.copy(current_iter_toned_signal)

        # Optional: Introduce non-linearities into the feedback path here for more "magic"
        # For example: delayed_toned_signal_for_feedback = np.tanh(delayed_toned_signal_for_feedback * 1.5)
        # This can help control runaway feedback or add harmonic content.
        # For now, keeping it linear.

    # The `current_iter_toned_signal` from the LAST iteration of the magic loop is our final wet signal
    final_wet_signal = current_iter_toned_signal

    # --- Mix ---
    output_audio = audio_float * (1.0 - mix) + final_wet_signal * mix

    # Final Normalize/clip output
    # It's generally better to avoid hard clipping if possible, but for an effect, it might be acceptable.
    # Normalizing to -1dBFS to leave some headroom.
    max_abs = np.max(np.abs(output_audio))
    if max_abs > 1.0:  # If it's already clipping
        output_audio /= max_abs  # Normalize to +/- 1.0
    elif max_abs > 0:  # If not silent and not clipping, normalize to -1 dBFS (0.891)
        # target_peak = 10**(-1.0/20.0) # -1 dBFS
        # if max_abs > target_peak: # Only scale down if current peak is above target
        #    output_audio = output_audio * (target_peak / max_abs)
        pass  # Decided against auto-normalizing to -1dBFS if not clipping. Let mix handle levels.

    return output_audio.astype(original_dtype)  # Changed return
