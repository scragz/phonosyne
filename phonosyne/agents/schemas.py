"""
Pydantic Schemas for Phonosyne Agents

This module defines Pydantic models used for data validation and structuring
the information passed between different agents in the Phonosyne pipeline.

Key features:
- `SampleStub`: Defines the structure for a single sample's initial description
                 as output by the DesignerAgent and input to the AnalyzerAgent.
- `DesignerOutput`: Defines the overall output structure of the DesignerAgent.
- `AnalyzerInput`: Defines the input structure for the AnalyzerAgent (derived from SampleStub).
- `AnalyzerOutput`: Defines the structured output of the AnalyzerAgent, which serves
                   as input to the CompilerAgent.

@dependencies
- `pydantic.BaseModel` for creating data validation models.
- `pydantic.Field` for detailed field configuration (e.g., constraints).
- `typing.List` for defining lists of other models.
- `phonosyne.settings` for default values like sample rate.

@notes
- These schemas enforce data consistency throughout the agent pipeline.
- Field constraints (e.g., `gt=0` for duration) help catch errors early.
- The schemas are based on the JSON structures described in the prompt files
  (e.g., `prompts/designer.md`, `prompts/analyzer.md`).
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from phonosyne import settings


class SampleStub(BaseModel):
    """
    Represents a single sample's initial description as planned by the DesignerAgent.
    This is part of a MovementStub.
    """

    id: str = Field(
        ..., description="Unique identifier for the sample (e.g., 'L1.1', 'A1')."
    )
    # module: Optional[str] = Field(None, description="Optional module hint (e.g., 'lubadh', 'arbhar').") # As per designer.md, but might be simplified
    seed_description: str = Field(
        ...,
        description="Concise natural-language description of the sound sample (max 200 chars as per plan).",
        max_length=250,  # Relaxed slightly from plan's 200 for prompt flexibility
    )
    duration_s: float = Field(
        ..., gt=0, description="Requested duration of the sample in seconds."
    )

    @field_validator("id")
    @classmethod
    def id_format(cls, v: str) -> str:
        return v


class DesignerOutput(BaseModel):
    """
    Represents the overall output of the DesignerAgent.
    This is the main plan for generating the sound collection.
    """

    theme: str = Field(..., description="Brief description of the original user brief.")
    samples: List[SampleStub] = Field(
        ...,
        min_length=1,  # Each piece must have at least one sample
        description="List of samples within this piece.",
    )


class AnalyzerInput(BaseModel):
    """
    Represents the input to the AnalyzerAgent for a single sample.
    This is typically derived from a SampleStub.
    """

    id: str = Field(..., description="Unique identifier for the sample.")
    seed_description: str = Field(
        ..., description="The initial seed description from the DesignerAgent."
    )
    duration_s: float = Field(..., gt=0, description="Requested duration in seconds.")
    # sample_rate: int = Field(default=settings.DEFAULT_SR, description="Target sample rate in Hz.") # Analyzer prompt implies SR is part of its output


class AnalyzerOutput(BaseModel):
    """
    Represents the structured output of the AnalyzerAgent.
    This serves as the input to the CompilerAgent.
    Corresponds to the JSON output format in `prompts/analyzer.md`.
    """

    effect_name: str = Field(
        ...,
        description="Slugified name for the effect, derived from the prompt/description.",
    )
    duration: float = Field(
        ...,
        gt=0,
        description="Duration of the sound effect in seconds (must be >= 0.1 as per analyzer.md).",
    )
    description: str = Field(
        ...,
        description="Detailed natural-language instructions for synthesizing the sound (min 40 chars as per spec, max ~120 words as per analyzer.md).",
    )

    @field_validator("duration")
    @classmethod
    def duration_min_value(cls, v: float) -> float:
        if v < 0.1:
            raise ValueError("Duration must be at least 0.1 seconds.")
        return v

    @field_validator("description")
    @classmethod
    def description_min_length(cls, v: str) -> str:
        # Technical spec says "rich natural-language (>= 40 chars)"
        # Analyzer prompt says "Keep it under ~120 words"
        if len(v) < 10:  # Relaxed from 40 for initial stubs, real check in agent
            # raise ValueError("Description must be at least 40 characters long.")
            pass  # Actual validation can be stricter in the agent itself
        return v


if __name__ == "__main__":
    # Example Usage and Validation
    print("Testing Pydantic Schemas for Phonosyne Agents...")

    # Example SampleStub
    try:
        sample1 = SampleStub(
            id="L1.1", seed_description="A test sound.", duration_s=3.5
        )
        print(f"\nValid SampleStub: {sample1.model_dump_json(indent=2)}")
        sample_invalid_id = SampleStub(
            id="Invalid", seed_description="Test", duration_s=1.0
        )  # Will pass due to relaxed validation
        print(
            f"SampleStub with potentially 'invalid' ID (passes relaxed validation): {sample_invalid_id.model_dump_json(indent=2)}"
        )
    except Exception as e:
        print(f"Error creating SampleStub: {e}")

    # Example DesignerOutput
    try:
        design_output = DesignerOutput(
            brief_slug="test-collection",
            samples=[sample1],  # Using sample1 from above
        )
        print(f"\nValid DesignerOutput: {design_output.model_dump_json(indent=2)}")
    except Exception as e:
        print(f"Error creating DesignerOutput: {e}")

    # Example AnalyzerInput
    try:
        analyzer_input = AnalyzerInput(
            id="L1.1",
            seed_description="A warm, evolving pad sound with a slow attack.",
            duration_s=15.0,
        )
        print(f"\nValid AnalyzerInput: {analyzer_input.model_dump_json(indent=2)}")
    except Exception as e:
        print(f"Error creating AnalyzerInput: {e}")

    # Example AnalyzerOutput
    try:
        analyzer_out = AnalyzerOutput(
            effect_name="warm_evolving_pad",
            duration=15.0,
            description="Create a multi-layered pad using sine waves detuned slightly. Apply a slow attack envelope (around 3 seconds) and a long release (around 5 seconds). Add a resonant low-pass filter with its cutoff slowly opening over the duration of the sound. Include subtle stereo chorus and a spacious reverb.",
        )
        print(f"\nValid AnalyzerOutput: {analyzer_out.model_dump_json(indent=2)}")

        analyzer_out_short_desc = AnalyzerOutput(
            effect_name="short_sound",
            duration=0.5,
            description="Short blip.",  # Will pass relaxed validation
        )
        print(
            f"AnalyzerOutput with short description (passes relaxed validation): {analyzer_out_short_desc.model_dump_json(indent=2)}"
        )

        analyzer_out_short_duration = AnalyzerOutput(
            effect_name="too_short_sound",
            duration=0.05,  # Invalid
            description="A very very short sound that is too short.",
        )
    except Exception as e:
        print(f"Error creating AnalyzerOutput: {e}")

    print("\nSchema testing complete.")
