import os

# Must be set before the package is imported; the module refuses to load without it
os.environ.setdefault("MIST_API_TOKEN", "test-token")

import httpx
import pytest

import juniper_mist_mcp as jm
from juniper_mist_mcp import api as jm_api


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_api():
    """
    Install an httpx.MockTransport as the shared HTTP client.

    Usage:
        def handler(request): return httpx.Response(200, json=...)
        mock_api(handler)
    """
    def install(handler):
        jm_api._http_client = httpx.AsyncClient(
            base_url=jm.MIST_API_BASE_URL,
            headers={
                "Authorization": f"Token {os.environ['MIST_API_TOKEN']}",
                "Content-Type": "application/json",
            },
            transport=httpx.MockTransport(handler),
        )
        return jm_api._http_client

    yield install
    jm_api._http_client = None
    jm_api._sites_cache.clear()
