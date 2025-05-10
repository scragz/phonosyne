import os
import sys

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter


def multi_tap_delay(y, sr, delays=[0.1, 0.25, 0.5], decays=[0.5, 0.3, 0.2]):
    """Apply multi-tap delay (echoes)."""
    output = np.copy(y)
    for d, decay in zip(delays, decays):
        delay_samples = int(d * sr)
        delayed = np.zeros_like(output)
        delayed[delay_samples:] = y[:-delay_samples]
        output += decay * delayed
    return output


def comb_filter(y, delay_samples=500, decay=0.7):
    """Apply a comb filter (hollow/metallic)."""
    output = np.copy(y)
    for i in range(delay_samples, len(y)):
        output[i] += decay * output[i - delay_samples]
    return output


def envelope_follower(y, window_size=1024):
    """Use amplitude envelope to modulate itself (ducking feel)."""
    envelope = np.abs(y)
    smoothed = np.convolve(envelope, np.ones(window_size) / window_size, mode="same")
    return y * (0.5 + 0.5 * smoothed / np.max(smoothed))


def phase_inversion_bursts(y, chunk_size=4410):
    """Invert phase randomly in chunks."""
    output = np.copy(y)
    for start in range(0, len(y), chunk_size):
        if np.random.rand() > 0.5:
            output[start : start + chunk_size] *= -1
    return output


def lowpass_sweep(y, sr, start_cutoff=8000, end_cutoff=500):
    """Sweep a low-pass filter downward over time."""
    output = np.zeros_like(y)
    n_steps = len(y)
    for i in range(0, n_steps, sr // 10):  # 0.1 sec steps
        progress = i / n_steps
        cutoff = start_cutoff - progress * (start_cutoff - end_cutoff)
        nyq = 0.5 * sr
        norm_cutoff = cutoff / nyq
        b, a = butter(2, norm_cutoff, btype="low", analog=False)
        end = min(i + sr // 10, n_steps)
        output[i:end] = lfilter(b, a, y[i:end])
    return output


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Multi-tap delay
    print("Applying multi-tap delay...")
    y = multi_tap_delay(y, sr, delays=[0.15, 0.3, 0.45], decays=[0.6, 0.4, 0.25])

    # Step 2: Comb filter
    print("Applying comb filter...")
    y = comb_filter(y, delay_samples=int(0.02 * sr), decay=0.7)

    # Step 3: Envelope follower
    print("Applying envelope follower...")
    y = envelope_follower(y, window_size=1024)

    # Step 4: Phase inversion bursts
    print("Applying phase inversion bursts...")
    y = phase_inversion_bursts(y, chunk_size=int(0.05 * sr))

    # Step 5: Low-pass sweep
    print("Applying low-pass sweep...")
    y = lowpass_sweep(y, sr, start_cutoff=6000, end_cutoff=500)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_echoes.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audio_echoes.py <audio_file>")
    else:
        process_audio(sys.argv[1])
