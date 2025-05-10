import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import iirpeak, lfilter


def allpass_sweep(y, sr, min_freq=300, max_freq=3000, sweep_rate=0.05):
    """Sweep an all-pass filter across the spectrum."""
    output = np.zeros_like(y)
    n_steps = len(y)
    for i in range(0, n_steps, sr // 20):
        progress = (np.sin(2 * np.pi * sweep_rate * (i / sr)) + 1) / 2
        fc = min_freq + progress * (max_freq - min_freq)
        w0 = fc / (sr / 2)
        # Simple first-order all-pass
        b = [-np.sin(w0), 1]
        a = [1, -np.sin(w0)]
        end = min(i + sr // 20, n_steps)
        output[i:end] = lfilter(b, a, y[i:end])
    return output


def resonant_peaks(y, sr, num_peaks=5):
    """Inject sharp resonant peaks at random frequencies."""
    output = np.copy(y)
    for _ in range(num_peaks):
        freq = np.random.uniform(200, 5000)
        Q = np.random.uniform(10, 30)
        b, a = iirpeak(freq / (0.5 * sr), Q)
        output = lfilter(b, a, output)
    return output


def recursive_blur(y, delay_samples=1000, feedback=0.5):
    """Recursive delay blur effect."""
    output = np.copy(y)
    for i in range(delay_samples, len(y)):
        output[i] += feedback * output[i - delay_samples]
    return output


def wavefold(y, threshold=0.3):
    """Wavefolding distortion."""
    folded = np.copy(y)
    above = np.abs(folded) > threshold
    folded[above] = threshold - (folded[above] - threshold)
    return folded


def microfade_slices(y, sr, slice_len=2048):
    """Apply tiny fades to each slice for a breathing texture."""
    fade_len = int(0.05 * slice_len)
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)
    output = np.copy(y)
    for i in range(0, len(y), slice_len):
        end = min(i + slice_len, len(y))
        if end - i < fade_len:
            continue
        output[i : i + fade_len] *= fade_in
        output[end - fade_len : end] *= fade_out
    return output


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: All-pass sweep
    print("Applying all-pass sweep...")
    y = allpass_sweep(y, sr, min_freq=300, max_freq=3000, sweep_rate=0.05)

    # Step 2: Resonant peaks
    print("Adding resonant peaks...")
    y = resonant_peaks(y, sr, num_peaks=5)

    # Step 3: Recursive blur
    print("Applying recursive blur...")
    y = recursive_blur(y, delay_samples=800, feedback=0.5)

    # Step 4: Wavefolding distortion
    print("Applying wavefolding...")
    y = wavefold(y, threshold=0.3)

    # Step 5: Microfade slicing
    print("Applying microfade slices...")
    y = microfade_slices(y, sr, slice_len=2048)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_ghosts.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    process_audio(sys.argv[1])
