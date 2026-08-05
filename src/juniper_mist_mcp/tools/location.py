"""Maps, assets & location tools for the Juniper Mist MCP server."""

import time
from datetime import datetime
from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import mist_api_request
from ..formatting import (
    format_timestamp,
    json_tool_result,
    local_timezone_name,
    truncate_response,
)
from ..server import READ_ONLY, mcp


async def _get_map_aps(site_id: str, map_id: str, map_info: Optional[dict] = None) -> list[dict]:
    """
    Get the AP devices placed on a map.

    The Mist map object does not embed AP placements; each placed AP's
    device object carries the map_id (plus x/y/height). Fetch the site's
    AP devices and filter by map.
    """
    devices = await mist_api_request(
        f"/sites/{site_id}/devices", params={"type": "ap", "limit": 1000}
    )
    placed = [d for d in devices if d.get('map_id') == map_id]
    # Fallback in case an API variant does embed aps in the map object
    if not placed and map_info and map_info.get('aps'):
        placed = map_info['aps']
    return placed

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_site_maps(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    List all floor plans/maps configured for a site.

    Retrieves all maps including floor plans, outdoor areas, and building layouts
    with their dimensions, AP placements, and zone configurations.

    Args:
        site_id: Site UUID (get from list_sites)
        format: Response format - "markdown" for readability, "json" for structured data

    Returns:
        List of maps with names, dimensions, and AP counts

    Example:
        User: "What floor plans are available at this site?"
        -> Use this tool with the site_id

        User: "Show me the maps"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no maps configured
        - Maps are required for location services
    """
    try:
        maps = await mist_api_request(f"/sites/{site_id}/maps")

        if format == "json":
            return json_tool_result(maps)

        if not maps:
            return "# Site Maps\n\nNo maps/floor plans configured for this site."

        result = "# Site Maps & Floor Plans\n\n"
        result += f"Found {len(maps)} map(s)\n\n"

        for map_info in maps:
            name = map_info.get('name', 'Unnamed Map')
            result += f"## {name}\n\n"

            result += f"- **Map ID:** `{map_info.get('id', 'N/A')}`\n"

            # Map type
            if map_info.get('type'):
                result += f"- **Type:** {map_info['type']}\n"

            # Dimensions
            width = map_info.get('width', 0)
            height = map_info.get('height', 0)
            if width and height:
                result += f"- **Dimensions:** {width}m x {height}m\n"

            # Scale/PPM (pixels per meter)
            if map_info.get('ppm'):
                result += f"- **Scale (PPM):** {map_info['ppm']} pixels/meter\n"

            # Orientation
            if map_info.get('orientation'):
                result += f"- **Orientation:** {map_info['orientation']}°\n"

            # Image info
            if map_info.get('url'):
                result += "- **Has Image:** Yes\n"

            # Location
            if map_info.get('latlng'):
                latlng = map_info['latlng']
                result += f"- **Coordinates:** {latlng.get('lat')}, {latlng.get('lng')}\n"

            # Locked status
            if map_info.get('locked'):
                result += "- **Locked:** Yes (no edits allowed)\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing site maps: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_map_info(
    site_id: str,
    map_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get detailed information about a specific map/floor plan.

    Retrieves comprehensive map details including AP placements, walls,
    zones, beacons, and other overlay objects.

    Args:
        site_id: Site UUID
        map_id: Map UUID (get from list_site_maps)
        format: Response format

    Returns:
        Detailed map configuration including AP positions and zones

    Example:
        User: "Show me details of the first floor map"
        -> Use this tool with site_id and map_id

        User: "What APs are on this floor plan?"
        -> Use this tool to see AP placements

    Error Handling:
        - Returns error if map not found
        - Use list_site_maps to get valid map IDs
    """
    try:
        map_info = await mist_api_request(f"/sites/{site_id}/maps/{map_id}")

        # AP positions (placements live on the device objects, not the map)
        aps = await _get_map_aps(site_id, map_id, map_info)

        if format == "json":
            return json_tool_result({**map_info, "aps": aps})

        name = map_info.get('name', 'Unnamed Map')
        result = f"# Map: {name}\n\n"

        result += f"- **Map ID:** `{map_info.get('id', 'N/A')}`\n"
        result += f"- **Site ID:** `{site_id}`\n"

        # Dimensions and scale
        width = map_info.get('width', 0)
        height = map_info.get('height', 0)
        if width and height:
            result += f"- **Dimensions:** {width}m x {height}m ({width * height:.0f} m²)\n"

        if map_info.get('ppm'):
            result += f"- **Scale:** {map_info['ppm']} pixels/meter\n"

        if map_info.get('orientation'):
            result += f"- **Orientation:** {map_info['orientation']}°\n"

        # Location
        if map_info.get('latlng'):
            latlng = map_info['latlng']
            result += f"- **Geo Location:** {latlng.get('lat')}, {latlng.get('lng')}\n"

        if aps:
            result += f"\n## Access Points ({len(aps)})\n\n"
            result += "| Name | MAC | X (m) | Y (m) | Height |\n"
            result += "|------|-----|-------|-------|--------|\n"

            for ap in aps[:30]:
                ap_name = ap.get('name', 'Unknown')
                ap_mac = ap.get('mac', 'N/A')
                x = ap.get('x') or 0
                y = ap.get('y') or 0
                height_val = ap.get('height', 'N/A')
                result += f"| {ap_name} | `{ap_mac}` | {x:.1f} | {y:.1f} | {height_val}m |\n"

            if len(aps) > 30:
                result += f"\n*... and {len(aps) - 30} more APs*\n"

        # Zones
        if map_info.get('zones'):
            zones = map_info['zones']
            result += f"\n## Zones ({len(zones)})\n\n"
            for zone in zones:
                result += f"- **{zone.get('name', 'Unnamed Zone')}** (ID: `{zone.get('id', 'N/A')}`)\n"

        # Walls (for RF planning)
        if map_info.get('walls'):
            walls = map_info['walls']
            result += "\n## Walls\n\n"
            result += f"- **Wall Segments:** {len(walls)}\n"

        # Beacons
        if map_info.get('beacons'):
            beacons = map_info['beacons']
            result += f"\n## Virtual Beacons ({len(beacons)})\n\n"
            for beacon in beacons[:10]:
                result += f"- **{beacon.get('name', 'Unnamed')}** at ({beacon.get('x', 0):.1f}, {beacon.get('y', 0):.1f})\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting map info: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_zones(
    site_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    List all location zones configured at a site.

    Zones are areas defined on floor plans used for location analytics,
    occupancy tracking, and triggering location-based events.

    Args:
        site_id: Site UUID
        format: Response format

    Returns:
        List of zones with names, types, and associated maps

    Example:
        User: "What zones are defined at this site?"
        -> Use this tool with the site_id

        User: "Show me the location zones"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no zones configured
        - Zones require maps to be configured first
    """
    try:
        zones = await mist_api_request(f"/sites/{site_id}/zones")

        if format == "json":
            return json_tool_result(zones)

        if not zones:
            return "# Location Zones\n\nNo zones configured for this site."

        result = "# Location Zones\n\n"
        result += f"Found {len(zones)} zone(s)\n\n"

        for zone in zones:
            name = zone.get('name', 'Unnamed Zone')
            result += f"## {name}\n\n"

            result += f"- **Zone ID:** `{zone.get('id', 'N/A')}`\n"

            if zone.get('map_id'):
                result += f"- **Map ID:** `{zone['map_id']}`\n"

            if zone.get('type'):
                result += f"- **Type:** {zone['type']}\n"

            # Zone vertices (polygon shape)
            if zone.get('vertices'):
                vertices = zone['vertices']
                result += f"- **Vertices:** {len(vertices)} points\n"

            # Zone settings
            if zone.get('occupancy_limit'):
                result += f"- **Occupancy Limit:** {zone['occupancy_limit']}\n"

            if zone.get('asset_filter'):
                result += "- **Asset Filter:** Configured\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing zones: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def list_assets(
    site_id: str,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    List BLE assets configured at a site.

    Retrieves all BLE asset tags and tracked devices configured at the site,
    including their current status, location, and battery level.

    Args:
        site_id: Site UUID
        limit: Maximum assets to return (default 100)
        format: Response format

    Returns:
        List of assets with name, MAC, status, and location info

    Example:
        User: "What assets are being tracked at this site?"
        -> Use this tool with the site_id

        User: "Show me all BLE tags"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no assets configured
        - Requires asset tracking license
    """
    try:
        assets = await mist_api_request(
            f"/sites/{site_id}/assets",
            params={"limit": limit}
        )

        if format == "json":
            return json_tool_result(assets)

        # Format as markdown
        result = "# BLE Assets\n\n"

        if not assets:
            return result + "No assets found at this site.\n"

        result += f"Found {len(assets)} asset(s)\n\n"

        for asset in assets:
            name = asset.get('name', 'Unnamed Asset')
            result += f"## {name}\n\n"

            result += f"- **Asset ID:** `{asset.get('id', 'N/A')}`\n"
            result += f"- **MAC Address:** `{asset.get('mac', 'N/A')}`\n"

            if asset.get('device_type'):
                result += f"- **Device Type:** {asset['device_type']}\n"

            if asset.get('map_id'):
                result += f"- **Map ID:** `{asset['map_id']}`\n"

            # Location if available
            if asset.get('x') is not None and asset.get('y') is not None:
                result += f"- **Position:** ({asset['x']:.1f}, {asset['y']:.1f})\n"

            # Battery level
            if asset.get('battery_voltage'):
                result += f"- **Battery:** {asset['battery_voltage']}V\n"

            # Tags/labels
            if asset.get('labels'):
                result += f"- **Labels:** {', '.join(asset['labels'])}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error listing assets: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_asset_stats(
    site_id: str,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get real-time statistics for BLE assets at a site.

    Retrieves current location, last seen time, and signal metrics
    for tracked BLE assets.

    Args:
        site_id: Site UUID
        limit: Maximum assets to return (default 100)
        format: Response format

    Returns:
        Asset statistics including location, RSSI, and last seen time

    Example:
        User: "Where are the tracked assets right now?"
        -> Use this tool with the site_id

        User: "Show me asset locations"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no assets or none currently visible
        - Requires asset tracking to be enabled
    """
    try:
        stats = await mist_api_request(
            f"/sites/{site_id}/stats/assets",
            params={"limit": limit}
        )

        if format == "json":
            return json_tool_result(stats)

        # Format as markdown
        result = "# Asset Statistics\n\n"

        if not stats:
            return result + "No asset statistics available.\n"

        result += f"Found {len(stats)} asset(s) with stats\n\n"

        for stat in stats:
            name = stat.get('name', stat.get('mac', 'Unknown'))
            result += f"## {name}\n\n"

            result += f"- **MAC:** `{stat.get('mac', 'N/A')}`\n"

            # Map and location
            if stat.get('map_id'):
                result += f"- **Map ID:** `{stat['map_id']}`\n"

            if stat.get('x') is not None and stat.get('y') is not None:
                result += f"- **Current Position:** ({stat['x']:.1f}, {stat['y']:.1f})\n"

            # Signal info
            if stat.get('rssi') is not None:
                result += f"- **RSSI:** {stat['rssi']} dBm\n"

            # Last seen
            if stat.get('last_seen'):
                result += f"- **Last Seen:** {format_timestamp(stat['last_seen'])}\n"

            # Battery
            if stat.get('battery_voltage'):
                result += f"- **Battery:** {stat['battery_voltage']}V\n"

            # Zone if available
            if stat.get('zone_id'):
                result += f"- **Zone ID:** `{stat['zone_id']}`\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting asset stats: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_assets(
    site_id: str,
    search_term: str,
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Search for BLE assets by name or MAC address.

    Searches across all assets at a site to find matches.

    Args:
        site_id: Site UUID
        search_term: Search string (name or MAC address)
        limit: Maximum results to return
        format: Response format

    Returns:
        Matching assets with their details

    Example:
        User: "Find asset named 'forklift'"
        -> Use this tool with search_term="forklift"

        User: "Search for asset with MAC aa:bb:cc"
        -> Use this tool with search_term="aa:bb:cc"

    Error Handling:
        - Returns empty if no matches found
        - Search is case-insensitive
    """
    try:
        # Get all assets and filter locally
        assets = await mist_api_request(
            f"/sites/{site_id}/assets",
            params={"limit": limit * 2}  # Get more to filter
        )

        # Filter by search term
        search_lower = search_term.lower()
        matched = []
        for asset in assets:
            name = asset.get('name', '').lower()
            mac = asset.get('mac', '').lower()
            if search_lower in name or search_lower in mac:
                matched.append(asset)
                if len(matched) >= limit:
                    break

        if format == "json":
            return json_tool_result(matched)

        # Format as markdown
        result = f"# Asset Search Results for '{search_term}'\n\n"

        if not matched:
            return result + "No matching assets found.\n"

        result += f"Found {len(matched)} matching asset(s)\n\n"

        for asset in matched:
            name = asset.get('name', 'Unnamed Asset')
            result += f"## {name}\n\n"

            result += f"- **Asset ID:** `{asset.get('id', 'N/A')}`\n"
            result += f"- **MAC Address:** `{asset.get('mac', 'N/A')}`\n"

            if asset.get('device_type'):
                result += f"- **Device Type:** {asset['device_type']}\n"

            if asset.get('labels'):
                result += f"- **Labels:** {', '.join(asset['labels'])}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching assets: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_discovered_assets(
    site_id: str,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get discovered but unassigned BLE devices at a site.

    Retrieves BLE devices that have been detected by the network but
    haven't been configured as tracked assets yet.

    Args:
        site_id: Site UUID
        limit: Maximum discoveries to return (default 100)
        format: Response format

    Returns:
        List of discovered BLE devices with MAC, RSSI, and detection info

    Example:
        User: "What new BLE devices have been discovered?"
        -> Use this tool with the site_id

        User: "Show unassigned BLE tags"
        -> Use this tool with the site_id

    Error Handling:
        - Returns empty if no new devices discovered
        - Requires BLE scanning to be enabled on APs
    """
    try:
        discovered = await mist_api_request(
            f"/sites/{site_id}/stats/discovered_assets",
            params={"limit": limit}
        )

        if format == "json":
            return json_tool_result(discovered)

        # Format as markdown
        result = "# Discovered BLE Devices\n\n"

        if not discovered:
            return result + "No unassigned BLE devices discovered.\n"

        result += f"Found {len(discovered)} discovered device(s)\n\n"

        for device in discovered:
            mac = device.get('mac', 'Unknown')
            result += f"## {mac}\n\n"

            # Device type/manufacturer
            if device.get('device_type'):
                result += f"- **Device Type:** {device['device_type']}\n"

            if device.get('manufacture'):
                result += f"- **Manufacturer:** {device['manufacture']}\n"

            # Signal and detection
            if device.get('rssi') is not None:
                result += f"- **RSSI:** {device['rssi']} dBm\n"

            if device.get('ap_mac'):
                result += f"- **Detected by AP:** `{device['ap_mac']}`\n"

            # Last seen
            if device.get('last_seen'):
                result += f"- **Last Seen:** {format_timestamp(device['last_seen'])}\n"

            # iBeacon info if present
            if device.get('ibeacon_uuid'):
                result += f"- **iBeacon UUID:** `{device['ibeacon_uuid']}`\n"
                if device.get('ibeacon_major'):
                    result += f"- **iBeacon Major:** {device['ibeacon_major']}\n"
                if device.get('ibeacon_minor'):
                    result += f"- **iBeacon Minor:** {device['ibeacon_minor']}\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting discovered assets: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_client_location_history(
    site_id: str,
    client_mac: str,
    duration: int = 24,
    start: Optional[str] = None,
    end: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Track a client device's location history over a time period.

    Returns a concise timeline showing where the device was based on which
    AP it connected to. Uses session data + AP names from device inventory.

    Args:
        site_id: Site UUID (get from list_sites)
        client_mac: Client MAC address (format: aa:bb:cc:dd:ee:ff)
        duration: Hours of history (default 24, max 168) - used if start/end not provided
        start: Start time as "YYYY-MM-DD HH:MM" (optional, local timezone of the machine running this server)
        end: End time as "YYYY-MM-DD HH:MM" (optional, local timezone of the machine running this server)
        format: "markdown" for concise output, "json" for structured data

    Returns:
        Timeline of locations with time, AP name, and duration

    Example:
        User: "Where has device aa:bb:cc:dd:ee:ff been today?"
        -> Use with client_mac="aa:bb:cc:dd:ee:ff", duration=24

        User: "Track location yesterday 8am-4pm"
        -> Use with start="2026-02-02 08:00", end="2026-02-02 16:00"
    """

    try:
        # Handle start/end time parameters
        if start and end:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
                start_time = int(start_dt.timestamp())
                end_time = int(end_dt.timestamp())
            except ValueError:
                return "Error: Use format 'YYYY-MM-DD HH:MM' for start/end times"
        else:
            duration = min(duration, 168)
            end_time = int(time.time())
            start_time = end_time - (duration * 3600)
        mac = client_mac.lower().replace("-", ":")

        # Get sessions
        sessions = await mist_api_request(
            f"/sites/{site_id}/clients/sessions/search",
            params={"mac": mac, "start": start_time, "end": end_time, "limit": 500}
        )
        results = sessions.get('results', sessions) if isinstance(sessions, dict) else sessions

        if not results:
            return f"No sessions found for `{client_mac}` in the specified time range."

        # Get AP names from device stats (one API call)
        ap_stats = await mist_api_request(f"/sites/{site_id}/stats/devices", params={"type": "ap", "limit": 1000})
        ap_names = {d.get('mac', '').lower(): d.get('name', d.get('mac', '?')) for d in ap_stats}

        # Build movement timeline - track when client moved between APs
        # Sort all sessions by connect time (API uses 'connect' not 'connect_time')
        sessions_sorted = sorted(results, key=lambda s: s.get('connect') or s.get('connect_time') or s.get('timestamp') or 0)

        # Build movement list: each entry is when client connected to a NEW AP
        movements = []
        last_ap = None
        for s in sessions_sorted:
            # API uses 'ap' not 'ap_mac'
            ap_mac = (s.get('ap') or s.get('ap_mac', '')).lower().replace('-', ':')
            # API uses 'connect' not 'connect_time'
            t = s.get('connect') or s.get('connect_time') or s.get('timestamp')
            if not t:
                continue

            ap_name = ap_names.get(ap_mac, ap_mac)

            # Only record if this is a different AP than the last one (actual movement)
            if ap_name != last_ap:
                movements.append({
                    'start': t,
                    'ap': ap_name
                })
                last_ap = ap_name

        # Calculate end times: end time is when they moved to the next AP
        timeline = []
        for i, m in enumerate(movements):
            if i + 1 < len(movements):
                end_t = movements[i + 1]['start']
            else:
                # Last movement - use the last session's disconnect time or duration
                last_session = sessions_sorted[-1] if sessions_sorted else None
                if last_session:
                    # API uses 'disconnect' not 'disconnect_time'
                    end_t = last_session.get('disconnect') or last_session.get('disconnect_time') or (m['start'] + last_session.get('duration', 0))
                else:
                    end_t = m['start']

            timeline.append({
                'start': m['start'],
                'end': end_t,
                'ap': m['ap'],
                'still_connected': False
            })

        # Check if client is currently connected to the last AP
        if timeline:
            try:
                # Get org_id from site, then use org-level client search
                site_info = await mist_api_request(f"/sites/{site_id}")
                org_id = site_info.get('org_id')
                if org_id:
                    current = await mist_api_request(f"/orgs/{org_id}/clients/search", params={"mac": mac, "limit": 1})
                    results_list = current.get('results', []) if isinstance(current, dict) else current
                    if results_list and len(results_list) > 0:
                        last_ap_mac = results_list[0].get('last_ap', '').lower().replace('-', ':')
                        last_ap_name = ap_names.get(last_ap_mac, last_ap_mac)
                        # If still on the same AP as last timeline entry, mark as still connected
                        if last_ap_name == timeline[-1]['ap']:
                            timeline[-1]['still_connected'] = True
                            timeline[-1]['end'] = time.time()
            except Exception:
                pass  # If check fails, just use session data

        if format == "json":
            return json_tool_result({'mac': mac, 'timeline': timeline})

        # Concise markdown table
        lines = [f"# Location: `{mac}`\n"]
        lines.append(f"Times are {local_timezone_name()} (server local).\n")
        lines.append("| Time | AP Name |")
        lines.append("|------|---------|")

        for e in timeline[:100]:
            start_str = datetime.fromtimestamp(e['start']).strftime('%m-%d %H:%M')
            if e.get('still_connected'):
                end_str = "now"
                duration_sec = time.time() - e['start']
            else:
                end_str = datetime.fromtimestamp(e['end']).strftime('%H:%M')
                duration_sec = e['end'] - e['start']
            if duration_sec < 60:
                dur_str = f"{duration_sec:.0f}s"
            elif duration_sec < 3600:
                dur_str = f"{duration_sec/60:.0f}m"
            else:
                dur_str = f"{duration_sec/3600:.1f}h"
            lines.append(f"| {start_str} - {end_str} ({dur_str}) | {e['ap']} |")

        if len(timeline) > 100:
            lines.append(f"\n*+{len(timeline)-100} more*")

        return '\n'.join(lines)

    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_clients_by_location(
    site_id: str,
    map_id: str,
    duration: int = 1,
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Find all clients that have been on a specific floor plan.

    Args:
        site_id: Site UUID
        map_id: Map/floor UUID (get from list_site_maps)
        duration: Hours to search back (default 1)
        limit: Max clients to return (default 50)
        format: Response format

    Returns:
        List of clients seen on this floor with last seen time

    Example:
        User: "Who has been on the 3rd floor?"
        -> Use with map_id for 3rd floor
    """

    try:
        # Get map and its APs (placements live on the device objects, not the map)
        map_info = await mist_api_request(f"/sites/{site_id}/maps/{map_id}")
        map_name = map_info.get('name', 'Map')
        placed = await _get_map_aps(site_id, map_id, map_info)
        aps = {ap.get('mac', '').lower(): ap.get('name', 'AP') for ap in placed if ap.get('mac')}

        if not aps:
            return f"No APs on {map_name}."

        # Get sessions
        end_time = int(time.time())
        sessions = await mist_api_request(
            f"/sites/{site_id}/clients/sessions/search",
            params={"start": end_time - (duration * 3600), "end": end_time, "limit": 1000}
        )
        results = sessions.get('results', sessions) if isinstance(sessions, dict) else sessions

        # Filter to clients on this map's APs
        clients = {}
        for s in results:
            # API uses 'ap' and 'connect' (not 'ap_mac'/'connect_time')
            ap_mac = (s.get('ap') or s.get('ap_mac') or '').lower().replace('-', ':')
            if ap_mac in aps:
                mac = s.get('mac', '').lower()
                t = s.get('connect') or s.get('connect_time') or s.get('timestamp') or 0
                if mac and (mac not in clients or t > clients[mac]['t']):
                    clients[mac] = {
                        't': t,
                        'host': s.get('hostname', '?'),
                        'ap': aps.get(ap_mac, 'AP')
                    }

        if not clients:
            return f"No clients on {map_name} in last {duration}h."

        # Sessions often omit hostnames; enrich from current client stats (one call)
        if any(not c['host'] or c['host'] == '?' for c in clients.values()):
            try:
                live = await mist_api_request(
                    f"/sites/{site_id}/stats/clients", params={"limit": 1000}
                )
                names = {
                    lc.get('mac', '').lower(): lc['hostname']
                    for lc in live if lc.get('hostname')
                }
                for mac, c in clients.items():
                    if (not c['host'] or c['host'] == '?') and mac in names:
                        c['host'] = names[mac]
            except Exception:
                pass  # enrichment is best-effort

        if format == "json":
            return json_tool_result({'map': map_name, 'clients': clients})

        lines = [f"# Clients on {map_name} ({duration}h)\n"]
        lines.append(f"Times are {local_timezone_name()} (server local).\n")
        lines.append("| MAC | Hostname | Last AP | Last Seen |")
        lines.append("|-----|----------|---------|-----------|")

        for mac, c in sorted(clients.items(), key=lambda x: x[1]['t'] or 0, reverse=True)[:limit]:
            t = datetime.fromtimestamp(c['t']).strftime('%m-%d %H:%M') if c['t'] else '?'
            lines.append(f"| `{mac}` | {c['host']} | {c['ap']} | {t} |")

        if len(clients) > limit:
            lines.append(f"\n*+{len(clients)-limit} more*")

        return '\n'.join(lines)

    except Exception as e:
        return f"Error: {str(e)}"
