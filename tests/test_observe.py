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
async def test_observe_login_unknown_email_shows_register(client):
    """POST /observe/login with unknown email shows the registration form."""
    resp = await client.post(
        "/observe/login",
        data={"email": "nobody@test.com"},
    )
    assert resp.status_code == 200
    # Should show the register form instead of just an error
    assert "No account found" in resp.text
    assert 'name="name"' in resp.text  # Register form has a name field
    assert "Create account" in resp.text


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


# --- Observer registration flow ---


@pytest.mark.asyncio
async def test_observe_register_page(client):
    """GET /observe/register shows the registration form."""
    resp = await client.get("/observe/register")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'name="name"' in resp.text
    assert 'name="email"' in resp.text
    assert "Create account" in resp.text


@pytest.mark.asyncio
async def test_observe_register_flow(client):
    """Full observer registration: name+email → code → verify → signed in."""
    # Step 1: Register
    resp = await client.post(
        "/observe/register",
        data={"name": "New Person", "email": "newperson@test.com"},
    )
    assert resp.status_code == 200
    assert 'name="code"' in resp.text  # Should show code form
    # Dev mode shows the code
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]

    # Step 2: Verify — should redirect with a cookie
    resp = await client.post(
        "/observe/register/verify",
        data={"email": "newperson@test.com", "code": code},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/observe"
    assert "botjoin_jwt" in resp.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_observe_register_existing_email_shows_error(client, registered_agent):
    """POST /observe/register with an already-verified email shows error."""
    resp = await client.post(
        "/observe/register",
        data={"name": "Imposter", "email": "mikey@test.com"},
    )
    assert resp.status_code == 200
    assert "already exists" in resp.text


@pytest.mark.asyncio
async def test_observe_register_wrong_code(client):
    """POST /observe/register/verify with wrong code shows error."""
    # Register first
    await client.post(
        "/observe/register",
        data={"name": "Bad Code", "email": "badcode@test.com"},
    )
    # Try wrong code
    resp = await client.post(
        "/observe/register/verify",
        data={"email": "badcode@test.com", "code": "000000"},
    )
    assert resp.status_code == 200
    assert "Invalid verification code" in resp.text


@pytest.mark.asyncio
async def test_observe_setup_guide_for_new_user(client):
    """Observer shows setup guide when user has no agents."""
    # Register a human through the Observer (no agent)
    resp = await client.post(
        "/observe/register",
        data={"name": "Agent-less Human", "email": "noagent@test.com"},
    )
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]

    # Verify and get the cookie
    resp = await client.post(
        "/observe/register/verify",
        data={"email": "noagent@test.com", "code": code},
        follow_redirects=False,
    )
    # Extract the JWT cookie
    cookie_header = resp.headers.get("set-cookie", "")
    jwt_start = cookie_header.find("botjoin_jwt=") + len("botjoin_jwt=")
    jwt_end = cookie_header.find(";", jwt_start)
    jwt_token = cookie_header[jwt_start:jwt_end]

    # Visit the dashboard — should show setup guide, not empty conversations
    client.cookies.set("botjoin_jwt", jwt_token)
    resp = await client.get("/observe")
    assert resp.status_code == 200
    assert "Welcome to BotJoin" in resp.text
    assert "connect your first AI agent" in resp.text
    assert "/setup" in resp.text  # Link to full setup instructions
    # Framework-specific tabs should be present
    assert "Claude Code" in resp.text
    assert "OpenClaw" in resp.text
    assert "ChatGPT" in resp.text
    assert "setup-tab" in resp.text
    # Raw API calls should NOT be shown to non-developer users
    assert "/auth/recover" not in resp.text


@pytest.mark.asyncio
async def test_observe_register_verify_sends_welcome_email(client):
    """Observer registration verify triggers a welcome email (UI variant)."""
    from unittest.mock import patch, AsyncMock

    with patch("src.app.routers.observe.send_welcome_email", new_callable=AsyncMock, return_value=True) as mock_send:
        # Register
        resp = await client.post(
            "/observe/register",
            data={"name": "Welcome Person", "email": "welcome-obs@test.com"},
        )
        html = resp.text
        code_start = html.find("your code is: ") + len("your code is: ")
        code = html[code_start:code_start + 6]

        # Verify
        resp = await client.post(
            "/observe/register/verify",
            data={"email": "welcome-obs@test.com", "code": code},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "welcome-obs@test.com"
        assert args[1] == "Welcome Person"


@pytest.mark.asyncio
async def test_observe_login_has_register_link(client):
    """Login page has a link to create an account."""
    resp = await client.get("/observe")
    assert resp.status_code == 200
    assert "Create an account" in resp.text
    assert "/observe/register" in resp.text
