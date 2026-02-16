"""
Tests for auth endpoints: register, verify, login, recover, agent management.
"""
import pytest
from tests.conftest import auth_header, _register_and_verify, _login_and_verify


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
async def test_verify_without_agent_name_creates_human_only(client):
    """Verify with no agent_name creates a verified human but no agent."""
    # Register
    resp = await client.post("/auth/register", json={
        "email": "humanonly@test.com",
        "name": "Human Only",
    })
    code = resp.json()["message"].split("code is: ")[1].split(".")[0]

    # Verify without agent_name
    resp = await client.post("/auth/verify", json={
        "email": "humanonly@test.com",
        "code": code,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert data["agent_id"] is None  # No agent created
    assert data["api_key"] is None   # No API key
    assert "add an agent later" in data["message"]

    # The human can still log in and get a JWT
    resp = await client.post("/auth/login", json={"email": "humanonly@test.com"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_sends_code_then_verify_returns_jwt(client, registered_agent):
    """Login is 2-step: email → code, then code → JWT."""
    # Step 1: Login sends a verification code
    resp = await client.post("/auth/login", json={"email": "mikey@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "code is:" in data["message"]  # Dev mode includes the code

    # Extract the code from dev mode message
    code = data["message"].split("code is: ")[1].split(".")[0]

    # Step 2: Verify with the code → get JWT
    verify_resp = await client.post("/auth/login/verify", json={
        "email": "mikey@test.com",
        "code": code,
    })
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert "token" in verify_data
    assert verify_data["name"] == "Mikey"


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


# --- Recover flow ---


@pytest.mark.asyncio
async def test_recover_sends_code(client, registered_agent):
    """POST /auth/recover sends a verification code to a verified email."""
    resp = await client.post("/auth/recover", json={"email": "mikey@test.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "code is:" in data["message"]  # Dev mode includes the code


@pytest.mark.asyncio
async def test_recover_for_unregistered_email_fails(client):
    """POST /auth/recover with unknown email returns 404."""
    resp = await client.post("/auth/recover", json={"email": "nobody@test.com"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recover_verify_regenerates_key(client, registered_agent):
    """Recover verify regenerates the agent's key — old key dies, new key works."""
    old_key = registered_agent["api_key"]

    # Request a recover code
    resp = await client.post("/auth/recover", json={"email": "mikey@test.com"})
    code = resp.json()["message"].split("code is: ")[1].split(".")[0]

    # Verify with agent_name → regenerate key
    resp = await client.post("/auth/recover/verify", json={
        "email": "mikey@test.com",
        "code": code,
        "agent_name": "Mikey's Agent",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "Mikey's Agent"
    assert data["api_key"].startswith("cex_")
    assert data["created"] is False  # Regenerated, not created
    new_key = data["api_key"]

    # Old key should be dead
    resp = await client.get("/auth/me", headers=auth_header(old_key))
    assert resp.status_code == 401

    # New key should work
    resp = await client.get("/auth/me", headers=auth_header(new_key))
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mikey's Agent"


@pytest.mark.asyncio
async def test_recover_verify_creates_agent_if_not_found(client, registered_agent):
    """Recover verify with unknown agent_name creates a new agent."""
    # Request a recover code
    resp = await client.post("/auth/recover", json={"email": "mikey@test.com"})
    code = resp.json()["message"].split("code is: ")[1].split(".")[0]

    # Verify with a new agent name → should create it
    resp = await client.post("/auth/recover/verify", json={
        "email": "mikey@test.com",
        "code": code,
        "agent_name": "Mikey's Claude Code",
        "framework": "claude",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "Mikey's Claude Code"
    assert data["created"] is True  # Created, not regenerated
    assert data["api_key"].startswith("cex_")

    # The new agent should work
    resp = await client.get("/auth/me", headers=auth_header(data["api_key"]))
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mikey's Claude Code"


@pytest.mark.asyncio
async def test_recover_verify_wrong_code_fails(client, registered_agent):
    """Recover verify with bad code is rejected."""
    # Request a recover code
    await client.post("/auth/recover", json={"email": "mikey@test.com"})

    # Verify with wrong code
    resp = await client.post("/auth/recover/verify", json={
        "email": "mikey@test.com",
        "code": "000000",
        "agent_name": "Mikey's Agent",
    })
    assert resp.status_code == 400
    assert "Invalid verification code" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_recover_verify_primary_agent(client, registered_agent):
    """Recover verify with no agent_name/id regenerates the primary agent's key."""
    old_key = registered_agent["api_key"]

    # Request a recover code
    resp = await client.post("/auth/recover", json={"email": "mikey@test.com"})
    code = resp.json()["message"].split("code is: ")[1].split(".")[0]

    # Verify with no agent specified → regenerates primary
    resp = await client.post("/auth/recover/verify", json={
        "email": "mikey@test.com",
        "code": code,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "Mikey's Agent"
    assert data["created"] is False
    new_key = data["api_key"]

    # Old key dead, new key works
    assert (await client.get("/auth/me", headers=auth_header(old_key))).status_code == 401
    assert (await client.get("/auth/me", headers=auth_header(new_key))).status_code == 200


# --- JWT auth for agent management ---


@pytest.mark.asyncio
async def test_jwt_can_list_agents(client, registered_agent):
    """GET /auth/agents accepts JWT auth and returns agent list."""
    login_data = await _login_and_verify(client, "mikey@test.com")
    jwt_token = login_data["token"]

    resp = await client.get(
        "/auth/agents",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "Mikey's Agent"


@pytest.mark.asyncio
async def test_jwt_can_add_agent(client, registered_agent):
    """POST /auth/agents accepts JWT auth and creates a new agent."""
    login_data = await _login_and_verify(client, "mikey@test.com")
    jwt_token = login_data["token"]

    resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's GPT", "framework": "gpt"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_id" in data
    assert data["api_key"].startswith("cex_")

    # Verify the new agent exists
    resp = await client.get(
        "/auth/agents",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    agents = resp.json()
    assert len(agents) == 2
    names = {a["name"] for a in agents}
    assert "Mikey's GPT" in names


@pytest.mark.asyncio
async def test_login_verify_wrong_code_fails(client, registered_agent):
    """POST /auth/login/verify with bad code is rejected."""
    # Request login code
    await client.post("/auth/login", json={"email": "mikey@test.com"})

    # Verify with wrong code
    resp = await client.post("/auth/login/verify", json={
        "email": "mikey@test.com",
        "code": "000000",
    })
    assert resp.status_code == 400
