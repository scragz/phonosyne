"""
Abstract Base Class for Phonosyne Agents

This module defines `AgentBase`, an abstract base class (ABC) that provides
common functionalities for all specialized agents (Designer, Analyzer, Compiler)
in the Phonosyne pipeline.

Key features:
- Abstract `run` method to be implemented by subclasses.
- Helper method for making LLM calls via an OpenAI-compatible client.
  - Configurable model, temperature, max_tokens.
  - Retry logic for transient API errors.
- Helper method for loading prompt templates from files.
- Integration with Pydantic for input/output validation if specified.

@dependencies
- `abc.ABC`, `abc.abstractmethod` for creating abstract classes.
- `openai.OpenAI` or a compatible client for LLM interactions.
  (Using `smolagents.SmolOpenAIAgent` as a reference or direct use of `openai` client)
- `httpx` for potential timeout configurations if using `openai` client directly.
- `tenacity` for retry mechanisms.
- `pathlib.Path` for file operations (loading prompts).
- `typing` for type hints.
- `pydantic.BaseModel` for schema validation.
- `phonosyne.settings` for API keys, model names, retry counts.
- `logging` for agent activity logging.

@notes
- The LLM client will be configured to use OpenRouter's API endpoint.
- API key is sourced from `phonosyne.settings` (which loads from .env).
- Prompt templates are assumed to be in the directory specified by `settings.PROMPTS_DIR`.
"""

import abc
import logging
from pathlib import Path
from typing import Any, Dict, Generic, Optional, Type, TypeVar

# Attempt to use smolagents' client or a direct OpenAI client
try:
    from smolagents import SmolOpenAIAgent  # For structure reference

    # If using SmolOpenAIAgent directly, it handles retries and client setup.
    # However, the plan implies a more direct OpenAI client usage for Phonosyne.
except ImportError:
    SmolOpenAIAgent = None

import httpx
from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from phonosyne import settings

logger = logging.getLogger(__name__)

# Generic types for Pydantic models
InputSchema = TypeVar("InputSchema", bound=BaseModel)
OutputSchema = TypeVar("OutputSchema", bound=BaseModel)

DEFAULT_HTTP_TIMEOUT = 60.0  # seconds


