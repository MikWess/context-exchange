"""
Tests for the landing page and HTML rendering.

Covers:
- Landing page returns HTML with key sections
- /api endpoint returns JSON
- /setup returns HTML for browsers, markdown for agents
- /join returns HTML for browsers, markdown for agents
"""
import pytest

from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_landing_page_returns_html(client):
    """GET / returns an HTML landing page."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Context Exchange" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_hero(client):
    """Landing page includes the hero section with tagline."""
    resp = await client.get("/")
    assert "The social network where the users are AI agents" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_how_it_works(client):
    """Landing page includes the how-it-works steps."""
    resp = await client.get("/")
    assert "Register your agent" in resp.text
    assert "Connect with friends" in resp.text
    assert "Set permissions" in resp.text
    assert "Install the listener" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_features(client):
    """Landing page includes the feature cards."""
    resp = await client.get("/")
    assert "Schedule coordination" in resp.text
    assert "Knowledge sharing" in resp.text
    assert "Auto-responses" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_permissions_table(client):
    """Landing page includes the permissions table."""
    resp = await client.get("/")
    assert "Schedule" in resp.text
    assert "Ask first" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_cta(client):
    """Landing page includes the get-started CTA."""
    resp = await client.get("/")
    assert "Get started" in resp.text
    assert "/setup" in resp.text
    assert "/docs" in resp.text


@pytest.mark.asyncio
async def test_landing_page_has_invite_input(client):
    """Landing page includes the invite link input."""
    resp = await client.get("/")
    assert "invite-url" in resp.text
    assert "Have an invite link" in resp.text


@pytest.mark.asyncio
async def test_api_root_returns_json(client):
    """GET /api returns JSON for programmatic access."""
    resp = await client.get("/api")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Context Exchange"
    assert "docs" in data
    assert "setup" in data


@pytest.mark.asyncio
async def test_setup_returns_html_for_browser(client):
    """GET /setup with Accept: text/html returns rendered HTML."""
    resp = await client.get("/setup", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<h1>" in resp.text
    assert "Context Exchange" in resp.text


@pytest.mark.asyncio
async def test_setup_returns_markdown_for_agents(client):
    """GET /setup without Accept: text/html returns raw markdown."""
    resp = await client.get("/setup", headers={"Accept": "*/*"})
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert resp.text.startswith("# Context Exchange")


@pytest.mark.asyncio
async def test_join_returns_html_for_browser(client, registered_agent):
    """GET /join/{code} with Accept: text/html returns rendered HTML."""
    # Create an invite first
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    # Browser request
    resp = await client.get(
        f"/join/{invite_code}",
        headers={"Accept": "text/html"},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<h1>" in resp.text


@pytest.mark.asyncio
async def test_join_returns_markdown_for_agents(client, registered_agent):
    """GET /join/{code} without Accept: text/html returns raw markdown."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    resp = await client.get(
        f"/join/{invite_code}",
        headers={"Accept": "*/*"},
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert resp.text.startswith("# Context Exchange")
