"""
Tests for the platform announcement system.

Covers:
- Announcements show up in inbox response
- Announcements show up in stream response
- Announcements are marked as read (don't repeat)
- instructions_version field present in responses
- Admin endpoint creates announcements (with valid key)
- Admin endpoint rejects invalid key
- Inactive announcements not returned
"""
import pytest

from tests.conftest import auth_header


ADMIN_KEY = "dev-admin-key"  # Matches config default


def admin_header():
    """Helper to build the admin key header."""
    return {"X-Admin-Key": ADMIN_KEY}


# --- Admin endpoint ---

@pytest.mark.asyncio
async def test_admin_create_announcement(client):
    """Admin can create an announcement with a valid key."""
    resp = await client.post(
        "/admin/announcements",
        json={
            "title": "Test Announcement",
            "content": "This is a test announcement for all agents.",
            "version": "2",
        },
        headers=admin_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Announcement"
    assert data["content"] == "This is a test announcement for all agents."
    assert data["version"] == "2"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_admin_rejects_invalid_key(client):
    """Admin endpoint rejects requests without a valid key."""
    resp = await client.post(
        "/admin/announcements",
        json={
            "title": "Sneaky",
            "content": "Should not work",
            "version": "1",
        },
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_rejects_missing_key(client):
    """Admin endpoint rejects requests with no key at all."""
    resp = await client.post(
        "/admin/announcements",
        json={
            "title": "Sneaky",
            "content": "Should not work",
            "version": "1",
        },
    )
    assert resp.status_code == 422  # Missing required header


@pytest.mark.asyncio
async def test_admin_list_announcements(client):
    """Admin can list all announcements."""
    # Create two announcements
    await client.post(
        "/admin/announcements",
        json={"title": "First", "content": "First announcement", "version": "1"},
        headers=admin_header(),
    )
    await client.post(
        "/admin/announcements",
        json={"title": "Second", "content": "Second announcement", "version": "2"},
        headers=admin_header(),
    )

    resp = await client.get("/admin/announcements", headers=admin_header())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


# --- Announcement delivery via inbox ---

@pytest.mark.asyncio
async def test_announcement_in_inbox(client, registered_agent):
    """Announcements show up in the inbox response."""
    # Create an announcement
    await client.post(
        "/admin/announcements",
        json={
            "title": "Big Update",
            "content": "Streaming is here!",
            "version": "2",
        },
        headers=admin_header(),
    )

    # Check inbox — should include the announcement
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["announcements"]) == 1
    assert data["announcements"][0]["title"] == "Big Update"
    assert data["announcements"][0]["content"] == "Streaming is here!"


@pytest.mark.asyncio
async def test_announcement_not_repeated(client, registered_agent):
    """Once delivered, announcements don't show up again."""
    # Create an announcement
    await client.post(
        "/admin/announcements",
        json={
            "title": "One-Time",
            "content": "You should only see this once.",
            "version": "2",
        },
        headers=admin_header(),
    )

    # First inbox call — gets the announcement
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 1

    # Second inbox call — announcement already read, not returned
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 0


@pytest.mark.asyncio
async def test_announcement_in_stream_with_messages(client, registered_agent, second_agent):
    """Announcements are delivered alongside messages in the stream response."""
    # Connect the two agents
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

    # Create an announcement
    await client.post(
        "/admin/announcements",
        json={
            "title": "Stream Update",
            "content": "You got this via stream!",
            "version": "2",
        },
        headers=admin_header(),
    )

    # Send a message so the stream has something to return
    await client.post(
        "/messages",
        json={
            "to_agent_id": registered_agent["agent_id"],
            "content": "Hello!",
        },
        headers=auth_header(second_agent["api_key"]),
    )

    # Stream should return messages + announcements together
    resp = await client.get(
        "/messages/stream?timeout=2",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1  # The message
    assert len(data["announcements"]) == 1
    assert data["announcements"][0]["title"] == "Stream Update"


@pytest.mark.asyncio
async def test_stream_timeout_no_announcements(client, registered_agent):
    """Stream timeout returns empty — announcements delivered via inbox instead."""
    # Create an announcement
    await client.post(
        "/admin/announcements",
        json={
            "title": "Timeout Test",
            "content": "Should not appear on timeout.",
            "version": "2",
        },
        headers=admin_header(),
    )

    # Stream with short timeout — no messages, so no announcements either
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    # Announcements not delivered on timeout (they'll come via inbox or next stream with messages)
    assert "announcements" not in data or len(data.get("announcements", [])) == 0

    # But inbox DOES deliver the announcement
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 1
    assert resp.json()["announcements"][0]["title"] == "Timeout Test"


@pytest.mark.asyncio
async def test_announcement_per_agent(client, registered_agent, second_agent):
    """Each agent gets their own copy of the announcement independently."""
    # Create an announcement
    await client.post(
        "/admin/announcements",
        json={
            "title": "For Everyone",
            "content": "All agents should see this.",
            "version": "2",
        },
        headers=admin_header(),
    )

    # Agent A gets it
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 1

    # Agent B also gets it (independent read tracking)
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(second_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 1

    # Agent A doesn't get it again
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 0


# --- instructions_version field ---

@pytest.mark.asyncio
async def test_announcement_has_source_field(client, registered_agent):
    """Announcements include source: 'context-exchange-platform' to prevent impersonation."""
    await client.post(
        "/admin/announcements",
        json={"title": "Sourced", "content": "Check my source field.", "version": "2"},
        headers=admin_header(),
    )

    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.json()["announcements"][0]["source"] == "context-exchange-platform"


@pytest.mark.asyncio
async def test_instructions_version_in_inbox(client, registered_agent):
    """Inbox response includes the current instructions_version."""
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert "instructions_version" in resp.json()
    assert resp.json()["instructions_version"] == "3"  # Current version from config


@pytest.mark.asyncio
async def test_instructions_version_in_stream(client, registered_agent):
    """Stream response includes the current instructions_version."""
    resp = await client.get(
        "/messages/stream?timeout=1",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert resp.status_code == 200
    assert resp.json()["instructions_version"] == "3"


# --- Inactive announcements ---

@pytest.mark.asyncio
async def test_inactive_announcement_not_returned(client, registered_agent, db_session):
    """Inactive announcements are not delivered to agents."""
    from src.app.models import Announcement

    # Create an announcement directly and set it inactive
    ann = Announcement(
        title="Hidden",
        content="You should not see this.",
        version="2",
        is_active=False,
    )
    db_session.add(ann)
    await db_session.flush()

    # Check inbox — no announcements
    resp = await client.get(
        "/messages/inbox",
        headers=auth_header(registered_agent["api_key"]),
    )
    assert len(resp.json()["announcements"]) == 0
