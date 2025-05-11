import numpy as np
from scipy.signal import butter, hilbert, lfilter


class EnvelopeFollower:
    """Simple envelope follower."""

    def __init__(self, sample_rate: int, attack_ms: float, release_ms: float):
        self.attack_coeff = np.exp(-1.0 / (max(1, attack_ms / 1000.0 * sample_rate)))
        self.release_coeff = np.exp(-1.0 / (max(1, release_ms / 1000.0 * sample_rate)))
        self._envelope = 0.0

    def process(self, sample_abs: float) -> float:
        if sample_abs > self._envelope:
            self._envelope = (
                self.attack_coeff * self._envelope
                + (1 - self.attack_coeff) * sample_abs
            )
        else:
            self._envelope = (
                self.release_coeff * self._envelope
                + (1 - self.release_coeff) * sample_abs
            )
        return self._envelope


class BandpassFilter:
    """Simple bandpass filter (Butterworth)."""

    def __init__(
        self, sample_rate: int, lowcut_hz: float, highcut_hz: float, order: int = 2
    ):
        self.nyquist = 0.5 * sample_rate
        self.low = lowcut_hz / self.nyquist
        self.high = highcut_hz / self.nyquist
        if self.low >= self.high:
            # Avoid issues if highcut is too close or below lowcut
            self.high = self.low + 0.01  # Ensure a small passband
            if self.high >= 1.0:
                self.high = 0.99
                self.low = self.high - 0.01
        if self.low <= 0:
            self.low = 0.001

        self.b, self.a = butter(order, [self.low, self.high], btype="band")
        self._z = np.zeros(max(len(self.b), len(self.a)) - 1)  # Initial filter state

    def process(self, sample: float) -> float:
        # Using lfilter for single sample processing is inefficient but simple for demonstration
        # For block processing, lfilter(self.b, self.a, block) is better.
        # Here, we manage state manually for sample-by-sample processing.
        # This is a simplified way to use lfilter for one sample at a time.
        out_sample, self._z = lfilter(self.b, self.a, [sample], zi=self._z)
        return out_sample[0]

    def update_coeffs(
        self, sample_rate: int, lowcut_hz: float, highcut_hz: float, order: int = 2
    ):
        self.nyquist = 0.5 * sample_rate
        self.low = lowcut_hz / self.nyquist
        self.high = highcut_hz / self.nyquist
        if self.low >= self.high:
            self.high = self.low + 0.01
            if self.high >= 1.0:
                self.high = 0.99
                self.low = self.high - 0.01
        if self.low <= 0:
            self.low = 0.001
        if self.high >= 1.0:
            self.high = 0.99

        self.b, self.a = butter(order, [self.low, self.high], btype="band")
        # Reset filter state as coefficients changed
        self._z = np.zeros(max(len(self.b), len(self.a)) - 1)


