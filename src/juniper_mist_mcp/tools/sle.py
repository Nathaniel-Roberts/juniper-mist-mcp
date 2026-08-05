"""SLE (Service Level Expectation) tools for the Juniper Mist MCP server."""

import json
import time
from datetime import datetime
from typing import Literal, Optional

from ..api import mist_api_request
from ..formatting import truncate_response
from ..server import READ_ONLY, mcp


def _build_sle_scope_path(
    scope: str,
    site_id: str,
    scope_id: Optional[str] = None
) -> tuple[str, Optional[str]]:
    """
    Build the scope path for SLE API endpoints.

    Args:
        scope: Scope level - "site", "ap", or "client"
        site_id: Site UUID
        scope_id: Required if scope is "ap" or "client" - the AP MAC or client MAC

    Returns:
        Tuple of (scope_path, error_message).
        If error_message is not None, an error occurred and scope_path should be ignored.
    """
    if scope == "site":
        return f"site/{site_id}", None
    elif scope == "ap":
        if not scope_id:
            return "", "Error: scope_id (AP MAC) is required when scope is 'ap'"
        return f"ap/{scope_id}", None
    elif scope == "client":
        if not scope_id:
            return "", "Error: scope_id (client MAC) is required when scope is 'client'"
        return f"client/{scope_id}", None
    else:
        # Default to site scope
        return f"site/{site_id}", None

