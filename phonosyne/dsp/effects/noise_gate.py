import numpy as np

from phonosyne import settings


class NoiseGate:
    """
    A simple noise gate.
    """

    def __init__(
        self,
        sample_rate: int,  # This will be settings.DEFAULT_SR
        threshold_db: float = -50.0,
        attack_ms: float = 1.0,
        hold_ms: float = 10.0,
        release_ms: float = 20.0,
        attenuation_db: float = -96.0,
    ):  # How much to reduce signal when gate is closed
        self.sample_rate = sample_rate
        self.threshold_lin = 10 ** (threshold_db / 20.0)
        self.attack_samples = int(attack_ms / 1000.0 * sample_rate)
        self.hold_samples = int(hold_ms / 1000.0 * sample_rate)
        self.release_samples = int(release_ms / 1000.0 * sample_rate)
        self.attenuation_lin = 10 ** (attenuation_db / 20.0)

        self._envelope = 0.0  # Current envelope of the control signal (not the audio)
        self._gain = 1.0  # Current gain applied to audio (1.0 or attenuation_lin)
        self._state = "closed"  # "closed", "attack", "hold", "release"
        self._samples_in_state = 0

        # Coefficients for envelope smoothing (simple one-pole IIR)
        # Use attack for envelope rise, release for envelope fall for level detection
        self.env_attack_coeff = np.exp(
            -1.0 / (max(1, self.attack_samples) * 0.5)
        )  # Faster for detection
        self.env_release_coeff = np.exp(-1.0 / (max(1, self.release_samples) * 0.5))

    def process_sample(self, sample: float) -> float:
        input_level_lin = np.abs(sample)

        # Update envelope detector
        if input_level_lin > self._envelope:
            self._envelope = (
                self.env_attack_coeff * self._envelope
                + (1 - self.env_attack_coeff) * input_level_lin
            )
        else:
            self._envelope = (
                self.env_release_coeff * self._envelope
                + (1 - self.env_release_coeff) * input_level_lin
            )

        # State machine for gate logic
        current_state = self._state

        if current_state == "closed":
            if self._envelope > self.threshold_lin:
                self._state = "attack"
                self._samples_in_state = 0
                self._gain = self.attenuation_lin  # Start opening from fully attenuated
            else:
                self._gain = self.attenuation_lin  # Stay closed

        elif current_state == "attack":
            self._samples_in_state += 1
            if self.attack_samples > 0:
                self._gain = self.attenuation_lin + (1.0 - self.attenuation_lin) * (
                    self._samples_in_state / self.attack_samples
                )
            else:
                self._gain = 1.0  # Instant attack

            if self._gain >= 1.0:
                self._gain = 1.0
                self._state = "hold"
                self._samples_in_state = 0
            elif (
                self._envelope <= self.threshold_lin
            ):  # If signal drops during attack, go to release
                self._state = "release"
                self._samples_in_state = 0  # Start release from current gain

        elif current_state == "hold":
            self._samples_in_state += 1
            self._gain = 1.0  # Gate is open
            if self._envelope <= self.threshold_lin:
                if (
                    self._samples_in_state > self.hold_samples
                ):  # Check hold time only if signal is low
                    self._state = "release"
                    self._samples_in_state = 0
            else:  # Signal still above threshold, reset hold counter
                self._samples_in_state = 0

        elif current_state == "release":
            self._samples_in_state += 1
            if self.release_samples > 0:
                # Start release from current gain if coming from attack, or 1.0 if from hold
                # This logic was simplified: gain is already set when entering release from attack.
                # If coming from hold, gain was 1.0.
                # The gain at the start of release should be the gain when it triggered.
                # For simplicity, assume gain was 1.0 when release starts from hold/attack completion.
                # If release was triggered from attack phase, gain might be < 1.0.
                # This needs a more robust gain interpolation from the point it switched to release.
                # Let's assume gain is 1.0 when release starts for now.
                self._gain = 1.0 - (1.0 - self.attenuation_lin) * (
                    self._samples_in_state / self.release_samples
                )
            else:
                self._gain = self.attenuation_lin  # Instant release

            if self._gain <= self.attenuation_lin:
                self._gain = self.attenuation_lin
                self._state = "closed"
                self._samples_in_state = 0
            elif (
                self._envelope > self.threshold_lin
            ):  # Signal comes back up during release
                self._state = "attack"  # Re-trigger attack
                self._samples_in_state = 0
                # Gain should ramp up from current gain, not jump. This is a simplification.

        self._gain = np.clip(self._gain, self.attenuation_lin, 1.0)
        return sample * self._gain

    def process_block(self, audio_block: np.ndarray) -> np.ndarray:
        processed_block = np.copy(audio_block)
        if audio_block.ndim == 1:  # Mono
            for i in range(len(audio_block)):
                processed_block[i] = self.process_sample(audio_block[i])
        elif audio_block.ndim == 2:  # Stereo
            # For stereo, could use linked (max of L/R for envelope) or dual mono.
            # This is dual mono for simplicity.
            # To do linked, the envelope and state machine would be shared.
            # This requires a redesign of process_sample or a new stereo_process_sample.
            # For now, creating two independent gates for stereo.
            # This is NOT how it's usually done. A proper stereo gate has one detector.
            # This is a placeholder for a more correct stereo implementation.
            gate_l = NoiseGate(
                self.sample_rate,  # This is already correct
                20 * np.log10(self.threshold_lin),
                self.attack_samples * 1000 / self.sample_rate,
                self.hold_samples * 1000 / self.sample_rate,
                self.release_samples * 1000 / self.sample_rate,
                20 * np.log10(self.attenuation_lin),
            )
            gate_r = NoiseGate(
                self.sample_rate,  # This is already correct
                20 * np.log10(self.threshold_lin),
                self.attack_samples * 1000 / self.sample_rate,
                self.hold_samples * 1000 / self.sample_rate,
                self.release_samples * 1000 / self.sample_rate,
                20 * np.log10(self.attenuation_lin),
            )
            for i in range(audio_block.shape[0]):
                processed_block[i, 0] = gate_l.process_sample(audio_block[i, 0])
                processed_block[i, 1] = gate_r.process_sample(audio_block[i, 1])
        return processed_block


