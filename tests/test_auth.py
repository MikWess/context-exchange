"""
Tests for auth endpoints: register, verify, login, get profile.
"""
import pytest
from tests.conftest import auth_header, _register_and_verify


@pytest.mark.asyncio
async def test_register_returns_pending(client):
    """POST /auth/register returns a pending response with verification code in dev mode."""
    resp = await client.post("/auth/register", json={
        "email": "test@example.com",
        "name": "Test User",
    })
    assert resp.status_code == 200
    data = resp.json()

    # Should return pending status and user ID
    assert data["pending"] is True
    assert "user_id" in data
    # Dev mode: code is in the message
    assert "code is:" in data["message"]


@pytest.mark.asyncio
async def test_verify_creates_agent_with_api_key(client):
    """Full register → verify flow creates a user + agent and returns an API key."""
    data = await _register_and_verify(
        client, "test@example.com", "Test User", "Test Agent", "openclaw",
    )

    # Should return all the IDs and a key
    assert "user_id" in data
    assert "agent_id" in data
    assert "api_key" in data
    # Key should have the cex_ prefix
    assert data["api_key"].startswith("cex_")


@pytest.mark.asyncio
async def test_verify_with_wrong_code_fails(client):
    """Verification with an incorrect code is rejected."""
    resp = await client.post("/auth/register", json={
        "email": "wrongcode@test.com",
        "name": "Wrong Code User",
    })
    assert resp.status_code == 200

    resp = await client.post("/auth/verify", json={
        "email": "wrongcode@test.com",
        "code": "000000",
        "agent_name": "Agent",
    })
    assert resp.status_code == 400
    assert "Invalid verification code" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_duplicate_verified_email_fails(client):
    """Can't register again after email is already verified."""
    # Register and verify first
    await _register_and_verify(
        client, "dupe@example.com", "First", "Agent 1", "openclaw",
    )

    # Try to register same email again — should fail
    resp = await client.post("/auth/register", json={
        "email": "dupe@example.com",
        "name": "Second",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_unverified_email_allows_re_register(client):
    """Can re-register with same email if it was never verified (gets new code)."""
    # Register but don't verify
    resp1 = await client.post("/auth/register", json={
        "email": "lazy@example.com",
        "name": "Lazy User",
    })
    assert resp1.status_code == 200

    # Register again with same email — should succeed (new code)
    resp2 = await client.post("/auth/register", json={
        "email": "lazy@example.com",
        "name": "Lazy User v2",
    })
    assert resp2.status_code == 200
    assert "code is:" in resp2.json()["message"]


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
