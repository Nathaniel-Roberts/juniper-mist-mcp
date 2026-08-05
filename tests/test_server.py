"""Tests for the Juniper Mist MCP server.

All HTTP traffic goes through an httpx.MockTransport injected as the shared
client, so tools are exercised through their real code paths.
"""

import time

import httpx
import pytest

import juniper_mist_mcp as jm

pytestmark = pytest.mark.anyio

MAP_ID = "1721723f-3c2b-4da3-ae5b-60a3d1267ab3"


# ----------------------------------------------------------------------------
# Tool registration
# ----------------------------------------------------------------------------

async def test_all_tools_marked_read_only():
    tools = await jm.mcp.list_tools()
    assert len(tools) >= 47
    missing = [t.name for t in tools if not (t.annotations and t.annotations.read_only_hint)]
    assert missing == []


# ----------------------------------------------------------------------------
# HTTP client behaviour
# ----------------------------------------------------------------------------

async def test_base_url_and_auth_header(mock_api):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"privileges": []})

    mock_api(handler)
    await jm.mist_api_request("/self")
    assert seen["url"] == "https://api.mist.com/api/v1/self"
    assert seen["auth"] == "Token test-token"


async def test_429_retries_once_when_wait_is_short(mock_api):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    mock_api(handler)
    assert await jm.mist_api_request("/self") == {"ok": True}
    assert len(attempts) == 2


async def test_429_not_retried_when_wait_is_long(mock_api):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(429, headers={"Retry-After": "120"})

    mock_api(handler)
    with pytest.raises(jm.MistAPIError, match="Rate limit"):
        await jm.mist_api_request("/self")
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "status,match",
    [
        (401, "Authentication failed"),
        (403, "Access forbidden"),
        (404, "Resource not found"),
        (500, "HTTP 500"),
    ],
)
async def test_http_errors_become_friendly_messages(mock_api, status, match):
    mock_api(lambda request: httpx.Response(status, text="boom"))
    with pytest.raises(jm.MistAPIError, match=match):
        await jm.mist_api_request("/self")


