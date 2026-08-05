"""Client troubleshooting tools for the Juniper Mist MCP server."""

import asyncio
import time
from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import mist_api_request, resolve_org_id, resolve_site_id
from ..formatting import format_timestamp, json_tool_result, truncate_response
from ..server import READ_ONLY, mcp


async def _best_effort(coro):
    """Run one part of a composite lookup; failures become notes, not errors."""
    try:
        return await coro, None
    except Exception as e:
        return None, str(e)


def _results_of(data) -> list:
    if data is None:
        return []
    return data.get("results", data) if isinstance(data, dict) else data


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def troubleshoot_client(
    client_mac: str,
    site_id: Optional[str] = None,
    org_id: Optional[str] = None,
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Run a full troubleshooting workup for one client in a single call.

    Combines what would otherwise be five separate lookups: current client
    status, wireless client events, session history, NAC/802.1X events, and
    wired client events. Each part is best-effort, so a missing NAC licence
    or an unused event type does not block the rest of the report.

    Use this FIRST when someone asks why a device or user cannot connect,
    keeps dropping, or landed in the wrong VLAN.

    Args:
        client_mac: Client MAC address (format: aa:bb:cc:dd:ee:ff)
        site_id: Site UUID or site name (optional; auto-detected from the
                 client's last known site when omitted)
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
        duration: Hours of history to analyze (default 24)
        format: Response format

    Returns:
        A single report: identity and current status, connection failures
        with reasons, session/roaming summary, and NAC decisions

    Example:
        User: "Why can't aa:bb:cc:dd:ee:ff get on the network?"
        -> Use this tool with the client_mac

        User: "Kristy's laptop keeps dropping off the wifi"
        -> Find the MAC (search by hostname), then use this tool
    """
    try:
        org_id = resolve_org_id(org_id)
        mac = client_mac.lower().replace("-", ":")
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)
        window = {"start": start_time, "end": end_time}

        # Step 1: find the client and its site
        lookup, lookup_err = await _best_effort(mist_api_request(
            f"/orgs/{org_id}/clients/search", params={"mac": mac, "limit": 1}
        ))
        client = (_results_of(lookup) or [None])[0]

        if site_id:
            site_id = await resolve_site_id(site_id, org_id)
        elif client and client.get("site_id"):
            site_id = client["site_id"]

        # Step 2: gather evidence concurrently
        nac_coro = _best_effort(mist_api_request(
            f"/orgs/{org_id}/nac_clients/events/search",
            params={"mac": mac, "limit": 200, **window},
        ))
        if site_id:
            events_coro = _best_effort(mist_api_request(
                f"/sites/{site_id}/clients/events/search",
                params={"mac": mac, "limit": 200, **window},
            ))
            sessions_coro = _best_effort(mist_api_request(
                f"/sites/{site_id}/clients/sessions/search",
                params={"mac": mac, "limit": 100, **window},
            ))
            wired_coro = _best_effort(mist_api_request(
                f"/sites/{site_id}/wired_clients/events/search",
                params={"mac": mac, "limit": 100, **window},
            ))
            (events, events_err), (sessions, sessions_err), \
                (nac, nac_err), (wired, wired_err) = await asyncio.gather(
                    events_coro, sessions_coro, nac_coro, wired_coro)
        else:
            events = sessions = wired = None
            events_err = sessions_err = wired_err = "no site known for this client"
            nac, nac_err = await nac_coro

        events_list = _results_of(events)
        sessions_list = _results_of(sessions)
        nac_list = _results_of(nac)
        wired_list = _results_of(wired)

        if format == "json":
            return json_tool_result({
                "mac": mac,
                "client": client,
                "site_id": site_id,
                "events": events_list,
                "sessions": sessions_list,
                "nac_events": nac_list,
                "wired_events": wired_list,
                "errors": {k: v for k, v in {
                    "client_lookup": lookup_err, "events": events_err,
                    "sessions": sessions_err, "nac": nac_err, "wired": wired_err,
                }.items() if v},
            })

        result = f"# Client Troubleshooting Report: `{mac}`\n\n"
        result += f"**Window:** last {duration} hour(s)\n\n"

        # Identity & current status
        result += "## Current Status\n\n"
        if client:
            hostname = client.get("hostname")
            if hostname:
                result += f"- **Hostname:** {hostname}\n"
            device = f"{client.get('manufacture', '')} {client.get('os', '')}".strip()
            if device:
                result += f"- **Device:** {device}\n"
            result += f"- **Connected:** {'Yes' if client.get('connected') else 'No'}\n"
            for label, key in (("SSID", "ssid"), ("IP", "ip"), ("VLAN", "vlan"),
                               ("Username", "username"), ("NAC Role", "nac_role")):
                if client.get(key):
                    result += f"- **{label}:** {client[key]}\n"
            ap = client.get("ap") or client.get("last_ap")
            if ap:
                result += f"- **AP:** {ap}\n"
            if client.get("last_seen"):
                result += f"- **Last Seen:** {format_timestamp(client['last_seen'])}\n"
        else:
            result += ("- Client not found in the org client index. It may never have "
                       "connected, or the MAC may be wrong/randomised.\n")

        # Failures first: NAC + wireless auth/dhcp/dns problems
        nac_failures = [e for e in nac_list
                        if (e.get("nac_result") or e.get("auth_result")) == "failure"
                        or "DENY" in str(e.get("type", ""))]
        problem_events = [e for e in events_list
                          if any(w in str(e.get("type", "")).upper()
                                 for w in ("FAIL", "DENY", "TIMEOUT", "REJECT"))]

        result += "\n## Failures\n\n"
        if not nac_failures and not problem_events:
            result += "No authentication, DHCP, or DNS failures in the window.\n"
        for e in (nac_failures + problem_events)[:15]:
            ts = format_timestamp(e["timestamp"]) if e.get("timestamp") else "?"
            reason = e.get("failure_reason") or e.get("reason") or \
                e.get("radius_reply_message") or ""
            line = f"- {ts}: **{e.get('type', 'failure')}**"
            if e.get("ssid"):
                line += f" on {e['ssid']}"
            if e.get("username"):
                line += f" as {e['username']}"
            if reason:
                line += f" — {reason}"
            result += line + "\n"

        # Session summary
        result += "\n## Sessions\n\n"
        if sessions_list:
            aps = {}
            for s in sessions_list:
                ap = s.get("ap") or s.get("ap_mac") or "?"
                aps[ap] = aps.get(ap, 0) + 1
            result += f"- **Sessions in window:** {len(sessions_list)}\n"
            result += f"- **Distinct APs:** {len(aps)}"
            if len(aps) > 1:
                result += " (roaming between them)"
            result += "\n"
            last = max(sessions_list,
                       key=lambda s: s.get("connect") or s.get("timestamp") or 0)
            ts = last.get("connect") or last.get("timestamp")
            if ts:
                result += f"- **Most recent session:** {format_timestamp(ts)}"
                if last.get("ssid"):
                    result += f" on {last['ssid']}"
                result += "\n"
        else:
            result += "No wireless sessions found in the window.\n"

        # NAC decisions (successes carry the policy outcome)
        nac_ok = [e for e in nac_list
                  if (e.get("nac_result") or e.get("auth_result")) == "success"]
        if nac_ok:
            result += "\n## NAC Decisions\n\n"
            last_ok = max(nac_ok, key=lambda e: e.get("timestamp") or 0)
            ts = format_timestamp(last_ok["timestamp"]) if last_ok.get("timestamp") else "?"
            result += f"- **Last successful auth:** {ts}\n"
            for label, key in (("Auth Type", "auth_type"), ("Assigned VLAN", "vlan"),
                               ("NAC Rule", "nac_rule_matched"), ("Role", "nac_role")):
                if last_ok.get(key):
                    result += f"- **{label}:** {last_ok[key]}\n"

        if wired_list:
            result += f"\n## Wired Events ({len(wired_list)})\n\n"
            for e in wired_list[:5]:
                ts = format_timestamp(e["timestamp"]) if e.get("timestamp") else "?"
                port = e.get("port_id", "?")
                result += f"- {ts}: {e.get('type', '?')} on port {port}\n"

        # Anything that could not be checked
        notes = {"client lookup": lookup_err, "wireless events": events_err,
                 "sessions": sessions_err, "NAC events": nac_err,
                 "wired events": wired_err}
        skipped = {k: v for k, v in notes.items() if v}
        if skipped:
            result += "\n## Not Checked\n\n"
            for part, why in skipped.items():
                result += f"- {part}: {why}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error troubleshooting client: {str(e)}"


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_client_stats(
    site_id: str,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get statistics about connected wireless clients.

    Retrieves information about clients currently connected to the network,
    including device types, connection details, and performance metrics.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC") to get clients from
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
        site_id = await resolve_site_id(site_id)
        endpoint = f"/sites/{site_id}/stats/clients"
        params = {"limit": limit}

        clients = await mist_api_request(endpoint, params=params)

        if format == "json":
            return json_tool_result(clients)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_client_by_mac(
    client_mac: str,
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Look up detailed information about a client by MAC address.

    Retrieves comprehensive client details including current connection status,
    authentication info, assigned network attributes, and device identification.
    Searches across the entire organization.

    Args:
        client_mac: Client MAC address (format: aa:bb:cc:dd:ee:ff)
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        mac_normalized = client_mac.lower().replace("-", ":")

        # Search for the client across the org
        params = {
            "mac": mac_normalized,
            "limit": 1
        }

        clients = await mist_api_request(f"/orgs/{org_id}/clients/search", params=params)

        if format == "json":
            return json_tool_result(clients)

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
            ts = format_timestamp(client['last_seen'])
            result += f"- **Last Seen:** {ts}\n"
        if client.get('first_seen'):
            ts = format_timestamp(client['first_seen'])
            result += f"- **First Seen:** {ts}\n"
        if client.get('connect_time'):
            ts = format_timestamp(client['connect_time'])
            result += f"- **Connected At:** {ts}\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error looking up client: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_client_events(
    site_id: str,
    client_mac: Optional[str] = None,
    event_type: Optional[str] = None,
    ssid: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Search for wireless client events at a site for troubleshooting.

    Retrieves client connection events including associations, disassociations,
    roaming, authentication failures, and DHCP issues. Essential for troubleshooting
    client connectivity problems.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
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
            return json_tool_result(events)

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
                    ts = format_timestamp(event['timestamp'])
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_client_session_history(
    site_id: str,
    client_mac: str,
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get detailed session history for a specific wireless client.

    Retrieves comprehensive session information for a client including
    connection times, authentication details, roaming history, and network assignment.
    Essential for troubleshooting individual client issues.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "mac": client_mac.lower().replace("-", ":"),
            "start": start_time,
            "end": end_time
        }

        sessions = await mist_api_request(f"/sites/{site_id}/clients/sessions/search", params=params)

        if format == "json":
            return json_tool_result(sessions)

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
                result += f"- **Connected:** {format_timestamp(connect_ts)}\n"
            if 'disconnect_time' in session:
                result += f"- **Disconnected:** {format_timestamp(session['disconnect_time'])}\n"
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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_wired_client_events(
    site_id: str,
    client_mac: Optional[str] = None,
    switch_mac: Optional[str] = None,
    port_id: Optional[str] = None,
    event_type: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Search for wired client events at a site.

    Retrieves 802.1X authentication events, port security events, and
    wired client connectivity events from switches. Essential for
    troubleshooting wired NAC and port security issues.

    Args:
        site_id: Site UUID or site name (e.g. "GPCC")
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
        site_id = await resolve_site_id(site_id)
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
            return json_tool_result(events)

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
                    ts = format_timestamp(event['timestamp'])
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
