"""
Tests for the onboarding endpoints.

/join/{invite_code} — returns setup instructions with invite code baked in
/setup             — returns generic setup instructions (no invite)
"""
import pytest
from tests.conftest import auth_header


# --- GET /setup (no invite) ---

@pytest.mark.asyncio
async def test_setup_returns_markdown(client):
    """GET /setup returns plain text markdown with setup instructions."""
    resp = await client.get("/setup")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    body = resp.text
    # Should contain the key sections
    assert "BotJoin" in body
    assert "Step 1" in body
    assert "Step 2" in body
    assert "/auth/register" in body
    assert "/auth/verify" in body
    # Should contain the test server URL
    assert "http://test" in body
    # Should NOT contain invite-specific content
    assert "Step 4: Accept the invite" not in body


# --- GET /join/{invite_code} ---

@pytest.mark.asyncio
async def test_join_with_valid_invite(client, registered_agent):
    """GET /join/{code} returns instructions with invite code + inviter name."""
    # Create an invite from the registered agent
    key = registered_agent["api_key"]
    invite_resp = await client.post("/connections/invite", headers=auth_header(key))
    assert invite_resp.status_code == 200
    invite_code = invite_resp.json()["invite_code"]

    # Fetch the magic link
    resp = await client.get(f"/join/{invite_code}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    body = resp.text
    # Should contain the invite code in the curl command
    assert invite_code in body
    # Should contain the inviter's agent name
    # Now shows the human's name, not the agent's name
    assert "Mikey" in body
    # Should contain the invite acceptance step
    assert "Step 4: Accept the invite" in body
    # Should contain the server URL
    assert "http://test" in body


@pytest.mark.asyncio
async def test_join_with_invalid_invite(client):
    """GET /join/{bad_code} returns 404."""
    resp = await client.get("/join/nonexistent_code_123")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_join_with_used_invite(client, registered_agent, second_agent):
    """GET /join/{code} returns 400 if the invite was already used."""
    # Create invite from first agent
    key_a = registered_agent["api_key"]
    invite_resp = await client.post("/connections/invite", headers=auth_header(key_a))
    invite_code = invite_resp.json()["invite_code"]

    # Accept it with the second agent (marks it as used)
    key_b = second_agent["api_key"]
    await client.post(
        "/connections/accept",
        json={"invite_code": invite_code},
        headers=auth_header(key_b),
    )

    # Now try to fetch the magic link — should fail
    resp = await client.get(f"/join/{invite_code}")
    assert resp.status_code == 400
