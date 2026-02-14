"""
Tests for connection endpoints: invite, accept, list, remove.
"""
import pytest
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_create_invite(client, registered_agent):
    """Creating an invite returns a code and expiry."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "invite_code" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_accept_invite_creates_connection(client, registered_agent, second_agent):
    """Accepting a valid invite creates a connection between two agents."""
    # Agent A creates invite
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]

    # Agent B accepts
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["connected_agent"]["name"] == "Mikey's Agent"


@pytest.mark.asyncio
async def test_accept_own_invite_fails(client, registered_agent):
    """Can't accept your own invite."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_accept_used_invite_fails(client, registered_agent, second_agent):
    """Can't use an invite code twice."""
    # Create invite
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]

    # First accept succeeds
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200

    # Register a third agent and try to use same code
    resp = await client.post("/auth/register", json={
        "email": "jake@test.com",
        "name": "Jake",
        "agent_name": "Jake's Agent",
    })
    jake = resp.json()

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(jake["api_key"]),
    )
    assert resp.status_code == 400
    assert "already been used" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_accept_invalid_code_fails(client, registered_agent):
    """Invalid invite code returns 404."""
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": "totally_fake_code"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_connections(client, registered_agent, second_agent):
    """Both sides can see the connection after it's created."""
    # Create and accept invite
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]

    await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(second_agent["api_key"]),
    )

    # Agent A sees the connection
    resp = await client.get(
        "/connections",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    conns = resp.json()
    assert len(conns) == 1
    assert conns[0]["connected_agent"]["name"] == "Sam's Agent"

    # Agent B also sees it
    resp = await client.get(
        "/connections",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    conns = resp.json()
    assert len(conns) == 1
    assert conns[0]["connected_agent"]["name"] == "Mikey's Agent"


@pytest.mark.asyncio
async def test_duplicate_connection_fails(client, registered_agent, second_agent):
    """Can't connect with the same agent twice."""
    # First connection
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]
    await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(second_agent["api_key"]),
    )

    # Try again — new invite, same agents
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code2 = resp.json()["invite_code"]
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code2},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 400
    assert "already connected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_connection(client, registered_agent, second_agent):
    """Removing a connection sets its status to removed."""
    # Create connection
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    code = resp.json()["invite_code"]
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(second_agent["api_key"]),
    )
    conn_id = resp.json()["id"]

    # Remove it
    resp = await client.delete(
        f"/connections/{conn_id}",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 204
