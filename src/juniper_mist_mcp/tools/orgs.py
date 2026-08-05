"""Organization & site tools for the Juniper Mist MCP server."""

from typing import Literal

from mcp.types import CallToolResult

from ..api import mist_api_request
from ..formatting import json_tool_result, format_as_markdown, truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_organizations(
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(orgs)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_organization_info(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(org)

        return truncate_response(format_as_markdown(org, f"Organization: {org.get('name', org_id)}"))

    except Exception as e:
        return f"Error getting organization info: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_sites(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(sites)

        if not sites:
            return f"# Sites in Organization {org_id}\n\nNo sites found."

        result = "# Sites in Organization\n\n"
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_site_info(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(site)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_site_stats(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(stats)

        result = "# Site Statistics\n\n"

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
            result += "\n## Access Points\n"
            result += f"- **Total APs:** {stats.get('num_aps', 0)}\n"
            result += f"- **APs Connected:** {stats.get('num_aps_connected', 0)}\n"

        if 'num_switches' in stats:
            result += "\n## Switches\n"
            result += f"- **Total Switches:** {stats.get('num_switches', 0)}\n"
            result += f"- **Switches Connected:** {stats.get('num_switches_connected', 0)}\n"

        if 'num_gateways' in stats:
            result += "\n## Gateways\n"
            result += f"- **Total Gateways:** {stats.get('num_gateways', 0)}\n"
            result += f"- **Gateways Connected:** {stats.get('num_gateways_connected', 0)}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting site stats: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_org_stats_summary(
    org_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
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
            return json_tool_result(org_stats)

        result = "# Organization Network Summary\n\n"

        # Device counts
        result += "## Devices\n\n"
        result += f"- **Total Devices:** {org_stats.get('num_devices', 'N/A')}\n"
        result += f"- **Devices Connected:** {org_stats.get('num_devices_connected', 'N/A')}\n"
        result += f"- **Devices Disconnected:** {org_stats.get('num_devices_disconnected', 'N/A')}\n"

        if 'num_aps' in org_stats:
            result += "\n### Access Points\n"
            result += f"- **Total APs:** {org_stats.get('num_aps', 0)}\n"
            result += f"- **APs Connected:** {org_stats.get('num_aps_connected', 0)}\n"
            result += f"- **APs Disconnected:** {org_stats.get('num_aps_disconnected', 0)}\n"

        if 'num_switches' in org_stats:
            result += "\n### Switches\n"
            result += f"- **Total Switches:** {org_stats.get('num_switches', 0)}\n"
            result += f"- **Switches Connected:** {org_stats.get('num_switches_connected', 0)}\n"
            result += f"- **Switches Disconnected:** {org_stats.get('num_switches_disconnected', 0)}\n"

        if 'num_gateways' in org_stats:
            result += "\n### Gateways\n"
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
