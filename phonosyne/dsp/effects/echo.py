import numpy as np

from phonosyne import settings

from .delay import apply_delay


def apply_echo(
    audio_data: np.ndarray,
    echo_time_s: float = 0.5,
    feedback: float = 0.4,
    mix: float = 0.5,
) -> np.ndarray:  # Changed return type
    """
    Applies a simple echo effect.
    This is essentially a delay with feedback.

    Args:
        audio_data: NumPy array of the input audio.
        echo_time_s: Time for each echo repetition in seconds.
        feedback: Feedback gain (0.0 to <1.0), determining how many echoes are heard.
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        The processed audio data (NumPy array).  # Changed return type in docstring
    """
    # apply_delay will now use settings.DEFAULT_SR internally and return only the array
    return apply_delay(  # Removed sample_rate argument
        audio_data, delay_time_s=echo_time_s, feedback=feedback, mix=mix
    )
