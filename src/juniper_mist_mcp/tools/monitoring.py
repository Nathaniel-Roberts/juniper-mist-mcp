"""Monitoring tools for the Juniper Mist MCP server."""

import time
from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import get_org_sites, mist_api_request, resolve_org_id, resolve_site_id
from ..formatting import format_timestamp, json_tool_result, truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_alarm_summary(
    org_id: Optional[str] = None,
    severity: Literal["critical", "warn", "info", "all"] = "all",
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get active alarms grouped into stories instead of a raw repeating feed.

    The raw alarm feed repeats the same issue many times (e.g. one DHCP
    failure alarm per interval per AP). This tool groups alarms by type,
    site, and severity, with counts, first/last seen times, and affected
    devices, so triage is one call. Use get_alarms for full per-alarm detail.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
        severity: Filter by severity level
        duration: Hours of history to summarize (default 24)
        format: Response format

    Returns:
        Alarm groups sorted by severity then occurrence count

    Example:
        User: "Summarize the current alarms"
        -> Use this tool with default parameters

        User: "What critical issues are ongoing?"
        -> Use this tool with severity="critical"
    """
    try:
        org_id = resolve_org_id(org_id)
        end_time = int(time.time())
        params = {
            "limit": 1000,
            "start": end_time - (duration * 3600),
            "end": end_time,
        }
        if severity != "all":
            params["severity"] = severity

        response = await mist_api_request(f"/orgs/{org_id}/alarms/search", params=params)
        alarms = response.get("results", []) if isinstance(response, dict) else response

        try:
            site_names = {s["id"]: s.get("name", s["id"]) for s in await get_org_sites(org_id)}
        except Exception:
            site_names = {}

        # Group by (type, site, severity)
        groups: dict[tuple, dict] = {}
        for alarm in alarms:
            key = (alarm.get("type", "unknown"),
                   alarm.get("site_id", "unknown"),
                   alarm.get("severity", "info"))
            g = groups.setdefault(key, {
                "type": key[0],
                "site_id": key[1],
                "site_name": site_names.get(key[1], key[1]),
                "severity": key[2],
                "count": 0,
                "first_seen": None,
                "last_seen": None,
                "hostnames": set(),
                "reasons": set(),
            })
            g["count"] += alarm.get("count", 1)
            ts = alarm.get("timestamp") or alarm.get("last_seen")
            if ts:
                g["first_seen"] = ts if g["first_seen"] is None else min(g["first_seen"], ts)
                g["last_seen"] = ts if g["last_seen"] is None else max(g["last_seen"], ts)
            for h in alarm.get("hostnames", []) or []:
                g["hostnames"].add(h)
            if alarm.get("reasons"):
                g["reasons"].update(str(r) for r in alarm["reasons"])
            elif alarm.get("reason"):
                g["reasons"].add(str(alarm["reason"]))

        sev_rank = {"critical": 0, "warn": 1, "info": 2}
        ordered = sorted(
            groups.values(),
            key=lambda g: (sev_rank.get(g["severity"], 3), -g["count"]),
        )
        for g in ordered:  # sets aren't JSON serializable
            g["hostnames"] = sorted(g["hostnames"])
            g["reasons"] = sorted(g["reasons"])

        if format == "json":
            return json_tool_result({
                "total_alarms": len(alarms),
                "groups": ordered,
            })

        if not ordered:
            return f"# Alarm Summary\n\nNo alarms in the last {duration} hour(s)."

        result = "# Alarm Summary\n\n"
        result += (f"{len(alarms)} alarm(s) in the last {duration} hour(s), "
                   f"grouped into {len(ordered)} distinct issue(s)\n\n")

        current_sev = None
        for g in ordered:
            if g["severity"] != current_sev:
                current_sev = g["severity"]
                result += f"## {current_sev.upper()}\n\n"
            result += f"### {g['type']} @ {g['site_name']} ({g['count']}x)\n\n"
            if g["first_seen"]:
                result += f"- **First seen:** {format_timestamp(g['first_seen'])}\n"
            if g["last_seen"]:
                result += f"- **Last seen:** {format_timestamp(g['last_seen'])}\n"
            if g["hostnames"]:
                shown = ", ".join(g["hostnames"][:8])
                more = f" (+{len(g['hostnames']) - 8} more)" if len(g["hostnames"]) > 8 else ""
                result += f"- **Devices:** {shown}{more}\n"
            if g["reasons"]:
                result += f"- **Reasons:** {', '.join(g['reasons'][:5])}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error summarizing alarms: {str(e)}"


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_alarms(
    org_id: Optional[str] = None,
    severity: Literal["critical", "warn", "info", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get active alarms and alerts for an organization.

    Retrieves current network alarms including device offline, high utilization,
    configuration issues, and security alerts.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        params = {"limit": limit}
        if severity != "all":
            params["severity"] = severity

        response = await mist_api_request(f"/orgs/{org_id}/alarms/search", params=params)

        if format == "json":
            return json_tool_result(response)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_marvis_actions(
    org_id: Optional[str] = None,
    category: Literal["all", "wired", "wireless", "wan", "switch", "ap", "gateway"] = "all",
    status: Literal["all", "open", "resolved"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get Marvis AI-generated action alerts and recommendations.

    Marvis is Juniper Mist's AI engine that proactively identifies network issues
    and provides actionable recommendations. This retrieves current Marvis actions
    including connectivity issues, loop detection, coverage problems, and more.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
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
            return json_tool_result(actions)

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
                    ts = format_timestamp(action['timestamp'])
                    result += f"- **Detected:** {ts}\n"
                elif 'last_seen' in action:
                    ts = format_timestamp(action['last_seen'])
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_site_wan_stats(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get WAN (internet) connection statistics for a site.

    Retrieves WAN link status, bandwidth usage, latency, and ISP information
    for sites with Mist Edge or gateway devices.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        stats = await mist_api_request(f"/sites/{site_id}/stats/devices", params={"type": "gateway"})

        if format == "json":
            return json_tool_result(stats)

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
