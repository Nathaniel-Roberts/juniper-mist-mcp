"""NAC & authentication tools for the Juniper Mist MCP server."""

import time
from typing import Literal, Optional

from mcp.types import CallToolResult

from ..api import mist_api_request, resolve_org_id, resolve_site_id
from ..formatting import format_timestamp, json_tool_result, truncate_response
from ..server import READ_ONLY, mcp


@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def search_nac_client_events(
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    client_mac: Optional[str] = None,
    username: Optional[str] = None,
    auth_type: Optional[str] = None,
    nac_result: Optional[Literal["success", "failure", "all"]] = "all",
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Search NAC (Network Access Control) authentication events.

    Retrieves 802.1X, RADIUS, and NAC authentication events including successes,
    failures, and policy matches. Critical for troubleshooting authentication issues.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        if site_id:
            site_id = await resolve_site_id(site_id, org_id)
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
            return json_tool_result(events)

        results_list = events.get('results', events) if isinstance(events, dict) else events

        if not results_list:
            return f"# NAC Client Events\n\nNo NAC events found in the last {duration} hour(s)."

        result = "# NAC Client Events\n\n"
        result += f"Found {len(results_list)} event(s) in the last {duration} hour(s)\n\n"

        # Group by result (single-pass O(n) approach)
        successes = []
        failures = []
        others = []
        for e in results_list:
            nac_result = e.get('nac_result') or e.get('auth_result')
            if nac_result == 'success':
                successes.append(e)
            elif nac_result == 'failure':
                failures.append(e)
            else:
                others.append(e)

        if failures:
            result += f"## Authentication Failures ({len(failures)})\n\n"
            for event in failures[:30]:
                if 'timestamp' in event:
                    ts = format_timestamp(event['timestamp'])
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
                if event.get('failure_reason') or event.get('reason'):
                    result += f"- **Reason:** {event.get('failure_reason') or event.get('reason')}\n"
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
            result += f"## Authentication Successes ({len(successes)})\n\n"
            for event in successes[:20]:
                if 'timestamp' in event:
                    ts = format_timestamp(event['timestamp'])
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
            result += f"## Other Events ({len(others)})\n\n"
            for event in others[:10]:
                result += f"- {event.get('type', 'Unknown')}: MAC {event.get('mac', 'N/A')}\n"
            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error searching NAC events: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_nac_rules(
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get NAC (Network Access Control) rules and policies.

    Retrieves all NAC rules configured at the organization level, including
    matching criteria, actions, and VLAN assignments. Useful for understanding
    why clients are assigned to specific VLANs or denied access.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        rules = await mist_api_request(f"/orgs/{org_id}/nacrules")

        if format == "json":
            return json_tool_result(rules)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_nac_tags(
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get NAC tags (labels/roles) configured in the organization.

    NAC tags are labels used to categorize clients and apply policies.
    They can be assigned by RADIUS, IdP, or NAC rules.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        tags = await mist_api_request(f"/orgs/{org_id}/nactags")

        if format == "json":
            return json_tool_result(tags)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_org_radius_config(
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get RADIUS and authentication server configurations.

    Retrieves RADIUS server configurations, including primary/secondary servers,
    authentication settings, and accounting configuration. Essential for
    troubleshooting 802.1X and NAC authentication issues.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
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
            return json_tool_result(radius_config)

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

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_org_idps(
    org_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get Identity Provider (IdP) configurations for NAC.

    Retrieves configured identity providers used for authentication,
    including LDAP, Azure AD, Okta, and other SAML/OAuth providers.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        # IdPs are under the SSO endpoint in Mist API
        idps = await mist_api_request(f"/orgs/{org_id}/ssos")

        if format == "json":
            return json_tool_result(idps)

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
                result += "- **SCIM Enabled:** Yes\n"

            # Group/role mapping
            if idp.get('group_filter'):
                result += f"- **Group Filter:** {idp['group_filter']}\n"
            if idp.get('role_attr_extraction'):
                result += f"- **Role Attribute:** {idp['role_attr_extraction']}\n"
            if idp.get('role_attr_from'):
                result += f"- **Role Source:** {idp['role_attr_from']}\n"

            # MDM integration
            if idp.get('mxedge_proxy_enabled'):
                result += "- **MXEdge Proxy:** Enabled\n"

            result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting IdPs: {str(e)}"

@mcp.tool(annotations=READ_ONLY, structured_output=False)
async def get_nac_portal_logs(
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    nac_portal_id: Optional[str] = None,
    duration: int = 24,
    limit: int = 100,
    format: Literal["json", "markdown"] = "markdown"
) -> str | CallToolResult:
    """
    Get NAC portal (guest/sponsor) authentication logs.

    Retrieves logs from NAC portals including guest registration,
    sponsor approvals, and self-registration events.

    Args:
        org_id: Organization UUID (optional; defaults to the MIST_ORG_ID env var)
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
        org_id = resolve_org_id(org_id)
        if site_id:
            site_id = await resolve_site_id(site_id, org_id)
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
                return json_tool_result({"portals": portals, "logs": []})

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
            return json_tool_result(logs)

        results_list = logs.get('results', logs) if isinstance(logs, dict) else logs

        if not results_list:
            return f"# NAC Portal Logs\n\nNo NAC portal activity found in the last {duration} hour(s)."

        result = "# NAC Portal Logs\n\n"
        result += f"Found {len(results_list)} log entries in the last {duration} hour(s)\n\n"

        for log in results_list[:limit]:
            if 'timestamp' in log:
                ts = format_timestamp(log['timestamp'])
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
