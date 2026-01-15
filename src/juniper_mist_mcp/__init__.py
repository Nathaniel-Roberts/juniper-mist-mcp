#!/usr/bin/env python3
"""
Juniper Mist MCP Server

Provides Claude with access to Juniper Mist networking APIs.
Phase 1: Read-only operations for safe network monitoring
Phase 2: Write operations (planned)

Author: Claude
License: MIT
"""

import os
import json
from pathlib import Path
from typing import Literal, Optional, Any
from mcp.server.fastmcp import FastMCP
import httpx
from dotenv import load_dotenv

# Load environment variables from multiple locations (in order of priority):
# 1. ~/.config/juniper-mist-mcp/.env (user config directory)
# 2. Current working directory .env
config_dir = Path.home() / ".config" / "juniper-mist-mcp"
config_env_file = config_dir / ".env"
if config_env_file.exists():
    load_dotenv(config_env_file)
load_dotenv()  # Also check current directory

# Initialize MCP server
mcp = FastMCP("Juniper Mist")

# Configuration
MIST_API_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_API_BASE_URL = os.getenv("MIST_API_BASE_URL", "https://api.mist.com/api/v1")
MIST_ORG_ID = os.getenv("MIST_ORG_ID")  # Optional default org

if not MIST_API_TOKEN:
    raise ValueError(
        "MIST_API_TOKEN not found. Set it by either:\n"
        "1. Creating ~/.config/juniper-mist-mcp/.env with: MIST_API_TOKEN=your_token\n"
        "2. Setting MIST_API_TOKEN in your mcp.json env section\n"
        "Get your token from: https://manage.mist.com > Organization > Settings > API Tokens"
    )


# ============================================================================
# Utility Functions
# ============================================================================

async def mist_api_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[dict] = None,
    json_data: Optional[dict] = None
) -> Any:
    """
    Make an authenticated request to the Mist API.

    Args:
        endpoint: API endpoint (e.g., "/orgs" or "/orgs/{org_id}/sites")
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
                    f"Rate limit exceeded (5,000 requests/hour). "
                    f"Please wait {retry_after} seconds before retrying."
                )

            # Handle authentication errors
            if response.status_code == 401:
                raise Exception(
                    "Authentication failed. Please check your MIST_API_TOKEN. "
                    "You can generate a new token at: "
                    "https://manage.mist.com > Organization > Settings > API Tokens"
                )

            # Handle forbidden
            if response.status_code == 403:
                raise Exception(
                    "Access forbidden. Your API token may not have permission for this resource. "
                    "Check token permissions in the Mist dashboard."
                )

            # Handle not found
            if response.status_code == 404:
                raise Exception(
                    "Resource not found. Please verify the organization/site/device ID. "
                    "Use list_organizations to see available organizations."
                )

            # Raise for other HTTP errors
            response.raise_for_status()

            return response.json()

        except httpx.TimeoutException:
            raise Exception(
                "Request timed out after 30 seconds. "
                "Please check your network connection and try again."
            )
        except httpx.NetworkError as e:
            raise Exception(
                f"Network error: Unable to connect to Mist API at {MIST_API_BASE_URL}. "
                f"Details: {str(e)}"
            )
        except Exception as e:
            # Re-raise our custom exceptions
            if "Rate limit" in str(e) or "Authentication" in str(e) or "not found" in str(e):
                raise
            # Handle JSON decode errors
            if "JSON" in str(e):
                raise Exception(f"Invalid response from Mist API: {str(e)}")
            raise


def format_markdown_table(data: list[dict], columns: list[str], title: str = "") -> str:
    """
    Format a list of dictionaries as a Markdown table.

    Args:
        data: List of dictionaries to format
        columns: Column names to include
        title: Optional title for the table

    Returns:
        Formatted markdown table
    """
    if not data:
        return f"# {title}\n\nNo data available.\n" if title else "No data available.\n"

    result = ""
    if title:
        result += f"# {title}\n\n"

    # Create header
    result += "| " + " | ".join(columns) + " |\n"
    result += "| " + " | ".join(["---"] * len(columns)) + " |\n"

    # Add rows
    for item in data:
        row = []
        for col in columns:
            value = item.get(col, "N/A")
            # Handle nested dicts/lists
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            # Escape pipe characters
            value = str(value).replace("|", "\\|")
            row.append(value)
        result += "| " + " | ".join(row) + " |\n"

    return result


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


# ============================================================================
# Organization Tools
# ============================================================================

@mcp.tool()
async def list_organizations(
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    List all Mist organizations accessible with your API token.

    This retrieves all organizations you have access to. Use this as your
    first step to discover organization IDs before querying specific data.

    Args:
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        Formatted list of organizations with IDs, names, and basic info

    Example:
        User: "What organizations do I have access to?"
        -> Use this tool with default parameters

    Error Handling:
        - If authentication fails: Check MIST_API_TOKEN environment variable
        - If no orgs returned: Verify API token has org access permissions
    """
    try:
        # Use /self endpoint to get account privileges and organizations
        self_data = await mist_api_request("/self")

        # Extract organizations from privileges
        orgs = []
        if 'privileges' in self_data:
            for priv in self_data['privileges']:
                if priv.get('scope') == 'org':
                    orgs.append({
                        'id': priv.get('org_id'),
                        'name': priv.get('name'),
                        'role': priv.get('role')
                    })

        if format == "json":
            return json.dumps(orgs, indent=2)

        # Format as markdown
        if not orgs:
            return "# Mist Organizations\n\nNo organizations found. Verify your API token has access."

        result = "# Mist Organizations\n\n"
        result += "Use these organization IDs for other commands.\n\n"

        for org in orgs:
            result += f"## {org.get('name', 'Unnamed Organization')}\n\n"
            result += f"- **Organization ID:** `{org['id']}`\n"
            result += f"- **Your Role:** {org.get('role', 'N/A')}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing organizations: {str(e)}"


