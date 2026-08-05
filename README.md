# Juniper Mist MCP Server

Query and manage your Juniper Mist network infrastructure directly from Claude. This server lets Claude access your Mist-managed networks, devices, sites, clients, and NAC events through natural language.

## What Does This Do?

This is a bridge between Claude (via the Model Context Protocol) and the Juniper Mist API. Once set up, you can ask Claude questions about your network in plain English:

- "How many access points are offline right now?"
- "Show me all critical alerts from the past hour"
- "Why can't user john@example.com authenticate?"
- "Check client events for device aa:bb:cc:dd:ee:ff"
- "What NAC rules are configured?"

Claude will query your Mist infrastructure and give you the answers directly.

## Installation

### Step 1: Add your token to `.env`

Add to your project's `.env` file:

```
MIST_API_TOKEN=your_token_here

# Optional but recommended if you have one organization: tools then
# no longer need an org_id argument
MIST_ORG_ID=your_org_uuid
```

With `MIST_ORG_ID` set, site-scoped tools also accept site **names**
("GPCC", "Library") anywhere they take a site_id.

### Step 2: Add to your `.mcp.json`

Add this to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "juniper-mist": {
      "command": "uvx",
      "args": [
        "--env-file", ".env",
        "--from",
        "git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp",
        "juniper-mist-mcp"
      ]
    }
  }
}
```

That's it! The `--env-file .env` flag tells uvx to load your token from the `.env` file.

### Alternative: Token directly in mcp.json

If you prefer not to use a `.env` file:

```json
{
  "mcpServers": {
    "juniper-mist": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp",
        "juniper-mist-mcp"
      ],
      "env": {
        "MIST_API_TOKEN": "YOUR_TOKEN_HERE"
      }
    }
  }
}
```

## Getting Your Mist API Token

1. Log in to the Mist dashboard at https://manage.mist.com
2. Go to **Organization > Settings > API Tokens**
3. Click **Create Token**
4. Give it a name like "Claude MCP Server"
5. Set permissions to **Read Only** (recommended for safety)
6. Copy the token

## Verify Installation

```bash
# List configured MCP servers
claude mcp list

# You should see "juniper-mist" listed
```

## Available Tools

All 47 tools are read-only (each carries the MCP `readOnlyHint` annotation); nothing here can change your network. Every tool takes `format: "markdown" | "json"`; JSON responses include MCP `structuredContent` alongside the text so clients get machine-readable data.

### Organizations & Sites
- `list_organizations` - See all your organizations
- `get_organization_info` - Get details about a specific org
- `get_org_stats_summary` - Organization-wide health summary
- `list_sites` - List all sites in an organization
- `get_site_info` - Get site configuration details
- `get_site_stats` - Get site health metrics

### Devices
- `get_device_inventory` - View all devices in your inventory
- `get_device_stats` - Get real-time device statistics
- `get_device_config` - View device configuration
- `get_device_events` - Get device events
- `search_organization_devices` - Find devices by name, MAC, serial, or model
- `get_switch_port_stats` - Get switch port status and traffic

### Wireless & RF
- `list_wlans` - Site wireless networks
- `list_org_wlans` - Organization WLAN templates
- `get_rf_stats` - RF environment statistics
- `get_ap_radio_status` - Channels, power, and clients per AP radio
- `get_rogue_aps` - Detect rogue access points
- `get_site_insights` - Site traffic/client analytics over time

### Monitoring
- `get_alarms` - View active alerts and alarms
- `get_marvis_actions` - Get Marvis AI recommendations
- `get_site_wan_stats` - WAN link status

### Client Troubleshooting
- `get_client_stats` - Connected client information
- `get_client_by_mac` - Look up client details by MAC address
- `search_client_events` - Wireless client events (auth failures, DHCP issues, roaming)
- `get_client_session_history` - Detailed session history for a client
- `search_wired_client_events` - Wired port authentication events

### NAC & Authentication
- `search_nac_client_events` - Search 802.1X/RADIUS authentication events
- `get_nac_rules` - View NAC policy rules
- `get_nac_tags` - View NAC tags/roles
- `get_org_radius_config` - RADIUS server configuration
- `get_org_idps` - Identity provider (IdP) configuration
- `get_nac_portal_logs` - Guest/sponsor portal logs

### SLE (Service Level Expectations)
- `get_sle_metrics` - List available SLE metrics
- `get_sle_summary` - Success rate for a metric
- `get_sle_histogram` - Metric performance over time
- `get_sle_impact` - What's causing metric failures
- `get_sle_impacted_aps` - APs most affected by failures
- `get_sle_impacted_clients` - Clients most affected by failures

### Maps, Assets & Location
- `list_site_maps` - Floor plans configured at a site
- `get_map_info` - Map details including AP placements
- `list_zones` - Location zones on floor plans
- `list_assets` / `search_assets` - BLE asset tags
- `get_asset_stats` - Real-time asset locations
- `get_discovered_assets` - Detected but unassigned BLE devices
- `get_client_location_history` - Where a device has been (AP timeline)
- `search_clients_by_location` - Who has been on a specific floor

## Example Queries

```
"What organizations do I have access to?"

"Are there any critical alarms right now?"

"Show me all disconnected access points"

"Why is user john@example.com having authentication problems?"

"Check client events for MAC aa:bb:cc:dd:ee:ff over the last 48 hours"

"What NAC rules would apply to a device from VLAN 100?"

"Show me 802.1X failures in the last hour"

"How many clients are connected across all sites?"
```

## Troubleshooting

**"Authentication failed"**
- Double-check your API token
- Make sure the token hasn't expired
- Verify the token has the right permissions

**"Organization not found"**
- Use `list_organizations` first to see available orgs
- Make sure you're using the correct organization ID (UUID format)

**"Rate limit exceeded"**
- The Mist API limits requests to 5,000 per hour
- Wait a few minutes and try again

**Server not appearing**
- Run `claude mcp list` to verify registration
- Restart Claude Code after adding the server

## Requirements

- Python 3.10 or higher
- MCP Python SDK 2.0 or higher (installed automatically)
- A Juniper Mist account with API access

## Development

```bash
git clone https://github.com/Nathaniel-Roberts/juniper-mist-mcp
cd juniper-mist-mcp

# Run tests (no Mist account needed; HTTP is mocked)
uv run --group dev pytest

# Lint
uv run --group dev ruff check .
```

Source layout: `src/juniper_mist_mcp/` contains `api.py` (HTTP client),
`server.py` (MCP server instance), `formatting.py` (markdown helpers), and
`tools/` with one module per tool group. See `CLAUDE.md` for conventions
when adding tools.

## Security Notes

- Start with **read-only tokens** - only add write permissions when needed
- Your API token is stored in your MCP config - keep this file secure
- Rotate your API tokens periodically
- If you suspect a token has been compromised, revoke it immediately in the Mist dashboard

## License

MIT License

---

*This project was created with [Claude Code](https://claude.ai/code), an AI-powered coding assistant by Anthropic.*
