#!/usr/bin/env python3
"""
Juniper Mist MCP Server

Provides Claude with access to Juniper Mist networking APIs.
Phase 1: Read-only operations for safe network monitoring
Phase 2: Write operations (planned)

License: MIT
"""

from .api import (  # noqa: F401
    MIST_API_BASE_URL,
    MIST_API_TOKEN,
    MIST_ORG_ID,
    MistAPIError,
    mist_api_request,
)
from .formatting import (  # noqa: F401
    format_as_markdown,
    format_dict_as_markdown,
    format_timestamp,
    json_tool_result,
    local_timezone_name,
    truncate_response,
)
from .server import READ_ONLY, mcp  # noqa: F401
from . import tools  # noqa: F401  (importing registers all tools)

from .tools.orgs import (  # noqa: F401
    list_organizations,
    get_organization_info,
    list_sites,
    get_site_info,
    get_site_stats,
    get_org_stats_summary,
)
from .tools.devices import (  # noqa: F401
    get_device_inventory,
    get_device_stats,
    search_organization_devices,
    get_device_config,
    get_device_events,
    get_switch_port_stats,
)
from .tools.wireless import (  # noqa: F401
    list_wlans,
    list_org_wlans,
    get_rf_stats,
    get_ap_radio_status,
    get_rogue_aps,
    get_site_insights,
)
from .tools.monitoring import (  # noqa: F401
    get_alarms,
    get_marvis_actions,
    get_site_wan_stats,
)
from .tools.clients import (  # noqa: F401
    get_client_stats,
    get_client_by_mac,
    search_client_events,
    get_client_session_history,
    search_wired_client_events,
)
from .tools.nac import (  # noqa: F401
    search_nac_client_events,
    get_nac_rules,
    get_nac_tags,
    get_org_radius_config,
    get_org_idps,
    get_nac_portal_logs,
)
from .tools.sle import (  # noqa: F401
    get_sle_metrics,
    get_sle_summary,
    get_sle_histogram,
    get_sle_impact,
    get_sle_impacted_aps,
    get_sle_impacted_clients,
)
from .tools.location import (  # noqa: F401
    list_site_maps,
    get_map_info,
    list_zones,
    list_assets,
    get_asset_stats,
    search_assets,
    get_discovered_assets,
    get_client_location_history,
    search_clients_by_location,
)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