@mcp.tool()
async def get_organization_info(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get detailed information about a specific organization.

    Retrieves comprehensive details about an organization including settings,
    statistics, and configuration.

    Args:
        org_id: Organization UUID (get from list_organizations)
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        Detailed organization information

    Example:
        User: "Tell me about organization abc-123"
        -> Use this tool with org_id="abc-123"

    Error Handling:
        - If org not found: Use list_organizations to find valid org IDs
        - If access denied: Check API token permissions
    """
    try:
        org = await mist_api_request(f"/orgs/{org_id}")

        if format == "json":
            return json.dumps(org, indent=2)

        return truncate_response(format_as_markdown(org, f"Organization: {org.get('name', org_id)}"))

    except Exception as e:
        return f"Error getting organization info: {str(e)}"


@mcp.tool()
async def list_sites(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    List all sites within an organization.

    Retrieves all sites (locations) configured in the specified organization.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        List of sites with IDs, names, addresses, and basic statistics

    Example:
        User: "What sites are in my organization?"
        -> Use this tool with the org_id

    Error Handling:
        - If no sites found: Organization may not have any sites configured
        - Use list_organizations first if org_id is unknown
    """
    try:
        sites = await mist_api_request(f"/orgs/{org_id}/sites")

        if format == "json":
            return json.dumps(sites, indent=2)

        if not sites:
            return f"# Sites in Organization {org_id}\n\nNo sites found."

        result = f"# Sites in Organization\n\n"
        result += f"Found {len(sites)} site(s)\n\n"

        for site in sites:
            result += f"## {site.get('name', 'Unnamed Site')}\n\n"
            result += f"- **Site ID:** `{site['id']}`\n"
            if site.get('address'):
                result += f"- **Address:** {site['address']}\n"
            if site.get('timezone'):
                result += f"- **Timezone:** {site['timezone']}\n"
            if site.get('country_code'):
                result += f"- **Country:** {site['country_code']}\n"
            if 'num_devices' in site:
                result += f"- **Devices:** {site['num_devices']}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing sites: {str(e)}"


@mcp.tool()
async def get_site_info(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get detailed information about a specific site.

    Retrieves comprehensive site configuration including address, timezone,
    RF settings, network policies, and enabled features.

    Args:
        site_id: Site UUID (get from list_sites)
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        Detailed site configuration and settings

    Example:
        User: "Tell me about the main office site"
        -> Use this tool with the site_id from list_sites

    Error Handling:
        - If site not found: Use list_sites to find valid site IDs
        - If access denied: Check API token permissions
    """
    try:
        site = await mist_api_request(f"/sites/{site_id}")

        if format == "json":
            return json.dumps(site, indent=2)

        result = f"# Site: {site.get('name', 'Unnamed Site')}\n\n"
        result += f"- **Site ID:** `{site['id']}`\n"

        if site.get('address'):
            result += f"- **Address:** {site['address']}\n"
        if site.get('timezone'):
            result += f"- **Timezone:** {site['timezone']}\n"
        if site.get('country_code'):
            result += f"- **Country:** {site['country_code']}\n"
        if site.get('latlng'):
            result += f"- **Coordinates:** {site['latlng'].get('lat')}, {site['latlng'].get('lng')}\n"

        # Network settings
        result += "\n## Network Settings\n\n"
        if site.get('networktemplate_id'):
            result += f"- **Network Template ID:** `{site['networktemplate_id']}`\n"
        if site.get('rftemplate_id'):
            result += f"- **RF Template ID:** `{site['rftemplate_id']}`\n"
        if site.get('sitetemplate_id'):
            result += f"- **Site Template ID:** `{site['sitetemplate_id']}`\n"

        # Features
        if 'vars' in site:
            result += "\n## Site Variables\n\n"
            for key, value in site['vars'].items():
                result += f"- **{key}:** {value}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting site info: {str(e)}"


@mcp.tool()
async def get_site_stats(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get real-time statistics and health metrics for a site.

    Retrieves current site status including device counts, client counts,
    and overall network health metrics.

    Args:
        site_id: Site UUID (get from list_sites)
        format: Response format

    Returns:
        Site statistics including device counts, client counts, and health status

    Example:
        User: "How is the main office network performing?"
        -> Use this tool with the site_id

    Error Handling:
        - If site not found: Use list_sites to find valid site IDs
    """
    try:
        stats = await mist_api_request(f"/sites/{site_id}/stats")

        if format == "json":
            return json.dumps(stats, indent=2)

        result = f"# Site Statistics\n\n"

        if 'num_clients' in stats:
            result += f"- **Connected Clients:** {stats['num_clients']}\n"
        if 'num_devices' in stats:
            result += f"- **Total Devices:** {stats['num_devices']}\n"
        if 'num_devices_connected' in stats:
            result += f"- **Devices Online:** {stats['num_devices_connected']}\n"
        if 'num_devices_disconnected' in stats:
            result += f"- **Devices Offline:** {stats['num_devices_disconnected']}\n"

        # Device breakdown
        if 'num_aps' in stats:
            result += f"\n## Access Points\n"
            result += f"- **Total APs:** {stats.get('num_aps', 0)}\n"
            result += f"- **APs Connected:** {stats.get('num_aps_connected', 0)}\n"

        if 'num_switches' in stats:
            result += f"\n## Switches\n"
            result += f"- **Total Switches:** {stats.get('num_switches', 0)}\n"
            result += f"- **Switches Connected:** {stats.get('num_switches_connected', 0)}\n"

        if 'num_gateways' in stats:
            result += f"\n## Gateways\n"
            result += f"- **Total Gateways:** {stats.get('num_gateways', 0)}\n"
            result += f"- **Gateways Connected:** {stats.get('num_gateways_connected', 0)}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting site stats: {str(e)}"


# ============================================================================
# Device Tools
# ============================================================================

@mcp.tool()
async def get_device_inventory(
    org_id: str,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get inventory of all devices in an organization.

    Retrieves device inventory including claimed and unclaimed devices,
    with their serial numbers, models, MAC addresses, and claim status.

    Args:
        org_id: Organization UUID
        device_type: Filter by device type - "ap" (access points), "switch", "gateway", or "all"
        limit: Maximum number of devices to return (1-1000, default 100)
        format: Response format

    Returns:
        Device inventory with model, serial, MAC, claim status, and site assignment

    Example:
        User: "Show me all access points in inventory"
        -> Use this tool with device_type="ap"

    Error Handling:
        - If no devices: Organization inventory may be empty
        - Starting 2026, responses will be paginated (max 1000 per request)
    """
    try:
        params = {"limit": min(limit, 1000)}
        if device_type != "all":
            params["type"] = device_type

        inventory = await mist_api_request(f"/orgs/{org_id}/inventory", params=params)

        if format == "json":
            return json.dumps(inventory, indent=2)

        if not inventory:
            return f"# Device Inventory\n\nNo devices found in inventory."

        result = f"# Device Inventory ({device_type})\n\n"
        result += f"Found {len(inventory)} device(s)\n\n"

        # Group by type
        by_type = {}
        for device in inventory:
            dtype = device.get('type', 'unknown')
            if dtype not in by_type:
                by_type[dtype] = []
            by_type[dtype].append(device)

        for dtype, devices in by_type.items():
            result += f"## {dtype.upper()} Devices ({len(devices)})\n\n"

            for device in devices[:50]:  # Limit per type
                result += f"### {device.get('name', device.get('model', 'Unknown'))}\n\n"
                result += f"- **Serial:** {device.get('serial', 'N/A')}\n"
                result += f"- **MAC:** {device.get('mac', 'N/A')}\n"
                result += f"- **Model:** {device.get('model', 'N/A')}\n"
                result += f"- **Type:** {device.get('type', 'N/A')}\n"
                if 'site_id' in device:
                    result += f"- **Site ID:** `{device['site_id']}`\n"
                if 'claimed' in device:
                    result += f"- **Claimed:** {'Yes' if device['claimed'] else 'No'}\n"
                result += "\n"

            if len(devices) > 50:
                result += f"... and {len(devices) - 50} more {dtype} devices\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device inventory: {str(e)}"


@mcp.tool()
async def get_device_stats(
    org_id: str,
    site_id: Optional[str] = None,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    status: Literal["connected", "disconnected", "all"] = "all",
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get real-time statistics for devices in an organization or site.

    Retrieves current device status, uptime, version, client count, and performance metrics.

    Args:
        org_id: Organization UUID
        site_id: Optional site UUID to filter by site
        device_type: Filter by device type
        status: Filter by connection status
        limit: Maximum devices to return (1-1000)
        format: Response format

    Returns:
        Device statistics including status, uptime, clients, CPU, memory, version

    Example:
        User: "Which access points are offline?"
        -> Use this tool with device_type="ap", status="disconnected"

    Error Handling:
        - Returns empty if no devices match filters
        - Use list_sites to get valid site_id values
    """
    try:
        endpoint = f"/sites/{site_id}/stats/devices" if site_id else f"/orgs/{org_id}/stats/devices"
        params = {"limit": min(limit, 1000)}

        if device_type != "all":
            params["type"] = device_type
        if status != "all":
            params["status"] = status

        stats = await mist_api_request(endpoint, params=params)

        if format == "json":
            return json.dumps(stats, indent=2)

        if not stats:
            return f"# Device Statistics\n\nNo devices found matching the filters."

        result = f"# Device Statistics\n\n"
        result += f"Found {len(stats)} device(s)\n\n"

        for device in stats[:100]:
            name = device.get('name', device.get('mac', 'Unknown'))
            result += f"## {name}\n\n"
            result += f"- **MAC:** {device.get('mac', 'N/A')}\n"
            result += f"- **Model:** {device.get('model', 'N/A')}\n"
            result += f"- **Type:** {device.get('type', 'N/A')}\n"
            result += f"- **Status:** {device.get('status', 'N/A')}\n"

            if 'uptime' in device:
                uptime_hours = device['uptime'] / 3600
                result += f"- **Uptime:** {uptime_hours:.1f} hours\n"

            if 'version' in device:
                result += f"- **Firmware:** {device['version']}\n"

            if 'num_clients' in device:
                result += f"- **Connected Clients:** {device['num_clients']}\n"

            if 'cpu_stat' in device:
                cpu = device['cpu_stat']
                result += f"- **CPU Usage:** {cpu.get('usage', 'N/A')}%\n"

            if 'memory_stat' in device:
                mem = device['memory_stat']
                result += f"- **Memory Usage:** {mem.get('usage', 'N/A')}%\n"

            if 'ip' in device:
                result += f"- **IP Address:** {device['ip']}\n"

            result += "\n"

        if len(stats) > 100:
            result += f"... and {len(stats) - 100} more devices (showing first 100)\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device statistics: {str(e)}"


# ============================================================================
# Monitoring Tools
# ============================================================================

@mcp.tool()
async def get_alarms(
    org_id: str,
    severity: Literal["critical", "warn", "info", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get active alarms and alerts for an organization.

    Retrieves current network alarms including device offline, high utilization,
    configuration issues, and security alerts.

    Args:
        org_id: Organization UUID
        severity: Filter by severity level - "critical", "warn", "info", or "all"
        limit: Maximum alarms to return (default 50)
        format: Response format

    Returns:
        List of alarms with timestamp, severity, type, description, and affected devices

    Example:
        User: "Show me critical alarms"
        -> Use this tool with severity="critical"

        User: "Are there any alarms right now?"
        -> Use this tool with severity="all"

    Error Handling:
        - Returns empty list if no active alarms (which is good!)
        - Use get_device_stats to identify offline devices
    """
    try:
        params = {"limit": limit}
        if severity != "all":
            params["severity"] = severity

        alarms = await mist_api_request(f"/orgs/{org_id}/alarms/search", params=params)

        if format == "json":
            return json.dumps(alarms, indent=2)

        if not alarms:
            return f"# Network Alarms\n\nNo active alarms found. Network is healthy!"

        result = f"# Network Alarms\n\n"
        result += f"Found {len(alarms)} active alarm(s)\n\n"

        # Group by severity
        by_severity = {"critical": [], "warn": [], "info": []}
        for alarm in alarms:
            sev = alarm.get('severity', 'info')
            if sev in by_severity:
                by_severity[sev].append(alarm)

        for sev in ["critical", "warn", "info"]:
            if by_severity[sev]:
                result += f"## {sev.upper()} Alarms ({len(by_severity[sev])})\n\n"

                for alarm in by_severity[sev]:
                    result += f"### {alarm.get('type', 'Unknown Alarm')}\n\n"
                    result += f"- **Severity:** {alarm.get('severity', 'N/A')}\n"
                    result += f"- **Timestamp:** {alarm.get('timestamp', 'N/A')}\n"

                    if 'hostnames' in alarm:
                        result += f"- **Affected Devices:** {', '.join(alarm['hostnames'])}\n"

                    if 'site_name' in alarm:
                        result += f"- **Site:** {alarm['site_name']}\n"

                    if 'reason' in alarm:
                        result += f"- **Reason:** {alarm['reason']}\n"

                    result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting alarms: {str(e)}"


@mcp.tool()
async def get_client_stats(
    org_id: str,
    site_id: Optional[str] = None,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get statistics about connected wireless clients.

    Retrieves information about clients currently connected to the network,
    including device types, connection details, and performance metrics.

    Args:
        org_id: Organization UUID
        site_id: Optional site UUID to filter by site
        limit: Maximum clients to return (default 100)
        format: Response format

    Returns:
        Client information including hostname, MAC, IP, SSID, AP connection, signal strength

    Example:
        User: "How many clients are connected?"
        -> Use this tool to get client count and details

        User: "Show me connected clients at site X"
        -> Use this tool with site_id parameter

    Error Handling:
        - Returns empty if no clients connected
        - Use list_sites to get valid site_id values
    """
    try:
        endpoint = f"/sites/{site_id}/stats/clients" if site_id else f"/orgs/{org_id}/clients"
        params = {"limit": limit}

        clients = await mist_api_request(endpoint, params=params)

        if format == "json":
            return json.dumps(clients, indent=2)

        if not clients:
            location = f"site {site_id}" if site_id else "organization"
            return f"# Connected Clients\n\nNo clients currently connected to {location}."

        result = f"# Connected Clients\n\n"
        result += f"Total: {len(clients)} client(s)\n\n"

        for i, client in enumerate(clients[:100], 1):
            hostname = client.get('hostname', client.get('mac', f'Client {i}'))
            result += f"## {hostname}\n\n"

            result += f"- **MAC:** {client.get('mac', 'N/A')}\n"

            if 'ip' in client:
                result += f"- **IP:** {client['ip']}\n"

            if 'ssid' in client:
                result += f"- **SSID:** {client['ssid']}\n"

            if 'ap_mac' in client:
                result += f"- **Connected to AP:** {client['ap_mac']}\n"

            if 'rssi' in client:
                result += f"- **Signal Strength (RSSI):** {client['rssi']} dBm\n"

            if 'snr' in client:
                result += f"- **SNR:** {client['snr']} dB\n"

            if 'band' in client:
                result += f"- **Band:** {client['band']}\n"

            if 'channel' in client:
                result += f"- **Channel:** {client['channel']}\n"

            if 'manufacture' in client or 'os' in client:
                result += f"- **Device:** {client.get('manufacture', '')} {client.get('os', '')}\n"

            if 'uptime' in client:
                uptime_min = client['uptime'] / 60
                result += f"- **Session Duration:** {uptime_min:.0f} minutes\n"

            result += "\n"

        if len(clients) > 100:
            result += f"... and {len(clients) - 100} more clients (showing first 100)\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting client statistics: {str(e)}"


@mcp.tool()
async def search_organization_devices(
    org_id: str,
    search_term: str,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Search for devices by name, MAC address, serial number, or model.

    Searches across all devices in an organization to find matches.

    Args:
        org_id: Organization UUID
        search_term: Search string (name, MAC, serial, model)
        device_type: Filter by device type
        limit: Maximum results to return
        format: Response format

    Returns:
        Matching devices with their details

    Example:
        User: "Find device with MAC aa:bb:cc:dd:ee:ff"
        -> Use this tool with search_term="aa:bb:cc:dd:ee:ff"

        User: "Search for switches named 'floor-3'"
        -> Use this tool with search_term="floor-3", device_type="switch"

    Error Handling:
        - Returns empty if no matches found
        - Search is case-insensitive
    """
    try:
        # Get inventory to search through
        inventory = await mist_api_request(f"/orgs/{org_id}/inventory")

        if not inventory:
            return f"# Device Search Results\n\nNo devices in inventory to search."

        # Filter by type if specified
        if device_type != "all":
            inventory = [d for d in inventory if d.get('type') == device_type]

        # Search across relevant fields
        search_lower = search_term.lower()
        matches = []

        for device in inventory:
            name = device.get('name', '').lower()
            mac = device.get('mac', '').lower()
            serial = device.get('serial', '').lower()
            model = device.get('model', '').lower()

            if (search_lower in name or
                search_lower in mac or
                search_lower in serial or
                search_lower in model):
                matches.append(device)

            if len(matches) >= limit:
                break

        if format == "json":
            return json.dumps(matches, indent=2)

        if not matches:
            return f"# Device Search Results\n\nNo devices found matching '{search_term}'."

        result = f"# Device Search Results\n\n"
        result += f"Found {len(matches)} device(s) matching '{search_term}'\n\n"

        for device in matches:
            result += f"## {device.get('name', 'Unnamed Device')}\n\n"
            result += f"- **Serial:** {device.get('serial', 'N/A')}\n"
            result += f"- **MAC:** {device.get('mac', 'N/A')}\n"
            result += f"- **Model:** {device.get('model', 'N/A')}\n"
            result += f"- **Type:** {device.get('type', 'N/A')}\n"
            if 'site_id' in device:
                result += f"- **Site ID:** `{device['site_id']}`\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching devices: {str(e)}"


# ============================================================================
# WLAN Tools
# ============================================================================

@mcp.tool()
async def list_wlans(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    List all WLANs (wireless networks) configured at a site.

    Retrieves all wireless network configurations including SSIDs, security settings,
    VLANs, and enabled features.

    Args:
        site_id: Site UUID (get from list_sites)
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        List of WLANs with SSID, security type, VLAN, and configuration details

    Example:
        User: "What wireless networks are available at this site?"
        -> Use this tool with the site_id

        User: "Show me all SSIDs"
        -> Use this tool with the site_id

    Error Handling:
        - If no WLANs found: Site may not have any wireless networks configured
        - Use list_sites to get valid site_id values
    """
    try:
        wlans = await mist_api_request(f"/sites/{site_id}/wlans")

        if format == "json":
            return json.dumps(wlans, indent=2)

        if not wlans:
            return "# WLANs\n\nNo WLANs configured at this site."

        result = "# WLANs (Wireless Networks)\n\n"
        result += f"Found {len(wlans)} WLAN(s)\n\n"

        for wlan in wlans:
            ssid = wlan.get('ssid', 'Unnamed WLAN')
            result += f"## {ssid}\n\n"
            result += f"- **WLAN ID:** `{wlan.get('id', 'N/A')}`\n"
            result += f"- **SSID:** {ssid}\n"
            result += f"- **Enabled:** {'Yes' if wlan.get('enabled', False) else 'No'}\n"

            # Security
            auth_type = wlan.get('auth', {}).get('type', 'open')
            result += f"- **Security:** {auth_type}\n"

            if wlan.get('auth', {}).get('psk'):
                result += f"- **PSK Configured:** Yes\n"

            # VLAN
            if 'vlan_id' in wlan:
                result += f"- **VLAN ID:** {wlan['vlan_id']}\n"
            if wlan.get('vlan_enabled'):
                result += f"- **VLAN Enabled:** Yes\n"

            # Band
            if 'band' in wlan:
                result += f"- **Band:** {wlan['band']}\n"

            # Visibility
            result += f"- **Hidden SSID:** {'Yes' if wlan.get('hide_ssid', False) else 'No'}\n"

            # Guest settings
            if wlan.get('portal_enabled'):
                result += f"- **Captive Portal:** Enabled\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing WLANs: {str(e)}"


@mcp.tool()
async def list_org_wlans(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    List all WLAN templates configured at the organization level.

    Retrieves organization-level WLAN configurations that can be applied to sites.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        List of org-level WLANs with configuration details

    Example:
        User: "What WLAN templates exist in the organization?"
        -> Use this tool with the org_id
    """
    try:
        wlans = await mist_api_request(f"/orgs/{org_id}/wlans")

        if format == "json":
            return json.dumps(wlans, indent=2)

        if not wlans:
            return "# Organization WLANs\n\nNo organization-level WLANs configured."

        result = "# Organization WLAN Templates\n\n"
        result += f"Found {len(wlans)} WLAN template(s)\n\n"

        for wlan in wlans:
            ssid = wlan.get('ssid', 'Unnamed WLAN')
            result += f"## {ssid}\n\n"
            result += f"- **WLAN ID:** `{wlan.get('id', 'N/A')}`\n"
            result += f"- **SSID:** {ssid}\n"

            auth_type = wlan.get('auth', {}).get('type', 'open')
            result += f"- **Security:** {auth_type}\n"

            if 'vlan_id' in wlan:
                result += f"- **VLAN ID:** {wlan['vlan_id']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing org WLANs: {str(e)}"


# ============================================================================
# Switch Port Tools
# ============================================================================

@mcp.tool()
async def get_switch_port_stats(
    site_id: str,
    switch_mac: Optional[str] = None,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get switch port statistics including status, speed, and traffic.

    Retrieves real-time port information for switches at a site including
    link status, speed/duplex, VLAN, PoE status, and connected devices.

    Args:
        site_id: Site UUID
        switch_mac: Optional switch MAC address to filter by specific switch
        limit: Maximum ports to return (default 100)
        format: Response format

    Returns:
        Port statistics including up/down status, speed, VLAN, PoE, and connected clients

    Example:
        User: "Show me switch port status"
        -> Use this tool with the site_id

        User: "What's connected to switch aa:bb:cc:dd:ee:ff?"
        -> Use this tool with switch_mac parameter

    Error Handling:
        - If no ports found: Site may not have switches or they may be offline
    """
    try:
        params = {"limit": limit}
        if switch_mac:
            params["mac"] = switch_mac

        response = await mist_api_request(f"/sites/{site_id}/stats/switch_ports/search", params=params)

        if format == "json":
            return json.dumps(response, indent=2)

        # Extract results from search response
        ports = response.get('results', response) if isinstance(response, dict) else response

        if not ports:
            return "# Switch Port Statistics\n\nNo switch port data available."

        result = "# Switch Port Statistics\n\n"
        result += f"Found {len(ports)} port(s)\n\n"

        # Group by switch
        by_switch = {}
        for port in ports:
            switch = port.get('switch_mac', 'Unknown')
            if switch not in by_switch:
                by_switch[switch] = []
            by_switch[switch].append(port)

        for switch_mac_addr, switch_ports in by_switch.items():
            switch_name = switch_ports[0].get('switch_name', switch_mac_addr) if switch_ports else switch_mac_addr
            result += f"## Switch: {switch_name}\n\n"
            result += f"MAC: `{switch_mac_addr}`\n\n"

            result += "| Port | Status | Speed | VLAN | PoE | Description |\n"
            result += "|------|--------|-------|------|-----|-------------|\n"

            for port in sorted(switch_ports, key=lambda x: x.get('port_id', '')):
                port_id = port.get('port_id', 'N/A')
                status = '🟢 Up' if port.get('up', False) else '🔴 Down'
                speed = port.get('speed', 'N/A')
                if speed and speed != 'N/A':
                    speed = f"{speed}Mbps"
                vlan = port.get('vlan_id', 'N/A')
                poe_on = '⚡' if port.get('poe_on', False) else '-'
                desc = port.get('port_desc', '-')[:20]

                result += f"| {port_id} | {status} | {speed} | {vlan} | {poe_on} | {desc} |\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting switch port stats: {str(e)}"


# ============================================================================
# Event Tools
# ============================================================================

@mcp.tool()
async def get_device_events(
    site_id: str,
    device_mac: Optional[str] = None,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get recent events for devices at a site.

    Retrieves device events including status changes, configuration updates,
    reboots, and errors.

    Args:
        site_id: Site UUID
        device_mac: Optional device MAC to filter events for specific device
        device_type: Filter by device type
        limit: Maximum events to return (default 50)
        format: Response format

    Returns:
        List of device events with timestamps, types, and descriptions

    Example:
        User: "What events happened on the network today?"
        -> Use this tool with the site_id

        User: "Show events for device aa:bb:cc:dd:ee:ff"
        -> Use this tool with device_mac parameter

    Error Handling:
        - Returns empty if no recent events
    """
    try:
        params = {"limit": limit}
        if device_mac:
            params["mac"] = device_mac
        if device_type != "all":
            params["type"] = device_type

        events = await mist_api_request(f"/sites/{site_id}/devices/events/search", params=params)

        if format == "json":
            return json.dumps(events, indent=2)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            return "# Device Events\n\nNo recent events found."

        result = "# Device Events\n\n"
        result += f"Found {len(results_list)} event(s)\n\n"

        for event in results_list[:limit]:
            event_type = event.get('type', 'Unknown Event')
            result += f"## {event_type}\n\n"

            if 'timestamp' in event:
                from datetime import datetime
                ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                result += f"- **Time:** {ts}\n"

            if 'device_name' in event:
                result += f"- **Device:** {event['device_name']}\n"
            if 'mac' in event:
                result += f"- **MAC:** {event['mac']}\n"
            if 'device_type' in event:
                result += f"- **Type:** {event['device_type']}\n"
            if 'text' in event:
                result += f"- **Details:** {event['text']}\n"
            if 'reason' in event:
                result += f"- **Reason:** {event['reason']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device events: {str(e)}"


@mcp.tool()
async def get_audit_logs(
    org_id: str,
    admin_name: Optional[str] = None,
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get audit logs showing administrative actions in the organization.

    Retrieves a log of configuration changes, user actions, and administrative
    events for compliance and troubleshooting.

    Args:
        org_id: Organization UUID
        admin_name: Optional admin username to filter logs
        limit: Maximum logs to return (default 50)
        format: Response format

    Returns:
        List of audit events with admin, action, timestamp, and details

    Example:
        User: "Who made changes to the network recently?"
        -> Use this tool with the org_id

        User: "Show audit logs for admin john@example.com"
        -> Use this tool with admin_name parameter

    Error Handling:
        - Returns empty if no audit logs in timeframe
        - May require admin privileges to access
    """
    try:
        params = {"limit": limit}
        if admin_name:
            params["admin_name"] = admin_name

        logs = await mist_api_request(f"/orgs/{org_id}/logs", params=params)

        if format == "json":
            return json.dumps(logs, indent=2)

        results_list = logs.get('results', logs) if isinstance(logs, dict) else logs

        if not results_list:
            return "# Audit Logs\n\nNo audit logs found."

        result = "# Audit Logs\n\n"
        result += f"Found {len(results_list)} log entries\n\n"

        for log in results_list[:limit]:
            action = log.get('message', 'Unknown Action')
            result += f"## {action[:50]}{'...' if len(action) > 50 else ''}\n\n"

            if 'timestamp' in log:
                from datetime import datetime
                ts = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                result += f"- **Time:** {ts}\n"

            if 'admin_name' in log:
                result += f"- **Admin:** {log['admin_name']}\n"
            if 'src_ip' in log:
                result += f"- **Source IP:** {log['src_ip']}\n"
            if 'site_id' in log:
                result += f"- **Site ID:** `{log['site_id']}`\n"
            if 'message' in log:
                result += f"- **Action:** {log['message']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting audit logs: {str(e)}"


# ============================================================================
# WAN/Gateway Tools
# ============================================================================

@mcp.tool()
async def get_site_wan_stats(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get WAN (internet) connection statistics for a site.

    Retrieves WAN link status, bandwidth usage, latency, and ISP information
    for sites with Mist Edge or gateway devices.

    Args:
        site_id: Site UUID
        format: Response format

    Returns:
        WAN statistics including link status, bandwidth, latency, and uptime

    Example:
        User: "How is the internet connection at this site?"
        -> Use this tool with the site_id

        User: "Show me WAN link status"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no WAN devices at site
        - Requires gateway/edge device at the site
    """
    try:
        stats = await mist_api_request(f"/sites/{site_id}/stats/devices", params={"type": "gateway"})

        if format == "json":
            return json.dumps(stats, indent=2)

        if not stats:
            return "# WAN Statistics\n\nNo gateway devices found at this site."

        result = "# WAN Statistics\n\n"

        for gw in stats:
            name = gw.get('name', gw.get('mac', 'Gateway'))
            result += f"## {name}\n\n"
            result += f"- **Status:** {gw.get('status', 'N/A')}\n"

            if 'ip' in gw:
                result += f"- **IP Address:** {gw['ip']}\n"

            if 'uptime' in gw:
                uptime_hours = gw['uptime'] / 3600
                result += f"- **Uptime:** {uptime_hours:.1f} hours\n"

            # WAN interfaces
            if 'ports' in gw:
                result += "\n### WAN Ports\n\n"
                for port_name, port_info in gw['ports'].items():
                    if 'wan' in port_name.lower() or port_info.get('is_wan'):
                        result += f"#### {port_name}\n"
                        result += f"- **Status:** {'Up' if port_info.get('up') else 'Down'}\n"
                        if 'ip' in port_info:
                            result += f"- **IP:** {port_info['ip']}\n"
                        if 'speed' in port_info:
                            result += f"- **Speed:** {port_info['speed']}Mbps\n"
                        result += "\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting WAN stats: {str(e)}"


# ============================================================================
# Security Tools
# ============================================================================

@mcp.tool()
async def get_rogue_aps(
    site_id: str,
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get detected rogue access points at a site.

    Retrieves a list of unauthorized or unknown access points detected by
    the wireless network, which may indicate security threats.

    Args:
        site_id: Site UUID
        limit: Maximum rogues to return (default 50)
        format: Response format

    Returns:
        List of rogue APs with SSID, BSSID, signal strength, and detection info

    Example:
        User: "Are there any rogue access points?"
        -> Use this tool with the site_id

        User: "Show unauthorized WiFi networks"
        -> Use this tool with the site_id

    Error Handling:
        - Empty result means no rogues detected (good!)
        - Requires wireless APs at the site for detection
    """
    try:
        params = {"limit": limit}
        rogues = await mist_api_request(f"/sites/{site_id}/insights/rogues", params=params)

        if format == "json":
            return json.dumps(rogues, indent=2)

        results_list = rogues.get('results', rogues) if isinstance(rogues, dict) else rogues

        if not results_list:
            return "# Rogue AP Detection\n\n✅ No rogue access points detected."

        result = "# Rogue AP Detection\n\n"
        result += f"⚠️ Found {len(results_list)} potential rogue AP(s)\n\n"

        for rogue in results_list[:limit]:
            ssid = rogue.get('ssid', '<Hidden SSID>')
            result += f"## {ssid}\n\n"

            result += f"- **BSSID:** {rogue.get('bssid', 'N/A')}\n"
            result += f"- **Channel:** {rogue.get('channel', 'N/A')}\n"

            if 'rssi' in rogue:
                result += f"- **Signal Strength:** {rogue['rssi']} dBm\n"

            if 'times_heard' in rogue:
                result += f"- **Times Detected:** {rogue['times_heard']}\n"

            if 'ap_mac' in rogue:
                result += f"- **Detected By AP:** {rogue['ap_mac']}\n"

            if 'last_seen' in rogue:
                from datetime import datetime
                ts = datetime.fromtimestamp(rogue['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
                result += f"- **Last Seen:** {ts}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting rogue APs: {str(e)}"


# ============================================================================
# RF/Wireless Analytics Tools
# ============================================================================

@mcp.tool()
async def get_rf_stats(
    site_id: str,
    band: Literal["24", "5", "6", "all"] = "all",
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get RF (radio frequency) environment statistics for a site.

    Retrieves wireless environment metrics including channel utilization,
    interference levels, noise floor, and client distribution by band.

    Args:
        site_id: Site UUID
        band: Filter by frequency band - "24" (2.4GHz), "5" (5GHz), "6" (6GHz), or "all"
        format: Response format

    Returns:
        RF statistics including channel utilization, interference, and capacity metrics

    Example:
        User: "How is the wireless environment?"
        -> Use this tool with the site_id

        User: "Show me 5GHz channel utilization"
        -> Use this tool with band="5"

    Error Handling:
        - Requires APs at the site for RF data
        - Returns aggregate site-wide metrics
    """
    try:
        # Get AP stats which include RF metrics
        params = {"type": "ap"}
        stats = await mist_api_request(f"/sites/{site_id}/stats/devices", params=params)

        if format == "json":
            return json.dumps(stats, indent=2)

        if not stats:
            return "# RF Statistics\n\nNo access points found at this site."

        result = "# RF Environment Statistics\n\n"

        # Aggregate RF stats
        bands_data = {"24": [], "5": [], "6": []}

        for ap in stats:
            if 'radio_stat' in ap:
                for radio in ap.get('radio_stat', {}).values():
                    radio_band = str(radio.get('band', ''))
                    if radio_band in bands_data:
                        bands_data[radio_band].append({
                            'name': ap.get('name', ap.get('mac')),
                            'channel': radio.get('channel'),
                            'power': radio.get('power'),
                            'bandwidth': radio.get('bandwidth'),
                            'num_clients': radio.get('num_clients', 0),
                            'util_all': radio.get('util_all', 0),
                            'util_non_wifi': radio.get('util_non_wifi', 0),
                            'noise_floor': radio.get('noise_floor')
                        })

        for band_name, band_label in [("24", "2.4 GHz"), ("5", "5 GHz"), ("6", "6 GHz")]:
            if band != "all" and band != band_name:
                continue

            radios = bands_data[band_name]
            if not radios:
                continue

            result += f"## {band_label} Band\n\n"
            result += f"**Active Radios:** {len(radios)}\n\n"

            # Calculate averages
            total_clients = sum(r['num_clients'] for r in radios)
            avg_util = sum(r['util_all'] for r in radios) / len(radios) if radios else 0

            result += f"- **Total Clients:** {total_clients}\n"
            result += f"- **Avg Channel Utilization:** {avg_util:.1f}%\n"

            result += "\n| AP | Channel | Power | Clients | Utilization |\n"
            result += "|-----|---------|-------|---------|-------------|\n"

            for radio in radios[:20]:
                result += f"| {radio['name'][:15]} | {radio['channel']} | {radio['power']}dBm | {radio['num_clients']} | {radio['util_all']:.0f}% |\n"

            if len(radios) > 20:
                result += f"\n... and {len(radios) - 20} more radios\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting RF stats: {str(e)}"


# ============================================================================
# Marvis AI Tools
# ============================================================================

@mcp.tool()
async def get_marvis_actions(
    org_id: str,
    category: Literal["all", "wired", "wireless", "wan", "switch", "ap", "gateway"] = "all",
    status: Literal["all", "open", "resolved"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get Marvis AI-generated action alerts and recommendations.

    Marvis is Juniper Mist's AI engine that proactively identifies network issues
    and provides actionable recommendations. This retrieves current Marvis actions
    including connectivity issues, loop detection, coverage problems, and more.

    Args:
        org_id: Organization UUID
        category: Filter by category - "wired", "wireless", "wan", "switch", "ap", "gateway", or "all"
        status: Filter by status - "open" (active issues), "resolved", or "all"
        limit: Maximum actions to return (default 50)
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        List of Marvis actions with type, affected devices, site, timestamp, and details

    Example:
        User: "What does Marvis say about network issues?"
        -> Use this tool with default parameters

        User: "Show me open wired network issues"
        -> Use this tool with category="wired", status="open"

        User: "Are there any loop detection alerts?"
        -> Use this tool and look for "Loop Detected" actions

    Error Handling:
        - Returns empty if no Marvis actions (network is healthy!)
        - Requires Marvis subscription/license for full functionality
    """
    try:
        params = {"limit": limit}

        # The Marvis API uses different parameter names
        if category != "all":
            params["category"] = category
        if status != "all":
            params["status"] = status

        # Marvis actions are part of the alarms system with group="marvis"
        params["group"] = "marvis"
        actions = await mist_api_request(f"/orgs/{org_id}/alarms/search", params=params)

        if format == "json":
            return json.dumps(actions, indent=2)

        # Handle response format (could be list or dict with results)
        results_list = actions.get('results', actions) if isinstance(actions, dict) else actions

        if not results_list:
            return "# Marvis Actions\n\n✅ No active Marvis actions. Network looks healthy!"

        result = "# Marvis AI Actions\n\n"
        result += f"Found {len(results_list)} action(s)\n\n"

        # Group by category if available
        by_category = {}
        for action in results_list:
            cat = action.get('category', action.get('type', 'Unknown'))
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(action)

        for cat, cat_actions in by_category.items():
            result += f"## {cat.title()} ({len(cat_actions)})\n\n"

            for action in cat_actions:
                action_type = action.get('type', action.get('action_type', 'Unknown Action'))
                result += f"### {action_type}\n\n"

                # Status
                action_status = action.get('status', 'N/A')
                status_icon = '🔴' if action_status == 'open' else '✅' if action_status == 'resolved' else '🟡'
                result += f"- **Status:** {status_icon} {action_status}\n"

                # Site info
                if 'site_name' in action:
                    result += f"- **Site:** {action['site_name']}\n"
                elif 'site_id' in action:
                    result += f"- **Site ID:** `{action['site_id']}`\n"

                # Affected devices/count
                if 'num_aps' in action:
                    result += f"- **Affected APs:** {action['num_aps']}\n"
                if 'num_switches' in action:
                    result += f"- **Affected Switches:** {action['num_switches']}\n"
                if 'num_gateways' in action:
                    result += f"- **Affected Gateways:** {action['num_gateways']}\n"
                if 'num_clients' in action:
                    result += f"- **Affected Clients:** {action['num_clients']}\n"

                # Device details
                if 'hostnames' in action and action['hostnames']:
                    hosts = action['hostnames'][:5]  # Show first 5
                    result += f"- **Devices:** {', '.join(hosts)}"
                    if len(action['hostnames']) > 5:
                        result += f" (+{len(action['hostnames']) - 5} more)"
                    result += "\n"

                if 'macs' in action and action['macs']:
                    macs = action['macs'][:3]
                    result += f"- **MACs:** {', '.join(macs)}"
                    if len(action['macs']) > 3:
                        result += f" (+{len(action['macs']) - 3} more)"
                    result += "\n"

                # Timestamp
                if 'timestamp' in action:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(action['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"- **Detected:** {ts}\n"
                elif 'last_seen' in action:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(action['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"- **Last Seen:** {ts}\n"

                # Description/details
                if 'details' in action:
                    result += f"- **Details:** {action['details']}\n"
                if 'reason' in action:
                    result += f"- **Reason:** {action['reason']}\n"
                if 'recommendation' in action:
                    result += f"- **Recommendation:** {action['recommendation']}\n"

                # Action ID for reference
                if 'id' in action:
                    result += f"- **Action ID:** `{action['id']}`\n"

                result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting Marvis actions: {str(e)}"


# ============================================================================
# Summary/Dashboard Tools
# ============================================================================

@mcp.tool()
async def get_org_stats_summary(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get a high-level summary of network statistics across the organization.

    Retrieves organization-wide metrics including total devices, clients,
    site health, and key performance indicators.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        Summary dashboard with device counts, health status, and key metrics

    Example:
        User: "Give me an overview of the network"
        -> Use this tool with the org_id

        User: "How is the network health?"
        -> Use this tool with the org_id

    Error Handling:
        - Aggregates data from multiple API calls
        - May take longer for large organizations
    """
    try:
        # Get organization stats
        org_stats = await mist_api_request(f"/orgs/{org_id}/stats")

        if format == "json":
            return json.dumps(org_stats, indent=2)

        result = "# Organization Network Summary\n\n"

        # Device counts
        result += "## Devices\n\n"
        result += f"- **Total Devices:** {org_stats.get('num_devices', 'N/A')}\n"
        result += f"- **Devices Connected:** {org_stats.get('num_devices_connected', 'N/A')}\n"
        result += f"- **Devices Disconnected:** {org_stats.get('num_devices_disconnected', 'N/A')}\n"

        if 'num_aps' in org_stats:
            result += f"\n### Access Points\n"
            result += f"- **Total APs:** {org_stats.get('num_aps', 0)}\n"
            result += f"- **APs Connected:** {org_stats.get('num_aps_connected', 0)}\n"
            result += f"- **APs Disconnected:** {org_stats.get('num_aps_disconnected', 0)}\n"

        if 'num_switches' in org_stats:
            result += f"\n### Switches\n"
            result += f"- **Total Switches:** {org_stats.get('num_switches', 0)}\n"
            result += f"- **Switches Connected:** {org_stats.get('num_switches_connected', 0)}\n"
            result += f"- **Switches Disconnected:** {org_stats.get('num_switches_disconnected', 0)}\n"

        if 'num_gateways' in org_stats:
            result += f"\n### Gateways\n"
            result += f"- **Total Gateways:** {org_stats.get('num_gateways', 0)}\n"
            result += f"- **Gateways Connected:** {org_stats.get('num_gateways_connected', 0)}\n"

        # Clients
        result += "\n## Clients\n\n"
        result += f"- **Connected Clients:** {org_stats.get('num_clients', 'N/A')}\n"

        # Sites
        result += "\n## Sites\n\n"
        result += f"- **Total Sites:** {org_stats.get('num_sites', 'N/A')}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting org summary: {str(e)}"


@mcp.tool()
async def get_device_config(
    site_id: str,
    device_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get the configuration of a specific device.

    Retrieves the full configuration of an AP, switch, or gateway including
    network settings, ports, radio config, and management settings.

    Args:
        site_id: Site UUID
        device_id: Device UUID (not MAC address - get from device inventory/stats)
        format: Response format

    Returns:
        Device configuration details

    Example:
        User: "Show me the config for device xyz"
        -> Use this tool with site_id and device_id

    Error Handling:
        - Device ID is UUID, not MAC address
        - Use search_organization_devices to find device IDs
    """
    try:
        config = await mist_api_request(f"/sites/{site_id}/devices/{device_id}")

        if format == "json":
            return json.dumps(config, indent=2)

        result = f"# Device Configuration\n\n"
        result += f"- **Name:** {config.get('name', 'N/A')}\n"
        result += f"- **Device ID:** `{config.get('id', 'N/A')}`\n"
        result += f"- **MAC:** {config.get('mac', 'N/A')}\n"
        result += f"- **Model:** {config.get('model', 'N/A')}\n"
        result += f"- **Type:** {config.get('type', 'N/A')}\n"

        if 'ip_config' in config:
            result += "\n## IP Configuration\n\n"
            ip_config = config['ip_config']
            result += f"- **Type:** {ip_config.get('type', 'N/A')}\n"
            if ip_config.get('ip'):
                result += f"- **IP:** {ip_config['ip']}\n"
            if ip_config.get('gateway'):
                result += f"- **Gateway:** {ip_config['gateway']}\n"

        if 'radio_config' in config:
            result += "\n## Radio Configuration\n\n"
            for band, radio in config['radio_config'].items():
                result += f"### {band}\n"
                result += f"- **Channel:** {radio.get('channel', 'Auto')}\n"
                result += f"- **Power:** {radio.get('power', 'Auto')}\n"
                result += f"- **Bandwidth:** {radio.get('bandwidth', 'N/A')}\n"
                result += "\n"

        if 'port_config' in config:
            result += "\n## Port Configuration\n\n"
            for port_name, port_cfg in list(config['port_config'].items())[:10]:
                result += f"### {port_name}\n"
                result += f"- **Usage:** {port_cfg.get('usage', 'N/A')}\n"
                if port_cfg.get('vlan_id'):
                    result += f"- **VLAN:** {port_cfg['vlan_id']}\n"
                result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device config: {str(e)}"


# ============================================================================
# Client Events & Troubleshooting Tools
# ============================================================================

@mcp.tool()
async def search_client_events(
    site_id: str,
    client_mac: Optional[str] = None,
    event_type: Optional[str] = None,
    ssid: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Search for wireless client events at a site for troubleshooting.

    Retrieves client connection events including associations, disassociations,
    roaming, authentication failures, and DHCP issues. Essential for troubleshooting
    client connectivity problems.

    Args:
        site_id: Site UUID
        client_mac: Optional client MAC address to filter events for specific client
        event_type: Optional event type filter (e.g., "CLIENT_AUTH_FAILURE", "CLIENT_CONNECTED",
                   "CLIENT_DISCONNECTED", "CLIENT_ROAM", "CLIENT_DHCP_FAILURE")
        ssid: Optional SSID name to filter events
        duration: Hours of history to search (default 24 hours)
        limit: Maximum events to return (default 100)
        format: Response format

    Returns:
        List of client events with timestamp, type, client info, and details

    Example:
        User: "Why can't client aa:bb:cc:dd:ee:ff connect?"
        -> Use this tool with client_mac="aa:bb:cc:dd:ee:ff"

        User: "Show me all auth failures in the last hour"
        -> Use this tool with event_type="CLIENT_AUTH_FAILURE", duration=1

        User: "What client events happened on the guest network?"
        -> Use this tool with ssid="Guest"

    Error Handling:
        - Returns empty if no events match the criteria
        - Use longer duration if recent events not found
    """
    try:
        import time
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "limit": limit,
            "start": start_time,
            "end": end_time
        }

        if client_mac:
            params["mac"] = client_mac.lower().replace("-", ":")
        if event_type:
            params["type"] = event_type
        if ssid:
            params["ssid"] = ssid

        events = await mist_api_request(f"/sites/{site_id}/clients/events/search", params=params)

        if format == "json":
            return json.dumps(events, indent=2)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            filter_desc = []
            if client_mac:
                filter_desc.append(f"client {client_mac}")
            if event_type:
                filter_desc.append(f"type {event_type}")
            if ssid:
                filter_desc.append(f"SSID {ssid}")
            filter_str = " for " + ", ".join(filter_desc) if filter_desc else ""
            return f"# Client Events\n\nNo events found{filter_str} in the last {duration} hour(s)."

        result = "# Client Events\n\n"
        result += f"Found {len(results_list)} event(s) in the last {duration} hour(s)\n\n"

        # Group by type for better readability
        by_type = {}
        for event in results_list:
            etype = event.get('type', 'UNKNOWN')
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(event)

        # Priority order for troubleshooting
        priority_types = ['CLIENT_AUTH_FAILURE', 'CLIENT_DHCP_FAILURE', 'CLIENT_DNS_FAILURE',
                         'CLIENT_DISCONNECTED', 'CLIENT_ROAM', 'CLIENT_CONNECTED']

        sorted_types = []
        for ptype in priority_types:
            if ptype in by_type:
                sorted_types.append(ptype)
        for etype in by_type:
            if etype not in sorted_types:
                sorted_types.append(etype)

        for etype in sorted_types:
            type_events = by_type[etype]
            # Use appropriate icons for different event types
            if 'FAILURE' in etype:
                icon = '🔴'
            elif 'DISCONNECTED' in etype:
                icon = '🟠'
            elif 'CONNECTED' in etype:
                icon = '🟢'
            elif 'ROAM' in etype:
                icon = '🔄'
            else:
                icon = '📋'

            result += f"## {icon} {etype} ({len(type_events)})\n\n"

            for event in type_events[:20]:  # Show up to 20 per type
                if 'timestamp' in event:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"### {ts}\n\n"

                result += f"- **Client MAC:** {event.get('mac', 'N/A')}\n"

                if event.get('hostname'):
                    result += f"- **Hostname:** {event['hostname']}\n"
                if event.get('ssid'):
                    result += f"- **SSID:** {event['ssid']}\n"
                if event.get('ap'):
                    result += f"- **AP:** {event['ap']}\n"
                if event.get('ap_mac'):
                    result += f"- **AP MAC:** {event['ap_mac']}\n"
                if event.get('band'):
                    result += f"- **Band:** {event['band']}\n"
                if event.get('channel'):
                    result += f"- **Channel:** {event['channel']}\n"
                if event.get('rssi'):
                    result += f"- **RSSI:** {event['rssi']} dBm\n"

                # Auth-specific fields
                if event.get('auth_type'):
                    result += f"- **Auth Type:** {event['auth_type']}\n"
                if event.get('username'):
                    result += f"- **Username:** {event['username']}\n"
                if event.get('failure_reason') or event.get('reason'):
                    reason = event.get('failure_reason') or event.get('reason')
                    result += f"- **Reason:** {reason}\n"

                # Network info
                if event.get('ip'):
                    result += f"- **IP:** {event['ip']}\n"
                if event.get('vlan'):
                    result += f"- **VLAN:** {event['vlan']}\n"

                result += "\n"

            if len(type_events) > 20:
                result += f"... and {len(type_events) - 20} more {etype} events\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching client events: {str(e)}"


@mcp.tool()
async def get_client_session_history(
    site_id: str,
    client_mac: str,
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get detailed session history for a specific wireless client.

    Retrieves comprehensive session information for a client including
    connection times, authentication details, roaming history, and network assignment.
    Essential for troubleshooting individual client issues.

    Args:
        site_id: Site UUID
        client_mac: Client MAC address (format: aa:bb:cc:dd:ee:ff)
        duration: Hours of history to retrieve (default 24)
        format: Response format

    Returns:
        Detailed session history with auth info, network assignment, and connection quality

    Example:
        User: "Show me the connection history for laptop aa:bb:cc:dd:ee:ff"
        -> Use this tool with the client_mac

        User: "What happened when this device tried to connect?"
        -> Use this tool to see auth attempts and session details

    Error Handling:
        - Returns empty if client not found or no sessions in timeframe
        - Increase duration if looking for older sessions
    """
    try:
        import time
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "mac": client_mac.lower().replace("-", ":"),
            "start": start_time,
            "end": end_time
        }

        sessions = await mist_api_request(f"/sites/{site_id}/clients/sessions/search", params=params)

        if format == "json":
            return json.dumps(sessions, indent=2)

        results_list = sessions.get('results', sessions) if isinstance(sessions, dict) else sessions

        if not results_list:
            return f"# Client Session History\n\nNo sessions found for client `{client_mac}` in the last {duration} hour(s)."

        result = f"# Client Session History\n\n"
        result += f"**Client MAC:** `{client_mac}`\n"
        result += f"**Time Range:** Last {duration} hour(s)\n"
        result += f"**Total Sessions:** {len(results_list)}\n\n"

        for i, session in enumerate(results_list, 1):
            result += f"## Session {i}\n\n"

            # Connection times
            if 'connect_time' in session or 'timestamp' in session:
                from datetime import datetime
                connect_ts = session.get('connect_time') or session.get('timestamp')
                result += f"- **Connected:** {datetime.fromtimestamp(connect_ts).strftime('%Y-%m-%d %H:%M:%S')}\n"
            if 'disconnect_time' in session:
                from datetime import datetime
                result += f"- **Disconnected:** {datetime.fromtimestamp(session['disconnect_time']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            if 'duration' in session:
                dur_min = session['duration'] / 60
                result += f"- **Duration:** {dur_min:.1f} minutes\n"

            # Device info
            if session.get('hostname'):
                result += f"- **Hostname:** {session['hostname']}\n"
            if session.get('device_name') or session.get('manufacture'):
                result += f"- **Device:** {session.get('manufacture', '')} {session.get('os', '')}\n"

            # Network assignment
            result += "\n### Network Assignment\n\n"
            if session.get('ssid'):
                result += f"- **SSID:** {session['ssid']}\n"
            if session.get('wlan_id'):
                result += f"- **WLAN ID:** `{session['wlan_id']}`\n"
            if session.get('vlan'):
                result += f"- **VLAN:** {session['vlan']}\n"
            if session.get('ip'):
                result += f"- **IP Address:** {session['ip']}\n"

            # Authentication
            result += "\n### Authentication\n\n"
            if session.get('auth_type'):
                result += f"- **Auth Type:** {session['auth_type']}\n"
            if session.get('username'):
                result += f"- **Username:** {session['username']}\n"
            if session.get('psk_name'):
                result += f"- **PSK Name:** {session['psk_name']}\n"
            if session.get('idp_id'):
                result += f"- **IdP ID:** `{session['idp_id']}`\n"
            if session.get('nac_rule_matched'):
                result += f"- **NAC Rule Matched:** {session['nac_rule_matched']}\n"
            if session.get('nac_role'):
                result += f"- **NAC Role:** {session['nac_role']}\n"

            # Connection quality
            result += "\n### Connection Details\n\n"
            if session.get('ap'):
                result += f"- **Access Point:** {session['ap']}\n"
            if session.get('ap_mac'):
                result += f"- **AP MAC:** {session['ap_mac']}\n"
            if session.get('band'):
                result += f"- **Band:** {session['band']}\n"
            if session.get('channel'):
                result += f"- **Channel:** {session['channel']}\n"
            if session.get('rssi'):
                result += f"- **RSSI:** {session['rssi']} dBm\n"
            if session.get('snr'):
                result += f"- **SNR:** {session['snr']} dB\n"

            # Disconnect reason
            if session.get('disconnect_reason'):
                result += f"\n### Disconnect\n\n"
                result += f"- **Reason:** {session['disconnect_reason']}\n"

            result += "\n---\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting client session history: {str(e)}"


# ============================================================================
# NAC (Network Access Control) Tools
# ============================================================================

@mcp.tool()
async def search_nac_client_events(
    org_id: str,
    site_id: Optional[str] = None,
    client_mac: Optional[str] = None,
    username: Optional[str] = None,
    auth_type: Optional[str] = None,
    nac_result: Optional[Literal["success", "failure", "all"]] = "all",
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Search NAC (Network Access Control) authentication events.

    Retrieves 802.1X, RADIUS, and NAC authentication events including successes,
    failures, and policy matches. Critical for troubleshooting authentication issues.

    Args:
        org_id: Organization UUID
        site_id: Optional site UUID to filter by site
        client_mac: Optional client MAC address to filter
        username: Optional username to filter (for 802.1X)
        auth_type: Optional auth type filter (e.g., "dot1x", "mab", "psk")
        nac_result: Filter by result - "success", "failure", or "all"
        duration: Hours of history to search (default 24)
        limit: Maximum events to return (default 100)
        format: Response format

    Returns:
        NAC events with auth details, policy matches, and failure reasons

    Example:
        User: "Why can't john@example.com authenticate?"
        -> Use this tool with username="john@example.com"

        User: "Show me all 802.1X failures"
        -> Use this tool with auth_type="dot1x", nac_result="failure"

        User: "What NAC events happened for device aa:bb:cc:dd:ee:ff?"
        -> Use this tool with client_mac="aa:bb:cc:dd:ee:ff"

    Error Handling:
        - Returns empty if no NAC events match criteria
        - Requires NAC/802.1X to be configured
    """
    try:
        import time
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "limit": limit,
            "start": start_time,
            "end": end_time
        }

        if client_mac:
            params["mac"] = client_mac.lower().replace("-", ":")
        if username:
            params["username"] = username
        if auth_type:
            params["auth_type"] = auth_type
        if nac_result and nac_result != "all":
            params["nac_result"] = nac_result

        # Try org-level or site-level NAC events
        if site_id:
            endpoint = f"/sites/{site_id}/nac_clients/events/search"
        else:
            endpoint = f"/orgs/{org_id}/nac_clients/events/search"

        events = await mist_api_request(endpoint, params=params)

        if format == "json":
            return json.dumps(events, indent=2)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            return f"# NAC Client Events\n\nNo NAC events found in the last {duration} hour(s)."

        result = "# NAC Client Events\n\n"
        result += f"Found {len(results_list)} event(s) in the last {duration} hour(s)\n\n"

        # Group by result
        successes = [e for e in results_list if e.get('nac_result') == 'success' or e.get('auth_result') == 'success']
        failures = [e for e in results_list if e.get('nac_result') == 'failure' or e.get('auth_result') == 'failure']
        others = [e for e in results_list if e not in successes and e not in failures]

        if failures:
            result += f"## 🔴 Authentication Failures ({len(failures)})\n\n"
            for event in failures[:30]:
                if 'timestamp' in event:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"### {ts}\n\n"

                result += f"- **Client MAC:** {event.get('mac', 'N/A')}\n"
                if event.get('username'):
                    result += f"- **Username:** {event['username']}\n"
                if event.get('auth_type'):
                    result += f"- **Auth Type:** {event['auth_type']}\n"
                if event.get('ssid'):
                    result += f"- **SSID:** {event['ssid']}\n"
                if event.get('ap') or event.get('ap_mac'):
                    result += f"- **AP:** {event.get('ap', event.get('ap_mac', 'N/A'))}\n"

                # Failure details - critical for troubleshooting
                if event.get('failure_reason'):
                    result += f"- **⚠️ Failure Reason:** {event['failure_reason']}\n"
                if event.get('reason'):
                    result += f"- **⚠️ Reason:** {event['reason']}\n"
                if event.get('radius_reply_code'):
                    result += f"- **RADIUS Reply Code:** {event['radius_reply_code']}\n"
                if event.get('radius_reply_message'):
                    result += f"- **RADIUS Message:** {event['radius_reply_message']}\n"

                # NAC policy info
                if event.get('nac_rule_id'):
                    result += f"- **NAC Rule ID:** `{event['nac_rule_id']}`\n"
                if event.get('nac_policy'):
                    result += f"- **NAC Policy:** {event['nac_policy']}\n"

                result += "\n"

            if len(failures) > 30:
                result += f"... and {len(failures) - 30} more failures\n\n"

        if successes:
            result += f"## 🟢 Authentication Successes ({len(successes)})\n\n"
            for event in successes[:20]:
                if 'timestamp' in event:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"### {ts}\n\n"

                result += f"- **Client MAC:** {event.get('mac', 'N/A')}\n"
                if event.get('username'):
                    result += f"- **Username:** {event['username']}\n"
                if event.get('auth_type'):
                    result += f"- **Auth Type:** {event['auth_type']}\n"
                if event.get('ssid'):
                    result += f"- **SSID:** {event['ssid']}\n"

                # Assigned attributes
                if event.get('vlan'):
                    result += f"- **Assigned VLAN:** {event['vlan']}\n"
                if event.get('nac_role'):
                    result += f"- **NAC Role:** {event['nac_role']}\n"
                if event.get('nac_rule_matched'):
                    result += f"- **NAC Rule Matched:** {event['nac_rule_matched']}\n"
                if event.get('user_group'):
                    result += f"- **User Group:** {event['user_group']}\n"

                result += "\n"

            if len(successes) > 20:
                result += f"... and {len(successes) - 20} more successes\n\n"

        if others:
            result += f"## 📋 Other Events ({len(others)})\n\n"
            for event in others[:10]:
                result += f"- {event.get('type', 'Unknown')}: MAC {event.get('mac', 'N/A')}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching NAC events: {str(e)}"


@mcp.tool()
async def get_nac_rules(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get NAC (Network Access Control) rules and policies.

    Retrieves all NAC rules configured at the organization level, including
    matching criteria, actions, and VLAN assignments. Useful for understanding
    why clients are assigned to specific VLANs or denied access.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        List of NAC rules with matching criteria, actions, and priority

    Example:
        User: "What NAC rules are configured?"
        -> Use this tool with the org_id

        User: "Why was this client put in VLAN 100?"
        -> Use this tool to see which rule matched

    Error Handling:
        - Returns empty if no NAC rules configured
        - NAC rules require appropriate license
    """
    try:
        rules = await mist_api_request(f"/orgs/{org_id}/nacrules")

        if format == "json":
            return json.dumps(rules, indent=2)

        if not rules:
            return "# NAC Rules\n\nNo NAC rules configured in this organization."

        result = "# NAC Rules\n\n"
        result += f"Found {len(rules)} NAC rule(s)\n\n"

        # Sort by order/priority if available
        sorted_rules = sorted(rules, key=lambda x: x.get('order', x.get('priority', 999)))

        for rule in sorted_rules:
            rule_name = rule.get('name', 'Unnamed Rule')
            result += f"## {rule_name}\n\n"

            result += f"- **Rule ID:** `{rule.get('id', 'N/A')}`\n"
            if 'order' in rule:
                result += f"- **Priority/Order:** {rule['order']}\n"
            result += f"- **Enabled:** {'Yes' if rule.get('enabled', True) else 'No'}\n"

            # Matching criteria
            result += "\n### Matching Criteria\n\n"

            if rule.get('matching'):
                matching = rule['matching']
                if matching.get('auth_type'):
                    result += f"- **Auth Type:** {matching['auth_type']}\n"
                if matching.get('nac_tag'):
                    result += f"- **NAC Tag:** {matching['nac_tag']}\n"
                if matching.get('user_groups'):
                    result += f"- **User Groups:** {', '.join(matching['user_groups'])}\n"
                if matching.get('vendor'):
                    result += f"- **Vendor:** {matching['vendor']}\n"
                if matching.get('family'):
                    result += f"- **Device Family:** {matching['family']}\n"
                if matching.get('os'):
                    result += f"- **OS:** {matching['os']}\n"
                if matching.get('idp_roles'):
                    result += f"- **IdP Roles:** {', '.join(matching['idp_roles'])}\n"
                if matching.get('port_types'):
                    result += f"- **Port Types:** {', '.join(matching['port_types'])}\n"

            # Actions
            result += "\n### Actions\n\n"

            if rule.get('action') or rule.get('actions'):
                action = rule.get('action') or rule.get('actions', {})
                if isinstance(action, dict):
                    if action.get('action'):
                        result += f"- **Action:** {action['action']}\n"
                    if action.get('vlan_id'):
                        result += f"- **Assign VLAN:** {action['vlan_id']}\n"
                    if action.get('nac_tag'):
                        result += f"- **Assign NAC Tag:** {action['nac_tag']}\n"
                    if action.get('user_group'):
                        result += f"- **Assign User Group:** {action['user_group']}\n"
                    if action.get('session_timeout'):
                        result += f"- **Session Timeout:** {action['session_timeout']} seconds\n"
                    if action.get('idle_timeout'):
                        result += f"- **Idle Timeout:** {action['idle_timeout']} seconds\n"
                else:
                    result += f"- **Action:** {action}\n"

            # Not matching criteria (deny)
            if rule.get('not_matching'):
                result += "\n### Exclusions (NOT Matching)\n\n"
                for key, value in rule['not_matching'].items():
                    result += f"- **NOT {key}:** {value}\n"

            result += "\n---\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting NAC rules: {str(e)}"


@mcp.tool()
async def get_nac_tags(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get NAC tags (labels/roles) configured in the organization.

    NAC tags are labels used to categorize clients and apply policies.
    They can be assigned by RADIUS, IdP, or NAC rules.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        List of NAC tags with their types and values

    Example:
        User: "What NAC tags are available?"
        -> Use this tool with the org_id

        User: "What roles can be assigned to clients?"
        -> Use this tool to see available NAC tags

    Error Handling:
        - Returns empty if no NAC tags configured
    """
    try:
        tags = await mist_api_request(f"/orgs/{org_id}/nactags")

        if format == "json":
            return json.dumps(tags, indent=2)

        if not tags:
            return "# NAC Tags\n\nNo NAC tags configured in this organization."

        result = "# NAC Tags\n\n"
        result += f"Found {len(tags)} NAC tag(s)\n\n"

        # Group by type
        by_type = {}
        for tag in tags:
            tag_type = tag.get('type', 'custom')
            if tag_type not in by_type:
                by_type[tag_type] = []
            by_type[tag_type].append(tag)

        for tag_type, type_tags in by_type.items():
            result += f"## {tag_type.title()} Tags ({len(type_tags)})\n\n"

            for tag in type_tags:
                tag_name = tag.get('name', 'Unnamed Tag')
                result += f"### {tag_name}\n\n"

                result += f"- **Tag ID:** `{tag.get('id', 'N/A')}`\n"
                result += f"- **Type:** {tag.get('type', 'N/A')}\n"

                if tag.get('values'):
                    result += f"- **Values:** {', '.join(str(v) for v in tag['values'])}\n"
                if tag.get('match'):
                    result += f"- **Match:** {tag['match']}\n"
                if tag.get('vlan_id'):
                    result += f"- **Associated VLAN:** {tag['vlan_id']}\n"
                if tag.get('gbp_tag'):
                    result += f"- **GBP Tag:** {tag['gbp_tag']}\n"
                if tag.get('radius_group'):
                    result += f"- **RADIUS Group:** {tag['radius_group']}\n"

                result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting NAC tags: {str(e)}"


@mcp.tool()
async def get_org_radius_config(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get RADIUS and authentication server configurations.

    Retrieves RADIUS server configurations, including primary/secondary servers,
    authentication settings, and accounting configuration. Essential for
    troubleshooting 802.1X and NAC authentication issues.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        RADIUS configuration including servers, ports, and settings

    Example:
        User: "What RADIUS servers are configured?"
        -> Use this tool with the org_id

        User: "Show me the authentication configuration"
        -> Use this tool to see RADIUS/IdP settings

    Error Handling:
        - Returns empty if no RADIUS configured
        - Does not show shared secrets for security
    """
    try:
        # Get org settings which includes RADIUS config
        org_settings = await mist_api_request(f"/orgs/{org_id}/setting")

        if format == "json":
            # Filter to RADIUS-related settings only
            radius_config = {
                'radius': org_settings.get('radius', {}),
                'radius_proxy': org_settings.get('radius_proxy', {}),
                'mist_nac': org_settings.get('mist_nac', {}),
                'coa_servers': org_settings.get('coa_servers', [])
            }
            return json.dumps(radius_config, indent=2)

        result = "# RADIUS & Authentication Configuration\n\n"

        # Mist NAC settings
        if org_settings.get('mist_nac'):
            nac = org_settings['mist_nac']
            result += "## Mist NAC\n\n"
            result += f"- **Enabled:** {'Yes' if nac.get('enabled') else 'No'}\n"
            if nac.get('idps'):
                result += f"- **Identity Providers:** {len(nac['idps'])}\n"
            if nac.get('default_idp_id'):
                result += f"- **Default IdP:** `{nac['default_idp_id']}`\n"
            result += "\n"

        # RADIUS servers
        if org_settings.get('radius'):
            radius = org_settings['radius']
            result += "## RADIUS Servers\n\n"

            if radius.get('auth_servers'):
                result += "### Authentication Servers\n\n"
                for i, server in enumerate(radius['auth_servers'], 1):
                    result += f"#### Server {i}\n"
                    result += f"- **Host:** {server.get('host', 'N/A')}\n"
                    result += f"- **Port:** {server.get('port', 1812)}\n"
                    result += f"- **Secret:** {'Configured' if server.get('secret') else 'Not set'}\n"
                    result += "\n"

            if radius.get('acct_servers'):
                result += "### Accounting Servers\n\n"
                for i, server in enumerate(radius['acct_servers'], 1):
                    result += f"#### Server {i}\n"
                    result += f"- **Host:** {server.get('host', 'N/A')}\n"
                    result += f"- **Port:** {server.get('port', 1813)}\n"
                    result += "\n"

        # RADIUS proxy
        if org_settings.get('radius_proxy'):
            proxy = org_settings['radius_proxy']
            result += "## RADIUS Proxy\n\n"
            result += f"- **Enabled:** {'Yes' if proxy.get('enabled') else 'No'}\n"
            if proxy.get('auth_servers'):
                result += f"- **Upstream Servers:** {len(proxy['auth_servers'])}\n"
            result += "\n"

        # CoA servers
        if org_settings.get('coa_servers'):
            result += "## CoA (Change of Authorization) Servers\n\n"
            for i, server in enumerate(org_settings['coa_servers'], 1):
                result += f"### CoA Server {i}\n"
                result += f"- **IP:** {server.get('ip', 'N/A')}\n"
                result += f"- **Port:** {server.get('port', 3799)}\n"
                result += "\n"

        if result == "# RADIUS & Authentication Configuration\n\n":
            result += "No RADIUS or NAC configuration found.\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting RADIUS config: {str(e)}"


@mcp.tool()
async def search_wired_client_events(
    site_id: str,
    client_mac: Optional[str] = None,
    switch_mac: Optional[str] = None,
    port_id: Optional[str] = None,
    event_type: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Search for wired client events at a site.

    Retrieves 802.1X authentication events, port security events, and
    wired client connectivity events from switches. Essential for
    troubleshooting wired NAC and port security issues.

    Args:
        site_id: Site UUID
        client_mac: Optional client MAC address to filter
        switch_mac: Optional switch MAC to filter events for specific switch
        port_id: Optional port identifier (e.g., "ge-0/0/1")
        event_type: Optional event type filter (e.g., "NAC_CLIENT_PERMIT", "NAC_CLIENT_DENY")
        duration: Hours of history to search (default 24)
        limit: Maximum events to return (default 100)
        format: Response format

    Returns:
        Wired client events with port, switch, auth status, and failure reasons

    Example:
        User: "Why can't this device authenticate on the switch port?"
        -> Use this tool with client_mac or port_id

        User: "Show me all denied wired clients"
        -> Use this tool with event_type="NAC_CLIENT_DENY"

    Error Handling:
        - Returns empty if no wired events match criteria
        - Requires switches with 802.1X/NAC configured
    """
    try:
        import time
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "limit": limit,
            "start": start_time,
            "end": end_time
        }

        if client_mac:
            params["mac"] = client_mac.lower().replace("-", ":")
        if switch_mac:
            params["switch_mac"] = switch_mac.lower().replace("-", ":")
        if port_id:
            params["port_id"] = port_id
        if event_type:
            params["type"] = event_type

        events = await mist_api_request(f"/sites/{site_id}/wired_clients/events/search", params=params)

        if format == "json":
            return json.dumps(events, indent=2)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            return f"# Wired Client Events\n\nNo wired client events found in the last {duration} hour(s)."

        result = "# Wired Client Events\n\n"
        result += f"Found {len(results_list)} event(s) in the last {duration} hour(s)\n\n"

        # Group by type
        by_type = {}
        for event in results_list:
            etype = event.get('type', 'UNKNOWN')
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(event)

        # Show denials first
        for etype in sorted(by_type.keys(), key=lambda x: 0 if 'DENY' in x else 1):
            type_events = by_type[etype]
            icon = '🔴' if 'DENY' in etype or 'FAILURE' in etype else '🟢' if 'PERMIT' in etype or 'SUCCESS' in etype else '📋'

            result += f"## {icon} {etype} ({len(type_events)})\n\n"

            for event in type_events[:25]:
                if 'timestamp' in event:
                    from datetime import datetime
                    ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"### {ts}\n\n"

                result += f"- **Client MAC:** {event.get('mac', 'N/A')}\n"

                # Switch/port info
                if event.get('switch_name') or event.get('switch_mac'):
                    result += f"- **Switch:** {event.get('switch_name', event.get('switch_mac', 'N/A'))}\n"
                if event.get('port_id'):
                    result += f"- **Port:** {event['port_id']}\n"

                # Auth details
                if event.get('username'):
                    result += f"- **Username:** {event['username']}\n"
                if event.get('auth_type'):
                    result += f"- **Auth Type:** {event['auth_type']}\n"

                # Result/VLAN assignment
                if event.get('vlan'):
                    result += f"- **VLAN Assigned:** {event['vlan']}\n"
                if event.get('nac_role'):
                    result += f"- **NAC Role:** {event['nac_role']}\n"

                # Failure reasons
                if event.get('failure_reason'):
                    result += f"- **⚠️ Failure Reason:** {event['failure_reason']}\n"
                if event.get('reason'):
                    result += f"- **⚠️ Reason:** {event['reason']}\n"
                if event.get('radius_reply_message'):
                    result += f"- **RADIUS Message:** {event['radius_reply_message']}\n"

                result += "\n"

            if len(type_events) > 25:
                result += f"... and {len(type_events) - 25} more {etype} events\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching wired client events: {str(e)}"


@mcp.tool()
async def get_client_by_mac(
    org_id: str,
    client_mac: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Look up detailed information about a client by MAC address.

    Retrieves comprehensive client details including current connection status,
    authentication info, assigned network attributes, and device identification.
    Searches across the entire organization.

    Args:
        org_id: Organization UUID
        client_mac: Client MAC address (format: aa:bb:cc:dd:ee:ff)
        format: Response format

    Returns:
        Client details including status, auth, network assignment, device info

    Example:
        User: "Tell me about client aa:bb:cc:dd:ee:ff"
        -> Use this tool with the client_mac

        User: "Is this MAC address currently connected?"
        -> Use this tool to get current connection status

    Error Handling:
        - Returns not found if client never connected
        - Shows last known info if client currently disconnected
    """
    try:
        mac_normalized = client_mac.lower().replace("-", ":")

        # Search for the client across the org
        params = {
            "mac": mac_normalized,
            "limit": 1
        }

        clients = await mist_api_request(f"/orgs/{org_id}/clients/search", params=params)

        if format == "json":
            return json.dumps(clients, indent=2)

        results_list = clients.get('results', clients) if isinstance(clients, dict) else clients

        if not results_list:
            return f"# Client Lookup\n\nNo client found with MAC address `{client_mac}`."

        client = results_list[0]

        result = f"# Client Details\n\n"
        result += f"**MAC Address:** `{client.get('mac', client_mac)}`\n\n"

        # Basic info
        result += "## Device Information\n\n"
        if client.get('hostname'):
            result += f"- **Hostname:** {client['hostname']}\n"
        if client.get('manufacture'):
            result += f"- **Manufacturer:** {client['manufacture']}\n"
        if client.get('os'):
            result += f"- **Operating System:** {client['os']}\n"
        if client.get('model'):
            result += f"- **Model:** {client['model']}\n"
        if client.get('device'):
            result += f"- **Device Type:** {client['device']}\n"

        # Connection status
        result += "\n## Connection Status\n\n"
        if client.get('connected'):
            result += "- **Status:** 🟢 Connected\n"
        else:
            result += "- **Status:** 🔴 Disconnected\n"

        if client.get('site_name') or client.get('site_id'):
            result += f"- **Site:** {client.get('site_name', client.get('site_id', 'N/A'))}\n"
        if client.get('ap') or client.get('ap_mac'):
            result += f"- **Access Point:** {client.get('ap', client.get('ap_mac', 'N/A'))}\n"
        if client.get('ssid'):
            result += f"- **SSID:** {client['ssid']}\n"
        if client.get('band'):
            result += f"- **Band:** {client['band']}\n"
        if client.get('channel'):
            result += f"- **Channel:** {client['channel']}\n"

        # Network assignment
        result += "\n## Network Assignment\n\n"
        if client.get('ip'):
            result += f"- **IP Address:** {client['ip']}\n"
        if client.get('vlan'):
            result += f"- **VLAN:** {client['vlan']}\n"
        if client.get('network'):
            result += f"- **Network:** {client['network']}\n"

        # Authentication
        result += "\n## Authentication\n\n"
        if client.get('auth_type'):
            result += f"- **Auth Type:** {client['auth_type']}\n"
        if client.get('username'):
            result += f"- **Username:** {client['username']}\n"
        if client.get('psk_name'):
            result += f"- **PSK Name:** {client['psk_name']}\n"
        if client.get('nac_role'):
            result += f"- **NAC Role:** {client['nac_role']}\n"
        if client.get('idp_id'):
            result += f"- **IdP ID:** `{client['idp_id']}`\n"
        if client.get('user_group'):
            result += f"- **User Group:** {client['user_group']}\n"

        # Signal quality
        if client.get('rssi') or client.get('snr'):
            result += "\n## Signal Quality\n\n"
            if client.get('rssi'):
                result += f"- **RSSI:** {client['rssi']} dBm\n"
            if client.get('snr'):
                result += f"- **SNR:** {client['snr']} dB\n"

        # Timestamps
        result += "\n## Timestamps\n\n"
        if client.get('last_seen'):
            from datetime import datetime
            ts = datetime.fromtimestamp(client['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **Last Seen:** {ts}\n"
        if client.get('first_seen'):
            from datetime import datetime
            ts = datetime.fromtimestamp(client['first_seen']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **First Seen:** {ts}\n"
        if client.get('connect_time'):
            from datetime import datetime
            ts = datetime.fromtimestamp(client['connect_time']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **Connected At:** {ts}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error looking up client: {str(e)}"


@mcp.tool()
async def get_org_idps(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get Identity Provider (IdP) configurations for NAC.

    Retrieves configured identity providers used for authentication,
    including LDAP, Azure AD, Okta, and other SAML/OAuth providers.

    Args:
        org_id: Organization UUID
        format: Response format

    Returns:
        List of IdPs with connection settings and status

    Example:
        User: "What identity providers are configured?"
        -> Use this tool with the org_id

        User: "Is Azure AD configured for authentication?"
        -> Use this tool to see configured IdPs

    Error Handling:
        - Returns empty if no IdPs configured
        - Does not show sensitive credentials
    """
    try:
        # IdPs are under the SSO endpoint in Mist API
        idps = await mist_api_request(f"/orgs/{org_id}/ssos")

        if format == "json":
            return json.dumps(idps, indent=2)

        if not idps:
            return "# Identity Providers\n\nNo Identity Providers configured."

        result = "# Identity Providers (IdPs)\n\n"
        result += f"Found {len(idps)} IdP(s)\n\n"

        for idp in idps:
            name = idp.get('name', 'Unnamed IdP')
            result += f"## {name}\n\n"

            result += f"- **IdP ID:** `{idp.get('id', 'N/A')}`\n"
            result += f"- **Type:** {idp.get('idp_type', idp.get('type', 'N/A'))}\n"

            if idp.get('domain'):
                result += f"- **Domain:** {idp['domain']}\n"
            if idp.get('issuer'):
                result += f"- **Issuer:** {idp['issuer']}\n"
            if idp.get('nameid_format'):
                result += f"- **NameID Format:** {idp['nameid_format']}\n"

            # LDAP-specific
            if idp.get('ldap_type'):
                result += f"- **LDAP Type:** {idp['ldap_type']}\n"
            if idp.get('ldap_server'):
                result += f"- **LDAP Server:** {idp['ldap_server']}\n"
            if idp.get('ldap_base_dn'):
                result += f"- **Base DN:** {idp['ldap_base_dn']}\n"
            if idp.get('ldap_user_filter'):
                result += f"- **User Filter:** {idp['ldap_user_filter']}\n"

            # OAuth/SAML
            if idp.get('oauth_cc_client_id'):
                client_id = idp['oauth_cc_client_id']
                result += f"- **OAuth Client ID:** {client_id[:20]}{'...' if len(client_id) > 20 else ''}\n"
            if idp.get('oauth_type'):
                result += f"- **OAuth Type:** {idp['oauth_type']}\n"
            if idp.get('scim_enabled'):
                result += f"- **SCIM Enabled:** Yes\n"

            # Group/role mapping
            if idp.get('group_filter'):
                result += f"- **Group Filter:** {idp['group_filter']}\n"
            if idp.get('role_attr_extraction'):
                result += f"- **Role Attribute:** {idp['role_attr_extraction']}\n"
            if idp.get('role_attr_from'):
                result += f"- **Role Source:** {idp['role_attr_from']}\n"

            # MDM integration
            if idp.get('mxedge_proxy_enabled'):
                result += f"- **MXEdge Proxy:** Enabled\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting IdPs: {str(e)}"


@mcp.tool()
async def get_nac_portal_logs(
    org_id: str,
    site_id: Optional[str] = None,
    nac_portal_id: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get NAC portal (guest/sponsor) authentication logs.

    Retrieves logs from NAC portals including guest registration,
    sponsor approvals, and self-registration events.

    Args:
        org_id: Organization UUID
        site_id: Optional site UUID to filter
        nac_portal_id: Optional NAC portal ID to filter
        duration: Hours of history (default 24)
        limit: Maximum logs to return (default 100)
        format: Response format

    Returns:
        NAC portal events with registration details and approvals

    Example:
        User: "Show me guest registration activity"
        -> Use this tool with the org_id

        User: "What sponsor approvals happened today?"
        -> Use this tool to see NAC portal logs

    Error Handling:
        - Returns empty if no NAC portals or activity
        - Requires NAC portal to be configured
    """
    try:
        import time
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        # First check if any NAC portals are configured
        try:
            portals = await mist_api_request(f"/orgs/{org_id}/nacportals")
            if not portals:
                return "# NAC Portal Logs\n\nNo NAC portals configured in this organization."
        except Exception:
            # NAC portals endpoint not available or no portals configured
            return "# NAC Portal Logs\n\nNo NAC portals configured or NAC portal feature not available."

        # Try to get guest authorization logs
        params = {
            "limit": limit,
            "start": start_time,
            "end": end_time
        }

        if site_id:
            params["site_id"] = site_id

        # Guest authorizations are part of the NAC client events
        # Filter for portal-related events
        try:
            logs = await mist_api_request(f"/orgs/{org_id}/nac_clients/events/search", params=params)
        except Exception:
            # Fall back to listing configured portals
            if format == "json":
                return json.dumps({"portals": portals, "logs": []}, indent=2)

            result = "# NAC Portals\n\n"
            result += f"Found {len(portals)} NAC portal(s) configured:\n\n"
            for portal in portals:
                result += f"## {portal.get('name', 'Unnamed Portal')}\n\n"
                result += f"- **Portal ID:** `{portal.get('id', 'N/A')}`\n"
                if portal.get('ssid'):
                    result += f"- **SSID:** {portal['ssid']}\n"
                if portal.get('auth'):
                    result += f"- **Auth Type:** {portal['auth']}\n"
                result += "\n"
            result += "\n*Note: No guest authorization logs available for the requested time period.*\n"
            return truncate_response(result)

        if format == "json":
            return json.dumps(logs, indent=2)

        results_list = logs.get('results', logs) if isinstance(logs, dict) else logs

        if not results_list:
            return f"# NAC Portal Logs\n\nNo NAC portal activity found in the last {duration} hour(s)."

        result = "# NAC Portal Logs\n\n"
        result += f"Found {len(results_list)} log entries in the last {duration} hour(s)\n\n"

        for log in results_list[:limit]:
            if 'timestamp' in log:
                from datetime import datetime
                ts = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                result += f"## {ts}\n\n"

            result += f"- **Type:** {log.get('type', 'N/A')}\n"

            if log.get('name') or log.get('guest_name'):
                result += f"- **Guest Name:** {log.get('name', log.get('guest_name', 'N/A'))}\n"
            if log.get('email') or log.get('guest_email'):
                result += f"- **Email:** {log.get('email', log.get('guest_email', 'N/A'))}\n"
            if log.get('company'):
                result += f"- **Company:** {log['company']}\n"
            if log.get('sponsor_name'):
                result += f"- **Sponsor:** {log['sponsor_name']}\n"
            if log.get('sponsor_email'):
                result += f"- **Sponsor Email:** {log['sponsor_email']}\n"

            if log.get('mac'):
                result += f"- **Client MAC:** {log['mac']}\n"
            if log.get('ssid'):
                result += f"- **SSID:** {log['ssid']}\n"
            if log.get('username'):
                result += f"- **Username:** {log['username']}\n"

            if log.get('authorized') is not None:
                result += f"- **Authorized:** {'Yes' if log['authorized'] else 'No'}\n"
            if log.get('nac_result'):
                result += f"- **Result:** {log['nac_result']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting NAC portal logs: {str(e)}"


# ============================================================================
# Server Entry Point
# ============================================================================

def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
