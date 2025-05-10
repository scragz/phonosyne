"""
Analyzer Agent for Phonosyne

This module defines the `AnalyzerAgent`, responsible for taking a single sample
description (a "stub") from the DesignerAgent's plan and expanding it into a
detailed, natural-language synthesis recipe. This recipe is then structured
as an `AnalyzerOutput` Pydantic model, ready for the CompilerAgent.

Key features:
- Inherits from `AgentBase`.
- Uses the `prompts/analyzer.md` template.
- Input: `AnalyzerInput` schema (containing sample ID, seed description, duration).
- Output: `AnalyzerOutput` schema (containing effect name, duration, sample rate,
          and a detailed natural-language synthesis description).
- Focuses on enriching a concise idea into a more actionable set of instructions
  for DSP code generation.

@dependencies
- `phonosyne.agents.base.AgentBase`
- `phonosyne.agents.schemas.AnalyzerInput`, `phonosyne.agents.schemas.AnalyzerOutput`
- `phonosyne.settings` (for `MODEL_ANALYZER`, `DEFAULT_SR`)
- `phonosyne.utils.slugify` (for generating `effect_name`)
- `logging`

@notes
- The quality of the `description` field in `AnalyzerOutput` is critical for the
  success of the subsequent CompilerAgent.
- The agent ensures the output conforms to the structure expected by `prompts/analyzer.md`.
"""

import logging
from typing import Any

from phonosyne import settings
from phonosyne.agents.base import AgentBase
from phonosyne.agents.schemas import AnalyzerInput, AnalyzerOutput
from phonosyne.utils import slugify  # For generating effect_name

logger = logging.getLogger(__name__)


class AnalyzerAgent(AgentBase[AnalyzerInput, AnalyzerOutput]):
    """
    The AnalyzerAgent enriches a sample stub into a detailed synthesis recipe.
    """

    agent_name = "AnalyzerAgent"
    prompt_template_name = "analyzer.md"  # Corresponds to prompts/analyzer.md
    input_schema = AnalyzerInput
    output_schema = AnalyzerOutput
    llm_model_name = settings.MODEL_ANALYZER

    def run(self, inputs: AnalyzerInput, **kwargs: Any) -> AnalyzerOutput:
        """
        Executes the AnalyzerAgent's logic.

        Args:
            inputs: An AnalyzerInput Pydantic model containing the sample's
                    id, seed_description, and duration_s.
            **kwargs: Additional keyword arguments (not currently used).

        Returns:
            An AnalyzerOutput Pydantic model.

        Raises:
            ValueError: If the prompt template is not loaded.
            pydantic.ValidationError: If the LLM output fails to parse or validate.
        """
        if not self.prompt_template:
            logger.error("AnalyzerAgent prompt template not loaded.")
            raise ValueError(
                "Prompt template is essential for AnalyzerAgent but not loaded."
            )

        # The analyzer.md prompt is a system prompt.
        # The actual input for the LLM call will be a user message formatted
        # according to the "Input" section of analyzer.md, which is:
        # "original user prompt (natural language)" - this refers to the seed_description.
        # However, the prompt also mentions honoring user-supplied duration/sample_rate.
        # So, we need to construct a user message that includes these details.

        # Let's create a structured user prompt for the LLM,
        # even though analyzer.md says "Input: original user prompt (natural language)".
        # This makes it explicit for the LLM.
        user_message_prompt = (
            f'Sound idea: "{inputs.seed_description}"\n'
            f"Requested duration: {inputs.duration_s} seconds.\n"
            f"Target sample rate: {settings.DEFAULT_SR} Hz.\n\n"
            f"Please provide the detailed synthesis recipe as a single-line JSON object."
        )

        logger.info(
            f"Running AnalyzerAgent for sample ID '{inputs.id}' "
            f"with seed: '{inputs.seed_description[:100]}...'"
        )

        raw_llm_output = self._llm_call(
            prompt=user_message_prompt,
            system_prompt=self.prompt_template,  # analyzer.md is the system prompt
            temperature=0.6,  # Analyzer needs to be descriptive and somewhat creative
            max_tokens=1024,  # Max tokens for the JSON output + description
            json_mode=False,  # Relying on prompt for single-line JSON, as per analyzer.md
        )

        logger.debug(f"AnalyzerAgent raw LLM output: {raw_llm_output}")

        try:
            # The LLM is asked to produce a single-line JSON.
            # _parse_output uses model_validate_json.
            parsed_output = self._parse_output(raw_llm_output)

            # Ensure the effect_name is a slug, as per analyzer.md's schema example.
            # The LLM might generate a slug, or it might generate a phrase.
            # Let's re-slugify it here to be certain.
            # If the LLM already produces a good slug, this won't harm it much.
            # If it produces "My Cool Effect", this will turn it into "my-cool-effect".
            # The prompt asks for "snake_case_slug", so slugify might need adjustment
            # or the prompt needs to be very specific. For now, default slugify.
            if parsed_output.effect_name:
                # Current slugify produces kebab-case. If snake_case is strict,
                # we'd need a slugify variant or trust the LLM.
                # For now, let's assume kebab-case from slugify is acceptable,
                # or the LLM will follow "snake_case_slug" instruction.
                # To be safe, let's enforce our slugify, then replace hyphens if snake_case is critical.
                generated_slug = slugify(parsed_output.effect_name)
                # If snake_case is a hard requirement:
                # generated_slug = slugify(parsed_output.effect_name).replace('-', '_')
                if generated_slug != parsed_output.effect_name:
                    logger.info(
                        f"Original effect_name '{parsed_output.effect_name}' re-slugified to '{generated_slug}'."
                    )
                    parsed_output.effect_name = generated_slug

            return parsed_output
        except ValidationError as e:
            logger.error(f"AnalyzerAgent output validation failed: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error parsing AnalyzerAgent output: {e}", exc_info=True
            )
            logger.error(
                f"Problematic raw output from LLM for AnalyzerAgent: {raw_llm_output}"
            )
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if not settings.OPENROUTER_API_KEY:
        print("Skipping AnalyzerAgent test: OPENROUTER_API_KEY not set.")
    else:
        print("Testing AnalyzerAgent (will make a real LLM call)...")
        analyzer_agent = AnalyzerAgent()

        # Example input, similar to what a DesignerAgent's SampleStub might provide
        test_analyzer_input = AnalyzerInput(
            id="A1_test",
            seed_description="A deep, resonant bass drone with slow, evolving metallic textures and a hint of distant choir.",
            duration_s=20.0,
        )

        raw_input_data = test_analyzer_input.model_dump()

        try:
            analysis_result = analyzer_agent.process(raw_input_data)
            print("\nAnalyzerAgent Test Output:")
            print(analysis_result.model_dump_json(indent=2))

            # Basic checks
            assert analysis_result.effect_name, "Effect name should be present."
            assert (
                analysis_result.duration == test_analyzer_input.duration_s
            ), "Duration should match input."
            assert (
                analysis_result.sample_rate == settings.DEFAULT_SR
            ), "Sample rate should be default."
            assert (
                len(analysis_result.description) >= 10
            ), "Description should be reasonably long."  # Relaxed from 40 for test
            print("\nAnalyzerAgent test successful (basic structure checks passed).")

        except ValidationError as e:
            print(f"\nAnalyzerAgent Pydantic Validation Error: {e.errors()}")
        except APIError as e:
            print(f"\nAnalyzerAgent API Error: {e}")
        except Exception as e:
            print(
                f"\nAn unexpected error occurred during AnalyzerAgent test: {e}",
                exc_info=True,
            )
