import numpy as np

from phonosyne import settings


class Compressor:
    """
    A simple dynamic range compressor.
    """

    def __init__(
        self,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 5.0,
        release_ms: float = 50.0,
        makeup_gain_db: float = 0.0,
        knee_db: float = 0.0,
    ):
        self.threshold_lin = 10 ** (threshold_db / 20.0)
        self.ratio = ratio
        self.attack_coeff = (
            np.exp(-1.0 / (attack_ms / 1000.0 * settings.DEFAULT_SR))
            if attack_ms > 0
            else 0.0
        )
        self.release_coeff = (
            np.exp(-1.0 / (release_ms / 1000.0 * settings.DEFAULT_SR))
            if release_ms > 0
            else 0.0
        )
        self.makeup_gain_lin = 10 ** (makeup_gain_db / 20.0)
        self.knee_width_lin = 10 ** (
            knee_db / 20.0
        )  # This interpretation of knee might be too simplistic
        self.knee_db = knee_db

        self._envelope = 0.0  # Current envelope level (linear)

    def _calculate_gain_reduction(self, level_db: float) -> float:
        """Calculates gain reduction in dB based on level, threshold, ratio, and knee."""
        threshold_db = 20 * np.log10(self.threshold_lin)

        # Below knee / threshold
        if self.knee_db <= 0 or level_db < (threshold_db - self.knee_db / 2.0):
            if level_db <= threshold_db:
                return 0.0  # No gain reduction
            else:
                return (threshold_db - level_db) * (
                    1.0 - 1.0 / self.ratio
                )  # Hard knee compression

        # Within knee
        elif level_db <= (threshold_db + self.knee_db / 2.0):
            # Quadratic interpolation for soft knee
            # This is a common way to implement a soft knee
            over_knee_start = level_db - (threshold_db - self.knee_db / 2.0)
            gain_reduction_at_knee_end = (self.knee_db / 2.0) * (
                1.0 - 1.0 / self.ratio
            )  # GR if input was at knee_end with hard knee starting at threshold
            # Simplified: (slope_change_factor * x^2) / (2 * knee_width)
            # slope_change = (1.0 - 1.0/self.ratio)
            # gain_reduction = (slope_change * (over_knee_start**2)) / (2 * self.knee_db) # This needs dB units consistently
            # A simpler soft knee: gradually apply ratio over the knee width
            knee_factor = (
                level_db - (threshold_db - self.knee_db / 2.0)
            ) / self.knee_db
            effective_ratio = 1 + knee_factor * (self.ratio - 1)
            if effective_ratio <= 1.0:
                return 0.0  # Should not happen if level_db is in knee
            return (threshold_db - self.knee_db / 2.0 - level_db) * (
                1.0 - 1.0 / effective_ratio
            )

        # Above knee / threshold
        else:
            return (threshold_db - level_db) * (
                1.0 - 1.0 / self.ratio
            )  # Hard knee compression beyond knee

    def process_sample(self, sample: float) -> float:
        # Level detection (RMS or peak, here using peak for simplicity)
        # For stereo, usually process channels linked or independently based on max level
        input_level_lin = np.abs(sample)

        # Envelope follower
        if input_level_lin > self._envelope:
            self._envelope = (
                self.attack_coeff * self._envelope
                + (1 - self.attack_coeff) * input_level_lin
            )
        else:
            self._envelope = (
                self.release_coeff * self._envelope
                + (1 - self.release_coeff) * input_level_lin
            )

        # Avoid log(0)
        if self._envelope < 1e-9:  # Effectively -180 dB
            gain_reduction_db = 0.0
        else:
            envelope_db = 20 * np.log10(self._envelope)
            gain_reduction_db = self._calculate_gain_reduction(envelope_db)

        # Apply gain reduction
        gain_lin = 10 ** (gain_reduction_db / 20.0)
        compressed_sample = sample * gain_lin

        # Apply makeup gain
        return compressed_sample * self.makeup_gain_lin

    def process_block(self, audio_block: np.ndarray) -> np.ndarray:
        processed_block = np.copy(audio_block)
        if audio_block.ndim == 1:  # Mono
            for i in range(len(audio_block)):
                processed_block[i] = self.process_sample(audio_block[i])
        elif audio_block.ndim == 2:  # Stereo
            # For stereo, typically use a single envelope derived from max of L/R or L+R
            # Here, we'll process independently for simplicity, or use max for linked compression.
            # Let's use linked (max of abs values for envelope detection)
            for i in range(audio_block.shape[0]):
                # Level detection from max of channels for this sample instant
                input_level_lin = np.max(np.abs(audio_block[i, :]))

                if input_level_lin > self._envelope:
                    self._envelope = (
                        self.attack_coeff * self._envelope
                        + (1 - self.attack_coeff) * input_level_lin
                    )
                else:
                    self._envelope = (
                        self.release_coeff * self._envelope
                        + (1 - self.release_coeff) * input_level_lin
                    )

                if self._envelope < 1e-9:
                    gain_reduction_db = 0.0
                else:
                    envelope_db = 20 * np.log10(self._envelope)
                    gain_reduction_db = self._calculate_gain_reduction(envelope_db)

                gain_lin = 10 ** (gain_reduction_db / 20.0)
                processed_block[i, 0] = (
                    audio_block[i, 0] * gain_lin * self.makeup_gain_lin
                )
                processed_block[i, 1] = (
                    audio_block[i, 1] * gain_lin * self.makeup_gain_lin
                )
        return processed_block


def apply_compressor(
    audio_data: np.ndarray,
    threshold_db: float = -20.0,
    ratio: float = 4.0,
    attack_ms: float = 5.0,
    release_ms: float = 50.0,
    makeup_gain_db: float = 0.0,
    knee_db: float = 0.0,
) -> np.ndarray:
    """
    Applies a compressor effect to audio data.

    Args:
        audio_data: NumPy array of the input audio.
        threshold_db: Compressor threshold in dB. Signal levels above this will be compressed.
        ratio: Compression ratio (e.g., 4.0 means 4:1 compression).
        attack_ms: Attack time in milliseconds. How quickly the compressor reacts to signals above the threshold.
        release_ms: Release time in milliseconds. How quickly the compressor stops compressing after the signal falls below threshold.
        makeup_gain_db: Output gain applied after compression, in dB.
        knee_db: Width of the soft knee in dB. 0 for hard knee.

    Returns:
        The processed audio data (NumPy array).
    """
    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])  # Handle scalar input
    if audio_data.size == 0:
        return audio_data  # Handle empty input

    comp = Compressor(
        threshold_db, ratio, attack_ms, release_ms, makeup_gain_db, knee_db
    )
    processed_audio = comp.process_block(
        audio_data.astype(np.float64)
    )  # Work with float64 for precision

    # Ensure output dtype matches input if integer
    if np.issubdtype(audio_data.dtype, np.integer):
        processed_audio = np.clip(
            processed_audio,
            np.iinfo(audio_data.dtype).min,
            np.iinfo(audio_data.dtype).max,
        )

    return processed_audio.astype(audio_data.dtype)
