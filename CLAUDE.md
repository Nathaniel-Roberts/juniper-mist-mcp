# Juniper Mist MCP Server - Development Guide

## Project Overview

This MCP server provides Claude with access to Juniper Mist network infrastructure APIs. The implementation is in Python using the MCP SDK, starting with read-only operations and designed to expand into write capabilities.

## Implementation Architecture

**Language:** Python 3.10+
**Framework:** MCP Python SDK with FastMCP
**API Client:** httpx (async HTTP client)
**Validation:** Pydantic for input/output schemas

**Why Python:**
- Simpler, more concise implementation
- Easier to iterate and extend
- Better for network automation (common in the industry)
- FastMCP library reduces boilerplate

## Development Phases

### Phase 1: Read-Only Operations (Current)

Build tools that query network information without making changes:
- Organization and site discovery
- Device inventory and status
- Network monitoring (alarms, insights)
- Client statistics and locations

**Safety First:** All Phase 1 tools must set `readOnlyHint=true`

### Phase 2: Write Operations (Future)

Expand into network management capabilities:
- Device configuration changes
- Site and network policy updates
- User and access management
- Firmware updates and reboots

**Caution Required:** Write operations need careful validation and confirmation

## Getting Started

### Step 1: Research the Mist API

Before implementing, understand what endpoints are available:

```bash
# Use WebFetch to load documentation
- Mist API Reference: https://api.mist.com/api/v1/docs/
- Mist API Authentication Guide
- Look for read-only vs write endpoints
```

**Key Endpoints to Research:**

**Read-Only Endpoints:**
- `GET /api/v1/orgs` - List organizations
- `GET /api/v1/orgs/{org_id}` - Organization details
- `GET /api/v1/orgs/{org_id}/sites` - List sites
- `GET /api/v1/orgs/{org_id}/stats/devices` - Device statistics
- `GET /api/v1/orgs/{org_id}/inventory` - Device inventory
- `GET /api/v1/orgs/{org_id}/alarms` - Active alarms
- `GET /api/v1/orgs/{org_id}/insights` - Network insights
- `GET /api/v1/sites/{site_id}/stats/clients` - Client statistics
- `GET /api/v1/sites/{site_id}/devices` - Site devices

**Write Endpoints (Phase 2):**
- `PUT /api/v1/orgs/{org_id}/sites/{site_id}` - Update site
- `PUT /api/v1/sites/{site_id}/devices/{device_id}` - Update device config
- `POST /api/v1/sites/{site_id}/devices/{device_id}/restart` - Restart device
- `PUT /api/v1/orgs/{org_id}/networks/{network_id}` - Update network settings

### Step 2: Set Up the Project

```bash
# Create project structure
mkdir juniper-mist-mcp
cd juniper-mist-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install mcp httpx pydantic python-dotenv

# Create files
touch mist_server.py
touch requirements.txt
touch .env.example
touch .gitignore
```

**requirements.txt:**
```
mcp>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

**.env.example:**
```bash
# Juniper Mist API Token
MIST_API_TOKEN=your_token_here

# Optional: Default organization ID
MIST_ORG_ID=

# API Base URL (usually don't need to change)
MIST_API_BASE_URL=https://api.mist.com/api/v1
```

**.gitignore:**
```
venv/
__pycache__/
*.pyc
.env
.DS_Store
*.egg-info/
dist/
build/
```

### Step 3: Build Core Infrastructure

**File: mist_server.py**

Start with these foundational components:

```python
#!/usr/bin/env python3
"""
Juniper Mist MCP Server

Provides Claude with access to Juniper Mist networking APIs.
Phase 1: Read-only operations
Phase 2: Write operations (planned)
"""

import os
import asyncio
from typing import Literal, Optional
from mcp.server.fastmcp import FastMCP
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize MCP server
mcp = FastMCP("Juniper Mist")

# Configuration
MIST_API_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_API_BASE_URL = os.getenv("MIST_API_BASE_URL", "https://api.mist.com/api/v1")

if not MIST_API_TOKEN:
    raise ValueError("MIST_API_TOKEN environment variable is required")


# Utility Functions

async def mist_api_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[dict] = None,
    json_data: Optional[dict] = None
) -> dict:
    """
    Make an authenticated request to the Mist API.

    Args:
        endpoint: API endpoint (e.g., "/orgs")
        method: HTTP method (GET, POST, PUT, DELETE)
        params: Query parameters
        json_data: JSON body for POST/PUT requests

    Returns:
        Parsed JSON response

    Raises:
        Exception with user-friendly error messages
    """
    url = f"{MIST_API_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Token {MIST_API_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise Exception(
                    f"Rate limit exceeded. Please wait {retry_after} seconds before retrying."
                )

            # Handle authentication errors
            if response.status_code == 401:
                raise Exception(
                    "Authentication failed. Please check your MIST_API_TOKEN."
                )

            # Handle not found
            if response.status_code == 404:
                raise Exception(
                    "Resource not found. Please verify the organization/site/device ID."
                )

            # Raise for other HTTP errors
            response.raise_for_status()

            return response.json()

        except httpx.TimeoutException:
            raise Exception(
                "Request timed out. Please check your network connection and try again."
            )
        except httpx.NetworkError:
            raise Exception(
                "Network error. Unable to connect to Mist API."
            )


