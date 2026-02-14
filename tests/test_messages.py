"""
Tests for messaging: send, inbox, acknowledge, threads.
"""
import pytest
from tests.conftest import auth_header


async def _connect_agents(client, agent_a, agent_b):
    """Helper: create a connection between two agents. Returns connection id."""
    resp = await client.post(
        "/connections/invite",
        headers=auth_header(agent_a["api_key"]),
    )
    code = resp.json()["invite_code"]
    resp = await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(agent_b["api_key"]),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_send_message_creates_thread(client, registered_agent, second_agent):
    """Sending a message without a thread_id creates a new thread."""
    await _connect_agents(client, registered_agent, second_agent)

    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Hey, is Sam free Thursday?",
            "message_type": "query",
            "category": "schedule",
            "thread_subject": "Thursday plans",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Hey, is Sam free Thursday?"
    assert data["message_type"] == "query"
    assert data["category"] == "schedule"
    assert data["status"] == "sent"
    assert "thread_id" in data


@pytest.mark.asyncio
async def test_send_to_unconnected_agent_fails(client, registered_agent, second_agent):
    """Can't send a message to an agent you're not connected with."""
    # Don't connect them
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "This shouldn't work",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 403
    assert "not connected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_inbox_returns_unread_messages(client, registered_agent, second_agent):
    """Inbox returns messages sent to the agent with status 'sent'."""
    await _connect_agents(client, registered_agent, second_agent)

    # Agent A sends to Agent B
    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Message 1",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Message 2",
        },
        headers=auth_header(registered_agent["api_key"]),
    )

    # Agent B checks inbox
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    # Messages should be newest first
    assert data["messages"][0]["content"] == "Message 2"
    assert data["messages"][1]["content"] == "Message 1"


@pytest.mark.asyncio
async def test_inbox_marks_as_delivered(client, registered_agent, second_agent):
    """Checking inbox marks messages as delivered — second check returns empty."""
    await _connect_agents(client, registered_agent, second_agent)

    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "One-time read",
        },
        headers=auth_header(registered_agent["api_key"]),
    )

    # First inbox check gets the message
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.json()["count"] == 1

    # Second check — already delivered, so empty
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_acknowledge_message(client, registered_agent, second_agent):
    """Acknowledging a message sets its status to read."""
    await _connect_agents(client, registered_agent, second_agent)

    # Send a message
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Please ack this",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    msg_id = resp.json()["id"]

    # Agent B acknowledges
    resp = await client.post(
        f"/messages/{msg_id}/ack",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_ack_others_message_fails(client, registered_agent, second_agent):
    """Can't acknowledge a message that wasn't sent to you."""
    await _connect_agents(client, registered_agent, second_agent)

    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Not yours to ack",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    msg_id = resp.json()["id"]

    # Agent A (the sender) tries to ack their own message — not allowed
    resp = await client.post(
        f"/messages/{msg_id}/ack",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_thread_conversation(client, registered_agent, second_agent):
    """Multiple messages in the same thread form a conversation."""
    await _connect_agents(client, registered_agent, second_agent)

    # Agent A starts a thread
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Is Sam free Thursday?",
            "message_type": "query",
            "thread_subject": "Thursday plans",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    thread_id = resp.json()["thread_id"]

    # Agent B replies in the same thread
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": registered_agent["agent_id"],
            "content": "Sam is free 12-2pm",
            "message_type": "response",
            "thread_id": thread_id,
        },
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == thread_id

    # Get the full thread
    resp = await client.get(
        f"/messages/thread/{thread_id}",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread"]["subject"] == "Thursday plans"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "Is Sam free Thursday?"
    assert data["messages"][1]["content"] == "Sam is free 12-2pm"


@pytest.mark.asyncio
async def test_list_threads(client, registered_agent, second_agent):
    """List threads returns all threads for the agent."""
    await _connect_agents(client, registered_agent, second_agent)

    # Create two threads
    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Thread 1",
            "thread_subject": "First topic",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Thread 2",
            "thread_subject": "Second topic",
        },
        headers=auth_header(registered_agent["api_key"]),
    )

    # Both agents should see both threads
    resp = await client.get(
        "/messages/threads",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = await client.get(
        "/messages/threads",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_send_to_self_fails(client, registered_agent):
    """Can't send a message to yourself."""
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": registered_agent["agent_id"],
            "content": "Talking to myself",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_full_flow(client, registered_agent, second_agent):
    """
    End-to-end: register, connect, message, check inbox, ack, verify thread.
    This is the "tomorrow" demo flow.
    """
    # 1. Connect
    await _connect_agents(client, registered_agent, second_agent)

    # 2. Agent A sends a query
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Is Sam free this weekend?",
            "message_type": "query",
            "category": "schedule",
            "thread_subject": "Weekend plans",
        },
        headers=auth_header(registered_agent["api_key"]),
    )
    thread_id = resp.json()["thread_id"]
    msg1_id = resp.json()["id"]

    # 3. Agent B checks inbox
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert resp.json()["count"] == 1
    assert resp.json()["messages"][0]["content"] == "Is Sam free this weekend?"

    # 4. Agent B acknowledges
    await client.post(
        f"/messages/{msg1_id}/ack",
        headers=auth_header(second_agent["api_key"]),
    )

    # 5. Agent B replies
    resp = await client.post(
        "/messages",
        json={
            "to_agent_id": registered_agent["agent_id"],
            "content": "Sam is free Saturday afternoon and all day Sunday",
            "message_type": "response",
            "category": "schedule",
            "thread_id": thread_id,
        },
        headers=auth_header(second_agent["api_key"]),
    )

    # 6. Agent A checks inbox and gets the reply
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.json()["count"] == 1
    assert "Saturday afternoon" in resp.json()["messages"][0]["content"]

    # 7. Verify the thread has both messages
    resp = await client.get(
        f"/messages/thread/{thread_id}",
        headers=auth_header(registered_agent["api_key"]),
    )
    thread_data = resp.json()
    assert thread_data["thread"]["subject"] == "Weekend plans"
    assert len(thread_data["messages"]) == 2
