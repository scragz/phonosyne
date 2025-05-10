"""
Phonosyne Settings

This module contains global constants and configuration settings for the Phonosyne application.
These settings control various aspects of the sound generation pipeline, including
LLM models, audio parameters, file output, and execution behavior.

Key features:
- Centralized configuration for easy management.
- Defines default models for different agent stages.
- Specifies audio characteristics like sample rate.
- Sets operational limits like timeouts and iteration counts.

@dependencies
- `pathlib.Path` for defining file system paths.

@notes
- These constants can be overridden if necessary, though the primary mechanism
  for user-specific configuration (like API keys) is via .env files.
- Model names should correspond to valid identifiers on the configured LLM provider (e.g., OpenRouter).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# LLM Model Configuration
MODEL_DEFAULT: str = os.getenv("MODEL_DEFAULT", "openai/gpt-4.1")
MODEL_ORCHESTRATOR: str = os.getenv("MODEL_ORCHESTRATOR", MODEL_DEFAULT)
MODEL_DESIGNER: str = os.getenv("MODEL_DESIGNER", MODEL_DEFAULT)
MODEL_ANALYZER: str = os.getenv("MODEL_ANALYZER", MODEL_DEFAULT)
MODEL_COMPILER: str = os.getenv("MODEL_COMPILER", "openai/o4-mini")

# Audio Processing Settings
DEFAULT_SR: int = 48_000  # Default sample rate in Hz
TARGET_PEAK_DBFS: float = -1.0  # Target peak level in dBFS for normalization
DURATION_TOLERANCE_S: float = 0.5  # Allowed duration tolerance in seconds
BIT_DEPTH: int = 32  # Bit depth for output WAV files (32-bit float)

# File System Settings
DEFAULT_OUT_DIR: Path = Path("./output")
PROMPTS_DIR: Path = Path("./prompts")

# Agent & Compiler Settings
MAX_TURNS: int = 50
MAX_COMPILER_ITERATIONS: int = (
    10  # Maximum attempts for the CompilerAgent to generate valid code
)
COMPILER_TIMEOUT_S: int = 300  # Timeout in seconds for a single compiler execution run
AGENT_MAX_RETRIES: int = 3  # Maximum retries for an agent call if it fails

# Execution Environment
# Supported modes: "subprocess", "inline"
# "subprocess": Executes generated code in a sandboxed Python subprocess. Safer.
# "inline": Executes generated code using exec() in the current process. Faster, for testing.
EXECUTION_MODE: str = os.getenv("PHONOSYNE_EXECUTION_MODE", "subprocess")
MAX_LLM_CODE_OPERATIONS: int = int(
    os.getenv("MAX_LLM_CODE_OPERATIONS", 50_000_000)
)  # Max operations for LocalPythonExecutor
MAX_ORCHESTRATOR_SAMPLE_RETRIES: int = int(
    os.getenv("MAX_ORCHESTRATOR_SAMPLE_RETRIES", 2)
)  # Max retries for a single sample if compilation fails

# Concurrency
# Default number of worker processes for parallel tasks.
# Can be overridden by --workers CLI flag or PHONOSYNE_WORKERS env var.
DEFAULT_WORKERS: int = min(os.cpu_count() or 1, 8)

# API Keys - typically loaded from .env
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

# OpenRouter Configuration
OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
# You can set a preferred default model via environment variable,
# or change the fallback string literal below.
DEFAULT_OPENROUTER_MODEL_NAME: str = os.getenv(
    "OPENROUTER_MODEL_NAME", "mistralai/mistral-7b-instruct"  # Example fallback
)

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: Path | None = (
    None  # Set to a Path object to enable file logging, e.g., Path("phonosyne.log")
)

# UI/UX
USE_ANSI_COLORS: bool = os.getenv("NO_COLOR") is None and os.getenv("TERM") != "dumb"
