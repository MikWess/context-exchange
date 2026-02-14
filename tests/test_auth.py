"""
Tests for auth endpoints: register, login, get profile.
"""
import pytest
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_register_creates_user_and_agent(client):
    """Registration creates a user + agent and returns an API key."""
    resp = await client.post("/auth/register", json={
        "email": "test@example.com",
        "name": "Test User",
        "agent_name": "Test Agent",
        "framework": "openclaw",
    })
    assert resp.status_code == 200
    data = resp.json()

    # Should return all the IDs and a key
    assert "user_id" in data
    assert "agent_id" in data
    assert "api_key" in data
    # Key should have the cex_ prefix
    assert data["api_key"].startswith("cex_")


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client):
    """Can't register twice with the same email."""
    payload = {
        "email": "dupe@example.com",
        "name": "First",
        "agent_name": "Agent 1",
    }
    resp1 = await client.post("/auth/register", json=payload)
    assert resp1.status_code == 200

    resp2 = await client.post("/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_jwt(client, registered_agent):
    """Login with a registered email returns a JWT."""
    resp = await client.post("/auth/login", json={"email": "mikey@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["name"] == "Mikey"


@pytest.mark.asyncio
async def test_login_unknown_email_fails(client):
    """Login with unregistered email returns 404."""
    resp = await client.post("/auth/login", json={"email": "nobody@test.com"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_me_with_valid_key(client, registered_agent):
    """GET /auth/me returns agent profile when key is valid."""
    resp = await client.get(
        "/auth/me",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Mikey's Agent"
    assert data["framework"] == "openclaw"


@pytest.mark.asyncio
async def test_get_me_with_bad_key_fails(client):
    """GET /auth/me rejects invalid API keys."""
    resp = await client.get(
        "/auth/me",
        headers=auth_header("cex_definitely_not_a_real_key"),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_no_prefix_fails(client):
    """GET /auth/me rejects keys without the cex_ prefix."""
    resp = await client.get(
        "/auth/me",
        headers=auth_header("not_even_prefixed"),
    )
    assert resp.status_code == 401
