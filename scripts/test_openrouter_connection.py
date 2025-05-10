"""
Test script for basic OpenRouter connection using a simple agent.

This script helps verify that the OpenRouterModelProvider is working correctly
and that basic API calls to OpenRouter can be made, independent of the
full Phonosyne agent setup.

Instructions:
1. Ensure your .env file is in the project root and contains:
   OPENROUTER_API_KEY="your_actual_openrouter_key"
   OPENROUTER_MODEL_NAME="model_you_want_to_test_with" (e.g., "mistralai/mistral-7b-instruct")
2. Run this script from the project root:
   python scripts/test_openrouter_connection.py
"""

import asyncio
import os

# Ensure .env is loaded by importing settings from the project
# This is crucial for OPENROUTER_API_KEY to be available.
# The phonosyne.sdk module imports phonosyne.settings, which calls load_dotenv().
try:
    from phonosyne.sdk import OPENROUTER_MODEL_PROVIDER
    from phonosyne.settings import (
        DEFAULT_OPENROUTER_MODEL_NAME,  # To show which model is being targeted
    )
except ImportError:
    print(
        "Error: Could not import Phonosyne modules. "
        "Make sure you are running this script from the project root directory, "
        "and that Phonosyne is installed or PYTHONPATH is set correctly."
    )
    exit(1)

from agents import (  # function_tool removed as get_capital_city is removed
    Agent,
    RunConfig,
    Runner,
)


async def main():
    print("--- Starting OpenRouter Connection Test with Agents as Tools ---")

    # Check if API key is loaded (it's checked in sdk.py, but good to be aware)
    if not os.getenv("OPENROUTER_API_KEY"):
        print(
            "ERROR: OPENROUTER_API_KEY not found in environment. "
            "Please ensure it's set in your .env file and loaded."
        )
        return

    print(
        f"Attempting to use model: {DEFAULT_OPENROUTER_MODEL_NAME} (or as overridden by agent)"
    )

    # Define Specialist Agents
    spanish_translator_agent = Agent(
        name="SpanishTranslatorAgent",
        instructions="You are a highly skilled translator. Translate the given text accurately into Spanish. Output only the translation.",
        # model_name can be specified here if needed
    )

    french_translator_agent = Agent(
        name="FrenchTranslatorAgent",
        instructions="You are a highly skilled translator. Translate the given text accurately into French. Output only the translation.",
        # model_name can be specified here if needed
    )

    # Define the Orchestrator Agent that uses other agents as tools
    orchestrator_agent = Agent(
        name="TranslationOrchestratorAgent",
        instructions=(
            "You are a multilingual translation coordinator. "
            "Use the available translator tools to translate the user's text into the requested languages. "
            "Combine the results clearly. If asked for multiple translations, call all relevant tools."
        ),
        tools=[
            spanish_translator_agent.as_tool(
                tool_name="translate_to_spanish",  # This name is how the orchestrator refers to the tool
                tool_description="Use this tool to translate a given text to Spanish.",
            ),
            french_translator_agent.as_tool(
                tool_name="translate_to_french",
                tool_description="Use this tool to translate a given text to French.",
            ),
        ],
        # model_name can be specified here
    )

    test_prompt = "Translate the phrase 'Hello, world!' into Spanish and French."
    print(f"\nSending prompt to OrchestratorAgent: '{test_prompt}'")

    try:
        result = await Runner.run(
            starting_agent=orchestrator_agent,  # Start with the OrchestratorAgent
            input=test_prompt,
            run_config=RunConfig(model_provider=OPENROUTER_MODEL_PROVIDER),
        )

        print("\n--- Final Response from OrchestratorAgent ---")
        if result.final_output:
            print(result.final_output)
        else:
            print("No final output received from the agent.")
            if result.error:
                print(f"Agent run resulted in an error: {result.error}")
            print("Full result object:")
            print(result)

    except Exception as e:
        print(f"\n--- An error occurred during the test ---")
        print(f"Error type: {type(e).__name__}")
        print(f"Error details: {e}")
        import traceback

        traceback.print_exc()

    finally:
        print("\n--- OpenRouter Connection Test with Agents as Tools Finished ---")


if __name__ == "__main__":
    # This setup assumes the script is run from the project root
    # where 'phonosyne' is a subdirectory or in PYTHONPATH.
    # If you have issues with imports, ensure your execution environment is set up correctly.
    # For example, you might need to add the project root to PYTHONPATH:
    # import sys
    # sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    asyncio.run(main())
