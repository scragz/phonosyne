import os
import sys

import librosa
import numpy as np
import soundfile as sf


def compressor(y, threshold=0.2, ratio=4):
    """Simple dynamic range compressor."""
    compressed = np.copy(y)
    mask = np.abs(y) > threshold
    compressed[mask] = np.sign(y[mask]) * (
        threshold + (np.abs(y[mask]) - threshold) / ratio
    )
    return compressed


def limiter(y, limit=0.99):
    """Hard limiter to catch peaks."""
    return np.clip(y, -limit, limit)


def normalize(y):
    """Peak normalize the audio."""
    peak = np.max(np.abs(y))
    if peak == 0:
        return y
    return y / peak


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Compress
    print("Applying compression...")
    y = compressor(y, threshold=0.2, ratio=4)

    # Step 2: Limit
    print("Applying limiting...")
    y = limiter(y, limit=0.99)

    # Step 3: Normalize
    print("Applying normalization...")
    y = normalize(y)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_comp.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    process_audio(sys.argv[1])
