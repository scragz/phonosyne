import numpy as np

from .delay import apply_delay


def apply_echo(
    audio_data: np.ndarray,
    sample_rate: int,
    echo_time_s: float = 0.5,
    feedback: float = 0.4,
    mix: float = 0.5,
) -> tuple[np.ndarray, int]:
    """
    Applies a simple echo effect.
    This is essentially a delay with feedback.

    Args:
        audio_data: NumPy array of the input audio.
        sample_rate: Sample rate of the audio in Hz.
        echo_time_s: Time for each echo repetition in seconds.
        feedback: Feedback gain (0.0 to <1.0), determining how many echoes are heard.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        A tuple containing the processed audio data (NumPy array) and the sample rate (int).
    """
    return apply_delay(
        audio_data, sample_rate, delay_time_s=echo_time_s, feedback=feedback, mix=mix
    )
