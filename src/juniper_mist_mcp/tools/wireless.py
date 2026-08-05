"""Wireless & RF tools for the Juniper Mist MCP server."""

import time
from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import mist_api_request, resolve_org_id, resolve_site_id
from ..formatting import format_timestamp, json_tool_result, truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_wlans(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    List all WLANs (wireless networks) configured at a site.

    Retrieves all wireless network configurations including SSIDs, security settings,
    VLANs, and enabled features.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC") (get from list_sites)
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
        site_id = await resolve_site_id(site_id)
        wlans = await mist_api_request(f"/sites/{site_id}/wlans")

        if format == "json":
            return json_tool_result(wlans)

        if not wlans:
            return "# WLANs\n\nNo WLANs configured at this site."

        result = "# WLANs (Wireless Networks)\n\n"
        result += f"Found {len(wlans)} WLAN(s)\n\n"

        for wlan in wlans:
            ssid = wlan.get('ssid', 'Unnamed WLAN')
            result += f"## {ssid}\n\n"
            result += f"- **WLAN ID:** `{wlan.get('id', 'N/A')}`\n"
            result += f"- **Enabled:** {'Yes' if wlan.get('enabled', False) else 'No'}\n"

            # Security
            auth_type = wlan.get('auth', {}).get('type', 'open')
            result += f"- **Security:** {auth_type}\n"

            if wlan.get('auth', {}).get('psk'):
                result += "- **PSK Configured:** Yes\n"

            # VLAN
            if 'vlan_id' in wlan:
                result += f"- **VLAN ID:** {wlan['vlan_id']}\n"
            if wlan.get('vlan_enabled'):
                result += "- **VLAN Enabled:** Yes\n"

            # Band
            if 'band' in wlan:
                result += f"- **Band:** {wlan['band']}\n"

            # Visibility
            result += f"- **Hidden SSID:** {'Yes' if wlan.get('hide_ssid', False) else 'No'}\n"

            # Guest settings
            if wlan.get('portal_enabled'):
                result += "- **Captive Portal:** Enabled\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing WLANs: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_org_wlans(
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    List all WLAN templates configured at the organization level.

    Retrieves organization-level WLAN configurations that can be applied to sites.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
        format: Response format

    Returns:
        List of org-level WLANs with configuration details

    Example:
        User: "What WLAN templates exist in the organization?"
        -> Use this tool with the org_id
    """
    try:
        org_id = resolve_org_id(org_id)
        wlans = await mist_api_request(f"/orgs/{org_id}/wlans")

        if format == "json":
            return json_tool_result(wlans)

        if not wlans:
            return "# Organization WLANs\n\nNo organization-level WLANs configured."

        result = "# Organization WLAN Templates\n\n"
        result += f"Found {len(wlans)} WLAN template(s)\n\n"

        for wlan in wlans:
            ssid = wlan.get('ssid', 'Unnamed WLAN')
            result += f"## {ssid}\n\n"
            result += f"- **WLAN ID:** `{wlan.get('id', 'N/A')}`\n"

            auth_type = wlan.get('auth', {}).get('type', 'open')
            result += f"- **Security:** {auth_type}\n"

            if 'vlan_id' in wlan:
                result += f"- **VLAN ID:** {wlan['vlan_id']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing org WLANs: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_rf_stats(
    site_id: str,
    band: Literal["24", "5", "6", "all"] = "all",
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get RF (radio frequency) environment statistics for a site.

    Retrieves wireless environment metrics including channel utilization,
    interference levels, noise floor, and client distribution by band.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        # Get AP stats which include RF metrics
        params = {"type": "ap"}
        stats = await mist_api_request(f"/sites/{site_id}/stats/devices", params=params)

        if format == "json":
            return json_tool_result(stats)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_ap_radio_status(
    site_id: str,
    ap_mac: Optional[str] = None,
    band: Literal["24", "5", "6", "all"] = "all",
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get current radio status and channel assignments for APs.

    Retrieves real-time radio information including current channel,
    power level, bandwidth, and client count per radio.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
        ap_mac: Optional AP MAC to filter for specific AP
        band: Filter by frequency band
        format: Response format

    Returns:
        Radio status including channels, power, and client distribution

    Example:
        User: "What channels are the APs using?"
        -> Use this tool with the site_id

        User: "Show me the 5GHz radio status"
        -> Use this tool with band="5"
    """
    try:
        site_id = await resolve_site_id(site_id)
        # Get device stats which includes radio info
        params = {"type": "ap"}
        if ap_mac:
            params["mac"] = ap_mac

        stats = await mist_api_request(
            f"/sites/{site_id}/stats/devices",
            params=params
        )

        if format == "json":
            return json_tool_result(stats)

        result = "# AP Radio Status\n\n"

        if not stats:
            return result + "No AP stats available.\n"

        result += f"Found {len(stats)} AP(s)\n\n"

        for ap in stats:
            name = ap.get('name', ap.get('mac', 'Unknown'))
            result += f"## {name}\n\n"
            result += f"- **MAC:** `{ap.get('mac', 'N/A')}`\n"
            result += f"- **Status:** {ap.get('status', 'N/A')}\n"

            # Radio info
            if ap.get('radio_stat'):
                radios = ap['radio_stat']

                # 2.4 GHz
                if (band in ["24", "all"]) and radios.get('band_24'):
                    r24 = radios['band_24']
                    result += "\n**2.4 GHz Radio:**\n"
                    result += f"  - Channel: {r24.get('channel', 'N/A')}\n"
                    result += f"  - Power: {r24.get('power', 'N/A')} dBm\n"
                    result += f"  - Bandwidth: {r24.get('bandwidth', 'N/A')} MHz\n"
                    result += f"  - Clients: {r24.get('num_clients', 0)}\n"
                    if r24.get('util_all') is not None:
                        result += f"  - Utilization: {r24['util_all']}%\n"

                # 5 GHz
                if (band in ["5", "all"]) and radios.get('band_5'):
                    r5 = radios['band_5']
                    result += "\n**5 GHz Radio:**\n"
                    result += f"  - Channel: {r5.get('channel', 'N/A')}\n"
                    result += f"  - Power: {r5.get('power', 'N/A')} dBm\n"
                    result += f"  - Bandwidth: {r5.get('bandwidth', 'N/A')} MHz\n"
                    result += f"  - Clients: {r5.get('num_clients', 0)}\n"
                    if r5.get('util_all') is not None:
                        result += f"  - Utilization: {r5['util_all']}%\n"

                # 6 GHz
                if (band in ["6", "all"]) and radios.get('band_6'):
                    r6 = radios['band_6']
                    result += "\n**6 GHz Radio:**\n"
                    result += f"  - Channel: {r6.get('channel', 'N/A')}\n"
                    result += f"  - Power: {r6.get('power', 'N/A')} dBm\n"
                    result += f"  - Bandwidth: {r6.get('bandwidth', 'N/A')} MHz\n"
                    result += f"  - Clients: {r6.get('num_clients', 0)}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting AP radio status: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_rogue_aps(
    site_id: str,
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get detected rogue access points at a site.

    Retrieves a list of unauthorized or unknown access points detected by
    the wireless network, which may indicate security threats.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        params = {"limit": limit}
        rogues = await mist_api_request(f"/sites/{site_id}/insights/rogues", params=params)

        if format == "json":
            return json_tool_result(rogues)

        results_list = rogues.get('results', rogues) if isinstance(rogues, dict) else rogues

        if not results_list:
            return "# Rogue AP Detection\n\nNo rogue access points detected."

        result = "# Rogue AP Detection\n\n"
        result += f"**Warning:** Found {len(results_list)} potential rogue AP(s)\n\n"

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
                ts = format_timestamp(rogue['last_seen'])
                result += f"- **Last Seen:** {ts}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting rogue APs: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_site_insights(
    site_id: str,
    metric: str = "bytes",
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get site-level network insights and analytics.

    Retrieves aggregated metrics and analytics for a site over a time period.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
        metric: Metric type - "bytes", "num_clients", "num_aps"
        duration: Hours of data to analyze (default 24)
        format: Response format

    Returns:
        Site insights with metrics and trends

    Example:
        User: "How much traffic has the site had today?"
        -> Use this tool with metric="bytes"

        User: "How many clients connected over the past week?"
        -> Use this tool with metric="num_clients", duration=168
    """
    try:
        site_id = await resolve_site_id(site_id)
        # Calculate time range
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        insights = await mist_api_request(
            f"/sites/{site_id}/insights/{metric}",
            params={"start": start_time, "end": end_time}
        )

        if format == "json":
            return json_tool_result(insights)

        result = f"# Site Insights: {metric}\n\n"
        result += f"**Time Range:** Last {duration} hours\n\n"

        if isinstance(insights, dict):
            results = insights.get('results', [])
            timestamps = insights.get('rt', [])

            if results:
                result += f"Found {len(results)} data point(s)\n\n"

                # Results can be floats directly or dicts
                if results and isinstance(results[0], (int, float)):
                    values = [v for v in results if v is not None and v > 0]
                else:
                    values = [r.get('value', 0) for r in results if isinstance(r, dict) and r.get('value')]

                if values:
                    total = sum(values)
                    # Format bytes nicely
                    if metric == "bytes":
                        if total > 1e12:
                            result += f"- **Total:** {total/1e12:.2f} TB\n"
                        elif total > 1e9:
                            result += f"- **Total:** {total/1e9:.2f} GB\n"
                        else:
                            result += f"- **Total:** {total/1e6:.2f} MB\n"
                    else:
                        result += f"- **Total:** {total:,.0f}\n"

                    result += f"- **Average:** {sum(values)/len(values):,.0f}\n"
                    result += f"- **Peak:** {max(values):,.0f}\n"
                    result += f"- **Data Points:** {len(values)}\n"

                    # Show time range if available
                    if timestamps and len(timestamps) >= 2:
                        result += f"\n**Period:** {timestamps[0]} to {timestamps[-1]}\n"
            else:
                result += "No data available for this metric.\n"
        elif isinstance(insights, list):
            if insights:
                result += f"Found {len(insights)} data point(s)\n"
            else:
                result += "No data available.\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting site insights: {str(e)}"
