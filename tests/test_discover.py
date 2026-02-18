"""
Tests for the Discover feature.

GET  /surge                — Public browse page
GET  /surge/signup         — Signup form
POST /surge/signup         — Create profile + send verification
POST /surge/signup/verify  — Verify email, go live
GET  /discover/search         — Agent API: search profiles
GET  /discover/profiles/{id}  — Agent API: profile detail
POST /discover/profiles/{id}/reach-out — Agent API: outreach email
"""
import pytest
from tests.conftest import auth_header


# --- Public browse page ---


@pytest.mark.asyncio
async def test_discover_page_empty(client):
    """GET /surge with no real profiles shows browse grid with demo profiles."""
    resp = await client.get("/surge")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Should show profile card grid with demo profiles
    assert "browse-grid" in resp.text
    assert "profile-card" in resp.text
    assert "Maya Chen" in resp.text
    assert "Hunter K." in resp.text
    # Should have search input and signup CTA
    assert "browse-search" in resp.text
    assert "/surge/signup" in resp.text


@pytest.mark.asyncio
async def test_discover_page_shows_profiles(client):
    """GET /surge shows real profiles as cards when they exist."""
    # Sign up through discover
    resp = await client.post(
        "/surge/signup",
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

    # Verify — should redirect to /observe (auto-login)
    resp = await client.post(
        "/surge/signup/verify",
        data={"email": "alice@test.com", "code": code},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/observe"
    assert "botjoin_jwt" in resp.cookies

    # Now the browse page should show Alice as a card
    resp = await client.get("/surge")
    assert resp.status_code == 200
    assert "Alice" in resp.text
    assert "profile-card" in resp.text


# --- Signup flow ---


@pytest.mark.asyncio
async def test_discover_signup_form(client):
    """GET /surge/signup shows the module-style signup form."""
    resp = await client.get("/surge/signup")
    assert resp.status_code == 200
    assert 'name="name"' in resp.text
    assert 'name="email"' in resp.text
    assert 'name="bio"' in resp.text
    assert 'name="looking_for"' in resp.text
    # New bento module fields on the signup form
    assert 'name="superpower"' in resp.text
    assert 'name="current_project"' in resp.text
    assert 'name="fun_fact"' in resp.text
    assert "Build your profile" in resp.text
    assert "signup-module" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_sends_code(client):
    """POST /surge/signup sends a verification code."""
    resp = await client.post(
        "/surge/signup",
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
        "/surge/signup",
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

    # Verify — should auto-login and redirect to dashboard
    resp = await client.post(
        "/surge/signup/verify",
        data={"email": "charlie@test.com", "code": code},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/observe"
    assert "botjoin_jwt" in resp.cookies


@pytest.mark.asyncio
async def test_discover_signup_wrong_code(client):
    """POST /surge/signup/verify with wrong code shows error."""
    await client.post(
        "/surge/signup",
        data={
            "name": "Bad Code",
            "email": "badcode@discover.com",
            "bio": "Test",
            "looking_for": "Nothing",
        },
    )
    resp = await client.post(
        "/surge/signup/verify",
        data={"email": "badcode@discover.com", "code": "000000"},
    )
    assert resp.status_code == 200
    assert "Invalid verification code" in resp.text


@pytest.mark.asyncio
async def test_discover_signup_existing_verified_user(client, registered_agent):
    """POST /surge/signup with existing verified email updates profile."""
    resp = await client.post(
        "/surge/signup",
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
        "/surge/signup",
        data={"name": name, "email": email, "bio": bio, "looking_for": looking_for},
    )
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]
    await client.post(
        "/surge/signup/verify",
        data={"email": email, "code": code},
    )


@pytest.mark.asyncio
async def test_discover_search_returns_profiles(client, registered_agent):
    """GET /surge/search returns discoverable profiles."""
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
    """GET /surge/search with no query returns all profiles."""
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
    """GET /surge/search without auth returns 401."""
    resp = await client.get("/discover/search")
    assert resp.status_code in (401, 403)


# --- Agent profile detail ---


@pytest.mark.asyncio
async def test_discover_profile_detail(client, registered_agent):
    """GET /surge/profiles/{id} returns profile detail."""
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
    """GET /surge/profiles/{bad_id} returns 404."""
    key = registered_agent["api_key"]
    resp = await client.get(
        "/discover/profiles/nonexistent123",
        headers=auth_header(key),
    )
    assert resp.status_code == 404


# --- Agent outreach ---


@pytest.mark.asyncio
async def test_discover_reach_out(client, registered_agent):
    """POST /discover/profiles/{id}/reach-out stores outreach in DB."""
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
    assert "outreach_id" in data
    assert len(data["outreach_id"]) == 16


@pytest.mark.asyncio
async def test_discover_reach_out_to_self_fails(client, registered_agent):
    """Can't reach out to your own human's profile."""
    # Make the registered agent's human discoverable
    await client.post(
        "/surge/signup",
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


# --- Outreach reply polling ---


@pytest.mark.asyncio
async def test_discover_outreach_replies_empty(client, registered_agent):
    """GET /discover/outreach/replies with no replies returns empty list."""
    key = registered_agent["api_key"]
    resp = await client.get(
        "/discover/outreach/replies",
        headers=auth_header(key),
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_discover_outreach_replies_no_auth_fails(client):
    """GET /discover/outreach/replies without auth returns 401."""
    resp = await client.get("/discover/outreach/replies")
    assert resp.status_code in (401, 403)


# --- Browse page card grid ---


@pytest.mark.asyncio
async def test_surge_browse_has_search(client):
    """GET /surge shows a search bar for filtering profiles."""
    resp = await client.get("/surge")
    assert resp.status_code == 200
    assert "browse-search" in resp.text
    assert "Search people" in resp.text


@pytest.mark.asyncio
async def test_surge_browse_cards_link_to_profile(client):
    """Profile cards on /surge link to /surge/profile/."""
    resp = await client.get("/surge")
    assert resp.status_code == 200
    assert "/surge/profile/" in resp.text


# --- Bento profile detail page ---


@pytest.mark.asyncio
async def test_surge_profile_demo(client):
    """GET /surge/profile/demo-0 renders a demo profile bento page."""
    resp = await client.get("/surge/profile/demo-0")
    assert resp.status_code == 200
    assert "Maya Chen" in resp.text
    assert "bento-grid" in resp.text
    # Should show the superpower module
    assert "Superpower" in resp.text


@pytest.mark.asyncio
async def test_surge_profile_demo_with_fields(client):
    """Demo profile bento page shows filled-in bento modules."""
    resp = await client.get("/surge/profile/demo-0")
    assert resp.status_code == 200
    # Maya Chen has superpower, current_project, fun_fact, education
    assert "Making complex AI concepts feel simple" in resp.text
    assert "Working on" in resp.text
    assert "Education" in resp.text


@pytest.mark.asyncio
async def test_surge_profile_real_user(client):
    """GET /surge/profile/{id} renders a real user's bento page."""
    await _create_discoverable_profile(
        client, "Bento Bob", "bento@test.com",
        "Full-stack developer", "Collaborators",
    )
    # Browse to find the profile link
    resp = await client.get("/surge")
    assert "Bento Bob" in resp.text
    assert "/surge/profile/" in resp.text


@pytest.mark.asyncio
async def test_surge_profile_not_found(client):
    """GET /surge/profile/bad-id returns 404."""
    resp = await client.get("/surge/profile/nonexistent123")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_surge_profile_demo_out_of_range(client):
    """GET /surge/profile/demo-999 returns 404."""
    resp = await client.get("/surge/profile/demo-999")
    assert resp.status_code == 404


# --- Discover search page ---


@pytest.mark.asyncio
async def test_surge_discover_requires_auth(client):
    """/surge/discover without JWT redirects to /surge."""
    resp = await client.get("/surge/discover", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/surge"


@pytest.mark.asyncio
async def test_surge_discover_with_auth(client):
    """/surge/discover with JWT shows search page."""
    await _create_discoverable_profile(
        client, "Discoverable Dan", "dan@test.com",
        "Backend engineer", "Jobs",
    )
    # Log in as Dan via Surge signup
    resp = await client.post(
        "/surge/signup",
        data={"name": "Searcher", "email": "searcher@test.com", "bio": "Looking around", "looking_for": "Friends"},
    )
    html = resp.text
    code_start = html.find("your code is: ") + len("your code is: ")
    code = html[code_start:code_start + 6]
    resp = await client.post(
        "/surge/signup/verify",
        data={"email": "searcher@test.com", "code": code},
    )
    assert resp.status_code == 303
    jwt = resp.cookies.get("botjoin_jwt")
    assert jwt

    # Now visit /surge/discover with JWT cookie
    client.cookies.set("botjoin_jwt", jwt)
    resp = await client.get("/surge/discover")
    assert resp.status_code == 200
    assert "Discover people" in resp.text
    assert "Discoverable Dan" in resp.text


@pytest.mark.asyncio
async def test_surge_discover_search_filter(client):
    """/surge/discover?q= filters profiles by search query."""
    await _create_discoverable_profile(
        client, "Python Pete", "pete@test.com",
        "Python expert building APIs", "Jobs",
    )
    await _create_discoverable_profile(
        client, "Design Diana", "diana@test.com",
        "UI/UX designer", "Freelance gigs",
    )
    # Log in
    resp = await client.post(
        "/surge/signup",
        data={"name": "QQ", "email": "qq@test.com", "bio": "x", "looking_for": "x"},
    )
    code_start = resp.text.find("your code is: ") + len("your code is: ")
    code = resp.text[code_start:code_start + 6]
    resp = await client.post(
        "/surge/signup/verify",
        data={"email": "qq@test.com", "code": code},
    )
    jwt = resp.cookies.get("botjoin_jwt")
    client.cookies.set("botjoin_jwt", jwt)

    # Search for "python"
    resp = await client.get("/surge/discover?q=python")
    assert resp.status_code == 200
    assert "Python Pete" in resp.text
    # Diana should not appear (python not in her profile)
    assert "Design Diana" not in resp.text


# --- Agent API returns new fields ---


@pytest.mark.asyncio
async def test_discover_search_returns_new_fields(client, registered_agent):
    """GET /discover/search returns superpower and other new bento fields."""
    await _create_discoverable_profile(
        client, "Fields Test", "fields@test.com",
        "Developer", "Jobs",
    )
    key = registered_agent["api_key"]
    resp = await client.get(
        "/discover/search?q=fields",
        headers=auth_header(key),
    )
    data = resp.json()
    assert len(data) >= 1
    profile = next(p for p in data if p["name"] == "Fields Test")
    # New fields should be present in the response (None for unfilled)
    assert "superpower" in profile
    assert "current_project" in profile
    assert "need_help_with" in profile
    assert "dream_collab" in profile
    assert "fun_fact" in profile
    assert "education" in profile
    assert "photo_url" in profile


@pytest.mark.asyncio
async def test_discover_profile_detail_returns_new_fields(client, registered_agent):
    """GET /discover/profiles/{id} returns new bento fields."""
    await _create_discoverable_profile(
        client, "Detail Fields", "dfields@test.com",
        "Engineer", "Startups",
    )
    key = registered_agent["api_key"]
    search_resp = await client.get(
        "/discover/search?q=detail+fields",
        headers=auth_header(key),
    )
    profile_id = search_resp.json()[0]["id"]

    resp = await client.get(
        f"/discover/profiles/{profile_id}",
        headers=auth_header(key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "superpower" in data
    assert "current_project" in data
    assert "photo_url" in data
