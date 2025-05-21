"""
Phonosyne Utilities Subpackage

This module initializes the `phonosyne.utils` subpackage and exports
key utility functions for use throughout the application.

Key features:
- Marks the 'phonosyne/utils' directory as a Python subpackage.
- Exports utility functions like `slugify` and `run_code`.

@dependencies
- Modules within this subpackage (e.g., `slugify`, `exec_env`).

@notes
- Functions will be imported here as they are implemented in their respective modules.
"""

# TODO: Import run_code from .exec_env once implemented
from .exec_env import SecurityException, run_supercollider_code

# TODO: Import slugify from .slugify once implemented
from .slugify import slugify
from .string_utils import extract_and_parse_json, extract_json_from_text

__all__ = [
    "slugify",
    "run_supercollider_code",
    "SecurityException",
    "extract_json_from_text",
    "extract_and_parse_json",
]
