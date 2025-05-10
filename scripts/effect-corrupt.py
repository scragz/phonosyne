import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter


def add_noise(y, noise_level=0.01):
    """Inject subtle white noise."""
    noise = np.random.normal(0, noise_level, y.shape)
    return y + noise


def compressor(y, threshold=0.2, ratio=4):
    """Simple dynamic range compressor."""
    compressed = np.copy(y)
    mask = np.abs(y) > threshold
    compressed[mask] = np.sign(y[mask]) * (
        threshold + (np.abs(y[mask]) - threshold) / ratio
    )
    return compressed


def spectral_gating(y, sr):
    """Randomly gate spectral bins for glitch effects."""
    S = librosa.stft(y)
    magnitude, phase = np.abs(S), np.angle(S)
    mask = np.random.rand(*magnitude.shape) > 0.9  # ~10% random dropouts
    magnitude[mask] = 0
    S_gated = magnitude * np.exp(1j * phase)
    return librosa.istft(S_gated)


def fast_tremolo(y, sr, rate=8.0):
    """Fast amplitude modulation."""
    lfo = np.sin(2 * np.pi * rate * np.arange(len(y)) / sr)
    return y * (0.5 + 0.5 * lfo)


def moving_highpass(y, sr, start_cutoff=100, end_cutoff=2000):
    """Sweep a high-pass filter across time."""
    output = np.zeros_like(y)
    n_steps = len(y)
    for i in range(0, n_steps, sr // 10):  # step every 0.1 sec
        progress = i / n_steps
        cutoff = start_cutoff + progress * (end_cutoff - start_cutoff)
        nyq = 0.5 * sr
        norm_cutoff = cutoff / nyq
        b, a = butter(2, norm_cutoff, btype="high", analog=False)
        end = min(i + sr // 10, n_steps)
        output[i:end] = lfilter(b, a, y[i:end])
    return output


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Add noise
    print("Adding noise...")
    # y = add_noise(y, noise_level=0.01)

    # Step 2: Compress
    print("Applying compression...")
    y = compressor(y, threshold=0.2, ratio=4)

    # Step 3: Spectral gating
    print("Applying spectral gating...")
    y = spectral_gating(y, sr)

    # Step 4: Fast tremolo
    print("Applying fast tremolo...")
    # y = fast_tremolo(y, sr, rate=8.0)

    # Step 5: High-pass sweep
    # print("Applying high-pass sweep...")
    # y = moving_highpass(y, sr, start_cutoff=100, end_cutoff=2000)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_corrupt.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    process_audio(sys.argv[1])
