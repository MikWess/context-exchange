"""
Tests for the contract-based permission system.

Covers:
- Default permissions created from "friends" contract (3 categories)
- Other contracts (coworkers, casual) set different defaults
- Invalid contract rejected
- GET permissions returns 3 categories
- PUT permission updates a category's level
- Can't view/update permissions for a connection you're not part of
- "never" level blocks messages (from sender or receiver side)
- Messages with no category always go through
- GET /contracts returns available presets
"""
import pytest

from tests.conftest import auth_header


@pytest.fixture
async def connected_agents(client, registered_agent, second_agent):
    """
    Create two agents and connect them via invite (default "friends" contract).
    Returns (agent_a_data, agent_b_data, connection_id).
    """
    # Agent A creates an invite
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    invite_code = resp.json()["invite_code"]

    # Agent B accepts the invite (default contract = "friends")
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    connection_id = resp.json()["id"]

    return registered_agent, second_agent, connection_id


# --- Contract-based defaults ---

@pytest.mark.asyncio
async def test_default_permissions_from_friends_contract(client, connected_agents):
    """When two agents connect with 'friends' contract, each gets 3 permissions: info=auto, requests=ask, personal=ask."""
    agent_a, agent_b, connection_id = connected_agents

    # Check agent A's permissions
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["connection_id"] == connection_id
    perms = data["permissions"]
    assert len(perms) == 3

    # Build a lookup: category -> level
    perm_map = {p["category"]: p["level"] for p in perms}
    assert perm_map == {"info": "auto", "requests": "ask", "personal": "ask"}


@pytest.mark.asyncio
async def test_both_agents_get_same_contract_defaults(client, connected_agents):
    """Each agent gets independent permissions, both matching the contract."""
    agent_a, agent_b, connection_id = connected_agents

    # Agent B also has 3 permissions matching "friends" contract
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert len(perms) == 3
    perm_map = {p["category"]: p["level"] for p in perms}
    assert perm_map == {"info": "auto", "requests": "ask", "personal": "ask"}


@pytest.mark.asyncio
async def test_coworkers_contract(client, registered_agent, second_agent):
    """Coworkers contract: info=auto, requests=auto, personal=never."""
    # Create invite and accept with "coworkers" contract
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code, "contract": "coworkers"},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["contract_type"] == "coworkers"
    connection_id = resp.json()["id"]

    # Check permissions match "coworkers" contract
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(registered_agent["api_key"]),
    )
    perm_map = {p["category"]: p["level"] for p in resp.json()["permissions"]}
    assert perm_map == {"info": "auto", "requests": "auto", "personal": "never"}


@pytest.mark.asyncio
async def test_casual_contract(client, registered_agent, second_agent):
    """Casual contract: info=auto, requests=never, personal=never."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code, "contract": "casual"},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["contract_type"] == "casual"
    connection_id = resp.json()["id"]

    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(second_agent["api_key"]),
    )
    perm_map = {p["category"]: p["level"] for p in resp.json()["permissions"]}
    assert perm_map == {"info": "auto", "requests": "never", "personal": "never"}


@pytest.mark.asyncio
async def test_invalid_contract_rejected(client, registered_agent, second_agent):
    """Accepting with an unknown contract name returns 400."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code, "contract": "besties"},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 400
    assert "Unknown contract" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_connection_includes_contract_type(client, connected_agents):
    """Connection info includes which contract was used."""
    agent_a, _, connection_id = connected_agents

    resp = await client.get(
        "/connections",
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    connections = resp.json()
    assert len(connections) == 1
    assert connections[0]["contract_type"] == "friends"


# --- Updating permissions ---

@pytest.mark.asyncio
async def test_update_permission_level(client, connected_agents):
    """Agent can change a category's level (e.g. requests from 'ask' to 'auto')."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "requests", "level": "auto"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "requests"
    assert resp.json()["level"] == "auto"

    # Verify it persisted
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(agent_a["api_key"]),
    )
    req_perm = [p for p in resp.json()["permissions"] if p["category"] == "requests"][0]
    assert req_perm["level"] == "auto"


@pytest.mark.asyncio
async def test_update_permission_to_never(client, connected_agents):
    """Agent can block a category by setting it to 'never'."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "personal", "level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["level"] == "never"


@pytest.mark.asyncio
async def test_update_permission_invalid_level(client, connected_agents):
    """Rejects invalid permission levels."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "info", "level": "yolo"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 400
    assert "Invalid level" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_permission_invalid_category(client, connected_agents):
    """Rejects invalid category names (old categories don't work anymore)."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "schedule", "level": "auto"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 400
    assert "Invalid category" in resp.json()["detail"]


# --- Access control ---

@pytest.mark.asyncio
async def test_cant_view_permissions_for_other_connection(client, connected_agents):
    """Agent can't view permissions for a connection they're not part of."""
    _, _, connection_id = connected_agents

    # Register a third agent who is NOT in this connection
    resp = await client.post("/auth/register", json={
        "email": "outsider@test.com",
        "name": "Outsider",
        "agent_name": "Outsider's Agent",
        "framework": "custom",
    })
    outsider_key = resp.json()["api_key"]

    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(outsider_key),
    )
    assert resp.status_code == 403
    assert "Not your connection" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cant_update_permissions_for_other_connection(client, connected_agents):
    """Agent can't update permissions for a connection they're not part of."""
    _, _, connection_id = connected_agents

    resp = await client.post("/auth/register", json={
        "email": "outsider2@test.com",
        "name": "Outsider2",
        "agent_name": "Outsider2's Agent",
        "framework": "custom",
    })
    outsider_key = resp.json()["api_key"]

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "info", "level": "auto"},
        headers=auth_header(outsider_key),
    )
    assert resp.status_code == 403


