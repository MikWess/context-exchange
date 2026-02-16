"""
Tests for the observer page.

GET /observe        → Login form (no auth) or dashboard (with auth)
GET /observe?token  → Dashboard with API key auth (backward compat)
GET /observe?jwt    → Dashboard with JWT auth (backward compat)
POST /observe/login → Send verification code
POST /observe/login/verify → Verify code, set JWT cookie, redirect
GET /observe/logout → Clear cookie, redirect to login
"""
import pytest
from tests.conftest import auth_header, _login_and_verify


@pytest.mark.asyncio
async def test_observe_returns_html(client, registered_agent):
    """GET /observe with valid token returns an HTML page."""
    key = registered_agent["api_key"]
    resp = await client.get(f"/observe?token={key}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Observer" in resp.text
    # Agent name appears in the switcher dropdown (HTML-escaped apostrophe)
    assert "Mikey&#x27;s Agent" in resp.text


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


# --- Observer login flow ---


@pytest.mark.asyncio
async def test_observe_no_auth_shows_login_form(client):
    """GET /observe with no auth shows a login form."""
    resp = await client.get("/observe")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Sign in" in resp.text
    assert 'name="email"' in resp.text


@pytest.mark.asyncio
async def test_observe_login_sends_code(client, registered_agent):
    """POST /observe/login sends a verification code and shows code form."""
    resp = await client.post(
        "/observe/login",
        data={"email": "mikey@test.com"},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Should show the code input form
    assert 'name="code"' in resp.text
    # Dev mode shows the code in the page
    assert "Dev mode" in resp.text


@pytest.mark.asyncio
async def test_observe_login_unknown_email_shows_error(client):
    """POST /observe/login with unknown email shows error in the form."""
    resp = await client.post(
        "/observe/login",
        data={"email": "nobody@test.com"},
    )
    assert resp.status_code == 200
    assert "No verified account" in resp.text


@pytest.mark.asyncio
async def test_observe_login_verify_sets_cookie(client, registered_agent):
    """POST /observe/login/verify with correct code sets JWT cookie and redirects."""
    # Step 1: Get the code from the login form
    resp = await client.post(
        "/observe/login",
        data={"email": "mikey@test.com"},
    )
    # Extract code from the dev mode message in the HTML
    # The message contains "Dev mode — your code is: 123456"
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]

    # Step 2: Verify — should redirect with a cookie
    resp = await client.post(
        "/observe/login/verify",
        data={"email": "mikey@test.com", "code": code},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/observe"
    # Cookie should be set
    assert "botjoin_jwt" in resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_observe_jwt_cookie_auth(client, registered_agent):
    """GET /observe with JWT cookie shows the dashboard."""
    # Get a JWT via the API login flow
    login_data = await _login_and_verify(client, "mikey@test.com")
    jwt_token = login_data["token"]

    # Set the cookie and request the dashboard
    client.cookies.set("botjoin_jwt", jwt_token)
    resp = await client.get("/observe")
    assert resp.status_code == 200
    assert "Observer" in resp.text
    assert "Mikey&#x27;s Agent" in resp.text


@pytest.mark.asyncio
async def test_observe_logout_clears_cookie(client, registered_agent):
    """GET /observe/logout clears the JWT cookie and redirects to login."""
    resp = await client.get("/observe/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/observe"
    # Cookie should be deleted
    cookie_header = resp.headers.get("set-cookie", "")
    assert "botjoin_jwt" in cookie_header
