"""Client troubleshooting tools for the Juniper Mist MCP server."""

import json
import time
from datetime import datetime
from typing import Literal, Optional

from ..api import mist_api_request
from ..formatting import truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY)
async def get_client_stats(
    org_id: str,
    site_id: str,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get statistics about connected wireless clients.

    Retrieves information about clients currently connected to the network,
    including device types, connection details, and performance metrics.

    Args:
        org_id: Organization UUID
        site_id: Site UUID to get clients from
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
        endpoint = f"/sites/{site_id}/stats/clients"
        params = {"limit": limit}

        clients = await mist_api_request(endpoint, params=params)

        if format == "json":
            return truncate_response(json.dumps(clients, indent=2))

        if not clients:
            return "# Connected Clients\n\nNo clients currently connected to site."

        result = "# Connected Clients\n\n"
        result += f"Total: {len(clients)} client(s)\n\n"

        # Table header
        result += "| Hostname | MAC | IP | SSID | AP MAC | RSSI | Band | Device |\n"
        result += "|----------|-----|----|----- |--------|------|------|--------|\n"

        for i, client in enumerate(clients[:100], 1):
            hostname = client.get('hostname', client.get('mac', f'Client {i}'))
            mac = client.get('mac', 'N/A')
            ip = client.get('ip', 'N/A')
            ssid = client.get('ssid', 'N/A')
            ap_mac = client.get('ap_mac', 'N/A')
            rssi = f"{client['rssi']} dBm" if 'rssi' in client else 'N/A'
            band = client.get('band', 'N/A')
            device = f"{client.get('manufacture', '')} {client.get('os', '')}".strip() or 'N/A'
            result += f"| {hostname} | {mac} | {ip} | {ssid} | {ap_mac} | {rssi} | {band} | {device} |\n"

        if len(clients) > 100:
            result += f"\n... and {len(clients) - 100} more clients (showing first 100)\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting client statistics: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
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
            return truncate_response(json.dumps(clients, indent=2))

        results_list = clients.get('results', clients) if isinstance(clients, dict) else clients

        if not results_list:
            return f"# Client Lookup\n\nNo client found with MAC address `{client_mac}`."

        client = results_list[0]

        result = "# Client Details\n\n"
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
            result += "- **Status:** Connected\n"
        else:
            result += "- **Status:** Disconnected\n"

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
            ts = datetime.fromtimestamp(client['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **Last Seen:** {ts}\n"
        if client.get('first_seen'):
            ts = datetime.fromtimestamp(client['first_seen']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **First Seen:** {ts}\n"
        if client.get('connect_time'):
            ts = datetime.fromtimestamp(client['connect_time']).strftime('%Y-%m-%d %H:%M:%S')
            result += f"- **Connected At:** {ts}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error looking up client: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
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
            return truncate_response(json.dumps(events, indent=2))

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

            result += f"## {etype} ({len(type_events)})\n\n"

            for event in type_events[:20]:  # Show up to 20 per type
                if 'timestamp' in event:
                    ts = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    result += f"### {ts}\n\n"

                result += f"- **Client MAC:** {event.get('mac', 'N/A')}\n"

                if event.get('hostname'):
                    result += f"- **Hostname:** {event['hostname']}\n"
                if event.get('ssid'):
                    result += f"- **SSID:** {event['ssid']}\n"
                if event.get('ap') or event.get('ap_mac'):
                    result += f"- **AP:** {event.get('ap') or event.get('ap_mac', 'N/A')}\n"
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

@mcp.tool(annotations=READ_ONLY)
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
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "mac": client_mac.lower().replace("-", ":"),
            "start": start_time,
            "end": end_time
        }

        sessions = await mist_api_request(f"/sites/{site_id}/clients/sessions/search", params=params)

        if format == "json":
            return truncate_response(json.dumps(sessions, indent=2))

        results_list = sessions.get('results', sessions) if isinstance(sessions, dict) else sessions

        if not results_list:
            return f"# Client Session History\n\nNo sessions found for client `{client_mac}` in the last {duration} hour(s)."

        result = "# Client Session History\n\n"
        result += f"**Client MAC:** `{client_mac}`\n"
        result += f"**Time Range:** Last {duration} hour(s)\n"
        result += f"**Total Sessions:** {len(results_list)}\n\n"

        for i, session in enumerate(results_list, 1):
            result += f"## Session {i}\n\n"

            # Connection times
            if 'connect_time' in session or 'timestamp' in session:
                connect_ts = session.get('connect_time') or session.get('timestamp')
                result += f"- **Connected:** {datetime.fromtimestamp(connect_ts).strftime('%Y-%m-%d %H:%M:%S')}\n"
            if 'disconnect_time' in session:
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
                result += "\n### Disconnect\n\n"
                result += f"- **Reason:** {session['disconnect_reason']}\n"

            result += "\n---\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting client session history: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
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
            return truncate_response(json.dumps(events, indent=2))

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
            result += f"## {etype} ({len(type_events)})\n\n"

            for event in type_events[:25]:
                if 'timestamp' in event:
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
                if event.get('failure_reason') or event.get('reason'):
                    result += f"- **Reason:** {event.get('failure_reason') or event.get('reason')}\n"
                if event.get('radius_reply_message'):
                    result += f"- **RADIUS Message:** {event['radius_reply_message']}\n"

                result += "\n"

            if len(type_events) > 25:
                result += f"... and {len(type_events) - 25} more {etype} events\n\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching wired client events: {str(e)}"
