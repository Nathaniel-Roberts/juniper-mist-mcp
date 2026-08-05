# Juniper Mist MCP Server - Development Guide

## What This Is

An MCP server exposing 50 read-only Juniper Mist API tools, built on the
MCP Python SDK v2 (`MCPServer`). Installed by consumers via
`uvx --from git+https://github.com/Nathaniel-Roberts/juniper-mist-mcp` —
every push to main is what users get on their next fresh install.

## Layout

```
src/juniper_mist_mcp/
  __init__.py     re-exports everything; main() entry point
  api.py          config/env, shared httpx client, MistAPIError, mist_api_request()
  server.py       MCPServer instance (mcp) and the READ_ONLY annotation
  formatting.py   markdown helpers, truncate_response()
  tools/
    orgs.py        organizations, sites, org summary
    devices.py     inventory, stats, config, events, search, switch ports
    wireless.py    WLANs, RF stats, radio status, rogues, insights
    monitoring.py  alarms, Marvis actions, WAN stats
    clients.py     client stats/lookup, session history, client events
    nac.py         NAC events, rules, tags, RADIUS, IdPs, portal logs
    sle.py         SLE metrics/summary/histogram/impact
    location.py    maps, zones, BLE assets, location history
tests/            pytest suite; HTTP mocked via httpx.MockTransport
```

## Commands

```bash
uv run --group dev pytest          # run tests (no Mist account needed)
uv run --group dev ruff check .    # lint (CI enforces both)
```

Don't run the server directly in a terminal (it waits on stdio). The stdio
test in `tests/test_stdio.py` covers the real server startup path.

## Conventions for Tools

Every tool follows the same pattern — copy an existing one in the right
`tools/` module:

- `@mcp.tool(annotations=READ_ONLY, structured_output=False)` on an async
  function. All Phase 1 tools are read-only; do not add a write tool
  without the confirmation pattern (see Phase 2 below).
  `structured_output=False` is required — it lets tools return
  `CallToolResult` per call without the SDK generating an output schema.
- Parameters validated with `Literal[...]` types where the API accepts an
  enum; `format: Literal["json", "markdown"] = "markdown"` on everything.
- Call the API only through `mist_api_request()` (shared client, auth,
  friendly errors, one automatic 429 retry). It raises `MistAPIError`.
- Wrap the body in try/except and return `f"Error <doing X>: {e}"` —
  tools return error strings rather than raising.
- Markdown returns go through `truncate_response()` (25k char cap).
  `format="json"` returns go through `json_tool_result(data)`, which
  emits truncated JSON text plus `structuredContent` (omitted when the
  payload exceeds the cap — never bypass that).
- Render epoch timestamps with `format_timestamp()` (server-local time
  with the zone visible); compact tables may keep short formats but must
  carry a `local_timezone_name()` note.
- org_id parameters are `Optional[str] = None` resolved via
  `resolve_org_id()` (falls back to MIST_ORG_ID). site_id parameters
  accept names as well as UUIDs — resolve with `await resolve_site_id()`
  as the first statement in the try block. Site lists are cached 60s via
  `get_org_sites()`.
- Docstring must include: summary, Args, Returns, an Example block with
  user phrasing, and Error Handling notes. The docstring is the tool
  description the model sees — write it for tool selection.
- Add a test in `tests/test_server.py` using the `mock_api` fixture with
  a realistic response payload.

## Mist API Gotchas (learned the hard way)

- Session search results use `ap` and `connect`/`disconnect`, not
  `ap_mac`/`connect_time`.
- Map objects do NOT embed AP placements; placed APs carry `map_id`
  (plus x/y/height) on their device objects. Use `_get_map_aps()`.
- Mist returns 403 (not 404) for IDs outside your org.
- Search-style endpoints wrap results as `{"results": [...]}`; plain
  list endpoints return bare arrays. Handle both.
- Rate limit is 5,000 requests/hour per token.
- `list_organizations` uses `/self` privileges, not `/orgs`.
- `GET /orgs/{org_id}/stats/devices` defaults `type` to `ap` server-side;
  always send type explicitly (see get_org_device_status).

## Phase 2: Write Operations (not started)

If adding write tools: no `READ_ONLY` annotation, require a
`confirm: bool = False` parameter that previews the change unless True,
start with low-risk operations (names, labels, descriptions), and test
against a non-production org. Keep them in a separate `tools/` module so
they're easy to audit.

## Releasing

There is no release process — pushing to main publishes. Before pushing:
tests and ruff green, and if tool schemas changed, sanity-check with a
fresh install (`uv cache clean juniper-mist-mcp` in a consuming project).
