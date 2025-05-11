import numpy as np

from phonosyne import settings


def apply_delay(
    audio_data: np.ndarray,
    delay_time_s: float,
    feedback: float = 0.3,
    mix: float = 0.5,
) -> np.ndarray:
    """
    Applies a delay effect to audio data.

    Args:
        audio_data: NumPy array of the input audio. Assumed to be mono (1D) or stereo (2D, channels last).
        delay_time_s: Delay time in seconds.
        feedback: Feedback gain (0.0 to <1.0).
        mix: Wet/dry mix (0.0 dry to 1.0 wet).

    Returns:
        The processed audio data (NumPy array).
    """
    if not 0.0 <= feedback < 1.0:
        raise ValueError("Feedback must be between 0.0 and just under 1.0.")
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Mix must be between 0.0 and 1.0.")

    delay_samples = int(delay_time_s * settings.DEFAULT_SR)

    # Ensure audio_data is at least 1D
    if audio_data.ndim == 0:
        audio_data = np.array([audio_data])

    processed_audio = np.copy(audio_data)

    if delay_samples <= 0:
        # No delay, return mixed original signal (effectively just scaling if mix < 1)
        return (audio_data * (1 - mix) + processed_audio * mix).astype(audio_data.dtype)

    if audio_data.ndim == 1:  # Mono
        delay_buffer = np.zeros(delay_samples, dtype=audio_data.dtype)
        for i in range(len(audio_data)):
            delayed_sample = delay_buffer[-1]
            output_sample = audio_data[i] * (1 - mix) + delayed_sample * mix

            new_buffer_input = audio_data[i] + delayed_sample * feedback
            delay_buffer = np.roll(delay_buffer, 1)
            delay_buffer[0] = new_buffer_input
            processed_audio[i] = output_sample

    elif audio_data.ndim == 2:  # Stereo (samples, channels)
        num_channels = audio_data.shape[1]
        delay_buffers = [
            np.zeros(delay_samples, dtype=audio_data.dtype) for _ in range(num_channels)
        ]

        for i in range(audio_data.shape[0]):  # Iterate over samples
            for ch in range(num_channels):
                delayed_sample = delay_buffers[ch][-1]
                output_sample = audio_data[i, ch] * (1 - mix) + delayed_sample * mix

                new_buffer_input = audio_data[i, ch] + delayed_sample * feedback
                delay_buffers[ch] = np.roll(delay_buffers[ch], 1)
                delay_buffers[ch][0] = new_buffer_input
                processed_audio[i, ch] = output_sample
    else:
        raise ValueError("Audio data must be 1D (mono) or 2D (stereo, channels last).")

    return processed_audio
