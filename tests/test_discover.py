"""
Tests for the Discover feature.

GET  /discover                — Public browse page
GET  /discover/signup         — Signup form
POST /discover/signup         — Create profile + send verification
POST /discover/signup/verify  — Verify email, go live
GET  /discover/search         — Agent API: search profiles
GET  /discover/profiles/{id}  — Agent API: profile detail
POST /discover/profiles/{id}/reach-out — Agent API: outreach email
"""
import pytest
from tests.conftest import auth_header


# --- Public browse page ---


@pytest.mark.asyncio
async def test_discover_page_empty(client):
    """GET /discover with no real profiles shows demo profiles."""
    resp = await client.get("/discover")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Put yourself out there" in resp.text
    # Should show demo profiles
    assert "See what this looks like" in resp.text
    assert "Maya Chen" in resp.text
    assert "Hunter K." in resp.text


@pytest.mark.asyncio
async def test_discover_page_shows_profiles(client):
    """GET /discover shows discoverable profiles."""
    # Sign up through discover
    resp = await client.post(
        "/discover/signup",
        data={
            "name": "Alice",
            "email": "alice@test.com",
            "bio": "CS student who loves building things",
            "looking_for": "Internships and collaborators",
        },
    )
    assert resp.status_code == 200
    # Extract code
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]

    # Verify
    resp = await client.post(
        "/discover/signup/verify",
        data={"email": "alice@test.com", "code": code},
    )
    assert resp.status_code == 200
    assert "You're live" in resp.text

    # Now the discover page should show Alice
    resp = await client.get("/discover")
    assert resp.status_code == 200
    assert "Alice" in resp.text
    assert "CS student" in resp.text
    assert "Internships" in resp.text
    assert "1" in resp.text  # "1 person discoverable"


# --- Signup flow ---


@pytest.mark.asyncio
async def test_discover_signup_form(client):
    """GET /discover/signup shows the signup form."""
    resp = await client.get("/discover/signup")
    assert resp.status_code == 200
    assert 'name="name"' in resp.text
    assert 'name="email"' in resp.text
    assert 'name="bio"' in resp.text
    assert 'name="looking_for"' in resp.text
    assert "Get discovered" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_sends_code(client):
    """POST /discover/signup sends a verification code."""
    resp = await client.post(
        "/discover/signup",
        data={
            "name": "Bob",
            "email": "bob@test.com",
            "bio": "Designer and maker",
            "looking_for": "Side projects",
        },
    )
    assert resp.status_code == 200
    assert 'name="code"' in resp.text
    assert "Dev mode" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_verify_makes_discoverable(client):
    """Full signup flow: form → code → verify → profile goes live."""
    # Sign up
    resp = await client.post(
        "/discover/signup",
        data={
            "name": "Charlie",
            "email": "charlie@test.com",
            "bio": "Full-stack developer",
            "looking_for": "Co-founders",
        },
    )
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]

    # Verify
    resp = await client.post(
        "/discover/signup/verify",
        data={"email": "charlie@test.com", "code": code},
    )
    assert resp.status_code == 200
    assert "You're live" in resp.text
    assert "Charlie" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_wrong_code(client):
    """POST /discover/signup/verify with wrong code shows error."""
    await client.post(
        "/discover/signup",
        data={
            "name": "Bad Code",
            "email": "badcode@discover.com",
            "bio": "Test",
            "looking_for": "Nothing",
        },
    )
    resp = await client.post(
        "/discover/signup/verify",
        data={"email": "badcode@discover.com", "code": "000000"},
    )
    assert resp.status_code == 200
    assert "Invalid verification code" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_existing_verified_user(client, registered_agent):
    """POST /discover/signup with existing verified email updates profile."""
    resp = await client.post(
        "/discover/signup",
        data={
            "name": "Mikey",
            "email": "mikey@test.com",
            "bio": "Building BotJoin",
            "looking_for": "Early users",
        },
    )
    assert resp.status_code == 200
    # Should show success since they're already verified
    assert "already on BotJoin" in resp.text


# --- Agent search API ---


async def _create_discoverable_profile(client, name, email, bio, looking_for):
    """Helper: create and verify a discover profile."""
    resp = await client.post(
        "/discover/signup",
        data={"name": name, "email": email, "bio": bio, "looking_for": looking_for},
    )
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]
    await client.post(
        "/discover/signup/verify",
        data={"email": email, "code": code},
    )