async def test_invalid_json_is_reported(mock_api):
    mock_api(lambda request: httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(jm.MistAPIError, match="Invalid response"):
        await jm.mist_api_request("/self")


# ----------------------------------------------------------------------------
# Response formatting
# ----------------------------------------------------------------------------

async def test_json_format_is_truncated(mock_api):
    big = [{"mac": f"aa:bb:cc:dd:ee:{i:02x}", "notes": "x" * 500} for i in range(200)]
    mock_api(lambda request: httpx.Response(200, json=big))
    out = await jm.get_device_stats(org_id="o", site_id="s", format="json")
    text = out.content[0].text
    assert len(text) < 26000
    assert "truncated" in text
    # oversized payloads must not sneak through as structured content
    assert out.structured_content is None


async def test_json_format_returns_structured_content(mock_api):
    data = [{"mac": "aa:bb:cc:dd:ee:01", "status": "connected"}]
    mock_api(lambda request: httpx.Response(200, json=data))
    out = await jm.get_device_stats(org_id="o", site_id="s", format="json")
    # lists are wrapped so structuredContent is always an object
    assert out.structured_content == {"results": data}
    assert "aa:bb:cc:dd:ee:01" in out.content[0].text


async def test_structured_content_reaches_mcp_layer(mock_api):
    data = {"privileges": [{"scope": "org", "org_id": "o1", "name": "Org", "role": "admin"}]}
    mock_api(lambda request: httpx.Response(200, json=data))
    result = await jm.mcp.call_tool("list_organizations", {"format": "json"})
    assert result.is_error is False
    assert result.structured_content == {
        "results": [{"id": "o1", "name": "Org", "role": "admin"}]
    }


def test_format_timestamp_shows_timezone():
    out = jm.format_timestamp(1754358000)
    assert out.count(":") == 2
    tz = out.rsplit(" ", 1)[1]
    assert tz and not tz[0].isdigit()  # e.g. AEST, not a bare time


def test_truncate_response_passthrough():
    assert jm.truncate_response("short") == "short"
    long = "x" * 30000
    out = jm.truncate_response(long)
    assert len(out) < 26000 and "truncated" in out


# ----------------------------------------------------------------------------
# Tool behaviour against realistic API shapes
# ----------------------------------------------------------------------------

def _map_and_devices_handler(request):
    path = request.url.path
    if path.endswith(f"/maps/{MAP_ID}"):
        # Real Mist map objects do NOT embed an 'aps' array
        return httpx.Response(200, json={
            "id": MAP_ID, "name": "L Block 1st Floor",
            "width": 40, "height": 30, "ppm": 20,
        })
    if path.endswith("/devices"):
        return httpx.Response(200, json=[
            {"mac": "aa:aa:aa:aa:aa:01", "name": "Lib-NorthEast", "map_id": MAP_ID,
             "x": 5.0, "y": 3.2, "height": 2.7},
            {"mac": "aa:aa:aa:aa:aa:02", "name": "Lib-West", "map_id": MAP_ID,
             "x": None, "y": None},
            {"mac": "bb:bb:bb:bb:bb:03", "name": "OtherFloor-AP", "map_id": "another-map"},
            {"mac": "cc:cc:cc:cc:cc:04", "name": "Unplaced-AP"},
        ])
    if "clients/sessions/search" in path:
        now = int(time.time())
        # Real session results use 'ap' and 'connect'
        return httpx.Response(200, json={"results": [
            {"mac": "de:ad:be:ef:00:01", "ap": "AA:AA:AA:AA:AA:01",
             "connect": now - 600, "hostname": "on-floor-laptop"},
            {"mac": "de:ad:be:ef:00:02", "ap": "bb:bb:bb:bb:bb:03",
             "connect": now - 100, "hostname": "wrong-floor"},
        ]})
    return httpx.Response(500, text=f"unexpected path {path}")


async def test_get_map_info_lists_placed_aps(mock_api):
    mock_api(_map_and_devices_handler)
    out = await jm.get_map_info(site_id="s", map_id=MAP_ID)
    assert "Access Points (2)" in out
    assert "Lib-NorthEast" in out and "Lib-West" in out
    assert "OtherFloor-AP" not in out and "Unplaced-AP" not in out


async def test_get_map_info_json_includes_placed_aps(mock_api):
    mock_api(_map_and_devices_handler)
    out = await jm.get_map_info(site_id="s", map_id=MAP_ID, format="json")
    data = out.structured_content
    assert [ap["name"] for ap in data["aps"]] == ["Lib-NorthEast", "Lib-West"]


async def test_search_clients_by_location_matches_real_fields(mock_api):
    mock_api(_map_and_devices_handler)
    out = await jm.search_clients_by_location(site_id="s", map_id=MAP_ID)
    assert "on-floor-laptop" in out
    assert "wrong-floor" not in out


async def test_search_clients_by_location_enriches_hostnames(mock_api):
    now = int(time.time())

    def handler(request):
        path = request.url.path
        if path.endswith(f"/maps/{MAP_ID}"):
            return httpx.Response(200, json={"id": MAP_ID, "name": "Floor"})
        if path.endswith("/devices"):
            return httpx.Response(200, json=[
                {"mac": "aa:aa:aa:aa:aa:01", "name": "AP-One", "map_id": MAP_ID}])
        if "clients/sessions/search" in path:
            # sessions without hostnames, as the live API often returns
            return httpx.Response(200, json={"results": [
                {"mac": "de:ad:be:ef:00:01", "ap": "aa:aa:aa:aa:aa:01", "connect": now - 60}]})
        if path.endswith("/stats/clients"):
            return httpx.Response(200, json=[
                {"mac": "DE:AD:BE:EF:00:01", "hostname": "KristyHcBookAir"}])
        return httpx.Response(500, text=f"unexpected path {path}")

    mock_api(handler)
    out = await jm.search_clients_by_location(site_id="s", map_id=MAP_ID)
    assert "KristyHcBookAir" in out


async def test_client_location_history_builds_timeline(mock_api):
    now = int(time.time())

    def handler(request):
        path = request.url.path
        if "clients/sessions/search" in path:
            return httpx.Response(200, json={"results": [
                {"mac": "de:ad:be:ef:00:01", "ap": "aa:aa:aa:aa:aa:01",
                 "connect": now - 7200, "disconnect": now - 3600},
                {"mac": "de:ad:be:ef:00:01", "ap": "aa:aa:aa:aa:aa:02",
                 "connect": now - 3600, "disconnect": now - 60},
            ]})
        if path.endswith("/stats/devices"):
            return httpx.Response(200, json=[
                {"mac": "aa:aa:aa:aa:aa:01", "name": "AP-One"},
                {"mac": "aa:aa:aa:aa:aa:02", "name": "AP-Two"},
            ])
        if path.endswith("/sites/s"):
            return httpx.Response(200, json={"org_id": "org-1"})
        if "clients/search" in path:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(500, text=f"unexpected path {path}")

    mock_api(handler)
    out = await jm.get_client_location_history(site_id="s", client_mac="DE:AD:BE:EF:00:01")
    assert "AP-One" in out and "AP-Two" in out
    # moved between two APs -> two timeline rows
    assert out.count("| ") >= 2


async def test_list_organizations_reads_self_privileges(mock_api):
    def handler(request):
        assert request.url.path.endswith("/self")
        return httpx.Response(200, json={"privileges": [
            {"scope": "org", "org_id": "org-1", "name": "Melos Education", "role": "admin"},
            {"scope": "site", "site_id": "ignored"},
        ]})

    mock_api(handler)
    out = await jm.list_organizations()
    assert "Melos Education" in out and "org-1" in out and "admin" in out
    assert "ignored" not in out


async def test_tool_returns_error_string_not_exception(mock_api):
    mock_api(lambda request: httpx.Response(404))
    out = await jm.list_sites(org_id="nope")
    assert out.startswith("Error listing sites:")
    assert "Resource not found" in out
