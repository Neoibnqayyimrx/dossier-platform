"""CORS preflight tests (P11).

WHY these exist as their own file: the missing CORS middleware was a real
bug that all 198 backend tests sailed past, because httpx -- unlike a
browser -- does not enforce the same-origin policy, so every existing API
test kept passing while the API was in fact unreachable from the frontend.
It was only caught by driving a real browser at it. These tests encode the
one thing httpx CAN check: that the preflight response carries the right
headers.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app

ALLOWED_ORIGIN = "http://localhost:3000"


async def _preflight(origin: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            "/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )


async def test_preflight_from_the_configured_frontend_origin_is_allowed():
    response = await _preflight(ALLOWED_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


async def test_preflight_from_an_unlisted_origin_is_not_granted():
    """A bearer-token API must not hand its CORS grant to arbitrary sites --
    an unlisted origin gets no allow-origin header back, so the browser
    blocks the real request."""
    response = await _preflight("https://evil.example.com")
    assert "access-control-allow-origin" not in response.headers


def test_allowed_origins_are_an_explicit_list_never_a_wildcard():
    origins = get_settings().cors_allow_origin_list
    assert origins, "at least one frontend origin must be configured"
    assert "*" not in origins, (
        "a wildcard origin on a credentialed API lets any site a logged-in "
        "user visits call it with their token"
    )
