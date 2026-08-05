"""Monitoring tools for the Juniper Mist MCP server."""

import json
from datetime import datetime
from typing import Literal

from ..api import mist_api_request
from ..formatting import truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY)
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

        response = await mist_api_request(f"/orgs/{org_id}/alarms/search", params=params)

        if format == "json":
            return truncate_response(json.dumps(response, indent=2))

        # Extract alarms from the results key
        alarms = response.get("results", []) if isinstance(response, dict) else response

        if not alarms:
            return "# Network Alarms\n\nNo active alarms found. Network is healthy!"

        result = "# Network Alarms\n\n"
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

@mcp.tool(annotations=READ_ONLY)
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
            return truncate_response(json.dumps(actions, indent=2))

        # Handle response format (could be list or dict with results)
        results_list = actions.get('results', actions) if isinstance(actions, dict) else actions

        if not results_list:
            return "# Marvis Actions\n\nNo active Marvis actions. Network looks healthy!"

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
                status_icon = '[OPEN]' if action_status == 'open' else '[RESOLVED]' if action_status == 'resolved' else '[PENDING]'
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
                    ts = datetime.fromtimestamp(action['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"- **Detected:** {ts}\n"
                elif 'last_seen' in action:
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

@mcp.tool(annotations=READ_ONLY)
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
            return truncate_response(json.dumps(stats, indent=2))

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
