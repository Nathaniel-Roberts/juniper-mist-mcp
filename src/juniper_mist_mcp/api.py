"""Configuration, HTTP client, and Mist API request helper."""

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

# Load environment variables from .env file in current directory
load_dotenv()

# Configuration
MIST_API_TOKEN = os.getenv("MIST_API_TOKEN")
MIST_API_BASE_URL = os.getenv("MIST_API_BASE_URL", "https://api.mist.com/api/v1")
MIST_ORG_ID = os.getenv("MIST_ORG_ID")  # Optional default org

if not MIST_API_TOKEN:
    raise ValueError(
        "MIST_API_TOKEN not found. Set it by either:\n"
        "1. Adding MIST_API_TOKEN=your_token to your .env file\n"
        "2. Setting MIST_API_TOKEN in your mcp.json env section\n"
        "Get your token from: https://manage.mist.com > Organization > Settings > API Tokens"
    )

# 429 responses asking for a wait up to this long are retried once
# automatically; longer waits are surfaced to the caller instead.
MAX_RETRY_AFTER_SECONDS = 30


class MistAPIError(Exception):
    """A Mist API request failed; the message is safe to show the user."""


_http_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared HTTP client, creating it on first use."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=MIST_API_BASE_URL,
            headers={
                "Authorization": f"Token {MIST_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    return _http_client


@asynccontextmanager
async def _lifespan(server):
    """Close the shared HTTP client when the server shuts down."""
    global _http_client
    try:
        yield None
    finally:
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None


async def mist_api_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[dict] = None,
    json_data: Optional[dict] = None
) -> Any:
    """
    Make an authenticated request to the Mist API.

    Args:
        endpoint: API endpoint (e.g., "/orgs" or "/orgs/{org_id}/sites")
        method: HTTP method (GET, POST, PUT, DELETE)
        params: Query parameters
        json_data: JSON body for POST/PUT requests

    Returns:
        Parsed JSON response

    Raises:
        MistAPIError with a user-friendly message
    """
    client = _get_client()

    for attempt in (1, 2):
        try:
            response = await client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json_data
            )
        except httpx.TimeoutException:
            raise MistAPIError(
                "Request timed out after 30 seconds. "
                "Please check your network connection and try again."
            )
        except httpx.NetworkError as e:
            raise MistAPIError(
                f"Network error: Unable to connect to Mist API at {MIST_API_BASE_URL}. "
                f"Details: {str(e)}"
            )

        if response.status_code == 429:
            try:
                retry_after = int(response.headers.get("Retry-After", "60"))
            except ValueError:
                retry_after = 60
            if attempt == 1 and retry_after <= MAX_RETRY_AFTER_SECONDS:
                await asyncio.sleep(retry_after)
                continue
            raise MistAPIError(
                f"Rate limit exceeded (5,000 requests/hour). "
                f"Please wait {retry_after} seconds before retrying."
            )

        if response.status_code == 401:
            raise MistAPIError(
                "Authentication failed. Please check your MIST_API_TOKEN. "
                "You can generate a new token at: "
                "https://manage.mist.com > Organization > Settings > API Tokens"
            )

        if response.status_code == 403:
            raise MistAPIError(
                "Access forbidden. The ID may not exist in your organization (Mist returns "
                "403 rather than 404 for IDs outside your org), or your API token may not "
                "have permission for this resource."
            )

        if response.status_code == 404:
            raise MistAPIError(
                "Resource not found. Please verify the organization/site/device ID. "
                "Use list_organizations to see available organizations."
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise MistAPIError(
                f"Mist API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as e:
            raise MistAPIError(f"Invalid response from Mist API: {str(e)}")


# ============================================================================
# Org / site resolution
# ============================================================================

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

# Site lists are near-static; cache briefly to keep name resolution from
# burning rate limit when an agent makes many site-scoped calls.
SITE_CACHE_TTL_SECONDS = 60.0
_sites_cache: dict[str, tuple[float, list[dict]]] = {}


def resolve_org_id(org_id: Optional[str] = None) -> str:
    """Return org_id, falling back to the MIST_ORG_ID environment variable."""
    org = org_id or os.getenv("MIST_ORG_ID")
    if not org:
        raise MistAPIError(
            "No org_id provided and MIST_ORG_ID is not set. Pass org_id explicitly "
            "(use list_organizations to find it) or set MIST_ORG_ID in the environment."
        )
    return org


async def get_org_sites(org_id: str) -> list[dict]:
    """Get the org's sites, cached for SITE_CACHE_TTL_SECONDS."""
    cached = _sites_cache.get(org_id)
    if cached and time.monotonic() - cached[0] < SITE_CACHE_TTL_SECONDS:
        return cached[1]
    sites = await mist_api_request(f"/orgs/{org_id}/sites")
    _sites_cache[org_id] = (time.monotonic(), sites)
    return sites


async def resolve_site_id(site_id: str, org_id: Optional[str] = None) -> str:
    """
    Accept a site UUID or a site name and return the UUID.

    Names are matched against the org's site list: exact match first
    (case-insensitive), then unique substring match. Ambiguous or unknown
    names raise MistAPIError listing the candidates.
    """
    site = (site_id or "").strip()
    if _UUID_RE.fullmatch(site):
        return site

    org = resolve_org_id(org_id)
    sites = await get_org_sites(org)
    wanted = site.lower()

    exact = [s for s in sites if s.get("name", "").lower() == wanted]
    if len(exact) == 1:
        return exact[0]["id"]

    partial = [s for s in sites if wanted in s.get("name", "").lower()]
    if len(partial) == 1:
        return partial[0]["id"]
    if len(partial) > 1:
        names = ", ".join(s.get("name", "?") for s in partial)
        raise MistAPIError(f"Site name '{site_id}' is ambiguous; matches: {names}")

    names = ", ".join(s.get("name", "?") for s in sites[:20])
    raise MistAPIError(f"No site named '{site_id}'. Sites in this org: {names}")
