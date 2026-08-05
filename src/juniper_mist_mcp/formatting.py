"""Markdown formatting helpers."""

from typing import Any


def format_as_markdown(data: Any, title: str) -> str:
    """
    Format API response data as readable Markdown.

    Args:
        data: Response data to format
        title: Title for the markdown section

    Returns:
        Formatted markdown string
    """
    result = f"# {title}\n\n"

    if isinstance(data, list):
        if not data:
            return result + "No items found.\n"
        # List of items
        for i, item in enumerate(data, 1):
            result += f"## Item {i}\n\n"
            result += format_dict_as_markdown(item)
            result += "\n"
    elif isinstance(data, dict):
        result += format_dict_as_markdown(data)
    else:
        result += f"```\n{data}\n```\n"

    return result


def format_dict_as_markdown(data: dict, indent: int = 0) -> str:
    """Format a dictionary as markdown with proper indentation."""
    result = ""
    prefix = "  " * indent

    for key, value in data.items():
        if isinstance(value, dict):
            result += f"{prefix}- **{key}:**\n"
            result += format_dict_as_markdown(value, indent + 1)
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                result += f"{prefix}- **{key}:** (list of {len(value)} items)\n"
                for item in value[:3]:  # Show first 3 items
                    result += format_dict_as_markdown(item, indent + 1)
                if len(value) > 3:
                    result += f"{prefix}  ... and {len(value) - 3} more\n"
            else:
                result += f"{prefix}- **{key}:** {value}\n"
        else:
            result += f"{prefix}- **{key}:** {value}\n"

    return result


def truncate_response(text: str, max_chars: int = 25000) -> str:
    """
    Truncate response if it exceeds character limit.

    Args:
        text: Text to potentially truncate
        max_chars: Maximum characters allowed (MCP recommends 25,000)

    Returns:
        Truncated text with indicator if needed
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    omitted = len(text) - max_chars
    return f"{truncated}\n\n... (Response truncated: {omitted} characters omitted)"