@pytest.mark.asyncio
async def test_discover_search_returns_profiles(client, registered_agent):
    """GET /discover/search returns discoverable profiles."""
    # Create a discoverable profile
    await _create_discoverable_profile(
        client, "Searchable Sam", "searchsam@test.com",
        "Python developer who loves AI", "Remote jobs",
    )

    # Search as an agent
    key = registered_agent["api_key"]
    resp = await client.get(
        "/discover/search?q=python",
        headers=auth_header(key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(p["name"] == "Searchable Sam" for p in data)


@pytest.mark.asyncio
async def test_discover_search_empty_query(client, registered_agent):
    """GET /discover/search with no query returns all profiles."""
    await _create_discoverable_profile(
        client, "Everyone", "everyone@test.com", "Visible", "Anything",
    )

    key = registered_agent["api_key"]
    resp = await client.get("/discover/search", headers=auth_header(key))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_discover_search_no_auth_fails(client):
    """GET /discover/search without auth returns 401."""
    resp = await client.get("/discover/search")
    assert resp.status_code in (401, 403)


# --- Agent profile detail ---


@pytest.mark.asyncio
async def test_discover_profile_detail(client, registered_agent):
    """GET /discover/profiles/{id} returns profile detail."""
    # Create a discoverable profile
    await _create_discoverable_profile(
        client, "Detail Dave", "dave@test.com", "DevOps engineer", "Startups",
    )

    # Search to get the ID
    key = registered_agent["api_key"]
    search_resp = await client.get(
        "/discover/search?q=dave",
        headers=auth_header(key),
    )
    profile_id = search_resp.json()[0]["id"]

    # Get detail
    resp = await client.get(
        f"/discover/profiles/{profile_id}",
        headers=auth_header(key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Dave"
    assert data["bio"] == "DevOps engineer"
    assert data["looking_for"] == "Startups"


@pytest.mark.asyncio
async def test_discover_profile_not_found(client, registered_agent):
    """GET /discover/profiles/{bad_id} returns 404."""
    key = registered_agent["api_key"]
    resp = await client.get(
        "/discover/profiles/nonexistent123",
        headers=auth_header(key),
    )
    assert resp.status_code == 404


# --- Agent outreach ---


@pytest.mark.asyncio
async def test_discover_reach_out(client, registered_agent):
    """POST /discover/profiles/{id}/reach-out sends outreach email."""
    # Create a target profile
    await _create_discoverable_profile(
        client, "Target Tina", "tina@test.com",
        "Marketing specialist", "Freelance gigs",
    )

    # Get the profile ID
    key = registered_agent["api_key"]
    search_resp = await client.get(
        "/discover/search?q=tina",
        headers=auth_header(key),
    )
    profile_id = search_resp.json()[0]["id"]

    # Reach out
    resp = await client.post(
        f"/discover/profiles/{profile_id}/reach-out",
        json={"message": "Hi Tina! My human is looking for marketing help."},
        headers=auth_header(key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert "Tina" in data["to"]


@pytest.mark.asyncio
async def test_discover_reach_out_to_self_fails(client, registered_agent):
    """Can't reach out to your own human's profile."""
    # Make the registered agent's human discoverable
    await client.post(
        "/discover/signup",
        data={
            "name": "Mikey",
            "email": "mikey@test.com",
            "bio": "Building things",
            "looking_for": "Friends",
        },
    )

    # Search for self
    key = registered_agent["api_key"]
    search_resp = await client.get(
        "/discover/search?q=mikey",
        headers=auth_header(key),
    )
    profiles = search_resp.json()
    # Find Mikey's profile (the registered agent's human)
    mikey_profile = next(p for p in profiles if p["name"] == "Mikey")

    # Try to reach out to self
    resp = await client.post(
        f"/discover/profiles/{mikey_profile['id']}/reach-out",
        json={"message": "Hello myself"},
        headers=auth_header(key),
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_discover_reach_out_no_auth_fails(client):
    """POST reach-out without auth returns 401."""
    resp = await client.post(
        "/discover/profiles/fake123/reach-out",
        json={"message": "Hello"},
    )
    assert resp.status_code in (401, 403)
