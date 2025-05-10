"""
Phonosyne SDK Implementation

This module contains the core SDK logic for Phonosyne, including the
`run_prompt` function and the configuration for using OpenRouter.
"""

import asyncio
import os
from typing import Any

from agents import (
    Model,
    ModelProvider,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    set_tracing_disabled,
)
from openai import AsyncOpenAI

from . import settings  # Import the settings module

# Import the OrchestratorAgent from its location
# Assuming it's in .agents.orchestrator relative to the phonosyne package root
# from .agents.orchestrator import OrchestratorAgent # Moved to run_prompt

# --- OpenRouter Configuration (sourced from settings) ---
if not settings.OPENROUTER_API_KEY:
    raise ValueError(
        "OPENROUTER_API_KEY is not set in environment variables or .env file. "
        "Please set it to your OpenRouter API key. It should be loaded via phonosyne.settings."
    )

openrouter_client = AsyncOpenAI(
    base_url=settings.OPENROUTER_BASE_URL,
    api_key=settings.OPENROUTER_API_KEY,
    default_headers={
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/scragz/phonosyne",
        "X-Title": "Phonosyne",
    },
)

set_tracing_disabled(disabled=False)


class OpenRouterModelProvider(ModelProvider):
    """
    A custom model provider that directs LLM calls to OpenRouter.
    """

    def get_model(self, model_name: str | None) -> Model:
        """
        Provides an OpenAIChatCompletionsModel configured for OpenRouter.
        Uses DEFAULT_OPENROUTER_MODEL_NAME from settings if model_name is None.
        """
        effective_model_name = model_name or settings.DEFAULT_OPENROUTER_MODEL_NAME
        return OpenAIChatCompletionsModel(
            model=effective_model_name,
            openai_client=openrouter_client,
        )


OPENROUTER_MODEL_PROVIDER = OpenRouterModelProvider()
# --- End OpenRouter Configuration ---


async def run_prompt(
    prompt: str,
    **kwargs: Any,
) -> Any:
    """
    Main SDK entry point to run the Phonosyne generation pipeline using OrchestratorAgent,
    configured to use OpenRouter.
    """
    from .agents.orchestrator import OrchestratorAgent  # Import here

    orchestrator_agent = OrchestratorAgent(**kwargs)

    result = await Runner.run(
        starting_agent=orchestrator_agent,
        input=prompt,
        run_config=RunConfig(model_provider=OPENROUTER_MODEL_PROVIDER),
    )

    return result.final_output
