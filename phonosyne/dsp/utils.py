import numpy as np


def unpack_audio_input(audio_data, sample_rate):
    """
    Unpacks audio_data if it's a tuple from a previous effect.

    Args:
        audio_data: The audio data, which might be a NumPy array or a tuple
                    (np.ndarray, int) from a previous effect.
        sample_rate: The default sample rate if audio_data is not a tuple.

    Returns:
        A tuple (np.ndarray, int) of the audio data and its sample rate.
    """
    if (
        isinstance(audio_data, tuple)
        and len(audio_data) == 2
        and isinstance(audio_data[0], np.ndarray)
        and isinstance(audio_data[1], int)
    ):
        # If audio_data is (np_array, sr_int), use those.
        return audio_data[0], audio_data[1]
    # Otherwise, assume audio_data is a np_array and use the provided sample_rate.
    return audio_data, sample_rate
