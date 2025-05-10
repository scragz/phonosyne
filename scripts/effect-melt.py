import os
import sys

import librosa
import numpy as np
import soundfile as sf


def varispeed_stretch(y, sr, min_rate=0.8, max_rate=1.2, chunk_size=22050):
    """Apply random stretch factors to audio chunks."""
    segments = []
    for start in range(0, len(y), chunk_size):
        end = min(start + chunk_size, len(y))
        chunk = y[start:end]
        rate = np.random.uniform(min_rate, max_rate)
        stretched = (
            librosa.effects.time_stretch(chunk, rate=rate)
            if len(chunk) > 1000
            else chunk
        )
        segments.append(stretched)
    return np.concatenate(segments)


def inject_silences(y, sr, chance=0.1, silence_len=1024):
    """Randomly insert short silences."""
    output = []
    for i in range(0, len(y), silence_len):
        chunk = y[i : i + silence_len]
        if np.random.rand() < chance:
            output.append(np.zeros_like(chunk))
        else:
            output.append(chunk)
    return np.concatenate(output)


def convolve_smear(y, window_size=400):
    """Smudge waveform via convolution with a flat window."""
    window = np.ones(window_size) / window_size
    return np.convolve(y, window, mode="same")


def asymmetric_clip(y, pos_clip=0.4, neg_clip=-0.8):
    """Clip positive and negative values differently."""
    y_clipped = np.copy(y)
    y_clipped[y > pos_clip] = pos_clip
    y_clipped[y < neg_clip] = neg_clip
    return y_clipped


def decay_tail(y, sr, decay_time=2.0):
    """Apply soft decay toward the end."""
    tail_length = int(decay_time * sr)
    if len(y) < tail_length:
        return y
    fade = np.linspace(1, 0, tail_length)
    y[-tail_length:] *= fade
    return y


def process_audio(file_path):
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Varispeed time warping
    print("Applying varispeed stretch...")
    y = varispeed_stretch(y, sr, min_rate=0.8, max_rate=1.2, chunk_size=int(0.25 * sr))

    # Step 2: Silence injection
    print("Injecting silences...")
    y = inject_silences(y, sr, chance=0.1, silence_len=int(0.05 * sr))

    # Step 3: Smearing via convolution
    print("Smearing waveform...")
    y = convolve_smear(y, window_size=400)

    # Step 4: Asymmetric clipping
    print("Applying asymmetric clipping...")
    y = asymmetric_clip(y, pos_clip=0.4, neg_clip=-0.8)

    # Step 5: Decay envelope
    print("Applying decay tail...")
    y = decay_tail(y, sr, decay_time=2.0)

    # Save output
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_melt.wav"
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audio_melt.py <audio_file>")
    else:
        process_audio(sys.argv[1])
