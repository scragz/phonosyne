import numpy as np

from phonosyne import settings


def apply_tremolo(
    audio_data: np.ndarray,
    rate_hz: float = 5.0,
    depth: float = 0.8,
    lfo_shape: str = "sine",  # 'sine', 'triangle', 'square'
    stereo_phase_deg: float = 0.0,
) -> tuple[np.ndarray, int]:
    """
    Applies a tremolo effect (amplitude modulation) to audio data.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        rate_hz: Frequency of the LFO modulating the amplitude, in Hz.
        depth: Depth of the modulation (0.0 to 1.0). 1.0 means amplitude goes to 0.
        lfo_shape: Shape of the LFO ('sine', 'triangle', 'square').
        stereo_phase_deg: LFO phase difference between L/R channels in degrees (0-180) for stereo panning tremolo.

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= depth <= 1.0:
        raise ValueError("Depth must be between 0.0 and 1.0.")
    if not 0.0 <= stereo_phase_deg <= 180.0:
        raise ValueError("Stereo phase must be between 0.0 and 180.0 degrees.")

    num_samples = audio_data.shape[0]
    t = np.arange(num_samples) / settings.DEFAULT_SR

    # Generate LFO
    if lfo_shape == "sine":
        lfo = (np.sin(2 * np.pi * rate_hz * t) + 1.0) / 2.0  # LFO from 0 to 1
    elif lfo_shape == "triangle":
        lfo = 2.0 * np.abs((rate_hz * t) - np.floor((rate_hz * t) + 0.5))
        # Ensure it's 0-1 if it's a symmetric triangle around 0
        # A simpler triangle LFO: 2 * np.abs(np.arcsin(np.sin(2 * np.pi * rate_hz * t)) / np.pi)
        # Or: (np.abs(np.mod(rate_hz * t - 0.25, 1) * 4 - 2) -1) # Sawtooth like
        # Let's use a common triangle: from -1 to 1 then scale
        lfo_base = (
            np.abs(np.mod(2 * rate_hz * t - 0.5, 2) - 1) * 2 - 1
        )  # Triangle -1 to 1
        lfo = (lfo_base + 1.0) / 2.0
    elif lfo_shape == "square":
        lfo = (np.sign(np.sin(2 * np.pi * rate_hz * t)) + 1.0) / 2.0  # LFO 0 or 1
    else:
        raise ValueError(
            f"Unknown LFO shape: {lfo_shape}. Choose 'sine', 'triangle', or 'square'."
        )

    # Modulation signal: 1 - depth * lfo (if lfo is 0-1, this goes from 1 down to 1-depth)
    # Or, more intuitively: (1-depth) + depth * lfo (if lfo is 0-1, this goes from 1-depth up to 1)
    # Let's use: lfo scaled from (1-depth) to 1. So when lfo is 0, gain is (1-depth), when lfo is 1, gain is 1.
    # No, standard tremolo is amplitude goes from (1-depth)*original_amp to original_amp.
    # Or, if depth is 1, it goes from 0 to original_amp.
    # So, gain modulator = (1 - depth * lfo_0_1)
    # If lfo is 0..1, then gain_mod = 1 - depth * lfo. This makes amplitude dip.
    # If we want lfo to control the gain directly: gain_mod = (1-depth) + depth * lfo_0_1. This is better.
    gain_mod_l = (1.0 - depth) + depth * lfo

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    processed_audio = np.copy(audio_data).astype(np.float64)

    if audio_data.ndim == 1:  # Mono
        processed_audio *= gain_mod_l
    elif audio_data.ndim == 2 and audio_data.shape[1] == 2:  # Stereo
        if stereo_phase_deg == 0.0:
            processed_audio[:, 0] *= gain_mod_l
            processed_audio[:, 1] *= gain_mod_l
        else:
            phase_offset_rad = np.deg2rad(stereo_phase_deg)
            if lfo_shape == "sine":
                lfo_r = (np.sin(2 * np.pi * rate_hz * t + phase_offset_rad) + 1.0) / 2.0
            elif lfo_shape == "triangle":
                lfo_base_r = (
                    np.abs(
                        np.mod(
                            2 * rate_hz * t + phase_offset_rad / (2 * np.pi) - 0.5, 2
                        )
                        - 1
                    )
                    * 2
                    - 1
                )
                lfo_r = (lfo_base_r + 1.0) / 2.0
            elif lfo_shape == "square":
                lfo_r = (
                    np.sign(np.sin(2 * np.pi * rate_hz * t + phase_offset_rad)) + 1.0
                ) / 2.0

            gain_mod_r = (1.0 - depth) + depth * lfo_r
            processed_audio[:, 0] *= gain_mod_l
            processed_audio[:, 1] *= gain_mod_r
    else:
        raise ValueError("Audio data must be 1D (mono) or 2D (stereo, channels last).")

    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype)
