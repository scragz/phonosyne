import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d


def downsample(y, factor=4):
    """Reduce sample rate by decimation."""
    return y[::factor]


def spectral_smear(y, size=10):
    """Blur the magnitude spectrum to smear transients."""
    S = librosa.stft(y)
    magnitude, phase = np.abs(S), np.angle(S)
    smeared = uniform_filter1d(magnitude, size=size, axis=1)
    S_smeared = smeared * np.exp(1j * phase)
    return librosa.istft(S_smeared)


def nonlinear_distort(y, amount=20):
    """Apply aggressive wave-shaping distortion."""
    return np.tanh(y * amount)


def reverse_segments(y, segment_length=4410):
    """Flip audio in segments (e.g., ~0.1s at 44.1kHz)."""
    output = np.copy(y)
    for start in range(0, len(y), segment_length):
        end = min(start + segment_length, len(y))
        output[start:end] = output[start:end][::-1]
    return output


def fade_pulse(y, sr, rate=0.25):
    """Slow fade in/out modulation (breathing effect)."""
    lfo = (np.sin(2 * np.pi * rate * np.arange(len(y)) / sr) + 1) / 2
    return y * (0.8 + 0.2 * lfo)


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Downsample (light crunch)
    print("Downsampling...")
    y = downsample(y, factor=2)
    # Upsample back to original length (stretch to match original)
    y = librosa.resample(y, orig_sr=sr // 2, target_sr=sr)

    # Step 2: Spectral smear
    print("Applying spectral smear...")
    y = spectral_smear(y, size=30)

    # Step 3: Distortion
    print("Applying nonlinear distortion...")
    y = nonlinear_distort(y, amount=15)

    # Step 4: Reverse segments
    print("Reversing segments...")
    y = reverse_segments(y, segment_length=int(0.1 * sr))

    # Step 5: Fade pulse
    print("Applying fade pulse...")
    y = fade_pulse(y, sr, rate=0.25)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_warp.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    process_audio(sys.argv[1])
