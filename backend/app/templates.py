"""Prompt files from the agent folders use {{name}} placeholders."""

import re

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def fill(text: str, **values: str) -> str:
    """Every {{name}} with a value replaced; an unknown one is left alone."""
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