def format_as_markdown(data: dict, title: str) -> str:
    """
    Format API response data as readable Markdown.

    Args:
        data: Response data to format
        title: Title for the markdown section

    Returns:
        Formatted markdown string
    """
    # Implementation depends on data structure
    # Start with basic formatting, enhance as needed
    import json
    return f"# {title}\n\n```json\n{json.dumps(data, indent=2)}\n```"


def truncate_response(text: str, max_chars: int = 25000) -> str:
    """
    Truncate response if it exceeds character limit.

    Args:
        text: Text to potentially truncate
        max_chars: Maximum characters allowed

    Returns:
        Truncated text with indicator if needed
    """
    if len(text) <= max_chars:
        return text

    return text[:max_chars] + f"\n\n... (truncated, {len(text) - max_chars} characters omitted)"
```

### Step 4: Implement Read-Only Tools

**Tool Implementation Pattern:**

```python
@mcp.tool()
async def list_organizations(
    format: Literal["json", "markdown"] = "markdown",
    detail: Literal["concise", "detailed"] = "concise"
) -> str:
    """
    List all Mist organizations accessible with your API token.

    This retrieves all organizations you have access to. Use this as your
    first step to discover organization IDs before querying specific data.

    Args:
        format: Response format - "markdown" for readability, "json" for structured data
        detail: "concise" for basic info, "detailed" for full organization data

    Returns:
        Formatted list of organizations with IDs, names, and basic stats

    Example:
        User: "What organizations do I have access to?"
        -> Use this tool with default parameters
    """
    try:
        orgs = await mist_api_request("/orgs")

        if format == "json":
            import json
            return json.dumps(orgs, indent=2)

        # Format as markdown
        result = "# Mist Organizations\n\n"
        for org in orgs:
            result += f"## {org['name']}\n"
            result += f"- **ID:** `{org['id']}`\n"
            if detail == "detailed":
                result += f"- **Created:** {org.get('created_time', 'N/A')}\n"
                result += f"- **Num Sites:** {org.get('num_sites', 0)}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing organizations: {str(e)}"
```

**Implement these core tools following the same pattern:**

1. `list_organizations` - Discover available orgs
2. `get_organization_info` - Get detailed org information
3. `list_sites` - List sites in an org
4. `get_device_inventory` - Get device inventory
5. `get_device_statistics` - Get device stats
6. `get_alarms` - Get active alarms
7. `get_network_insights` - Get AI insights
8. `get_client_statistics` - Get client info
9. `search_devices` - Search for specific devices
10. `get_site_info` - Get detailed site information

**Tool Guidelines:**
- Always include comprehensive docstrings
- Use Pydantic or Literal types for validation
- Default to markdown format for agent readability
- Handle errors gracefully with actionable messages
- Set appropriate tool hints (readOnlyHint, etc.)
- Truncate responses to stay under 25,000 characters

### Step 5: Add Server Entry Point

```python
# At the end of mist_server.py

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
```

### Step 6: Test the Server

**Don't run the server directly** (it will hang waiting for stdio). Instead:

**Option 1: MCP Inspector**
```bash
npm install -g @modelcontextprotocol/inspector
mcp-inspector python mist_server.py
```

**Option 2: Claude Code Integration**
```bash
# In your project directory
/mcp add

