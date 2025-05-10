"""
String Utility Functions for Phonosyne

This module provides helper functions for string manipulation.
"""

import json
import re
from typing import Any, Dict, Optional


def extract_json_from_text(text: str) -> Optional[str]:
    """
    Extracts a JSON string from a larger text block that might be enclosed
    in markdown-style code fences (e.g., ```json ... ``` or ``` ... ```).

    Args:
        text: The input string containing the potential JSON block.

    Returns:
        The extracted JSON string if found and valid, otherwise None.
    """
    # Regex to find content within ```json ... ``` or ``` ... ```
    # It handles optional "json" and captures the content inside.
    # It's non-greedy (.*?) to match the shortest possible block.
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1).strip()
        # Basic validation: try to parse it
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            # If it's not valid JSON, perhaps it's a more complex case or not JSON at all.
            # For now, we return None if parsing fails.
            # A more robust solution might try to find the largest valid JSON substring.
            return None
    return None


def extract_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts a JSON string from a text block and parses it into a Python dictionary.

    Args:
        text: The input string containing the potential JSON block.

    Returns:
        A dictionary if a valid JSON block is found and parsed, otherwise None.
    """
    json_str = extract_json_from_text(text)
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None


if __name__ == "__main__":
    print("Testing JSON extraction...")

    test_cases = [
        (
            'Some text before ```json\n{\n  "key": "value",\n  "number": 123\n}\n``` and after.',
            '{\n  "key": "value",\n  "number": 123\n}',
        ),
        ('No language specifier: ```\n{"hello": "world"}\n```', '{"hello": "world"}'),
        ('```json{"compact":true}```', '{"compact":true}'),
        ('```{"another_compact":false}```', '{"another_compact":false}'),
        (
            'Text with ```json\n{\n"name":"test", "data": [1,2,3]\n}\n``` embedded.',
            '{\n"name":"test", "data": [1,2,3]\n}',
        ),
        ('Mismatched ticks should not match ```json {"foo":"bar"} ``', None),
        ("No JSON block here.", None),
        (
            "Invalid JSON: ```json\n{key: 'value'}\n``` (single quotes)",
            None,
        ),  # Will be caught by json.loads
        (
            '```\n  {\n    "leading_whitespace": "should be kept by strip inside group",\n    "trailing_whitespace": "too  "  \n  }\n  ```',
            '{\n    "leading_whitespace": "should be kept by strip inside group",\n    "trailing_whitespace": "too  "  \n  }',
        ),
        (
            '```json\n{\n    "complex": {\n        "nested": true,\n        "list": ["a", "b", 100]\n    },\n    "valid": true\n}\n```',
            '{\n    "complex": {\n        "nested": true,\n        "list": ["a", "b", 100]\n    },\n    "valid": true\n}',
        ),
        (
            'Plain JSON without ticks: {"plain": "json"}',
            None,
        ),  # Current regex requires ticks
        ("```json\n``` (empty block)", ""),  # json.loads("") will fail
        ("```\n``` (empty block no lang)", ""),  # json.loads("") will fail
    ]

    for i, (text, expected_json_str) in enumerate(test_cases):
        print(f"\n--- Test Case {i+1} ---")
        print(f"Input:\n{text}")
        extracted = extract_json_from_text(text)
        print(f"Expected string:\n{expected_json_str}")
        print(f"Extracted string:\n{extracted}")

        if extracted == expected_json_str:
            print(f"String extraction: PASS")
        else:
            print(f"String extraction: FAIL")
            continue  # Skip parsing if string extraction failed

        if expected_json_str is not None:
            # Test parsing
            parsed_data = extract_and_parse_json(text)
            print(f"Parsed data: {parsed_data}")
            try:
                expected_parsed = json.loads(expected_json_str)
                if parsed_data == expected_parsed:
                    print("Parsing: PASS")
                else:
                    print("Parsing: FAIL - Mismatched content")
            except json.JSONDecodeError:
                if parsed_data is None:  # Expected parsing to fail
                    print("Parsing: PASS (expected failure, got None)")
                else:
                    print("Parsing: FAIL (expected failure, but got data)")
        elif extracted is None:  # Expected None, got None
            print("Parsing: PASS (expected None, got None)")
        else:  # Expected None, but got something that wasn't valid JSON
            parsed_data = extract_and_parse_json(text)
            if parsed_data is None:
                print("Parsing: PASS (expected None, got None after failed parse)")
            else:
                print(f"Parsing: FAIL (expected None, but got {parsed_data})")

    # Test for robustness with multiple blocks (should take the first one)
    multiple_blocks_text = (
        'First: ```json{"first": true}``` Second: ```{"second": false}```'
    )
    print(f"\n--- Test Case Multiple Blocks ---")
    print(f"Input:\n{multiple_blocks_text}")
    extracted_multiple = extract_json_from_text(multiple_blocks_text)
    expected_multiple = '{"first": true}'
    print(f"Expected string:\n{expected_multiple}")
    print(f"Extracted string:\n{extracted_multiple}")
    if extracted_multiple == expected_multiple:
        print("String extraction (multiple): PASS")
    else:
        print("String extraction (multiple): FAIL")

    # Test with no space after json keyword
    no_space_text = '```json{"key":"value"}```'
    print(f"\n--- Test Case No Space After 'json' ---")
    print(f"Input:\n{no_space_text}")
    extracted_no_space = extract_json_from_text(no_space_text)
    expected_no_space = '{"key":"value"}'
    print(f"Expected string:\n{expected_no_space}")
    print(f"Extracted string:\n{extracted_no_space}")
    if extracted_no_space == expected_no_space:
        print("String extraction (no space): PASS")
    else:
        print("String extraction (no space): FAIL")

    print("\nJSON extraction testing complete.")
