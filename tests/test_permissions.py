"""
Tests for the permission system.

Covers:
- Default permissions created on connection accept (outbound + inbound)
- GET permissions returns all categories with both levels
- PUT permission updates outbound and/or inbound level
- Can't view/update permissions for a connection you're not part of
- Outbound "never" blocks messages
- Inbound "never" blocks messages from the other side
- Messages with no category always go through
"""
import pytest

from src.app.config import DEFAULT_INBOUND_LEVELS
from tests.conftest import auth_header


@pytest.fixture
async def connected_agents(client, registered_agent, second_agent):
    """
    Create two agents and connect them via invite.
    Returns (agent_a_data, agent_b_data, connection_id).
    """
    # Agent A creates an invite
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    invite_code = resp.json()["invite_code"]

    # Agent B accepts the invite
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code},
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    connection_id = resp.json()["id"]

    return registered_agent, second_agent, connection_id


# --- Default permissions created on connect ---

@pytest.mark.asyncio
async def test_default_permissions_created_on_connect(client, connected_agents):
    """When two agents connect, each gets 6 permission rows with correct defaults."""
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
    assert len(perms) == 6

    # All outbound should be "ask" by default
    categories = {p["category"] for p in perms}
    assert categories == {"schedule", "projects", "knowledge", "interests", "requests", "personal"}
    for p in perms:
        assert p["level"] == "ask"
        # Inbound defaults vary by category
        assert p["inbound_level"] == DEFAULT_INBOUND_LEVELS[p["category"]]


@pytest.mark.asyncio
async def test_both_agents_get_separate_permissions(client, connected_agents):
    """Each agent has their own set of permissions — they're independent."""
    agent_a, agent_b, connection_id = connected_agents

    # Agent B also has 6 permissions with correct defaults
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert len(perms) == 6
    for p in perms:
        assert p["level"] == "ask"
        assert p["inbound_level"] == DEFAULT_INBOUND_LEVELS[p["category"]]


# --- Updating permissions ---

@pytest.mark.asyncio
async def test_update_permission_to_auto(client, connected_agents):
    """Agent can upgrade a category from 'ask' to 'auto'."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "schedule", "level": "auto"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "schedule"
    assert resp.json()["level"] == "auto"
    # inbound_level should be unchanged (still the default)
    assert resp.json()["inbound_level"] == "auto"

    # Verify it persisted
    resp = await client.get(
        f"/connections/{connection_id}/permissions",
        headers=auth_header(agent_a["api_key"]),
    )
    schedule_perm = [p for p in resp.json()["permissions"] if p["category"] == "schedule"][0]
    assert schedule_perm["level"] == "auto"


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
        json={"category": "schedule", "level": "yolo"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 400
    assert "Invalid level" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_permission_invalid_category(client, connected_agents):
    """Rejects invalid category names."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "secrets", "level": "auto"},
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
        json={"category": "schedule", "level": "auto"},
        headers=auth_header(outsider_key),
    )
    assert resp.status_code == 403


# --- Permission enforcement on messages ---

@pytest.mark.asyncio
async def test_message_blocked_when_category_is_never(client, connected_agents):
    """Messages with a category set to 'never' are rejected with 403."""
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
async def test_message_allowed_when_category_is_auto(client, connected_agents):
    """Messages with a category set to 'auto' go through."""
    agent_a, agent_b, connection_id = connected_agents

    # Set "schedule" to "auto" for agent A
    await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "schedule", "level": "auto"},
        headers=auth_header(agent_a["api_key"]),
    )

    # Agent A sends a "schedule" message → allowed
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "I'm free after 5pm today",
            "category": "schedule",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["category"] == "schedule"


@pytest.mark.asyncio
async def test_message_allowed_when_category_is_ask(client, connected_agents):
    """Messages with 'ask' level go through (agent handles the asking on its side)."""
    agent_a, agent_b, connection_id = connected_agents

    # Default is "ask" — should still allow the message
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Working on Context Exchange",
            "category": "projects",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_message_no_category_always_allowed(client, connected_agents):
    """Messages without a category always go through, regardless of permissions."""
    agent_a, agent_b, connection_id = connected_agents

    # Even if we set everything to "never", no-category messages still work
    for cat in ["schedule", "projects", "knowledge", "interests", "requests", "personal"]:
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
    """Agent A blocking 'personal' doesn't affect Agent B's ability to send 'personal'."""
    agent_a, agent_b, connection_id = connected_agents

    # Agent A blocks "personal" outbound
    await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "personal", "level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )

    # Agent B can still send "personal" (their outbound permission is still "ask")
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_a["agent_id"],
            "content": "Here's something personal from B",
            "category": "personal",
        },
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200


# --- Inbound permission enforcement ---

@pytest.mark.asyncio
async def test_inbound_never_blocks_messages(client, connected_agents):
    """When receiver sets inbound to 'never', messages of that category are blocked."""
    agent_a, agent_b, connection_id = connected_agents

    # Agent B blocks inbound "knowledge"
    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "knowledge", "inbound_level": "never"},
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["inbound_level"] == "never"

    # Agent A tries to send "knowledge" to Agent B → blocked by B's inbound rule
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Here's some knowledge for you",
            "category": "knowledge",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 403
    # Error message is intentionally vague to avoid leaking receiver's settings
    assert "could not be delivered" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_inbound_auto_allows_messages(client, connected_agents):
    """When receiver's inbound is 'auto' (default for safe categories), messages go through."""
    agent_a, agent_b, connection_id = connected_agents

    # schedule defaults to inbound "auto" — should work
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "I'm free at 5pm",
            "category": "schedule",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_inbound_level(client, connected_agents):
    """Agent can update just the inbound_level without changing outbound."""
    agent_a, _, connection_id = connected_agents

    # Update only inbound_level for "schedule"
    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "schedule", "inbound_level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["inbound_level"] == "never"
    # Outbound should be unchanged
    assert resp.json()["level"] == "ask"


@pytest.mark.asyncio
async def test_update_both_levels_at_once(client, connected_agents):
    """Can update both outbound and inbound in one request."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "projects", "level": "auto", "inbound_level": "never"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["level"] == "auto"
    assert resp.json()["inbound_level"] == "never"


@pytest.mark.asyncio
async def test_update_requires_at_least_one_level(client, connected_agents):
    """Must provide at least level or inbound_level."""
    agent_a, _, connection_id = connected_agents

    resp = await client.put(
        f"/connections/{connection_id}/permissions",
        json={"category": "schedule"},
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 400
    assert "at least one" in resp.json()["detail"].lower()
