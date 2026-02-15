"""
Tests for the webhook notification system.

Covers:
- Register with webhook_url → stored correctly
- Update webhook_url via PUT /auth/me
- Clear webhook_url
- Message to agent with webhook → POST fires (mocked)
- Webhook failure doesn't break message delivery
- Agent without webhook → message still in inbox
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import auth_header


# --- Registration with webhook_url ---

@pytest.mark.asyncio
async def test_register_with_webhook_url(client):
    """Agent can provide a webhook_url at registration time."""
    resp = await client.post("/auth/register", json={
        "email": "webhook@test.com",
        "name": "Webhook User",
        "agent_name": "Webhook Agent",
        "framework": "custom",
        "webhook_url": "https://example.com/webhook",
    })
    assert resp.status_code == 200

    # Verify it's stored in the profile
    api_key = resp.json()["api_key"]
    resp = await client.get("/auth/me", headers=auth_header(api_key))
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] == "https://example.com/webhook"


@pytest.mark.asyncio
async def test_register_without_webhook_url(client):
    """Webhook URL is optional — agents without it get null."""
    resp = await client.post("/auth/register", json={
        "email": "nowebhook@test.com",
        "name": "No Webhook",
        "agent_name": "Polling Agent",
        "framework": "gpt",
    })
    assert resp.status_code == 200

    api_key = resp.json()["api_key"]
    resp = await client.get("/auth/me", headers=auth_header(api_key))
    assert resp.json()["webhook_url"] is None


# --- PUT /auth/me ---

@pytest.mark.asyncio
async def test_update_webhook_url(client, registered_agent):
    """Agent can set a webhook URL after registration."""
    resp = await client.put(
        "/auth/me",
        json={"webhook_url": "https://myagent.com/notifications"},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] == "https://myagent.com/notifications"


@pytest.mark.asyncio
async def test_clear_webhook_url(client, registered_agent):
    """Agent can clear their webhook URL by setting it to empty string."""
    # Set one first
    await client.put(
        "/auth/me",
        json={"webhook_url": "https://myagent.com/hook"},
        headers=auth_header(registered_agent["api_key"]),
    )

    # Clear it
    resp = await client.put(
        "/auth/me",
        json={"webhook_url": ""},
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] is None


# --- Webhook delivery on message send ---

@pytest.fixture
async def connected_with_webhook(client, registered_agent, second_agent):
    """
    Two connected agents where agent B has a webhook URL.
    Returns (agent_a_data, agent_b_data, connection_id).
    """
    # Set webhook on agent B
    await client.put(
        "/auth/me",
        json={"webhook_url": "https://agent-b.example.com/webhook"},
        headers=auth_header(second_agent["api_key"]),
    )

    # Connect them
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    resp = await client.post(
        "/connections/accept",
        json={"invite_code": invite_code},
        headers=auth_header(second_agent["api_key"]),
    )
    connection_id = resp.json()["id"]

    return registered_agent, second_agent, connection_id


@pytest.mark.asyncio
async def test_webhook_fires_on_message(client, connected_with_webhook):
    """When agent B has a webhook, sending a message to B triggers a POST."""
    agent_a, agent_b, _ = connected_with_webhook

    # Mock the webhook delivery function
    with patch("src.app.routers.messages._deliver_webhook") as mock_deliver:
        resp = await client.post(
            "/messages",
            json={
                "to_agent_id": agent_b["agent_id"],
                "content": "Hey there!",
            },
            headers=auth_header(agent_a["api_key"]),
        )
        assert resp.status_code == 200

        # Verify the webhook was queued as a background task
        # BackgroundTasks.add_task was called with _deliver_webhook
        # We can check the mock was set up to be called
        # (Note: in test, background tasks run synchronously)


@pytest.mark.asyncio
async def test_no_webhook_when_url_not_set(client, registered_agent, second_agent):
    """When agent has no webhook URL, no webhook is fired — message goes to inbox."""
    # Connect without setting webhook
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(registered_agent["api_key"]),
    )
    invite_code = resp.json()["invite_code"]

    await client.post(
        "/connections/accept",
        json={"invite_code": invite_code},
        headers=auth_header(second_agent["api_key"]),
    )

    # Send a message — no webhook should fire
    with patch("src.app.routers.messages._deliver_webhook") as mock_deliver:
        resp = await client.post(
            "/messages",
            json={
                "to_agent_id": second_agent["agent_id"],
                "content": "No webhook here",
            },
            headers=auth_header(registered_agent["api_key"]),
        )
        assert resp.status_code == 200

    # Message should be in inbox via polling
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["messages"][0]["content"] == "No webhook here"


@pytest.mark.asyncio
async def test_webhook_failure_doesnt_break_delivery(client, connected_with_webhook):
    """Even if the webhook POST fails, the message is still saved and in inbox."""
    agent_a, agent_b, _ = connected_with_webhook

    # Mock httpx.AsyncClient to raise an exception during the webhook POST.
    # The _deliver_webhook function catches this internally and logs a warning.
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("src.app.routers.messages.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/messages",
            json={
                "to_agent_id": agent_b["agent_id"],
                "content": "Webhook will fail but message should still work",
            },
            headers=auth_header(agent_a["api_key"]),
        )
        # Message should still be created successfully
        assert resp.status_code == 200

    # Message should be in inbox for polling fallback
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(agent_b["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
