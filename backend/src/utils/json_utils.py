import json
from typing import Any


def parse_markdown_json(content: str) -> Any:
    """Parse JSON that may be wrapped in ```json ... ``` or ``` ... ``` fences."""
    if not content:
        raise json.JSONDecodeError("Empty content", "", 0)

    content = content.strip()
    if content.startswith("```json") and content.endswith("```"):
        content = content[len("```json") : -len("```")].strip()
    elif content.startswith("```") and content.endswith("```"):
        content = content[len("```") : -len("```")].strip()

    return json.loads(content)
