"""
Phonosyne Package Initializer

This module initializes the Phonosyne package and will export key functionalities
such as `run_prompt`.

Key features:
- Marks the 'phonosyne' directory as a Python package.
- Will serve as the main entry point for importing package components.

@dependencies
- None directly at this stage, but will depend on other modules within the package.

@notes
- The `run_prompt` function will be implemented and imported here in a later step (Step 5.2).
"""

# TODO: Implement and import run_prompt in Step 5.2
from typing import Any, Dict, Optional

from .orchestrator import Manager  # Import the Manager class


def run_prompt(
    prompt: str,
    num_workers: Optional[int] = None,
    verbose: bool = False,
    **kwargs: Any,  # To catch any other potential future manager args
) -> Dict[str, Any]:
    """
    Main SDK entry point to run the Phonosyne generation pipeline.

    Args:
        prompt: The user's natural-language sound design brief.
        num_workers: Optional number of parallel workers to use.
                     If None, uses default from settings or CPU count.
                     0 means serial execution.
        verbose: If True, enables more detailed logging.
        **kwargs: Additional keyword arguments for future flexibility.

    Returns:
        A dictionary summarizing the outcome of the generation process,
        as returned by Manager.run().
    """
    manager = Manager(num_workers=num_workers, verbose=verbose)
    return manager.run(user_brief=prompt)


__version__ = "0.1.0"

__all__ = [
    "run_prompt",
    "Manager",  # Optionally export Manager if direct use is desired
    "__version__",
]
