"""
Tests for multi-agent identity system.

Covers:
- Adding a second agent to the same user account
- Listing agents under an account
- Second agent can message through shared human-level connection
- Permissions are per-human (changing via one agent affects all)
- Observer JWT auth shows all agents
"""
import pytest
from tests.conftest import auth_header, _register_and_verify


# --- Adding agents ---

@pytest.mark.asyncio
async def test_add_second_agent(client, registered_agent):
    """POST /auth/agents creates a second agent under the same user."""
    resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_id" in data
    assert "api_key" in data
    assert data["api_key"].startswith("cex_")


@pytest.mark.asyncio
async def test_list_agents_shows_both(client, registered_agent):
    """GET /auth/agents returns all agents under the same human."""
    # Add a second agent
    await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(registered_agent["api_key"]),
    )

    # List all agents
    resp = await client.get(
        "/auth/agents",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 2
    names = {a["name"] for a in agents}
    assert "Mikey's Agent" in names
    assert "Mikey's Claude" in names


@pytest.mark.asyncio
async def test_first_agent_is_primary(client, registered_agent):
    """The first agent created is marked as primary."""
    resp = await client.get(
        "/auth/me",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.json()["is_primary"] is True


@pytest.mark.asyncio
async def test_second_agent_is_not_primary(client, registered_agent):
    """Additional agents are not primary by default."""
    resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(registered_agent["api_key"]),
    )
    new_key = resp.json()["api_key"]

    resp = await client.get("/auth/me", headers=auth_header(new_key))
    assert resp.json()["is_primary"] is False


# --- Multi-agent messaging ---

@pytest.mark.asyncio
async def test_second_agent_can_message_through_shared_connection(
    client, registered_agent, second_agent,
):
    """
    Agent A1 connects with user B. Agent A2 (same user as A1) can also
    message user B's agent through the shared human-level connection.
    """
    key_a1 = registered_agent["api_key"]
    key_b = second_agent["api_key"]

    # Connect user A with user B (via agent A1)
    invite_resp = await client.post("/connections/invite", headers=auth_header(key_a1))
    code = invite_resp.json()["invite_code"]
    await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(key_b),
    )

    # Add a second agent (A2) under the same user
    a2_resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(key_a1),
    )
    key_a2 = a2_resp.json()["api_key"]

    # Agent A2 can message agent B through the human-level connection
    msg_resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Hi from Mikey's second agent!",
        },
        headers=auth_header(key_a2),
    )
    assert msg_resp.status_code == 200
    assert msg_resp.json()["content"] == "Hi from Mikey's second agent!"


@pytest.mark.asyncio
async def test_second_agent_sees_same_connections(client, registered_agent, second_agent):
    """All agents under the same user see the same connections."""
    key_a1 = registered_agent["api_key"]
    key_b = second_agent["api_key"]

    # Connect via agent A1
    invite_resp = await client.post("/connections/invite", headers=auth_header(key_a1))
    code = invite_resp.json()["invite_code"]
    await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(key_b),
    )

    # Add agent A2
    a2_resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(key_a1),
    )
    key_a2 = a2_resp.json()["api_key"]

    # Agent A2 sees the same connection
    resp = await client.get("/connections", headers=auth_header(key_a2))
    assert resp.status_code == 200
    conns = resp.json()
    assert len(conns) == 1
    assert conns[0]["connected_user"]["name"] == "Sam"


# --- Permissions are per-human ---

@pytest.mark.asyncio
async def test_permission_change_affects_all_agents(client, registered_agent, second_agent):
    """Changing permissions via one agent affects messaging for all agents under that human."""
    key_a1 = registered_agent["api_key"]
    key_b = second_agent["api_key"]

    # Connect
    invite_resp = await client.post("/connections/invite", headers=auth_header(key_a1))
    code = invite_resp.json()["invite_code"]
    accept_resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(key_b),
    )
    conn_id = accept_resp.json()["id"]

    # Add agent A2
    a2_resp = await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(key_a1),
    )
    key_a2 = a2_resp.json()["api_key"]

    # Set personal to "never" via agent A1
    await client.put(
        f"/connections/{conn_id}/permissions",
        json={"category": "personal", "level": "never"},
        headers=auth_header(key_a1),
    )

    # Agent A2 should also be blocked for personal messages
    msg_resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Personal stuff",
            "category": "personal",
        },
        headers=auth_header(key_a2),
    )
    assert msg_resp.status_code == 403


# --- Observer JWT auth ---

@pytest.mark.asyncio
async def test_observer_jwt_shows_all_agents(client, registered_agent):
    """Observer with JWT shows all agents under the user."""
    # Get a JWT
    login_resp = await client.post("/auth/login", json={"email": "mikey@test.com"})
    jwt_token = login_resp.json()["token"]

    # Add a second agent
    await client.post(
        "/auth/agents",
        json={"agent_name": "Mikey's Claude", "framework": "claude"},
        headers=auth_header(registered_agent["api_key"]),
    )

    # Observer with JWT
    resp = await client.get(f"/observe?jwt={jwt_token}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Should show both agents in the switcher
    assert "Mikey&#x27;s Agent" in resp.text
    assert "Mikey&#x27;s Claude" in resp.text


@pytest.mark.asyncio
async def test_observer_no_auth_fails(client):
    """Observer without token or JWT returns 401."""
    resp = await client.get("/observe")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_observer_bad_jwt_fails(client):
    """Observer with invalid JWT returns 401."""
    resp = await client.get("/observe?jwt=bad_token")
    assert resp.status_code == 401
