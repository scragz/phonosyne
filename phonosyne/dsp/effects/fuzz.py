import numpy as np

from phonosyne import settings


def apply_fuzz(
    audio_data: np.ndarray,
    fuzz_amount: float = 0.8,
    gain_db: float = 0.0,
    mix: float = 1.0,
) -> np.ndarray:
    """
    Applies a simple fuzz effect.
    Fuzz is typically achieved by heavily clipping the signal, often after significant gain,
    and can involve some filtering or non-linearities that emphasize even harmonics or intermodulation.
    This version uses a combination of gain, hard clipping, and a slight squaring to add harmonics.

    Args:
        audio_data: NumPy array of the input audio.
        fuzz_amount: Controls the intensity of the fuzz effect (0.0 to 1.0).
                     Higher values mean more gain before clipping and more squaring.
        gain_db: Output gain adjustment in dB after the fuzz effect.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        The processed audio data (NumPy array).
    """
    if not 0.0 <= fuzz_amount <= 1.0:
        raise ValueError("Fuzz amount must be between 0.0 and 1.0.")
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])
    if audio_data.size == 0:
        return audio_data

    original_dtype = audio_data.dtype
    audio_float = audio_data.astype(np.float64)

    # Apply significant gain based on fuzz_amount. Max gain 1 + 49*1 = 50x
    input_gain = 1.0 + fuzz_amount * 49.0
    gained_audio = audio_float * input_gain

    # Introduce non-linearity: squaring the signal can add even harmonics before clipping.
    # This is a very simplified way to emulate some fuzz characteristics.
    # Amount of squaring also controlled by fuzz_amount.
    # (1 - fuzz_amount) * x + fuzz_amount * x^2 (approx, needs normalization)
    # Let's try: x_processed = (1-fuzz_amount*0.5)*x + (fuzz_amount*0.5)*sign(x)*x^2 to keep polarity
    # This can make signal very large, so clipping is essential.
    # A simpler approach: just heavy clipping after gain.
    # For a bit more character, let's try a non-linear shaping before final clipping.
    # One common fuzz technique is to bias and clip, or use transistor-like curves.

    # Simplified fuzz: hard clipping after gain.
    # To make it more "fuzzy" than simple distortion, the gain is usually much higher.
    # Let's use a slightly softer clipping than pure hard clipping for a bit of character.
    # A common fuzz equation: y = (x/|x|) * (1 - exp(-gain*|x|)) (if x != 0)
    # This is a type of soft clipper that becomes harder with more gain.

    # For this implementation, let's try a variation of hard clipping with some asymmetry
    # or a specific non-linear function. A common fuzz sound comes from germanium transistors.
    # A very basic fuzz: high gain -> clip -> (optional) filter

    # Let's use a simple hard clip, but the high gain is key for fuzz.
    # Threshold for clipping, fuzz often clips hard.
    fuzz_threshold = (
        0.7 + (1.0 - fuzz_amount) * 0.3
    )  # Higher fuzz_amount = lower threshold = harder fuzz
    fuzzed_signal = np.clip(gained_audio, -fuzz_threshold, fuzz_threshold)

    # Optional: Add a slight squaring component for more harmonics, scaled by fuzz_amount
    # This needs to be handled carefully to avoid excessive DC offset or extreme levels.
    if fuzz_amount > 0.5:
        # Apply squaring to the already clipped signal to further shape it.
        # This is a very artificial way to add some buzz.
        square_component = fuzzed_signal**2
        if fuzzed_signal.ndim == 1:
            square_component *= np.sign(
                fuzzed_signal
            )  # Preserve original polarity somewhat
        elif fuzzed_signal.ndim == 2:
            square_component *= np.sign(fuzzed_signal)

        # Mix in the squared component, scaled by fuzz_amount
        # This is experimental and might need tuning.
        fuzzed_signal = (1 - fuzz_amount * 0.3) * fuzzed_signal + (
            fuzz_amount * 0.3
        ) * square_component
        # Renormalize/clip again as squaring can change levels significantly
        max_abs = np.max(np.abs(fuzzed_signal))
        if max_abs > 0:
            fuzzed_signal = (
                fuzzed_signal / max_abs * fuzz_threshold
            )  # Scale back to threshold

    # Apply output gain adjustment
    output_gain_lin = 10 ** (gain_db / 20.0)
    fuzzed_signal *= output_gain_lin

    # Mix dry and wet
    processed_audio = audio_float * (1.0 - mix) + fuzzed_signal * mix

    if np.issubdtype(original_dtype, np.integer):
        max_val = np.iinfo(original_dtype).max
        min_val = np.iinfo(original_dtype).min
        processed_audio = np.clip(processed_audio, min_val, max_val)
    else:  # Float output
        processed_audio = np.clip(processed_audio, -1.0, 1.0)

    return processed_audio.astype(original_dtype)