class AgentBase(abc.ABC, Generic[InputSchema, OutputSchema]):
    """
    Abstract base class for all Phonosyne agents.
    Provides common LLM interaction, prompt loading, and retry logic.
    """

    agent_name: str
    prompt_template_name: Optional[str] = None  # e.g., "designer_prompt.md"
    input_schema: Optional[Type[InputSchema]] = None
    output_schema: Optional[Type[OutputSchema]] = None
    llm_model_name: str  # To be set by subclass, e.g., settings.MODEL_DESIGNER

    def __init__(self):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY not found in environment or settings. "
                "Please ensure it's set in your .env file."
            )

        # Configure httpx client with timeout for OpenAI client
        timeout_config = httpx.Timeout(
            DEFAULT_HTTP_TIMEOUT, connect=DEFAULT_HTTP_TIMEOUT
        )
        http_client = httpx.Client(timeout=timeout_config)

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            http_client=http_client,
        )
        self.prompt_template: Optional[str] = None
        if self.prompt_template_name:
            self.prompt_template = self._load_prompt_template(self.prompt_template_name)

    def _load_prompt_template(self, template_name: str) -> str:
        """Loads a prompt template from the filesystem."""
        template_path = settings.PROMPTS_DIR / template_name
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Prompt template not found: {template_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading prompt template {template_path}: {e}")
            raise

    @retry(
        wait=wait_exponential(
            multiplier=1, min=2, max=30
        ),  # Exponential backoff: 2s, 4s, 8s ... up to 30s
        stop=stop_after_attempt(settings.AGENT_MAX_RETRIES),
        retry=retry_if_exception_type(
            (APITimeoutError, RateLimitError, APIError)
        ),  # Retry on specific OpenAI errors
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying LLM call for {retry_state.fn.__qualname__ if hasattr(retry_state.fn, '__qualname__') else 'agent'} "
            f"due to {type(retry_state.outcome.exception()).__name__}, "
            f"attempt {retry_state.attempt_number}/{settings.AGENT_MAX_RETRIES}..."
        ),
    )
    def _llm_call(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        temperature: float = 0.7,  # Default temperature
        max_tokens: int = 2048,  # Default max tokens
        system_prompt: Optional[str] = None,
        json_mode: bool = False,  # For OpenAI JSON mode if output is expected to be JSON
    ) -> str:
        """
        Makes a call to the LLM with retry logic.
        """
        target_model = model_name or self.llm_model_name
        logger.debug(
            f"Making LLM call to model: {target_model} "
            f"(temp={temperature}, max_tokens={max_tokens}, json_mode={json_mode})"
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response_kwargs = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                # Ensure the model supports JSON mode. Some models might require specific phrasing in the prompt.
                # Example: "claude-3-haiku-20240307" on OpenRouter might not directly support response_format.
                # Check OpenRouter documentation for model-specific JSON mode support.
                # For now, we assume it's available if requested.
                # If not, the agent will have to parse JSON from string output.
                # response_kwargs["response_format"] = {"type": "json_object"} # This is standard OpenAI
                pass  # JSON mode handling might need to be model-specific or done via prompt engineering

            completion = self.client.chat.completions.create(**response_kwargs)

            content = completion.choices[0].message.content
            if content is None:
                raise APIError("LLM response content is None.", request=None, body=None)  # type: ignore

            logger.debug(f"LLM raw response: {content[:500]}...")  # Log a snippet
            return content.strip()

        except APITimeoutError as e:
            logger.error(f"LLM call timed out for model {target_model}: {e}")
            raise
        except RateLimitError as e:
            logger.error(f"Rate limit exceeded for model {target_model}: {e}")
            raise
        except (
            APIError
        ) as e:  # Catch other API errors (e.g., server errors, bad requests after retries)
            logger.error(f"API error during LLM call to {target_model}: {e}")
            raise
        except Exception as e:  # Catch any other unexpected errors
            logger.error(
                f"Unexpected error during LLM call to {target_model}: {e}",
                exc_info=True,
            )
            raise

    def _parse_output(self, output_str: str) -> OutputSchema:
        """
        Parses the string output from LLM into the defined Pydantic output_schema.
        Raises ValidationError if parsing fails.
        """
        if self.output_schema is None:
            # This should not happen if an output_schema is expected.
            # If no schema, then output_str is returned as is by the run method.
            raise TypeError(
                f"Agent {self.agent_name} has no output_schema defined for parsing."
            )

        try:
            # If JSON mode was successful and output_str is already JSON, this will parse it.
            # If output_str is natural language containing JSON, this might require
            # more sophisticated extraction before parsing.
            # For now, assume output_str is directly parsable as JSON if schema is set.
            parsed_output = self.output_schema.model_validate_json(output_str)
            logger.debug(
                f"Successfully parsed LLM output into {self.output_schema.__name__}."
            )
            return parsed_output
        except ValidationError as e:
            logger.error(
                f"Failed to validate LLM output against {self.output_schema.__name__}. Errors: {e.errors()}"
            )
            logger.error(f"Raw output that failed validation: {output_str[:1000]}...")
            # Consider including the full raw output in a more detailed log or an exception payload
            raise  # Re-raise the ValidationError

    @abc.abstractmethod
    def run(self, inputs: InputSchema, **kwargs: Any) -> OutputSchema | str:
        """
        Main execution method for the agent.
        Subclasses must implement this method.

        Args:
            inputs: Validated input data according to self.input_schema (if defined).
                    If no input_schema, this could be a raw type like str.
            **kwargs: Additional keyword arguments for specific agent needs.

        Returns:
            Validated output data according to self.output_schema (if defined),
            or a raw string if no output_schema is specified.
        """
        pass

    def process(self, raw_inputs: Dict[str, Any], **kwargs: Any) -> OutputSchema | str:
        """
        Validates raw input against input_schema (if defined), then calls run().
        This acts as a public entry point that includes input validation.
        """
        validated_inputs: InputSchema | Dict[str, Any]
        if self.input_schema:
            try:
                validated_inputs = self.input_schema.model_validate(raw_inputs)
                logger.debug(
                    f"Successfully validated input against {self.input_schema.__name__}."
                )
            except ValidationError as e:
                logger.error(
                    f"Input validation failed for {self.agent_name}. Errors: {e.errors()}"
                )
                logger.error(f"Raw input that failed validation: {raw_inputs}")
                raise
        else:
            # If no input schema, pass raw_inputs (which should be of the type expected by run)
            # This branch assumes raw_inputs is already in the correct format for `run`
            # or `run` handles dicts directly.
            # For consistency, `run` should expect `InputSchema` or a basic type like `str`.
            # If `input_schema` is None, `run`'s type hint for `inputs` should reflect that.
            # This part might need refinement based on how agents without schemas are called.
            validated_inputs = (
                raw_inputs  # Or handle as error if schema always expected
            )

        # The type checker might complain here if input_schema is None, as validated_inputs
        # would be Dict, but run might expect InputSchema.
        # This implies that if input_schema is None, the `run` method's `inputs`
        # parameter should be typed as `Any` or `Dict[str, Any]`.
        # For now, casting to InputSchema for the call, assuming `run` handles it or
        # this path is taken only when `input_schema` is indeed `None` and `run` expects `Dict`.
        return self.run(inputs=validated_inputs, **kwargs)  # type: ignore


if __name__ == "__main__":
    # This is an abstract class, so direct instantiation for testing is limited.
    # We can test parts like prompt loading if settings are available.

    logging.basicConfig(level=logging.DEBUG)
    logger.info("AgentBase module loaded. Contains abstract class AgentBase.")

    # Example: Test prompt loading (requires PROMPTS_DIR and a dummy prompt file)
    # Ensure phonosyne/settings.py and a prompts directory exist relative to this script
    # or that the project is installed and phonosyne.settings can be imported.

    # Create dummy settings and prompt for testing if not found
    if not hasattr(settings, "PROMPTS_DIR"):
        print("Patching settings for AgentBase test...")
        settings.PROMPTS_DIR = Path("./temp_prompts_dir_for_test")
        settings.PROMPTS_DIR.mkdir(exist_ok=True)
        settings.OPENROUTER_API_KEY = "dummy_key_for_test_no_call"  # Avoids ValueError
        settings.AGENT_MAX_RETRIES = 1

    dummy_prompt_name = "test_prompt.md"
    dummy_prompt_path = settings.PROMPTS_DIR / dummy_prompt_name
    with open(dummy_prompt_path, "w") as f:
        f.write("This is a {{test_variable}} prompt.")

    class ConcreteTestAgent(
        AgentBase[BaseModel, BaseModel]
    ):  # Using BaseModel for generic test
        agent_name = "TestAgent"
        prompt_template_name = dummy_prompt_name  # Use the dummy prompt
        llm_model_name = "test_model/not_called"  # Dummy model

        def run(
            self, inputs: BaseModel, **kwargs: Any
        ) -> str:  # Return str for this test
            if self.prompt_template:
                return self.prompt_template.replace("{{test_variable}}", "loaded")
            return "Prompt not loaded"

    try:
        agent = ConcreteTestAgent()
        loaded_prompt_content = agent.prompt_template
        print(f"Successfully loaded prompt template content: '{loaded_prompt_content}'")

        # Test the run method (which uses the loaded prompt)
        # Input schema is BaseModel, so pass an empty one or mock.
        class DummyInput(BaseModel):
            pass

        result = agent.run(DummyInput())
        print(f"Agent run result (after template processing): '{result}'")
        assert result == "This is a loaded prompt."

    except Exception as e:
        print(f"Error during AgentBase concrete test: {e}")
    finally:
        # Clean up dummy prompt and dir
        if dummy_prompt_path.exists():
            dummy_prompt_path.unlink()
        if (
            settings.PROMPTS_DIR.name == "temp_prompts_dir_for_test"
            and settings.PROMPTS_DIR.exists()
        ):
            settings.PROMPTS_DIR.rmdir()
        print("AgentBase test cleanup finished.")
