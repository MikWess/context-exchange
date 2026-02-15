"""
Tests for the observer page.

GET /observe?token=API_KEY → HTML page showing agent conversations
"""
import pytest
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_observe_returns_html(client, registered_agent):
    """GET /observe with valid token returns an HTML page."""
    key = registered_agent["api_key"]
    resp = await client.get(f"/observe?token={key}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Observer" in resp.text
    assert "Mikey's Agent" in resp.text


@pytest.mark.asyncio
async def test_observe_invalid_token(client):
    """GET /observe with bad token returns 401."""
    resp = await client.get("/observe?token=cex_badtoken123")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_observe_shows_messages(client, registered_agent, second_agent):
    """Observer page shows messages between connected agents."""
    key_a = registered_agent["api_key"]
    key_b = second_agent["api_key"]

    # Connect the two agents
    invite_resp = await client.post("/connections/invite", headers=auth_header(key_a))
    code = invite_resp.json()["invite_code"]
    await client.post(
        "/connections/accept",
        json={"invite_code": code},
        headers=auth_header(key_b),
    )

    # Send a message
    await client.post(
        "/messages",
        json={
            "to_agent_id": second_agent["agent_id"],
            "content": "Hey Sam, are you free Thursday?",
            "message_type": "query",
            "category": "schedule",
            "thread_subject": "Thursday plans",
        },
        headers=auth_header(key_a),
    )

    # Check the observer page shows it
    resp = await client.get(f"/observe?token={key_a}")
    assert resp.status_code == 200
    assert "Thursday plans" in resp.text
    assert "Hey Sam, are you free Thursday?" in resp.text
    assert "Sam&#x27;s Agent" in resp.text  # HTML-escaped apostrophe
