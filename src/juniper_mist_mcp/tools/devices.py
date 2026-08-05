"""Device tools for the Juniper Mist MCP server."""

from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import mist_api_request, resolve_org_id, resolve_site_id
from ..formatting import format_timestamp, json_tool_result, truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_device_inventory(
    org_id: Optional[str] = None,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get inventory of all devices in an organization.

    Retrieves device inventory including claimed and unclaimed devices,
    with their serial numbers, models, MAC addresses, and claim status.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        params = {"limit": min(limit, 1000)}
        if device_type != "all":
            params["type"] = device_type

        inventory = await mist_api_request(f"/orgs/{org_id}/inventory", params=params)

        if format == "json":
            return json_tool_result(inventory)

        if not inventory:
            return "# Device Inventory\n\nNo devices found in inventory."

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

            # Table header
            result += "| Name | Serial | MAC | Model | Site ID | Claimed |\n"
            result += "|------|--------|-----|-------|---------|--------|\n"

            for device in devices[:50]:  # Limit per type
                name = device.get('name', device.get('model', 'Unknown'))
                serial = device.get('serial', 'N/A')
                mac = device.get('mac', 'N/A')
                model = device.get('model', 'N/A')
                site_id = device.get('site_id', 'N/A')
                claimed = 'Yes' if device.get('claimed') else 'No'
                result += f"| {name} | {serial} | {mac} | {model} | {site_id} | {claimed} |\n"

            if len(devices) > 50:
                result += f"\n... and {len(devices) - 50} more {dtype} devices\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device inventory: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_device_stats(
    site_id: str,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    status: Literal["connected", "disconnected", "all"] = "all",
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get real-time statistics for devices in an organization or site.

    Retrieves current device status, uptime, version, client count, and performance metrics.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        endpoint = f"/sites/{site_id}/stats/devices"
        params = {"limit": min(limit, 1000)}

        if device_type != "all":
            params["type"] = device_type
        if status != "all":
            params["status"] = status

        stats = await mist_api_request(endpoint, params=params)

        if format == "json":
            return json_tool_result(stats)

        if not stats:
            return "# Device Statistics\n\nNo devices found matching the filters."

        result = "# Device Statistics\n\n"
        result += f"Found {len(stats)} device(s)\n\n"

        # Table header
        result += "| Name | MAC | Model | Type | Status | Uptime (hrs) | Clients | IP |\n"
        result += "|------|-----|-------|------|--------|--------------|---------|----|\n"

        for device in stats[:100]:
            name = device.get('name', device.get('mac', 'Unknown'))
            mac = device.get('mac', 'N/A')
            model = device.get('model', 'N/A')
            dtype = device.get('type', 'N/A')
            status = device.get('status', 'N/A')
            uptime = f"{device['uptime'] / 3600:.1f}" if 'uptime' in device else 'N/A'
            clients = str(device.get('num_clients', 'N/A'))
            ip = device.get('ip', 'N/A')
            result += f"| {name} | {mac} | {model} | {dtype} | {status} | {uptime} | {clients} | {ip} |\n"

        if len(stats) > 100:
            result += f"\n... and {len(stats) - 100} more devices (showing first 100)\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting device statistics: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_organization_devices(
    search_term: str,
    org_id: Optional[str] = None,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Search for devices by name, MAC address, serial number, or model.

    Searches across all devices in an organization to find matches.

    Args:
        search_term: Search string (name, MAC, serial, model)
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        # Normalize search term for MAC address matching
        search_normalized = search_term.lower().replace("-", ":").replace(".", ":")

        # Build query params for server-side filtering
        # The Mist inventory API supports: serial, mac, model, type, limit
        params = {"limit": min(limit * 3, 500)}  # Request more than needed for client-side filtering

        if device_type != "all":
            params["type"] = device_type

        # Detect if search term looks like a MAC address, serial, or model
        # and use the appropriate server-side filter
        is_mac_format = len(search_normalized.replace(":", "")) == 12 and all(
            c in "0123456789abcdef:" for c in search_normalized
        )
        is_serial_format = search_term.upper().replace("-", "").isalnum() and len(search_term) >= 8

        # Try server-side filtering first for exact matches
        matches = []

        # If it looks like a MAC address, try exact MAC filter first
        if is_mac_format:
            params["mac"] = search_normalized
            inventory = await mist_api_request(f"/orgs/{org_id}/inventory", params=params)
            if inventory:
                matches.extend(inventory)

        # If it looks like a serial number and no MAC matches, try serial filter
        if not matches and is_serial_format:
            serial_params = {"limit": min(limit, 100)}
            if device_type != "all":
                serial_params["type"] = device_type
            serial_params["serial"] = search_term.upper()
            inventory = await mist_api_request(f"/orgs/{org_id}/inventory", params=serial_params)
            if inventory:
                matches.extend(inventory)

        # If no exact matches found, fall back to broader search with client-side filtering
        if not matches:
            # Request a limited inventory for client-side search
            fallback_params = {"limit": min(limit * 5, 500)}  # Limit payload size
            if device_type != "all":
                fallback_params["type"] = device_type

            inventory = await mist_api_request(f"/orgs/{org_id}/inventory", params=fallback_params)

            if not inventory:
                return "# Device Search Results\n\nNo devices in inventory to search."

            # Search across relevant fields (client-side)
            search_lower = search_term.lower()

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

        # Deduplicate matches (in case of overlap from multiple queries)
        seen_serials = set()
        unique_matches = []
        for device in matches:
            serial = device.get('serial', '')
            if serial not in seen_serials:
                seen_serials.add(serial)
                unique_matches.append(device)
                if len(unique_matches) >= limit:
                    break

        matches = unique_matches

        if format == "json":
            return json_tool_result(matches)

        if not matches:
            return f"# Device Search Results\n\nNo devices found matching '{search_term}'."

        result = "# Device Search Results\n\n"
        result += f"Found {len(matches)} device(s) matching '{search_term}'\n\n"

        # Table format
        result += "| Name | Serial | MAC | Model | Type | Site ID |\n"
        result += "|------|--------|-----|-------|------|--------|\n"

        for device in matches:
            name = device.get('name', 'Unnamed')
            serial = device.get('serial', 'N/A')
            mac = device.get('mac', 'N/A')
            model = device.get('model', 'N/A')
            dtype = device.get('type', 'N/A')
            site = device.get('site_id', 'N/A')[:8] + '...' if device.get('site_id') else 'N/A'
            result += f"| {name} | {serial} | {mac} | {model} | {dtype} | {site} |\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching devices: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_device_config(
    site_id: str,
    device_id: str,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get the configuration of a specific device.

    Retrieves the full configuration of an AP, switch, or gateway including
    network settings, ports, radio config, and management settings.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        config = await mist_api_request(f"/sites/{site_id}/devices/{device_id}")

        if format == "json":
            return json_tool_result(config)

        result = "# Device Configuration\n\n"
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_device_events(
    site_id: str,
    device_mac: Optional[str] = None,
    device_type: Literal["ap", "switch", "gateway", "all"] = "all",
    limit: int = 50,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get recent events for devices at a site.

    Retrieves device events including status changes, configuration updates,
    reboots, and errors.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        params = {"limit": limit}
        if device_mac:
            params["mac"] = device_mac
        if device_type != "all":
            params["type"] = device_type

        events = await mist_api_request(f"/sites/{site_id}/devices/events/search", params=params)

        if format == "json":
            return json_tool_result(events)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            return "# Device Events\n\nNo recent events found."

        result = "# Device Events\n\n"
        result += f"Found {len(results_list)} event(s)\n\n"

        for event in results_list[:limit]:
            event_type = event.get('type', 'Unknown Event')
            result += f"## {event_type}\n\n"

            if 'timestamp' in event:
                ts = format_timestamp(event['timestamp'])
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_switch_port_stats(
    site_id: str,
    switch_mac: Optional[str] = None,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get switch port statistics including status, speed, and traffic.

    Retrieves real-time port information for switches at a site including
    link status, speed/duplex, VLAN, PoE status, and connected devices.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        params = {"limit": limit}
        if switch_mac:
            params["mac"] = switch_mac

        response = await mist_api_request(f"/sites/{site_id}/stats/switch_ports/search", params=params)

        if format == "json":
            return json_tool_result(response)

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
                status = 'Up' if port.get('up', False) else 'Down'
                speed = port.get('speed', 'N/A')
                if speed and speed != 'N/A':
                    speed = f"{speed}Mbps"
                vlan = port.get('vlan_id', 'N/A')
                poe_on = 'Yes' if port.get('poe_on', False) else '-'
                desc = port.get('port_desc', '-')[:20]

                result += f"| {port_id} | {status} | {speed} | {vlan} | {poe_on} | {desc} |\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting switch port stats: {str(e)}"
