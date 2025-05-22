import logging

from agents import (
    Agent,
    ModelSettings,
)

from phonosyne import settings
from phonosyne.agents.schemas import AnalyzerOutput  # Conceptual input schema
from phonosyne.tools import (
    run_supercollider_code,
    validate_audio_file,
)

logger = logging.getLogger(__name__)


class CompilerAgent(Agent):
    """Agent that compiles and analyzes code."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # The 'model' kwarg will be passed in by OrchestratorAgent.
        model_arg = kwargs.pop("model", settings.MODEL_COMPILER)
        logger.info(f"CompilerAgent initializing with model_arg: {model_arg!r}")

        # The tools available to this agent
        agent_tools = [
            run_supercollider_code,
            validate_audio_file,
        ]

        logger.info("Output directory for CompilerAgent: %s", settings.DEFAULT_OUT_DIR)

    # ... existing methods ...