# Or manually edit claude_desktop_config.json:
{
  "mcpServers": {
    "mist": {
      "command": "python",
      "args": ["/absolute/path/to/mist_server.py"],
      "env": {
        "MIST_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

## Phase 2: Adding Write Operations

When you're ready to add write capabilities:

### Planning Write Operations

**1. Choose Write Operations Carefully**

Start with low-risk operations:
- Update device names/descriptions
- Modify site metadata
- Change device locations
- Update configuration labels

Avoid initially:
- Firmware updates
- Device reboots
- Policy changes that affect connectivity
- User access modifications

**2. Add Confirmation Requirements**

For write operations, consider adding confirmation:

```python
@mcp.tool()
async def update_device_name(
    org_id: str,
    device_id: str,
    new_name: str,
    confirm: bool = False
) -> str:
    """
    Update the name of a device.

    This is a WRITE operation that modifies device configuration.

    Args:
        org_id: Organization ID
        device_id: Device ID to update
        new_name: New device name
        confirm: Must be set to True to execute the change

    Returns:
        Confirmation of the change or preview if confirm=False
    """
    if not confirm:
        return (
            f"Preview: This will rename device {device_id} to '{new_name}'.\n"
            f"To execute, call again with confirm=True"
        )

    try:
        result = await mist_api_request(
            f"/orgs/{org_id}/devices/{device_id}",
            method="PUT",
            json_data={"name": new_name}
        )
        return f"Device renamed successfully to '{new_name}'"
    except Exception as e:
        return f"Error updating device: {str(e)}"
```

**3. Update API Token Permissions**

Before implementing write tools:
1. Create a new API token in Mist dashboard
2. Grant specific write permissions needed
3. Test in a non-production organization first
4. Update `.env` with the new token

**4. Remove readOnlyHint**

Write tools should not have `readOnlyHint=true`. The MCP framework will properly indicate these are write operations.

### Common Write Operations

**Device Management:**
- Update device names/descriptions
- Change device locations
- Modify device assignments
- Restart devices (use with caution)

**Site Configuration:**
- Update site settings
- Modify site metadata
- Change site timezone/location

**Network Policies:**
- Update WLAN configurations
- Modify network policies
- Change security settings

## MCP Server Configuration for Claude Code

### Using `/mcp add`

Claude Code can automatically discover MCP servers. To make your server discoverable:

1. Ensure `mist_server.py` has proper shebang: `#!/usr/bin/env python3`
2. Make it executable: `chmod +x mist_server.py`
3. Create a `.mcp` metadata file (optional but helpful)

**Optional: Create .mcp file:**
```json
{
  "name": "Juniper Mist",
  "description": "Query and manage Juniper Mist network infrastructure",
  "version": "1.0.0",
  "command": "python",
  "args": ["mist_server.py"],
  "env": {
    "MIST_API_TOKEN": ""
  }
}
```

### Manual Configuration

If using manual configuration, the server can be added to Claude Desktop or Claude Code config:

```json
{
  "mcpServers": {
    "mist": {
      "command": "python",
      "args": ["/absolute/path/to/juniper-mist-mcp/mist_server.py"],
      "env": {
        "MIST_API_TOKEN": "your_actual_token",
        "MIST_ORG_ID": "optional_default_org_id"
      }
    }
  }
}
```

## Best Practices

### Code Organization

```
mist_server.py structure:
1. Imports and setup
2. Configuration and environment variables
3. Utility functions (API client, formatters)
4. Read-only tools (Phase 1)
5. Write tools (Phase 2) - clearly separated
6. Server entry point
```

### Error Handling

- Catch specific exceptions (auth, rate limit, not found)
- Return user-friendly error messages
- Include actionable next steps in errors
- Log errors for debugging (consider adding logging)

### Documentation

Every tool must have:
- One-line summary
- Detailed description (2-3 sentences)
- Parameter descriptions with types
- Return value description
- Usage example
- Error scenarios

### Testing Strategy

1. **Unit Tests:** Test utility functions in isolation
2. **Integration Tests:** Test API requests with real token
3. **MCP Inspector:** Manual testing of each tool
4. **Claude Testing:** Real-world usage testing

### Security

- Never commit `.env` file
- Use read-only tokens for Phase 1
- Carefully audit write operations
- Test write operations in non-prod first
- Consider adding audit logging for write ops
- Rotate tokens regularly

## Troubleshooting Development Issues

**"Module not found"**
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**"Authentication failed"**
- Check `.env` file exists and has correct token
- Verify token hasn't expired in Mist dashboard

**"Server hangs when running directly"**
- Don't run with `python mist_server.py` directly
- Use MCP Inspector or Claude Desktop integration

**"Response too large"**
- Implement pagination for large result sets
- Use the `limit` parameter on API calls
- Truncate responses properly

## Resources

- **MCP Python SDK:** https://github.com/modelcontextprotocol/python-sdk
- **MCP Protocol Spec:** https://modelcontextprotocol.io/llms-full.txt
- **Mist API Docs:** https://api.mist.com/api/v1/docs/
- **FastMCP Examples:** https://github.com/modelcontextprotocol/python-sdk/tree/main/examples
- **httpx Documentation:** https://www.python-httpx.org/

## Next Steps

1. Research Mist API endpoints thoroughly
2. Implement all read-only tools from Phase 1
3. Test each tool with MCP Inspector
4. Integrate with Claude Code using `/mcp add`
5. Gather feedback on read-only functionality
6. Plan Phase 2 write operations carefully
7. Implement write tools incrementally
8. Test write operations in safe environment
9. Document all changes and update README

## Extending the Server

Want to add new capabilities?

1. **Research the API endpoint** - Understand request/response format
2. **Design the tool interface** - What parameters? What output?
3. **Implement the tool** - Follow existing patterns
4. **Add comprehensive docs** - Docstrings with examples
5. **Test thoroughly** - Use MCP Inspector
6. **Update README** - Document the new tool

Remember: Start simple, test thoroughly, expand carefully.
