"""
Phonosyne SDK Implementation

This module contains the core SDK logic for Phonosyne, including the
`run_prompt` function and the configuration for using OpenRouter.
"""

import asyncio
import logging
import os
from typing import Any, Generic, TypeVar

from agents import (
    Agent,
    Model,
    ModelProvider,
    OpenAIChatCompletionsModel,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    Runner,
    Tool,
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

# --- Logging Configuration ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Or your desired level

TContext = TypeVar("TContext")


class LoggingRunHooks(RunHooks[TContext]):
    """
    A RunHooks implementation that logs all lifecycle events.
    """

    async def on_agent_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
    ) -> None:
        logger.info(
            f"Agent Start: {agent.name if hasattr(agent, 'name') else agent.__class__.__name__}, Context ID: {context.run_id}"
        )

    async def on_agent_end(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        logger.info(
            f"Agent End: {agent.name if hasattr(agent, 'name') else agent.__class__.__name__}, Context ID: {context.run_id}, Output: {str(output)[:100]}..."
        )  # Log snippet of output

    async def on_handoff(
        self,
        context: RunContextWrapper[TContext],
        from_agent: Agent[TContext],
        to_agent: Agent[TContext],
    ) -> None:
        logger.info(
            f"Handoff: From {from_agent.name if hasattr(from_agent, 'name') else from_agent.__class__.__name__} to {to_agent.name if hasattr(to_agent, 'name') else to_agent.__class__.__name__}, Context ID: {context.run_id}"
        )

    async def on_tool_start(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        logger.info(
            f"Tool Start: {tool.name if hasattr(tool, 'name') else tool.__class__.__name__} by Agent: {agent.name if hasattr(agent, 'name') else agent.__class__.__name__}, Context ID: {context.run_id}"
        )

    async def on_tool_end(
        self,
        context: RunContextWrapper[TContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        logger.info(
            f"Tool End: {tool.name if hasattr(tool, 'name') else tool.__class__.__name__} by Agent: {agent.name if hasattr(agent, 'name') else agent.__class__.__name__}, Context ID: {context.run_id}, Result: {str(result)[:100]}..."
        )  # Log snippet of result


DEFAULT_LOGGING_HOOKS = LoggingRunHooks()
# --- End Logging Configuration ---


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
        hooks=DEFAULT_LOGGING_HOOKS,  # Add the logging hooks
    )

    return result.final_output