@mcp.tool(annotations=READ_ONLY)
async def get_sle_metrics(
    site_id: str,
    scope: Literal["site", "ap", "client"] = "site",
    scope_id: Optional[str] = None,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    List available SLE (Service Level Expectation) metrics for a site.

    SLEs measure network health from the end-user perspective. This tool
    shows which metrics are available and their current status.

    Args:
        site_id: Site UUID to get SLE metrics for
        scope: Scope level - "site" for overall, "ap" for specific AP, "client" for specific client
        scope_id: Required if scope is "ap" or "client" - the AP MAC or client MAC
        format: Response format

    Returns:
        List of available SLE metrics with descriptions

    Available Metrics:
        - time-to-connect: How long it takes clients to connect
        - throughput: Data transfer speeds
        - coverage: Signal strength adequacy
        - capacity: Network load handling
        - roaming: Handoff success between APs
        - successful-connect: Connection success rate
        - ap-availability: AP uptime

    Example:
        User: "What SLE metrics are available?"
        -> Use this with site_id

        User: "Show me network health metrics"
        -> Use this tool to list SLE options
    """
    try:
        # Build the scope path
        scope_path, error = _build_sle_scope_path(scope, site_id, scope_id)
        if error:
            return error

        metrics = await mist_api_request(f"/sites/{site_id}/sle/{scope_path}/metrics")

        if format == "json":
            return truncate_response(json.dumps(metrics, indent=2))

        result = "# SLE Metrics\n\n"
        result += f"**Scope:** {scope}\n"
        result += f"**Site ID:** `{site_id}`\n\n"

        # Known metric descriptions
        metric_descriptions = {
            "time-to-connect": "Measures how long it takes clients to fully connect (association, auth, DHCP)",
            "throughput": "Measures actual data transfer speeds experienced by clients",
            "coverage": "Measures signal strength and whether clients have adequate coverage",
            "capacity": "Measures whether the network can handle the load without degradation",
            "roaming": "Measures success and speed of client handoffs between APs",
            "successful-connect": "Measures the percentage of successful connection attempts",
            "ap-availability": "Measures AP uptime and reachability"
        }

        if isinstance(metrics, list):
            result += f"## Available Metrics ({len(metrics)})\n\n"
            for metric in metrics:
                metric_name = metric if isinstance(metric, str) else metric.get('metric', str(metric))
                result += f"### {metric_name}\n"
                if metric_name in metric_descriptions:
                    result += f"{metric_descriptions[metric_name]}\n"
                if isinstance(metric, dict):
                    if metric.get('threshold'):
                        result += f"- **Threshold:** {metric['threshold']}\n"
                    if metric.get('enabled') is not None:
                        result += f"- **Enabled:** {'Yes' if metric['enabled'] else 'No'}\n"
                result += "\n"
        elif isinstance(metrics, dict):
            for metric_name, metric_data in metrics.items():
                result += f"### {metric_name}\n"
                if metric_name in metric_descriptions:
                    result += f"{metric_descriptions[metric_name]}\n"
                if isinstance(metric_data, dict):
                    for key, value in metric_data.items():
                        result += f"- **{key}:** {value}\n"
                result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting SLE metrics: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
async def get_sle_summary(
    site_id: str,
    metric: Literal["time-to-connect", "throughput", "coverage", "capacity", "roaming", "successful-connect", "ap-availability"],
    scope: Literal["site", "ap", "client"] = "site",
    scope_id: Optional[str] = None,
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get SLE summary showing success rate for a specific metric.

    Returns the percentage of time the metric met its threshold,
    along with the number of samples and degraded samples.

    Args:
        site_id: Site UUID
        metric: Which SLE metric to query
        scope: Scope level - "site", "ap", or "client"
        scope_id: Required if scope is "ap" or "client"
        duration: Hours of data to analyze (default 24)
        format: Response format

    Returns:
        Success rate percentage and sample counts

    Example:
        User: "What's our time-to-connect SLE?"
        -> Use with metric="time-to-connect"

        User: "How is network throughput performing?"
        -> Use with metric="throughput"

        User: "Show me coverage SLE for the last week"
        -> Use with metric="coverage", duration=168
    """
    try:
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        # Build scope path
        scope_path, error = _build_sle_scope_path(scope, site_id, scope_id)
        if error:
            return error

        params = {
            "start": start_time,
            "end": end_time
        }

        summary = await mist_api_request(
            f"/sites/{site_id}/sle/{scope_path}/metric/{metric}/summary",
            params=params
        )

        if format == "json":
            return truncate_response(json.dumps(summary, indent=2))

        result = f"# SLE Summary: {metric}\n\n"
        result += f"**Scope:** {scope}\n"
        result += f"**Period:** Last {duration} hour(s)\n\n"

        # Handle both dict and list responses
        if isinstance(summary, list) and len(summary) > 0:
            summary = summary[0] if len(summary) == 1 else {'data': summary}

        if isinstance(summary, dict):
            # Check for Mist API structure with 'sle' nested object
            sle_data = summary.get('sle', {})
            samples = sle_data.get('samples', {})

            if samples:
                # Sum up all intervals
                total_list = samples.get('total', [])
                degraded_list = samples.get('degraded', [])
                total = sum(total_list) if total_list else 0
                degraded = sum(degraded_list) if degraded_list else 0
            else:
                # Fall back to simple structure
                total = summary.get('total_count', summary.get('total', 0))
                degraded = summary.get('degraded_count', summary.get('degraded', 0))

            if total > 0:
                success_rate = ((total - degraded) / total) * 100
                result += f"## Success Rate: {success_rate:.1f}%\n\n"

                # Visual indicator
                if success_rate >= 95:
                    result += "**Status:** Excellent\n\n"
                elif success_rate >= 80:
                    result += "**Status:** Good\n\n"
                elif success_rate >= 60:
                    result += "**Status:** Fair\n\n"
                else:
                    result += "**Status:** Poor\n\n"

            result += "## Details\n\n"
            result += f"- **Total Samples:** {int(total):,}\n"
            result += f"- **Degraded Samples:** {int(degraded):,}\n"
            result += f"- **Successful Samples:** {int(total - degraded):,}\n"

            # Show impact info if available
            impact = summary.get('impact', {})
            if impact:
                result += "\n## Impact\n\n"
                result += f"- **Affected Users:** {impact.get('num_users', 0)} / {impact.get('total_users', 0)}\n"
                result += f"- **Affected APs:** {impact.get('num_aps', 0)} / {impact.get('total_aps', 0)}\n"

            # Show classifier breakdown if available
            classifiers = summary.get('classifiers', [])
            if classifiers and degraded > 0:
                result += "\n## Failure Breakdown by Classifier\n\n"
                for classifier in classifiers:
                    name = classifier.get('name', 'Unknown')
                    clf_samples = classifier.get('samples', {})
                    clf_degraded_list = clf_samples.get('degraded', [])
                    clf_degraded = sum(clf_degraded_list) if clf_degraded_list else 0
                    if clf_degraded > 0:
                        pct = (clf_degraded / degraded * 100) if degraded > 0 else 0
                        clf_impact = classifier.get('impact', {})
                        users = clf_impact.get('num_users', 0)
                        result += f"- **{name}:** {int(clf_degraded):,} ({pct:.1f}%) - {users} users affected\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting SLE summary: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
async def get_sle_histogram(
    site_id: str,
    metric: Literal["time-to-connect", "throughput", "coverage", "capacity", "roaming", "successful-connect", "ap-availability"],
    scope: Literal["site", "ap", "client"] = "site",
    scope_id: Optional[str] = None,
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get SLE histogram showing time-series data for a metric.

    Returns data points over time showing how the SLE metric
    varied across the specified duration.

    Args:
        site_id: Site UUID
        metric: Which SLE metric to query
        scope: Scope level - "site", "ap", or "client"
        scope_id: Required if scope is "ap" or "client"
        duration: Hours of data (default 24)
        format: Response format

    Returns:
        Time-series data showing metric performance over time

    Example:
        User: "Show me throughput over the last day"
        -> Use with metric="throughput"

        User: "How has coverage varied this week?"
        -> Use with metric="coverage", duration=168
    """
    try:
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        # Build scope path
        scope_path, error = _build_sle_scope_path(scope, site_id, scope_id)
        if error:
            return error

        params = {
            "start": start_time,
            "end": end_time
        }

        histogram = await mist_api_request(
            f"/sites/{site_id}/sle/{scope_path}/metric/{metric}/histogram",
            params=params
        )

        if format == "json":
            return truncate_response(json.dumps(histogram, indent=2))

        result = f"# SLE Histogram: {metric}\n\n"
        result += f"**Period:** Last {duration} hour(s)\n\n"

        if isinstance(histogram, dict):
            data_points = histogram.get('data', histogram.get('results', []))
            x_label = histogram.get('x_label', 'Value')
            y_label = histogram.get('y_label', 'Count')

            if isinstance(data_points, list) and len(data_points) > 0:
                # Check if this is a range-based histogram (distribution)
                if data_points[0].get('range') is not None:
                    result += f"## Distribution Data ({len(data_points)} buckets)\n\n"
                    result += f"**X-Axis:** {x_label}\n"
                    result += f"**Y-Axis:** {y_label}\n\n"
                    result += f"| Range ({x_label}) | {y_label.title()} |\n"
                    result += "|------------------|--------|\n"

                    total_value = sum(p.get('value', 0) for p in data_points)

                    for point in data_points:
                        range_vals = point.get('range', [None, None])
                        low = range_vals[0] if range_vals[0] is not None else "< "
                        high = range_vals[1] if range_vals[1] is not None else "+"
                        value = point.get('value', 0)

                        if range_vals[0] is None:
                            range_str = f"< {high}"
                        elif range_vals[1] is None:
                            range_str = f"> {low}"
                        else:
                            range_str = f"{low} to {high}"

                        pct = (value / total_value * 100) if total_value > 0 else 0
                        result += f"| {range_str} | {value:,.0f} ({pct:.1f}%) |\n"

                # Otherwise, assume time-series data
                else:
                    result += f"## Time Series Data ({len(data_points)} data points)\n\n"
                    result += "| Time | Total | Degraded | Success Rate |\n"
                    result += "|------|-------|----------|-------------|\n"

                    for point in data_points[-20:]:
                        ts = point.get('timestamp', point.get('start', 0))
                        if ts:
                            time_str = datetime.fromtimestamp(ts).strftime('%m/%d %H:%M')
                        else:
                            time_str = "N/A"

                        total = point.get('total_count', point.get('total', 0))
                        degraded = point.get('degraded_count', point.get('degraded', 0))

                        if total > 0:
                            success = ((total - degraded) / total) * 100
                            result += f"| {time_str} | {total} | {degraded} | {success:.1f}% |\n"
                        else:
                            result += f"| {time_str} | {total} | {degraded} | N/A |\n"

                    if len(data_points) > 20:
                        result += f"\n*Showing last 20 of {len(data_points)} data points*\n"
            else:
                result += "No histogram data available for this period.\n"
        else:
            result += "No histogram data available.\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting SLE histogram: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
async def get_sle_impact(
    site_id: str,
    metric: Literal["time-to-connect", "throughput", "coverage", "capacity", "roaming", "successful-connect", "ap-availability"],
    duration: int = 24,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get SLE impact analysis showing what's causing metric failures.

    Breaks down failures by classifier, WLAN, device type, OS,
    and band to identify root causes of SLE degradation.

    Args:
        site_id: Site UUID
        metric: Which SLE metric to analyze
        duration: Hours of data (default 24)
        format: Response format

    Returns:
        Impact breakdown showing failure causes

    Classifiers by Metric:
        - time-to-connect: association, authorization, dhcp, ip-services
        - throughput: capacity, coverage, device-capability, network-issues
        - coverage: asymmetry-downlink, asymmetry-uplink, weak-signal
        - capacity: ap-load, non-wifi-interference, wifi-interference
        - roaming: slow-11r-roams, slow-okc-roams, slow-standard-roams
        - successful-connect: association, authorization, dhcp
        - ap-availability: ap-reboot, ap-unreachable, site-down

    Example:
        User: "Why are clients slow to connect?"
        -> Use with metric="time-to-connect"

        User: "What's causing throughput issues?"
        -> Use with metric="throughput"
    """
    try:
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "start": start_time,
            "end": end_time
        }

        impact = await mist_api_request(
            f"/sites/{site_id}/sle/site/{site_id}/metric/{metric}/impact-summary",
            params=params
        )

        if format == "json":
            return truncate_response(json.dumps(impact, indent=2))

        result = f"# SLE Impact Analysis: {metric}\n\n"
        result += f"**Period:** Last {duration} hour(s)\n\n"

        if isinstance(impact, dict):
            # Classifier breakdown
            if impact.get('classifiers'):
                result += "## Failures by Classifier\n\n"
                total_failures = sum(impact['classifiers'].values())
                for classifier, count in sorted(impact['classifiers'].items(), key=lambda x: x[1], reverse=True):
                    if count > 0:
                        pct = (count / total_failures * 100) if total_failures > 0 else 0
                        result += f"- **{classifier}:** {count:,} ({pct:.1f}%)\n"
                result += "\n"

            # WLAN breakdown
            if impact.get('wlans') or impact.get('wlan'):
                wlan_data = impact.get('wlans', impact.get('wlan', {}))
                result += "## Failures by WLAN/SSID\n\n"
                if isinstance(wlan_data, dict):
                    for wlan, count in sorted(wlan_data.items(), key=lambda x: x[1], reverse=True):
                        if count > 0:
                            result += f"- **{wlan}:** {count:,}\n"
                result += "\n"

            # Device type breakdown
            if impact.get('device_types') or impact.get('device_type'):
                device_data = impact.get('device_types', impact.get('device_type', {}))
                result += "## Failures by Device Type\n\n"
                if isinstance(device_data, dict):
                    for device, count in sorted(device_data.items(), key=lambda x: x[1], reverse=True):
                        if count > 0:
                            result += f"- **{device}:** {count:,}\n"
                result += "\n"

            # OS breakdown
            if impact.get('os') or impact.get('operating_systems'):
                os_data = impact.get('os', impact.get('operating_systems', {}))
                result += "## Failures by Operating System\n\n"
                if isinstance(os_data, dict):
                    for os_name, count in sorted(os_data.items(), key=lambda x: x[1], reverse=True):
                        if count > 0:
                            result += f"- **{os_name}:** {count:,}\n"
                result += "\n"

            # Band breakdown
            if impact.get('bands') or impact.get('band'):
                band_data = impact.get('bands', impact.get('band', {}))
                result += "## Failures by Band\n\n"
                if isinstance(band_data, dict):
                    for band, count in sorted(band_data.items(), key=lambda x: x[1], reverse=True):
                        if count > 0:
                            result += f"- **{band}:** {count:,}\n"
                result += "\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting SLE impact: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
async def get_sle_impacted_aps(
    site_id: str,
    metric: Literal["time-to-connect", "throughput", "coverage", "capacity", "roaming", "successful-connect", "ap-availability"],
    duration: int = 24,
    limit: int = 20,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get list of APs most impacted by SLE failures.

    Identifies which access points are contributing most to
    SLE metric failures, helping prioritize troubleshooting.

    Args:
        site_id: Site UUID
        metric: Which SLE metric to analyze
        duration: Hours of data (default 24)
        limit: Maximum APs to return (default 20)
        format: Response format

    Returns:
        List of APs ranked by failure impact

    Example:
        User: "Which APs have the worst coverage?"
        -> Use with metric="coverage"

        User: "What APs are causing connection issues?"
        -> Use with metric="time-to-connect"
    """
    try:
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "start": start_time,
            "end": end_time,
            "limit": limit
        }

        impacted = await mist_api_request(
            f"/sites/{site_id}/sle/site/{site_id}/metric/{metric}/impacted-aps",
            params=params
        )

        if format == "json":
            return truncate_response(json.dumps(impacted, indent=2))

        result = f"# Impacted APs: {metric}\n\n"
        result += f"**Period:** Last {duration} hour(s)\n\n"

        aps = impacted if isinstance(impacted, list) else impacted.get('results', impacted.get('aps', []))

        if not aps:
            result += "No impacted APs found for this metric and time period.\n"
            return result

        result += f"## Top {len(aps)} Impacted Access Points\n\n"
        result += "| Rank | AP Name | MAC | Failures | Total | Impact % |\n"
        result += "|------|---------|-----|----------|-------|----------|\n"

        for i, ap in enumerate(aps, 1):
            name = ap.get('name', ap.get('ap_name', 'Unknown'))
            mac = ap.get('mac', ap.get('ap_mac', 'N/A'))
            degraded = ap.get('degraded_count', ap.get('degraded', ap.get('failures', 0)))
            total = ap.get('total_count', ap.get('total', 0))

            if total > 0:
                impact_pct = (degraded / total) * 100
                result += f"| {i} | {name} | `{mac}` | {degraded:,} | {total:,} | {impact_pct:.1f}% |\n"
            else:
                result += f"| {i} | {name} | `{mac}` | {degraded:,} | {total:,} | N/A |\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting impacted APs: {str(e)}"

@mcp.tool(annotations=READ_ONLY)
async def get_sle_impacted_clients(
    site_id: str,
    metric: Literal["time-to-connect", "throughput", "coverage", "capacity", "roaming", "successful-connect", "ap-availability"],
    duration: int = 24,
    limit: int = 20,
    format: Literal["json", "markdown"] = "markdown"
) -> str:
    """
    Get list of clients most impacted by SLE failures.

    Identifies which client devices are experiencing the most
    issues with a specific SLE metric.

    Args:
        site_id: Site UUID
        metric: Which SLE metric to analyze
        duration: Hours of data (default 24)
        limit: Maximum clients to return (default 20)
        format: Response format

    Returns:
        List of clients ranked by failure impact

    Example:
        User: "Which users have the worst WiFi experience?"
        -> Use with metric="throughput"

        User: "Who is having roaming problems?"
        -> Use with metric="roaming"
    """
    try:
        end_time = int(time.time())
        start_time = end_time - (duration * 3600)

        params = {
            "start": start_time,
            "end": end_time,
            "limit": limit
        }

        impacted = await mist_api_request(
            f"/sites/{site_id}/sle/site/{site_id}/metric/{metric}/impacted-users",
            params=params
        )

        if format == "json":
            return truncate_response(json.dumps(impacted, indent=2))

        result = f"# Impacted Clients: {metric}\n\n"
        result += f"**Period:** Last {duration} hour(s)\n\n"

        clients = impacted if isinstance(impacted, list) else impacted.get('results', impacted.get('users', impacted.get('clients', [])))

        if not clients:
            result += "No impacted clients found for this metric and time period.\n"
            return result

        result += f"## Top {len(clients)} Impacted Clients\n\n"
        result += "| Rank | Client | MAC | Failures | Total | Impact % |\n"
        result += "|------|--------|-----|----------|-------|----------|\n"

        for i, client in enumerate(clients, 1):
            # Try various field names for client identifier
            name = client.get('name', client.get('hostname', client.get('username', 'Unknown')))
            mac = client.get('mac', client.get('client_mac', 'N/A'))
            degraded = client.get('degraded_count', client.get('degraded', client.get('failures', 0)))
            total = client.get('total_count', client.get('total', 0))

            if total > 0:
                impact_pct = (degraded / total) * 100
                result += f"| {i} | {name} | `{mac}` | {degraded:,} | {total:,} | {impact_pct:.1f}% |\n"
            else:
                result += f"| {i} | {name} | `{mac}` | {degraded:,} | {total:,} | N/A |\n"

        return truncate_response(result)

    except Exception as e:
        return f"Error getting impacted clients: {str(e)}"
