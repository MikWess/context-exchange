"""
Discover — a public directory where anyone can put themselves out there
for AI agents to find. No agent required.

The viral loop:
1. Human signs up with name, email, bio, what they're looking for
2. Profile appears on the public discover page
3. Other people's agents search and find them
4. Agents reach out via email on behalf of their human

Routes:
GET  /discover                              — Browse profiles (HTML)
GET  /discover/signup                       — Profile creation form
POST /discover/signup                       — Create profile, send verification
POST /discover/signup/verify                — Verify email, go live
GET  /discover/search                       — Agent API: search profiles (JSON)
GET  /discover/profiles/{user_id}           — Agent API: profile detail (JSON)
POST /discover/profiles/{user_id}/reach-out — Agent API: send outreach email
"""
from datetime import timedelta
from html import escape as html_escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import get_current_agent
from src.app.config import EMAIL_VERIFICATION_EXPIRE_MINUTES
from src.app.database import get_db
from src.app.email import (
    generate_verification_code,
    get_base_url,
    is_dev_mode,
    send_outreach_email,
    send_verification_email,
    send_welcome_email,
)
from src.app.models import Agent, User, utcnow

router = APIRouter(tags=["discover"])


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

DISCOVER_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #fafafa;
    color: #1a1a1a;
}
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Nav */
.nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    max-width: 960px;
    margin: 0 auto;
    padding: 16px 20px;
}
.nav-brand {
    font-weight: 700;
    font-size: 15px;
    color: #111;
    text-decoration: none;
}
.nav-brand:hover { text-decoration: none; }
.nav-links {
    display: flex;
    gap: 16px;
    align-items: center;
    font-size: 14px;
}
.nav-links a { color: #6b7280; }
.nav-links a:hover { color: #111; text-decoration: none; }
.nav-cta {
    padding: 6px 16px;
    background: #111;
    color: #fff !important;
    border-radius: 6px;
    font-weight: 500;
    font-size: 14px;
}
.nav-cta:hover { background: #333; text-decoration: none; }

/* Hero */
.hero {
    text-align: center;
    padding: 60px 20px 40px;
    max-width: 640px;
    margin: 0 auto;
}
.hero h1 {
    font-size: 40px;
    font-weight: 700;
    letter-spacing: -1px;
    line-height: 1.1;
    margin-bottom: 12px;
}
.hero .sub {
    font-size: 18px;
    color: #6b7280;
    line-height: 1.6;
    margin-bottom: 28px;
}
.hero-cta {
    display: inline-block;
    padding: 12px 32px;
    background: #111;
    color: #fff;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    text-decoration: none;
    transition: background 0.15s;
}
.hero-cta:hover { background: #333; text-decoration: none; color: #fff; }

/* Search */
.search-bar {
    max-width: 960px;
    margin: 0 auto 32px;
    padding: 0 20px;
}
.search-bar input {
    width: 100%;
    padding: 12px 16px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    font-size: 15px;
    color: #1a1a1a;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.search-bar input:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.08);
}

/* Profile grid */
.grid {
    max-width: 960px;
    margin: 0 auto;
    padding: 0 20px 60px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
}

/* Profile card */
.card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 24px;
    transition: box-shadow 0.2s, border-color 0.2s;
}
.card:hover {
    border-color: #d1d5db;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.card-top {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}
.card-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 18px;
    flex-shrink: 0;
}
.card-name {
    font-size: 16px;
    font-weight: 600;
}
.card-bio {
    font-size: 14px;
    color: #374151;
    line-height: 1.5;
    margin-bottom: 12px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.card-looking {
    font-size: 13px;
    color: #6b7280;
    background: #f3f4f6;
    padding: 8px 12px;
    border-radius: 8px;
    line-height: 1.4;
}
.card-looking strong {
    color: #374151;
}

/* Empty state */
.empty {
    text-align: center;
    padding: 60px 20px;
    max-width: 480px;
    margin: 0 auto;
}
.empty h3 {
    font-size: 18px;
    margin-bottom: 8px;
    color: #374151;
}
.empty p {
    font-size: 14px;
    color: #9ca3af;
    margin-bottom: 20px;
}

/* Stats */
.stats {
    text-align: center;
    font-size: 14px;
    color: #9ca3af;
    margin-bottom: 24px;
}
.stats strong {
    color: #374151;
}

/* Form */
.form-container {
    max-width: 480px;
    margin: 40px auto;
    padding: 0 20px;
}
.form-box {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 32px;
}
.form-box h2 {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 6px;
}
.form-box .form-sub {
    font-size: 14px;
    color: #6b7280;
    margin-bottom: 24px;
}
.form-box label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    margin-bottom: 6px;
}
.form-box input, .form-box textarea {
    width: 100%;
    padding: 10px 14px;
    background: #fafafa;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    font-size: 15px;
    font-family: inherit;
    color: #1a1a1a;
    margin-bottom: 16px;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.form-box input:focus, .form-box textarea:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.08);
    background: #fff;
}
.form-box textarea {
    min-height: 80px;
    resize: vertical;
}
.form-box button {
    width: 100%;
    padding: 12px;
    background: #111;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
}
.form-box button:hover { background: #333; }
.form-hint {
    font-size: 12px;
    color: #9ca3af;
    text-align: center;
    margin-top: 12px;
}
.form-error {
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
}
.form-message {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    color: #16a34a;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
}

/* Success page */
.success {
    text-align: center;
    max-width: 480px;
    margin: 80px auto;
    padding: 0 20px;
}
.success h2 {
    font-size: 24px;
    font-weight: 700;
    margin-bottom: 8px;
}
.success p {
    font-size: 16px;
    color: #6b7280;
    margin-bottom: 24px;
    line-height: 1.6;
}
.success .btn {
    display: inline-block;
    padding: 12px 32px;
    background: #111;
    color: #fff;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    text-decoration: none;
}
.success .btn:hover { background: #333; text-decoration: none; color: #fff; }

/* Footer */
.footer {
    text-align: center;
    padding: 32px 20px;
    font-size: 13px;
    color: #c0c0c0;
}
.footer a { color: #9ca3af; text-decoration: none; }
.footer a:hover { color: #6b7280; }

@media (max-width: 640px) {
    .hero h1 { font-size: 28px; }
    .grid { grid-template-columns: 1fr; }
}
"""


def _page(title: str, body: str) -> str:
    """Wrap discover page content in a full HTML document."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>{DISCOVER_CSS}</style>
</head>
<body>
    <nav class="nav">
        <a href="/" class="nav-brand">BotJoin</a>
        <div class="nav-links">
            <a href="/discover">Discover</a>
            <a href="/observe">Sign in</a>
            <a href="/discover/signup" class="nav-cta">Get discovered</a>
        </div>
    </nav>
    {body}
    <div class="footer">
        <a href="/">BotJoin</a> &middot;
        <a href="/discover">Discover</a> &middot;
        <a href="/observe">Observer</a> &middot;
        <a href="/docs">API Docs</a>
    </div>
</body>
</html>"""


def _build_cards(profiles: list) -> str:
    """Build HTML for a list of profile cards."""
    cards = ""
    for p in profiles:
        initial = html_escape(p.name[0].upper()) if p.name else "?"
        name = html_escape(p.name)
        bio = html_escape(p.bio or "")
        if len(bio) > 200:
            bio = bio[:200] + "..."
        looking_for = html_escape(p.looking_for or "")

        looking_html = ""
        if looking_for:
            looking_html = (
                f'<div class="card-looking">'
                f"<strong>Looking for:</strong> {looking_for}"
                f"</div>"
            )

        cards += f"""
        <div class="card">
            <div class="card-top">
                <div class="card-avatar">{initial}</div>
                <div>
                    <div class="card-name">{name}</div>
                </div>
            </div>
            <div class="card-bio">{bio}</div>
            {looking_html}
        </div>"""
    return cards


def _signup_form_html(
    error: str = "",
    message: str = "",
    email: str = "",
    show_code_form: bool = False,
) -> str:
    """Build the signup or verification form HTML."""
    error_html = f'<div class="form-error">{html_escape(error)}</div>' if error else ""
    message_html = f'<div class="form-message">{html_escape(message)}</div>' if message else ""

    if show_code_form:
        form_html = f"""
        <form method="POST" action="/discover/signup/verify">
            <input type="hidden" name="email" value="{html_escape(email)}">
            <label for="code">Verification code</label>
            <input type="text" id="code" name="code" placeholder="123456"
                   maxlength="6" pattern="[0-9]{{6}}" autocomplete="one-time-code" autofocus required>
            <button type="submit">Verify</button>
            <p class="form-hint">Check your email for a 6-digit code.</p>
        </form>"""
    else:
        form_html = f"""
        <form method="POST" action="/discover/signup">
            <label for="name">Your name</label>
            <input type="text" id="name" name="name" placeholder="Your name" autofocus required>
            <label for="email">Email</label>
            <input type="email" id="email" name="email" placeholder="you@example.com"
                   value="{html_escape(email)}" required>
            <label for="bio">About you</label>
            <textarea id="bio" name="bio" placeholder="Tell people about yourself — what you do, what you're into..."></textarea>
            <label for="looking_for">What are you looking for?</label>
            <textarea id="looking_for" name="looking_for" placeholder="Internships, collaborators, friends with similar interests..."></textarea>
            <button type="submit">Get discovered</button>
            <p class="form-hint">We'll verify your email, then your profile goes live.</p>
        </form>"""

    body = f"""
    <div class="form-container">
        <div class="form-box">
            <h2>Put yourself out there</h2>
            <p class="form-sub">Create a profile and let AI agents from real people discover you. No agent required.</p>
            {error_html}
            {message_html}
            {form_html}
        </div>
    </div>"""
    return _page("BotJoin Discover — Sign up", body)


# ---------------------------------------------------------------------------
# Public HTML routes
# ---------------------------------------------------------------------------


@router.get("/discover", response_class=HTMLResponse)
async def discover_browse(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public discover page — browse people who put themselves out there.

    Input: nothing (public, no auth)
    Output: HTML page with profile cards grid
    """
    result = await db.execute(
        select(User)
        .where(User.discoverable == True)
        .order_by(User.created_at.desc())
    )
    profiles = result.scalars().all()
    count = len(profiles)

    hero = """
    <div class="hero">
        <h1>Put yourself out there</h1>
        <p class="sub">
            Create a profile and let AI agents from real people discover you.
            No agent required &mdash; just be you.
        </p>
        <a href="/discover/signup" class="hero-cta">Get discovered</a>
    </div>"""

    if count == 0:
        main_content = """
        <div class="empty">
            <h3>Be the first</h3>
            <p>No one has put themselves out there yet. You could be first.</p>
            <a href="/discover/signup" class="hero-cta" style="font-size:14px;padding:10px 24px;">Get discovered</a>
        </div>"""
    else:
        people = "person" if count == 1 else "people"
        stats = f'<div class="stats"><strong>{count}</strong> {people} discoverable</div>'
        search = """
        <div class="search-bar">
            <input type="text" id="discover-search" placeholder="Search people, interests, skills..."
                   oninput="filterCards(this.value)">
        </div>"""
        cards = _build_cards(profiles)
        main_content = f"""
        {stats}
        {search}
        <div class="grid" id="discover-grid">
            {cards}
        </div>
        <script>
        function filterCards(query) {{
            var q = query.toLowerCase();
            var cards = document.querySelectorAll('.card');
            cards.forEach(function(card) {{
                var text = card.textContent.toLowerCase();
                card.style.display = text.includes(q) ? '' : 'none';
            }});
        }}
        </script>"""

    return HTMLResponse(_page("BotJoin Discover", hero + main_content))


@router.get("/discover/signup", response_class=HTMLResponse)
async def discover_signup_page():
    """
    Show the discover signup form.

    Input: nothing
    Output: HTML page with name, email, bio, looking_for form
    """
    return HTMLResponse(_signup_form_html())


@router.post("/discover/signup", response_class=HTMLResponse)
async def discover_signup(
    name: str = Form(...),
    email: str = Form(...),
    bio: str = Form(""),
    looking_for: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle discover signup form. Creates or updates a user and sends verification.

    Input: name, email, bio, looking_for (form POST)
    Output: HTML page with verification code form
    """
    # Check if email already belongs to a verified user
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing and existing.verified:
        # Already verified — set their profile fields and mark discoverable
        existing.bio = bio or existing.bio
        existing.looking_for = looking_for or existing.looking_for
        existing.discoverable = True
        return HTMLResponse(_page("BotJoin Discover — Sign up", """
        <div class="success">
            <h2>You're already on BotJoin!</h2>
            <p>We've updated your Discover profile. You're now discoverable.</p>
            <a href="/discover" class="btn">View Discover</a>
        </div>"""))

    # Generate verification code
    code = generate_verification_code()
    expires_at = utcnow() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES)

    if existing and not existing.verified:
        # Unverified — update fields and resend code
        existing.name = name
        existing.bio = bio
        existing.looking_for = looking_for
        existing.verification_code = code
        existing.verification_expires_at = expires_at
    else:
        # New user
        user = User(
            email=email,
            name=name,
            bio=bio,
            looking_for=looking_for,
            verified=False,
            verification_code=code,
            verification_expires_at=expires_at,
        )
        db.add(user)
        await db.flush()

    # Send verification email
    await send_verification_email(email, code)

    # In dev mode, show the code
    message = ""
    if is_dev_mode():
        message = f"Dev mode — your code is: {code}"

    return HTMLResponse(_signup_form_html(
        message=message,
        email=email,
        show_code_form=True,
    ))


@router.post("/discover/signup/verify", response_class=HTMLResponse)
async def discover_signup_verify(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify email and make profile discoverable.

    Input: email + code (form POST)
    Output: success page or error
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return HTMLResponse(_signup_form_html(
            error="Something went wrong. Please try again.",
        ))

    if user.verified and user.discoverable:
        # Already done (double-submit)
        return HTMLResponse(_page("BotJoin Discover", """
        <div class="success">
            <h2>You're already live!</h2>
            <p>Your profile is on BotJoin Discover.</p>
            <a href="/discover" class="btn">View Discover</a>
        </div>"""))

    # Check the code
    if user.verification_code != code:
        return HTMLResponse(_signup_form_html(
            error="Invalid verification code.",
            email=email,
            show_code_form=True,
        ))

    # Check expiry
    if user.verification_expires_at and utcnow() > user.verification_expires_at:
        return HTMLResponse(_signup_form_html(
            error="Code expired. Please try again.",
            email=email,
        ))

    # Mark verified and discoverable
    user.verified = True
    user.discoverable = True
    user.verification_code = None
    user.verification_expires_at = None

    # Send welcome email
    base_url = get_base_url(request)
    await send_welcome_email(email, user.name, base_url)

    return HTMLResponse(_page("BotJoin Discover", f"""
    <div class="success">
        <h2>You're live!</h2>
        <p>{html_escape(user.name)}, your profile is now on BotJoin Discover.
        AI agents from real people can find you and reach out.</p>
        <a href="/discover" class="btn">View Discover</a>
    </div>"""))


# ---------------------------------------------------------------------------
# Agent API routes (JSON)
# ---------------------------------------------------------------------------


@router.get("/discover/search")
async def discover_search(
    q: str = "",
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Search discoverable profiles. Requires agent API key auth.

    Input: q (search query, optional — returns all if empty)
    Output: JSON array of matching profiles
    """
    query = select(User).where(User.discoverable == True)

    if q:
        # Simple text search across name, bio, interests, looking_for
        pattern = f"%{q}%"
        query = query.where(
            or_(
                User.name.ilike(pattern),
                User.bio.ilike(pattern),
                User.interests.ilike(pattern),
                User.looking_for.ilike(pattern),
            )
        )

    query = query.order_by(User.created_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "bio": p.bio,
            "interests": p.interests,
            "looking_for": p.looking_for,
        }
        for p in profiles
    ]


@router.get("/discover/profiles/{user_id}")
async def discover_profile(
    user_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single discoverable profile. Requires agent API key auth.

    Input: user_id (path param)
    Output: JSON profile object
    """
    result = await db.execute(
        select(User).where(User.id == user_id, User.discoverable == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": user.id,
        "name": user.name,
        "bio": user.bio,
        "interests": user.interests,
        "looking_for": user.looking_for,
    }


class ReachOutRequest(BaseModel):
    """Body for the reach-out endpoint."""
    message: str


@router.post("/discover/profiles/{user_id}/reach-out")
async def discover_reach_out(
    user_id: str,
    body: ReachOutRequest,
    request: Request,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Agent reaches out to a discovered person via email.

    Input: user_id (path), message (JSON body), agent API key (header)
    Output: confirmation that outreach email was sent

    The discovered person receives an email with the agent's message
    and links to set up their own agent or browse Discover.
    """
    # Find the target profile
    result = await db.execute(
        select(User).where(User.id == user_id, User.discoverable == True)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Validate message
    if len(body.message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 chars)")

    # Get the agent's human
    result = await db.execute(select(User).where(User.id == agent.user_id))
    agent_human = result.scalar_one()

    # Don't let agents reach out to their own human
    if target.id == agent_human.id:
        raise HTTPException(status_code=400, detail="Can't reach out to yourself")

    # Send outreach email
    base_url = get_base_url(request)
    sent = await send_outreach_email(
        to_email=target.email,
        to_name=target.name,
        from_human_name=agent_human.name,
        from_agent_name=agent.name,
        message=body.message,
        base_url=base_url,
    )

    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send outreach email")

    return {
        "status": "sent",
        "to": target.name,
        "message": f"Outreach email sent to {target.name}",
    }
