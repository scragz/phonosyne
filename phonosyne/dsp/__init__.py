"""
Phonosyne DSP Subpackage

This module initializes the `phonosyne.dsp` subpackage.
It will export DSP utility functions (oscillators, envelopes, etc. - from skipped Step 4.1)
and audio validation functions.

Key features:
- Marks the 'phonosyne/dsp' directory as a Python subpackage.
- Will export `validate_wav` from `validators.py`.
- Would export DSP helper functions from `utils.py` if it were implemented.

@dependencies
- Modules within this subpackage (e.g., `validators`, `utils`).

@notes
- DSP utility functions from `phonosyne.dsp.utils` (Step 4.1) are currently skipped.
  If implemented later, they would be exported here.
"""

# TODO: Import and export validate_wav from .validators (Step 4.2)
from .validators import ValidationFailedError, validate_wav

# TODO: Import and export DSP utilities from .utils if Step 4.1 is implemented
# from .utils import ...

__all__ = [
    "validate_wav",
    "ValidationFailedError",
    # Add names of DSP util functions here if implemented
]
