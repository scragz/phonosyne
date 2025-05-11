import numpy as np
from scipy.signal import butter, lfilter


class AllPassFilter:
    """Simple first-order all-pass filter."""

    def __init__(self, coefficient=0.5):
        self.coefficient = coefficient
        self._z1 = 0.0

    def process(self, sample):
        output = -self.coefficient * sample + self._z1
        self._z1 = output * self.coefficient + sample
        return output

    def process_block(self, block):
        output_block = np.zeros_like(block)
        for i, sample in enumerate(block):
            output_block[i] = self.process(sample)
        return output_block


def apply_phaser(
    audio_data: np.ndarray,
    sample_rate: int,
    rate_hz: float = 0.5,
    depth: float = 0.8,  # Normalized depth of LFO (0 to 1)
    stages: int = 4,  # Number of all-pass filter stages
    feedback: float = 0.3,
    mix: float = 0.5,
    stereo_spread_deg: float = 30.0,
) -> tuple[np.ndarray, int]:
    """
    Applies a phaser effect to audio data.
    Phasing is created by passing the signal through a series of all-pass filters
    whose center frequencies are modulated by an LFO.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        sample_rate: Sample rate of the audio in Hz.
        rate_hz: Frequency of the LFO modulating the filter coefficients, in Hz.
        depth: Depth of the LFO modulation (0.0 to 1.0). Controls sweep range.
        stages: Number of all-pass filter stages. More stages = more notches.
        feedback: Feedback gain from the output of the filters back to the input (0.0 to <1.0).
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        stereo_spread_deg: LFO phase difference between L/R channels in degrees (0-180).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")
    if not 0.0 <= feedback < 1.0:
        raise ValueError("Feedback must be between 0.0 and just under 1.0.")
    if not 0.0 <= depth <= 1.0:
        raise ValueError("Depth must be between 0.0 and 1.0.")
    if not 1 <= stages <= 12:  # Practical limit
        raise ValueError("Stages must be between 1 and 12.")

    num_samples = audio_data.shape[0]
    t = np.arange(num_samples) / sample_rate
    lfo = (np.sin(2 * np.pi * rate_hz * t) + 1.0) / 2.0  # LFO from 0 to 1

    # Modulate filter coefficients. All-pass coefficient 'a' is typically between -1 and 1.
    # (1-d)/sqrt(2) to d/sqrt(2) ? No, this is more complex.
    # The coefficient 'a' of a 1st order APF: y[n] = a*x[n] + x[n-1] - a*y[n-1]
    # Or: H(z) = (a + z^-1) / (1 + a*z^-1)
    # The notch frequency is related to 'a'. Let's vary 'a' sinusoidally.
    # A common range for 'a' is e.g. 0.1 to 0.7 for audible sweep.
    min_coeff = 0.1
    max_coeff = 0.7
    modulated_coeffs = min_coeff + lfo * (max_coeff - min_coeff) * depth

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    is_stereo = audio_data.ndim == 2 and audio_data.shape[1] == 2
    num_output_channels = 2 if is_stereo else 1
    processed_audio = np.zeros(
        (num_samples, num_output_channels) if is_stereo else num_samples,
        dtype=np.float64,
    )

    # Feedback buffer
    feedback_sample_l, feedback_sample_r = 0.0, 0.0

    if not is_stereo:
        allpass_filters = [AllPassFilter(0.5) for _ in range(stages)]
        for i in range(num_samples):
            current_coeff = modulated_coeffs[i]
            for apf in allpass_filters:
                apf.coefficient = current_coeff  # Update coefficient based on LFO

            input_sample = audio_data[i] + feedback_sample_l * feedback
            filtered_sample = input_sample
            for apf in allpass_filters:
                filtered_sample = apf.process(filtered_sample)

            feedback_sample_l = filtered_sample  # Store for next feedback iteration
            processed_audio[i] = audio_data[i] * (1 - mix) + filtered_sample * mix
    else:
        allpass_filters_l = [AllPassFilter(0.5) for _ in range(stages)]
        allpass_filters_r = [AllPassFilter(0.5) for _ in range(stages)]

        lfo_r_phase_offset_rad = np.deg2rad(stereo_spread_deg)
        lfo_r = (np.sin(2 * np.pi * rate_hz * t + lfo_r_phase_offset_rad) + 1.0) / 2.0
        modulated_coeffs_r = min_coeff + lfo_r * (max_coeff - min_coeff) * depth

        for i in range(num_samples):
            current_coeff_l = modulated_coeffs[i]
            current_coeff_r = modulated_coeffs_r[i]

            for apf_l, apf_r in zip(allpass_filters_l, allpass_filters_r):
                apf_l.coefficient = current_coeff_l
                apf_r.coefficient = current_coeff_r

            input_sample_l = audio_data[i, 0] + feedback_sample_l * feedback
            input_sample_r = audio_data[i, 1] + feedback_sample_r * feedback

            filtered_sample_l = input_sample_l
            for apf in allpass_filters_l:
                filtered_sample_l = apf.process(filtered_sample_l)

            filtered_sample_r = input_sample_r
            for apf in allpass_filters_r:
                filtered_sample_r = apf.process(filtered_sample_r)

            feedback_sample_l = filtered_sample_l
            feedback_sample_r = filtered_sample_r

            processed_audio[i, 0] = (
                audio_data[i, 0] * (1 - mix) + filtered_sample_l * mix
            )
            processed_audio[i, 1] = (
                audio_data[i, 1] * (1 - mix) + filtered_sample_r * mix
            )

    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype), sample_rate
