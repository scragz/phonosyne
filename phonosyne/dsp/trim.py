import logging

import librosa
import soundfile as sf

logger = logging.getLogger(__name__)


def trim_silence(input_path, output_path, top_db=40):
    """
    Trims silence from the beginning and end of an audio file.

    Args:
        input_path (str or Path): Path to the input audio file.
        output_path (str or Path): Path to save the trimmed audio file.
        top_db (int): The threshold (in decibels) below reference to consider as silence.
    """
    try:
        y, sr = librosa.load(input_path, sr=None, mono=True)

        # Trim leading and trailing silence
        # top_db=40 means any sound more than 40dB below the peak is considered silence
        y_trimmed, index = librosa.effects.trim(y, top_db=top_db)

        duration_before = len(y) / sr
        duration_after = len(y_trimmed) / sr

        logger.info(
            f"Trimmed {input_path}: {duration_before:.2f}s -> {duration_after:.2f}s"
        )

        # Save output
        sf.write(output_path, y_trimmed, sr)
        return True
    except Exception as e:
        logger.error(f"Error trimming {input_path}: {e}")
        return False
        return False
