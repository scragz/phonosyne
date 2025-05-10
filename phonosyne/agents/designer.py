"""
Designer Agent for Phonosyne

This module defines the `DesignerAgent`, which is responsible for the first stage
of the Phonosyne pipeline: taking a user's sound design brief and expanding it
into a structured plan for an 18-sample, 6-movement sound collection.

Key features:
- Inherits from `AgentBase` for common LLM interaction logic.
- Uses the `prompts/designer.md` template for its LLM calls.
- Takes a user brief (string) as input.
- Outputs a JSON object conforming to the `DesignerOutput` Pydantic schema,
  detailing movements and sample descriptions.
- Handles parsing of the LLM's JSON output.

@dependencies
- `phonosyne.agents.base.AgentBase`
- `phonosyne.agents.schemas.DesignerOutput` (for output validation)
- `phonosyne.agents.schemas.AnalyzerInput` (as a conceptual input type, though Designer takes a string)
- `phonosyne.settings` (for `MODEL_DESIGNER`)
- `pydantic.BaseModel` (for a simple input wrapper if needed, though a string is fine)
- `logging`

@notes
- The agent is designed to be stateless.
- The prompt template (`designer.md`) is crucial for guiding the LLM
  to produce the correct JSON structure.
- JSON parsing and validation are key responsibilities of this agent.
"""

import logging
from typing import Any, Dict

from pydantic import BaseModel, Field  # For a simple input wrapper

from phonosyne import settings
from phonosyne.agents.base import AgentBase
from phonosyne.agents.schemas import DesignerOutput  # For output

logger = logging.getLogger(__name__)


class DesignerAgentInput(BaseModel):
    """
    Pydantic model for the input to the DesignerAgent's run method.
    Wraps the user brief string for consistency with AgentBase.process.
    """

    user_brief: str = Field(..., description="The user's sound design brief.")


class DesignerAgent(AgentBase[DesignerAgentInput, DesignerOutput]):
    """
    The DesignerAgent expands a user brief into a detailed plan for sound generation.
    """

    agent_name = "DesignerAgent"
    prompt_template_name = "designer.md"  # Corresponds to prompts/designer.md
    input_schema = DesignerAgentInput
    output_schema = DesignerOutput
    llm_model_name = settings.MODEL_DESIGNER

    def run(self, inputs: DesignerAgentInput, **kwargs: Any) -> DesignerOutput:
        """
        Executes the DesignerAgent's logic.

        Args:
            inputs: A DesignerAgentInput Pydantic model containing the user_brief.
            **kwargs: Additional keyword arguments (not currently used by this agent).

        Returns:
            A DesignerOutput Pydantic model representing the structured plan.

        Raises:
            ValueError: If the prompt template is not loaded.
            pydantic.ValidationError: If the LLM output fails to parse or validate.
            Various APIError from _llm_call.
        """
        if not self.prompt_template:
            logger.error("DesignerAgent prompt template not loaded.")
            raise ValueError(
                "Prompt template is essential for DesignerAgent but not loaded."
            )

        user_brief = inputs.user_brief

        # The designer.md prompt is a system prompt.
        # The user_brief should be injected into a user message, or the system prompt
        # should be structured to take the brief as a variable.
        # Current designer.md has "User Brief: {{user_brief}}"
        # So, we format the system prompt itself.

        # Let's assume the entire designer.md is the system prompt,
        # and it contains a placeholder for the user_brief.
        # This is slightly different from typical system + user message structure.
        # Alternative: designer.md is system, user_brief is user message.
        # For now, follow the {{user_brief}} in designer.md.

        # If designer.md is a system prompt that itself takes the brief:
        formatted_system_prompt = self.prompt_template.replace(
            "{{user_brief}}", user_brief
        )

        # The LLM call for DesignerAgent needs to produce a single line of JSON.
        # The prompt itself instructs the LLM to do this.
        # We might not need to use OpenAI's JSON mode if the prompt is strong enough.
        # If JSON mode is used, the system prompt must also instruct it.

        logger.info(f"Running DesignerAgent with user brief: '{user_brief[:100]}...'")

        # The designer.md prompt is more like a full request, not just a system message.
        # Let's treat the formatted prompt as the main user message.
        # No separate system prompt for this agent, as designer.md contains all instructions.
        raw_llm_output = self._llm_call(
            prompt=formatted_system_prompt,  # The entire designer.md content, formatted
            temperature=0.5,  # Designer needs to be creative but structured
            max_tokens=3072,  # Allow ample space for 18 samples in JSON (approx 2k-4k tokens)
            # system_prompt=None, # designer.md acts as the full prompt
            json_mode=False,  # Relying on prompt for JSON structure, as OpenRouter JSON mode varies
        )

        logger.debug(f"DesignerAgent raw LLM output: {raw_llm_output}")

        # Parse the raw LLM output string into the DesignerOutput Pydantic model
        try:
            parsed_output = self._parse_output(raw_llm_output)
            return parsed_output
        except ValidationError as e:
            logger.error(f"DesignerAgent output validation failed: {e}")
            # Potentially add a repair loop here or rely on orchestrator's retries
            # For now, re-raise to indicate failure at this stage.
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error parsing DesignerAgent output: {e}", exc_info=True
            )
            logger.error(f"Problematic raw output from LLM: {raw_llm_output}")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # This test requires OPENROUTER_API_KEY to be set in .env
    # and phonosyne.settings to be importable.
    # It will make a real LLM call.

    if not settings.OPENROUTER_API_KEY:
        print("Skipping DesignerAgent test: OPENROUTER_API_KEY not set.")
    else:
        print("Testing DesignerAgent (will make a real LLM call)...")
        designer_agent = DesignerAgent()

        test_brief = "A collection of sounds representing a futuristic cityscape, with a sense of melancholy and wonder."

        # Use the process method for input validation
        raw_input_data = {"user_brief": test_brief}

        try:
            design_plan = designer_agent.process(raw_input_data)
            print("\nDesignerAgent Test Output:")
            print(design_plan.model_dump_json(indent=2))

            # Basic checks on the output
            assert (
                len(design_plan.movements) > 0
            ), "DesignerOutput should have at least one movement."
            if design_plan.movements:
                assert (
                    len(design_plan.movements[0].samples) > 0
                ), "First movement should have samples."
            print("\nDesignerAgent test successful (basic structure checks passed).")

        except ValidationError as e:
            print(f"\nDesignerAgent Pydantic Validation Error: {e.errors()}")
        except APIError as e:
            print(f"\nDesignerAgent API Error: {e}")
        except Exception as e:
            print(
                f"\nAn unexpected error occurred during DesignerAgent test: {e}",
                exc_info=True,
            )
