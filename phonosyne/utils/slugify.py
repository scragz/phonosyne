"""
Slugify Utility

This module provides a function to convert a string into a URL-friendly "slug".
Slugs are typically used in URLs or as parts of filenames to represent a piece of
content in a human-readable and web-safe format.

Key features:
- Converts input string to lowercase.
- Replaces spaces and punctuation with hyphens.
- Removes non-alphanumeric characters (except hyphens).
- Handles multiple consecutive hyphens.
- Trims leading/trailing hyphens.

@dependencies
- `re` (Python's regular expression module).
- `unicodedata` for handling Unicode characters by normalizing them.

@notes
- This is a simple ASCII-focused slugify function. For more complex internationalization
  requirements, a more robust library might be needed.
"""

import re
import unicodedata


def slugify(value: str, allow_unicode: bool = False) -> str:
    """
    Convert a string to a slug.

    Adapted from Django's slugify function.
    Converts to lowercase, removes non-word characters (alphanumerics and
    underscores) and converts spaces to hyphens. Also strips leading and
    trailing whitespace.

    Args:
        value: The string to slugify.
        allow_unicode: If True, allows Unicode characters in the slug.
                       If False (default), converts to ASCII.

    Returns:
        The slugified string.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value)
    value = re.sub(r"^-+|-+$", "", value)  # remove leading/trailing hyphens
    return value


if __name__ == "__main__":
    # Example usage
    test_strings = [
        "Hello World!",
        "  leading and trailing spaces  ",
        "Special Chars: !@#$%^&*()_+",
        "Multiple --- hyphens --- and spaces",
        "CamelCaseString",
        "UPPERCASE STRING",
        "A string with àçčéñtš",
    ]

    print("ASCII Slugs:")
    for s in test_strings:
        print(f"Original: '{s}' -> Slug: '{slugify(s)}'")

    print("\nUnicode Slugs (if allow_unicode=True):")
    for s in test_strings:
        print(f"Original: '{s}' -> Slug: '{slugify(s, allow_unicode=True)}'")

    # Test case from technical spec: "corrupted modem drones"
    brief_slug_test = "corrupted modem drones"
    print(
        f"\nTest from spec: '{brief_slug_test}' -> Slug: '{slugify(brief_slug_test)}'"
    )
