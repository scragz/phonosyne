import numpy as np


def unpack_audio_input(audio_data):
    """
    Unpacks audio_data if it's a tuple from a previous effect, returning only the array.

    Args:
        audio_data: The audio data, which might be a NumPy array or a tuple
                    (np.ndarray, int) from a previous effect.

    Returns:
        A np.ndarray. If input was a tuple (array, sr), it returns the array.
        Otherwise, it returns the input as is (assuming it's already an array).
    """
    if (
        isinstance(audio_data, tuple)
        and len(audio_data) == 2
        and isinstance(audio_data[0], np.ndarray)
        and isinstance(audio_data[1], int)
    ):
        # If audio_data is (np_array, sr_int), return just the np_array.
        return audio_data[0]
    # Otherwise, assume audio_data is already a np_array.
    return audio_data
