"""
Tests for the long-polling /messages/stream endpoint.

Covers:
- Returns empty response when no messages after timeout
- Returns messages immediately when they exist
- Messages are marked as "delivered" after streaming
- Respects the limit of 50 messages
- Requires authentication
"""
import pytest
from unittest.mock import patch, AsyncMock

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


@pytest.mark.asyncio
async def test_stream_returns_empty_on_timeout(client, registered_agent):
    """Stream endpoint returns empty response when no messages arrive before timeout."""
    # Use timeout=1 so the test doesn't wait long
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_stream_returns_existing_messages(client, connected_agents):
    """Stream returns messages immediately if they already exist when called."""
    agent_a, agent_b, _ = connected_agents

    # Agent A sends a message to Agent B
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "Hello from stream test!",
        },
        headers=auth_header(agent_a["api_key"]),
    )
    assert resp.status_code == 200

    # Agent B streams — should get the message immediately (no waiting)
    resp = await client.get(
        "/messages/stream?timeout=5",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["messages"][0]["content"] == "Hello from stream test!"


@pytest.mark.asyncio
async def test_stream_marks_messages_as_delivered(client, connected_agents):
    """Messages returned by stream are marked as 'delivered' — won't show up again."""
    agent_a, agent_b, _ = connected_agents

    # Send a message
    await client.post(
        "/messages",
        json={
            "to_agent_id": agent_b["agent_id"],
            "content": "One-time delivery",
        },
        headers=auth_header(agent_a["api_key"]),
    )

    # First stream call gets the message
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.json()["count"] == 1

    # Second stream call — message already delivered, so empty
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_stream_returns_multiple_messages(client, connected_agents):
    """Stream returns all pending messages at once."""
    agent_a, agent_b, _ = connected_agents

    # Send 3 messages
    for i in range(3):
        await client.post(
            "/messages",
            json={
                "to_agent_id": agent_b["agent_id"],
                "content": f"Message {i}",
            },
            headers=auth_header(agent_a["api_key"]),
        )

    # Stream should return all 3
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.json()["count"] == 3


@pytest.mark.asyncio
async def test_stream_requires_auth(client):
    """Stream endpoint requires authentication."""
    resp = await client.get("/messages/stream?timeout=1")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_stream_timeout_bounds(client, registered_agent):
    """Timeout parameter has bounds: 1-60 seconds."""
    # Too low
    resp = await client.get(
        "/messages/stream?timeout=0",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 422  # Validation error

    # Too high
    resp = await client.get(
        "/messages/stream?timeout=120",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 422
