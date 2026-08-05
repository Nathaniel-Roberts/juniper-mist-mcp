"""Markdown formatting and tool-result helpers."""

import json
from datetime import datetime
from typing import Any

from mcp.types import CallToolResult, TextContent


def local_timezone_name() -> str:
    """Short name of the server's local timezone (e.g. AEST)."""
    return datetime.now().astimezone().strftime('%Z')


def format_timestamp(ts: float) -> str:
    """
    Render an epoch timestamp in the server's local timezone, zone visible.

    Example: "2026-08-05 12:01:33 AEST"
    """
    return datetime.fromtimestamp(ts).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')


def json_tool_result(data: Any) -> CallToolResult:
    """
    Build a tool result for format="json" responses.

    Carries the data twice: as pretty-printed (and truncated) JSON text
    for readability, and as structuredContent for machine consumption.
    structuredContent is omitted when the payload exceeds the text cap,
    so oversized responses cannot bypass truncation.
    """
    text = json.dumps(data, indent=2)
    structured = data if isinstance(data, dict) else {"results": data}
    if len(text) <= 25000:
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=structured,
        )
    return CallToolResult(
        content=[TextContent(type="text", text=truncate_response(text))],
    )


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
