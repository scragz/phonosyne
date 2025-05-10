import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter


def stutter_gate(y, sr, chunk_len=2048, repeats=3):
    """Stutter effect: repeat small chunks multiple times."""
    output = []
    for i in range(0, len(y), chunk_len):
        chunk = y[i : i + chunk_len]
        for _ in range(repeats):
            output.append(chunk)
    return np.concatenate(output)


def bandpass_sweep(y, sr, low=200, high=3000, sweep_rate=0.1):
    """Sweep a bandpass filter across frequency range."""
    output = np.zeros_like(y)
    n_steps = len(y)
    for i in range(0, n_steps, sr // 20):  # sweep chunk every ~0.05 sec
        progress = (np.sin(2 * np.pi * sweep_rate * (i / sr)) + 1) / 2
        cutoff = low + progress * (high - low)
        nyq = 0.5 * sr
        band = [max(10, cutoff - 100), min(nyq - 10, cutoff + 100)]
        b, a = butter(2, [band[0] / nyq, band[1] / nyq], btype="band")
        end = min(i + sr // 20, n_steps)
        output[i:end] = lfilter(b, a, y[i:end])
    return output


def random_polarity(y, sr, chunk_len=2048, chance=0.3):
    """Randomly invert polarity of chunks."""
    output = []
    for i in range(0, len(y), chunk_len):
        chunk = y[i : i + chunk_len]
        if np.random.rand() < chance:
            chunk = -chunk
        output.append(chunk)
    return np.concatenate(output)


def hard_clip(y, threshold=0.3):
    """Hard clipping at the given threshold."""
    return np.clip(y, -threshold, threshold)


def pulse_amplitude_mod(y, sr, rate=2.0, duty_cycle=0.5):
    """Square wave amplitude modulation."""
    lfo = (np.mod(np.arange(len(y)) * rate / sr, 1.0) < duty_cycle) * 1.0
    return y * lfo


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Stutter gate
    print("Applying stutter gate...")
    # y = stutter_gate(y, sr, chunk_len=int(0.02 * sr), repeats=3)

    # Step 2: Bandpass sweep
    print("Applying bandpass sweep...")
    # y = bandpass_sweep(y, sr, low=200, high=3000, sweep_rate=0.1)

    # Step 3: Random polarity inversion
    print("Applying random polarity inversion...")
    y = random_polarity(y, sr, chunk_len=int(0.05 * sr), chance=0.3)

    # Step 4: Hard clipping
    print("Applying hard clipping...")
    y = hard_clip(y, threshold=0.3)

    # Step 5: Pulse-width modulation
    print("Applying pulse-width amplitude modulation...")
    y = pulse_amplitude_mod(y, sr, rate=2.0, duty_cycle=0.5)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_fracture.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audio_fracture.py <audio_file>")
    else:
        process_audio(sys.argv[1])
