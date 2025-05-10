"""
Phonosyne CLI Wrapper Script

This script provides a convenient way to run the Phonosyne CLI,
especially during development or if the package's entry points are not yet
installed/configured on the system PATH.

It directly invokes the Typer application defined in `phonosyne.cli`.

To use:
    python scripts/phonosyne_cli.py run --prompt "your sound brief"
"""

import sys
from pathlib import Path

# Add the project root to sys.path to allow importing 'phonosyne'
# This assumes the script is in 'scripts/' and the 'phonosyne' package is one level up.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from phonosyne.cli import app  # Import the Typer app

if __name__ == "__main__":
    app()