def apply_autowah(
    audio_data: np.ndarray,
    sample_rate: int,
    mix: float = 0.7,
    sensitivity: float = 0.8,  # How much envelope affects filter cutoff (0-1)
    attack_ms: float = 10.0,
    release_ms: float = 70.0,
    base_freq_hz: float = 100.0,  # Min frequency of the wah filter
    sweep_range_hz: float = 2000.0,  # Max additional frequency sweep
    q_factor: float = 2.0,  # Q of the bandpass filter
    lfo_rate_hz: float = 0.0,  # Optional LFO to add to envelope follower
    lfo_depth: float = 0.0,  # Depth of optional LFO (0-1)
) -> tuple[np.ndarray, int]:
    """
    Applies an autowah (envelope-controlled filter) effect to audio data.

    Args:
        audio_data: NumPy array of the input audio.
        sample_rate: Sample rate of the audio in Hz.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).
        sensitivity: Controls how much the input signal's envelope affects the filter cutoff.
        attack_ms: Attack time for the envelope follower.
        release_ms: Release time for the envelope follower.
        base_freq_hz: The lowest center frequency of the bandpass filter.
        sweep_range_hz: The range above base_freq_hz that the filter can sweep to.
        q_factor: Q factor for the bandpass filter. Higher Q = narrower, more resonant peak.
        lfo_rate_hz: Optional LFO rate to modulate filter cutoff along with envelope.
        lfo_depth: Depth of the optional LFO modulation.

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")
    if not 0.0 <= sensitivity <= 1.0:
        raise ValueError("Sensitivity must be between 0.0 and 1.0.")
    if not 0.0 <= lfo_depth <= 1.0:
        raise ValueError("LFO depth must be between 0.0 and 1.0.")

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data, sample_rate

    original_dtype = audio_data.dtype
    audio_float = audio_data.astype(np.float64)
    processed_audio = np.zeros_like(audio_float)

    env_follower = EnvelopeFollower(sample_rate, attack_ms, release_ms)
    # Initial filter setup - will be updated each sample
    # For a bandpass, Q relates to bandwidth: BW = Fc/Q. We need lowcut and highcut.
    # Let Fc be the center frequency. lowcut = Fc - BW/2, highcut = Fc + BW/2
    # This dynamic update is tricky with scipy.butter. Let's try to set a fixed BW based on initial Q.
    initial_center_freq = base_freq_hz + sweep_range_hz * 0.1  # A starting point
    initial_bw = initial_center_freq / q_factor
    bp_filter = BandpassFilter(
        sample_rate,
        initial_center_freq - initial_bw / 2,
        initial_center_freq + initial_bw / 2,
        order=2,
    )

    num_samples = audio_float.shape[0]
    t = np.arange(num_samples) / sample_rate
    lfo_signal = (
        np.sin(2 * np.pi * lfo_rate_hz * t) * lfo_depth
        if lfo_rate_hz > 0
        else np.zeros(num_samples)
    )

    # Process mono or stereo
    if audio_float.ndim == 1:
        for i in range(num_samples):
            env_val = env_follower.process(np.abs(audio_float[i]))

            # Combine envelope and LFO for modulation source
            mod_source = (
                env_val * sensitivity
                + (lfo_signal[i] + 1.0) / 2.0 * (1.0 - sensitivity) * lfo_depth
            )
            mod_source = np.clip(mod_source, 0.0, 1.0)

            center_freq = base_freq_hz + mod_source * sweep_range_hz
            center_freq = np.clip(
                center_freq, 20.0, sample_rate / 2.0 - 50.0
            )  # Ensure valid range

            bandwidth = center_freq / q_factor
            bandwidth = max(bandwidth, 10.0)  # Ensure minimum bandwidth

            lowcut = center_freq - bandwidth / 2.0
            highcut = center_freq + bandwidth / 2.0

            lowcut = np.clip(lowcut, 20.0, sample_rate / 2.0 - 20.0)
            highcut = np.clip(highcut, lowcut + 10.0, sample_rate / 2.0 - 10.0)

            bp_filter.update_coeffs(sample_rate, lowcut, highcut)
            processed_audio[i] = bp_filter.process(audio_float[i])
    elif audio_float.ndim == 2:
        # For stereo, typically use a single envelope from combined L/R, or independent.
        # Here, let's use a combined envelope for simplicity and linked wah effect.
        # Or, could create two EnvelopeFollower and BandpassFilter instances for true stereo.
        # This is a simplified stereo: one envelope, two filters (could be one if coeffs are same).
        env_follower_stereo = EnvelopeFollower(sample_rate, attack_ms, release_ms)
        bp_filter_l = BandpassFilter(
            sample_rate,
            initial_center_freq - initial_bw / 2,
            initial_center_freq + initial_bw / 2,
            order=2,
        )
        bp_filter_r = BandpassFilter(
            sample_rate,
            initial_center_freq - initial_bw / 2,
            initial_center_freq + initial_bw / 2,
            order=2,
        )

        for i in range(num_samples):
            # Use max of L/R for envelope detection for linked effect
            env_val = env_follower_stereo.process(np.max(np.abs(audio_float[i, :])))

            mod_source = (
                env_val * sensitivity
                + (lfo_signal[i] + 1.0) / 2.0 * (1.0 - sensitivity) * lfo_depth
            )
            mod_source = np.clip(mod_source, 0.0, 1.0)

            center_freq = base_freq_hz + mod_source * sweep_range_hz
            center_freq = np.clip(center_freq, 20.0, sample_rate / 2.0 - 50.0)
            bandwidth = center_freq / q_factor
            bandwidth = max(bandwidth, 10.0)

            lowcut = center_freq - bandwidth / 2.0
            highcut = center_freq + bandwidth / 2.0
            lowcut = np.clip(lowcut, 20.0, sample_rate / 2.0 - 20.0)
            highcut = np.clip(highcut, lowcut + 10.0, sample_rate / 2.0 - 10.0)

            bp_filter_l.update_coeffs(sample_rate, lowcut, highcut)
            bp_filter_r.update_coeffs(
                sample_rate, lowcut, highcut
            )  # Same coeffs for L/R for now

            processed_audio[i, 0] = bp_filter_l.process(audio_float[i, 0])
            processed_audio[i, 1] = bp_filter_r.process(audio_float[i, 1])
    else:
        raise ValueError("Audio data must be 1D (mono) or 2D (stereo, channels last).")

    # Mix dry and wet
    mixed_audio = audio_float * (1 - mix) + processed_audio * mix

    if np.issubdtype(original_dtype, np.integer):
        mixed_audio = np.clip(
            mixed_audio, np.iinfo(original_dtype).min, np.iinfo(original_dtype).max
        )

    return mixed_audio.astype(original_dtype), sample_rate