def apply_noise_gate(
    audio_data: np.ndarray,
    threshold_db: float = -50.0,
    attack_ms: float = 1.0,
    hold_ms: float = 10.0,
    release_ms: float = 20.0,
    attenuation_db: float = -96.0,
) -> np.ndarray:  # Changed return type
    """
    Applies a noise gate effect to audio data.

    Args:
        audio_data: NumPy array of the input audio.
        threshold_db: Gate threshold in dB. Signals below this (after hold) will be attenuated.
        attack_ms: Attack time in milliseconds. How quickly the gate opens.
        hold_ms: Hold time in milliseconds. How long the gate stays open after signal drops below threshold.
        release_ms: Release time in milliseconds. How quickly the gate closes.
        attenuation_db: Amount of gain reduction when the gate is closed, in dB (e.g., -96dB for near silence).

    Returns:
        The processed audio data (NumPy array). # Changed
    """
    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data  # Return ndarray

    gate = NoiseGate(
        settings.DEFAULT_SR,  # Use global sample rate
        threshold_db,
        attack_ms,
        hold_ms,
        release_ms,
        attenuation_db,
    )

    # Process with float64 for internal calculations
    original_dtype = audio_data.dtype
    processed_audio_float = gate.process_block(audio_data.astype(np.float64))

    if np.issubdtype(original_dtype, np.integer):
        processed_audio_float = np.clip(
            processed_audio_float,
            np.iinfo(original_dtype).min,
            np.iinfo(original_dtype).max,
        )

    return processed_audio_float.astype(original_dtype)  # Return ndarray