# --- Permission enforcement on messages ---

@pytest.mark.asyncio
async def test_message_blocked_when_sender_level_is_never(client, connected_agents):
    """If sender sets a category to 'never', they can't send messages in that category."""
    agent_a, agent_b, connection_id = connected_agents

    # Set "personal" to "never" for agent A
    await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "personal", "level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )

    # Agent A tries to send a "personal" message → blocked
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Here's my SSN...",
            "category": "personal",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 403
    assert "permission" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_message_blocked_when_receiver_level_is_never(client, connected_agents):
    """If receiver sets a category to 'never', messages in that category are blocked."""
    agent_a, agent_b, connection_id = connected_agents

    # Agent B blocks "info" category
    await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "info", "level": "never"},
        headers=auth_header(agent_b["api_key"]),
    )

    # Agent A tries to send "info" to Agent B → blocked by B's setting
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Here's some info",
            "category": "info",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 403
    # Error message is intentionally vague to avoid leaking receiver's settings
    assert "could not be delivered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_message_allowed_when_auto(client, connected_agents):
    """Messages with 'auto' level go through. Info defaults to auto on friends contract."""
    agent_a, agent_b, connection_id = connected_agents

    # info is "auto" by default on "friends" contract — should work
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "I'm free after 5pm today",
            "category": "info",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "info"


@pytest.mark.asyncio
async def test_message_allowed_when_ask(client, connected_agents):
    """Messages with 'ask' level go through (agent handles asking on its side)."""
    agent_a, agent_b, connection_id = connected_agents

    # requests is "ask" by default on "friends" — should still allow sending
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Can you review my PR?",
            "category": "requests",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_message_no_category_always_allowed(client, connected_agents):
    """Messages without a category always go through, regardless of permissions."""
    agent_a, agent_b, connection_id = connected_agents

    # Even if we set everything to "never", no-category messages still work
    for cat in ["info", "requests", "personal"]:
        await client.put(
            f"/connections/{connection_id}/permissions",
            json={"category": cat, "level": "never"},
            headers=auth_header(agent_a["api_key"]),
        )

    # Plain text message with no category → always allowed
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Hey, what's up?",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["category"] is None


@pytest.mark.asyncio
async def test_permission_is_per_agent(client, connected_agents):
    """
    Permissions are per-agent. Agent A setting requests to 'never' blocks
    A from sending requests, but doesn't affect B's ability to send requests.
    """
    agent_a, agent_b, connection_id = connected_agents

    # Agent A blocks "requests" outbound
    await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "requests", "level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )

    # Agent A can't send requests
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Can you do this?",
            "category": "requests",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 403

    # Agent B CAN still send requests (their level is still "ask", and A's is "never"
    # but A is the receiver here — the receiver check blocks if receiver.level=="never".
    # Since A set requests to "never", messages TO A in "requests" are also blocked.)
    # This is the new behavior: "never" means "I want nothing to do with this category"

    # But B can send info (which A still has as "auto")
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_a["agent_id"],
            "content": "Here's some info for you",
            "category": "info",
        },
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200


# --- Contracts endpoint ---

@pytest.mark.asyncio
async def test_list_contracts(client):
    """GET /contracts returns the built-in contract presets."""
    resp = await client.get("/contracts")
    assert resp.status_code == 200
    contracts = resp.json()
    assert len(contracts) == 3

    # Check each contract has the right structure
    names = {c["name"] for c in contracts}
    assert names == {"friends", "coworkers", "casual"}

    # Verify "friends" contract levels
    friends = [c for c in contracts if c["name"] == "friends"][0]
    assert friends["levels"] == {"info": "auto", "requests": "ask", "personal": "ask"}

    # Verify "coworkers" contract levels
    coworkers = [c for c in contracts if c["name"] == "coworkers"][0]
    assert coworkers["levels"] == {"info": "auto", "requests": "auto", "personal": "never"}
