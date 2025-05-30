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
MODEL_DEFAULT: str = "openai/gpt-4.1"
MODEL_ORCHESTRATOR: str = os.getenv("MODEL_ORCHESTRATOR", MODEL_DEFAULT)
MODEL_DESIGNER: str = os.getenv("MODEL_DESIGNER", MODEL_DEFAULT)
MODEL_ANALYZER: str = os.getenv("MODEL_ANALYZER", MODEL_DEFAULT)
MODEL_COMPILER: str = os.getenv("MODEL_COMPILER", MODEL_DEFAULT)

# Audio Processing Settings
DEFAULT_SR: int = 48_000  # Default sample rate in Hz
TARGET_PEAK_DBFS: float = -0.1  # Target peak level in dBFS for normalization
DURATION_TOLERANCE_S: float = 2  # Allowed duration tolerance in seconds
BIT_DEPTH: int = 32  # Bit depth for output WAV files (32-bit float)
DEFAULT_AUDIO_BLOCK_SIZE: int = (
    256  # Default block size for block-based audio processing
)
SILENCE_THRESHOLD_LINEAR: float = 10 ** (
    -100 / 20
)  # Linear threshold for silence detection

# File System Settings
DEFAULT_OUT_DIR: Path = Path("./output").absolute()
PROMPTS_DIR: Path = Path("./prompts")

# Agent & Compiler Settings
MAX_TURNS: int = 200

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

SCLANG_TIMEOUT_BUFFER_SECONDS: float = 5.0  # General buffer for sclang operations
SCLANG_STOP_PROCESSING_TIME_SECONDS: float = (
    5.0  # Time for sclang to process /stop OSC and finalize
)
SCLANG_SETUP_TIMEOUT_SECONDS: float = (
    10.0  # Increased timeout for sclang initial script setup
)
SCLANG_TERMINATE_TIMEOUT_SECONDS: float = (
    5.0  # Timeout for sclang process to terminate gracefully
)
SCLANG_KILL_TIMEOUT_SECONDS: float = (
    5.0  # Timeout for sclang process to die after being killed
)

# SuperCollider Server (scsynth) specific timeouts
SCSYNTH_BOOT_TIMEOUT_SECONDS: float = (
    10.0  # Timeout for scsynth to boot and become ready
)
SCSYNTH_TERMINATE_TIMEOUT_SECONDS: float = (
    5.0  # Timeout for scsynth process to terminate gracefully
)
SCSYNTH_KILL_TIMEOUT_SECONDS: float = (
    5.0  # Timeout for scsynth process to die after being killed
)
SCSYNTH_QUIT_GRACE_PERIOD_SECONDS: float = (
    3.0  # Increased time for scsynth to process OSC /quit before termination
)
