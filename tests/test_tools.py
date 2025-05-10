"""
Unit tests for FunctionTools in phonosyne.tools.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from phonosyne.agents.schemas import AnalyzerOutput  # For validate_audio_file test
from phonosyne.dsp.validators import (
    ValidationFailedError,  # For validate_audio_file test
)

# Import the tools to be tested
from phonosyne.tools import (
    execute_python_dsp_code,
    generate_manifest_file,
    move_file,
    validate_audio_file,
)
from phonosyne.utils.exec_env import (
    CodeExecutionError,  # For execute_python_dsp_code test
)


@pytest.mark.asyncio
async def test_execute_python_dsp_code_success():
    """Test successful execution of Python DSP code."""
    mock_code = "print('hello')"
    mock_output_filename = "test_output.wav"
    expected_wav_path = Path("/tmp/exec_env_output/test_output.wav")

    with patch("phonosyne.tools.existing_run_code") as mock_run_code:
        mock_run_code.return_value = expected_wav_path

        result = await execute_python_dsp_code(mock_code, mock_output_filename)

        mock_run_code.assert_called_once_with(
            code=mock_code, output_filename=mock_output_filename, mode="local_executor"
        )
        assert result == str(expected_wav_path)


@pytest.mark.asyncio
async def test_execute_python_dsp_code_execution_error():
    """Test CodeExecutionError during DSP code execution."""
    mock_code = "raise ValueError('bad code')"
    mock_output_filename = "error_output.wav"
    error_message = "Simulated CodeExecutionError"

    with patch("phonosyne.tools.existing_run_code") as mock_run_code:
        mock_run_code.side_effect = CodeExecutionError(error_message)

        result = await execute_python_dsp_code(mock_code, mock_output_filename)

        mock_run_code.assert_called_once_with(
            code=mock_code, output_filename=mock_output_filename, mode="local_executor"
        )
        assert result == f"CodeExecutionError: {error_message}"


@pytest.mark.asyncio
async def test_execute_python_dsp_code_unexpected_error():
    """Test unexpected Exception during DSP code execution."""
    mock_code = "import os; os.exit(1)"
    mock_output_filename = "unexpected_error.wav"
    error_message = "Simulated unexpected error"

    with patch("phonosyne.tools.existing_run_code") as mock_run_code:
        mock_run_code.side_effect = Exception(error_message)

        result = await execute_python_dsp_code(mock_code, mock_output_filename)

        mock_run_code.assert_called_once_with(
            code=mock_code, output_filename=mock_output_filename, mode="local_executor"
        )
        assert result == f"Unexpected error during code execution: {error_message}"


# Tests for validate_audio_file, move_file, and generate_manifest_file will be added next.
