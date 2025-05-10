import os
import sys

import librosa
import numpy as np
import soundfile as sf


def granular_synthesis(y, sr, grain_size=2048):
    """Chop audio into small grains and shuffle them."""
    grains = [y[i : i + grain_size] for i in range(0, len(y), grain_size)]
    np.random.shuffle(grains)
    return np.concatenate(grains)


def spectral_freeze(y):
    """Freeze the magnitude spectrum across all frames."""
    S = librosa.stft(y)
    magnitude, phase = np.abs(S), np.angle(S)
    frozen_magnitude = np.mean(magnitude, axis=1, keepdims=True)
    S_frozen = frozen_magnitude * np.exp(1j * phase)
    return librosa.istft(S_frozen)


def bitcrusher(y, bit_depth=4):
    """Reduce bit depth to create a crushed/aliased effect."""
    max_val = np.max(np.abs(y))
    quantized = np.round(y / max_val * (2 ** (bit_depth - 1)))
    return quantized / (2 ** (bit_depth - 1)) * max_val


def amplitude_modulation(y, sr, rate=0.5):
    """Apply dynamic tremolo-like modulation using a low-frequency oscillator."""
    lfo = np.sin(2 * np.pi * rate * np.arange(len(y)) / sr)
    return y * (0.5 + 0.5 * lfo)


def process_audio(file_path):
    # Load the audio file
    y, sr = librosa.load(file_path, sr=None, mono=True)
    print(f"Loaded '{file_path}' (Length: {len(y)/sr:.2f}s, Sample rate: {sr} Hz)")

    # Step 1: Granular synthesis
    print("Applying granular synthesis...")
    y = granular_synthesis(y, sr, grain_size=int(0.05 * sr))

    # Step 2: Spectral freezing
    print("Applying spectral freeze...")
    # y = spectral_freeze(y)

    # Step 3: Bitcrushing
    print("Applying bitcrusher...")
    y = bitcrusher(y, bit_depth=4)

    # Step 4: Amplitude modulation (mono-friendly)
    print("Applying amplitude modulation...")
    # y = amplitude_modulation(y, sr)

    # Prepare output filename
    base, ext = os.path.splitext(file_path)
    output_path = f"{base}_crush.wav"

    # Save as mono WAV
    sf.write(output_path, y, sr)
    print(f"Saved processed audio to '{output_path}'")


if __name__ == "__main__":
    process_audio(sys.argv[1])
