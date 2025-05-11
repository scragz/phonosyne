import numpy as np

# Potential future imports:
# from scipy.signal import lfilter, resample_poly


def apply_particle(
    audio_data: np.ndarray,
    sample_rate: int,
    grain_size_ms: float = 50.0,  # Length of each grain (ms)
    density: float = 10.0,  # Grains per second, or overlap factor
    pitch_shift_semitones: float = 0.0,  # Pitch shift per grain (±12 semitones for an octave)
    pitch_quantize_mode: str = "free",  # "free", "semitone", "octave", etc.
    pitch_randomization_pct: float = 0.0,  # Percentage of pitch randomization (0-100)
    direction_reverse_prob: float = 0.0,  # Probability of reverse playback (0.0 to 1.0)
    delay_ms: float = 0.0,  # Base delay time for grains (0 to 2500ms)
    delay_randomization_pct: float = 0.0,  # Percentage of delay randomization (0-100)
    feedback_amount: float = 0.0,  # Amount of output routed back (0.0 to 1.0, careful with >0.95)
    feedback_tone_rolloff_hz: float = 5000.0,  # Lowpass filter cutoff for feedback path
    freeze_active: bool = False,  # True to freeze the buffer
    lfo_rate_hz: float = 1.0,  # LFO modulation speed
    lfo_to_pitch_depth_st: float = 0.0,  # LFO modulation depth to pitch (semitones)
    lfo_to_delay_depth_ms: float = 0.0,  # LFO modulation depth to delay (ms)
    lfo_to_grain_pos_depth_pct: float = 0.0,  # LFO modulation depth to grain start position (%)
    stereo_pan_width: float = 0.0,  # Random panning width (0.0 mono, 1.0 full stereo)
    mix: float = 0.5,  # Dry/wet mix (0.0 dry to 1.0 wet)
) -> tuple[np.ndarray, int]:
    """
    Applies a "Particle" granular synthesis effect, inspired by the Red Panda Particle V2.
    This effect chops live audio into small "grains" and manipulates their pitch,
    direction, delay, and scheduling, with options for feedback, LFO modulation,
    and buffer freezing.

    Args:
        audio_data: NumPy array of the input audio.
        sample_rate: Sample rate of the audio in Hz.
        grain_size_ms: Length of each grain in milliseconds (e.g., 10-500 ms).
        density: Controls how many grains are triggered or overlap.
                 Higher values mean more grains. (e.g., grains per second).
        pitch_shift_semitones: Base pitch shift for each grain in semitones.
        pitch_quantize_mode: Pitch quantization ("free", "semitone", "octave").
        pitch_randomization_pct: Amount of random variation to pitch (0-100%).
        direction_reverse_prob: Probability (0-1) that a grain plays in reverse.
        delay_ms: Base delay time for grains before playback.
        delay_randomization_pct: Amount of random variation to delay time (0-100%).
        feedback_amount: Gain of the feedback loop (0.0 to <1.0).
        feedback_tone_rolloff_hz: Cutoff frequency for a low-pass filter in the feedback path.
        freeze_active: If True, the current buffer contents are looped.
        lfo_rate_hz: Frequency of the LFO for modulating parameters.
        lfo_to_pitch_depth_st: Modulation depth of LFO to pitch shift (semitones).
        lfo_to_delay_depth_ms: Modulation depth of LFO to delay time (ms).
        lfo_to_grain_pos_depth_pct: Modulation depth of LFO to grain start position (%).
        stereo_pan_width: Controls random panning of grains for stereo width (0 mono, 1 full random).
        mix: Wet/dry mix (0.0 dry, 1.0 wet).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).

    Note:
        This is a complex effect. The initial implementation will be a placeholder.
        Key aspects to implement include:
        1. Circular buffer for live audio.
        2. Grain extraction and windowing (e.g., Hann window).
        3. Grain scheduler (density, inter-onset interval).
        4. Per-grain pitch shifting (e.g., resampling, phase vocoder for higher quality).
        5. Per-grain direction control.
        6. Delay lines for grains.
        7. Feedback path with filtering.
        8. LFO generation and application to parameters.
        9. Stereo panning for grains.
        10. Freeze buffer mechanism.
    """
    if audio_data.ndim == 0:  # Scalar input
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data, sample_rate

    original_dtype = audio_data.dtype
    # audio_float = audio_data.astype(np.float64) # Work with float64 for processing

    # Placeholder: returns dry signal for now
    # TODO: Implement the granular synthesis engine

    # Ensure output is in the original dtype
    # processed_audio = audio_float.astype(original_dtype)

    # For now, just return the original audio mixed appropriately
    dry_signal = audio_data
    wet_signal = np.copy(audio_data)  # Replace with actual processed wet signal

    # Placeholder for actual processing - this will be very involved
    # For example, a very basic "stutter" might just repeat tiny chunks
    # but a full granular engine is much more.

    # Mix dry and wet
    output_audio = (1 - mix) * dry_signal + mix * wet_signal
    output_audio = np.clip(
        output_audio, -1.0, 1.0
    )  # Assuming audio is in -1 to 1 range

    return output_audio.astype(original_dtype), sample_rate
