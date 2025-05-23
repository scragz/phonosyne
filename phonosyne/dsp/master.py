import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy import signal


def apply_saturation(y, drive_db):
    """Applies soft saturation to the audio signal."""
    gain_linear = 10 ** (drive_db / 20.0)
    y_driven = y * gain_linear
    y_saturated = np.tanh(y_driven)
    # Rescale to roughly original peak levels if drive is not too high,
    # or let normalize handle it. For now, tanh output is [-1, 1].
    # If gain_linear > 1, this will boost and then clip via tanh.
    # To preserve overall level better before normalization, we might scale back:
    if gain_linear > 0:  # Avoid division by zero
        y_saturated = y_saturated / gain_linear
        # This simple rescale might not be ideal, as tanh changes dynamics.
        # A more common approach is to ensure the output of tanh is scaled
        # to fit within a certain range or match input RMS, but for now,
        # we rely on the final normalization step.
        # Let's stick to the simpler version and let normalize do its job:
    y_saturated = np.tanh(y_driven)  # Output is in [-1, 1] if y_driven is large
    return y_saturated


def apply_band_compression(y_band, sr, threshold_db, ratio, attack_ms, release_ms):
    """Applies dynamic range compression to a single audio band."""
    if ratio <= 0:  # Ratio must be positive
        return y_band  # Or raise an error

    threshold_linear = 10 ** (threshold_db / 20.0)

    # Attack and release samples
    # Ensure attack/release times are at least 1 sample to avoid issues with exp(0) or division by zero
    attack_samples = max(1, (attack_ms / 1000.0) * sr)
    release_samples = max(1, (release_ms / 1000.0) * sr)

    alpha_attack = np.exp(-1.0 / attack_samples)
    alpha_release = np.exp(-1.0 / release_samples)

    envelope = np.zeros_like(y_band)
    gain_reduction = np.zeros_like(y_band)

    # RMS detection might be better, but peak detection is simpler for now
    # For peak detection, use absolute values
    abs_signal = np.abs(y_band)

    # Envelope detection
    current_level = 0.0
    for i in range(len(y_band)):
        if abs_signal[i] > current_level:
            current_level = (
                alpha_attack * current_level + (1 - alpha_attack) * abs_signal[i]
            )
        else:
            current_level = (
                alpha_release * current_level + (1 - alpha_release) * abs_signal[i]
            )
        envelope[i] = current_level

    # Gain computation
    # Avoid log10(0) by adding a small epsilon
    envelope_db = 20 * np.log10(envelope + 1e-12)

    # Calculate gain reduction in dB
    # If envelope_db is below threshold_db, overshoot_db is negative, no compression
    overshoot_db = envelope_db - threshold_db

    # Apply compression only when signal is above threshold
    # Gain reduction is negative or zero
    if ratio == 1.0:  # No compression if ratio is 1
        gain_reduction_db = np.zeros_like(overshoot_db)
    else:
        gain_reduction_db = np.where(
            overshoot_db > 0, overshoot_db * (1.0 / ratio - 1.0), 0
        )

    # Convert gain reduction to linear scale
    makeup_gain_linear = 10 ** (gain_reduction_db / 20.0)

    y_compressed = y_band * makeup_gain_linear
    return y_compressed


def apply_multiband_compression(
    y, sr, crossover_frequencies_hz, thresholds_db, ratios, attack_ms, release_ms
):
    """Applies multiband compression to the audio signal."""
    num_bands = len(crossover_frequencies_hz) + 1
    filter_order = 4  # 4th order Butterworth filters

    if not (
        len(thresholds_db) == num_bands
        and len(ratios) == num_bands
        and len(attack_ms) == num_bands
        and len(release_ms) == num_bands
    ):
        raise ValueError("Parameter lists must have length equal to num_bands.")

    # Normalize crossover frequencies
    nyquist = 0.5 * sr
    norm_crossovers = [f / nyquist for f in crossover_frequencies_hz]

    bands = []

    # Low band
    sos_low = signal.butter(
        filter_order, norm_crossovers[0], btype="lowpass", output="sos"
    )
    low_band = signal.sosfilt(sos_low, y)
    bands.append(
        apply_band_compression(
            low_band, sr, thresholds_db[0], ratios[0], attack_ms[0], release_ms[0]
        )
    )

    # Mid bands
    for i in range(len(norm_crossovers) - 1):
        sos_mid = signal.butter(
            filter_order,
            [norm_crossovers[i], norm_crossovers[i + 1]],
            btype="bandpass",
            output="sos",
        )
        mid_band = signal.sosfilt(sos_mid, y)
        bands.append(
            apply_band_compression(
                mid_band,
                sr,
                thresholds_db[i + 1],
                ratios[i + 1],
                attack_ms[i + 1],
                release_ms[i + 1],
            )
        )

    # High band
    sos_high = signal.butter(
        filter_order, norm_crossovers[-1], btype="highpass", output="sos"
    )
    high_band = signal.sosfilt(sos_high, y)
    bands.append(
        apply_band_compression(
            high_band, sr, thresholds_db[-1], ratios[-1], attack_ms[-1], release_ms[-1]
        )
    )

    # Sum processed bands
    y_processed = np.sum(bands, axis=0)
    return y_processed


def limiter(y, limit=0.99):
    """Hard limiter to catch peaks."""
    return np.clip(y, -limit, limit)


def normalize(y):
    """Peak normalize the audio."""
    peak = np.max(np.abs(y))
    if peak == 0:
        return y
    return y / peak


def apply_mastering(file_path, output_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 0: Normalize
    print("Normalizing audio...")
    y = normalize(y)

    # Step 1: Saturation
    print("Applying saturation...")
    drive_db = 6.0
    y = apply_saturation(y, drive_db=drive_db)
    print(
        f"Saturation applied. Min/Max after saturation: {np.min(y):.2f}/{np.max(y):.2f}"
    )

    # Step 2: Multiband Compression
    print("Applying multiband compression...")
    crossover_freqs = [150, 800, 4000]  # Defines 4 bands
    # Parameters for each band (Low, Low-Mid, High-Mid, High)
    thresholds = [-24.0, -20.0, -18.0, -15.0]
    comp_ratios = [2.0, 2.5, 3.0, 3.5]
    attack_times = [10.0, 8.0, 5.0, 3.0]
    release_times = [150.0, 120.0, 100.0, 80.0]

    y = apply_multiband_compression(
        y,
        sr,
        crossover_frequencies_hz=crossover_freqs,
        thresholds_db=thresholds,
        ratios=comp_ratios,
        attack_ms=attack_times,
        release_ms=release_times,
    )
    print(
        f"Multiband compression applied. Min/Max after compression: {np.min(y):.2f}/{np.max(y):.2f}"
    )

    # Step 3: Limit (using existing function)
    print("Applying limiting...")
    y = limiter(y, limit=0.98)  # Adjusted limit slightly
    print(f"Limiting applied. Min/Max after limiting: {np.min(y):.2f}/{np.max(y):.2f}")

    # Step 4: Normalize (using existing function)
    print("Applying normalization...")
    y = normalize(y)
    print(
        f"Normalization applied. Min/Max after normalization: {np.min(y):.2f}/{np.max(y):.2f}"
    )

    # Save output
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    apply_mastering(sys.argv[1], sys.argv[2])
