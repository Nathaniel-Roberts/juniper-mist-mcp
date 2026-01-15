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

### Step 1: Configure Your API Token

Create a config file at `~/.config/juniper-mist-mcp/.env`:

```bash
mkdir -p ~/.config/juniper-mist-mcp
echo "MIST_API_TOKEN=your_token_here" > ~/.config/juniper-mist-mcp/.env
```

This keeps your token out of mcp.json and works automatically.

### Step 2: Add the MCP Server

**Option A: Using `uvx` (No Install Required)**

```bash
claude mcp add juniper-mist -- uvx --from git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp juniper-mist-mcp
```

Or add directly to your mcp.json:
```json
{
  "mcpServers": {
    "juniper-mist": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp",
        "juniper-mist-mcp"
      ]
    }
  }
}
```

**Option B: Using `pip install`**

```bash
pip install git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp
```

Then add to your mcp.json:
```json
{
  "mcpServers": {
    "juniper-mist": {
      "command": "juniper-mist-mcp"
    }
  }
}
```

### Alternative: Token in mcp.json

If you prefer to keep the token in mcp.json instead of a `.env` file:

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

### Organization & Sites
- `list_organizations` - See all your organizations
- `get_organization_info` - Get details about a specific org
- `list_sites` - List all sites in an organization
- `get_site_info` - Get site configuration details
- `get_site_stats` - Get site health metrics

### Device Management
- `get_device_inventory` - View all devices in your inventory
- `get_device_stats` - Get real-time device statistics
- `get_device_config` - View device configuration
- `get_device_events` - Get device events
- `search_organization_devices` - Find devices by name, MAC, serial, or model
- `get_switch_port_stats` - Get switch port status and traffic

### Network Monitoring
- `get_alarms` - View active alerts and alarms
- `get_marvis_actions` - Get Marvis AI recommendations
- `get_org_stats_summary` - Organization-wide health summary
- `get_rf_stats` - RF environment statistics
- `get_site_wan_stats` - WAN link status
- `get_rogue_aps` - Detect rogue access points

### Client & Wireless
- `get_client_stats` - Connected client information
- `list_wlans` - Site wireless networks
- `list_org_wlans` - Organization WLAN templates

### NAC & Authentication Troubleshooting
- `search_client_events` - Search wireless client events (auth failures, DHCP issues, roaming)
- `get_client_session_history` - Detailed session history for a client
- `search_nac_client_events` - Search 802.1X/RADIUS authentication events
- `get_nac_rules` - View NAC policy rules
- `get_nac_tags` - View NAC tags/roles
- `get_org_radius_config` - RADIUS server configuration
- `get_org_idps` - Identity provider (IdP) configuration
- `search_wired_client_events` - Wired port authentication events
- `get_client_by_mac` - Look up client details by MAC address
- `get_nac_portal_logs` - Guest/sponsor portal logs

### Audit
- `get_audit_logs` - Administrative change logs

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
- A Juniper Mist account with API access

## Security Notes

- Start with **read-only tokens** - only add write permissions when needed
- Your API token is stored in your MCP config - keep this file secure
- Rotate your API tokens periodically
- If you suspect a token has been compromised, revoke it immediately in the Mist dashboard

## License

MIT License

---

*This project was created with [Claude Code](https://claude.ai/code), an AI-powered coding assistant by Anthropic.*
